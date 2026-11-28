"""Read sealed wheat checkpoint geometry, without mapping, selection or Q0 publication.

Run with the frozen producer tools and the sealed comparison helper on PYTHONPATH.
Inputs are a read-only local copy of new result/, selection/, snapshot.json and
its data/reference/IWGSC.fa.fai. All report percentages describe geometry,
not biological accuracy or equivalent coverage of two source assemblies.
"""
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import argparse
import json

SUMMARY='d23a49af479b6c9b81916518e8034d4044ea31b5c97229c5d0ce1624138fc9d4'
SNAPSHOT='2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d'


def union_bp(rows):
    end=-1;total=0
    for a,b in sorted(rows):
        if not 0<=a<b:raise ValueError('invalid interval')
        total+=max(0,b-max(a,end));end=max(end,b)
    return total


def run(root):
    from wheat_selection_checkpoint import decode
    from compare_wheat_local_only_paths import load_arm
    summary,_,admission,paths,_=load_arm(root,SUMMARY,'whole-wheat-local-supplement-v1')
    raw=(root/'snapshot.json').read_bytes()
    if sha256(raw).hexdigest()!=SNAPSHOT:raise ValueError('changed source snapshot')
    snapshot=json.loads(raw);relative='data/reference/IWGSC.fa.fai'
    expected=next(r for r in snapshot['files'] if r['path']==relative)
    raw=(root/relative).read_bytes()
    if len(raw)!=expected['size'] or sha256(raw).hexdigest()!=expected['sha256']:raise ValueError('changed reference index')
    lengths={r.split()[0]:int(r.split()[1]) for r in raw.decode().splitlines()}
    selected={x.placement_id:(g,x) for g,p in paths.items() for x in p.slices}
    source=defaultdict(list);reference=defaultdict(list);selected_ref=defaultdict(list);counts=defaultdict(int)
    with (root/'selection/admission.jsonl').open('rb') as stream:
        header=stream.readline();digest=sha256(header);n=0;ended=False
        for raw in stream:
            row=json.loads(raw)
            if isinstance(row,list):
                if row!=['end',n,digest.hexdigest()] or stream.read(1):raise ValueError('changed admission trailer')
                ended=True;break
            digest.update(raw);n+=1;p=decode(row);g=p.chromosome;counts[g]+=1
            if admission[g].get(p.placement_id)!=sha256(raw).hexdigest():raise ValueError('admission changed after chain verification')
            source[p.source].append((p.interval.start,p.interval.end))
            reference[g].extend((a.reference.start,a.reference.end) for a in p.reference_blocks)
            if p.placement_id not in selected:continue
            group,s=selected[p.placement_id]
            if group!=g or s.source!=p.source or s.orientation!=p.orientation or not p.interval.contains(s.interval):raise ValueError('path/admission mismatch')
            for anchor in p.reference_blocks:
                a=max(s.interval.start,anchor.source.start);b=min(s.interval.end,anchor.source.end)
                if a>=b:continue
                x=(anchor.reference.start+a-anchor.source.start if p.orientation=='+' else anchor.reference.start+anchor.source.end-b)
                selected_ref[g].append((x,x+b-a))
        if not ended:raise ValueError('incomplete admission')
    groups={g:{'reference_bp':lengths[g],'admitted_count':counts[g],'admitted_reference_union_bp':union_bp(reference[g]),
               'selected_slices':len(p.slices),'selected_source_bp':sum(s.interval.length for s in p.slices),
               'selected_reference_union_bp':union_bp(selected_ref[g]),'gap_count':sum(j.n_bp>0 for j in p.joins),
               'gap_placeholder_bp':sum(j.n_bp for j in p.joins)} for g,p in paths.items()}
    totals={key:sum(v[key] for v in groups.values()) for key in next(iter(groups.values()))}
    totals['admitted_source_union_bp']=sum(union_bp(v) for v in source.values())
    totals['selected_source_vs_reference_fraction']=totals['selected_source_bp']/totals['reference_bp']
    totals['selected_reference_covered_fraction']=totals['selected_reference_union_bp']/totals['reference_bp']
    return {'schema':'wheat_draft_absolute_extent_v1','new_summary_sha256':SUMMARY,'selection_chain':summary['selection_chain'],
            'totals':totals,'groups':groups,'mapper_calls':0,'selection_calls':0,'formal_q0_started':False,
            'decision':'Hold automatic full-flow launch: equality of two sparse drafts alone does not prove adequate whole-wheat coverage.',
            'scope':'Actual reference anchor unions, not bounding hulls. 100-N unknown-join placeholders are not measured biological gap lengths. Draft and formal selection share the ranking function, but these are not formal Q0 outputs. Admission loss and path exclusion require separate diagnosis; no cause inferred from these totals alone.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('inputs',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=run(a.inputs.resolve())
    with a.output.open('x') as stream:json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(result['totals'],indent=2))
