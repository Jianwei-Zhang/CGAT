from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server.tools.lgz_core import q0_admission
from server.tools.lgz_core.common import reverse_complement
from server.tools.lgz_core.q0_admission import (AdmissionPolicy, EvidenceInput, admit_placements,
                                               build_q0, construct_q0, load_evidence_input,
                                               _links_for_path_graphs, _ordered, _pair_neighbors,
                                               _PlacementNeighbors)
from server.tools.lgz_core.q0_reference_competition import _ReferenceBlockCandidates
from server.tools.lgz_core.q0_alignments import parse_paf_line
from server.tools.lgz_core.q0_catalog import evidence_ref
from server.tools.lgz_core.q0_paths import PairLink, ReferenceAnchor
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError, SourceKey, split_source


def dna(length, seed=17):
    return "".join(random.Random(seed).choices("ACGT", k=length))


class EvidenceFixture:
    def __init__(self, references=None):
        self.sources, self.refs, self.links, self.evidence = {}, {}, [], {}
        self.reference_lengths = references or {"chr1": 5000}
        self.raw = {}

    def source(self, name, sequence, dataset=None):
        source = SourceKey(dataset or name, name)
        self.sources[source] = sequence
        return source

    def paf(self, query, qrange, target_name, target_length, trange, *, strand="+", mapq=60, artifact="reference.paf"):
        length = qrange[1] - qrange[0]
        raw = "\t".join(map(str, [query.contig, len(self.sources[query]), *qrange, strand, target_name,
                                  target_length, *trange, length, length, mapq, f"cg:Z:{length}M"]))
        lines = self.raw.setdefault(artifact, [])
        lines.append(raw)
        hit = parse_paf_line(raw, artifact=artifact, line_number=len(lines))
        self.evidence[hit.evidence_id] = evidence_ref(hit)
        return hit

    def ref(self, source, qrange, trange, *, chromosome="chr1", strand="+", mapq=60):
        hit = self.paf(source, qrange, chromosome, self.reference_lengths[chromosome], trange,
                       strand=strand, mapq=mapq, artifact=f"runs/{source.dataset}_vs_ref/result.paf")
        self.refs.setdefault(source, []).append(hit)
        return hit

    def pair(self, query, target, qrange, trange, *, strand="+"):
        hit = self.paf(query, qrange, target.contig, len(self.sources[target]), trange, strand=strand,
                       artifact=f"runs/chr_chr1/{target.dataset}_vs_{query.dataset}/result.paf")
        self.links.append(PairLink(hit, query, target))
        return hit

    def data(self):
        parts, edges = {}, []
        for source, sequence in self.sources.items():
            index = split_source(source, sequence)
            parts.update((p.segment_id, p) for p in index.segments)
            edges.extend(index.adjacencies)
        evidence = dict(self.evidence)
        for edge in edges:
            evidence[edge.adjacency_id] = {"kind": "input_assembly_adjacency", "source": edge.source.contig}
        return EvidenceInput(dict(self.sources), parts, dict(self.reference_lengths), dict(self.refs),
                             tuple(self.links), tuple(edges), evidence, "controlled-input")

    def workspace(self, directory):
        from server.tests.test_grt_prepare_inputs import write_fasta, write_tsv
        from server.tests.q0_test_support import seed_q0_evidence
        root = Path(directory) / "gpm_server"
        rows = []
        datasets = sorted({s.dataset for s in self.sources})
        for dataset in datasets:
            relative = f"data/datasets/{dataset}.fa"
            write_fasta(root / relative, [(s.contig, seq) for s, seq in self.sources.items() if s.dataset == dataset])
            rows.append({"dataset_name": dataset, "fasta_relpath": relative})
            run = root / f"runs/{dataset}_vs_ref"
            run.mkdir(parents=True, exist_ok=True)
            (run / "tool_version.txt").write_text("controlled-paf-fixture\n")
            (run / "result.paf").write_text("\n".join(self.raw.get(f"runs/{dataset}_vs_ref/result.paf", [])) + "\n")
        write_tsv(root / "metadata/datasets.tsv", ["dataset_name", "fasta_relpath"], rows)
        write_fasta(root / "data/reference/ref.fa", [(name, getattr(self, "reference_sequences", {}).get(name, dna(length))) for name, length in self.reference_lengths.items()])
        write_tsv(root / "metadata/reference.tsv", ["fasta_relpath"], [{"fasta_relpath": "data/reference/ref.fa"}])
        write_tsv(root / "metadata/prepare_options.tsv", ["key", "value"], [{"key": "minimap_preset", "value": "asm10"}, {"key": "alignment_engine", "value": "minimap2"}, {"key": "threads", "value": "1"}])
        write_tsv(root / "metadata/track_member_orders.tsv", ["target_track", "target_chr", "member_dataset", "member_ctg", "member_order"], [])
        groups = {(s.dataset, s.contig, h.target_name) for s, hits in self.refs.items() for h in hits}
        write_tsv(root / "metadata/chr_assignments.tsv", ["dataset_name", "seq_name", "assigned_chr_name"],
                  [dict(zip(["dataset_name", "seq_name", "assigned_chr_name"], group)) for group in sorted(groups)])
        for relative, lines in self.raw.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines) + "\n")
        seed_q0_evidence(root)
        return root


def bridge_fixture(reverse=False):
    truth = dna(5000)
    fixture = EvidenceFixture()
    a = fixture.source("a", truth[:2200])
    b = fixture.source("b", truth[2600:])
    c = fixture.source("c", reverse_complement(truth[1800:3000]) if reverse else truth[1800:3000])
    fixture.ref(a, (0, 2200), (0, 2200))
    fixture.ref(b, (0, 2400), (2600, 5000))
    fixture.ref(c, (0, 1200), (1800, 3000), strand="-" if reverse else "+")
    fixture.pair(c, a, (800, 1200) if reverse else (0, 400), (1800, 2200), strand="-" if reverse else "+")
    fixture.pair(c, b, (0, 400) if reverse else (800, 1200), (0, 400), strand="-" if reverse else "+")
    return fixture, truth


class Q0AdmissionTests(unittest.TestCase):
    def test_fragmented_pair_screens_full_root_context_once(self):
        fixture = EvidenceFixture()
        source = dna(8000)
        anchor = fixture.source("root", source)
        fixture.ref(anchor, (0, 2500), (0, 2500))
        for name, start in (("off_ref", 3000), ("off_ref_second", 5000)):
            child = fixture.source(name, source[start:start + 2000])
            for offset in range(0, 2000, 200):
                fixture.pair(child, anchor, (offset, offset + 200), (start + offset, start + offset + 200))
        calls = []
        original = q0_admission._ComplexityCache.intervals
        def screen(cache, sequence, key, interval):
            calls.append((sequence, interval))
            return original(cache, sequence, key, interval)
        with patch.object(q0_admission._ComplexityCache, "intervals", screen):
            admission = admit_placements(fixture.data())
        self.assertEqual({p.source.contig for p in admission.placements if p.localization_kind == "pairwise"},
                         {"off_ref", "off_ref_second"})
        self.assertEqual(sum(args == (source, Interval(0, len(source))) for args in calls), 1)

    def test_reference_block_index_is_complete_for_nested_touching_and_random_intervals(self):
        rng = random.Random(9)
        pairs = [(0, 120), (1, 2), (2, 3), (121, 140), (3, 121)]
        pairs.extend((x, x + rng.randrange(1, 40)) for x in (rng.randrange(200) for _ in range(100)))
        rows = [SimpleNamespace(query=Interval(*pair), id=i) for i, pair in enumerate(pairs)]
        rng.shuffle(rows)
        index = _ReferenceBlockCandidates(rows)
        for row in rows:
            expected = {(other.id, i) for other in rows if (i := other.query.intersection(row.query)) is not None}
            self.assertEqual({(other.id, i) for other, i in index.intersecting(row.query)}, expected)

    def test_reference_order_matches_all_pairs_on_both_strands(self):
        def legacy(anchors, strand):
            for n, a in enumerate(anchors):
                for b in anchors[n+1:]:
                    if a.source.intersection(b.source):
                        continue
                    left, right = (a, b) if (a.source.start < b.source.start) == (strand == '+') else (b, a)
                    if left.reference.end > right.reference.start:
                        return False
            return True
        rng = random.Random(19)
        for _ in range(250):
            anchors = []
            for i in range(rng.randrange(1, 24)):
                pos, target, length = rng.randrange(30), rng.randrange(30), rng.randrange(1, 12)
                anchors.append(ReferenceAnchor(Interval(pos, pos+length), Interval(target, target+length), str(i)))
            for strand in ('+', '-'):
                self.assertEqual(_ordered(iter(anchors), strand), legacy(anchors, strand))
        forward = [ReferenceAnchor(Interval(i, i+1), Interval(i+1, i+2), str(i)) for i in range(100)]
        reverse = [ReferenceAnchor(a.source, Interval(100-a.source.start, 101-a.source.start), a.evidence_id) for a in forward]
        self.assertTrue(_ordered(reversed(forward), '+'))
        self.assertTrue(_ordered(reverse, '-'))
        self.assertFalse(_ordered(forward, '-'))
        self.assertFalse(_ordered(reverse, '+'))

    def test_sparse_neighbors_keep_snapshot_order_and_every_link_in_both_directions(self):
        f = EvidenceFixture()
        a, b, c, missing, unused = (f.source(name, dna(1000)) for name in ('a', 'b', 'c', 'm', 'u'))
        for left, right in ((a, c), (b, a), (a, missing), (a, a), (c, a)):
            f.pair(left, right, (0, 250), (500, 750))
        by_source = _pair_neighbors(f.links)
        self.assertIs(by_source[a][c], by_source[c][a])
        self.assertNotIn(a, by_source[a])
        placements = [SimpleNamespace(source=source, placement_id=str(i))
                      for i, source in enumerate((c, unused, b, c, a))]
        ordered = _PlacementNeighbors(placements, by_source)
        linked = ordered.for_source(a)
        self.assertEqual([p.placement_id for p, _ in linked], ['0', '2', '3'])
        self.assertEqual([list(links) for _, links in linked], [[f.links[0], f.links[4]], [f.links[1]], [f.links[0], f.links[4]]])
        self.assertEqual([p.placement_id for p, _ in ordered.for_source(a, after=2)], ['3'])
        self.assertEqual(ordered.for_source(unused), [])

    def test_path_graph_routing_keeps_all_conflicts_and_same_source_links_on_shared_chr(self):
        f = EvidenceFixture()
        a, b, c, unplaced = (f.source(name, dna(1000)) for name in ('a', 'b', 'c', 'u'))
        for left, right, strand in ((a, b, '+'), (a, c, '+'), (a, a, '-'), (a, b, '-'), (a, unplaced, '+')):
            f.pair(left, right, (0, 250), (500, 750), strand=strand)
        placements = [SimpleNamespace(source=s, chromosome=chr) for s, chr in
                      ((a, 'x'), (b, 'x'), (a, 'y'), (b, 'y'), (c, 'z'))]
        actual = _links_for_path_graphs(placements, f.links)
        self.assertEqual(dict(actual), {'x': [f.links[0], f.links[2], f.links[3]],
                                        'y': [f.links[0], f.links[2], f.links[3]]})

    def test_raw_reference_and_pairwise_evidence_build_bridge_without_admitted_test_nodes(self):
        fixture, truth = bridge_fixture()
        result = construct_q0(fixture.data())
        self.assertEqual(result.records, {"chr1": truth})
        self.assertEqual([j.kind for j in result.paths["chr1"].path.joins], ["sequence_overlap"] * 2)
        self.assertEqual(result.decisions["qc"], "not_measured")
        json.dumps(result.decisions)

    def test_reverse_bridge_is_reconstructed_from_original_source(self):
        fixture, truth = bridge_fixture(reverse=True)
        result = construct_q0(fixture.data())
        self.assertEqual(result.records["chr1"], truth)
        self.assertIn("-", [s.orientation for s in result.paths["chr1"].path.slices])

    def test_dataset_and_evidence_input_order_do_not_change_selected_sources(self):
        fixture, _ = bridge_fixture()
        data = fixture.data()
        first = construct_q0(data)
        second = construct_q0(replace(data, sources=dict(reversed(list(data.sources.items()))),
                                      parts=dict(reversed(list(data.parts.items()))), pair_links=tuple(reversed(data.pair_links))))
        self.assertEqual(first.records, second.records)
        self.assertEqual(first.paths["chr1"].path.slices, second.paths["chr1"].path.slices)

    def test_cross_chr_repeat_tail_is_kept_but_not_used_as_a_unique_anchor(self):
        f = EvidenceFixture({"chr1": 5000, "chr2": 5000})
        source = f.source("long", "TTAGGG" * 100 + dna(1300))
        f.ref(source, (0, 600), (0, 600), mapq=0)
        f.ref(source, (0, 600), (2000, 2600), chromosome="chr2", mapq=0)
        f.ref(source, (600, 1900), (600, 1900))
        result = construct_q0(f.data())
        self.assertEqual(result.records, {"chr1": f.sources[source]})
        placement = result.admission.placements[0]
        self.assertTrue(all(i.start >= 600 for i in placement.anchor_intervals))
        self.assertEqual(result.decisions["chromosomes"][1]["status"], "not_constructed")

    def test_cross_chr_specific_parts_are_not_split_without_independent_support(self):
        f = EvidenceFixture({"chr1": 5000, "chr2": 5000})
        chim = f.source("chim", dna(800, 1) + dna(800, 2))
        f.ref(chim, (0, 800), (0, 800))
        f.ref(chim, (800, 1600), (0, 800), chromosome="chr2")
        admission = admit_placements(f.data())
        self.assertFalse(admission.placements)
        self.assertTrue(any(row.get("reason") == "structural_ref_conflict" for row in admission.records))
        with self.assertRaisesRegex(Q0EvidenceError, "no chromosome"):
            construct_q0(f.data())

    def test_cross_chr_local_selection_uses_exact_disjoint_supported_source_intervals(self):
        f = EvidenceFixture({"chr1": 5000, "chr2": 5000})
        a = f.source("a", dna(800, 1)[:300])
        b = f.source("b", dna(800, 2)[:300])
        chim = f.source("chim", dna(800, 1) + dna(800, 2))
        f.ref(a, (0, 300), (0, 300)); f.ref(b, (0, 300), (0, 300), chromosome="chr2")
        f.ref(chim, (0, 800), (0, 800)); f.ref(chim, (800, 1600), (0, 800), chromosome="chr2")
        f.pair(chim, a, (0, 300), (0, 300)); f.pair(chim, b, (800, 1100), (0, 300))
        result = construct_q0(f.data())
        fragments = [p for p in result.admission.placements if p.source == chim]
        self.assertEqual({p.interval for p in fragments}, {Interval(0, 800), Interval(800, 1600)})
        self.assertEqual(result.records, {"chr1": dna(800, 1), "chr2": dna(800, 2)})

    def test_ref_uncovered_pairwise_neighbor_can_extend_an_anchored_source(self):
        truth = dna(2500)
        f = EvidenceFixture({"chr1": 2500})
        a, b = f.source("a", truth[:1400]), f.source("b", truth[1000:])
        f.ref(a, (0, 1000), (0, 1000))
        f.pair(b, a, (0, 400), (1000, 1400))
        result = construct_q0(f.data())
        self.assertEqual(result.records["chr1"], truth)
        derived = next(p for p in result.admission.placements if p.source == b)
        self.assertEqual(derived.localization_kind, "pairwise")
        self.assertEqual(derived.reference_blocks, ())
        self.assertEqual(derived.reference_intervals, ())

    def test_actual_off_ref_overlap_is_not_rejected_by_disjoint_ref_hulls(self):
        truth = dna(2500)
        f = EvidenceFixture({"chr1": 2100})
        a, b = f.source("a", truth[:1400]), f.source("b", truth[1000:])
        f.ref(a, (0, 1000), (0, 1000)); f.ref(b, (400, 1500), (1000, 2100))
        f.pair(b, a, (0, 400), (1000, 1400))
        result = construct_q0(f.data())
        self.assertEqual(result.records["chr1"], truth)
        self.assertEqual(result.paths["chr1"].path.joins[0].kind, "sequence_overlap")

    def test_same_sequence_at_different_ref_loci_is_not_collapsed(self):
        f = EvidenceFixture()
        a, b = f.source("a", dna(1000)), f.source("b", dna(1000))
        f.ref(a, (0, 1000), (0, 1000)); f.ref(b, (0, 1000), (2000, 3000))
        f.pair(b, a, (0, 1000), (0, 1000))
        result = construct_q0(f.data())
        self.assertEqual(result.records["chr1"], dna(1000) + "N" * 100 + dna(1000))

    def test_mapq_alone_does_not_override_competing_reference_loci(self):
        f = EvidenceFixture({"chr1": 5000, "chr2": 5000})
        source = f.source("repeat", dna(1000))
        f.ref(source, (0, 1000), (0, 1000)); f.ref(source, (0, 1000), (0, 1000), chromosome="chr2")
        self.assertFalse(admit_placements(f.data()).placements)

    def test_unknown_mapq_is_not_treated_as_high_confidence_but_pair_can_confirm_it(self):
        f = EvidenceFixture()
        a, b = f.source("a", dna(1000)), f.source("b", dna(1000)[200:800])
        f.ref(a, (0, 1000), (0, 1000)); f.ref(b, (0, 600), (200, 800), mapq=255)
        self.assertFalse(any(p.source == b for p in admit_placements(f.data()).placements))
        f.pair(b, a, (0, 600), (200, 800))
        self.assertTrue(any(p.source == b for p in admit_placements(f.data()).placements))

    def test_noncollinear_ref_anchors_are_not_mistaken_for_one_ordered_chain(self):
        f = EvidenceFixture()
        a = f.source("a", dna(2000))
        f.ref(a, (0, 1000), (2000, 3000)); f.ref(a, (1000, 2000), (0, 1000))
        result = admit_placements(f.data())
        self.assertFalse(result.placements)
        self.assertTrue(any(row.get("reason") == "noncollinear_reference_anchors" for row in result.records))

    def test_unaligned_original_n_neighbor_is_retained_only_as_soft_context(self):
        f = EvidenceFixture()
        sequence = dna(1000) + "N" * 137 + dna(500, 42)
        a = f.source("a", sequence)
        f.ref(a, (0, 1000), (0, 1000))
        result = construct_q0(f.data())
        self.assertEqual(result.records["chr1"], sequence)
        soft = next(p for p in result.admission.placements if not p.seed_eligible)
        self.assertEqual(soft.anchor_intervals, ())
        self.assertEqual(soft.localization_kind, "input_adjacency")
        self.assertEqual(result.decisions["unselected_source_intervals"][0]["intervals"], [])
        self.assertEqual(result.decisions["chromosomes"][0]["input_gap_joins"], 1)

    def test_original_adjacency_cannot_override_specific_other_chr_evidence(self):
        f = EvidenceFixture({"chr1": 5000, "chr2": 5000})
        a = f.source("a", dna(1000) + "N" * 100 + dna(500, 42))
        f.ref(a, (0, 1000), (0, 1000)); f.ref(a, (1100, 1600), (0, 500), chromosome="chr2", mapq=255)
        result = construct_q0(f.data())
        self.assertEqual(result.records["chr1"], dna(1000))
        self.assertTrue(any(r.get("reason") == "input_adjacency_conflict" for r in result.admission.records))

    def test_all_n_source_is_retained_as_unselected_not_a_fake_chr(self):
        f = EvidenceFixture()
        a = f.source("a", dna(1000)); f.source("allN", "N" * 1000)
        f.ref(a, (0, 1000), (0, 1000))
        result = construct_q0(f.data())
        self.assertEqual(result.records["chr1"], dna(1000))
        self.assertEqual(len(result.decisions["unselected_source_intervals"]), 2)

    def test_qc_input_is_explicit_and_failed_sources_do_not_enter_q0(self):
        fixture, _ = bridge_fixture()
        data = fixture.data()
        with self.assertRaisesRegex(Q0EvidenceError, "every source"):
            construct_q0(data, quality_pass={})
        passed = {key: key.contig != "c" for key in data.sources}
        result = construct_q0(data, quality_pass=passed)
        self.assertFalse(any(p.source.contig == "c" for p in result.admission.placements))
        self.assertEqual(result.decisions["qc"], "supplied_source_decisions")

    def test_missing_evidence_reference_fails_instead_of_inventing_proof(self):
        fixture, _ = bridge_fixture()
        data = fixture.data()
        data.evidence.pop(next(iter(data.evidence)))
        with self.assertRaisesRegex(Q0EvidenceError, "missing evidence"):
            construct_q0(data)

    def test_bound_workspace_to_q0_construction_preserves_original_inputs(self):
        fixture, truth = bridge_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = fixture.workspace(directory)
            originals = {p: p.read_bytes() for p in (root / "data").rglob("*.fa")}
            result = build_q0(root)
            self.assertEqual(result.records, {"chr1": truth})
            self.assertEqual({p: p.read_bytes() for p in originals}, originals)
            self.assertFalse((root / "grt/q/q0.fa").exists(), "construction must not publish around the donor transaction")
            self.assertTrue(load_evidence_input(root).pair_links)
            (root / "runs/a_vs_ref/result.paf").write_text("")
            with self.assertRaises(Q0EvidenceError):
                build_q0(root)

    def test_short_unique_ref_candidate_is_admitted_without_contig_length_filter(self):
        f = EvidenceFixture()
        a, short = f.source("a", dna(1000)), f.source("short", dna(20, 99))
        f.ref(a, (0, 1000), (0, 1000)); f.ref(short, (0, 20), (1200, 1220))
        result = construct_q0(f.data())
        self.assertEqual(result.records["chr1"], f.sources[a] + "N" * 100 + f.sources[short])

    def test_pairwise_only_discovery_is_rooted_and_reaches_a_fixed_point(self):
        truth = dna(3000)
        f = EvidenceFixture({"chr1": 3000})
        a, b, c = [f.source(name, truth[start:end]) for name, start, end in (("a", 0, 1400), ("b", 1000, 2400), ("c", 2000, 3000))]
        f.ref(a, (0, 1000), (0, 1000))
        f.pair(b, a, (0, 400), (1000, 1400)); f.pair(c, b, (0, 400), (1000, 1400))
        result = construct_q0(f.data())
        self.assertEqual(result.records["chr1"], truth)
        self.assertEqual(max(row.get("round", 0) for row in result.admission.records), 2)
        self.assertEqual(sum(bool(p.reference_blocks) for p in result.admission.placements), 1)

    def test_unrooted_pairwise_cycle_cannot_make_a_chr(self):
        f = EvidenceFixture()
        a, b = f.source("a", dna(1000)), f.source("b", dna(1000))
        f.pair(b, a, (0, 1000), (0, 1000))
        with self.assertRaisesRegex(Q0EvidenceError, "no chromosome"):
            construct_q0(f.data())

    def test_repetitive_off_ref_match_cannot_authorize_a_false_overlap(self):
        f = EvidenceFixture()
        tail = "TTAGGG" * 100
        a, b = f.source("a", dna(1000) + tail), f.source("b", tail + dna(1000, 42))
        f.ref(a, (0, 1000), (0, 1000)); f.ref(b, (600, 1600), (1000, 2000))
        f.pair(b, a, (0, 600), (1000, 1600))
        result = construct_q0(f.data())
        self.assertEqual(result.paths["chr1"].path.joins[0].kind, "reference_unknown")
        self.assertEqual(result.records["chr1"], f.sources[a] + "N" * 100 + f.sources[b])

    def test_real_minimap_pafs_flow_through_ready_evidence_and_new_selector(self):
        import contextlib
        import io
        import shlex
        import shutil
        import subprocess
        from server.tools.lgz_core.q0_preparation import prepare_evidence
        from server.tools.run_outer_checkpoints import OuterCheckpointManager
        minimap = shutil.which("minimap2")
        if not minimap:
            self.skipTest("requires minimap2 for controlled evidence-to-q0 validation")
        truth = dna(25000)
        f = EvidenceFixture({"chr1": 25000})
        a, b, c = f.source("a", truth[:11000]), f.source("b", truth[13000:]), f.source("c", truth[9000:15000])
        f.ref(a, (0, 11000), (0, 11000)); f.ref(b, (0, 12000), (13000, 25000)); f.ref(c, (0, 6000), (9000, 15000))
        f.pair(c, a, (0, 2000), (9000, 11000)); f.pair(c, b, (4000, 6000), (0, 2000))
        with tempfile.TemporaryDirectory() as directory:
            root = f.workspace(directory)
            for source in (a, b, c):
                output = root / f"runs/{source.dataset}_vs_ref/result.paf"
                command = [minimap, "-t", "1", "-x", "asm5", "-c", "-o", str(output),
                           str(root / "data/reference/ref.fa"), str(root / f"data/datasets/{source.dataset}.fa")]
                completed = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
            descriptor = json.loads((root / "runs/chr_chr1/q0_alignment_inputs.json").read_text())
            scripts = []
            for row in descriptor["alignments"]:
                command = [minimap, "-t", "1", "-x", "asm5", "-D", "-P", "--dual=yes", "--no-long-join", "-c",
                           "-o", str(root / row["paf"]), str(root / row["target_fasta"]), str(root / row["query_fasta"])]
                script = root / row["run_dir"] / "command.sh"
                script.write_text("#!/bin/sh\nset -eu\n" + shlex.join(command) + "\n")
                scripts.append("bash " + shlex.quote(str(script)))
            wrapper = root / "runs/chr_chr1/q0_command.sh"
            wrapper.write_text("#!/bin/sh\nset -eu\n" + "\n".join(scripts) + "\n")
            manager = OuterCheckpointManager(root)
            before = manager.prepare("q0_chr:chr1", "runs/chr_chr1/q0_command.sh")
            completed = subprocess.run(["bash", str(wrapper)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manager.commit(before)
            with contextlib.redirect_stdout(io.StringIO()):
                prepare_evidence(root, minimap2=minimap)
            result = build_q0(root)
            self.assertEqual(result.records, {"chr1": truth})
            self.assertEqual([j.kind for j in result.paths["chr1"].path.joins], ["sequence_overlap"] * 2)

    def test_other_chr_pair_support_can_localize_a_tail_absent_from_direct_ref_hits(self):
        f = EvidenceFixture({"chr1": 5000, "chr2": 5000})
        main, tail = dna(1000), dna(1500, 42)
        a, b = f.source("a", main + tail[:600]), f.source("b", tail)
        f.ref(a, (0, 1000), (0, 1000)); f.ref(b, (0, 1500), (0, 1500), chromosome="chr2")
        f.pair(b, a, (0, 600), (1000, 1600))
        result = construct_q0(f.data())
        self.assertEqual(result.records, {"chr1": main, "chr2": tail})
        pieces = [p for p in result.admission.placements if p.source == a]
        self.assertEqual({(p.chromosome, p.interval) for p in pieces},
                         {("chr1", Interval(0, 1000)), ("chr2", Interval(1000, 1600))})

    def test_other_source_continuity_prevents_ref_driven_cross_chr_tail_cut(self):
        f = EvidenceFixture({"chr1": 5000, "chr2": 5000})
        main, tail = dna(1000), dna(1500, 42)
        a, b, c = f.source("a", main + tail[:600]), f.source("b", tail), f.source("c", main + tail[:600])
        f.ref(a, (0, 1000), (0, 1000)); f.ref(c, (0, 1000), (0, 1000))
        f.ref(b, (0, 1500), (0, 1500), chromosome="chr2")
        f.pair(b, a, (0, 600), (1000, 1600)); f.pair(c, a, (0, 1600), (0, 1600))
        result = construct_q0(f.data())
        self.assertEqual(result.records["chr1"], main + tail[:600])
        self.assertTrue(any(row.get("reason") == "cross_chr_tail_continuity_supported" for row in result.admission.records))

    def test_selector_change_during_build_is_rejected_before_publication(self):
        from unittest import mock
        from server.tools.lgz_core import q0_admission
        fixture, _ = bridge_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = fixture.workspace(directory)
            with mock.patch.object(q0_admission, "selector_identity", side_effect=["before", "before", "after"]):
                with self.assertRaisesRegex(Q0EvidenceError, "selector changed"):
                    build_q0(root)
            self.assertFalse((root / "grt/q/q0.fa").exists())

    def test_preparation_discovers_other_chr_match_for_an_already_grouped_partial_source(self):
        import contextlib
        import io
        import shutil
        from server.tools.lgz_core.q0_preparation import prepare_evidence
        minimap = shutil.which("minimap2")
        if not minimap:
            self.skipTest("requires minimap2 for partial-source evidence discovery")
        f = EvidenceFixture({"chr1": 5000, "chr2": 5000})
        f.reference_sequences = {"chr1": dna(5000), "chr2": dna(5000, 42)}
        main, tail = dna(1000), dna(1500, 42)
        a, b = f.source("a", main + tail[:600]), f.source("b", tail)
        f.ref(a, (0, 1000), (0, 1000)); f.ref(b, (0, 1500), (0, 1500), chromosome="chr2")
        # No pair PAF is supplied: different original chr groups have no base
        # pair operation. Preparation itself must discover this missing link.
        with tempfile.TemporaryDirectory() as directory:
            root = f.workspace(directory)
            with contextlib.redirect_stdout(io.StringIO()):
                prepare_evidence(root, minimap2=minimap)
            data = load_evidence_input(root)
            self.assertTrue(any(task["kind"] == "partial_source_discovery" for task in data.catalog["supplementary_alignments"]))
            self.assertTrue(any({link.query_source, link.target_source} == {a, b} for link in data.pair_links))
            result = build_q0(root)
            self.assertEqual(result.records, {"chr1": main, "chr2": tail})

    def test_invalid_admission_policy_fails(self):
        for kwargs in ({"minimum_reference_identity": 0}, {"minimum_reference_mapq": 255}, {"kmer_size": 0}):
            with self.assertRaises(Q0EvidenceError):
                AdmissionPolicy(**kwargs)


if __name__ == "__main__":
    unittest.main()
