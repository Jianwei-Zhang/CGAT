"""Exact support unions and native pair/join semantics under interval indexing."""
import random,unittest
from types import SimpleNamespace
from lgz_core import q0_paths as paths
from lgz_core.q0_sources import Interval,merged_intervals
from wheat_indexed_anchor_support_readonly import AnchorSupportIndex,qualification,joins,NATIVE_QUALIFY,NATIVE_JOINS
from test_wheat_continuity_refinement import fixture


def brute(block,left,right):
    out=[]
    for a in left.anchor_intervals:
        clipped=block.clip_left(left.local(a))
        if clipped:
            for b in right.anchor_intervals:
                overlap=clipped.right.intersection(right.local(b))
                if overlap:
                    start=clipped.left.start+overlap.start-clipped.right.start
                    out.append(Interval(start,start+overlap.length))
    return merged_intervals(out)


class IndexedTests(unittest.TestCase):
    def test_random_support_unions_both_orientations(self):
        rng=random.Random(614589)
        for case in range(400):
            def placement(name,reverse):
                intervals=[]
                for _ in range(rng.randrange(1,40)):
                    lo=rng.randrange(0,990);hi=rng.randrange(lo+1,1001)
                    intervals.append(Interval(lo,hi))
                return SimpleNamespace(placement_id=name,anchor_intervals=tuple(intervals),
                    local=(lambda iv:Interval(1000-iv.end,1000-iv.start)) if reverse else (lambda iv:iv))
            left=placement('left',bool(case%2));right=placement('right',bool(case%3))
            length=rng.randrange(1,400);lo=rng.randrange(0,1000-length);ro=rng.randrange(0,1000-length)
            block=paths.Block(Interval(lo,lo+length),Interval(ro,ro+length))
            index=AnchorSupportIndex()
            self.assertEqual(merged_intervals(index.supported(block,left,right)),brute(block,left,right))

    def test_native_qualification_and_strict_join_objects_identical(self):
        graph,ps,_=fixture();links=[l for rows in graph.links.values() for l in rows]
        index=AnchorSupportIndex();fast,_=qualification(index);join,_=joins(index)
        for left,right in (ps,tuple(reversed(ps))):
            for supported in (True,False):
                self.assertEqual(NATIVE_QUALIFY(left,right,links,graph.policy,require_supported=supported),
                                 fast(left,right,links,graph.policy,require_supported=supported))
            graph._joins.clear();expected=NATIVE_JOINS(graph,left.placement_id,right.placement_id)
            graph._joins.clear();actual=join(graph,left.placement_id,right.placement_id)
            self.assertEqual(expected,actual)

    def test_actual_overlap_only_and_same_id_different_object_reindexed(self):
        rows=tuple(Interval(i*30,i*30+20) for i in range(10_000))
        left=SimpleNamespace(placement_id='a',anchor_intervals=rows,local=lambda x:x)
        right=SimpleNamespace(placement_id='b',anchor_intervals=rows,local=lambda x:x)
        block=paths.Block(rows[-1],rows[-1]);index=AnchorSupportIndex()
        self.assertEqual(merged_intervals(index.supported(block,left,right)),(rows[-1],))
        self.assertEqual((index.visited_left,index.visited_right),(1,1))
        replacement=SimpleNamespace(placement_id='a',anchor_intervals=(),local=lambda x:x)
        self.assertEqual(index.supported(block,replacement,right),[])


if __name__=='__main__':unittest.main()
