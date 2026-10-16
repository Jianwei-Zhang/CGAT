from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))


def load_generator():
    source = (TOOLS / "assign_chr_groups.py").read_text(encoding="utf-8")
    prefix, marker, _rest = source.partition(
        '\nwork_root = Path(os.environ["GPM_FAST_WORK_ROOT"])'
    )
    if not marker:
        raise AssertionError("cannot isolate assign_chr_groups function definitions")
    namespace: dict[str, object] = {}
    exec(compile(prefix, "assign_chr_groups.py", "exec"), namespace)
    namespace["SELF_BATCH_BASES"] = 20
    return namespace


class SelfAlignmentBatchTests(unittest.TestCase):
    def test_generated_batches_match_unbatched_and_resume_independently(self):
        namespace = load_generator()
        namespace["threads"] = "4"
        write_batches = namespace["write_self_batch_scripts"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = root / "operation"
            run_dir.mkdir()
            target = run_dir / "self_target.fa"
            query = run_dir / "self_query.fa"
            name_map = run_dir / "self_name_map.tsv"
            restore = run_dir / "restore_self_paf.py"
            target.write_text(
                ">gpm_pair_000000001a\nACGTACGTACGTACGTACGTACGT\n"
                ">gpm_pair_000000002a\nTTTTACGTACGTACGTAAAAACGT\n"
                ">gpm_pair_000000003a\nGGGGACGTACGTACGTCCCCACGT\n",
                encoding="utf-8",
            )
            query.write_text(target.read_text().replace("a\n", "b\n"), encoding="utf-8")
            name_map.write_text(
                "gpm_pair_000000001a\tone\n"
                "gpm_pair_000000001b\tone\n"
                "gpm_pair_000000002a\ttwo\n"
                "gpm_pair_000000002b\ttwo\n"
                "gpm_pair_000000003a\tthree\n"
                "gpm_pair_000000003b\tthree\n",
                encoding="utf-8",
            )
            restore.write_text(
                "import sys\nfrom pathlib import Path\n"
                "m=dict(x.split(b'\\t',1) for x in Path(sys.argv[1]).read_bytes().splitlines())\n"
                "for line in sys.stdin.buffer:\n"
                " f=line.rstrip(b'\\n').split(b'\\t'); f[0]=m[f[0]]; f[5]=m[f[5]]; "
                "sys.stdout.buffer.write(b'\\t'.join(f)+b'\\n')\n",
                encoding="utf-8",
            )
            _master, tasks = write_batches(
                run_dir,
                target,
                query,
                name_map,
                restore,
                TOOLS / "self_alignment_batches.py",
                threads="4",
                minimap_preset="asm10",
                self_min_chain_score=10,
                self_minimizers=1,
            )
            self.assertEqual(len(tasks), 3)
            environment = {**os.environ, "GPM_TASK_THREADS": "2"}
            for command, *_rest in tasks:
                subprocess.run(["bash", str(command)], check=True, env=environment,
                               capture_output=True, text=True)

            baseline_raw = run_dir / "baseline.raw.paf"
            with baseline_raw.open("wb") as output:
                subprocess.run(
                    ["minimap2", "-c", "-x", "asm10", "-X", "--no-hash-name",
                     "-m", "10", "-n", "1", "-t", "2", str(target), str(query)],
                    check=True, stdout=output, stderr=subprocess.DEVNULL,
                )
            baseline = subprocess.run(
                [sys.executable, str(restore), str(name_map)],
                check=True, input=baseline_raw.read_bytes(), capture_output=True,
            ).stdout
            self.assertEqual((run_dir / "result.paf").read_bytes(), baseline)

            first_dir = tasks[0][0].parent
            (first_dir / "result.paf").write_text("corrupt\n", encoding="utf-8")
            rerun = subprocess.run(
                ["bash", str(tasks[0][0])], check=True, env=environment,
                capture_output=True, text=True,
            )
            self.assertIn("SELF_BATCH_COMMITTED", rerun.stdout)
            self.assertEqual((run_dir / "result.paf").read_bytes(), baseline)
            cached = subprocess.run(
                ["bash", str(tasks[0][0])], check=True, env=environment,
                capture_output=True, text=True,
            )
            self.assertIn("SELF_BATCH_CACHE_HIT", cached.stdout)


if __name__ == "__main__":
    unittest.main()
