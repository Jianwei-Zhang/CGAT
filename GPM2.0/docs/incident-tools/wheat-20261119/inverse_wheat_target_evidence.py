"""Exact inverse of target padding/projection, for diagnostic counting, not parent fallback or a Q0 receipt."""
from bisect import bisect_left
from collections import defaultdict
from lgz_core.q0_catalog import _IntervalUnion
from lgz_core.q0_reference_index import _project
from lgz_core.q0_sources import Interval, merged_intervals


class TargetSpans:
    """For every prefix by start, keep the two farthest ends from *different* target parts."""
    def __init__(self, spans):
        self.starts=[]; self.best=[]; self.owners=[]; self.other=[]
        top=runner=0; owner=None
        for start,end,part in sorted(spans):
            if part==owner: top=max(top,end)
            elif end>top: runner,top,owner=top,end,part
            else: runner=max(runner,end)
            self.starts.append(start);self.best.append(top);self.owners.append(owner);self.other.append(runner)

    def intersects(self, region, exclude):
        i=bisect_left(self.starts,region.end)-1
        return i>=0 and (self.other[i] if self.owners[i]==exclude else self.best[i])>region.start


def invert(index, frontier, *, context=10000):
    """Pad each original source shoulder inside each part, then project true paired blocks to reference.

    A padded forward target overlaps the shoulder iff its unpadded bases overlap the padded shoulder.
    Clipping to the part must precede dilation or a shoulder in another part could falsely qualify.
    No query flanks/hulls are approximated: those still come from ordinary index.regions().
    """
    if type(context) is not int or context<0:raise ValueError('invalid target context')
    index.verify_inputs(); by_ref=defaultdict(list)
    for source,needed in frontier.items():
        for part in index.source_parts[source]:
            whole=part.interval; expanded=merged_intervals(Interval(max(whole.start,i.start-context),min(whole.end,i.end+context)) for s in needed if (i:=whole.intersection(s)) is not None)
            by_chr=defaultdict(_IntervalUnion)
            for shoulder in expanded:
                for hit in index._source_hits(source,shoulder):
                    for block in hit.aligned_blocks():
                        if block.operation=='X':continue
                        span=_project(block.query,block.target,hit.strand,shoulder,from_query=True)
                        if span is not None:by_chr[hit.target_name].append(span)
            for chr_,union in by_chr.items():by_ref[chr_].extend((i.start,i.end,part.segment_id) for i in union)
    index.verify_inputs();return {c:TargetSpans(v) for c,v in by_ref.items()}


def target_hit(mask,regions,query_part):
    return any(c in mask and any(mask[c].intersects(i,query_part) for i in intervals) for c,intervals in regions.items())
