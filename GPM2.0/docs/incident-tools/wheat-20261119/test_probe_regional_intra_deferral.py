from collections import defaultdict
from random import Random
import unittest
from unittest.mock import patch

from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_paths import PairLink, PathPolicy
from lgz_core.q0_sources import Interval
from lgz_core.q0_query_windows import QueryWindow
from probe_regional_cap_consumer import qualify, source
from replay_regional_reciprocal_coverage import covered_bases
from probe_regional_intra_deferral import choose, score


class DeferralScreenTests(unittest.TestCase):
    lookup = {name: {'dataset': dataset, 'contig': name, 'length': 8000}
              for name, dataset in [('q', 'A'), ('i', 'A'), ('c', 'B'), ('d', 'B')]}
    q = QueryWindow('q', 8000, 1000, 6000, ((2200, 2450),))

    def hit(self, name, qs=2100, qe=2550, ts=200, strand='+'):
        n = qe-qs
        return parse_paf_line(f'q\t8000\t{qs}\t{qe}\t{strand}\t{name}\t8000\t{ts}\t{ts+n}\t{n}\t{n}\t255\tcg:Z:{n}M',
                              artifact='test.paf', line_number=1)

    def test_single_full_cross_map_does_not_prove_intra_is_redundant(self):
        row = score(self.q, [self.hit('c'), self.hit('i', 2100, 2400)], self.lookup)
        self.assertTrue(row['single_full_cross_map_screen'])
        self.assertEqual(row['intra_qualified_core_maps'], 1)
        self.assertEqual(row['intra_qualified_core_paired_bp'], 200)
        self.assertEqual(row['intra_qualified_whole_paired_bp'], 300)

    def test_multiple_loci_or_union_only_do_not_authorize_deferral(self):
        self.assertFalse(score(self.q, [self.hit('c'), self.hit('d', 2150, 2380)], self.lookup)
                         ['single_full_cross_map_screen'])
        self.assertFalse(score(self.q, [self.hit('c', 2160, 2350), self.hit('d', 2300, 2500)], self.lookup)
                         ['single_full_cross_map_screen'])

    def test_same_pair_alternate_is_observed_even_when_both_are_unqualified(self):
        row = score(self.q, [self.hit('c'), self.hit('i'), self.hit('i', ts=3000, strand='-')], self.lookup)
        self.assertEqual(row['intra_qualified_core_maps'], 0)
        self.assertEqual(row['intra_observed_core_maps'], 2)

    def test_impossible_cross_skips_expensive_gate_without_fabricating_zeros(self):
        with patch('probe_regional_intra_deferral.qualified_maps', side_effect=AssertionError('unneeded gate')):
            row = score(self.q, [self.hit('c'), self.hit('d'), self.hit('i')], self.lookup)
        self.assertEqual(row['screen_outcome'], 'not_one_complete_observed_cross_map')
        self.assertEqual(row['distinct_cross_observed_core_maps'], 2)
        self.assertEqual(row['intra_projected_rows'], 1)
        self.assertIsNone(row['intra_qualified_core_maps'])

    def test_competition_outside_the_core_still_blocks_the_only_full_map(self):
        row = score(self.q, [self.hit('c', 1900, 2550), self.hit('c', 1900, 2090, ts=3000)], self.lookup)
        self.assertEqual(row['distinct_cross_observed_core_maps'], 1)
        self.assertEqual(row['screen_outcome'], 'cross_map_failed_qualification')
        self.assertEqual(row['full_cross_qualified_core_maps'], 0)

    def test_early_rejection_matches_full_pair_gate(self):
        rng = Random(361127)
        cores = tuple(Interval(*row) for row in self.q.cores)
        policy = PathPolicy()
        for _ in range(150):
            hits = [self.hit(rng.choice(('c', 'd')), start, start + rng.randrange(60, 800),
                             rng.randrange(0, 5000), rng.choice(('+', '-')))
                    for start in (rng.randrange(1650, 2600) for _ in range(rng.randrange(1, 13)))]
            pairs = defaultdict(list)
            for hit in hits:
                pairs[hit.target_name].append(PairLink(hit, source('q', self.lookup), source(hit.target_name, self.lookup)))
            full, maps = 0, 0
            for target, links in pairs.items():
                observed, accepted = qualify('q', target, links, self.lookup, policy)
                maps += sum(covered_bases(cores, spans) > 0 for spans in observed.values())
                full += sum(covered_bases(cores, spans) == 250 for spans in accepted.values())
            result = score(self.q, hits, self.lookup)
            self.assertEqual(result['distinct_cross_observed_core_maps'], maps)
            self.assertEqual(result['single_full_cross_map_screen'], full == 1 and maps == 1)

    def test_selection_is_deterministic_and_rejects_ambiguous_projects(self):
        qs = [self.q, QueryWindow('c', 8000, 1000, 6000, ((3200, 3450),))]
        raw = [{ 'raw_receipt': name, 'raw_receipt_sha256': name, 'cpu_seconds': i}
                for i,name in enumerate(('a','b'))]
        projects = [{'raw': row['raw_receipt'], 'query': q.record()} for row,q in zip(raw,qs)]
        trace = {'raw_markers': raw, 'new_projects': projects}
        self.assertEqual([(kind,r['raw_receipt']) for kind,r in choose(trace, limit=1)],
                         [('high_cpu','b'), ('short_interior','a')])
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            list(choose({**trace, 'new_projects': projects + projects[:1]}))


if __name__ == '__main__':
    unittest.main()
