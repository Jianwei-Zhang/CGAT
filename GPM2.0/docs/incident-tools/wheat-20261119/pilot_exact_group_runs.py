"""4D E: clip actual CIGAR runs with integers; allocate Interval/Block only for returned geometry."""
from collections import Counter
from contextlib import contextmanager, ExitStack
from unittest.mock import patch
from lgz_core import q0_paths as paths
from lgz_core.q0_alignments import PafAlignment
from lgz_core.q0_retained_hits import RetainedHit
from lgz_core.q0_sources import Interval
from pilot_exact_group_kernel import may_overlap, AxesCache


def source_runs(link):
    h=link.hit
    if type(h) not in (RetainedHit,PafAlignment):
        for a,b in link.source_blocks():yield a.start,a.end,b.start,b.end
        return
    forward=h.strand=="+"; q=(h.query.start if forward else h.query.end)+link.query_offset; t=h.target.start+link.target_offset
    for n,op in (h._ops() if type(h) is RetainedHit else h.cigar):
        if op in ("M","=","X"):
            q1=q+n if forward else q-n
            if op!="X":yield (q,q1,t,t+n) if forward else (q1,q,t,t+n)
            q=q1;t+=n
        elif op=="I":q=q+n if forward else q-n
        elif op in ("D","N"):t+=n
        else:raise ValueError("unsupported unvalidated operation")


def pairs(link,left,right):
    direct=(left,right)==(link.query_source,link.target_source);swap=(right,left)==(link.query_source,link.target_source)
    if not direct and not swap:return
    for q0,q1,t0,t1 in source_runs(link):
        if direct:yield q0,q1,t0,t1
        if swap:yield t0,t1,q0,q1


def clipped(link,left,right):
    if not may_overlap(link,left,right):return ()
    ls,le=left.interval.start,left.interval.end;rs,re=right.interval.start,right.interval.end
    lf=left.orientation=="+";rf=right.orientation=="+";forward=link.hit.strand=="+";values=set()
    for a,z,b,y in pairs(link,left.source,right.source):
        # Run parameter increases along the genomic left axis. Constrain both axes on that same parameter.
        if forward:
            lo=max(0,ls-a,rs-b);hi=min(z-a,le-a,re-b)
        else:
            lo=max(0,ls-a,y-re);hi=min(z-a,le-a,y-rs)
        if lo>=hi:continue
        u,v=(b+lo,b+hi) if forward else (y-hi,y-lo)
        x,w=(a+lo-ls,a+hi-ls) if lf else (le-a-hi,le-a-lo)
        c,d=(u-rs,v-rs) if rf else (re-v,re-u)
        values.add((x,w,c,d))
    return tuple(paths.Block(Interval(x,w),Interval(c,d)) for x,w,c,d in sorted(values))


def axes(links,left,right,minimum):
    xs=[];ys=[]
    for link in links:
        rev=link.hit.strand=="-"
        for a,z,b,y in pairs(link,left,right):
            if z-a<minimum:continue
            mapping=(rev,y+a if rev else b-a)
            xs.append((a,z-minimum,mapping));ys.append((b,y-minimum,mapping))
    return paths._CompetingAxis(xs),paths._CompetingAxis(ys)


@contextmanager
def run_kernel():
    counts=Counter()
    with ExitStack() as stack:
        stack.enter_context(patch.object(paths,"pair_blocks",clipped))
        stack.enter_context(patch.object(paths,"_competing_axes",AxesCache(axes,counts)))
        yield counts
