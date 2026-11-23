from types import SimpleNamespace as Row
import unittest
from unittest.mock import patch

from lgz_core.q0_sources import Interval, Q0EvidenceError
import replay_q0_reverse_parents as replay


def base_input():
    parts = {s: Row(source=s, interval=Interval(0, 100)) for s in ('t', 'bridge', 'edge', 'peer', 'spare', 'unknown')}
    parts['peer2'] = Row(source='peer', interval=Interval(100, 200))

    def hit(start, end, lo, hi, chrom='A'):
        return Row(query=Interval(start, end), target=Interval(lo, hi), target_name=chrom)

    hits = {'t': [hit(20, 30, 50, 60)], 'bridge': [hit(0, 10, 1, 11), hit(90, 100, 91, 101)],
            'edge': [hit(0, 10, 60, 70)], 'spare': [hit(0, 10, 50, 60, 'B')],
            'peer': [hit(10, 20, 130, 140), hit(110, 120, 130, 140)]}
    return Row(parts=parts, sources={s: range(200) for s in hits}, reference_hits=hits,
               reference_lengths={'A': 200, 'B': 200}, pair_links=())


class ShortlistTests(unittest.TestCase):
    def test_routing_hull_can_bridge_demand_but_abutting_or_other_chromosome_cannot(self):
        base = base_input()
        parents, counts = replay.shortlist(base, {'t': [Interval(20, 25)]}, target_context=0, reference_context=0)
        self.assertEqual(parents, {'t', 'bridge', 'unknown'})
        self.assertEqual(counts['unanchored_parents_retained'], 1)

    def test_cross_pair_offsets_select_only_overlapping_peer_part_in_either_direction(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                base = base_input()
                sides = [('t', 20), ('peer', 103)]
                (q, qo), (t, to) = sides[::-1] if reverse else sides
                base.pair_links = (Row(hit=Row(query=Interval(1, 9), target=Interval(1, 9)),
                                       query_source=q, target_source=t, query_offset=qo, target_offset=to),)
                parents, counts = replay.shortlist(base, {'t': [Interval(20, 25)]}, target_context=0, reference_context=0)
                self.assertEqual(parents, {'t', 'bridge', 'unknown', 'peer2'})
                self.assertEqual(counts['base_pair_neighbors'], 1)

    def test_missing_demand_or_missing_anchor_abstains_for_every_parent(self):
        base = base_input()
        for demand, reason in ((None, 'no_demand'), ({'t': (Interval(30, 40),)}, 'unanchored_question')):
            parents, counts = replay.shortlist(base, demand, target_context=0)
            self.assertEqual(parents, set(base.parts))
            self.assertEqual(counts['abstain'], reason)
        parents, _ = replay.shortlist(base, {'t': (Interval(30, 40),)}, target_context=1, reference_context=0)
        self.assertNotIn('spare', parents)

    def test_only_known_omission_can_trigger_another_round(self):
        selection = Row(admission=None, paths={})
        for kind in ('placement', 'pair evidence'):
            exc = Q0EvidenceError(f'q0 scoped {kind} has unsearched competing context; rerun with full supplemental evidence')
            with patch.object(replay, 'audit_selected_scope', side_effect=exc):
                self.assertTrue(replay.has_unsearched_context(None, selection))
        with patch.object(replay, 'audit_selected_scope', side_effect=Q0EvidenceError('unbound evidence')):
            with self.assertRaisesRegex(Q0EvidenceError, 'unbound evidence'):
                replay.has_unsearched_context(None, selection)

    def test_alternative_geometry_ignores_row_ids_but_not_orientation(self):
        def alternatives(row_id, strand):
            sl = Row(source='a', interval=Interval(10, 30), orientation=strand, placement_id=row_id)
            path = Row(slices=(sl,), joins=())
            return replay.alternatives(Row(paths={'chr': Row(alternatives=(path,))}))
        self.assertEqual(alternatives('1', '+'), alternatives('2', '+'))
        self.assertNotEqual(alternatives('1', '+'), alternatives('2', '-'))


if __name__ == '__main__':
    unittest.main()
