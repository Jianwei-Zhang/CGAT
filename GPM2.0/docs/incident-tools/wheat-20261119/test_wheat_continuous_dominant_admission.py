"""Focused synthetic continuity invariants; not biological acceptance."""
import unittest
from dataclasses import replace
from wheat_continuous_dominant_admission_readonly import (
    continuous_candidates, foreign_barriers, POLICY, adm, Interval, SourceKey, SourceSegment)


def anchor(lo, hi, ref=None, name='main'):
    return adm.ReferenceAnchor(Interval(lo, hi), Interval(lo if ref is None else ref,
                               (lo if ref is None else ref)+hi-lo), name)


def evaluate(main, foreign=(), length=1_000_000, target='1A', foreign_high=None):
    groups = {(target, '+'): tuple(main)}
    high = {(target, '+'): tuple(a.source for a in main)}
    if foreign:
        groups['1B', '+'] = tuple(foreign)
        high['1B', '+'] = tuple(a.source for a in foreign) if foreign_high is None else foreign_high
    part = SourceSegment('part', SourceKey('dataset', 'contig'), Interval(0, length), 'a'*64, 0, 'start', 'end')
    return continuous_candidates(part, groups, high, target=target)


class ContinuityTests(unittest.TestCase):
    def test_small_internal_island_does_not_cut_or_discard_unanchored_sequence(self):
        result, detail = evaluate([anchor(0, 400_000), anchor(401_000, 900_000)],
                                  [anchor(400_000, 401_000, name='foreign')])
        self.assertEqual([p.interval for p in result['90']], [Interval(0, 1_000_000)])
        self.assertEqual(detail['split_intervals'], [])
        self.assertEqual(detail['regions'][0]['foreign_qualified_source_bp'], 1000)
        self.assertEqual(detail['regions'][0]['unsupported_carried_bp'], 101_000)

    def test_large_internal_independent_chain_cuts(self):
        result, detail = evaluate([anchor(0, 400_000), anchor(550_000, 1_000_000)],
                                  [anchor(400_000, 550_000, name='foreign')])
        self.assertEqual([p.interval for p in result['80']],
                         [Interval(0, 400_000), Interval(550_000, 1_000_000)])
        self.assertFalse(result['90'])

    def test_terminal_foreign_chain_does_not_strip_other_unsupported_end(self):
        result, detail = evaluate([anchor(20_000, 900_000)],
                                  [anchor(0, 20_000, name='foreign')])
        self.assertEqual(result['90'][0].interval, Interval(20_000, 1_000_000))
        self.assertTrue(detail['foreign_chains'][0]['terminal'])

    def test_low_mapq_foreign_chain_cannot_authorize_cut(self):
        result, detail = evaluate([anchor(0, 400_000), anchor(550_000, 1_000_000)],
                                  [anchor(400_000, 550_000, name='foreign')], foreign_high=())
        self.assertEqual(detail['split_intervals'], [])
        self.assertEqual(result['80'][0].interval, Interval(0, 1_000_000))

    def test_tiny_main_chain_not_promoted(self):
        result, _ = evaluate([anchor(0, 50_000)], length=50_000)
        self.assertFalse(any(result.values()))

    def test_minimum_carried_support_is_not_hull_interpolation(self):
        result, _ = evaluate([anchor(0, 150_000)])
        self.assertFalse(any(result.values()))

    def test_foreign_dominant_source_is_not_forced_to_target(self):
        result, _ = evaluate([anchor(0, 200_000)], [anchor(200_000, 1_000_000)])
        self.assertFalse(any(result.values()))

    def test_overlapping_duplicate_foreign_anchors_do_not_hide_major_chain(self):
        main = [anchor(0, 400_000), anchor(550_000, 1_000_000)]
        foreign = [anchor(400_000, 550_000, name='f1'), anchor(400_000, 550_000, name='f2')]
        _, detail = evaluate(main, foreign)
        self.assertEqual(detail['split_intervals'], [[400_000, 550_000]])

    def test_other_group_argument_is_not_bound_to_1A(self):
        result, _ = evaluate([anchor(0, 900_000)], target='3D')
        self.assertEqual(result['90'][0].chromosome, '3D')

    def test_reverse_main_chain_preserves_source_continuity(self):
        main = (anchor(0, 400_000, 600_000), anchor(401_000, 900_000, 100_000))
        groups = {('1A', '-'): main, ('1B','+'): (anchor(400_000,401_000),)}
        part = SourceSegment('p',SourceKey('d','c'),Interval(0,1_000_000),'a'*64,0,'start','end')
        result, _ = continuous_candidates(part, groups, {('1A','-'): tuple(a.source for a in main)})
        self.assertEqual(result['90'][0].orientation, '-')
        self.assertEqual(result['90'][0].interval, Interval(0,1_000_000))


if __name__ == '__main__':
    unittest.main()
