from __future__ import annotations

from dataclasses import replace
import itertools
import json
import random
import unittest

from server.tools.lgz_core.common import reverse_complement
from server.tools.lgz_core.q0_alignments import parse_paf_line
from server.tools.lgz_core.q0_paths import (
    PairLink, PathGraph, PathPolicy, Placement, ReferenceAnchor, pair_blocks, reconstruct, search_paths,
)
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError, SourceKey, split_source


def placement(name, start, end, *, dataset=None, offset=0, orientation="+", chromosome="chr1"):
    interval = Interval(offset, offset + end - start)
    return Placement(name, name, SourceKey(dataset or name, name), interval, orientation, chromosome,
                     (Interval(start, end),), (interval,), ("ref-" + name,),
                     (ReferenceAnchor(interval, Interval(start, end), "ref-" + name),))


def link(left, right, left_range, right_range, *, number=1, cigar=None, matches=None,
         query_offset=0, target_offset=0):
    a = left.source_interval(Interval(*left_range))
    b = right.source_interval(Interval(*right_range))
    qlen, tlen = left.interval.end - query_offset, right.interval.end - target_offset
    length = max(a.length, b.length)
    fields = [left.source.contig, qlen, a.start - query_offset, a.end - query_offset,
              "+" if left.orientation == right.orientation else "-", right.source.contig,
              tlen, b.start - target_offset, b.end - target_offset,
              matches if matches is not None else min(a.length, b.length), length, 60,
              "cg:Z:" + (cigar or f"{a.length}M")]
    hit = parse_paf_line("\t".join(map(str, fields)), artifact="pair.paf", line_number=number)
    return PairLink(hit, left.source, right.source, query_offset, target_offset)


def bridge_fixture(reverse=False, original_gap=False):
    rng = random.Random(71)
    truth = "".join(rng.choices("ACGT", k=5000))
    a, b = placement("a", 0, 2200), placement("b", 2600, 5000)
    c = placement("c", 1800, 3000, orientation="-" if reverse else "+")
    original = ()
    sequences = {a.source: truth[:2200], b.source: truth[2600:],
                 c.source: reverse_complement(truth[1800:3000]) if reverse else truth[1800:3000]}
    if original_gap:
        source = SourceKey("assembly", "scaffold")
        sequence = truth[:2200] + "N" * 137 + truth[2600:]
        index = split_source(source, sequence)
        a = replace(a, source=source, segment_id=index.segments[0].segment_id)
        b = replace(b, source=source, segment_id=index.segments[1].segment_id,
                    interval=index.segments[1].interval, anchor_intervals=(index.segments[1].interval,),
                    reference_blocks=(ReferenceAnchor(index.segments[1].interval, Interval(2600, 5000), "ref-b"),))
        sequences = {source: sequence, c.source: sequences[c.source]}
        original = index.adjacencies
    links = (link(a, c, (1800, 2200), (0, 400), number=1),
             link(c, b, (800, 1200), (0, 400), number=2))
    return truth, (a, b, c), links, sequences, original


class Q0PathKernelTests(unittest.TestCase):
    def test_two_sided_bridge_keeps_outer_sequence_and_removes_unknown_join(self):
        truth, nodes, links, sequences, original = bridge_fixture()
        result = search_paths(PathGraph(nodes, links))
        self.assertEqual(result.path.nodes, ("a", "c", "b"))
        self.assertEqual(reconstruct(result.path, sequences), truth)
        self.assertEqual([s.interval for s in result.path.slices],
                         [Interval(0, 2000), Interval(200, 1000), Interval(200, 2400)])
        self.assertEqual([j.kind for j in result.path.joins], ["sequence_overlap"] * 2)
        self.assertTrue(any(row["operation"] == "bridge_replacement" for row in result.decisions))
        self.assertFalse(any(intervals for source, intervals in result.path.missing))
        json.dumps(result.record())

    def test_reverse_bridge_uses_original_forward_source_coordinates(self):
        truth, nodes, links, sequences, _ = bridge_fixture(reverse=True)
        result = search_paths(PathGraph(nodes, links))
        self.assertEqual(reconstruct(result.path, sequences), truth)
        bridge = result.path.slices[1]
        self.assertEqual(bridge.orientation, "-")
        self.assertEqual(bridge.interval, Interval(200, 1000))

    def test_input_order_does_not_choose_a_primary_dataset(self):
        truth, nodes, links, sequences, _ = bridge_fixture()
        snapshots = set()
        for permutation in itertools.permutations(nodes):
            for evidence_order in (links, tuple(reversed(links))):
                result = search_paths(PathGraph(permutation, evidence_order))
                snapshots.add((result.path.nodes, result.path.path_id, reconstruct(result.path, sequences)))
        self.assertEqual(len(snapshots), 1)

    def test_original_n_length_and_parent_coordinates_are_retained(self):
        truth, nodes, links, sequences, original = bridge_fixture(original_gap=True)
        graph = PathGraph(nodes[:2], (), original)
        result = search_paths(graph)
        self.assertEqual(result.path.joins[0].kind, "input_assembly_gap")
        self.assertEqual(result.path.joins[0].n_bp, 137)
        self.assertEqual(result.path.joins[0].gap_interval, Interval(2200, 2337))
        self.assertEqual(reconstruct(result.path, sequences), sequences[nodes[0].source])

    def test_bridge_replaces_original_n_without_overwriting_source(self):
        truth, nodes, links, sequences, original = bridge_fixture(original_gap=True)
        saved = dict(sequences)
        result = search_paths(PathGraph(nodes, links, original))
        self.assertEqual(reconstruct(result.path, sequences), truth)
        self.assertEqual(sequences, saved)
        self.assertTrue(any(d["operation"] == "bridge_replacement" for d in result.decisions))

    def test_reverse_original_connection_reverses_endpoints_not_gap_provenance(self):
        truth, nodes, links, sequences, original = bridge_fixture(original_gap=True)
        a, b = nodes[:2]
        a = replace(a, orientation="-", reference_intervals=(Interval(3000, 5200),),
                    reference_blocks=(ReferenceAnchor(a.interval, Interval(3000, 5200), "ref-a"),))
        b = replace(b, orientation="-", reference_intervals=(Interval(0, 2400),),
                    reference_blocks=(ReferenceAnchor(b.interval, Interval(0, 2400), "ref-b"),))
        result = search_paths(PathGraph([a, b], [], original))
        self.assertEqual(result.path.nodes, ("b", "a"))
        self.assertEqual(result.path.joins[0].gap_interval, original[0].gap_interval)
        self.assertEqual(reconstruct(result.path, sequences), reverse_complement(sequences[a.source]))

    def test_redundant_short_fragment_does_not_create_a_gap(self):
        a, b = placement("long", 0, 2000), placement("short", 500, 700)
        evidence = link(a, b, (500, 700), (0, 200))
        result = search_paths(PathGraph([b, a], [evidence]))
        self.assertEqual(result.path.nodes, ("long",))
        self.assertEqual(result.decisions[-1]["reason"], "represented_by_selected_sources")

    def test_trustworthy_short_unique_sequence_is_not_filtered_by_length(self):
        a, b = placement("long", 0, 2000), placement("short", 2100, 2120)
        result = search_paths(PathGraph([a, b], []))
        self.assertEqual(result.path.nodes, ("long", "short"))
        self.assertEqual(result.path.joins[0].kind, "reference_unknown")
        self.assertEqual(result.path.joins[0].n_bp, 100)

    def test_reference_containment_alone_does_not_prove_redundancy(self):
        a, b = placement("long", 0, 2000), placement("short", 500, 700)
        result = search_paths(PathGraph([a, b], []))
        self.assertEqual(result.path.nodes, ("long",))
        self.assertEqual(result.decisions[-1]["reason"], "unresolved_or_search_limited")
        self.assertTrue(result.decisions[-1]["unrepresented_intervals"])

    def test_ref_uncovered_source_tails_are_not_silently_trimmed(self):
        a = placement("long", 0, 2400)
        a = replace(a, reference_intervals=(Interval(0, 2000),), anchor_intervals=(Interval(200, 2200),),
                    reference_blocks=(ReferenceAnchor(Interval(200, 2200), Interval(0, 2000), "ref-a"),))
        result = search_paths(PathGraph([a], []))
        self.assertEqual(result.path.slices[0].interval, Interval(0, 2400))

    def test_repeat_anchor_without_localization_support_cannot_bridge(self):
        _, nodes, links, _, _ = bridge_fixture()
        a, b, c = nodes
        c = replace(c, anchor_intervals=(Interval(400, 800),))
        graph = PathGraph([a, b, c], links)
        self.assertEqual(graph.joins("a", "c"), ())
        self.assertEqual(graph.joins("c", "b"), ())

    def test_competing_pair_loci_cannot_authorize_a_cut(self):
        a, b = placement("a", 0, 1000), placement("b", 600, 1600)
        good = link(a, b, (600, 1000), (0, 400), number=1)
        competing = link(a, b, (600, 1000), (500, 900), number=2)
        graph = PathGraph([a, b], [good, competing])
        self.assertEqual(graph.joins("a", "b"), ())

    def test_unlocalized_repeat_match_does_not_discharge_source_contribution(self):
        a, b = placement("a", 0, 2000), placement("b", 500, 700)
        a = replace(a, anchor_intervals=(Interval(1000, 2000),))
        evidence = link(a, b, (500, 700), (0, 200))
        result = search_paths(PathGraph([a, b], [evidence]))
        self.assertEqual(result.diagnostics["unique_required_bp"], 2200)
        self.assertEqual(result.decisions[-1]["reason"], "unresolved_or_search_limited")

    def test_two_anchors_in_wrong_bridge_order_do_not_form_a_path(self):
        _, nodes, _, _, _ = bridge_fixture()
        a, b, c = nodes
        wrong = [link(a, c, (1800, 2200), (800, 1200), number=1),
                 link(c, b, (0, 400), (0, 400), number=2)]
        result = search_paths(PathGraph(nodes, wrong))
        self.assertNotEqual(result.path.nodes, ("a", "c", "b"))
        self.assertFalse(any(d["operation"] == "bridge_replacement" for d in result.decisions))

    def test_fabricated_cut_or_evidence_id_is_rejected(self):
        _, nodes, links, _, _ = bridge_fixture()
        graph = PathGraph(nodes, links)
        join = graph.joins("a", "c")[0]
        for fake in (replace(join, left_end=1200), replace(join, evidence_ids=("invented",))):
            with self.assertRaisesRegex(Q0EvidenceError, "unregistered"):
                graph.materialize(("a", "c"), (fake,))

    def test_wrong_orientation_does_not_authorize_overlap(self):
        _, nodes, links, _, _ = bridge_fixture()
        graph = PathGraph(nodes, [replace(link_, hit=replace(link_.hit, strand="-")) for link_ in links])
        self.assertEqual(graph.joins("a", "c"), ())
        self.assertEqual(graph.joins("c", "b"), ())

    def test_inverted_competitor_is_not_hidden_by_orientation_filtering(self):
        a, b = placement("a", 0, 1000), placement("b", 600, 1600)
        good = link(a, b, (600, 1000), (0, 400), number=1)
        inverted = link(a, replace(b, orientation="-"), (600, 1000), (0, 400), number=2)
        self.assertFalse(PathGraph([a, b], [good, inverted]).joins("a", "b"))

    def test_copying_a_dataset_does_not_multiply_coverage_score(self):
        a, b = placement("a", 0, 1000), placement("b", 0, 1200)
        baseline = search_paths(PathGraph([a, b], []))
        copies = [replace(a, placement_id=f"copy{i}", source=SourceKey(f"ds{i}", f"copy{i}")) for i in range(8)]
        evidence = [link(a, copy, (0, 1000), (0, 1000), number=i + 1) for i, copy in enumerate(copies)]
        result = search_paths(PathGraph([a, b, *copies], evidence))
        self.assertEqual(baseline.path.nodes, ("b",))
        self.assertEqual(result.path.nodes, baseline.path.nodes)
        self.assertEqual(result.path.score, baseline.path.score)
        self.assertEqual(result.diagnostics["unique_required_bp"], 2200)

    def test_source_switch_cost_does_not_prefer_members_of_the_same_dataset(self):
        a = placement("a", 0, 1000, dataset="same")
        b = placement("b", 1100, 1700, dataset="same")
        c = placement("c", 1100, 1700, dataset="other")
        graph = PathGraph([a, b, c], [])
        same = graph.materialize(("a", "b"), (graph.joins("a", "b")[0],))
        cross = graph.materialize(("a", "c"), (graph.joins("a", "c")[0],))
        self.assertEqual(same.score, cross.score)

    def test_transitive_repeat_collision_does_not_collapse_source_loci(self):
        # Each pair separately looks unique, but together they map two loci of
        # a to the same b/c coordinate. Discard the conflicting equivalences.
        a, b, c = placement("a", 0, 1000), placement("b", 0, 200), placement("c", 0, 200)
        a, b, c = [replace(p, reference_intervals=(), reference_blocks=(), localization_kind="pairwise") for p in (a, b, c)]
        links = [link(a, b, (0, 200), (0, 200), number=1),
                 link(a, c, (600, 800), (0, 200), number=2),
                 link(b, c, (0, 200), (0, 200), number=3)]
        result = search_paths(PathGraph([a, b, c], links))
        self.assertEqual(result.diagnostics["unique_required_bp"], 1400)
        self.assertEqual(set(result.diagnostics["ambiguous_equivalence_ids"]), {l.hit.evidence_id for l in links})

    def test_low_identity_is_not_sequence_equivalence(self):
        a, b = placement("a", 0, 1000), placement("b", 600, 1600)
        graph = PathGraph([a, b], [link(a, b, (600, 1000), (0, 400), matches=200)])
        self.assertFalse(graph.joins("a", "b"))
        self.assertEqual(graph.materialize(("a",), ()).score[0], 1000)

    def test_indel_chain_uses_a_paired_cut_and_preserves_inserted_bases(self):
        a, b = placement("a", 0, 1000), placement("b", 590, 1600)
        # b has ten additional bases between the two matching runs. Choose
        # either exact paired cut, not an ambiguous insertion boundary.
        b = replace(b, reference_intervals=(Interval(600, 1600),),
                    reference_blocks=(ReferenceAnchor(Interval(0, 200), Interval(600, 800), "ref-b"),
                                      ReferenceAnchor(Interval(210, 1010), Interval(800, 1600), "ref-b")))
        evidence = link(a, b, (600, 1000), (0, 410), cigar="200M10D200M")
        graph = PathGraph([a, b], [evidence])
        joins = graph.joins("a", "b")
        self.assertEqual(len(joins), 2)
        self.assertEqual({(j.left_end, j.right_start) for j in joins}, {(700, 100), (900, 310)})
        result = search_paths(graph)
        # Coverage prioritizes keeping b's unique insertion over dropping it.
        self.assertEqual(result.path.joins[0].left_end, 700)
        self.assertFalse(any(intervals for _, intervals in result.path.missing))

    def test_fragment_paf_offsets_and_both_orientations_are_normalized(self):
        for orientation in ("+", "-"):
            a = placement("a", 0, 1000, offset=123)
            b = placement("b", 600, 1600, offset=500, orientation=orientation)
            evidence = link(a, b, (600, 1000), (0, 400), query_offset=123, target_offset=500)
            blocks = pair_blocks(evidence, a, b)
            self.assertEqual([(b.left, b.right) for b in blocks], [(Interval(600, 1000), Interval(0, 400))])
            self.assertTrue(PathGraph([a, b], [evidence]).joins("a", "b"))

    def test_reciprocal_evidence_is_not_a_second_vote_or_join(self):
        a, b = placement("a", 0, 1000), placement("b", 600, 1600)
        forward = link(a, b, (600, 1000), (0, 400), number=1)
        reverse = link(b, a, (0, 400), (600, 1000), number=2)
        graph = PathGraph([a, b], [forward, reverse, forward])
        self.assertEqual(len(graph.joins("a", "b")), 1)
        self.assertEqual(len(graph.joins("a", "b")[0].evidence_ids), 2)
        self.assertEqual(search_paths(graph).path.score[0], 1600)

    def test_same_source_interval_cannot_be_accepted_twice(self):
        a, b = placement("a", 0, 1000), placement("b", 1100, 2100)
        b = replace(b, source=a.source)
        self.assertFalse(PathGraph([a, b], []).joins("a", "b"))

    def test_repeat_at_distinct_ref_loci_is_not_deduplicated(self):
        a, b = placement("a", 0, 1000), placement("b", 2000, 3000)
        evidence = link(a, b, (0, 1000), (0, 1000))
        result = search_paths(PathGraph([a, b], [evidence]))
        self.assertEqual(result.path.nodes, ("a", "b"))
        self.assertEqual(result.path.score[0], 2000)

    def test_later_competitor_replaces_a_longer_initial_source(self):
        # A long first candidate cannot connect to the two independently
        # supported alternatives. Their combined contribution must win.
        a = placement("a", 0, 1600)
        b, c = placement("b", 0, 1000), placement("c", 1100, 2100)
        result = search_paths(PathGraph([a, b, c], []))
        self.assertEqual(result.path.nodes, ("b", "c"))
        self.assertGreater(result.path.score[0], result.diagnostics["initial_score"][0])
        self.assertTrue(any(d["operation"] == "local_replacement" for d in result.decisions))

    def test_exhausted_budget_is_explicit_and_failed_proposals_are_counted(self):
        nodes = [placement(f"n{i:03}", 0, 1000) for i in range(30)]
        result = search_paths(PathGraph(nodes, [], policy=PathPolicy(maximum_evaluations=12)))
        self.assertEqual(result.diagnostics["evaluations"], 12)
        self.assertIn("maximum_evaluations", result.diagnostics["stop_reasons"])
        self.assertFalse(result.diagnostics["global_optimality_claimed"])
        self.assertTrue(any(d.get("reason") == "unresolved_or_search_limited" for d in result.decisions))

    def test_smallest_budget_and_empty_graph_remain_explicit(self):
        a, b = placement("a", 0, 1000), placement("b", 1100, 2100)
        result = search_paths(PathGraph([a, b], [], policy=PathPolicy(maximum_evaluations=1)))
        self.assertEqual(result.diagnostics["evaluations"], 1)
        self.assertIn("maximum_evaluations", result.diagnostics["stop_reasons"])
        empty = search_paths(PathGraph([], []))
        self.assertIsNone(empty.path)
        self.assertIn("no_admitted_placements", empty.diagnostics["stop_reasons"])

    def test_competing_mapping_outside_selected_fragment_still_blocks_a_cut(self):
        a = placement("a", 0, 1000)
        whole_b = placement("b", 600, 1800)
        b = replace(whole_b, interval=Interval(0, 400), anchor_intervals=(Interval(0, 400),),
                    reference_intervals=(Interval(600, 1000),),
                    reference_blocks=(ReferenceAnchor(Interval(0, 400), Interval(600, 1000), "ref-b"),))
        good = link(a, whole_b, (600, 1000), (0, 400), number=1)
        alternative = link(a, whole_b, (600, 1000), (700, 1100), number=2)
        self.assertFalse(PathGraph([a, b], [good, alternative]).joins("a", "b"))

    def test_soft_original_neighbor_cannot_form_an_independent_seed(self):
        p = placement("a", 0, 1000)
        soft = replace(p, reference_intervals=(), reference_blocks=(), anchor_intervals=(),
                       seed_eligible=False, localization_kind="input_adjacency")
        self.assertIsNone(search_paths(PathGraph([soft], [])).path)

    def test_simple_independent_coverage_is_not_lost_to_quadratic_seed_proposals(self):
        nodes = [placement(f"n{i:03}", i * 200, i * 200 + 100) for i in range(80)]
        result = search_paths(PathGraph(nodes, [], policy=PathPolicy(maximum_evaluations=500)))
        self.assertEqual(len(result.path.nodes), 80)
        self.assertEqual(result.path.score[0], 8000)
        self.assertLessEqual(result.diagnostics["evaluations"], 500)

    def test_provenance_id_order_cannot_choose_a_different_source(self):
        a, b = placement("a", 0, 1000), placement("b", 0, 1000)
        evidence = link(a, b, (0, 1000), (0, 1000))
        before = search_paths(PathGraph([a, b], [evidence]))
        after = search_paths(PathGraph([replace(a, placement_id="zzz"), replace(b, placement_id="aaa")], [evidence]))
        self.assertEqual(before.path.slices[0].source, after.path.slices[0].source)
        self.assertEqual(before.path.slices[0].interval, after.path.slices[0].interval)

    def test_invalid_policies_and_unlocalized_placements_fail(self):
        for kwargs in ({"beam_width": 0}, {"minimum_anchor_bp": -1}, {"minimum_pair_identity": 2}):
            with self.assertRaises(Q0EvidenceError):
                PathPolicy(**kwargs)
        a = placement("a", 0, 1000)
        with self.assertRaises(Q0EvidenceError):
            replace(a, anchor_intervals=())
        with self.assertRaises(Q0EvidenceError):
            PathGraph([a, replace(a, placement_id="b", chromosome="chr2")], [])

    def test_reconstruction_rejects_corrupted_original_gap(self):
        _, nodes, _, sequences, original = bridge_fixture(original_gap=True)
        path = search_paths(PathGraph(nodes[:2], [], original)).path
        sequences[nodes[0].source] = sequences[nodes[0].source].replace("N", "A")
        with self.assertRaisesRegex(Q0EvidenceError, "gap differs"):
            reconstruct(path, sequences)


if __name__ == "__main__":
    unittest.main()
