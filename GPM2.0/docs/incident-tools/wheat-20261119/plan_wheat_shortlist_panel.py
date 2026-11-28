"""Predeclare short whole queries and true wheat joins before running either native library."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys

from bound_regional_scope_from_native_receipts import LOOKUP_SHA
from measure_wheat_junction_bound import frozen
from probe_wheat_native_pair_scope import checked
from wheat_selection_checkpoint import need


def plan(folder, result, lookup_path):
    summary, detail, positions, paths = frozen(folder, result)
    lookup = checked(lookup_path, LOOKUP_SHA)
    parts = {(x['dataset'],x['contig']): k for k,x in lookup.items()}
    key = lambda s: parts[s.dataset,s.contig]
    keep = {parts[s['dataset'],s['contig']] for s,spans in detail['source_intervals'] if spans}
    retired = {parts['JM19_flye_ABD','JM19flyeA_contig_4549'],parts['JM19_hifiasm','ptg000010l']}
    # Independent of the two future mapper outputs. Multiplicity means distinct admitted placements,
    # not a claim that the alternate won or that every repeat is represented.
    multiplicity = Counter()
    with (folder/'admission.jsonl').open('rb') as f:
        for off in positions.values():
            for pos in off:
                f.seek(pos); p=json.loads(f.readline())['Placement']; multiplicity[p[1]] += 1
    bins = defaultdict(list)
    for path in paths:
        for i,j in enumerate(path.joins):
            l,r=path.slices[i:i+2]; strand='+' if l.orientation==r.orientation else '-'
            for a,b in ((l,r),(r,l)):
                q,t=key(a.source),key(b.source)
                if q==t or q in retired or lookup[q]['length']>500000: continue
                if j.kind=='sequence_overlap':
                    role='outside' if t not in keep else 'repeat' if max(multiplicity[q],multiplicity[t])>1 else 'inside'
                elif j.kind=='reference_unknown' and t in keep: role='gap'
                else: continue
                row=dict(q=q,t=t,kind=j.kind,chromosome=path.chromosome,join=j.join_id,left=key(l.source),right=key(r.source),
                         left_strand=l.orientation,right_strand=r.orientation,left_cut=l.interval.end if l.orientation=='+' else l.interval.start,
                         right_cut=r.interval.start if r.orientation=='+' else r.interval.end,query_bp=lookup[q]['length'],
                         alternative_placements=max(multiplicity[q],multiplicity[t]),partner_retained=t in keep)
                bins[role+strand].append(row)
    picked=[]; queries=set();joins=set()
    for role in ('inside+','inside-','repeat+','repeat-','outside+','outside-','gap+','gap-'):
        for row in sorted(bins[role],key=lambda v:sha256((v['join']+v['q']).encode()).digest()):
            if row['q'] not in queries and row['join'] not in joins:
                picked.append(dict(stratum=role,**row));queries.add(row['q']);joins.add(row['join']);break
    need(len(queries)>=4 and any(r['kind']=='sequence_overlap' and r['partner_retained'] and r['left_strand']==r['right_strand'] for r in picked) and any(r['kind']=='sequence_overlap' and r['partner_retained'] and r['left_strand']!=r['right_strand'] for r in picked),'uninformative control panel')
    need(len(lookup)==38267 and len(keep)==3755 and sum(lookup[k]['length'] for k in keep)==2302475263,'different wheat libraries')
    return dict(schema='wheat_shortlist_preregistered_v1',selection=summary['selection_chain'],questions=summary['questions'],lookup=LOOKUP_SHA,
                cases=picked,queries=sorted(queries),retained=sorted(keep),available={k:len(v) for k,v in bins.items()})


if __name__=='__main__':
    with Path(sys.argv[4]).open('x') as f:json.dump(plan(*map(Path,sys.argv[1:4])),f,sort_keys=True,separators=(',',':'));f.write('\n')
