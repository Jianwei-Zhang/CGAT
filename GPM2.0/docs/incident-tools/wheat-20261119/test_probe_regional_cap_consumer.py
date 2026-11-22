from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_paths import PairLink
from lgz_core.q0_query_windows import QueryWindow, TargetWindow
from lgz_core.q0_sources import Interval
from probe_regional_cap_consumer import compare, projected_links, source


class RegionalCapConsumerTests(unittest.TestCase):
    lookup = {'q': {'dataset': 'one', 'contig': 'q', 'length': 1000},
              't': {'dataset': 'one', 'contig': 't', 'length': 1000},
              'u': {'dataset': 'two', 'contig': 'u', 'length': 1000}}

    def link(self, target, q, t, bases, strand='+'):
        hit = parse_paf_line(f'q\t1000\t{q}\t{q+bases}\t{strand}\t{target}\t1000\t{t}\t{t+bases}'
                             f'\t{bases}\t{bases}\t60\tcg:Z:{bases}M', artifact='test.paf', line_number=1)
        return PairLink(hit, source('q', self.lookup), source(target, self.lookup))

    def test_deleting_nonqualified_competitor_can_admit_an_old_relation(self):
        kept = self.link('t', 0, 0, 420)
        alternate = self.link('t', 0, 500, 150)
        result = compare('q', {'t': [kept, alternate]}, {'t': [kept]}, self.lookup)['intra']
        self.assertEqual(result['old_qualified_paired_bp'], 0)
        self.assertEqual(result['gained_qualified_paired_bp'], 420)
        self.assertEqual(result['gained_previously_observed_but_unqualified_paired_bp'], 420)
        self.assertEqual(result['pairs_with_previously_unqualified_gain'], 1)

    def test_reverse_tail_shrink_on_same_map_is_not_a_change_in_locus(self):
        old = self.link('u', 100, 300, 400, '-')
        new = self.link('u', 100, 350, 350, '-')
        result = compare('q', {'u': [old]}, {'u': [new]}, self.lookup)
        self.assertEqual(result['intra']['changed_source_pairs'], 0)
        self.assertEqual(result['cross']['lost_qualified_paired_bp'], 50)
        self.assertEqual(result['cross']['gained_qualified_paired_bp'], 0)
        self.assertEqual(result['cross']['pairs_with_qualified_loss'], 1)

    def test_replay_projects_real_window_offsets_and_keeps_only_core_touching_rows(self):
        query = QueryWindow('q', 1000, 100, 500, ((250, 300),))
        target = TargetWindow('t', 1000, 300, 800)
        case = {'query': query, 'targets': [target]}
        def row(qstart, tstart):
            return (f'{query.window_id}\t400\t{qstart}\t{qstart+100}\t-'
                    f'\t{target.window_id}\t500\t{tstart}\t{tstart+100}\t100\t100\t60\tcg:Z:100M\n')
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'raw.paf'
            path.write_text(row(0, 0) + row(100, 50))
            links = projected_links(path, case, self.lookup, 'test.paf')
        self.assertEqual(list(links), ['t'])
        (link,) = links['t']
        self.assertEqual(list(link.source_blocks()), [(Interval(200, 300), Interval(350, 450))])
        self.assertEqual((link.hit.strand, link.hit.line_number, link.hit.mapq), ('-', 1, 255))

    def test_duplicate_bytes_do_not_make_a_new_relation(self):
        kept = self.link('t', 0, 0, 420)
        result = compare('q', {'t': [kept, kept]}, {'t': [kept]}, self.lookup)
        self.assertEqual(result['intra']['changed_source_pairs'], 0)


if __name__ == '__main__':
    unittest.main()
