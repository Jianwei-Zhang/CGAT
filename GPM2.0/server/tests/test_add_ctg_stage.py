import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]
MODULE_PATH = REPO_ROOT / "server" / "tools" / "add_ctg_stage.py"

SPEC = importlib.util.spec_from_file_location("add_ctg_stage", MODULE_PATH)
ADD_CTG_STAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADD_CTG_STAGE)


class AddCtgStageTests(unittest.TestCase):
    def test_generated_minimap_and_winnowmap_commands_request_cigar(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            command = root / "command.sh"
            for engine in ["minimap2", "winnowmap"]:
                for self_mode in [False, True]:
                    ADD_CTG_STAGE.write_alignment_command(
                        command, root, root / "target.fa", root / "query.fa",
                        {"alignment_engine": engine}, self_mode=self_mode,
                    )
                    line = next(line for line in command.read_text().splitlines() if line.startswith(engine + " "))
                    self.assertIn(" -c ", line)
                    self.assertEqual(" -X " in line, self_mode)

    def parse_assignment(self, paf_text):
        with tempfile.TemporaryDirectory() as temporary_dir:
            server_dir = Path(temporary_dir) / "gpm_server"
            paf_path = server_dir / "runs/add_ctg/test_ctg_vs_ref/result.paf"
            paf_path.parent.mkdir(parents=True)
            paf_path.write_text(paf_text, encoding="utf-8", newline="")
            return ADD_CTG_STAGE.parse_ref_paf_assignment(
                server_dir,
                "test_ctg",
                "Chr01",
                "A" * 2_000,
            )

    def test_negative_block_majority_sets_reverse_source_orientation(self):
        assignment = self.parse_assignment(
            "test_ctg\t2000\t0\t500\t+\tChr01\t10000\t100\t600\t500\t500\t60\n"
            "test_ctg\t2000\t500\t1100\t-\tChr01\t10000\t1000\t1600\t600\t600\t60\n"
        )

        self.assertEqual(assignment["source_orientation"], "-")
        self.assertEqual(assignment["orientation_source"], "ref_alignment")

    def test_equal_strand_block_totals_resolve_to_forward_orientation(self):
        assignment = self.parse_assignment(
            "test_ctg\t2000\t0\t500\t+\tChr01\t10000\t100\t600\t500\t500\t60\n"
            "test_ctg\t2000\t500\t1000\t-\tChr01\t10000\t1000\t1500\t500\t500\t60\n"
        )

        self.assertEqual(assignment["source_orientation"], "+")
        self.assertEqual(assignment["orientation_source"], "ref_alignment")


if __name__ == "__main__":
    unittest.main()
