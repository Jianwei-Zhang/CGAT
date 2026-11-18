"""Real MUMmer4/minimap2 stage tests on controlled pre-q0 evidence fixtures.

GPM_TEST_MUMMER_BIN selects an existing MUMmer4 bin directory; no installation.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from server.tests.test_q0_admission import EvidenceFixture, dna
from server.tests.test_q0_publication import complete_workspace, run_prepare, PROJECT
from server.tools.lgz_core.common import read_fasta, read_tsv, reverse_complement
from server.tools.lgz_core.source_intervals import SourceAuthorization
from server.tools.lgz_core.stage_io import load_q_paths, source_catalog


class RealSourceStructuralPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get("GPM_TEST_MUMMER_BIN")
        cls.tools = {name: str(Path(selected) / name) if selected else shutil.which(name)
                     for name in ("nucmer", "delta-filter", "show-coords")}
        if not shutil.which("minimap2") or not all(value and Path(value).is_file() for value in cls.tools.values()):
            if selected:
                raise RuntimeError("explicit MUMmer4 test environment is incomplete")
            raise unittest.SkipTest("MUMmer4/minimap2 are not installed")
        version = subprocess.run([cls.tools["nucmer"], "--version"], capture_output=True, text=True)
        if not re.search(r"\b4\.\d", version.stdout + version.stderr):
            if selected:
                raise RuntimeError("explicit test environment does not provide MUMmer4")
            raise unittest.SkipTest("default nucmer is not MUMmer4; set GPM_TEST_MUMMER_BIN")

    def run_pipeline(self, root, profile="optimized"):
        for script in ("lgz_step1.py", "lgz_step2.py", "lgz_step3.py"):
            command = [sys.executable, str(PROJECT / "server/tools" / script), "--server-dir", str(root), "--threads", "1"]
            for name, executable in self.tools.items():
                command += ["--"+name, executable]
            if script in {"lgz_step1.py", "lgz_step2.py"}:
                command += ["--execution-profile", profile]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{script}: {result.stdout}\n{result.stderr}")
        sources = source_catalog(root)
        auth = SourceAuthorization.load(root, sources)
        _, paths, _ = load_q_paths(root, "q3", read_tsv(root / "metadata/grt_q_segments.tsv"), sources)
        auth.validate_paths(paths)
        return dict(read_fasta(root / "grt/q/q3.fa"))

    def test_original_n_adjacency_survives_self_context_in_both_orientations(self):
        for orientation, duplicate in (("+", False), ("-", False), ("+", True), ("-", True)):
            with self.subTest(orientation=orientation, duplicate=duplicate), tempfile.TemporaryDirectory() as directory:
                fixture = EvidenceFixture({"chr1": 50000})
                sequence = dna(22000, 74) + "N" * 137 + dna(23000, 75)
                source = fixture.source("assembly", sequence)
                fixture.ref(source, (0, 22000), (0, 22000), strand=orientation)
                if duplicate:
                    fixture.source("clone", sequence)
                root = complete_workspace(fixture, Path(directory))
                prepared = run_prepare(root)
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                expected = sequence if orientation == "+" else reverse_complement(sequence)
                self.assertEqual(dict(read_fasta(root / "grt/q/q0.fa")), {"chr1": expected})
                self.assertEqual(self.run_pipeline(root), {"chr1": expected})
                for version in ("q0", "q1", "q2"):
                    self.assertEqual(dict(read_fasta(root / f"grt/q/{version}.fa")), {"chr1": expected})
                candidates = read_tsv(root / "grt/evidence/step1/candidates.tsv")
                self.assertTrue(any(row["reason"] == "self_context_is_not_independent_structural_evidence" for row in candidates))
                if duplicate:
                    self.assertTrue(any(row["reason"] == "guide_confirms_existing_sequence_context" for row in candidates))

    def test_original_n_split_components_merge_only_with_independent_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = EvidenceFixture({"chr1": 40000})
            before, common, after = dna(4000, 701), dna(12000, 702), dna(4000, 703)
            original = before + common + "N"*137 + common + after
            source = fixture.source("scaffold", original)
            fixture.ref(source, (0, 4000), (0, 4000))
            fixture.ref(source, (28137, 32137), (16000, 20000))
            fixture.source("bridge", before + common + after)
            # Its perfect crossing hit must not suppress the independent
            # bridge's two anchors after equivalent-context rejection.
            fixture.source("clone", original)
            root = complete_workspace(fixture, Path(directory))
            prepared = run_prepare(root)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(dict(read_fasta(root / "grt/q/q0.fa")), {"chr1": original})
            self.assertEqual(self.run_pipeline(root), {"chr1": before + common + after})
            rows = [row for row in read_tsv(root / "metadata/grt_q_segments.tsv") if row["q_version"] == "q3"]
            self.assertTrue(all(row["dataset_name"] == "scaffold" for row in rows))
            self.assertEqual([(row["source_start"], row["source_end"]) for row in rows], [("1", "16000"), ("28138", "32137")])

    def test_real_cross_dataset_overlap_uses_guide_and_releases_trimmed_source(self):
        for profile in ("baseline", "optimized"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                fixture = EvidenceFixture({"chr1": 40000})
                before, overlap, after = dna(4000, 401), dna(12000, 402), dna(4000, 403)
                left = fixture.source("same", before + overlap, dataset="left")
                right = fixture.source("same", overlap + after, dataset="right")
                # Exterior anchors only and a completed empty pre-q0 pair task
                # deliberately leave the junction for actual downstream LGZ.
                fixture.ref(left, (0, 4000), (0, 4000))
                fixture.ref(right, (12000, 16000), (16000, 20000))
                fixture.source("bridge", before + overlap + after, dataset="guide")
                root = complete_workspace(fixture, Path(directory))
                prepared = run_prepare(root)
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                self.assertEqual(dict(read_fasta(root / "grt/q/q0.fa")), {"chr1": before + overlap + "N"*100 + overlap + after})
                records = self.run_pipeline(root, profile)
                self.assertEqual(records, {"chr1": before + overlap + after})
                proofs = [json.loads(row["parameters_json"]) for row in read_tsv(root / "metadata/grt_evidence_registry.tsv")]
                self.assertTrue(any(p.get("source_overlap_support", {}).get("status") == "supported"
                                    for p in proofs if p.get("source_overlap_support") is not None))
                source_rows = [row for row in read_tsv(root / "metadata/grt_q_segments.tsv") if row["q_version"] == "q3"]
                right_row = next(row for row in source_rows if row["dataset_name"] == "right")
                self.assertEqual((right_row["source_start"], right_row["source_end"]), ("12001", "16000"))
                self.assertNotIn("guide", {row["dataset_name"] for row in source_rows})

    def test_removed_overlap_becomes_usable_on_another_chromosome(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = EvidenceFixture({"chr1": 40000, "chr2": 70000})
            before, common, after = dna(4000, 501), dna(12000, 502), dna(4000, 503)
            left = fixture.source("same", before + common, dataset="left")
            right = fixture.source("same", common + after, dataset="right")
            fixture.ref(left, (0, 4000), (0, 4000))
            fixture.ref(right, (12000, 16000), (16000, 20000))
            fixture.source("bridge", before + common + after, dataset="z-guide")
            x_prefix, y_suffix = dna(20000, 504), dna(21000, 505)
            x = fixture.source("x", x_prefix + common[:2000])
            y = fixture.source("y", common[-2000:] + y_suffix)
            fixture.ref(x, (0, 20000), (0, 20000), chromosome="chr2")
            fixture.ref(y, (2000, 23000), (32000, 53000), chromosome="chr2")
            root = complete_workspace(fixture, Path(directory))
            prepared = run_prepare(root)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            frozen = json.loads((root / "metadata/grt_q0_freeze.json").read_text())
            frozen_right = next(row for row in frozen["sources"] if row["source"]["dataset"] == "right")
            self.assertEqual(frozen_right["available"], [])
            self.assertEqual(frozen_right["occupied"], [{"start": 0, "end": 16000}])
            self.assertEqual(self.run_pipeline(root), {"chr1": before + common + after, "chr2": x_prefix + common + y_suffix})
            q3 = [row for row in read_tsv(root / "metadata/grt_q_segments.tsv") if row["q_version"] == "q3"]
            reused = [row for row in q3 if row["chr"] == "chr2" and row["dataset_name"] == "right"]
            self.assertEqual([(row["source_start"], row["source_end"]) for row in reused], [("2001", "10000")])
            decisions = [json.loads(row["parameters_json"]).get("source_interval_authorization")
                         for row in read_tsv(root / "metadata/grt_evidence_registry.tsv")]
            decisions = [row for row in decisions if row]
            self.assertTrue(any(row["status"] == "accepted" and any(
                released["source"]["dataset"] == "right" and released["intervals"] == [{"start": 0, "end": 12000}]
                for released in row.get("released_source_intervals", [])) for row in decisions))
            self.assertTrue(any(row["status"] == "accepted" and row["target_chr"] == "chr2"
                                and row.get("source", {}).get("dataset") == "right"
                                and row["added_source_interval"] == {"start": 2000, "end": 10000} for row in decisions))

    def test_evidence_guided_short_q0_component_survives_length_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = EvidenceFixture({"chr1": 200000})
            long, short = dna(130000, 801), dna(1200, 802)
            a, b = fixture.source("long", long), fixture.source("short", short)
            fixture.ref(a, (0, len(long)), (0, len(long)))
            fixture.ref(b, (0, len(short)), (150000, 151200))
            root = complete_workspace(fixture, Path(directory))
            prepared = run_prepare(root)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            expected = {"chr1": long + "N" * 100 + short}
            self.assertEqual(dict(read_fasta(root / "grt/q/q0.fa")), expected)
            final = self.run_pipeline(root)
            self.assertEqual(len(final["chr1"]), len(expected["chr1"]))
            self.assertEqual(final, expected)
            events = [json.loads(line) for line in (root / "metadata/grt_events.jsonl").read_text().splitlines()]
            retained = [event for event in events if event["stage"] == "step2"
                        and event["reason"] == "q0_supported_short_components_retained"]
            self.assertEqual(len(retained), 1)
            self.assertEqual(retained[0]["edit"]["q0_protection"]["retained_components"], [[130101, 131300]])

    def test_real_terminal_extension_uses_frozen_dtel_and_live_source_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = EvidenceFixture({"chr1": 60000})
            backbone, terminal = dna(50000, 601), "TTTAGGG" * 80
            source = fixture.source("backbone", backbone)
            fixture.ref(source, (0, len(backbone)), (0, len(backbone)))
            fixture.source("tel", backbone[-30000:] + terminal)
            root = complete_workspace(fixture, Path(directory))
            prepared = run_prepare(root)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(dict(read_fasta(root / "grt/q/q0.fa")), {"chr1": backbone})
            self.assertEqual(self.run_pipeline(root), {"chr1": backbone + terminal})
            terminal_evidence = [row for row in read_tsv(root / "metadata/grt_evidence_registry.tsv")
                                 if row["stage"] == "step3" and row["status"] == "accepted"
                                 and row["evidence_type"] in {"mummer_telomere_anchor", "minimap2_terminal_overlap_validation"}]
            self.assertTrue(terminal_evidence)
            self.assertTrue(all(json.loads(row["parameters_json"])["source_interval_authorization"]["status"] == "accepted"
                                for row in terminal_evidence))


if __name__ == "__main__":
    unittest.main()
