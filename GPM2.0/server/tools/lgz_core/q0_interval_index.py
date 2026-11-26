"""Exact half-open interval indexes. Overlapping inputs are never discarded."""
from bisect import bisect_left, bisect_right


class IntervalIndex:
    def __init__(self, rows, interval):
        self.rows = tuple(sorted(enumerate(rows), key=lambda v: (interval(v[1]).start, interval(v[1]).end, v[0])))
        self.interval = interval
        starts, farthest_ends = [], []
        farthest = -1
        for _, row in self.rows:
            iv = interval(row)
            starts.append(iv.start)
            farthest = max(farthest, iv.end)
            farthest_ends.append(farthest)
        self.starts, self.ends = tuple(starts), tuple(farthest_ends)

    def overlapping(self, span):
        lo, hi = bisect_right(self.ends, span.start), bisect_left(self.starts, span.end)
        for index, row in self.rows[lo:hi]:
            if self.interval(row).intersection(span) is not None:
                yield index, row
