"""Diagnostic-only exact paired-anchor chains; no mapper or production hooks."""
from bisect import bisect_left, bisect_right
from heapq import heappush, heappop
from lgz_core.q0_sources import Interval, merged_intervals
from lgz_core import q0_admission as adm


def chain(anchors, strand):
    """Maximum summed support of source-disjoint, collinear actual anchors.

    No tolerance, reference hull interpolation, or chromosome preference. This
    conservative interval-chain objective may discard partially overlapping
    anchors; its effect must be reported, not claimed globally optimal coverage.
    """
    rows=sorted(set(anchors),key=lambda a:(a.source.start,a.source.end,a.reference.start,a.reference.end,a.evidence_id))
    if not rows:return ()
    def coords(a):return (a.reference.start,a.reference.end) if strand=='+' else (-a.reference.end,-a.reference.start)
    ends=sorted(set(coords(a)[1] for a in rows));tree=[(0,-1)]*(len(ends)+1);heap=[];scores=[];previous=[]
    def update(pos,value):
        while pos<len(tree):
            if value>tree[pos]:tree[pos]=value
            pos+=pos&-pos
    def query(pos):
        best=(0,-1)
        while pos:
            best=max(best,tree[pos]);pos-=pos&-pos
        return best
    for i,a in enumerate(rows):
        while heap and heap[0][0]<=a.source.start:
            _,j=heappop(heap);update(bisect_left(ends,coords(rows[j])[1])+1,(scores[j],j))
        rstart,_=coords(a);score,prev=query(bisect_right(ends,rstart));scores.append(score+a.source.length);previous.append(prev);heappush(heap,(a.source.end,i))
    j=max(range(len(rows)),key=lambda i:(scores[i],i));out=[]
    while j!=-1:out.append(rows[j]);j=previous[j]
    out.reverse()
    if not adm._ordered(out,strand):raise ValueError('chain is not collinear')
    if sum(a.source.length for a in out)!=adm._size(a.source for a in out):raise ValueError('overlapping chain support')
    return tuple(out)


def clipped(anchors, interval, strand):
    out=[]
    for a in anchors:
        ov=a.source.intersection(interval)
        if ov is not None:out.append(adm.ReferenceAnchor(ov,adm._project(a.source,a.reference,strand,ov),a.evidence_id))
    return tuple(out)


def footprint(placements):
    return adm._size(a.reference for p in placements for a in p.reference_blocks)


def trimmed_reference(placement,fraction=.99):
    """Sensitivity diagnostic only: central fraction of reference support.

    Never authorizes a placement or modifies the graph. Report separately from
    a proven erroneous-anchor classification.
    """
    rows=merged_intervals(placement.reference_intervals)
    if not rows:return ()
    total=sum(i.length for i in rows);trim=int(total*(1-fraction)/2)
    if not trim:return placement.reference_blocks
    def endpoint(amount,reverse=False):
        for iv in (reversed(rows) if reverse else rows):
            if amount<iv.length:return iv.end-amount if reverse else iv.start+amount
            amount-=iv.length
        raise ValueError('empty quantile')
    lo,hi=endpoint(trim),endpoint(trim,True);region=Interval(lo,hi);out=[]
    for a in placement.reference_blocks:
        ov=a.reference.intersection(region)
        if ov is not None:out.append(adm.ReferenceAnchor(adm._project(a.reference,a.source,placement.orientation,ov),ov,a.evidence_id))
    return tuple(out)
