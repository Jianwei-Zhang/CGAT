import random
import unittest
from unittest import mock
from server.tools.lgz_core.q0_neighbor_requests import known_neighbors, missing_neighbor_queries, _ActiveRanks


def original(bounds, sources, pairs, initial):
    queries=set(initial);active=[];rightmost=None
    for key,(low,high) in sorted(bounds.items(),key=lambda row:(*row[1],row[0])):
        active=[(other,end) for other,end in active if end>low]
        neighbors={other for other,end in active}
        if rightmost is not None:neighbors.add(rightmost[0])
        for other in neighbors:
            if tuple(sorted((sources[key],sources[other]))) not in pairs:queries.add(min(key,other))
        active.append((key,high))
        if rightmost is None or high>rightmost[1]:rightmost=(key,high)
    return queries


class NeighborQueriesTests(unittest.TestCase):
    def test_exact_legacy_selection_for_overlaps_ties_gaps_split_sources_and_known_pairs(self):
        rng=random.Random(8282)
        for trial in range(300):
            size=rng.randrange(0,80);ids=[f'p{i:03d}' for i in range(size)]
            bounds={key:(low:=rng.randrange(0,40),low+rng.randrange(1,50)) for key in ids}
            sources={key:rng.randrange(0,max(1,size//2)) for key in ids}
            pairs={tuple(sorted((sources[a],sources[b]))) for a in ids for b in ids if rng.random()<.02}
            initial={key for key in ids if rng.random()<.5}|{'out-of-bounds-candidate'}
            self.assertEqual(missing_neighbor_queries(bounds,sources,known_neighbors(pairs),initial),original(bounds,sources,pairs,initial))

    def test_dense_missing_pairs_do_not_require_quadratic_enumeration(self):
        size=10000;bounds={f'p{i:05d}':(0,1000) for i in range(size)};sources={key:key for key in bounds}
        original_before=_ActiveRanks.before;visited=0
        def counted(tree,end):
            nonlocal visited
            for index in original_before(tree,end):
                visited+=1;yield index
        with mock.patch.object(_ActiveRanks,'before',counted):
            result=missing_neighbor_queries(bounds,sources,{},())
        self.assertEqual(result,set(bounds)-{max(bounds)})
        self.assertLessEqual(visited,size)

    def test_all_preselected_sources_do_not_enumerate_overlaps(self):
        bounds={str(i):(0,1000) for i in range(1000)}
        with mock.patch.object(_ActiveRanks,'before',side_effect=AssertionError('no unresolved query')):
            self.assertEqual(missing_neighbor_queries(bounds,{key:key for key in bounds},{},bounds),set(bounds))


if __name__=='__main__':unittest.main()
