"""Controlled native proposals plus real samtools indexing, not a reads benchmark."""
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import post_lgz_degap as gapfill
from run_orchestration import build_unit_plan
from refinement_config import load_request, save_request
from workspace_layout import initialize_workspace
import server_run


@unittest.skipUnless(shutil.which("samtools"), "samtools required for bounded FASTA access")
class PostLgzTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "metadata").mkdir()
        (self.root / "grt/q").mkdir(parents=True)
        self.reads = self.root / "reads_file.fq"
        self.reads.write_text("@r\nACGT\n+\nIIII\n")
        self.config = {"schema_version": 2, "purpose": gapfill.PURPOSE,
                       "hifi": [str(self.reads)], "ont": []}
        gapfill.atomic_json(self.root / "metadata/degap_inputs.json", self.config)
        (self.root / "metadata/grt_final_path.json").write_text(json.dumps({"unchanged": True}))
        self.original = "AAA" + "N" * 20 + "CCC"
        self.fasta(self.original)
        self.real_run = subprocess.run
        self.native_calls = []
        self.mutate = lambda rows, native: None

    def fasta(self, sequence):
        self.original = sequence
        # Wrapping deliberately cuts across N runs.
        (self.root / "grt/q/q3.fa").write_text(">chr1\n" + "\n".join(sequence[i:i+7] for i in range(0, len(sequence), 7)) + "\n")

    def fake_native(self, command, **kwargs):
        if command[0] == "samtools":
            return self.real_run(command, **kwargs)
        self.native_calls.append(command)
        native = Path(command[command.index("--output") + 1])
        native.mkdir(parents=True)
        rows = []
        for i, match in enumerate(re.finditer("[Nn]+", self.original)):
            start, end = match.span()
            left, right = min(3, start), min(3, len(self.original) - end)
            candidate = native / f"{i}.final.fa"
            candidate.write_text(">bridge\n" + self.original[start-left:start] + "GT" + self.original[end:end+right] + "\n")
            rows.append({"chromosome": "chr1", "gap_start": start, "gap_end": end-1,
                         "gap_len": end-start, "left_flank_len": left, "right_flank_len": right,
                         "replace_start": start-left, "replace_end": end+right-1,
                         "replace_len": end-start+left+right, "filled": True,
                         "final_sequence_file": str(candidate)})
        self.mutate(rows, native)
        gapfill.atomic_json(native / "03.gap_filling/gap_filling_results.json", {"gaps": rows})
        return subprocess.CompletedProcess(command, 0)

    def run_stage(self):
        with mock.patch.object(gapfill.subprocess, "run", side_effect=self.fake_native):
            return gapfill.run(self.root, 4)

    def test_exact_bridge_preserves_lgz_and_binds_cache(self):
        before = (self.root / "grt/q/q3.fa").read_bytes()
        report = self.run_stage()
        self.assertEqual(report["accepted_count"], 1)
        self.assertEqual((self.root / gapfill.OUTPUT).read_text(), ">chr1\nAAAGTCCC\n")
        self.assertEqual((self.root / "grt/q/q3.fa").read_bytes(), before)
        self.assertEqual((self.root / "metadata/grt_final_path.json").read_text(), json.dumps({"unchanged": True}))
        self.assertIn("--hifi", self.native_calls[0])
        self.assertEqual(self.native_calls[0][-1], str(self.reads))
        self.assertEqual(self.native_calls[0][self.native_calls[0].index("--work")+1], "1")
        self.assertEqual(self.run_stage(), report)
        self.assertEqual(len(self.native_calls), 1)
        self.reads.write_text("@r\nTGCA\n+\nIIII\n")
        self.run_stage()
        self.assertEqual(len(self.native_calls), 2)
        (self.root / gapfill.OUTPUT).write_text(">bad\nA\n")
        self.assertFalse(gapfill.validate_result(self.root)[0])
        self.run_stage()
        self.assertEqual(len(self.native_calls), 3)

    def test_no_internal_eligible_gap_skips_engine(self):
        for sequence in ("ACGT", "NNACGTNN", "AANNNCC"):
            self.fasta(sequence)
            report = self.run_stage()
            self.assertEqual(report["accepted_count"], 0)
            self.assertEqual((self.root / gapfill.OUTPUT).read_text(), f">chr1\n{sequence}\n")
        self.assertFalse(self.native_calls)

    def test_ont_type_and_final_path_invalidate_cache(self):
        self.run_stage()
        self.config["ont"] = self.config.pop("hifi")
        self.config["hifi"] = []
        gapfill.atomic_json(self.root / "metadata/degap_inputs.json", self.config)
        self.run_stage()
        self.assertIn("--ont", self.native_calls[-1])
        (self.root / "metadata/grt_final_path.json").write_text("{}")
        self.run_stage()
        self.assertEqual(len(self.native_calls), 3)

    def test_mixed_native_arguments_and_legacy_recipe_resume(self):
        ont = self.root / "ont.fq"
        ont.write_text("ONT reads")
        hifi2 = self.root / "hifi2.fq"
        hifi2.write_text("second HiFi file")
        self.config["hifi"].append(str(hifi2))
        self.config["ont"] = [str(ont)]
        gapfill.atomic_json(self.root / "metadata/degap_inputs.json", self.config)
        report = self.run_stage()
        command = self.native_calls[-1]
        self.assertEqual(command[command.index("--hifi") + 1:command.index("--ont")], [str(self.reads), str(hifi2)])
        self.assertEqual(command[command.index("--ont") + 1:], [str(ont)])
        self.assertEqual(report["reads_type"], "mixed")
        self.run_stage()
        self.assertEqual(len(self.native_calls), 1)
        ont.write_text("changed ONT reads")
        self.run_stage()
        self.assertEqual(len(self.native_calls), 2)
        # Last implementation used schema 1: preserve its explicit meaning.
        legacy = {"schema_version": 1, "purpose": gapfill.PURPOSE, "reads_type": "hifi", "reads": [str(self.reads)]}
        gapfill.atomic_json(self.root / "metadata/degap_inputs.json", legacy)
        self.assertEqual(self.run_stage()["reads_type"], "hifi")
        self.assertNotIn("--ont", self.native_calls[-1])
        self.assertEqual(gapfill.load_json(self.root / "metadata/degap_inputs.json"), legacy)

    def test_ambiguous_or_empty_typed_inputs_rejected(self):
        for config in (
            {**self.config, "ont": [str(self.reads)]},
            {**self.config, "hifi": [], "ont": []},
            {**self.config, "hifi": "not-a-list"},
            {**self.config, "hifi": ["relative.fq"]},
            {**self.config, "reads": [str(self.reads)]},
        ):
            with self.subTest(config=config), self.assertRaises(ValueError):
                gapfill.read_groups(config)

    def test_candidate_rejections_preserve_gap(self):
        def change_sequence(sequence):
            return lambda rows, native: Path(rows[0]["final_sequence_file"]).write_text(">x\n" + sequence + "\n")
        cases = [
            (change_sequence("CAAGTCCC"), "flanks_changed_or_ambiguous"),
            (change_sequence("AAANGCCC"), "ambiguous_bridge"),
            (change_sequence("AAACCC"), "no_positive_bridge"),
            (lambda rows, native: rows[0].update(filled=False), "native_unfilled"),
            (lambda rows, native: rows[0].update(replace_end=999), "invalid_coordinates"),
            (lambda rows, native: rows[0].update(final_sequence_file=str(self.reads)), "candidate_outside_attempt_or_missing"),
            (lambda rows, native: rows.append(copy.deepcopy(rows[0])), "duplicate_candidates"),
            (lambda rows, native: rows.clear(), "missing_candidate"),
        ]
        for index, (mutate, reason) in enumerate(cases):
            with self.subTest(reason=reason):
                self.mutate = mutate
                self.reads.write_text(str(index))  # distinct binding, not stale-cache reuse
                report = self.run_stage()
                self.assertEqual(report["decisions"][0]["reason"], reason)
                self.assertEqual(report["accepted_count"], 0)
                self.assertEqual((self.root / gapfill.OUTPUT).read_text(), f">chr1\n{self.original}\n")

    def test_symlink_escape_and_merged_gaps_are_not_admitted(self):
        def escape(rows, native):
            link = native / "escape.fa"
            link.symlink_to(self.reads)
            rows[0]["final_sequence_file"] = str(link)
        self.mutate = escape
        self.assertEqual(self.run_stage()["accepted_count"], 0)
        self.fasta("AAA" + "N"*20 + "ACGT" + "N"*20 + "CCC")
        def merge(rows, native):
            rows[0]["gap_end"] = rows[-1]["gap_end"]
            del rows[1:]
        self.mutate = merge
        report = self.run_stage()
        self.assertEqual([d["reason"] for d in report["decisions"]], ["native_merged_gaps_not_admitted"]*2)
        self.assertEqual((self.root / gapfill.OUTPUT).read_text(), f">chr1\n{self.original}\n")

    def test_native_failure_and_changed_inputs_do_not_publish(self):
        def failure(rows, native):
            raise subprocess.CalledProcessError(2, "native")
        self.mutate = failure
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_stage()
        self.assertFalse(gapfill.validate_result(self.root)[0])
        self.assertEqual(len(list((self.root / "degap/attempts").iterdir())), 1)
        self.mutate = lambda rows, native: self.reads.write_text("changed during engine execution")
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.run_stage()
        self.assertFalse(gapfill.validate_result(self.root)[0])

    def test_scan_chunk_boundary_and_multiple_records(self):
        self.fasta("n"*9 + "A"*5 + "N"*17 + "CC")
        path = self.root / "grt/q/q3.fa"
        with path.open("a") as out:
            out.write(">chr2\nAANNCC\n")
        with mock.patch.object(gapfill, "CHUNK", 8):
            genome = gapfill.IndexedFasta(path, self.root / "indexed.fa")
            self.assertEqual(list(genome.gaps()), [("chr1", 0, 9), ("chr1", 14, 31), ("chr2", 2, 4)])

    def test_legacy_contract_not_reinterpreted(self):
        self.config.pop("purpose")
        gapfill.atomic_json(self.root / "metadata/degap_inputs.json", self.config)
        with self.assertRaisesRegex(ValueError, "legacy"):
            self.run_stage()


class PostLgzPlanTests(unittest.TestCase):
    def test_runner_rejects_bare_exit_success_and_recognizes_valid_cache(self):
        import test_run_all_runner as fixture
        helper = fixture.RunAllRunnerTests()
        with tempfile.TemporaryDirectory() as temporary:
            root = helper.make_workspace(Path(temporary), [
                ("degap_gapfill", "echo 'DEGAP gapfill cache hit: fixture'"),
                ("downstream", "touch downstream-ran")])
            failed = helper.run_runner(root)
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse((root / "downstream-ran").exists())
            output = root / gapfill.OUTPUT
            output.parent.mkdir(parents=True)
            output.write_text(">chr1\nACGT\n")
            gapfill.atomic_json(root / gapfill.REPORT, {"input_signature": "fixture", "gap_count": 1,
                "accepted_count": 1, "decisions": [], "output_fasta": gapfill.OUTPUT})
            gapfill.atomic_json(root / gapfill.CHECKPOINT, {"schema_version": 1, "signature": "fixture",
                "artifacts": {gapfill.OUTPUT: gapfill.digest(output),
                              gapfill.REPORT: gapfill.digest(root / gapfill.REPORT)}})
            success = helper.run_runner(root)
            self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
            self.assertIn("[CACHE_HIT] [degap_gapfill]", success.stdout)
            self.assertTrue((root / "downstream-ran").exists())
            from server_report_collect import collect_unit
            self.assertEqual(collect_unit(root, "degap_gapfill", {})["summary"]["accepted_count"], 1)
            gapfill.atomic_json(root / gapfill.CHECKPOINT, {"schema_version": 1, "status": "running"})
            self.assertEqual(collect_unit(root, "degap_gapfill", {})["summary"], {"available": False})

    def test_malformed_checkpoint_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gapfill.atomic_json(root / gapfill.CHECKPOINT, {"schema_version": 1, "artifacts": []})
            self.assertFalse(gapfill.validate_result(root)[0])

    def test_environment_fails_before_work_for_missing_dependencies(self):
        with mock.patch.object(gapfill.shutil, "which", return_value=None), \
                mock.patch.object(gapfill.importlib, "import_module", side_effect=ImportError):
            with self.assertRaisesRegex(ValueError, "install.sh --check"):
                gapfill.check_environment(Path("/tmp/safe-workspace"))
        with self.assertRaisesRegex(ValueError, "shell metacharacters"):
            gapfill.check_native_paths(Path("/tmp/work space"))
        with self.assertRaisesRegex(ValueError, "shell metacharacters"):
            gapfill.check_native_paths(Path("/tmp/safe-workspace"), ["/data/reads;unsafe.fq"])

    def test_old_plan_unchanged_and_new_stage_order(self):
        old = build_unit_plan(["ds"], ["chr1"])
        new = build_unit_plan(["ds"], ["chr1"], degap_enabled=True)
        self.assertNotIn("degap_gapfill", [item.unit_id for item in old])
        mapping = {item.unit_id: item.dependencies for item in new}
        self.assertEqual(mapping["degap_gapfill"], ("grt_step3",))
        self.assertEqual(mapping["chr:chr1"], ("degap_gapfill",))

    def test_typed_reads_and_legacy_resume_parser(self):
        cwd = Path.cwd()
        grouped = server_run.parse_options(["--hifi", "a.fq", "b.fq", "--ont", "o.fq", "-t", "4"], cwd)
        repeated = server_run.parse_options(["--hifi", "a.fq", "--hifi", "b.fq", "--ont", "o.fq", "-t", "4"], cwd)
        self.assertEqual(grouped, repeated)
        self.assertEqual(grouped["--hifi"], [[str(cwd / "a.fq")], [str(cwd / "b.fq")]])
        for args in (["--hifi"], ["--ont", "--hifi", "a.fq"]):
            with self.assertRaises(server_run.RunnerError):
                server_run.parse_options(args, cwd)
        # Both historical launch formats remain parseable, not rewritten on resume.
        server_run.parse_options(["--reads", "reads.fq", "--reads-qc", "full"], cwd)
        server_run.parse_options(["--reads", "reads.fq", "--reads-type", "ont"], cwd)

    def test_lgz_qc_reads_remain_locked_but_typed_refinement_reads_can_be_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_workspace(root)
            for name in ("qc.fq", "a.fq", "b.fq", "o.fq"):
                (root / name).write_text("@r\nACGT\n+\nIIII\n")
            saved = server_run.parse_options(["--reads", "qc.fq", "--reads-type", "hifi"], root)
            hifi_ont = server_run.parse_options(["--hifi", "a.fq", "b.fq", "--ont", "o.fq"], root)
            self.assertEqual(server_run.input_identities(hifi_ont), {})
            identities = server_run.input_identities(saved)
            self.assertEqual(set(identities), {str(root / "qc.fq")})
            server_run.check_resume_options({**saved, **hifi_ont}, saved, identities)
            first = save_request(root, hifi_ont, "first")
            self.assertEqual(first["groups"], {"hifi": [str(root / "a.fq"), str(root / "b.fq")], "ont": [str(root / "o.fq")]})
            equivalent = server_run.parse_options(["--hifi", "a.fq", "--hifi", "b.fq", "--ont", "o.fq"], root)
            self.assertEqual(save_request(root, equivalent, "again")["configuration_sha256"], first["configuration_sha256"])
            replacement = server_run.parse_options(["--ont", "o.fq"], root)
            server_run.check_resume_options(replacement, saved, identities)
            new = save_request(root, replacement, "replacement")
            self.assertEqual(new["groups"], {"hifi": [], "ont": [str(root / "o.fq")]})
            self.assertNotEqual(new["configuration_sha256"], first["configuration_sha256"])
            self.assertEqual(load_request(root, "first"), first)
            changed_type = server_run.parse_options(["--reads", "qc.fq", "--reads-type", "ont"], root)
            with self.assertRaisesRegex(server_run.RunnerError, "differs"):
                server_run.check_resume_options(changed_type, saved, identities)
            (root / "qc.fq").write_text("changed LGZ QC reads")
            with self.assertRaisesRegex(server_run.RunnerError, "Input changed"):
                server_run.check_resume_options(saved, saved, identities)


if __name__ == "__main__":
    unittest.main()
