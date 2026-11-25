"""Wheat cut-closure equivalence fixture runner. Use isolated imports for old and new arms.

The reference is the original whole-domain solver, with headroom only for the
known >200k case. The candidate uses the production island proof and its
uncapped final model. This checks geometry/coverage, not a real 3B completion.
"""
from hashlib import sha256
import json
from pathlib import Path
import sys

CASES = ('forward', 'reverse', 'touching', 'disjoint', 'shared_evidence',
         'required_endpoints', 'consistent_cycle', 'inconsistent_cycle', 'past_200000')


def setup(name):
    from lgz_core.q0_coverage import Equivalence
    from lgz_core.q0_sources import Interval, SourceKey
    a, b, c = (SourceKey('wheat_fixture', x) for x in 'abc')
    required = {s: [Interval(0, 64)] for s in (a, b, c)}
    def row(l, i, r, j, n, rev, eid):
        return Equivalence(l, Interval(i, i+n), r, Interval(j, j+n), rev, eid)
    ab = row(a, 0, b, 10, 20, False, 'ab'); bc = row(b, 14, c, 0, 8, False, 'bc')
    if name == 'forward': rows = [ab, bc]
    elif name == 'reverse': rows = [ab, row(b, 14, c, 0, 8, True, 'reverse')]
    elif name == 'touching': rows = [ab, row(b, 30, c, 5, 10, True, 'adjacent')]
    elif name == 'disjoint': rows = [ab, row(a, 22, b, 7, 2, True, 'different_axis')]
    elif name == 'required_endpoints':
        required[a] = [Interval(0, 20), Interval(40, 52)]
        required[b] = [Interval(4, 30), Interval(40, 50)]
        rows = [ab, bc, row(a, 42, b, 40, 8, True, 'other')]
    elif name == 'consistent_cycle': rows = [ab, bc, row(a, 4, c, 0, 8, False, 'ac')]
    elif name in ('inconsistent_cycle', 'shared_evidence'):
        rows = [ab, bc, row(a, 5, c, 0, 8, False, 'ac')]
        if name == 'shared_evidence':
            rows.extend([row(a, 41, c, 41, 10, False, 'ac'), row(a, 41, c, 41, 10, False, 'clean')])
    elif name == 'past_200000':
        n = 35_000; length = 2*n+2
        required = {s: [Interval(0, length)] for s in (a, b, c)}
        rows = [row(a, 0, b, 0, length, False, 'full')]
        rows.extend(row(a, 2*i+1, c, 2*i+1, 1, False, 'sparse') for i in range(n))
    else: raise ValueError(name)
    partial = [(a, Interval(3, 10)), (c, Interval(0, 7))]
    probes = [[], [(a, required[a][0])], partial, [(b, Interval(13, 17)), (a, Interval(2, 6))],
              [(a, Interval(0, 4)), (c, Interval(50, 53))], [(a, Interval(1, 3)), (a, Interval(2, 5))]]
    return required, rows, probes


def canonical(model, probes):
    # Atom IDs/union representatives are implementation details. Compare the
    # actual source spans, equivalence partition and relative orientation.
    anchors = {}; atoms = sha256()
    for i, ((source, span), (root, orientation)) in enumerate(zip(model.atoms, model.units)):
        anchor, first_flip = anchors.setdefault(root, (i, orientation))
        atoms.update(f'{source.dataset}:{source.contig}:{span.start}:{span.end}:{anchor}:{int(first_flip ^ orientation)}\n'.encode())
    scores, assessments = [], []
    for selected in probes:
        bp, dup, missing = model.assess(selected); score = model.unique_selected_bp(selected)
        if score != (None if dup else bp): raise ValueError('ranking coverage and full assessment disagree')
        m = sha256()
        for src, spans in missing:
            for r in spans: m.update(f'{src.dataset}:{src.contig}:{r.start}:{r.end}\n'.encode())
        scores.append(score); assessments.append([bp, dup, m.hexdigest()])
    return {'total_bp':model.total_bp, 'atoms':len(model.atoms), 'boundaries':model.boundary_count,
            'units':len(anchors), 'oriented_partition_sha256':atoms.hexdigest(), 'assessments':assessments}, scores


def run(arm):
    from lgz_core.q0_coverage import CoverageModel
    from lgz_core.q0_sources import Q0EvidenceError
    if arm not in ('reference','candidate'): raise ValueError('bad arm')
    for case in CASES:
        required, rels, probes = setup(case)
        if arm == 'reference':
            if case == 'past_200000':
                try: CoverageModel(required, rels, compact_first=True)
                except Q0EvidenceError as e:
                    if not all(t in str(e) for t in ('limit=200000','phase=propagation','observed_cuts=200001')): raise
                    print('REFERENCE_OLD_LIMIT_REPRODUCED', str(e), flush=True)
                else: raise ValueError('fixture did not reach old limit during propagation')
            kw = dict(maximum_boundaries=1_000_000) if case == 'past_200000' else {}
            orig = CoverageModel(required, rels, compact_first=True, **kw); excluded = orig.ambiguous_evidence_ids; del orig
        else:
            from lgz_core.q0_coverage import preliminary_ambiguity
            from lgz_core.q0_paths import PathPolicy
            if PathPolicy().maximum_coverage_boundaries is not None: raise ValueError('production cap still enabled')
            kw = {}; excluded = preliminary_ambiguity(required, rels, compact_first=True, progress=print)
        expected = {'ab','bc','ac'} if case in ('shared_evidence', 'inconsistent_cycle') else set()
        if set(excluded) != expected: raise ValueError((case, excluded, expected))
        model = CoverageModel(required, [r for r in rels if r.evidence_id not in excluded], compact_first=True, **kw)
        if model.ambiguous_evidence_ids or (case == 'past_200000' and model.boundary_count <= 200000):
            raise ValueError('wrong final coverage')
        coverage, scores = canonical(model, probes)
        with Path(f'{case}.{arm}.json').open('x') as out:
            json.dump(dict(ambiguous_ids=sorted(excluded), coverage=coverage,path_scores=scores), out, sort_keys=True);out.write('\n')
        print(arm,case,model.boundary_count,'cuts',len(excluded),'excluded',flush=True)


def compare():
    rows=[]
    for name in CASES:
        a,b=(Path(f'{name}.{arm}.json').read_bytes() for arm in ('reference','candidate'))
        if json.loads(a)!=json.loads(b):raise ValueError('geometry mismatch: '+name)
        rows.append(dict(name=name,reference_sha256=sha256(a).hexdigest(),candidate_sha256=sha256(b).hexdigest()))
    here=Path.cwd(); doc=dict(revision=(here/'latest.rev').read_text().strip(),snapshot_sha256=(here.parent.parent/'snapshot.sha').read_text().strip(),
                               job=(here/'geometry.jobid').read_text().strip(),cases=rows)
    with Path('review.pending.json').open('x') as f: json.dump(doc,f,sort_keys=True,indent=2);f.write('\n')
    print('NINE_MATCHED; human review pending',flush=True)


if __name__ == '__main__':
    compare() if sys.argv[1]=='compare' else run(sys.argv[1])
