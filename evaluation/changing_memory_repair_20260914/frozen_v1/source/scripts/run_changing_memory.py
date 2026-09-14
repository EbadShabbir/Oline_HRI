"""Frozen live changing-memory episodes through the default deployed text path.

The worker never reads the expected-state ledger. Logical time is supplied only
to MemoryStore; retrieval and Conversation snapshot validation delegate to it.
No database rows are edited by this harness. All output paths are exclusive.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
from time import perf_counter_ns, sleep

from oline_hri import evaluation_model_pairs as pair
from oline_hri.cli import _run_memory
from oline_hri.config import load_config
from oline_hri.conversation import Conversation
from oline_hri.embedding import BgeOnnxEmbedder, REQUIRED_ASSET_SHA256
from oline_hri.memory import MemoryItem, MemoryStore
from oline_hri.ollama import ChatMessage
from oline_hri.retrieval import HybridMatch, HybridRetriever
from oline_hri.routing import ConversationRouter
from oline_hri.timing import TraceRecorder
from post_memory_device_guard import stage2_limits, require_ready, policy_dict
from run_complete_system import RecordingRouter
from run_independent_retrieval import DurableClient, initial_sample, model_inventory, host, seal, verify_seal
from run_pair_remediation_validation import GuardedSampler
from run_post_memory_comparison import ComparisonBackend, cleanup_owned, package_versions

ROOT = Path(__file__).resolve().parents[1]
MODELS = ('qwen3:0.6b', 'qwen3:1.7b')
write = pair._write_new_json


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def sources():
    paths = list((ROOT/'src/oline_hri').glob('*.py'))
    paths += [ROOT/'config/default.json', ROOT/'src/oline_hri/default_config.json']
    paths += [ROOT/'scripts'/name for name in (
        'run_changing_memory.py', 'run_independent_retrieval.py',
        'run_post_memory_comparison.py', 'run_complete_system.py',
        'run_pair_remediation_validation.py', 'post_memory_device_guard.py',
        'complete_system_device_guard.py', 'run_arc_capability.py')]
    paths += list((ROOT/'tests').glob('test_changing_memory*.py'))
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)}


def identity():
    return dict(pid=os.getpid(), parent_pid=os.getppid(),
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                process_start_ticks=Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19],
                executable=sys.executable, wall_time=datetime.now(timezone.utc).isoformat())


def file_identity(path):
    value = Path(path).stat()
    return dict(path=str(Path(path).resolve()), device=value.st_dev, inode=value.st_ino, size=value.st_size)


def require_baseline(snapshot, frozen):
    baseline = frozen['host']['snapshot']
    for key in ('boot_id', 'power_mode', 'thermal_trip_events'):
        if snapshot[key] != baseline[key]:
            raise pair.SafetyGateError('frozen host baseline differs: '+key)
    if snapshot['memory']['swap_total_kib'] != baseline['memory']['swap_total_kib']:
        raise pair.SafetyGateError('frozen swap capacity differs')


class EvaluationClock:
    def __init__(self, value):
        self.value = datetime.fromisoformat(value.replace('Z', '+00:00'))

    def set(self, value):
        new = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if new.tzinfo is None or new < self.value:
            raise ValueError('evaluation clock must be aware and monotonic within branch')
        self.value = new

    def __call__(self):
        return self.value


def database_snapshot(path):
    """Read-only diagnostics; never call a listing API that might purge."""
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {table: [dict(row) for row in conn.execute(f'SELECT * FROM {table}')]
                for table in ('memory_item', 'memory_audit') if table in tables}


class ObservedEmbedder:
    def __init__(self, delegate, writer, clock):
        self.delegate, self.writer, self.clock = delegate, writer, clock
        self.model_id, self.model_revision, self.dimension = (
            delegate.model_id, delegate.model_revision, delegate.dimension)

    def invoke(self, method, value):
        row = dict(event='embedding', method=method, input=value,
                   logical_time=self.clock().isoformat(), started_ns=perf_counter_ns())
        try:
            result = getattr(self.delegate, method)(value)
            row.update(status='ok', shape=list(result.shape), vector_sha256=sha256(result.tobytes()).hexdigest())
            return result
        except BaseException as error:
            row.update(status='error', error=type(error).__name__, message=str(error))
            raise
        finally:
            row['wall_ns'] = perf_counter_ns()-row['started_ns']; self.writer.write(row)

    def embed_passages(self, passages):
        return self.invoke('embed_passages', passages)

    def embed_query(self, query):
        return self.invoke('embed_query', query)


class ObservedRetriever:
    def __init__(self, store, clock):
        self.delegate, self.clock = HybridRetriever(store), clock
        self.calls, self.checks = [], []
        self.inject_snapshot = None

    def retrieve(self, query, *, limit=3):
        row = dict(query=query, logical_time=self.clock().isoformat(), started_ns=perf_counter_ns())
        try:
            if self.inject_snapshot is not None:
                result = self.inject_snapshot
                row['diagnostic_snapshot_replay'] = True
            else:
                result = self.delegate.retrieve(query, limit=limit)
            row.update(status='ok', matches=[dict(memory=m.memory.to_dict(), fused_score=m.fused_score) for m in result])
            return result
        except BaseException as error:
            row.update(status='error', error=type(error).__name__, message=str(error)); raise
        finally:
            row['wall_ns'] = perf_counter_ns()-row['started_ns']; self.calls.append(row)

    def is_current(self, matches):
        row = dict(logical_time=self.clock().isoformat(), records=[m.memory.to_dict() for m in matches])
        try:
            result = self.delegate.is_current(matches)
            row['current'] = result
            return result
        except BaseException as error:
            row.update(error=type(error).__name__, message=str(error)); raise
        finally:
            self.checks.append(row)


class ObservedStore(MemoryStore):
    def __init__(self, *args, events, **kwargs):
        self.events = events
        super().__init__(*args, **kwargs)

    def purge_expired(self):
        result = super().purge_expired()
        self.events.write(dict(event='automatic_retention_purge', logical_time=self._clock().isoformat(),
                               removed_ids=list(result), process=identity()))
        return result


class Episode:
    """One live conversation and store persist across operations in a process."""
    def __init__(self, branch, database, backend, embedder, writer, events, restored=None):
        self.branch, self.database, self.backend = branch, database, backend
        self.writer, self.events = writer, events
        self.clock = EvaluationClock(restored['logical_time'] if restored else branch['operations'][0]['time'])
        self.store = ObservedStore(database, profile_id=branch['profile_id'], events=events,
                                 clock=self.clock, retention_days=load_config().memory.retention_days,
                                 embedder=ObservedEmbedder(embedder, events, self.clock))
        self.store.list_memories()  # Initialize schema through the real public read API.
        self.retriever = ObservedRetriever(self.store, self.clock)
        self.router = RecordingRouter(ConversationRouter(backend, model=MODELS[0]))
        self.conversation = self.new_conversation()
        self.ids, self.saved_snapshot = {}, ()
        if restored:
            if restored['process']['pid'] == os.getpid():
                raise ValueError('object reconstruction is not a process restart')
            self.conversation._messages = [ChatMessage(**m) for m in restored['history']]
            self.ids = restored['ids']
            current_file = file_identity(database)
            if any(current_file[k] != restored['database_identity'][k] for k in ('path', 'device', 'inode')):
                raise ValueError('restart database file identity changed')
            self.saved_snapshot = tuple(HybridMatch(**{**m, 'memory': MemoryItem(**m['memory'])})
                                        for m in restored['saved_snapshot'])
            self.events.write(dict(event='history_restored_after_process_restart', from_process=restored['process'],
                                   process=identity(), exact_history=restored['history']))

    def new_conversation(self):
        config = load_config()
        return Conversation(self.backend, system_prompt=config.conversation.system_prompt,
            router=self.router, retriever=self.retriever, small_model=MODELS[0],
            general_large_model=MODELS[1], large_model=MODELS[1],
            context_length=config.generation.context_length, max_output_tokens=config.generation.max_output_tokens)

    def state(self):
        return dict(ids=self.ids, history=[m.to_dict() for m in self.conversation.messages], process=identity(),
                    logical_time=self.clock().isoformat(), saved_snapshot=[asdict(m) for m in self.saved_snapshot],
                    database_identity=file_identity(self.database))

    def ask(self, op, *, diagnostic=False):
        conversation = self.new_conversation() if op.get('history', 'retained') == 'fresh' else self.conversation
        start_calls, start_retrieval, start_checks = len(self.backend.calls), len(self.retriever.calls), len(self.retriever.checks)
        self.router.result = None
        self.backend.transport_error = None
        row = dict(op=op, checkpoint_id=op.get('checkpoint_id'), branch_id=self.branch['branch_id'],
                   scenario_id=self.branch['scenario_id'], branch=self.branch['branch'],
                   process=identity(), logical_time=self.clock().isoformat(),
                   database_identity=file_identity(self.database),
                   history_before=[m.to_dict() for m in conversation.messages],
                   database_before=database_snapshot(self.database), status='started', diagnostic=diagnostic)
        self.events.write(dict(event='question_start', **row))
        trace = TraceRecorder(sink=lambda value: self.events.write(dict(checkpoint_id=row['checkpoint_id'], **value)))
        began = perf_counter_ns(); fatal = None
        try:
            with trace.activate():
                reply = conversation.send(op.get('question', op.get('text')))
            row.update(status='delivered', delivered_answer=reply.response.speech, response=reply.response.to_dict(),
                       generation=asdict(reply.generation), memory=reply.memory_diagnostics.to_dict(),
                       supplied_records=[m.memory.to_dict() for m in reply.retrieval],
                       answer_constraint=reply.answer_constraint, generation_policy=reply.generation_policy,
                       response_transform=reply.response_transform, fallback_from_model=reply.fallback_from_model,
                       validation_decision='accepted')
        except BaseException as error:
            row.update(status='withheld', delivered_answer=None, error=type(error).__name__, message=str(error),
                       validation_decision='rejected_or_pipeline_failure')
            if isinstance(error, (KeyboardInterrupt, SystemExit, pair.SafetyGateError)) or self.backend.transport_error:
                row['status'] = 'interrupted'; fatal = error
        finally:
            row.update(wall_ns=perf_counter_ns()-began, calls=self.backend.calls[start_calls:],
                       retrieval_calls=self.retriever.calls[start_retrieval:], snapshot_checks=self.retriever.checks[start_checks:],
                       route=asdict(self.router.result) if self.router.result else None,
                       history_after=[m.to_dict() for m in conversation.messages], trace=trace.events,
                       database_after=database_snapshot(self.database))
            row['raw_model_answers'] = [c.get('raw_generation', c.get('generation', {})).get('content')
                                        for c in row['calls'] if c.get('purpose') == 'generation']
            row['supplied_evidence_envelopes'] = []
            for call in row['calls']:
                if call.get('purpose') != 'generation':
                    continue
                for message in call.get('messages', []):
                    marker = 'PERSONAL_MEMORY_DATA='
                    if message['content'].startswith(marker):
                        payload, _ = json.JSONDecoder().raw_decode(message['content'][len(marker):])
                        row['supplied_evidence_envelopes'].append(payload)
            disclosure = next(o['text'] for o in self.branch['operations'] if o['op'] == 'disclose')
            row['original_disclosure_present_in_history'] = any(
                m['role'] == 'user' and m['content'] == disclosure for m in row['history_before'])
            self.writer.write(row)
            print(f"{self.branch['branch_id']} {op.get('checkpoint_id', op['op'])}: {row['status']} {row['wall_ns']/1e9:.2f}s", flush=True)
        if fatal:
            raise fatal
        return row

    def operation(self, op):
        self.clock.set(op['time'])
        if op['op'] in ('ask', 'disclose'):
            return self.ask(op)
        row = dict(event='operation', op=op, process=identity(), branch_id=self.branch['branch_id'],
                   logical_time=self.clock().isoformat(), database_before=database_snapshot(self.database))
        self.events.write(dict(event='operation_start', **{k:v for k,v in row.items() if k!='event'}))
        try:
            if op['op'] in ('remember', 'correct', 'forget'):
                # Invoke the actual CLI memory handler backed by the same live API.
                args = argparse.Namespace(memory_command=op['op'], text=op.get('text'),
                    kind=op.get('kind', 'fact'), sensitivity='normal', importance=3,
                    event_time=op.get('event_time'), valid_until=None, retention_until=None,
                    memory_id=self.ids.get(op.get('target_key', 'subject')), yes=True)
                output = StringIO()
                row['explicit_confirmation'] = 'Authored explicit API instruction; API consent_status confirmed. No conversational confirmation classifier.'
                _run_memory(args, self.store, input_stream=StringIO('yes\n'), output=output)
                row['acknowledgement'] = output.getvalue()
                if op['op'] in ('remember', 'correct'):
                    active = self.store.list_memories()
                    item = next(m for m in active if m.canonical_text == op['text'])
                    self.ids[op.get('record_key', op.get('target_key', 'subject'))] = item.id
                    row['result'] = item.to_dict()
            elif op['op'] == 'cache_probe':
                query = op['query']
                first = self.retriever.retrieve(query)
                second = self.retriever.retrieve(query)
                self.saved_snapshot = tuple(m for m in first if m.memory.id == self.ids['subject'])
                row.update(first=[m.memory.to_dict() for m in first], second=[m.memory.to_dict() for m in second],
                           retained_snapshot=[m.memory.to_dict() for m in self.saved_snapshot],
                           existing_retrieval_cache='none; production rebuilds matrix each search',
                           snapshot_current=self.retriever.is_current(self.saved_snapshot))
            elif op['op'] == 'snapshot_probe':
                row.update(retained_snapshot=[m.memory.to_dict() for m in self.saved_snapshot],
                           snapshot_current=self.retriever.is_current(self.saved_snapshot))
            else:
                raise ValueError('unknown operation '+op['op'])
            row.update(status='ok', database_after=database_snapshot(self.database))
        except BaseException as error:
            row.update(status='error', error=type(error).__name__, message=str(error)); raise
        finally:
            self.events.write(row)


def verify_frozen(directory):
    verify_seal(directory)
    frozen = json.loads((directory/'freeze.json').read_text())
    if frozen['source_sha256'] != sources() or frozen['config'] != load_config().to_dict():
        raise ValueError('runtime source/configuration differs from freeze')
    if frozen['models'] != model_inventory() or frozen['ollama_version'] != pair._http_json('/api/version'):
        raise ValueError('installed model/runtime drift')
    if (frozen['packages'] != package_versions() or frozen['python'] != sys.version
            or frozen['device_policy'] != policy_dict() or frozen['embedding_assets'] != REQUIRED_ASSET_SHA256):
        raise ValueError('package/embedding/device policy drift')
    return frozen


def freeze(args):
    directory = pair._new_private_directory(args.output.absolute())
    review = json.loads(args.review.read_text())
    for name in ('runtime.json', 'expected_ledger.json', 'protocol.md'):
        if review['sha256'][name] != digest(args.draft/name):
            raise ValueError('pre-inference reviewed artifact changed: '+name)
        shutil.copyfile(args.draft/name, directory/name)
    if not review['approved'] or review['source_sha256'] != sources():
        raise ValueError('independent protocol/harness review missing or stale')
    shutil.copyfile(args.review, directory/'preflight_review.json')
    preparation = directory/'preparation'; preparation.mkdir()
    for name in ('scenarios.json', 'author_ledger.py', 'authoring_v2_changes.md'):
        shutil.copyfile(args.draft.parent/name, preparation/name)
    for rel in ('developments.MD', 'results.md', 'evaluation/adaptive_selection_protocol_draft.md',
                'evaluation/memory_pipeline_20260912/README.md', 'evaluation/independent_retrieval_20260913/README.md',
                'evaluation/independent_retrieval_20260913/report_reviewed_v3/report.md',
                'evaluation/routing_overhead_20260912/README.md'):
        target = preparation/rel; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/rel, target)
    validation = args.draft.parent/'offline_validation_v1'
    if not validation.is_dir():
        raise ValueError('offline validation artifacts required before freeze')
    shutil.copytree(validation, preparation/'offline_validation')
    source = sources()
    for rel in source:
        target = directory/'source'/rel; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/rel, target)
    write(directory/'freeze.json', dict(created_at=datetime.now(timezone.utc).isoformat(),
        source_sha256=source, config=load_config().to_dict(), models=model_inventory(),
        ollama_version=pair._http_json('/api/version'), embedding_assets=REQUIRED_ASSET_SHA256,
        packages=package_versions(), python=sys.version, generation_seed=42, device_policy=policy_dict(),
        host=host(), routing_policy='llm (CLI default)', retain_large_model=False,
        logical_clock='MemoryStore injected callable; shared by retrieval and snapshot validation'))
    write(directory/'model_show.json', {m:pair._http_json('/api/show', body={'model':m}) for m in MODELS})
    seal(directory)
    print(directory, flush=True)


def worker(args):
    if not args.lease_fds:
        raise ValueError('worker requires inherited exclusive inference leases')
    lease_paths = (Path('/tmp/clara-jetson-inference.lock'), ROOT/'evaluation/independent_retrieval_inference.lock',
                   ROOT/'evaluation/matched_evidence_inference.lock')
    lease_fds = tuple(int(value) for value in args.lease_fds.split(','))
    if len(lease_fds) != len(lease_paths):
        raise ValueError('all three inherited inference leases are required')
    for fd, path in zip(lease_fds, lease_paths):
        actual, expected = os.fstat(fd), path.stat()
        if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise ValueError('inherited lease does not match lock path')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    frozen = verify_frozen(args.freeze)
    runtime = json.loads((args.freeze/'runtime.json').read_text())
    branch = next(b for b in runtime['branches'] if b['branch_id'] == args.branch)
    operations = branch['operations']
    restart = next(i for i, op in enumerate(operations) if op['op'] == 'restart')
    operations = operations[:restart] if args.segment == 'initial' else operations[restart+1:]
    next_offset = args.start_offset
    directory = pair._new_private_directory(args.output.absolute())
    database = args.database.absolute()
    if args.segment == 'initial' and args.start_offset == 0 and not args.state and database.exists():
        raise ValueError('initial branch database must be new')
    if args.segment == 'restart' and not database.is_file():
        raise ValueError('restart must reopen existing database')
    status, error_info, sampler, backend, client = 'failed', None, None, None, None
    cleanup_errors = []
    with stage2_limits():
        try:
            start = pair.capture_safety_snapshot(); write(directory/'start.json', start)
            require_ready(start)
            require_baseline(start, frozen)
            write(directory/'process.json', identity())
            restored = json.loads(args.state.read_text()) if args.state else None
            with ExitStack() as stack:
                http = stack.enter_context(pair._DurableJsonlWriter(directory/'http.jsonl'))
                telemetry = stack.enter_context(pair._DurableJsonlWriter(directory/'telemetry.jsonl'))
                events = stack.enter_context(pair._DurableJsonlWriter(directory/'events.jsonl'))
                answers = stack.enter_context(pair._DurableJsonlWriter(directory/'answers.jsonl'))
                monitor = pair._StreamingSafetyMonitor(telemetry); sampler = GuardedSampler(monitor)
                client = DurableClient(load_config().ollama, load_config().generation, http_writer=http)
                backend = ComparisonBackend(client, start, sampler, MODELS)
                with sampler:
                    try:
                        initial_sample(backend, sampler)
                        embedder = BgeOnnxEmbedder(load_config().embedding.model_directory,
                                                  load_config().embedding.intra_op_threads)
                        episode = Episode(branch, database, backend, embedder, answers, events, restored)
                        write(directory/'state_initial.json', episode.state())
                        for index, op in enumerate(operations[args.start_offset:], args.start_offset):
                            backend.check()
                            try:
                                episode.operation(op)
                            finally:
                                # Save actual state even after a failed/withheld checkpoint.
                                # Continuations never repeat an operation that started.
                                next_offset = index + 1
                                write(directory/f'state_after_{index:03}.json', episode.state())
                        write(directory/'state.json', episode.state())
                        status = 'complete'
                    finally:
                        cleanup_errors = cleanup_owned(client, backend)
        except BaseException as error:
            error_info = dict(type=type(error).__name__, message=str(error))
            status = 'interrupted' if isinstance(error, (KeyboardInterrupt, pair.SafetyGateError)) else 'failed'
        finally:
            try:
                finish = pair.capture_safety_snapshot()
                if 'start' in locals():
                    for key in ('boot_id', 'power_mode', 'thermal_trip_events'):
                        if finish[key] != start[key]:
                            cleanup_errors.append('start/finish mismatch: '+key)
                    if finish['memory']['swap_total_kib'] != start['memory']['swap_total_kib']:
                        cleanup_errors.append('swap capacity changed')
                    if finish['resident_models']:
                        cleanup_errors.append('model eviction incomplete')
            except BaseException as error:
                finish = dict(error=type(error).__name__, message=str(error))
                cleanup_errors.append('final resource/invariant capture failed: '+type(error).__name__)
            write(directory/'finish.json', dict(status=status, error=error_info, cleanup_errors=cleanup_errors,
                  snapshot=finish, telemetry=sampler.summary() if sampler else None,
                  guard_violation=sampler.monitor.violation if sampler else None,
                  next_offset=next_offset, operation_count=len(operations)))
    seal(directory)
    return 0 if status == 'complete' and not cleanup_errors else 1


@contextmanager
def inference_lock():
    with ExitStack() as stack:
        fds = []
        for path in (Path('/tmp/clara-jetson-inference.lock'),
                     ROOT/'evaluation/independent_retrieval_inference.lock',
                     ROOT/'evaluation/matched_evidence_inference.lock'):
            stream = stack.enter_context(path.open('a'))
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fds.append(stream.fileno())
        processes = subprocess.run(['ps','-eo','pid,args'], capture_output=True, text=True, check=True).stdout
        conflicts = [line.strip() for line in processes.splitlines()
                     if 'python' in line and ('scripts/run_' in line or 'scripts/continue_' in line or 'scripts/resume_' in line)
                     and 'run_changing_memory.py' not in line and 'ps -eo' not in line]
        if conflicts:
            raise pair.SafetyGateError('competing experiment: '+repr(conflicts))
        yield tuple(fds)


def _collect(args):
    frozen = verify_frozen(args.freeze)
    runtime = json.loads((args.freeze/'runtime.json').read_text())
    directory = pair._new_private_directory(args.output.absolute())
    results = []
    with inference_lock() as lease_fds:
        for branch in runtime['branches']:
            branch_dir = directory/branch['branch_id']; branch_dir.mkdir()
            state = None
            for segment in ('initial', 'restart'):
                offset = 0
                for fragment in range(1, 101):
                    name = segment if fragment == 1 else f'{segment}_continuation_{fragment:02}'
                    # Rejected admissions contain no inference and may be retried unchanged.
                    for admission in range(1, 181):
                        with stage2_limits():
                            snapshot = pair.capture_safety_snapshot()
                            try:
                                require_ready(snapshot)
                                require_baseline(snapshot, frozen)
                                break
                            except pair.SafetyGateError as error:
                                write(branch_dir/f'{name}_admission_{admission:03}.json',
                                      dict(error=str(error), snapshot=snapshot, process=identity()))
                                print(f'admission waiting {branch["branch_id"]}/{name}: {error}', flush=True)
                        sleep(20)
                    else:
                        raise pair.SafetyGateError('admission retry budget exhausted')
                    output = branch_dir/name
                    command = [sys.executable, str(Path(__file__).resolve()), 'worker', '--freeze', str(args.freeze.absolute()),
                               '--branch', branch['branch_id'], '--segment', segment, '--database', str(branch_dir/'memory.sqlite3'),
                               '--output', str(output), '--lease-fds', ','.join(map(str, lease_fds)), '--start-offset', str(offset)]
                    if state:
                        command += ['--state', str(state)]
                    with (branch_dir/f'{name}.log').open('x') as logfile:
                        proc = subprocess.Popen(command, stdout=logfile, stderr=subprocess.STDOUT, env=os.environ.copy(), pass_fds=lease_fds)
                        write(branch_dir/f'{name}_launch.json', dict(command=command, pid=proc.pid, supervisor=identity(),
                              restored_state_sha256=digest(state) if state else None, start_offset=offset))
                        try:
                            returncode = proc.wait()
                        except BaseException:
                            # Reap a stopped worker before any artifact sealing.
                            proc.send_signal(signal.SIGINT)
                            try:
                                proc.wait(timeout=30)
                            except subprocess.TimeoutExpired:
                                proc.terminate()
                                try:
                                    proc.wait(timeout=10)
                                except subprocess.TimeoutExpired:
                                    proc.kill(); proc.wait(timeout=10)
                            cleanup = pair._force_unload(MODELS)
                            write(branch_dir/f'{name}_supervisor_stop.json',
                                  dict(pid=proc.pid, returncode=proc.returncode, cleanup_errors=cleanup))
                            raise
                    result = dict(branch=branch['branch_id'], segment=segment, fragment=fragment, returncode=returncode)
                    results.append(result)
                    print(json.dumps(result), flush=True)
                    finish = json.loads((output/'finish.json').read_text())
                    states = sorted(output.glob('state_after_*.json'))
                    if (output/'state.json').exists():
                        state = output/'state.json'
                    elif states:
                        state = states[-1]
                    elif (output/'state_initial.json').exists():
                        state = output/'state_initial.json'
                    offset = finish['next_offset']
                    if returncode and (finish['cleanup_errors'] or (not state and offset != 0)):
                        write(directory/'interruption.json', dict(results=results, failed=result))
                        return 1
                    if offset == finish['operation_count']:
                        break
                    if not returncode:
                        raise ValueError('worker reported complete without completing operation coverage')
                else:
                    raise RuntimeError('continuation fragment budget exhausted')
            seal(branch_dir)
    write(directory/'finish.json', dict(status='complete', segments=results))
    seal(directory)
    return 0


def collect(args):
    try:
        return _collect(args)
    except BaseException as error:
        if args.output.is_dir() and not (args.output/'seal.json').exists():
            path = args.output/'orchestration_interruption.json'
            if not path.exists():
                recorded = []
                for answer_file in args.output.rglob('answers.jsonl'):
                    for line in answer_file.read_text().splitlines():
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if row.get('checkpoint_id'):
                            recorded.append(row['checkpoint_id'])
                write(path, dict(error=type(error).__name__, message=str(error), process=identity(),
                                 recorded_checkpoint_ids=recorded,
                                 status='interrupted; all absent checkpoints remain explicitly missing'))
            seal(args.output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('freeze'); p.add_argument('--draft', type=Path, required=True); p.add_argument('--review', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('collect'); p.add_argument('--freeze', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('worker'); p.add_argument('--freeze', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--branch', required=True); p.add_argument('--segment', choices=('initial','restart'), required=True)
    p.add_argument('--database', type=Path, required=True); p.add_argument('--state', type=Path)
    p.add_argument('--lease-fds', required=True)
    p.add_argument('--start-offset', type=int, default=0)
    args = parser.parse_args()
    os.umask(0o077)
    return globals()[args.command](args)


if __name__ == '__main__':
    raise SystemExit(main())
