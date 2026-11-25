"""4D second pass: keep collinear native sequence between local witnesses, never anchor in a mask."""
from bisect import bisect_right
from collections import Counter,defaultdict

from lgz_core import q0_admission as adm
from lgz_core.q0_source_screen import ordered_screens
from lgz_core.q0_sources import Interval,merged_intervals
from pilot_fast_group_run import GROUP

LOCAL_POLICY=dict(min_supported_bp=1000, min_supported_fraction=.50, max_unsupported_gap=32768,
                  gap_length_slack=1000, max_relative_gap_difference=.10)


def local_runs(part,groups,high,high_ids):
    candidates=[]
    for key,anchors in groups.items():
        ch,strand=key
        if ch!=GROUP or key not in high: continue
        other=merged_intervals(a.source for k,v in groups.items() if k!=key for a in v)
        ends=[v.end for v in other]
        def barrier(start,end):
            i=bisect_right(ends,start);return start<end and i<len(other) and other[i].start<end
        def axis(a):
            v=a.reference; return (v.start,v.end) if strand=='+' else (-v.end,-v.start)
        def emit(rows):
            if not rows:return
            supp=merged_intervals(a.source for a in rows); bp=sum(i.length for i in supp); span=Interval(supp[0].start,supp[-1].end)
            if bp<max(LOCAL_POLICY['min_supported_bp'],span.length*LOCAL_POLICY['min_supported_fraction']):return
            if not adm._ordered(rows,strand):return
            candidates.append(adm._placement(part,ch,strand,span,supp,rows,(a.evidence_id for a in rows),kind='reference'))
        rows=[]; last=None
        for a in sorted((a for a in anchors if a.evidence_id in high_ids),key=lambda x:(x.source,axis(x),x.evidence_id)):
            if barrier(a.source.start,a.source.end):continue
            if last is not None:
                gap=a.source.start-last.source.end; rgap=axis(a)[0]-axis(last)[1]
                if gap<0:
                    coherent=(gap==rgap)  # overlapping witnesses must give the same map
                else:
                    coherent=(0<=rgap<=LOCAL_POLICY['max_unsupported_gap'] and gap<=LOCAL_POLICY['max_unsupported_gap'] and
                              abs(gap-rgap)<=LOCAL_POLICY['gap_length_slack']+LOCAL_POLICY['max_relative_gap_difference']*max(gap,rgap) and
                              not barrier(last.source.end,a.source.start))
                if not coherent:emit(rows);rows=[];last=None
            rows.append(a)
            if last is None or a.source.end>last.source.end:last=a
        emit(rows)
    # A source interval can enter the chromosome at most once, even when different
    # alignments propose overlapping runs. Do not claim discarded intervals as donor evidence.
    ordered=sorted(candidates,key=lambda p:(p.interval.end,p.interval.start,p.placement_id));ends=[p.interval.end for p in ordered];best=[0];back=[]
    for i,p in enumerate(ordered):
        j=bisect_right(ends,p.interval.start,0,i);score=best[j]+sum(v.length for v in p.anchor_intervals); take=score>best[-1];best.append(max(score,best[-1]));back.append((j,take))
    result=[];i=len(back)
    while i:
        j,take=back[i-1]
        if take:result.append(ordered[i-1]);i=j
        else:i-=1
    return result[::-1]


def local_seeds(data):
    ap=adm.AdmissionPolicy(); selected=[]; counts=Counter(); ordered=sorted(data.parts.items()); ids={}
    for _,p in ordered:
        if p.source not in ids:
            ids[p.source]={h.evidence_id for h in data.reference_hits.get(p.source,()) if h.target_name==GROUP and
                           h.mapping_quality is not None and h.mapping_quality>=ap.minimum_reference_mapq and h.matches/h.block_length>=ap.minimum_reference_identity}
    allowed={k for k,p in ordered if ids[p.source]}
    for _,p,result in ordered_screens(data,ordered,allowed,ap,8,adm._request_reference_screen,lambda m:print(m,flush=True)):
        if result is None: counts['parts_without_group_anchor']+=1;continue
        groups,high,_,_=result  # the ordinary screen already subtracted ambiguous intervals from EACH witness
        rows=local_runs(p,groups,high,ids[p.source]);selected.extend(rows);counts['parts_with_local_seed' if rows else 'parts_without_admissible_local_run']+=1
    return selected,dict(counts)
