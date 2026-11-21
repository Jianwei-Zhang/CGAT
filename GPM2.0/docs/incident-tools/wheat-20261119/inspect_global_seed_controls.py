"""Explain a failed exact-coordinate control, without changing its acceptance.

Query/target marginal coverage is deliberately reported as a coarser diagnostic,
not equivalent pairwise geometry. This never maps or writes production evidence.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from probe_global_seed_controls import sha,signature,retention


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('control-dir','workspace','lookup-dir'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();root=a.control_dir.resolve(strict=True)
    sys.path[:0]=[str(root/'package'),str(a.workspace/'.prepare_lib/tools')]
    from lgz_core.q0_alignments import parse_paf_line,read_paf
    from lgz_core.q0_sources import merged_intervals
    from lgz_core.q0_preparation import atomic_write_json
    summary=json.loads((root/'summary.json').read_text());index=json.loads((root/'baseline-query-index.json').read_text())
    if summary['status']!='global_seed_controls_complete':raise ValueError('no complete controlled result')
    baseline=a.workspace/index['baseline_identity']['path'];candidate=root/'result.paf'
    identities={baseline:index['baseline_identity']['sha256'],candidate:summary['result_sha256']}
    before={path:signature(path) for path in identities}
    for path,value in identities.items():
        if sha(path)!=value:raise ValueError('controlled output changed')
    lookup_path=a.lookup_dir/'source-part-lookup.json'
    if sha(lookup_path)!=json.loads((a.lookup_dir/'receipt.json').read_text())['lookup_sha256']:raise ValueError('lookup changed')
    lookup=json.loads(lookup_path.read_text())
    def empty():return {'query':defaultdict(list),'target':defaultdict(list),'best':{},'any_query':defaultdict(list)}
    old={key:empty() for key in index['controls']};new={key:empty() for key in index['controls']}
    def add(table,hit,minimum):
        if hit.matches/hit.block_length<.95 or lookup[hit.query_name]['dataset']==lookup[hit.target_name]['dataset']:return
        blocks=[b for b in hit.aligned_blocks() if b.operation!='X'];paired=sum(b.query.length for b in blocks)
        if paired<minimum:return
        row=table[hit.query_name];key=(hit.target_name,hit.strand)
        row['best'][key]=max(row['best'].get(key,0),paired)
        for block in blocks:
            row['query'][key].append(block.query);row['target'][key].append(block.target)
            row['any_query']['all'].append(block.query)
    with baseline.open('rb') as stream:
        for key,ranges in index['ranges'].items():
            for start,size,line,count in ranges:
                stream.seek(start)
                for number in range(count):
                    hit=parse_paf_line(stream.readline().decode(),artifact=str(baseline),line_number=line+number)
                    if hit.query_name!=key:raise ValueError('baseline query index changed')
                    add(old,hit,10000)
                if stream.tell()!=start+size:raise ValueError('baseline query extent changed')
    native_spec=json.loads((baseline.parent/'success.json').read_text())['spec']
    for hit in read_paf(candidate,query_lengths={k:lookup[k]['length'] for k in index['controls']},
                        target_lengths={k:lookup[k]['length'] for k in native_spec['target_ids']}):add(new,hit,100)
    reports=[]
    for key in index['controls']:
        left,right=old[key],new[key]
        best=sorted(left['best'],key=lambda k:(-left['best'][k],k))[:5]
        reports.append({'query':key,'baseline_target_strand_pairs':len(left['best']),
            'retained_target_strand_pairs':len(set(left['best'])&set(right['best'])),
            'query_marginal_by_target':retention(left['query'],right['query'],merged_intervals),
            'target_marginal_by_target':retention(left['target'],right['target'],merged_intervals),
            'query_coverage_any_target':retention(left['any_query'],right['any_query'],merged_intervals),
            'five_longest_native_target_pairs':[{'target':pair[0],'strand':pair[1],'native_best_paired_bp':left['best'][pair],
                'query_retention':retention({pair:left['query'][pair]},right['query'],merged_intervals),
                'target_retention':retention({pair:left['target'][pair]},right['target'],merged_intervals)} for pair in best]})
    if any(signature(path)!=before[path] for path in identities):raise ValueError('control output changed during inspection')
    report={'status':'coarse_diagnostics_only','original_exact_coordinate_gate_passed':summary['all_long_control_coordinates_retained'],
            'acceptance_changed':False,'production_modified':False,'controls':reports}
    atomic_write_json(Path('diagnostics.json'),report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
