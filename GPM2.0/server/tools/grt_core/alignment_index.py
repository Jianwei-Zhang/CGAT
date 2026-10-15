"""Exact coordinate lookups preserving the original alignment-stream order.

These indexes only accelerate selection; no alignment, rejection, or tie is
removed. In particular callers still own the expanding-window stop condition.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right


class AlignmentCoordinateIndex:
    BLOCK_SIZE = 128

    def __init__(self, rows: list[dict[str, object]]):
        self.rows = rows
        self.starts = sorted((int(r["query_min"]), i) for i, r in enumerate(rows))
        self.ends = sorted((int(r["query_max"]), i) for i, r in enumerate(rows))
        self.start_values = [p for p, _ in self.starts]
        self.end_values = [p for p, _ in self.ends]
        self.block_max_ends = [
            max(int(rows[i]["query_max"]) for _, i in self.starts[offset:offset + self.BLOCK_SIZE])
            for offset in range(0, len(self.starts), self.BLOCK_SIZE)
        ]

    def crossing(self, position: int) -> list[dict[str, object]]:
        stop = bisect_right(self.start_values, position)
        indices = []
        for offset in range(0, stop, self.BLOCK_SIZE):
            if self.block_max_ends[offset // self.BLOCK_SIZE] < position:
                continue
            indices.extend(i for _, i in self.starts[offset:min(stop, offset + self.BLOCK_SIZE)]
                           if int(self.rows[i]["query_max"]) >= position)
        return [self.rows[i] for i in sorted(indices)]

    def anchors(self, position: int, window: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        left = self.ends[bisect_left(self.end_values, position - window):bisect_left(self.end_values, position)]
        right = self.starts[bisect_right(self.start_values, position):bisect_right(self.start_values, position + window)]
        return ([self.rows[i] for i in sorted(i for _, i in left)],
                [self.rows[i] for i in sorted(i for _, i in right)])


class Step2MemberIndex:
    """Return exactly the original stable top-two left/right anchors."""

    def __init__(self, rows: list[dict[str, object]]):
        self.left = sorted(enumerate(rows), key=lambda item: (
            int(item[1]["query_max"]), float(item[1]["identity"]), -item[0]))
        self.right = sorted(enumerate(rows), key=lambda item: (
            int(item[1]["query_min"]), -float(item[1]["identity"]), item[0]))
        self.left_values = [int(row["query_max"]) for _, row in self.left]
        self.right_values = [int(row["query_min"]) for _, row in self.right]

    def anchors(self, gap_position: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        stop = bisect_right(self.left_values, gap_position + 10)
        start = bisect_left(self.right_values, gap_position - 10)
        return ([row for _, row in reversed(self.left[max(0, stop - 2):stop])],
                [row for _, row in self.right[start:start + 2]])
