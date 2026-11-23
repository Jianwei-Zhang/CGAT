"""Read-only comparison of signed CIGAR coordinate maps; not an omission certificate."""
from bisect import bisect_right
from collections import defaultdict
from lgz_core.q0_sources import Interval, merged_intervals


def map_key(a, b, strand):
    if a.length != b.length or strand not in ('+', '-'):
        raise ValueError('not a paired equal-length block')
    # The minus invariant uses *boundaries* (end is exclusive), not base indices.
    return strand, b.start-a.start if strand=='+' else b.end+a.start


class Ranges:
    def __init__(self, spans):
        self.spans=merged_intervals(spans); self.ends=tuple(x.end for x in self.spans)

    def gaps(self, region):
        cursor=region.start; i=bisect_right(self.ends,cursor)
        while i<len(self.spans) and self.spans[i].start<region.end:
            s=self.spans[i]
            if cursor<s.start: yield Interval(cursor,s.start)
            cursor=max(cursor,s.end);i+=1
        if cursor<region.end: yield Interval(cursor,region.end)

    def intersect(self, region):
        i=bisect_right(self.ends,region.start)
        while i<len(self.spans) and self.spans[i].start<region.end:
            yield self.spans[i].intersection(region);i+=1


class LocusIndex:
    def __init__(self):
        self._pending=defaultdict(lambda:defaultdict(list)); self.rows=None

    def add(self, q, t, a, b, strand):
        if self.rows is not None:raise ValueError('index has already been sealed')
        self._pending[q,t][map_key(a,b,strand)].append(a)

    def seal(self):
        if self.rows is not None: raise ValueError('already sealed')
        self.rows={p:{k:Ranges(v) for k,v in maps.items()} for p,maps in self._pending.items()};del self._pending

    def novel(self,q,t,a,b,strand,cores,minimum):
        if minimum<1:raise ValueError('invalid minimum length')
        maps=self.rows.get((q,t),{});key=map_key(a,b,strand); old=maps.get(key)
        for span in cores.intersect(a):
            if span.length<minimum: continue
            if old is not None:
                if any(g.length>=minimum for g in old.gaps(span)): return 'extends_existing_map'
            elif not maps: return 'new_source_pair'
            elif any(k[0]==strand for k in maps):return 'new_map_on_existing_strand'
            else:return 'new_strand_on_existing_pair'
        return None
