"""Exact interval-index replacement for repeated whole-contig anchor scans.

No anchor, pair evidence, competition, minimum-support or cut rule is removed.
Indexes are ephemeral and bound to the actual Placement object in this process.
"""
import inspect,textwrap
from time import monotonic
from bisect import bisect_left,bisect_right
from contextlib import contextmanager
from hashlib import sha256
from unittest.mock import patch
from lgz_core import q0_paths as paths
from lgz_core.q0_sources import Interval,merged_intervals

NATIVE_QUALIFY=paths.qualify_pair_blocks
NATIVE_JOINS=paths.PathGraph.joins
QUALIFY_SOURCE=textwrap.dedent(inspect.getsource(NATIVE_QUALIFY))
JOIN_SOURCE=textwrap.dedent(inspect.getsource(NATIVE_JOINS))


class AnchorSupportIndex:
    def __init__(self,progress=None):
        self.progress=progress;self.last=monotonic()
        self.cache={};self.calls=0;self.visited_left=0;self.visited_right=0
    def index(self,p):
        old=self.cache.get(p.placement_id)
        if old is None or old[0] is not p:
            rows=merged_intervals(p.local(v) for v in p.anchor_intervals)
            old=(p,rows,tuple(v.start for v in rows),tuple(v.end for v in rows))
            self.cache[p.placement_id]=old
        return old[1:]
    @staticmethod
    def nearby(index,iv):
        rows,starts,ends=index
        return rows[bisect_right(ends,iv.start):bisect_left(starts,iv.end)]
    def supported(self,block,left,right):
        self.calls+=1;support=[];li=self.index(left);ri=self.index(right)
        if self.progress is not None and monotonic()-self.last>=30:
            self.progress(self.report());self.last=monotonic()
        for a in self.nearby(li,block.left):
            self.visited_left+=1;clipped=block.clip_left(a)
            if clipped is None:continue
            for b in self.nearby(ri,clipped.right):
                self.visited_right+=1;overlap=clipped.right.intersection(b)
                if overlap is not None:
                    start=clipped.left.start+overlap.start-clipped.right.start
                    support.append(Interval(start,start+overlap.length))
        return support
    def report(self):
        return {'placements_indexed':len(self.cache),'block_calls':self.calls,
                'overlapping_left_anchors_visited':self.visited_left,
                'overlapping_right_anchors_visited':self.visited_right}


def qualification(index):
    source=QUALIFY_SOURCE
    start=source.index('            for a in left.anchor_intervals:')
    stop=source.index('        if _size(supported)',start)
    needle=source[start:stop]
    if needle.count('for b in right.anchor_intervals:')!=1:
        raise ValueError('different frozen support loop')
    source=source[:start]+'            supported.extend(diagnostic_supported(block, left, right))\n'+source[stop:]
    ns=dict(vars(paths));ns['diagnostic_supported']=index.supported
    exec(compile(source,'<exact-indexed-anchor-qualification>','exec'),ns)
    return ns['qualify_pair_blocks'],sha256(source.encode()).hexdigest()


def joins(index,internal=False):
    source=JOIN_SOURCE
    source=source.replace('        anchors_left = tuple(left.local(i) for i in left.anchor_intervals)\n','')
    source=source.replace('        anchors_right = tuple(right.local(i) for i in right.anchor_intervals)\n','')
    start=source.index('            supported = []')
    stop=source.index('            # The cut needs one continuous anchor',start)
    if source[start:stop].count('for a in anchors_left:')!=1:
        raise ValueError('different frozen join anchor loop')
    source=source[:start]+'            supported = diagnostic_supported(block, left, right)\n'+source[stop:]
    if internal:
        needle='if blocks and (reaches_both := _end_spanning_evidence(blocks, left.interval.length)):'
        if source.count(needle)!=1:raise ValueError('different frozen endpoint rule')
        source=source.replace(needle,'if blocks:\n        reaches_both = {evidence_id for _, evidence_id in blocks}')
    ns=dict(vars(paths));ns['diagnostic_supported']=index.supported
    exec(compile(source,'<indexed-anchor-join>','exec'),ns)
    return ns['joins'],sha256(source.encode()).hexdigest()


@contextmanager
def indexed_native(index):
    qualify,qpin=qualification(index);join,jpin=joins(index)
    with patch.object(paths,'qualify_pair_blocks',qualify),patch.object(paths.PathGraph,'joins',join):
        yield {'qualification_sha256':qpin,'strict_joins_sha256':jpin}
