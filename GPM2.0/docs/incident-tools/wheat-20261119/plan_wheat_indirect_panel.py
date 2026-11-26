"""All short selected overlap controls matching the retired queries' *indirect-only* demand role.

Preregister on the frozen wheat admission/request alone. No native outcome is used in selection.
"""
from collections import Counter
from pathlib import Path
import json,sys
from bound_regional_scope_from_native_receipts import LOOKUP_SHA
from measure_wheat_junction_bound import frozen
from plan_wheat_panel_neighborhoods import PANEL
from probe_wheat_native_pair_scope import checked
from wheat_selection_checkpoint import need


def choose(paths,lookup,requests,former):
    part={(x['dataset'],x['contig']):k for k,x in lookup.items()}; key=lambda s:part[s.dataset,s.contig]
    need(len(part)==len(lookup),'not unique whole sources')
    spans={part[s['dataset'],s['contig']]:ivs for s,ivs in requests}; keep=set(spans);cases=[];all_sizes=Counter()
    for path in paths:
        for i,join in enumerate(path.joins):
            if join.kind!='sequence_overlap':continue
            l,r=path.slices[i:i+2];a,b=key(l.source),key(r.source)
            lc=l.interval.end if l.orientation=='+' else l.interval.start
            rc=r.interval.start if r.orientation=='+' else r.interval.end
            for q,t,cut in ((a,b,rc),(b,a,lc)):
                # If the query itself has a question, any untested partner could matter;
                # that is a different branch of question-driven native scope sizing.
                if q in keep or q in former or t not in keep or q==t:continue
                strand='+' if l.orientation==r.orientation else '-';all_sizes[strand]+=1
                if lookup[q]['length']>500000:continue
                distance=min(max(lo-cut,cut-hi,0) for lo,hi in spans[t]);cases.append(dict(
                    stratum='indirect-'+path.chromosome+'-'+strand,q=q,t=t,join=join.join_id,kind=join.kind,
                    left=a,right=b,chromosome=path.chromosome,left_strand=l.orientation,right_strand=r.orientation,
                    left_cut=lc,right_cut=rc,partner_retained=True,query_bp=lookup[q]['length'],target_cut_distance_to_demand=distance))
    return cases,sorted(keep),dict(all_sizes)


def plan(folder,result,lookup_file,earlier_panel):
    summary,d,_,paths=frozen(folder,result);look=checked(lookup_file,LOOKUP_SHA);earlier=checked(earlier_panel,PANEL)
    former={k for k,v in look.items() if (v['dataset'],v['contig']) in {('JM19_flye_ABD','JM19flyeA_contig_4549'),('JM19_hifiasm','ptg000010l')}}
    need(len(former)==2 and earlier['selection']==summary['selection_chain'] and earlier['questions']==summary['questions'],'foreign cohort')
    cases,keep,all_sizes=choose(paths,look,d['source_intervals'],former);queries=sorted({r['q'] for r in cases})
    need(keep==earlier['retained'] and set(earlier['queries'])<=set(keep) and not set(queries)&set(keep) and len(queries)==3 and len(cases)==4,'role counts differ')
    need(len({v['join'] for v in cases})==len({v['stratum'] for v in cases})==len(cases) and any(v['target_cut_distance_to_demand']==0 for v in cases),'missing original contact or duplicate case')
    return dict(schema='wheat_indirect_only_native_panel_v1',lookup=LOOKUP_SHA,selection=summary['selection_chain'],questions=summary['questions'],prior_panel=PANEL,
                retained=keep,queries=queries,cases=cases,directed_join_controls_all_sizes=all_sizes,prior_direct_query_count=len(earlier['queries']))

if __name__=='__main__':
    with Path(sys.argv[5]).open('x') as f:json.dump(plan(*map(Path,sys.argv[1:5])),f,sort_keys=True,separators=(',',':'));f.write('\n')
