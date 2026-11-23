from dataclasses import replace
from types import SimpleNamespace as Row
import unittest
from unittest.mock import patch

import replay_q0_draft_requests as exp
from lgz_core.q0_sources import Interval
from server.tests.test_q0_admission import EvidenceFixture, bridge_fixture, dna


def window(part, lo, hi):
    return Row(segment_id=part.segment_id, segment_length=part.interval.length, start=lo, end=hi)


class DraftFirstTests(unittest.TestCase):
    def test_blind_draft_recovers_required_reverse_bridge(self):
        fixture, truth = bridge_fixture(reverse=True)
        data = fixture.data()
        parts = {p.source: p for p in data.parts.values()}
        windows = {l.hit.artifact: (window(parts[l.query_source], l.hit.query.start, l.hit.query.end),
                                    (window(parts[l.target_source], l.hit.target.start, l.hit.target.end),))
                   for l in data.pair_links}
        data = replace(data, catalog={'base_alignments': [],
                                      'supplementary_alignments': [{'paf': k} for k in windows]})
        base = exp.subset_input(data, set())
        self.assertFalse(base.pair_links)
        self.assertNotEqual(exp.admission.construct_q0(base).records['chr1'], truth)
        requests = []
        def reveal(keys):
            requests.append(set(keys))
            return exp.subset_input(data, keys)
        arm, kept, history, _ = exp.decide(base, windows, set(), reveal)
        self.assertEqual(history[0]['visible_regional_before'], 0)
        self.assertEqual(requests[-1], kept)
        self.assertEqual(exp.admission.construct_q0(arm).records['chr1'], truth)

    def test_cut_and_competing_tie_endpoints_not_entire_source_or_worse_candidate(self):
        def path(name, score):
            return Row(slices=[Row(source=name, interval=Interval(10, 90), orientation='-')], score=score)
        row = Row(path=path('a', (3,)), alternatives=[path('b', (3,)), path('c', (2,))])
        sel = Row(paths={'chr': row}, admission=None)
        with patch.object(exp, 'decision_frontier', return_value={}), patch.object(exp, 'selected_proof_frontier', return_value={}):
            result = exp.cut_questions(None, sel)
        self.assertEqual(result, {k: (Interval(10, 11), Interval(89, 90)) for k in ('a','b')})

    def test_interior_unplaced_competitor_can_be_invisible_to_winner_guard(self):
        # A real copied substring, not random unrelated sequence behind an invented alignment.
        f = EvidenceFixture({'chr': 2000})
        seq = dna(2000); root = f.source('root', seq); alt = f.source('alternative', seq[850:1350])
        f.ref(root, (0, 2000), (0, 2000), chromosome='chr')
        hit = f.pair(alt, root, (0, 500), (850, 1350))
        data = replace(f.data(), catalog={'base_alignments': [], 'supplementary_alignments': [{'paf': hit.artifact}]})
        parts = {p.source: p for p in data.parts.values()}
        windows = {hit.artifact: (window(parts[alt], 0, 500), (window(parts[root], 850, 1350),))}
        reveal = lambda keys: exp.subset_input(data, keys)
        full = exp.admission.construct_q0(data)
        thin, kept, _, _ = exp.decide(reveal(set()), windows, set(), reveal, localization=False)
        old = exp.admission.construct_q0(thin)  # guard passes even though an alternative is missing
        self.assertFalse(kept); self.assertEqual(old.records, full.records)
        self.assertNotEqual(exp.alternatives(old), exp.alternatives(full))
        wide, kept, _, _ = exp.decide(reveal(set()), windows, set(), reveal)
        self.assertEqual(kept, set(windows))
        self.assertEqual(exp.alternatives(exp.admission.construct_q0(wide)), exp.alternatives(full))

    def test_partial_placement_offsets_and_batched_targets(self):
        def part(key, lo):
            return Row(segment_id=key, source=key, interval=Interval(lo, lo+100))
        parts = {k: part(k, n) for k, n in [('a', 100), ('b', 200), ('c', 0)]}
        placements = [Row(segment_id=k, source=k, interval=Interval(lo,hi)) for k,lo,hi in
                      [('a', 100, 200), ('b', 200, 240)]]
        windows = {'interior': (window(parts['a'], 30, 40), (window(parts['b'], 40, 50),)),
                   'anchored': (window(parts['a'], 30, 40), (window(parts['b'], 0, 40),)),
                   'both_unknown': (window(parts['c'], 10, 20), (window(parts['b'], 60, 80),))}
        self.assertEqual(exp.challenge_unlocalized(windows, parts, placements), {'interior'})
        # q->a is an unlocalized-to-localized pair even with a second, unplaced target.
        windows = {'batch': (window(parts['c'], 20, 25), (window(parts['a'], 0, 5), window(parts['b'], 45, 50)))}
        self.assertEqual(exp.challenge_unlocalized(windows, parts, placements), {'batch'})

    def test_no_path_full_fallback_includes_native_only_after_draft(self):
        base = Row(parts={}, catalog={}, ready_manifest_identity='')
        order = []
        def select(v):
            order.append('draft'); return object()
        def reveal(ids):
            order.append(set(ids)); return base
        with patch.object(exp.admission, 'select_q0_paths', side_effect=select), patch.object(exp, 'cut_questions', return_value=None), patch.object(exp, 'with_omissions', return_value=base):
            _, kept, _, why = exp.decide(base, {'r': None}, {'native'}, reveal)
        self.assertEqual((kept, why), ({'r'}, 'no_draft_path'))
        self.assertEqual(order, ['draft', {'r','native'}])

    def test_refused_or_exhausted_search_reveals_all_not_a_partial_success(self):
        base = Row(parts={}, catalog={}, ready_manifest_identity='')
        windows = dict.fromkeys('abc')
        for asks, reason in (([set()], 'unresolved_competition'),
                             ([{'a'}, {'b'}], 'request_budget_exhausted')):
            requests = []
            def reveal(ids):
                requests.append(set(ids)); return base
            with (patch.object(exp.admission, 'select_q0_paths'),
                  patch.object(exp, 'cut_questions', return_value={}),
                  patch.object(exp, 'pick', side_effect=asks),
                  patch.object(exp, 'with_omissions', return_value=base),
                  patch.object(exp, 'has_unsearched_context', return_value=True)):
                _, kept, _, fallback = exp.decide(base, windows, set(), reveal, maximum_requests=1,
                                                  localization=False)
            self.assertEqual((requests[-1], kept, fallback), (set('abc'), set('abc'), reason))

    def test_reselect_native_even_when_first_draft_needs_no_regions(self):
        # A new native observation introduces a target-side question on the next round.
        base = Row(parts={}, catalog={}, ready_manifest_identity='')
        requests = []
        def reveal(ids):
            requests.append(set(ids)); return base
        with patch.object(exp.admission, 'select_q0_paths'), patch.object(exp, 'cut_questions', return_value={}), patch.object(exp, 'pick', side_effect=[set(), {'r'}]), patch.object(exp, 'with_omissions', return_value=base):
            _, _, history, _ = exp.decide(base, {'r': None}, {'native'}, reveal, localization=False)
        self.assertEqual(requests, [{'native'}, {'r', 'native'}])
        self.assertEqual([row['visible_native_before'] for row in history], [0, 1])


if __name__ == '__main__':
    unittest.main()
