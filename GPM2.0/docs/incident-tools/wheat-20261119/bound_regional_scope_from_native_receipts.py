"""Read-only metadata bound, not a count of remaining native mapper calls.

A part outside every completed matrix's query side can only have tested edges
against those query sides. If the required anchor set contains >1 other part,
that part cannot be fully satisfied. Only the union of native query IDs can
skip whole parents. Bound that union's possible 100kb partial windows without
reading DNA, PAF or the main process's live Python objects. Future parent-native
fallback may replace many windows: this bound is NOT an exact mapping queue.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

EXPECTED={
 'q0-map-8024dde83cbf20e7ffa6d8ee':'994bfaa20bd68d035bedb7d8abacf616d826ebbb0bdc9c2cdc0b1e13b561245e',
 'q0-map-2b19c2c859bdfb5f2e9177e8':'ba5553ff1640cd1feff0db518b671baabed44fba84e02c7992e30a1cb76dd50a',
 'q0-map-a2e519761e94eff6ca09e121':'c36e5d98b8cbeac165865060565ed8c8953824f42baafa9c7db2e94b1ec7679f',
 'q0-map-b30137a13323db8a99874448':'26e6cb45d97322add5409035f06cdbeed6a2f367ea5ceb6ee5aed3b0e57442f3'}
LOOKUP_SHA='2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89'


def window_bound(length,policy):
    if type(length) is not int or length<1:raise ValueError('invalid source length')
    if length<policy.minimum_uncovered_bases:return 0
    # Distinct groups have at least 2*context+1 bases between them and each
    # contains at least minimum_uncovered_bases. All group spans fit in length.
    gap=2*policy.context_bases+1
    groups=(length+gap)//(policy.minimum_uncovered_bases+gap)
    # Sum ceil(span/core) <= floor(sum(span)/core)+number_of_groups.
    return length//policy.core_bases+groups


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--lookup',type=Path,required=True)
    p.add_argument('--package-dir',type=Path,required=True);p.add_argument('--planned-windows',type=int,required=True)
    a=p.parse_args();work=a.workspace.resolve(strict=True)
    if Path.cwd().resolve().is_relative_to(work) or a.planned_windows<1:raise ValueError('invalid readonly scope')
    sys.path.insert(0,str(a.package_dir))
    from lgz_core.common import stable_id
    from lgz_core.q0_query_windows import WindowPolicy
    lookup_raw=a.lookup.read_bytes()
    if hashlib.sha256(lookup_raw).hexdigest()!=LOOKUP_SHA:raise ValueError('source-part lookup changed')
    lookup=json.loads(lookup_raw);root=work/'grt/evidence/q0_prepare/tasks'
    if {p.parent.name for p in root.glob('*/success.json')}!=set(EXPECTED):
        raise ValueError('complete native matrix set changed; refresh rather than silently omit it')
    queries=set();rows=[];anchor_sets=[]
    for key,expected in EXPECTED.items():
        path=root/key/'success.json';raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('native success receipt changed: '+key)
        r=json.loads(raw);s=r['spec']
        if r['status']!='success' or s['schema']!='lgz_q0_mapping_v1' or stable_id('q0-map',s)!=key:
            raise ValueError('invalid completed native matrix identity')
        for pid,sha in s['members']:
            if lookup[pid]['sequence_sha256']!=sha:raise ValueError('matrix source identity changed')
        queries.update(s['query_ids'])
        if len(s['target_ids'])>10000:anchor_sets.append(frozenset(s['target_ids']))
        rows.append({'task_id':key,'query_parts':len(s['query_ids']),'target_parts':len(s['target_ids']),
            'query_bases':sum(lookup[k]['length'] for k in s['query_ids']),'receipt_sha256':expected})
    if not anchor_sets or any(s!=anchor_sets[0] for s in anchor_sets):raise ValueError('reference anchor sets differ')
    anchor=anchor_sets[0]
    if len(anchor-queries)<=1:raise ValueError('non-query parts might already have complete anchor coverage')
    monitor=Path('/share/home/xbzhang26/cgat-reads-debug/logs/wheat-live-parallel-20261122-062306.jsonl')
    with monitor.open('rb') as stream:
        stream.seek(max(0,monitor.stat().st_size-65536));tail=stream.read()
    lines=tail.splitlines()
    if not tail.endswith(b'\n'):lines.pop()
    live=next(r for r in json.loads(lines[-1]) if r['job']==43010335)
    if (live['state']!='RUNNING' or live['expected_run']!='20261121T222113Z-1973018-f3b56813'
            or live['regional_progress']['planned']!=a.planned_windows):raise ValueError('current run/phase changed')
    policy=WindowPolicy(core_bases=100000,context_bases=10000,trigger_query_bases=1,trigger_longest_bases=1,minimum_uncovered_bases=100)
    skip_bound=sum(window_bound(lookup[k]['length'],policy) for k in queries)
    report={'status':'native_matrix_parent_skip_metadata_upper_bound','complete_native_matrices':rows,
      'reference_anchor_parts':len(anchor),'union_native_query_parts':len(queries),
      'union_native_query_bases':sum(lookup[k]['length'] for k in queries),
      'potentially_skipped_partial_window_upper_bound':skip_bound,'actual_logged_planned_windows':a.planned_windows,
      'live_observer_at':live['at'],'latest_regional_progress':live['regional_progress'],
      'unaccounted_planned_windows_at_latest_log_after_maximum_skips_and_completed_pending_upper_bound':max(0,a.planned_windows-skip_bound-live['regional_progress']['completed']-99-14),
      'windows_not_fully_covered_by_complete_native_matrices_lower_bound':max(0,a.planned_windows-skip_bound),
      'metadata_only_not_full_output_validation':True,'source_dna_or_paf_read':False,'main_workspace_modified':False,
      'limitations':['counts original planned windows before subtracting current completed regional tasks',
       'includes possibly absent native-query parents/holes, so skip bound deliberately overestimates skips',
       'future regional or whole-parent native fallback is not predicted; this is not remaining minimap2 process count',
       'partial discovery targets contain the unchanged FIRST/weak seed reference-anchor inventory; pairwise-added targets may also exist']}
    Path('summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
