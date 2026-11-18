"""Package-v3 delivery checks with controlled q0 input and real stage tools."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from server.tests.test_q0_admission import bridge_fixture, EvidenceFixture, dna
from server.tests.test_q0_publication import complete_workspace, run_prepare, PROJECT
from server.tests.test_grt_prepare_inputs import write_tsv
from server.tests.q0_test_support import seed_q0_evidence
from server.tests import test_source_structural_pipeline as pipeline
from server.tools.lgz_core.common import read_tsv, read_fasta
from server.tools.lgz_core.contract.validator import validate_contract
from server.tools.lgz_core.contract.errors import ContractError
from server.tools.lgz_core.q0_lineage import Q0Lineage, display_peer_keys
from server.tools.lgz_evidence_package import accepted_source_cards, final_segment_anchors


class Q0LineageTests(unittest.TestCase):
    def test_exact_linked_source_coverage_not_name_or_hull(self):
        def row(start, end, evidence):
            return dict(q_version="q0", segment_kind="source", chr="chr1",
                        dataset_name="a", contig_name="ctg", orientation="-",
                        source_start=str(start), source_end=str(end),
                        evidence_ids_json=json.dumps([evidence]))
        index = Q0Lineage([row(1, 100, "e1"), row(201, 300, "e2")])
        source = dict(dataset="a", contig="ctg", start=10, end=90, orientation="-")
        self.assertTrue(index.covers("chr1", source, ["e1"]))
        for chromosome, changed, links in [
            ("chr2", source, ["e1"]), ("chr1", {**source, "dataset": "b"}, ["e1"]),
            ("chr1", {**source, "orientation": "+"}, ["e1"]),
            ("chr1", {**source, "end": 250}, ["e1", "e2"]),
            ("chr1", source, ["e2"]), ("chr1", source, []),
        ]:
            self.assertFalse(index.covers(chromosome, changed, links))


    def test_card_combines_real_event_and_retained_root_not_removed_root(self):
        for normal in (True, False):
            mode = "normal" if normal else "grt_promoted"
            assignment = "assigned" if normal else "unplaced"
            key = f"a:ctg:chr1:{mode}"
            source = dict(dataset="a", contig="ctg", start=1, end=100, orientation="-")
            roots = [dict(q_version="q0", segment_kind="source", chr="chr1",
                          dataset_name="a", contig_name="ctg", orientation="-",
                          source_start="1", source_end="100", evidence_ids_json='["root"]'),
                     dict(q_version="q0", segment_kind="source", chr="chr1",
                          dataset_name="removed", contig_name="ctg", orientation="+",
                          source_start="1", source_end="100", evidence_ids_json='["removed"]')]
            final = {"chromosomes": [{"chr": "chr1", "segments": [
                dict(segment_id="s1", kind="source", length=100, source=source,
                     event_id=None, evidence_ids=["root"]),
                dict(segment_id="s2", kind="patch", length=100,
                     source={**source, "start": 201, "end": 300, "orientation": "+"},
                     event_id="e1", evidence_ids=["patch"]),
            ]}]}
            event = dict(event_id="e1", status="accepted", action="fill", chr="chr1",
                         source={**final["chromosomes"][0]["segments"][1]["source"],
                                 "original_assignment": assignment},
                         source_card_key=key, final_path_segment_id="s2")
            cards = accepted_source_cards([event], {("a", "ctg"): {"chr1"}} if normal else {},
                                          final_segment_anchors(final), {("a", "ctg", "chr1"): ("+", 1)},
                                          final_path=final, q0_lineage=Q0Lineage(roots))
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["event_ids"], ["e1"])
            self.assertEqual(set(cards[0]["segment_ids"]), {"s1", "s2"})
            self.assertEqual(cards[0]["orientation"], "+" if normal else "-")
            self.assertNotIn("_placement_mode", event)

    def test_display_domain_distinguishes_no_peer_from_missing_evidence(self):
        source = dict(dataset_name="a", contig_name="ctg", target_chr="chr1", placement_mode="normal")
        promoted = dict(dataset_name="b", contig_name="ctg", target_chr="chr1", placement_mode="grt_promoted")
        assignments = {("a", "ctg"): {"chr1"}}
        self.assertEqual(display_peer_keys(source, assignments, [source, promoted]), set())
        self.assertEqual(display_peer_keys(promoted, assignments, [source, promoted]), {("a", "ctg")})
        assignments[("a", "second")] = {"chr1"}
        self.assertEqual(display_peer_keys(source, assignments, [source]), {("a", "second")})


class Q0DeliveryTests(unittest.TestCase):
    setUpClass = classmethod(pipeline.RealSourceStructuralPipelineTests.setUpClass.__func__)
    run_pipeline = pipeline.RealSourceStructuralPipelineTests.run_pipeline

    def test_q0_only_sources_have_cards_without_fake_repair_events(self):
        for promoted, reverse in ((False, False), (True, False), (False, True)):
            with self.subTest(promoted=promoted, reverse=reverse), tempfile.TemporaryDirectory() as directory:
                fixture, _truth = bridge_fixture(reverse=reverse)
                source = next(source for source in fixture.sources if source.dataset == "a")
                root = complete_workspace(fixture, Path(directory), unassign={source} if promoted else ())
                if reverse:
                    assignment_path = root / "metadata/chr_assignments.tsv"
                    rows = read_tsv(assignment_path)
                    for row in rows:
                        if row["dataset_name"] == "c":
                            row["source_orientation"] = "+"
                    write_tsv(assignment_path, list(rows[0]), rows)
                    seed_q0_evidence(root)
                prepared = run_prepare(root)
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                self.assertEqual(self.run_pipeline(root), dict(read_fasta(root / "grt/q/q0.fa")))
                command = [sys.executable, str(PROJECT / "server/tools/lgz_evidence_package.py"),
                           "--server-dir", str(root), "--threads", "1"]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                summary = validate_contract(root)
                self.assertEqual(summary["schema_version"], "3")
                cards = read_tsv(root / "metadata/grt_used_contigs.tsv")
                self.assertTrue(cards)
                self.assertTrue(all(json.loads(card["accepted_event_ids_json"]) == [] for card in cards))
                self.assertTrue(all(json.loads(card["final_path_segment_ids_json"]) for card in cards))
                card = next(card for card in cards if card["dataset_name"] == "a")
                self.assertEqual(card["placement_mode"], "grt_promoted" if promoted else "normal")
                if reverse:
                    self.assertEqual(next(card["orientation"] for card in cards if card["dataset_name"] == "c"), "+")
                # Missing comparison output is not the same as having no peer.
                cards_path = root / "metadata/grt_used_contigs.tsv"
                original_cards = cards_path.read_bytes()
                cards[0]["pairwise_evidence_ids_json"] = "[]"
                write_tsv(cards_path, list(cards[0]), cards)
                with self.assertRaisesRegex(ContractError, "incomplete trace"):
                    validate_contract(root)
                cards_path.write_bytes(original_cards)
                q_path = root / "metadata/grt_q_segments.tsv"
                original_q = q_path.read_bytes()
                qrows = read_tsv(q_path)
                next(row for row in qrows if row["q_version"] == "q4" and row["segment_kind"] == "source")["source_card_key"] = "forged"
                write_tsv(q_path, list(qrows[0]), qrows)
                with self.assertRaisesRegex(ContractError, "non-canonical source card"):
                    validate_contract(root)
                q_path.write_bytes(original_q)
                # Correct DNA is insufficient: replacing a root evidence link by
                # another source's legitimate evidence must still fail.
                path = root / "metadata/grt_final_path.json"
                document = json.loads(path.read_text())
                segments = document["chromosomes"][0]["segments"]
                segments[0]["evidence_ids"] = segments[1]["evidence_ids"]
                path.write_text(json.dumps(document))
                with self.assertRaisesRegex(ContractError, "q4 source mapping|frozen q0 provenance"):
                    validate_contract(root)

    def test_single_source_has_no_invented_pairwise_alignment(self):
        for promoted, orientation in ((False, "+"), (True, "-")):
            with self.subTest(promoted=promoted), tempfile.TemporaryDirectory() as directory:
                fixture = EvidenceFixture({"chr1": 5000})
                source = fixture.source("only", dna(2000))
                fixture.ref(source, (0, 2000), (0, 2000), strand=orientation)
                root = complete_workspace(fixture, Path(directory), unassign={source} if promoted else ())
                prepared = run_prepare(root)
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                self.run_pipeline(root)
                result = subprocess.run([sys.executable, str(PROJECT / "server/tools/lgz_evidence_package.py"),
                                         "--server-dir", str(root), "--threads", "1"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                relocated = root.with_name("relocated")
                root.rename(relocated)
                root = relocated
                validate_contract(root)
                cards = read_tsv(root / "metadata/grt_used_contigs.tsv")
                self.assertEqual(len(cards), 1)
                self.assertEqual(json.loads(cards[0]["pairwise_evidence_ids_json"]), [])
                self.assertEqual(json.loads(cards[0]["accepted_event_ids_json"]), [])
                self.assertEqual(cards[0]["orientation"], orientation)

    def test_real_telomere_event_and_q0_root_have_separate_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = EvidenceFixture({"chr1": 60000})
            backbone, terminal = dna(50000, 601), "TTTAGGG" * 80
            source = fixture.source("backbone", backbone)
            fixture.ref(source, (0, len(backbone)), (0, len(backbone)))
            fixture.source("tel", backbone[-30000:] + terminal)
            root = complete_workspace(fixture, Path(directory))
            prepared = run_prepare(root)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(self.run_pipeline(root), {"chr1": backbone + terminal})
            result = subprocess.run([sys.executable, str(PROJECT / "server/tools/lgz_evidence_package.py"),
                                     "--server-dir", str(root), "--threads", "1"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            validate_contract(root)
            cards = {card["dataset_name"]: card for card in read_tsv(root / "metadata/grt_used_contigs.tsv")}
            self.assertEqual(set(cards), {"backbone", "tel"})
            self.assertEqual(json.loads(cards["backbone"]["accepted_event_ids_json"]), [])
            self.assertEqual(len(json.loads(cards["tel"]["accepted_event_ids_json"])), 1)
            self.assertEqual(cards["tel"]["original_assignment"], "unplaced")
            self.assertTrue(json.loads(cards["tel"]["pairwise_evidence_ids_json"]))
