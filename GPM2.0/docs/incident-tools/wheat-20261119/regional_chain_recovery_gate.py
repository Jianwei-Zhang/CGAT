"""Diagnostic per-core, per-dataset recovery gate for bounded exact extension.

Only validated, high-identity paired exact blocks count. Coarse chains and
mismatch blocks never count. Coverage is a recovery heuristic, not proof of
orthology, preservation of alternative copies, or whole-genome equivalence.
"""
from collections import defaultdict

from benchmark_regional_candidate_screen import merged


POLICY = {'version':1,'identity_numerator':95,'identity_denominator':100,
          'minimum_paired_record_bases':100,
          'cross_core_coverage_numerator':98,'cross_core_coverage_denominator':100,
          'intra_core_coverage_numerator':90,'intra_core_coverage_denominator':100}


def validated_core_coverage(path, case, read_paf):
    query=case['query'];values=defaultdict(list)
    for hit in read_paf(path,query_lengths={query.window_id:query.length},target_lengths=case['lengths']):
        if hit.matches*POLICY['identity_denominator'] < hit.block_length*POLICY['identity_numerator']:continue
        blocks=list(hit.aligned_blocks())
        if sum(b.query.length for b in blocks)<POLICY['minimum_paired_record_bases']:continue
        ds=case['td'][hit.target_name]
        for b in blocks:
            if b.operation=='X':continue
            start,end=b.query.start+query.start,b.query.end+query.start
            for lo,hi in query.cores:
                if max(start,lo)<min(end,hi):values[ds].append((max(start,lo),min(end,hi)))
    return {dataset:merged(values[dataset]) for dataset in sorted(set(case['td'].values()))}


def recovery_decision(cores, query_dataset, target_datasets, coverage):
    """Use every core and every dataset separately, never a weighted total."""
    datasets=set(target_datasets)
    if not datasets or not cores or set(coverage)!=datasets:raise ValueError('recovery inventory is incomplete')
    normalized=[];last=-1
    for lo,hi in cores:
        if type(lo) is not int or type(hi) is not int or lo<0 or hi<=lo or lo<last:raise ValueError('invalid canonical core frame')
        normalized.append((lo,hi));last=hi
    rows=[];fallback=False
    for dataset in sorted(datasets):
        intervals=merged(coverage[dataset]);kind='intra' if dataset==query_dataset else 'cross'
        numerator=POLICY[kind+'_core_coverage_numerator'];denominator=POLICY[kind+'_core_coverage_denominator']
        for lo,hi in normalized:
            covered=sum(max(0,min(hi,b)-max(lo,a)) for a,b in intervals)
            sufficient=covered*denominator >= (hi-lo)*numerator
            rows.append({'dataset':dataset,'kind':kind,'core':[lo,hi],'covered_bases':covered,
                         'minimum_ratio':[numerator,denominator],'sufficient':sufficient})
            if not sufficient:fallback=True
    return {'policy':dict(POLICY),'native_recovery_required':fallback,'cores':rows,
            'approximate_chains_counted_as_coverage':False,'coverage_is_orthology_or_copy_equivalence':False}
