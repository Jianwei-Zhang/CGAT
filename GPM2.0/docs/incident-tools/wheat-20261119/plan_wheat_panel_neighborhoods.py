"""Prespecify a local re-admission panel from the frozen reference placements alone, not either new PAF."""
from pathlib import Path
import json, sys
from measure_wheat_junction_bound import frozen
from lgz_core.q0_sources import merged_intervals
from wheat_selection_checkpoint import decode, need
from probe_wheat_native_pair_scope import checked
from bound_regional_scope_from_native_receipts import LOOKUP_SHA

PANEL='8ecec1cd21d0240dad8fe6e9fe8f3cd2d45e0d690f2e3931f404d88bfbc1985c'

def plan(folder,result,lookup_path,panel_file):
    panel=checked(panel_file,PANEL);lookup=checked(lookup_path,LOOKUP_SHA);summary,_,positions,paths=frozen(folder,result);out=[]
    need(panel['selection']==summary['selection_chain'],'foreign admission'); by_chr={p.chromosome:p for p in paths};groups={}
    with (folder/'admission.jsonl').open('rb') as f:
        for c in sorted({r['chromosome'] for r in panel['cases']}):
            ps={}
            for pos in positions[c]:f.seek(pos);p=decode(json.loads(f.readline()));ps[p.placement_id]=p
            groups[c]=ps
    for row in panel['cases']:
        c=row['chromosome'];ps=groups[c];path=by_chr[c];i,=(i for i,j in enumerate(path.joins) if j.join_id==row['join']);l,r=path.nodes[i:i+2]
        regions=merged_intervals((*ps[l].reference_intervals,*ps[r].reference_intervals));forced={ps[k].segment_id for k in path.nodes[max(i-1,0):i+3]}
        # Include whole sources on either side, actual reference co-locations (also off shortlist), and immediate selected flanks.
        parts=sorted(forced|{p.segment_id for p in ps.values() if any(a.intersection(b) for a in p.reference_intervals for b in regions)})
        need({row['q'],row['t']}<=set(parts),'missing panel partner');out.append(dict(stratum=row['stratum'],chromosome=c,join=row['join'],parts=parts,bp=sum(lookup[k]['length'] for k in parts)))
    return dict(schema='wheat_raw_readmission_neighborhoods_v1',panel=PANEL,selection=summary['selection_chain'],cases=out)

if __name__=='__main__':
    with Path(sys.argv[5]).open('x') as f:json.dump(plan(*map(Path,sys.argv[1:5])),f,sort_keys=True,separators=(',',':'));f.write('\n')
