"""Compare original and indexed Q0 pair acceptance on bounded archived links.

No mapper, reference rebuild or main writes. Compare ordered returned blocks
and evidence IDs, not merely aggregate coverage. Full admission and selection
on the project's complete placement graph are separate acceptance steps.
"""
import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time

from benchmark_regional_mapper_dispatch import LOOKUP_SHA, TRACE_SHA, digest
from lgz_core import q0_paths as old
from probe_regional_cap_consumer import neutral_placement, source
from probe_regional_intra_deferral import choose
from replay_regional_reciprocal_coverage import MIB, bound_bytes, load, projected

OLD_SHA = '9739dc115e6b0468ce46aac0f583cb23c8bbcd0e88aa09d71cad6814f87dbec9'
NEW_SHA = '1578e60a68ed9d86356702245a89031fc9fb8b58f3622911747d5a93e5de21db'


def signature(blocks):
    return [(b.left.start, b.left.end, b.right.start, b.right.end, evidence) for b, evidence in blocks]


def ranked_groups(groups):
    scored = sorted((sum(len(link.hit.cigar) for link in links), target, links)
                    for target, links in groups.items() if 2 <= len(links) <= 48)
    eligible = [row for row in scored if 2 <= row[0] <= 220]
    if len(eligible) <= 4:
        return eligible
    return [eligible[0], eligible[(len(eligible)-1)//2], eligible[-2], eligible[-1]]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('workspace', 'trace', 'lookup', 'indexed', 'output'):
        p.add_argument('--'+n, type=Path, required=True)
    a = p.parse_args()
    work, out, indexed = a.workspace.resolve(strict=True), a.output.resolve(), a.indexed.resolve(strict=True)
    if out.is_relative_to(work) or indexed.is_relative_to(work) or digest(old.__file__) != OLD_SHA or digest(indexed) != NEW_SHA:
        raise ValueError('unaligned workspace or gate identity')
    spec = importlib.util.spec_from_file_location('lgz_core.q0_paths_candidate_proof', indexed)
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    trace = json.loads(bound_bytes(a.trace, TRACE_SHA, 4*MIB))
    lookup = json.loads(bound_bytes(a.lookup, LOOKUP_SHA, 32*MIB))
    policy = old.PathPolicy()
    rows = []
    totals = Counter()
    calls = 0
    total = 0
    for cohort, row in choose(trace, limit=4):
        query, targets, raw = load(work, row, lookup, 64*MIB-total)
        total += len(raw)
        groups = defaultdict(list)
        key = query.segment_id
        for hit in projected(query, targets, raw, row['raw_receipt']):
            groups[hit.target_name].append(old.PairLink(hit, source(key, lookup), source(hit.target_name, lookup)))
        left = neutral_placement(key, '+', lookup)
        for ops, target, links in ranked_groups(groups):
            previous, next_ = set(), set()
            accepted = 0
            for strand in ('+', '-'):
                right = neutral_placement(target, strand, lookup)
                for supported in (False, True):
                    # Alternate which gate runs first to reduce warm-cache bias.
                    order = (('old', old), ('indexed', candidate))
                    if calls % 2:
                        order = order[::-1]
                    results = {}
                    for label, module in order:
                        t = time.process_time()
                        result = module.qualify_pair_blocks(left, right, links, policy, require_supported=supported)
                        totals[label] += time.process_time() - t
                        results[label] = signature(result)
                    if results['old'] != results['indexed']:
                        raise ValueError('indexed gate changes ordered qualified blocks or evidence IDs')
                    previous.update(link.hit.strand for link in links)
                    next_.update(block[-1] for block in results['old'])
                    accepted += len(results['old'])
                    calls += 1
            rows.append({'cohort':cohort, 'archives':row['raw_receipt_sha256'], 'links':len(links), 'cigar_ops':ops,
                         'distinct_strands':len(previous), 'qualified_blocks_across_calls':accepted,
                         'qualified_evidence_ids':len(next_)})
        print(json.dumps({'cohort':cohort, 'checked_windows_paf_bytes':total, 'calls_equal_to_date':calls}), flush=True)
    if calls < 24 or not any(r['qualified_evidence_ids'] for r in rows):
        raise ValueError('insufficient nonempty parity evidence')
    with out.open('x') as handle:
        json.dump({'status':'real_regional_pair_gate_parity_only', 'node':socket.gethostname(),
                   'ordered_blocks_and_evidence_ids_equal':True, 'paf_bytes':total, 'calls':calls,
                   'old_gate_sha256':OLD_SHA, 'indexed_gate_sha256':NEW_SHA,
                   'cpu_seconds_only_pair_gate':dict(totals), 'main_workspace_modified':False,
                   'not_full_q0_selection':True, 'source_pair_counts':dict(Counter(r['cohort'] for r in rows)),
                   'pairs':rows}, handle, sort_keys=True, indent=2)
        handle.write('\n')


if __name__ == '__main__':
    main()
