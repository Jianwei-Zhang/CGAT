"""Paired A/B raw geometry, plus the stock Q0 selector in a fixed two-source control.

No baseline PAF (or duplicate projection of it) is mixed into an arm. This is not a
whole-wheat reranking: whole-input admission/background effects are separate.
"""
from collections import Counter,defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys

from bound_regional_scope_from_native_receipts import LOOKUP_SHA
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_paths import PathGraph,PairLink,search_request_path
from lgz_core.q0_sources import SourceKey
from measure_wheat_junction_bound import frozen
from probe_wheat_native_pair_scope import checked
from wheat_selection_checkpoint import decode,need


def read_arm(path,pin,queries,keep,lookup,pairs,reduced):
    h=sha256();common=Counter();counts=Counter();by_pair=defaultdict(list); names={k:SourceKey(v['dataset'],v['contig']) for k,v in lookup.items()}
    with path.open('rb') as f:
        for i,line in enumerate(f,1):
            h.update(line);a=line.rstrip(b'\r\n').split(b'\t');q=a[0].decode();t=a[5].decode(); retained=t in keep
            need(q in queries and t in lookup and (retained or not reduced) and int(a[1])==lookup[q]['length'] and int(a[6])==lookup[t]['length'],'foreign PAF names/length')
            cg,=(v for v in a[12:] if v.startswith(b'cg:Z:'));need(a[4] in (b'+',b'-'),'bad strand'); counts['retained' if retained else 'excluded']+=1
            if retained:common[sha256(b'\t'.join([*a[:11],cg])).digest()]+=1
            key=frozenset((q,t))
            if key in pairs:
                hit=parse_paf_line(line.decode(),artifact=path.name,line_number=i);by_pair[key].append(PairLink(hit,names[q],names[t]))
    need(h.hexdigest()==pin,'PAF content changed'); return counts,common,by_pair


def calls(placements,links,left,right):
    g=PathGraph(placements,links,(),first_request=True); l,r=g.placements[left],g.placements[right]
    def source_cuts(j):
        # At an overlap the oriented left-end/right-start are between-base coordinates.
        cut=lambda p,x:p.interval.start+x if p.orientation=='+' else p.interval.end-x
        return [j.kind,cut(l,j.left_end),cut(r,j.right_start)]
    choices=[source_cuts(j) for j in g.joins(left,right)]
    path=search_request_path(g).path
    win=None if path is None else dict(slices=[[s.source.dataset,s.source.contig,s.orientation,s.interval.start,s.interval.end] for s in path.slices],
                                     joins=[x.kind for x in path.joins])
    return choices,win


def assess(folder,result,lookup_path,owner):
    summary,detail,positions,paths=frozen(folder,result); lookup=checked(lookup_path,LOOKUP_SHA)
    record=json.loads((owner/'mapping.json').read_bytes());panel=checked(owner/'panel.json',record['panel']);need(summary['selection_chain']==panel['selection'] and summary['questions']==panel['questions'],'foreign panel')
    keep=set(panel['retained']);qs=set(panel['queries']);cases=panel['cases'];expected={frozenset((r['q'],r['t'])) for r in cases};expected.update(frozenset([k]) for row in cases for k in (row['q'],row['t']))
    arms={k:read_arm(owner/(k+'.paf'),record['mapper'][k]['paf_sha256'],qs,keep,lookup,expected,k=='reduced') for k in ('full','reduced')}
    chroms={r['chromosome'] for r in cases};parts=defaultdict(list);selected={j.join_id:j for p in paths for j in p.joins}
    with (folder/'admission.jsonl').open('rb') as f:
        for c in chroms:
            for pos in positions[c]:
                f.seek(pos);p=decode(json.loads(f.readline()));parts[c,p.segment_id].append(p)
    rows=[]
    for row in cases:
        c=row['chromosome'];q=row['q'];t=row['t'];j=selected[row['join']];ps=[*parts[c,q],*parts[c,t]];baseline=[row['kind'],row['left_cut'],row['right_cut']];by={}
        for k,(_,_,links) in arms.items():
            rel=[*links[frozenset([q,t])],*links[frozenset([q])],*links[frozenset([t])]]
            choices,win=calls(ps,rel,j.left_id,j.right_id);by[k]=dict(pair_rows=len(links[frozenset([q,t])]),cuts=choices,selected=win,reproduces_frozen_cut=baseline in choices)
        rows.append(dict(stratum=row['stratum'],chromosome=c,join=row['join'],old=baseline,full=by['full'],reduced=by['reduced'],same_cuts=sorted(by['full']['cuts'])==sorted(by['reduced']['cuts']),same_local_path=by['full']['selected']==by['reduced']['selected']))
    fc,fg,_=arms['full'];sc,sg,_=arms['reduced'];return dict(schema='wheat_shortlist_paired_geometry_v1',mapping=record,panel=record['panel'],full_rows=fc,reduced_rows=sc,retained_geometry_shared=sum((fg&sg).values()),retained_geometry_only_full=sum((fg-sg).values()),retained_geometry_only_reduced=sum((sg-fg).values()),cases=rows,formal_q0=False,limits='Identical frozen placements for the two sources; each arm uses only its own native PAF. Not full-input re-admission, not the next whole-wheat request, not a test of the two retired parents.')

if __name__=='__main__':
    doc=assess(*map(Path,sys.argv[1:5])); out=Path(sys.argv[5]);
    with out.open('x') as f: json.dump(doc,f,sort_keys=True,indent=2);f.write('\n')
