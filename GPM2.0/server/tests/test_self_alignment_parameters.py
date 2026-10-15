from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))


def load_command_writer():
    source = (TOOLS / "assign_chr_groups.py").read_text(encoding="utf-8")
    prefix, marker, _rest = source.partition(
        '\nwork_root = Path(os.environ["GPM_FAST_WORK_ROOT"])'
    )
    if not marker:
        raise AssertionError("cannot isolate assign_chr_groups function definitions")
    namespace: dict[str, object] = {}
    exec(compile(prefix, "assign_chr_groups.py", "exec"), namespace)
    return namespace


class SelfAlignmentParameterTests(unittest.TestCase):
    def test_self_thresholds_are_emitted_only_for_self_alignment(self):
        namespace = load_command_writer()
        namespace["threads"] = "8"
        write_command = namespace["write_run_command_script"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.fa"
            query = root / "query.fa"
            name_map = root / "names.tsv"
            restore = root / "restore.py"
            for path in (target, query, name_map, restore):
                path.write_text("fixture\n", encoding="utf-8")

            self_script = root / "self.sh"
            write_command(
                self_script,
                root,
                target,
                query,
                True,
                "8",
                "asm10",
                self_min_chain_score=250,
                self_minimizers=75,
                self_name_map=name_map,
                self_restore_script=restore,
            )
            self_text = self_script.read_text(encoding="utf-8")
            self.assertIn(" -X --no-hash-name -m 250 -n 75 ", self_text)
            self.assertIn('"${GPM_TASK_THREADS:-8}"', self_text)

            cross_script = root / "cross.sh"
            write_command(cross_script, root, target, query, False, "8", "asm10")
            cross_text = cross_script.read_text(encoding="utf-8")
            self.assertNotIn(" -m 250 ", cross_text)
            self.assertNotIn(" -n 75 ", cross_text)
            self.assertNotIn(" -X ", cross_text)

    def test_self_alignment_requires_both_thresholds(self):
        namespace = load_command_writer()
        namespace["threads"] = "8"
        write_command = namespace["write_run_command_script"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("target.fa", "query.fa", "names.tsv", "restore.py")]
            for path in paths:
                path.write_text("fixture\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                write_command(
                    root / "self.sh", root, paths[0], paths[1], True, "8", "asm10",
                    self_name_map=paths[2], self_restore_script=paths[3],
                )


if __name__ == "__main__":
    unittest.main()
