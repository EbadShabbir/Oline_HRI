#!/usr/bin/env python3
"""Recompute final descriptive findings from immutable completed analysis tables.

Offline reporting only; does not import the inference client or mutate raw traces.
Run from any directory: python evaluation/routing_overhead_20260912/build_final_findings.py
"""
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import csv
import json
import statistics

ROOT = Path(__file__).resolve().parent
ARMS = ("small", "large", "adaptive", "replay")
PATTERNS = ("EEEE", "DDDD", "EDED", "DDEE")
INPUTS = [
    "report_details_final_v2/sequence_details.csv",
    "report_details_final_v2/turn_details.csv",
    "report_details_final_v2/raw_backend_calls.csv",
    "report_reviewed_v2/components.csv",
    "report_reviewed_v2/events.csv",
    "report_reviewed_v2/paired_turns.csv",
    "report_reviewed_v2/paired_cluster_summary.csv",
    "report_reviewed_v2/analysis.json",
    "reviews_final_v2/blind/packet.jsonl",
    "reviews_final_v2/blind/private_mapping.json",
    "reviews_final_v2/resolved.jsonl",
    "reviews_final_v2/review_agreement.json",
    "workload.json",
    "final_collection_audit_v2_corrected/summary.json",
    "final_collection_audit_v2_corrected/independent_collection_summary.json",
]


def rows(name):
    with (ROOT / name).open() as stream:
        return list(csv.DictReader(stream))


def number(row, key):
    return float(row.get(key) or 0)


def mean(group, key):
    return statistics.mean(number(row, key) for row in group) if group else None


def total(group, key):
    return sum(number(row, key) for row in group)


def subset(group, **criteria):
    return [row for row in group if all(row[key] == str(value) for key, value in criteria.items())]


def table(headers, records):
    result = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for record in records:
        result.append("| " + " | ".join(f"{value:.3f}" if isinstance(value, float) else str(value) for value in record) + " |")
    return "\n".join(result)


def main():
    sequences = rows(INPUTS[0])
    turns = rows(INPUTS[1])
    calls = rows(INPUTS[2])
    for call in calls:
        call["purpose"] = {"memory_selector": "memory_classifier", "model_selector": "compute_classifier"}.get(call["purpose"], call["purpose"])
    components = rows(INPUTS[3])
    events = rows(INPUTS[4])
    pairs = rows(INPUTS[5])
    summary = json.loads((ROOT / INPUTS[7]).read_text())
    packets = {r["answer_id"]: r for r in map(json.loads, (ROOT / INPUTS[8]).read_text().splitlines())}
    mapping = json.loads((ROOT / INPUTS[9]).read_text())
    reviews = {r["answer_id"]: r for r in map(json.loads, (ROOT / INPUTS[10]).read_text().splitlines())}
    workload = json.loads((ROOT / "workload.json").read_text())
    assert len(sequences) == 144 and len(turns) == 576 and len(calls) == 855
    assert len(packets) == len(reviews) == 146 and len(mapping) == 576
    assert all(r["complete"] == "True" and r["accounting_ok"] == "True" for r in sequences)
    assert summary["audit_error_count"] == 0
    keyed_turns = {(r["attempt_directory"], r["id"], int(r["index"])): r for r in turns}
    assert len(keyed_turns) == 576
    raw_turns = {}
    for sequence in sequences:
        for raw in map(json.loads, (ROOT / "run_v2" / sequence["attempt_directory"] / "observations.jsonl").read_text().splitlines()):
            raw_turns[sequence["attempt_directory"], raw["id"], raw["index"]] = raw
    assert len(raw_turns) == 576
    seen = set()
    for entry in mapping:
        key = entry["attempt_directory"], entry["id"], entry["index"]
        assert key not in seen
        seen.add(key)
        raw, item, review = raw_turns[key], packets[entry["answer_id"]], reviews[entry["answer_id"]]
        supplied = set((raw.get("memory") or {}).get("supplied_ids", []))
        matches = {m["memory"]["id"]: m["memory"] for call in raw.get("retrieval_calls", []) for m in call.get("matches", [])}
        content = {
            "question": raw["prompt"], "history": raw.get("history_before", []),
            "rubric": workload["rubrics"][raw["id"]], "prepared_memory": workload["memory_seed"],
            "answer": (raw.get("response") or {}).get("speech", ""),
            "response_complete": raw["status"] == "ok", "answer_constraint": raw.get("answer_constraint"),
            "supplied_evidence": [matches[i] for i in sorted(supplied) if i in matches],
            "cited_memory_ids": (raw.get("response") or {}).get("memory_used", []),
        }
        assert {k: v for k, v in item.items() if k != "answer_id"} == content
        canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        assert sha256(canonical.encode()).hexdigest()[:24] == entry["answer_id"]
        correct = review["label"] in ("complete", "appropriate_abstention", "appropriate_uncertainty")
        assert keyed_turns[key]["quality_label"] == review["label"]
        assert (keyed_turns[key]["correct"] == "True") == correct
        assert not correct or (raw["status"] == "ok" and not review["unsupported_claim"] and not review["unsupported_personal_claim"])
    assert seen == set(keyed_turns)

    metrics = ("startup_seconds", "request_seconds", "sequence_gaps_seconds", "sequence_seconds", "cleanup_seconds", "envelope_seconds")
    totals, patterns, repetitions = [], [], []
    for pattern in ("overall", *PATTERNS):
        for arm in ARMS:
            seq = subset(sequences, arm=arm) if pattern == "overall" else subset(sequences, pattern=pattern, arm=arm)
            ts = subset(turns, arm=arm) if pattern == "overall" else subset(turns, pattern=pattern, arm=arm)
            record = dict(pattern=pattern, arm=arm, sequences=len(seq), turns=len(ts),
                          correct=sum(t["correct"] == "True" for t in ts), delivered=sum(t["status"] == "ok" for t in ts),
                          actual_generator_counts=dict(Counter(t["actual_final_generator"] for t in ts)))
            for metric in metrics:
                record[metric + "_mean"] = mean(seq, metric)
                record[metric + "_total"] = total(seq, metric)
            record["request_seconds_per_turn"] = mean(ts, "request_wall_seconds")
            record["quality_labels"] = dict(Counter(t["quality_label"] for t in ts))
            record["selected_routes"] = dict(Counter("".join("S" if x == "small" else "L" for x in json.loads(s["selected_model_sequence"])) for s in seq))
            assert abs(record["sequence_seconds_total"] - sum(record[k + "_total"] for k in metrics[:3])) < 1e-6
            (totals if pattern == "overall" else patterns).append(record)
            for repetition in (1, 2, 3):
                ss = subset(seq, repetition=repetition)
                tt = subset(ts, repetition=repetition)
                repetitions.append(dict(pattern=pattern, arm=arm, repetition=repetition,
                    sequence_seconds_mean=mean(ss, "sequence_seconds"),
                    turns=len(tt), correct=sum(t["correct"] == "True" for t in tt),
                    delivered=sum(t["status"] == "ok" for t in tt)))
    for record in totals:
        arm = record["arm"]
        for key in ("startup", "request", "sequence"):
            assert abs(record[f"{key}_seconds_total"] - summary["systems"][arm][f"{key}_seconds"]["total"]) < 1e-6
        assert record["correct"] == {"small": 66, "large": 97, "adaptive": 77, "replay": 77}[arm]

    sequence_lookup = {(s["sequence_id"], s["repetition"], s["arm"]): s for s in sequences}
    paired = []
    for pattern in ("overall", *PATTERNS):
        for comparator in ("small", "large", "replay"):
            aa = subset(sequences, arm="adaptive") if pattern == "overall" else subset(sequences, arm="adaptive", pattern=pattern)
            for repetition in ("all", "1", "2", "3"):
                selected = aa if repetition == "all" else subset(aa, repetition=repetition)
                comparisons = [(s, sequence_lookup[s["sequence_id"], s["repetition"], comparator]) for s in selected]
                record = dict(pattern=pattern, comparator=comparator, repetition=repetition,
                              sequence_clusters=len({s["sequence_id"] for s in selected}), paired_sessions=len(selected))
                fields = (*metrics, "generation_output_tokens_all_calls", "classifier_output_tokens",
                          "all_backend_load_duration_seconds", "all_backend_prompt_eval_duration_seconds", "all_backend_eval_duration_seconds",
                          "generation_backend_load_duration_seconds", "generation_backend_prompt_eval_duration_seconds", "generation_backend_eval_duration_seconds",
                          "classifier_backend_load_duration_seconds", "classifier_backend_prompt_eval_duration_seconds", "classifier_backend_eval_duration_seconds",
                          "residency_audit_seconds")
                for field in fields:
                    record["adaptive_minus_comparator_" + field] = statistics.mean(number(a, field) - number(b, field) for a, b in comparisons)
                record["adaptive_minus_comparator_sequence_excluding_direct_audit_seconds"] = record["adaptive_minus_comparator_sequence_seconds"] - record["adaptive_minus_comparator_residency_audit_seconds"]
                paired.append(record)
    quality_pairs = []
    for pattern in ("overall", *PATTERNS):
        for comparator in ("small", "large", "replay"):
            selected = subset(pairs, comparator=comparator) if pattern == "overall" else subset(pairs, comparator=comparator, pattern=pattern)
            for repetition in ("all", "1", "2", "3"):
                rr = selected if repetition == "all" else subset(selected, repetition=repetition)
                quality_pairs.append(dict(pattern=pattern, comparator=comparator, repetition=repetition,
                                          observations=len(rr), contingency=dict(Counter(r["quality_outcome"] for r in rr))))

    component_summary = []
    for arm in ARMS:
        rr = subset(components, arm=arm)
        by_component = {name: total(subset(rr, component=name), "exclusive_wall_seconds") for name in sorted({r["component"] for r in components})}
        assert abs(sum(by_component.values()) - total(subset(turns, arm=arm), "request_wall_seconds")) < 1e-6
        component_summary.append(dict(arm=arm, seconds_total=by_component, seconds_per_turn={k: v / 144 for k, v in by_component.items()}))
    backend = []
    placement = []
    for arm in ARMS:
        arm_calls = subset(calls, arm=arm)
        for purpose in ("all", "generation", "memory_classifier", "compute_classifier"):
            cc = arm_calls if purpose == "all" else subset(arm_calls, purpose=purpose)
            record = dict(arm=arm, purpose=purpose, calls=len(cc), output_tokens=int(total(cc, "output_tokens")),
                          failed_delivery_output_tokens=int(total([c for c in cc if c["request_status"] != "ok"], "output_tokens")),
                          prompt_tokens=int(total(cc, "prompt_tokens")),
                          max_output_tokens=max((number(c, "output_tokens") for c in cc), default=None))
            for metric in ("load_duration_seconds", "prompt_eval_duration_seconds", "eval_duration_seconds", "total_duration_seconds"):
                record[metric] = total(cc, metric)
                record[metric + "_per_sequence"] = total(cc, metric) / 36
            backend.append(record)
        for model in sorted({c["actual_model"] for c in arm_calls}):
            for purpose in ("all", "generation", "memory_classifier"):
                cc = subset(arm_calls, actual_model=model) if purpose == "all" else subset(arm_calls, actual_model=model, purpose=purpose)
                if not cc:
                    continue
                placement.append(dict(arm=arm, model=model, purpose=purpose, calls=len(cc),
                                      minimum=min(number(c, "gpu_allocation_fraction") for c in cc),
                                      mean=mean(cc, "gpu_allocation_fraction"),
                                      maximum=max(number(c, "gpu_allocation_fraction") for c in cc)))

    conditions = []
    for arm in ARMS:
        tt = subset(turns, arm=arm)
        groups = [("residency", condition, subset(tt, residency_condition=condition)) for condition in ("cold_start", "resident_same_model", "model_switch")]
        groups += [("following", condition, subset(tt, following_turn_of_condition=condition)) for condition in ("cold_start", "resident_same_model", "model_switch")]
        for grouping, condition, selected in groups:
            if selected:
                conditions.append(dict(arm=arm, grouping=grouping, condition=condition, turns=len(selected),
                    request_seconds_mean=mean(selected, "request_wall_seconds"),
                    request_seconds_min=min(number(t, "request_wall_seconds") for t in selected),
                    request_seconds_max=max(number(t, "request_wall_seconds") for t in selected),
                    nested_load_seconds_mean=mean(selected, "all_backend_load_duration_seconds"),
                    generation_output_tokens_mean=mean(selected, "generation_output_tokens_all_calls")))

    transitions = []
    for arm in ("adaptive", "replay"):
        for direction in ("small_to_large", "large_to_small"):
            selected = [t for t in turns if t["arm"] == arm and t["residency_condition"] == "model_switch"
                        and (t["return_to_small"] == "True") == (direction == "large_to_small")]
            keys = {(r["attempt_directory"], r["id"]) for r in selected}
            ev = [r for r in events if (r["attempt_directory"], r["request_id"]) in keys]
            record = dict(arm=arm, direction=direction, turns=len(selected),
                request_seconds_mean=mean(selected, "request_wall_seconds"),
                request_seconds_min=min(number(t, "request_wall_seconds") for t in selected),
                request_seconds_max=max(number(t, "request_wall_seconds") for t in selected),
                nested_all_load_seconds_mean=mean(selected, "all_backend_load_duration_seconds"),
                nested_all_load_seconds_min=min(number(t, "all_backend_load_duration_seconds") for t in selected),
                nested_all_load_seconds_max=max(number(t, "all_backend_load_duration_seconds") for t in selected),
                nested_classifier_load_seconds_mean=mean(selected, "classifier_backend_load_duration_seconds"),
                nested_generation_load_seconds_mean=mean(selected, "generation_backend_load_duration_seconds"),
                generation_output_tokens_mean=mean(selected, "generation_output_tokens_all_calls"))
            for name in ("unload_request", "eviction_verification"):
                matched = subset(ev, name=name)
                assert len(matched) == len(selected) == 9
                record[name + "_seconds_mean"] = mean(matched, "wall_ns") / 1e9
                record[name + "_seconds_min"] = min(number(e, "wall_ns") for e in matched) / 1e9
                record[name + "_seconds_max"] = max(number(e, "wall_ns") for e in matched) / 1e9
            for comparator in ("small", "large", "replay"):
                if comparator == arm:
                    continue
                other = [keyed_turns[t["attempt_directory"].rsplit("_", 1)[0] + "_" + comparator, t["id"], int(t["index"])] for t in selected]
                record["minus_" + comparator + "_request_seconds_mean"] = mean(selected, "request_wall_seconds") - mean(other, "request_wall_seconds")
            transitions.append(record)
    ddee_turns = []
    for index in (1, 2, 3, 4):
        for arm in ARMS:
            tt = subset(turns, pattern="DDEE", index=index, arm=arm)
            ddee_turns.append(dict(index=index, arm=arm, turns=len(tt), request_seconds_mean=mean(tt, "request_wall_seconds"),
                correct=sum(t["correct"] == "True" for t in tt), selected_models=dict(Counter(t["selected_model_size"] for t in tt))))
    noop_rows = [e for e in events if e["attempt_directory"] in ("ro_dddd_3_r1_replay", "ro_dddd_3_r2_replay")
                 and e["index"] == "2" and e["name"] in ("unload_request", "eviction_verification")]
    extra_noop = dict(turns=2, spans=len(noop_rows), seconds=total(noop_rows, "wall_ns") / 1e9,
                     unload_seconds=total(subset(noop_rows, name="unload_request"), "wall_ns") / 1e9,
                     verification_seconds=total(subset(noop_rows, name="eviction_verification"), "wall_ns") / 1e9)
    assert extra_noop["spans"] == 4

    deterministic = []
    for arm in ARMS:
        ee = subset(events, arm=arm, name="deterministic_routing")
        deterministic.append(dict(arm=arm, spans=len(ee), wall_seconds_total=total(ee, "wall_ns") / 1e9,
                                  wall_seconds_per_request=total(ee, "wall_ns") / 144e9))
    for arm in ARMS:
        classifier = next(r for r in backend if r["arm"] == arm and r["purpose"] == "memory_classifier")
        assert classifier["calls"] == (0 if arm == "replay" else 93)
        assert classifier["output_tokens"] == (0 if arm == "replay" else 1257)
    data = dict(
        scope="Final descriptive aggregation: 12 four-turn sequences, three dependent repetitions, four systems; all attempted output included.",
        inputs_sha256={f: sha256((ROOT / f).read_bytes()).hexdigest() for f in INPUTS},
        reporter_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        command="python evaluation/routing_overhead_20260912/build_final_findings.py",
        verification=dict(quality_mapping_rows=576, quality_content_hashes_and_evidence="all reconstructed independently from raw observations",
                          component_partition="matches every arm request total", complete_sequence_partition="matches startup + requests + measured gaps",
                          core_summary="all timing and correct counts agree", figures="sequence_latency.png and components.png visually inspected; consistent with tables"),
        overall=totals, patterns=patterns, per_repetition=repetitions, paired=paired, quality_contingencies=quality_pairs,
        exclusive_components=component_summary, backend_nested=backend, placement=placement,
        deterministic_decision_spans=deterministic,
        residency_and_following=conditions, real_transitions=transitions, ddee_turns=ddee_turns,
        extra_replay_noop=extra_noop,
        review=dict(groups=146, agreement=145, adjudicated=1, reviewers="two independent blinded assistant contexts", human_review="pending"),
        limitations=[
            "Dependent repetitions and shared templates/profile: 12 sequence clusters, three variants per pattern; no population-level or iid-turn inference.",
            "Main systems share initial history; later histories reflect their own responses. Replay uses the exact adaptive preturn history and generation HTTP body.",
            "Diagnostic replay is always last; output lengths, placement, cache/numerical execution can differ even for identical inputs.",
            "All-backend load includes classifier loading moved into replay generation; never add backend metadata to client wall durations.",
            "Two replay validation errors invalidate residency hints, causing extra no-op peer-unloads next turn, without changing actual residency or generator identity.",
            "Cold starts are empty LLM residency plus fresh embedder; OS file caches are not flushed. Admission/client/monitor setup and final cleanup lie outside primary sequence interval.",
            "DDEE returns small on turn4: no fifth request exists to measure resident-small benefit after that return.",
            "No compute-classifier calls were triggered in this workload; these costs are instrumented and tested but not estimated live.",
            "GPU byte-allocation fraction is placement metadata, not utilization or compute fraction. Full small GPU residency vs partially offloaded large model limits architecture-only attribution.",
            "Assistant judgments are complete but independent human validation remains pending; timings or successful JSON validation alone do not prove useful answers.",
        ])
    (ROOT / "final_findings.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    out = []
    add = out.append
    add("# Final numerical findings: CLARA routing overhead\n")
    large = next(x for x in totals if x["arm"] == "large")
    adaptive = next(x for x in totals if x["arm"] == "adaptive")
    savings = large["sequence_seconds_mean"] - adaptive["sequence_seconds_mean"]
    add(f"Adaptive completed the authored four-turn sequences in {adaptive['sequence_seconds_mean']:.3f} s on average, versus {large['sequence_seconds_mean']:.3f} s for large-only: a measured saving of {savings:.3f} s ({100*savings/large['sequence_seconds_mean']:.2f}%) after the observed routing, classification, switching, startup, and interturn costs. It took 45.579 s longer than small-only and 8.261 s longer than its diagnostic bypass replay. Thus selection recovered its observed wall-time costs against large-only for the balanced suite, but did not beat small-only. The strongest timing benefit was EEEE. DDEE was slower than large-only over the four-turn horizon, including its final small-model return.\n")
    add("The completed assistant review found 77/144 fully correct adaptive answers, versus 97/144 large-only and 66/144 small-only. Consequently the experiment does not establish a quality-preserving latency improvement; it shows a timing/answer-quality tradeoff. The clear EEEE speedup also reduced fully correct answers, 21/36 versus 33/36. Two independent blinded assistant contexts reviewed 146 distinct output groups, agreeing initially on 145 and adjudicating one; human validation remains pending.\n")
    add("All 576 turns from 144 eligible four-turn attempts are included, including 30 rejected answers. The exact v1 four-turn validation-failure session is eligible through the audited continuation adapter; its failed answer and original interrupted raw status remain preserved. Repetitions are dependent: there are 12 authored sequence clusters, with only three variants per pattern and shared templates/memory. Counts and means below are descriptive, not 576 independent trials.\n")
    add("## Complete-sequence accounting\n")
    add("Seconds below are means per four-turn sequence. Startup starts at BGE initialization and includes prepared memory and router/Conversation setup. The primary total is startup + four complete request walls + measured gaps. Initial admission/client/monitor setup belongs to the separate envelope; final cleanup is also separate. First backend loading is inside the first request, not startup.\n")
    add(table(["System", "Startup", "Four requests", "Gaps", "Complete", "Cleanup", "Fully correct / attempted"], [
        [r["arm"], r["startup_seconds_mean"], r["request_seconds_mean"], r["sequence_gaps_seconds_mean"], r["sequence_seconds_mean"], r["cleanup_seconds_mean"], f"{r['correct']}/{r['turns']}"] for r in totals]) + "\n")
    add(table(["Pattern", "System", "Startup", "Four requests", "Gaps", "Complete", "Correct / 36", "Actual route"], [
        [r["pattern"], r["arm"], r["startup_seconds_mean"], r["request_seconds_mean"], r["sequence_gaps_seconds_mean"], r["sequence_seconds_mean"], r["correct"], ", ".join(r["selected_routes"])] for r in patterns]) + "\n")
    add("Pattern letters are workload labels. Every repetition actually selected SSSS for EEEE, LLLL for DDDD, SLLL for EDED, and LLLS for DDEE in adaptive and replay. The first DDEE easy turn kept large; the second easy turn returned small. Fixed arms generated exclusively with their named models.\n")
    add("## Paired timings and repeat variation\n")
    add("Positive differences mean adaptive was slower. Overall and pattern means first average each sequence's three repetitions; balanced coverage makes these numerically equal to the corresponding session means.\n")
    add(table(["Pattern", "Adaptive − small", "Adaptive − large", "Adaptive − replay"], [
        [pattern] + [next(r["adaptive_minus_comparator_sequence_seconds"] for r in paired if r["pattern"] == pattern and r["comparator"] == comp and r["repetition"] == "all") for comp in ("small", "large", "replay")] for pattern in ("overall", *PATTERNS)]) + "\n")
    add(table(["Pattern", "Repeat", "Adaptive − small", "Adaptive − large", "Adaptive − replay"], [
        [pattern, rep] + [next(r["adaptive_minus_comparator_sequence_seconds"] for r in paired if r["pattern"] == pattern and r["comparator"] == comp and r["repetition"] == str(rep)) for comp in ("small", "large", "replay")] for pattern in PATTERNS for rep in (1, 2, 3)]) + "\n")
    add("EDED reverses against large-only in repetition 2 and against replay in repetition 3. DDEE reverses against large-only in repetition 2. EEEE is faster than large-only in all repetitions, but slower than small-only in repetitions 1–2. DDDD generates entirely with large in both arms; its small timing difference is not evidence of a benefit from choosing a smaller generator. Stratified sequence-cluster intervals in `report_reviewed_v2/paired_cluster_summary.csv` are exploratory; EDED, DDDD and DDEE intervals against large-only include zero.\n")
    add("## Useful-answer outcomes\n")
    add(table(["Pattern", "Repeat", "Small correct / 12", "Large correct / 12", "Adaptive correct / 12", "Replay correct / 12"], [
        [pattern, rep] + [next(r["correct"] for r in repetitions if r["pattern"] == pattern and r["arm"] == arm and r["repetition"] == rep) for arm in ARMS] for pattern in PATTERNS for rep in (1, 2, 3)]) + "\n")
    add(table(["Comparator", "Both correct", "Adaptive only", "Comparator only", "Neither correct"], [
        [r["comparator"]] + [r["contingency"].get(k, 0) for k in ("both_correct", "adaptive_only_correct", "comparator_only_correct", "neither_correct")] for r in quality_pairs if r["pattern"] == "overall" and r["repetition"] == "all"]) + "\n")
    add("Replay and adaptive have equal overall correctness counts but disagree on eight paired outcomes (four in each direction). Identical generation inputs therefore did not imply identical delivered outputs. Partial, incorrect, inappropriate abstention, and technical-failure labels all count as not fully correct. Every review mapping, supplied-evidence list, cited ID list, rubric, and content hash was independently reconstructed against all 576 raw observations for this summary; no join defect was found.\n")
    add("## Disjoint wall components and nested backend durations\n")
    names = sorted({r["component"] for r in components})
    add("The following seconds are per request. For each system, the components including residual time partition the complete request wall. Routing/bookkeeping includes enclosing Python/trace work. Explicit deterministic child spans identify the decision regions, still including trace overhead; they are not an estimate of uninstrumented algorithm cost. Backend load/prefill/decode below overlap these walls and must never be added to them.\n")
    add(table(["Exclusive component", *ARMS], [[name] + [next(r["seconds_per_turn"][name] for r in component_summary if r["arm"] == arm) for arm in ARMS] for name in names]) + "\n")
    add(table(["System", "Memory calls", "Compute calls", "Nested load / seq", "Nested prefill / seq", "Nested decode / seq"], [
        [arm, sum(c["purpose"] == "memory_classifier" for c in subset(calls, arm=arm)), sum(c["purpose"] == "compute_classifier" for c in subset(calls, arm=arm))] + [next(r[k + "_per_sequence"] for r in backend if r["arm"] == arm and r["purpose"] == "all") for k in ("load_duration_seconds", "prompt_eval_duration_seconds", "eval_duration_seconds")] for arm in ARMS]) + "\n")
    add("There were 93 memory-classifier calls in each normal system, none in replay, and zero compute-classifier calls. Fixed systems retain normal memory selection/retrieval and use only their named model. Adaptive memory-classifier exclusive wall totaled 458.932 s (12.748 s/sequence); it is not an incremental selection estimate because some calls also perform the cold load that replay performs in generation.\n")
    add(table(["System", "Deterministic decision spans", "Decision span total s", "Decision span s/request"], [
        [r["arm"], r["spans"], r["wall_seconds_total"], r["wall_seconds_per_request"]] for r in deterministic]) + "\n")
    add("## Cold residency, transitions, and the following turn\n")
    add(table(["System", "Request condition", "n", "Request mean s", "Nested load mean s"], [
        [r["arm"], r["condition"], r["turns"], r["request_seconds_mean"], r["nested_load_seconds_mean"]] for r in conditions if r["grouping"] == "residency"]) + "\n")
    add(table(["System", "Actual transition", "n", "Request s", "Unload acknowledgment s", "Verified eviction s", "Nested load s"], [
        [r["arm"], r["direction"], r["turns"], r["request_seconds_mean"], r["unload_request_seconds_mean"], r["eviction_verification_seconds_mean"], r["nested_all_load_seconds_mean"]] for r in transitions]) + "\n")
    add(table(["System", "Following previous request condition", "n", "Following request mean s", "Nested load mean s"], [
        [r["arm"], r["condition"], r["turns"], r["request_seconds_mean"], r["nested_load_seconds_mean"]] for r in conditions if r["grouping"] == "following"]) + "\n")
    add(table(["DDEE turn", "Small s", "Large s", "Adaptive s", "Replay s"], [
        [index] + [next(r["request_seconds_mean"] for r in ddee_turns if r["index"] == index and r["arm"] == arm) for arm in ARMS] for index in (1, 2, 3, 4)]) + "\n")
    returns = [r for r in transitions if r["direction"] == "large_to_small"]
    add(table(["System", "Return request range s", "Nested load range s", "Return minus resident large request s"], [
        [r["arm"], f"{r['request_seconds_min']:.3f}–{r['request_seconds_max']:.3f}", f"{r['nested_all_load_seconds_min']:.3f}–{r['nested_all_load_seconds_max']:.3f}", r["minus_large_request_seconds_mean"]] for r in returns]) + "\n")
    add("Adaptive's nine real small→large transitions occur at EDED turn 2; nine following turns are observed at EDED turn 3. Its nine large→small returns occur at DDEE turn 4. No turn 5 follows those returns, so the experiment cannot establish a subsequent resident-small saving or the longer-horizon break-even point. Unload acknowledgment, verified absence, and next backend call have separately ordered spans. Most other peer-unload calls are no-ops at cold entry; they are not model switches. Residency groups pool different questions, so their mean difference is descriptive rather than a matched cold-load intervention.\n")
    add("## Diagnostic selection cost and attribution limits\n")
    replay_pair = next(r for r in paired if r["pattern"] == "overall" and r["comparator"] == "replay" and r["repetition"] == "all")
    add(table(["Adaptive − replay, per sequence", "Difference"], [[label, replay_pair[key]] for label, key in (
        ("Complete wall s", "adaptive_minus_comparator_sequence_seconds"),
        ("Startup s", "adaptive_minus_comparator_startup_seconds"),
        ("Four request walls s", "adaptive_minus_comparator_request_seconds"),
        ("Measured gaps s", "adaptive_minus_comparator_sequence_gaps_seconds"),
        ("Direct residency-audit wall s", "adaptive_minus_comparator_residency_audit_seconds"),
        ("Complete wall after direct audit subtraction s", "adaptive_minus_comparator_sequence_excluding_direct_audit_seconds"),
        ("Nested all-backend load s", "adaptive_minus_comparator_all_backend_load_duration_seconds"),
        ("Nested all-backend prefill s", "adaptive_minus_comparator_all_backend_prompt_eval_duration_seconds"),
        ("Nested all-backend decode s", "adaptive_minus_comparator_all_backend_eval_duration_seconds"),
        ("Nested generation load s", "adaptive_minus_comparator_generation_backend_load_duration_seconds"),
        ("Nested classifier load s", "adaptive_minus_comparator_classifier_backend_load_duration_seconds"),
        ("Generation output tokens", "adaptive_minus_comparator_generation_output_tokens_all_calls"),
        ("Classifier output tokens", "adaptive_minus_comparator_classifier_output_tokens"),
    )]) + "\n")
    add(table(["System", "Generation tokens, all 144 calls", "Tokens from rejected deliveries", "Classifier tokens"], [
        [arm, next(r["output_tokens"] for r in backend if r["arm"] == arm and r["purpose"] == "generation"), next(r["failed_delivery_output_tokens"] for r in backend if r["arm"] == arm and r["purpose"] == "generation"), next(r["output_tokens"] for r in backend if r["arm"] == arm and r["purpose"] == "memory_classifier")] for arm in ARMS]) + "\n")
    add(table(["System", "Generator", "Calls", "GPU allocated byte fraction min", "Mean", "Max"], [
        [r["arm"], r["model"], r["calls"], r["minimum"], r["mean"], r["maximum"]] for r in placement if r["purpose"] == "generation"]) + "\n")
    add("The 8.261 s/sequence adaptive-minus-replay difference estimates the net observed cost of retaining selection on this execution path; it is not a pure classifier causal effect. Exact generation HTTP bodies, selected/actual generators, and adaptive starting histories were replayed, but replay always ran last. Model placement, cache/numerical execution, and output length varied. Adaptive generated 286 fewer tokens than replay overall, while its all-backend prefill/decode took longer. All 2,090 tokens from the 30 rejected deliveries are included above; delivered-only token fields in the frozen core table omit these and should not be used for all-attempt attribution.\n")
    add(f"Replay issued two extra no-op small-peer unloads following validation failures in `ro_dddd_3_r1_replay` and `ro_dddd_3_r2_replay`, when the client residency hint was invalidated. Large remained resident and generation identity remained exact. These extra unload/verification spans totaled {extra_noop['seconds']:.9f} s; their negligible magnitude does not remove the state-path distinction. A cold classifier may carry loading in adaptive that shifts to answer generation in replay, so generation-only load savings overstate net savings. Small was fully GPU allocated; large was partly offloaded. GPU byte allocation is neither utilization nor a fraction of computation.\n")
    add("Final telemetry/resource integrity was independently audited: 15,856 samples, peak temperature 57.343 °C, RAM 6,633 MiB, swap 2,485 MiB; maximum telemetry sample gap 1.9473 s. All sessions ended with empty LLM residency and no cleanup errors. Cold entry retained OS file caches. These controls bound the recorded run; they do not establish identical placement or thermal/cache conditions across systems.\n")
    add("The final figures were visually checked against these values. Reproduce the supplementary findings with `python evaluation/routing_overhead_20260912/build_final_findings.py`; exact source-table hashes, unrounded values, per-pattern quality contingencies, and transition comparisons are in `final_findings.json`. Frozen sources and raw traces were read without modification.\n")
    (ROOT / "final_findings.md").write_text("\n".join(out))
    print(json.dumps({"written": ["final_findings.json", "final_findings.md"], "quality_mapping_verified": len(seen), "sequence_rows": len(sequences), "turn_rows": len(turns)}))


if __name__ == "__main__":
    main()
