"""Report geometry and next-request differences from the fully calibrated wheat chromosome graphs."""
import json,sys
from collections import Counter
from pathlib import Path
from compare_wheat_panel_chromosomes import MAPPING
from bound_regional_scope_from_native_receipts import LOOKUP_SHA
from plan_wheat_panel_neighborhoods import INDIRECT,pinned_panel
from probe_wheat_native_pair_scope import checked
from summarize_wheat_paired_outcomes import load,footprint,request_delta
from wheat_selection_checkpoint import need


def group_summary(arms,expected,original_demand):
    old,full,small=[arms[x] for x in ('original','full','reduced')]
    for v in (old,full,small):
        need([r['stratum'] for r in v['cases']]==expected and v['request_assessable']==(v['selected'] is not None),'missing controls')
        if (p:=v['selected']) is not None:need(p['slices'] and len(p['slices'])==len(p['joins'])+1,'invalid path geometry')
    need(old['request_assessable'] and all(v['old_junction_selected'] for v in old['cases']),'original graph failed positive calibration')
    f,r=full['selected'],small['selected'];comparable=f is not None and r is not None
    same_order=([s[:3] for s in f['slices']]==[s[:3] for s in r['slices']]) if comparable else None
    delta=request_delta(full['request'],small['request'],original_demand) if full['request_assessable'] and small['request_assessable'] else None
    return dict(original_rows=old['pair_rows'],full_rows=full['pair_rows'],reduced_rows=small['pair_rows'],same_paths=f==r,
                same_source_order_and_strand=same_order,changed_cut_slices=(sum(x[3:]!=y[3:] for x,y in zip(f['slices'],r['slices'])) if same_order else None),
                same_join_types_and_gap_lengths=(f['joins']==r['joins'] if comparable else None),full_keeps_entire_original_path=f==old['selected'],
                reduced_keeps_entire_original_path=r==old['selected'],request_delta=delta,
                cases=[dict(stratum=a['stratum'],original_selected=True,full_selects_old=a['old_junction_selected'],reduced_selects_old=b['old_junction_selected']) for a,b in zip(full['cases'],small['cases'])])


def case_edge(raw,case,lookup):
    """Separate a nearby cut of the same directed source pair from an entirely different adjacency."""
    p=raw['selected']; out=[]
    if p is None:return dict(present_path=False)
    l,r=(lookup[case[k]] for k in ('left','right')); lname=(l['dataset'],l['contig']);rname=(r['dataset'],r['contig'])
    for left,j,right in zip(p['slices'],p['joins'],p['slices'][1:]):
        if (tuple(left[:2]),tuple(right[:2]))!=(lname,rname):continue
        same_strand=(left[2],right[2])==(case['left_strand'],case['right_strand'])
        lc=left[4] if left[2]=='+' else left[3];rc=right[3] if right[2]=='+' else right[4]
        out.append(dict(same_strands=same_strand,kind=j[0],left_shift_bp=lc-case['left_cut'],right_shift_bp=rc-case['right_cut']))
    return dict(present_path=True,left_source_selected=any(tuple(x[:2])==lname for x in p['slices']),
                right_source_selected=any(tuple(x[:2])==rname for x in p['slices']),directed_neighbors=out)


def describe_path(arm):
    p=arm['selected']
    if p is None:return None
    return dict(slices=len(p['slices']),source_slice_bp=sum(e-b for _,_,_,b,e in p['slices']),
                join_kinds=Counter(j[0] for j in p['joins']),gap_bp=sum(j[1] for j in p['joins']),
                weak_placement=arm['counts'].get('weak_placement',0),unproven_join=arm['counts'].get('unproven_join',0))


def summarize(path,panel_file,questions_file,lookup_file):
    lookup=checked(lookup_file,LOOKUP_SHA)
    doc,digest=load(path);panel,pin=pinned_panel(panel_file);demand=footprint(checked(questions_file,panel['questions'])['source_intervals'])
    need(doc['schema']=='wheat_indirect_full_chromosome_graphs_v1' and pin==INDIRECT==doc['panel'] and doc['mapping']==MAPPING and doc['selection']==panel['selection'] and doc['questions']==panel['questions'] and doc['mapper_starts']==0 and doc['published_q0'] is False,'unbound whole-graph trial')
    groups=sorted({r['chromosome'] for r in panel['cases']});need(sorted(doc['groups'])==groups==sorted(doc['placements']),'missing chromosome');out={}
    for c in groups:
        g=group_summary(doc['groups'][c],[r['stratum'] for r in panel['cases'] if r['chromosome']==c],demand);g['placements']=doc['placements'][c];out[c]=g
        g['path_metrics']={k:describe_path(v) for k,v in doc['groups'][c].items()}
        named={v['stratum']:v for v in panel['cases'] if v['chromosome']==c}
        for row in g['cases']:
            case=named[row['stratum']]; row['full_edge']=case_edge(doc['groups'][c]['full'],case,lookup);row['reduced_edge']=case_edge(doc['groups'][c]['reduced'],case,lookup)
            for k in ('full','reduced'):
                matches=any(e['same_strands'] and e['kind']==case['kind'] and e['left_shift_bp']==e['right_shift_bp']==0 for e in row[k+'_edge'].get('directed_neighbors',[]))
                need(matches==row[k+'_selects_old'],'named junction differs from whole path geometry')
        need(g['same_paths']==doc['same_selected'][c] and (None if g['request_delta'] is None else g['request_delta']['same'])==doc['same_request'][c],'raw graph decisions disagree with geometry')
    return dict(schema='wheat_indirect_calibrated_graph_summary_v1',result=digest,panel=pin,mapping=MAPPING,questions=panel['questions'],selection=panel['selection'],groups=out,limits='All admitted placements, competitors and old links in each chromosome graph; locations fixed to the real frozen whole-wheat admission, not new whole-wheat admission. Per-chromosome request lengths are not global unique bases. No old parent mapped.')

if __name__=='__main__':print(json.dumps(summarize(*map(Path,sys.argv[1:5])),sort_keys=True,indent=2))
