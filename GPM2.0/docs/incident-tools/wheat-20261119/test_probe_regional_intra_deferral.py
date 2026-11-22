import unittest

from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_query_windows import QueryWindow
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
