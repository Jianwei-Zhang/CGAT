import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]
TEST_ROOT = Path(__file__).parent
sys.path.insert(0, str(TEST_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server/tools"))

import test_grt_prepare_inputs as prepare_fixture
import test_grt_step23 as step23_fixture
from grt_prepare_inputs import read_fasta
from grt_telomere_finalize import verify_final_path


PREPARE_TOOL = REPO_ROOT / "server/tools/grt_prepare_inputs.py"
FINALIZE_TOOL = REPO_ROOT / "server/tools/grt_telomere_finalize.py"


class GrtTelomereFinalizeTests(unittest.TestCase):
    def write_executable(self, path: Path, source: str) -> Path:
        path.write_text(source, encoding="utf-8", newline="")
        path.chmod(0o755)
        return path

    def make_server(self, root: Path):
        helper = step23_fixture.GrtStep23Tests(
            "test_fixed_d0_step2_step3_interval_usage_replay_and_resume"
        )
        server = helper.make_server(root)
        support_path = server / "data/datasets/support.fa"
        support_records = read_fasta(support_path)
        support_records.extend(
            [
                ("s_tel_assigned", "TTTAGGG" * 100 + "G" * 19_300),
                ("s_tel_unplaced", "G" * 19_300 + "CCCTAAA" * 100),
            ]
        )
        prepare_fixture.write_fasta(support_path, support_records)
        locator = prepare_fixture.read_tsv(server / "metadata/source_seq_locator.tsv")
        locator.extend(
            [
                {
                    "dataset_name": "support",
                    "seq_name": name,
                    "fasta_relpath": "data/datasets/support.fa",
                }
                for name in ("s_tel_assigned", "s_tel_unplaced")
            ]
        )
        prepare_fixture.write_tsv(
            server / "metadata/source_seq_locator.tsv",
            ["dataset_name", "seq_name", "fasta_relpath"],
            locator,
        )
        assignments = prepare_fixture.read_tsv(server / "metadata/chr_assignments.tsv")
        assignments.append(
            {
                "dataset_name": "support",
                "seq_name": "s_tel_assigned",
                "seq_length_bp": 20_000,
                "assigned_chr_name": "Chr01",
                "support_bp": 20_000,
                "support_percent": "100.000",
                "anchor_start": 1,
            }
        )
        prepare_fixture.write_tsv(
            server / "metadata/chr_assignments.tsv",
            [
                "dataset_name",
                "seq_name",
                "seq_length_bp",
                "assigned_chr_name",
                "support_bp",
                "support_percent",
                "anchor_start",
            ],
            assignments,
        )
        with (server / "runs/support_vs_ref/result.paf").open(
            "a", encoding="utf-8", newline=""
        ) as handle:
            handle.write(
                "s_tel_assigned\t20000\t0\t20000\t+\tChr01\t60000\t0\t20000\t20000\t20000\t60\n"
            )
        completed = subprocess.run(
            [sys.executable, str(PREPARE_TOOL), "--server-dir", str(server)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        step23_tools = helper.make_tools(root)
        env = os.environ.copy()
        env["FAKE_GRT_MINIMAP_LOG"] = str(root / "step23_minimap.log")
        env["FAKE_GRT_MUMMER_LOG"] = str(root / "step23_mummer.log")
        step1 = helper.run_step1(server, step23_tools, env)
        self.assertEqual(step1.returncode, 0, step1.stderr)
        step23 = helper.run_step23(server, step23_tools, env)
        self.assertEqual(step23.returncode, 0, step23.stderr)
        return server

    def make_tools(self, root: Path):
        minimap = self.write_executable(
            root / "fake_tel_minimap2.py",
            r'''#!/usr/bin/env python3
import os
import sys

if '--version' in sys.argv:
    print('minimap2 fixture telomere 1')
    raise SystemExit(0)

def fasta(path):
    records = []
    name = None
    parts = []
    with open(path, encoding='utf-8') as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith('>'):
                if name is not None:
                    records.append((name, ''.join(parts)))
                name = line[1:].split()[0]
                parts = []
            elif line:
                parts.append(line)
    if name is not None:
        records.append((name, ''.join(parts)))
    return records

args = sys.argv[1:]
out = args[args.index('-o') + 1]
target_name, target = fasta(args[-2])[0]
query_name, query = fasta(args[-1])[0]
with open(os.environ['FAKE_TEL_MINIMAP_LOG'], 'a', encoding='utf-8') as handle:
    handle.write(target_name + '\n')
qlen = len(query)
tlen = len(target)
if '__5prime__' in target_name:
    qstart, qend = qlen - 15000, qlen
    tstart, tend = 0, 15000
else:
    qstart, qend = 0, 15000
    tstart, tend = tlen - 15000, tlen
line = (
    f'{query_name}\t{qlen}\t{qstart}\t{qend}\t+\t{target_name}\t{tlen}'
    f'\t{tstart}\t{tend}\t15000\t15000\t60\tcg:Z:15000M\n'
)
with open(out, 'w', encoding='utf-8', newline='') as handle:
    handle.write(line)
''',
        )
        nucmer = self.write_executable(
            root / "fake_tel_nucmer.py",
            r'''#!/usr/bin/env python3
import os
import sys

if '--version' in sys.argv:
    print('nucmer fixture telomere 1')
    raise SystemExit(0)
args = sys.argv[1:]
prefix = args[args.index('-p') + 1]
reference = args[-2]
query = args[-1]
with open(os.environ['FAKE_TEL_MUMMER_LOG'], 'a', encoding='utf-8') as handle:
    handle.write(query + '\n')
with open(prefix + '.delta', 'w', encoding='utf-8', newline='') as handle:
    handle.write(f'REFERENCE\t{reference}\nQUERY\t{query}\n')
''',
        )
        delta_filter = self.write_executable(
            root / "fake_tel_delta_filter.py",
            r'''#!/usr/bin/env python3
import sys
if '--version' in sys.argv:
    print('delta-filter fixture telomere 1')
    raise SystemExit(0)
with open(sys.argv[-1], encoding='utf-8') as handle:
    sys.stdout.write(handle.read())
''',
        )
        show_coords = self.write_executable(
            root / "fake_tel_show_coords.py",
            r'''#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

if '--version' in sys.argv:
    print('show-coords fixture telomere 1')
    raise SystemExit(0)

def fasta(path):
    records = []
    name = None
    parts = []
    with open(path, encoding='utf-8') as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith('>'):
                if name is not None:
                    records.append((name, ''.join(parts)))
                name = line[1:].split()[0]
                parts = []
            elif line:
                parts.append(line)
    if name is not None:
        records.append((name, ''.join(parts)))
    return records

values = {}
with open(sys.argv[-1], encoding='utf-8') as handle:
    for line in handle:
        key, value = line.rstrip('\n').split('\t', 1)
        values[key] = value
reference = values['REFERENCE']
query = values['QUERY']
query_name, query_sequence = fasta(query)[0]
if not query_name.startswith('Chr01__'):
    raise SystemExit(0)
with Path(reference).with_suffix('.manifest.tsv').open(encoding='utf-8', newline='') as handle:
    rows = list(csv.DictReader(handle, delimiter='\t'))
if query_name.endswith('__5prime'):
    contig = 's_tel_assigned'
    ref_start, ref_end = 5001, 20000
    query_start, query_end = 1, 15000
else:
    contig = 's_tel_unplaced'
    ref_start, ref_end = 1, 15000
    query_end = len(query_sequence)
    query_start = query_end - 14999
member = next(row for row in rows if row['contig_name'] == contig)
ref_name = member['fasta_record_name']
ref_length = len(dict(fasta(reference))[ref_name])
print('NUCMER')
print('[S1] [E1] | [S2] [E2] | [LEN 1] [LEN 2] | [% IDY] | [LEN R] [LEN Q] | [TAGS]')
print('=' * 80)
print(
    f'{ref_start} {ref_end} | {query_start} {query_end} | 15000 15000 | 99.50 | '
    f'{ref_length} {len(query_sequence)} | {ref_name} {query_name}'
)
''',
        )
        return {
            "minimap2": minimap,
            "nucmer": nucmer,
            "delta_filter": delta_filter,
            "show_coords": show_coords,
        }

    def run_finalize(self, server: Path, tools, env):
        return subprocess.run(
            [
                sys.executable,
                str(FINALIZE_TOOL),
                "--server-dir",
                str(server),
                "--minimap2",
                str(tools["minimap2"]),
                "--nucmer",
                str(tools["nucmer"]),
                "--delta-filter",
                str(tools["delta_filter"]),
                "--show-coords",
                str(tools["show_coords"]),
                "--threads",
                "2",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_assigned_and_unplaced_recovery_unresolved_and_exact_resume(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server = self.make_server(root)
            tools = self.make_tools(root)
            env = os.environ.copy()
            mummer_log = root / "tel_mummer.log"
            minimap_log = root / "tel_minimap.log"
            env["FAKE_TEL_MUMMER_LOG"] = str(mummer_log)
            env["FAKE_TEL_MINIMAP_LOG"] = str(minimap_log)
            q3 = dict(read_fasta(server / "grt/q/q3.fa"))

            completed = self.run_finalize(server, tools, env)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            stages = prepare_fixture.read_tsv(server / "metadata/grt_stage_status.tsv")
            self.assertEqual(
                [row["stage"] for row in stages],
                [
                    "donor_freeze",
                    "step1_round1",
                    "step1_filter",
                    "step1_round2",
                    "step2",
                    "step3",
                    "step4_telomere",
                    "finalize",
                ],
            )
            q4 = dict(read_fasta(server / "grt/q/q4.fa"))
            self.assertEqual(len(q4["Chr01"]), len(q3["Chr01"]) + 10_000)
            self.assertTrue(q4["Chr01"].startswith("TTTAGGG" * 100))
            self.assertTrue(q4["Chr01"].endswith("CCCTAAA" * 100))

            events = [
                json.loads(line)
                for line in (server / "metadata/grt_events.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]
            tel_events = [row for row in events if row["stage"] == "step4_telomere"]
            accepted = [row for row in tel_events if row["status"] == "accepted"]
            unresolved = [row for row in tel_events if row["status"] == "unresolved"]
            self.assertEqual(len(accepted), 2)
            self.assertEqual(len(unresolved), 2)
            self.assertEqual(
                {row["source"]["original_assignment"] for row in accepted},
                {"assigned", "unplaced"},
            )
            self.assertTrue(all(row["final_path_segment_id"] for row in accepted))
            superseded_patch = next(
                row
                for row in events
                if row["stage"] == "step2" and row["status"] == "superseded"
            )
            replacing_tel = next(
                row
                for row in accepted
                if row["event_id"] == superseded_patch["superseded_by_event_id"]
            )
            self.assertEqual(superseded_patch["final_path_segment_id"], "")
            self.assertIn(
                superseded_patch["event_id"], replacing_tel["superseded_event_ids"]
            )

            terminal_rows = prepare_fixture.read_tsv(
                server / "grt/evidence/step4_telomere/terminal_status.tsv"
            )
            self.assertEqual(
                sum(row["final_status"] == "recovered" for row in terminal_rows), 2
            )
            self.assertEqual(
                sum(row["final_status"] == "unresolved" for row in terminal_rows), 2
            )
            final_path = json.loads(
                (server / "metadata/grt_final_path.json").read_text(encoding="utf-8")
            )
            tel_segments = [
                segment
                for chromosome in final_path["chromosomes"]
                for segment in chromosome["segments"]
                if segment["kind"] == "telomere"
            ]
            self.assertEqual(len(tel_segments), 2)
            sources = {
                (row["dataset_name"], name): sequence
                for row in prepare_fixture.read_tsv(server / "metadata/datasets.tsv")
                for name, sequence in read_fasta(server / row["fasta_relpath"])
            }
            verify_final_path(final_path, q4, sources)
            evidence = prepare_fixture.read_tsv(
                server / "metadata/grt_evidence_registry.tsv"
            )
            tel_evidence = [row for row in evidence if row["stage"] == "step4_telomere"]
            self.assertTrue(
                any(row["evidence_type"] == "mummer_telomere_anchor" for row in tel_evidence)
            )
            self.assertTrue(
                any(
                    row["evidence_type"] == "minimap2_terminal_overlap_validation"
                    for row in tel_evidence
                )
            )
            for row in tel_evidence:
                self.assertEqual(
                    row["raw_artifact_sha256"],
                    prepare_fixture.sha256(server / row["raw_artifact_relpath"]),
                )

            mummer_calls = mummer_log.read_text(encoding="utf-8").splitlines()
            minimap_calls = minimap_log.read_text(encoding="utf-8").splitlines()
            q4_hash = prepare_fixture.sha256(server / "grt/q/q4.fa")
            repeated = self.run_finalize(server, tools, env)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(mummer_log.read_text(encoding="utf-8").splitlines(), mummer_calls)
            self.assertEqual(minimap_log.read_text(encoding="utf-8").splitlines(), minimap_calls)
            self.assertEqual(prepare_fixture.sha256(server / "grt/q/q4.fa"), q4_hash)

            path_file = server / "metadata/grt_final_path.json"
            path_file.write_text("{}\n", encoding="utf-8", newline="")
            repaired = self.run_finalize(server, tools, env)
            self.assertEqual(repaired.returncode, 0, repaired.stderr)
            self.assertEqual(mummer_log.read_text(encoding="utf-8").splitlines(), mummer_calls)
            verify_final_path(
                json.loads(path_file.read_text(encoding="utf-8")), q4, sources
            )

            broken = copy.deepcopy(final_path)
            broken["chromosomes"][0]["q4_length"] += 1
            with self.assertRaisesRegex(SystemExit, "does not exactly reconstruct"):
                verify_final_path(broken, q4, sources)

    def test_interrupted_step4_recovers_to_fresh_run_checksums(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)

            base_root = root / "base"
            base_root.mkdir()
            base_server = self.make_server(base_root)
            fresh_server = root / "fresh/gpm_server"
            resumed_server = root / "resumed/gpm_server"
            fresh_server.parent.mkdir()
            resumed_server.parent.mkdir()
            shutil.copytree(base_server, fresh_server)
            shutil.copytree(base_server, resumed_server)

            tools_root = root / "tools"
            tools_root.mkdir()
            tools = self.make_tools(tools_root)
            fresh_env = os.environ.copy()
            fresh_env["FAKE_TEL_MUMMER_LOG"] = str(root / "fresh_tel_mummer.log")
            fresh_env["FAKE_TEL_MINIMAP_LOG"] = str(root / "fresh_tel_minimap.log")
            fresh = self.run_finalize(fresh_server, tools, fresh_env)
            self.assertEqual(fresh.returncode, 0, fresh.stderr)

            resumed_env = os.environ.copy()
            resumed_env["FAKE_TEL_MUMMER_LOG"] = str(root / "resumed_tel_mummer.log")
            resumed_env["FAKE_TEL_MINIMAP_LOG"] = str(root / "resumed_tel_minimap.log")
            partial_evidence = resumed_server / "grt/evidence/step4_telomere"
            partial_evidence.mkdir(parents=True, exist_ok=True)
            (partial_evidence / "partial.txt").write_text(
                "interrupted\n",
                encoding="utf-8",
            )
            (resumed_server / "grt/q/q4.fa").write_text(
                ">Chr01\nPARTIAL\n",
                encoding="utf-8",
                newline="",
            )
            (resumed_server / "metadata/grt_final_path.json").write_text(
                "{\"interrupted\":true}\n",
                encoding="utf-8",
                newline="",
            )

            resumed = self.run_finalize(resumed_server, tools, resumed_env)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertFalse((partial_evidence / "partial.txt").exists())

            for q_version in ("q0", "q0r1", "q0f", "q1", "q2", "q3", "q4"):
                self.assertEqual(
                    prepare_fixture.sha256(fresh_server / f"grt/q/{q_version}.fa"),
                    prepare_fixture.sha256(resumed_server / f"grt/q/{q_version}.fa"),
                    q_version,
                )
            for relpath in (
                "metadata/grt_events.jsonl",
                "metadata/grt_donor_usage.tsv",
                "metadata/grt_final_path.json",
            ):
                self.assertEqual(
                    prepare_fixture.sha256(fresh_server / relpath),
                    prepare_fixture.sha256(resumed_server / relpath),
                    relpath,
                )


if __name__ == "__main__":
    unittest.main()
