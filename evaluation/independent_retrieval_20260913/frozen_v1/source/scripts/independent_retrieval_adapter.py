"""Controlled independent retrieval around the unchanged Conversation pipeline.

The production router couples memory access to response framing. This explicit
experiment adapter separates authorization, access selection, and shared answer
framing. OFF cannot access the store; ALWAYS attempts authorized retrieval even
on general questions; SELECTIVE runs the current OptimizedMemoryOnlyRouter.
All conditions frame responses using the same deterministic intent annotation
or actual request-linked evidence, never a classifier-only annotation. Thus an
unrelated neighbor cannot force a general question into personal abstention.

No scoring references enter this module. The application still performs its
own evidence linking, limits, composition, citation and freshness validation.
Only the fixed generator can be called, including helpers and failure paths.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from time import perf_counter_ns

from oline_hri.conversation import Conversation, MAX_RETRIEVED_MEMORIES, _required_memory_ids
from oline_hri.evaluation_systems import OptimizedMemoryOnlyRouter
from oline_hri.memory import MemoryStore, is_question_shaped_memory
from oline_hri.ollama import ChatResult
from oline_hri.retrieval import HybridRetriever
from oline_hri.routing import RouteDecision, RoutingResult, memory_intent_policy, privacy_abstention
from oline_hri.timing import trace_span


SMALL, LARGE = "qwen3:0.6b", "qwen3:1.7b"
POLICIES = ("off", "always", "selective")
ADAPTER_POLICY = {
    "version": "independent_retrieval_v1",
    "authorization": "request consent AND active profile AND production privacy gate",
    "selective_access": "current OptimizedMemoryOnlyRouter on sole model",
    "answer_framing": "shared deterministic personal intent OR request-linked eligible evidence",
    "ambiguous_answer_framing": "no personal framing without linked evidence",
    "retrieval": "production HybridRetriever; at most one real retrieval per request",
    "conversation": "unchanged production evidence limits, helpers and validators",
    "grounded_composition": True,
    "history": "new Conversation for every request",
    "fallback": "fixed_generator_model forbids cross-model fallback",
    "logical_roles": "condition sole model occupies common logical small role; unused other tag occupies both large roles",
    "inspection_definition": "unique eligible record IDs materialized during exact semantic scans plus keyword results; database/index internals are not counted",
}


def _instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _match_dict(match):
    return {**asdict(match), "sources": list(match.sources)}


class InspectedMemoryStore(MemoryStore):
    """Observe real search reads without issuing any additional memory query.

The exact cosine search materializes all eligible vectors/records twice, once
before query embedding and once for final scoring. Both snapshots are logged;
the union counts unique inspected records, not the top-20 returned candidates.
Profile, consent, lifecycle and temporal SQL filters remain untouched.
"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset_inspection()

    def reset_inspection(self):
        self.inspection_events = []
        self.search_calls = []
        self._inspection_phase = None

    def _embedding_rows(self, *args, **kwargs):
        rows = super()._embedding_rows(*args, **kwargs)
        if self._inspection_phase == "semantic":
            self.inspection_events.append({
                "stage": "semantic_eligible_snapshot",
                "ids": [item.id for item in rows.items],
                "eligible_count": rows.status.eligible,
                "complete": rows.status.complete,
                "reference_time": kwargs.get("reference_time"),
            })
        return rows

    def search_semantic(self, query, *, limit=5):
        return self._observe_search("semantic", super().search_semantic, query, limit=limit)

    def search_keywords(self, query, *, limit=5, as_of=None):
        return self._observe_search("keyword", super().search_keywords, query, limit=limit, as_of=as_of)

    def _observe_search(self, name, function, query, **kwargs):
        started = perf_counter_ns()
        call = {"source": name, "query": query, "limit": kwargs["limit"], "status": "error"}
        previous = self._inspection_phase
        self._inspection_phase = name
        try:
            results = function(query, **kwargs)
            call.update(status="ok", results=[asdict(item) for item in results])
            if name == "keyword":
                self.inspection_events.append({"stage": "keyword_returned_records",
                                               "ids": [item.memory.id for item in results]})
            return results
        except BaseException as error:
            call.update(error=type(error).__name__, message=str(error))
            raise
        finally:
            self._inspection_phase = previous
            call["wall_ns"] = perf_counter_ns() - started
            self.search_calls.append(call)


def open_snapshot(path, seed, embedder=None):
    """Open an existing prepared copy with a fixed evaluation clock."""
    if not Path(path).is_file():
        raise ValueError("prepared snapshot does not exist")
    evaluation_at = _instant(seed["evaluation_at"])
    return InspectedMemoryStore(path, profile_id=seed["profile_id"],
                                clock=lambda: evaluation_at, embedder=embedder,
                                retention_days=seed.get("retention_days"))


def snapshot_digest(path):
    """Hash authoritative logical contents, including stored embedding bytes."""
    content = {}
    with sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True) as db:
        names = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            rows = db.execute(f"SELECT * FROM {quoted}").fetchall()
            content[name] = sorted(
                [[{"blob_hex": value.hex()} if isinstance(value, bytes) else value for value in row]
                 for row in rows], key=lambda row: json.dumps(row, sort_keys=True))
    return sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def materialize_snapshot(path, seed, embedder=None):
    """Apply all confirmed fictional lifecycle events before freezing one DB.

Other profiles are stored in the same database, using the same implementation,
so wrong-profile exclusion exercises the real query filters. Retention cleanup
is completed at the frozen evaluation instant for every profile before return.
"""
    path = Path(path)
    if path.exists():
        raise ValueError("refusing to overwrite a memory snapshot")
    setup = {"profile_id": seed["profile_id"], "evaluation_at": seed["evaluation_at"],
             "profiles": [], "events": []}
    profiles = [seed, *seed.get("other_profile_seeds", ())]
    if len({profile["profile_id"] for profile in profiles}) != len(profiles):
        raise ValueError("snapshot profiles must be unique")
    all_ids = [event["memory_id"] for profile in profiles for event in profile["events"]
               if event["operation"] in {"remember", "correct"}]
    if len(set(all_ids)) != len(all_ids):
        raise ValueError("snapshot memory IDs must be globally unique")
    for profile in profiles:
        clock_value = [_instant(seed["evaluation_at"])]
        generated = iter(event["memory_id"] for event in profile["events"]
                         if event["operation"] in {"remember", "correct"})
        store = InspectedMemoryStore(path, profile_id=profile["profile_id"],
                                     clock=lambda: clock_value[0],
                                     memory_id_factory=lambda: next(generated), embedder=embedder,
                                     retention_days=seed.get("retention_days"))
        for event in profile["events"]:
            clock_value[0] = _instant(event["at"])
            if clock_value[0] > _instant(seed["evaluation_at"]):
                raise ValueError("lifecycle event occurs after evaluation instant")
            if event["operation"] == "remember":
                item = store.remember(event["canonical_text"], kind=event["kind"],
                                      source_turn_id=event["id"],
                                      **{key: event[key] for key in (
                                          "event_time", "valid_from", "valid_until", "retention_until",
                                          "sensitivity", "importance") if key in event})
                result = item.to_dict()
                if item.id != event["memory_id"]:
                    raise ValueError("memory ID replay diverged")
            elif event["operation"] == "correct":
                item = store.correct(event["target_id"], event["canonical_text"])
                result = item.to_dict()
                if item.id != event["memory_id"]:
                    raise ValueError("correction ID replay diverged")
            elif event["operation"] == "forget":
                result = list(store.forget(event["target_id"]))
            else:
                raise ValueError("unsupported lifecycle operation")
            setup["events"].append({"profile_id": profile["profile_id"], "event": event, "result": result})
        if next(generated, None) is not None:
            raise ValueError("memory ID replay incomplete")
        clock_value[0] = _instant(seed["evaluation_at"])
        expired = store.purge_expired()
        index = store.embedding_index_status() if embedder is not None else None
        if index is not None and not index.complete:
            raise ValueError("prepared semantic index is incomplete")
        setup["profiles"].append({"profile_id": profile["profile_id"],
                                  "purged_retention_ids": list(expired),
                                  "records": [item.to_dict() for item in store.list_memories(include_inactive=True)],
                                  "embedding_index": asdict(index) if index is not None else None})
    store = open_snapshot(path, seed, embedder)
    setup["logical_sha256"] = snapshot_digest(path)
    return store, setup


class _FixedBackend:
    def __init__(self, delegate, owner):
        self.delegate, self.owner = delegate, owner

    @property
    def resident_model(self):
        return getattr(self.delegate, "resident_model", None)

    def chat(self, model, messages, **kwargs):
        if model != self.owner.model:
            raise RuntimeError("independent-retrieval attempted a non-condition model")
        fields = (kwargs.get("response_format") or {}).get("properties", {})
        purpose = "generation" if "speech" in fields else "memory_selector"
        if purpose == "memory_selector" and self.owner.policy != "selective":
            raise RuntimeError("classifier is forbidden outside SELECTIVE")
        call = {"purpose": purpose, "requested_model": model, "status": "error",
                "messages": [message.to_dict() for message in messages],
                "options": deepcopy(kwargs)}
        self.owner.calls.append(call)
        started = perf_counter_ns()
        if purpose == "generation":
            self.owner.supplied_ids = tuple(fields.get("memory_used", {}).get("items", {}).get("enum", ()))
            self.owner.speech_enum = fields.get("speech", {}).get("enum")
            if self.owner.policy == "off" and self.owner.supplied_ids:
                raise RuntimeError("OFF supplied personal evidence")
        try:
            result = self.delegate.chat(model, messages, **kwargs)
            if not isinstance(result, ChatResult) or result.model != self.owner.model:
                raise RuntimeError("independent-retrieval received a non-condition model")
            call.update(status="ok", actual_model=result.model, raw_generation=asdict(result))
            return result
        except BaseException as error:
            call.update(error=type(error).__name__, message=str(error))
            raise
        finally:
            call["wall_ns"] = perf_counter_ns() - started


class IndependentRetrievalAdapter:
    """Single-request adapter; retain this object to archive traces on failure."""

    def __init__(self, backend, store, *, model, policy, consent_authorized, profile_id):
        if policy not in POLICIES or model not in (SMALL, LARGE):
            raise ValueError("unknown retrieval policy or generator")
        if type(consent_authorized) is not bool:
            raise ValueError("request consent must be explicitly boolean")
        if not isinstance(store, InspectedMemoryStore):
            raise TypeError("experiment requires an InspectedMemoryStore")
        self.store, self.model, self.policy = store, model, policy
        self.consent_authorized, self.profile_id = consent_authorized, profile_id
        self.backend = _FixedBackend(backend, self)
        self.delegate = HybridRetriever(store)
        self.calls, self.retrieval_calls, self.freshness_calls = [], [], []
        self.selection, self.authorization, self.framing = {}, {}, {}
        self.matches, self.supplied_ids, self.speech_enum = (), (), None
        self._query, self._used = None, False
        self.route_result = None
        self.cached_retrieval_calls = 0
        self.store.reset_inspection()

    def send(self, prompt, config):
        if self._used:
            raise RuntimeError("a fresh adapter and conversation are required per request")
        self._used = True
        # Conversation branches on logical roles when constructing general
        # instructions. Normalize the sole generator to one common role in
        # both model conditions, so equal evidence yields identical prompts.
        # The other logical tag is never callable through _FixedBackend.
        unused_peer = LARGE if self.model == SMALL else SMALL
        conversation = Conversation(
            self.backend, system_prompt=config.conversation.system_prompt,
            router=self, retriever=self, small_model=self.model, general_large_model=unused_peer,
            large_model=unused_peer, context_length=config.generation.context_length,
            max_output_tokens=config.generation.max_output_tokens,
            grounded_composition=True, fixed_generator_model=self.model)
        return conversation.send(prompt)

    def route(self, text, *, history=()):
        if history:
            raise RuntimeError("independent retrieval requires fresh history")
        self._query = text
        started = perf_counter_ns()
        with trace_span("retrieval_authorization"):
            privacy = privacy_abstention(text)
            self.authorization = {"consent_authorized": self.consent_authorized,
                "requested_profile": self.profile_id, "store_profile": self.store.profile_id,
                "profile_matches": self.profile_id == self.store.profile_id,
                "privacy_abstention": privacy,
                "authorized": self.consent_authorized and self.profile_id == self.store.profile_id and privacy is None}
        self.authorization["wall_ns"] = perf_counter_ns() - started
        started = perf_counter_ns()
        with trace_span("shared_response_intent"):
            common_intent, common_source = memory_intent_policy(text, ())
        self.framing = {"deterministic_intent": common_intent, "deterministic_source": common_source,
                        "intent_wall_ns": perf_counter_ns() - started}
        started = perf_counter_ns()
        self.selection = {"policy": self.policy, "retrieval_selected": False,
                          "source": "authorization_denied", "route": None}
        try:
            with trace_span("memory_access_selection", policy=self.policy):
                if self.authorization["authorized"]:
                    if self.policy == "selective":
                        route = OptimizedMemoryOnlyRouter(self.backend, model=self.model,
                            fixed_model_size="small").route(text)
                        self.selection.update(retrieval_selected=route.decision.memory_required,
                                              source=route.memory_decision_source, route=asdict(route))
                    else:
                        self.selection.update(retrieval_selected=self.policy == "always",
                                              source="policy_" + self.policy)
        finally:
            self.selection["wall_ns"] = perf_counter_ns() - started
            self.selection["classifier_calls"] = sum(call["purpose"] == "memory_selector" for call in self.calls)
        if self.selection["retrieval_selected"]:
            started = perf_counter_ns()
            record = {"query": text, "limit": MAX_RETRIEVED_MEMORIES, "status": "error"}
            self.retrieval_calls.append(record)
            try:
                with trace_span("independent_retrieval"):
                    self.matches = self.delegate.retrieve(text, limit=MAX_RETRIEVED_MEMORIES)
                record.update(status="ok", matches=[_match_dict(match) for match in self.matches])
            except BaseException as error:
                record.update(error=type(error).__name__, message=str(error))
                raise
            finally:
                record["wall_ns"] = perf_counter_ns() - started
        started = perf_counter_ns()
        with trace_span("response_evidence_linking"):
            linked = _required_memory_ids(tuple(match for match in self.matches
                if not is_question_shaped_memory(match.memory.canonical_text)), text)
        personal_frame = common_intent is True or bool(linked)
        self.framing.update(linked_ids=list(linked), evidence_linking_wall_ns=perf_counter_ns() - started,
                            memory_requested=personal_frame,
                            rule="deterministic_intent_is_true_or_request_linked_evidence")
        resident = self.backend.resident_model
        self.route_result = RoutingResult(
            decision=RouteDecision(personal_frame, "small"),
            memory_required_generation=None, model_size_generation=None,
            memory_decision_source="policy_privacy" if privacy else "policy_personal" if personal_frame else "policy_general",
            model_size_decision_source="fixed_generator", policy="fixed_memory_v1",
            fixed_generator_model=self.model, resident_model=resident if resident == self.model else None)
        return self.route_result

    def retrieve(self, query, *, limit=3):
        """Serve only this request's already-authorized cached result."""
        if query != self._query or limit != MAX_RETRIEVED_MEMORIES:
            raise RuntimeError("unexpected retrieval call or changed evidence limit")
        self.cached_retrieval_calls += 1
        if self.cached_retrieval_calls != 1:
            raise RuntimeError("Conversation requested evidence more than once")
        return self.matches

    def is_current(self, matches):
        started = perf_counter_ns()
        record = {"ids": [match.memory.id for match in matches], "status": "error"}
        self.freshness_calls.append(record)
        try:
            current = self.delegate.is_current(matches)
            record.update(status="ok", current=current)
            return current
        except BaseException as error:
            record.update(error=type(error).__name__, message=str(error))
            raise
        finally:
            record["wall_ns"] = perf_counter_ns() - started

    def to_dict(self, reply=None):
        supplied = {match.memory.id: match for match in self.matches}
        inspected = sorted({identifier for event in self.store.inspection_events for identifier in event["ids"]})
        return deepcopy({
            "policy": self.policy, "model": self.model, "authorization": self.authorization,
            "selection": self.selection, "framing": self.framing, "calls": self.calls,
            "retrieval_calls": self.retrieval_calls, "retrieval_attempts": len(self.retrieval_calls),
            "cached_retrieval_calls": self.cached_retrieval_calls,
            "inspection_events": self.store.inspection_events, "search_calls": self.store.search_calls,
            "inspected_ids": inspected, "inspected_count": len(inspected),
            "retrieved_ids": [match.memory.id for match in self.matches],
            "supplied_ids": list(self.supplied_ids),
            "supplied_evidence": [_match_dict(supplied[identifier]) for identifier in self.supplied_ids],
            "freshness_calls": self.freshness_calls,
            "helper_behavior": {"grounded_composition_enabled": True,
                "personal_evidence_available": bool(self.supplied_ids), "speech_enum": self.speech_enum,
                "answer_constraint": reply.answer_constraint if reply is not None else None,
                "generation_policy": reply.generation_policy if reply is not None else None,
                "response_transform": reply.response_transform if reply is not None else None,
                "reference_ids": list(reply.reference_ids) if reply is not None else None},
        })
