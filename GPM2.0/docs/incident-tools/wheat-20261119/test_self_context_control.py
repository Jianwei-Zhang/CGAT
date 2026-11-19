import copy
from pathlib import Path
import tempfile
import unittest

import self_context_control as control


class ContextControlTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.batch = {"entries": [{"name": "q", "length": 30_000_000}], "query": "/whole.fa", "key": "key"}
        self.manifest = {"version": 1, "preset": "asm10", "min_chain_score": 200,
                         "minimizers": 100, "cache": "/cache"}
        self.native = ["minimap2", "-c", "-x", "asm10", "-X", "--no-hash-name", "-m", "200",
                       "-n", "100", "-t", "1", "/cache/target.mmi", "/whole.fa"]
        self.candidate = {"status": "candidate_complete_not_compared_not_adopted", "candidate_adopted": False,
            "analysis_workspace_modified": False, "mapping": {"returncode": 0}, "native_batch_key": "key",
            "native_command": self.native,
            "command": control.pilot.candidate_command(self.manifest, self.batch, self.native),
            "driver_sha256": control.pilot.digest(Path(control.pilot.__file__)), "inputs": {"source": "bound"},
            "outputs": {"candidate": "bound"}}
        self.probe = {"status": "masked_native_vs_complete_candidate_compared_not_adopted",
            "mapping": {"returncode": 0}, "candidate_adopted": False, "analysis_workspace_modified": False,
            "query_name": "q", "query_length": 30_000_000, "window_bases": 1_000_000,
            "windows_0based_half_open": [[0, 1_000_000], [14_500_000, 15_500_000], [29_000_000, 30_000_000]],
            "native_command": self.native[:-1] + [str(self.root / "masked-query.fa")],
            "source_inputs": self.candidate["inputs"], "candidate_outputs": self.candidate["outputs"],
            "masked_query": {str(self.root / "masked-query.fa"): "bound"},
            "outputs": {str(self.root / n): "bound" for n in ("raw.paf", "stderr.log")}}

    def test_complete_source_contract(self):
        self.assertEqual(control.source_contract(self.probe, self.candidate, self.manifest, self.batch, self.root),
                         self.root / "masked-query.fa")

    def test_variant_only_changes_seed_filter(self):
        for fraction in ("0.005", "0.002", "0.001"):
            command = control.variant_command(self.probe["native_command"], fraction)
            self.assertEqual(command[-4:-2], ["-f", fraction])
            self.assertEqual(command[:-4] + command[-2:], self.probe["native_command"])
        self.assertEqual(self.native[-1], "/whole.fa")

    def test_unbounded_or_repeated_filter_rejected(self):
        with self.assertRaises(ValueError): control.variant_command(self.native, "0.1")
        with self.assertRaises(ValueError): control.variant_command(self.native + ["-f", "0.001"], "0.005")

    def test_failed_or_mutating_source_rejected(self):
        for key, value in (("status", "running"), ("mapping", {"returncode": 124}),
                           ("candidate_adopted", True), ("analysis_workspace_modified", True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                control.source_contract({**self.probe, key: value}, self.candidate, self.manifest, self.batch, self.root)

    def test_changed_windows_inputs_names_or_commands_rejected(self):
        changes = [("query_name", "other"), ("query_length", 1), ("window_bases", 5_000_000),
                   ("windows_0based_half_open", [[0, 1000]]), ("source_inputs", {}),
                   ("candidate_outputs", {}), ("masked_query", {}), ("outputs", {}),
                   ("native_command", self.native)]
        for key, value in changes:
            with self.subTest(key=key), self.assertRaises(ValueError):
                control.source_contract({**self.probe, key: value}, self.candidate, self.manifest, self.batch, self.root)

    def test_changed_full_candidate_not_reused(self):
        candidate = copy.deepcopy(self.candidate); candidate["command"].remove("-X")
        with self.assertRaises(ValueError):
            control.source_contract(self.probe, candidate, self.manifest, self.batch, self.root)

    def rows(self):
        # Primary short, secondary long high identity, and secondary low identity.
        return ["q\t30000000\t0\t1000\t+\tt\t40000000\t0\t1000\t990\t1000\t0\ttp:A:P\tcg:Z:1000M\n",
                "q\t30000000\t2000\t12000\t+\tt\t40000000\t2000\t12000\t9900\t10000\t0\ttp:A:S\tcg:Z:10000M\n",
                "q\t30000000\t20000\t30000\t+\tt\t40000000\t20000\t30000\t9000\t10000\t0\ttp:A:S\tcg:Z:10000M\n"]

    def test_strata_do_not_conflate_primary_with_long_or_high_identity(self):
        source = self.root / "input.paf"; source.write_text("".join(self.rows()))
        for stratum, index in (("tp_P", 0), ("long_high_identity", 1)):
            output = self.root / stratum
            control.write_stratum(source, output, stratum)
            self.assertEqual(output.read_text(), self.rows()[index])
        self.assertEqual(source.read_text(), "".join(self.rows()))

    def test_comparisons_retain_all_hits_and_label_filters(self):
        source = self.root / "input.paf"; source.write_text("".join(self.rows()))
        result = control.comparisons(source, source, {"q": [[0, 1_000_000]]}, self.root / "comparison")
        self.assertEqual(result["all_hits"]["baseline"]["paf_rows"], 3)
        self.assertEqual(result["tp_P"]["baseline"]["paf_rows"], 1)
        self.assertEqual(result["long_high_identity"]["baseline"]["paf_rows"], 1)
        self.assertTrue(result["tp_P"]["primary_or_mapq_filter_applied"])
        self.assertFalse(result["long_high_identity"]["primary_or_mapq_filter_applied"])
        for row in result.values():
            self.assertEqual(row["position_support"]["100"]["missing_baseline_placements"], 0)

    def test_derived_output_cannot_be_overwritten(self):
        source = self.root / "input.paf"; source.write_text("".join(self.rows()))
        with self.assertRaises(FileExistsError): control.write_stratum(source, source, "tp_P")
        self.assertEqual(source.read_text(), "".join(self.rows()))


if __name__ == "__main__":
    unittest.main()
