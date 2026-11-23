"""Bounded panel experiment, not a production scheduler. Compare complete decisions, not hashes."""
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import json
import multiprocessing
import os
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

from lgz_core import q0_admission as adm, q0_preparation as prep, q0_threshold_prepare as threshold
from lgz_core.q0_threshold_questions import questions

SCREEN = adm._reference_groups
SELECT = adm.select_q0_paths
POLICY = adm.AdmissionPolicy()


def screen_source(packet):
    source, dna, hits, parts = packet
    view = SimpleNamespace(sources={source: dna}, reference_hits={source: hits})
    return {part.segment_id: SCREEN(view, part, POLICY) for part in parts}


def source_packets(data):
    parts = defaultdict(list)
    for part in data.parts.values():
        parts[part.source].append(part)
    # Bounds apply only to these already frozen panels, never to the whole-wheat parent.
    if sum(map(len, data.sources.values())) > 80_000_000:
        raise ValueError('panel exceeds the experiment limit')
    packets = [(key, data.sources[key], data.reference_hits.get(key, ()), group) for key, group in parts.items()]
    return sorted(packets, key=lambda p: -(len(p[1]) if p[2] else 0))


def parallel_selection(data, cores):
    packets = iter(source_packets(data)); result = {}; assigned = 0
    # The owner is one compute lane; cap pending tasks. Never fork/pickle the evidence graph.
    with ProcessPoolExecutor(cores - 1, mp_context=multiprocessing.get_context('spawn')) as pool:
        pending = set()
        while True:
            own = next(packets, None)
            for _ in range(cores - 1 - len(pending)):
                item = next(packets, None)
                if item is None:
                    break
                pending.add(pool.submit(screen_source, item)); assigned += 1
            if own is not None:
                result.update(screen_source(own))
            if pending:
                done, pending = wait(pending, timeout=0 if own is not None else None, return_when=FIRST_COMPLETED)
                for f in done:
                    result.update(f.result())
            elif own is None:
                break
    if result.keys() != data.parts.keys():
        raise ValueError('screen results are incomplete')
    def consume(d, part, policy):
        if d is not data or policy != POLICY:
            raise ValueError('screen context changed')
        return result.pop(part.segment_id)
    with patch.object(adm, '_reference_groups', consume):
        selected = SELECT(data)
    if result:
        raise ValueError('screen results were not fully consumed')
    return selected, assigned


def rss_tree_kib(pid):
    todo = [pid]; total = 0; seen = set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p); root = Path('/proc')/str(p)
        try:
            total += next(int(v.split()[1]) for v in (root/'status').read_text().splitlines() if v.startswith('VmRSS:'))
            for children in (root/'task').glob('*/children'):
                todo.extend(map(int, children.read_text().split()))
        except (OSError, StopIteration):
            pass  # children may have just exited
    return total


def measure(data, assignments, cores):
    start_rss = rss_tree_kib(os.getpid()); peak = [start_rss]; stop = Event()
    def sample():
        while not stop.wait(.1):
            peak[0] = max(peak[0], rss_tree_kib(os.getpid()))
    thread = Thread(target=sample, daemon=True); thread.start(); start = monotonic(); count = 0; by_source = defaultdict(float)
    try:
        if cores == 1:
            def timed(d, part, policy):
                t = monotonic(); value = SCREEN(d, part, policy); by_source[part.source] += monotonic()-t
                return value
            with patch.object(adm, '_reference_groups', timed):
                selection = SELECT(data)
        else:
            selection, count = parallel_selection(data, cores)
        demand = questions(data, selection, assignments)
        seconds = monotonic()-start
    finally:
        stop.set(); thread.join()
    info = {'cores': cores, 'seconds': seconds, 'additional_rss_kib_sampled': max(0, peak[0]-start_rss), 'offloaded_sources': count}
    if by_source:
        info.update(serial_screen_seconds=sum(by_source.values()), largest_source_screen_seconds=max(by_source.values()))
    return (selection, demand), info


def run_panel(path, order):
    manifest = json.loads((path/'panel.json').read_text()); refs = json.loads((path/'reference-lengths.json').read_text())
    if manifest['panel'] != path.name:
        raise ValueError('wrong panel')
    datasets = prep.table(path,'metadata/datasets.tsv',('dataset_name','fasta_relpath'))
    assignments = prep.table(path,'metadata/chr_assignments.tsv',('dataset_name','seq_name','assigned_chr_name'))
    sequences = prep._dataset_sequences(path, datasets); matrices = json.loads((path/'base-alignments.json').read_text())
    trials = []; captured = []
    def take(data):
        captured.append(data)
        return SELECT(data)
    start = monotonic()
    with patch.object(adm,'select_q0_paths',take):
        threshold.initial_questions(path, sequences, refs, assignments, matrices)
    load_and_warmup = monotonic()-start
    data, = captured
    expected = None
    for cores in order:
        output, row = measure(data, assignments, cores)
        if expected is None:
            expected = output
        elif output != expected:
            raise ValueError('admission, path, occupied intervals or first request differs: '+path.name)
        trials.append(row)
        del output
    return {'panel': path.name, 'parts': len(data.parts), 'sources': len(data.sources), 'source_bp': sum(map(len,sequences.values())),
            'warmup_and_read_seconds': load_and_warmup, 'trials': trials}


if __name__ == '__main__':
    import sys
    result = run_panel(Path(sys.argv[1]).resolve(strict=True), [int(v) for v in sys.argv[2].split(',')]); print(json.dumps(result),flush=True)
