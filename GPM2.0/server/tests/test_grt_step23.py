import json
import os
import re
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
import test_grt_step1 as step1_fixture
from grt_prepare_inputs import read_fasta
from grt_step23 import (
    parse_mummer_coords,
    project_interval_after_refills,
    reject_candidates_spanning_other_gaps,
)


PREPARE_TOOL = REPO_ROOT / "server/tools/grt_prepare_inputs.py"
STEP1_TOOL = REPO_ROOT / "server/tools/grt_step1.py"
STEP23_TOOL = REPO_ROOT / "server/tools/grt_step23.py"


class GrtStep23Tests(unittest.TestCase):
    def make_server(self, root: Path) -> Path:
        server = step1_fixture.GrtStep1Tests(
            "test_two_round_cache_global_interval_ledger_and_resume"
        ).make_server(root)
        support_path = server / "data/datasets/support.fa"
        prepare_fixture.write_fasta(
            support_path,
            [
                ("s_assigned", "ACGT" * 12_500),
                ("s_unplaced", "ACGT" * 12_500),
                ("s_tel_short", "TTTAGGG" * 80),
            ],
        )
        completed = subprocess.run(
            [sys.executable, str(PREPARE_TOOL), "--server-dir", str(server)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return server

    def write_executable(self, path: Path, source: str) -> Path:
        path.write_text(source, encoding="utf-8", newline="")
        path.chmod(0o755)
        return path

    def make_tools(self, root: Path) -> dict[str, Path]:
        minimap = self.write_executable(
            root / "fake_minimap2.py",
            r'''#!/usr/bin/env python3
import csv
import os
import re
import sys
from pathlib import Path

if '--version' in sys.argv:
    print('minimap2 fixture step23 1')
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
target_path = args[-2]
query_path = args[-1]
targets = fasta(target_path)
queries = fasta(query_path)
lines = []
stage = 'step1'
if queries and queries[0][0].startswith('validate__'):
    stage = 'step2_validation'
elif 'step3_refill' in query_path:
    stage = 'step3_refill'
with open(os.environ['FAKE_GRT_MINIMAP_LOG'], 'a', encoding='utf-8') as handle:
    handle.write(stage + '\n')

if stage == 'step2_validation' and queries:
    target_name, target_sequence = targets[0]
    gap = re.search(r'N{100,}', target_sequence)
    if gap:
        for name, sequence in queries:
            side = name.rsplit('__', 1)[-1]
            qlen = len(sequence)
            if side == 'L':
                start = gap.start() - qlen
                end = gap.start()
            else:
                start = gap.end()
                end = gap.end() + qlen
            if 0 <= start < end <= len(target_sequence):
                lines.append(
                    f'{name}\t{qlen}\t0\t{qlen}\t+\t{target_name}\t{len(target_sequence)}'
                    f'\t{start}\t{end}\t{qlen}\t{qlen}\t60\tcg:Z:{qlen}M'
                )
elif stage == 'step3_refill' and queries:
    manifest = Path(target_path).with_suffix('.manifest.tsv')
    with manifest.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle, delimiter='\t'))
    target_name = next(row['fasta_record_name'] for row in rows if row['contig_name'] == 's_unplaced')
    target_length = dict(targets)[target_name].__len__()
    for name, sequence in queries[:2]:
        side = name.rsplit('__', 1)[-1]
        qlen = len(sequence)
        start = 30000 - qlen if side == 'L' else 30200
        end = 30000 if side == 'L' else 30200 + qlen
        lines.append(
            f'{name}\t{qlen}\t0\t{qlen}\t+\t{target_name}\t{target_length}'
            f'\t{start}\t{end}\t{qlen}\t{qlen}\t60\tcg:Z:{qlen}M'
        )

with open(out, 'w', encoding='utf-8', newline='') as handle:
    if lines:
        handle.write('\n'.join(lines) + '\n')
''',
        )
        nucmer = self.write_executable(
            root / "fake_nucmer.py",
            r'''#!/usr/bin/env python3
import hashlib
import os
import sys

if '--version' in sys.argv:
    print('nucmer fixture step23 1')
    raise SystemExit(0)
args = sys.argv[1:]
prefix = args[args.index('-p') + 1]
reference = args[-2]
query = args[-1]
stage = 'step3' if '/step3/' in query else 'step2'
with open(query, 'rb') as handle:
    query_hash = hashlib.sha256(handle.read()).hexdigest()
with open(os.environ['FAKE_GRT_MUMMER_LOG'], 'a', encoding='utf-8') as handle:
    handle.write(f'{stage}\t{query_hash}\n')
with open(prefix + '.delta', 'w', encoding='utf-8', newline='') as handle:
    handle.write(f'REFERENCE\t{reference}\nQUERY\t{query}\nSTAGE\t{stage}\n')
''',
        )
        delta_filter = self.write_executable(
            root / "fake_delta_filter.py",
            r'''#!/usr/bin/env python3
import sys
if '--version' in sys.argv:
    print('delta-filter fixture step23 1')
    raise SystemExit(0)
with open(sys.argv[-1], encoding='utf-8') as handle:
    sys.stdout.write(handle.read())
''',
        )
        show_coords = self.write_executable(
            root / "fake_show_coords.py",
            r'''#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path

if '--version' in sys.argv:
    print('show-coords fixture step23 1')
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
stage = values['STAGE']
query_name, query_sequence = fasta(query)[0]
gap = re.search(r'N{100,}', query_sequence)
if not gap:
    raise SystemExit(0)
manifest = Path(reference).with_suffix('.manifest.tsv')
with manifest.open(encoding='utf-8', newline='') as handle:
    rows = list(csv.DictReader(handle, delimiter='\t'))
ref_name = next(row['fasta_record_name'] for row in rows if row['contig_name'] == 's_unplaced')
ref_length = len(dict(fasta(reference))[ref_name])
query_length = len(query_sequence)
print(f'{reference} {query}')
print('NUCMER')
print('[S1] [E1] | [S2] [E2] | [LEN 1] [LEN 2] | [% IDY] | [LEN R] [LEN Q] | [TAGS]')
print('=' * 80)
if stage == 'step2':
    left_end = gap.start()
    left_start = left_end - 9999
    right_start = gap.end() + 1
    right_end = right_start + 9999
    if left_start >= 1 and right_end <= query_length:
        print(f'1 10000 | {left_start} {left_end} | 10000 10000 | 99.00 | {ref_length} {query_length} | {ref_name} {query_name}')
        print(f'10201 20200 | {right_start} {right_end} | 10000 10000 | 99.00 | {ref_length} {query_length} | {ref_name} {query_name}')
else:
    query_start = max(1, gap.start() - 4999)
    query_end = min(query_length, query_start + 9999)
    query_start = query_end - 9999
    if query_start >= 1 and query_start <= gap.start() + 1 <= query_end:
        print(f'35001 45000 | {query_start} {query_end} | 10000 10000 | 98.00 | {ref_length} {query_length} | {ref_name} {query_name}')
''',
        )
        return {
            "minimap2": minimap,
            "nucmer": nucmer,
            "delta_filter": delta_filter,
            "show_coords": show_coords,
        }

    def run_step1(self, server: Path, tools: dict[str, Path], env: dict[str, str]):
        return subprocess.run(
            [
                sys.executable,
                str(STEP1_TOOL),
                "--server-dir",
                str(server),
                "--minimap2",
                str(tools["minimap2"]),
                "--threads",
                "2",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def run_step23(
        self,
        server: Path,
        tools: dict[str, Path],
        env: dict[str, str],
        threads: int = 2,
    ):
        return subprocess.run(
            [
                sys.executable,
                str(STEP23_TOOL),
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
                str(threads),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_fixed_d0_step2_step3_interval_usage_replay_and_resume(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server = self.make_server(root)
            tools = self.make_tools(root)
            minimap_log = root / "minimap.log"
            mummer_log = root / "mummer.log"
            env = os.environ.copy()
            env["FAKE_GRT_MINIMAP_LOG"] = str(minimap_log)
            env["FAKE_GRT_MUMMER_LOG"] = str(mummer_log)

            step1 = self.run_step1(server, tools, env)
            self.assertEqual(step1.returncode, 0, step1.stderr)
            self.assertNotIn("step2_validation", minimap_log.read_text(encoding="utf-8"))
            self.assertEqual(len(re.findall(r"N{100,}", dict(read_fasta(server / "grt/q/q1.fa"))["Chr01"])), 2)

            completed = self.run_step23(server, tools, env)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                [line.split("\t")[0] for line in mummer_log.read_text(encoding="utf-8").splitlines()],
                ["step2", "step3"],
            )
            mummer_query_hashes = [
                line.split("\t")[1]
                for line in mummer_log.read_text(encoding="utf-8").splitlines()
            ]
            self.assertNotEqual(mummer_query_hashes[0], mummer_query_hashes[1])
            self.assertEqual(
                minimap_log.read_text(encoding="utf-8").splitlines().count("step2_validation"),
                1,
            )
            self.assertEqual(
                minimap_log.read_text(encoding="utf-8").splitlines().count("step3_refill"),
                1,
            )

            recipe = prepare_fixture.read_tsv(server / "metadata/grt_recipe.tsv")[0]
            donor_hash = next(
                row["fasta_sha256"]
                for row in prepare_fixture.read_tsv(server / "metadata/grt_donor_sets.tsv")
                if row["donor_set_id"] == recipe["donor_set_id"]
            )
            stages = prepare_fixture.read_tsv(server / "metadata/grt_stage_status.tsv")
            self.assertEqual(
                [row["stage"] for row in stages],
                ["donor_freeze", "step1_round1", "step1_filter", "step1_round2", "step2", "step3"],
            )
            self.assertEqual({row["donor_set_id"] for row in stages}, {recipe["donor_set_id"]})
            self.assertEqual(stages[-2]["q_input_sha256"], prepare_fixture.sha256(server / "grt/q/q1.fa"))
            self.assertEqual(stages[-1]["q_input_sha256"], prepare_fixture.sha256(server / "grt/q/q2.fa"))

            evidence = prepare_fixture.read_tsv(server / "metadata/grt_evidence_registry.tsv")
            mummer_evidence = [
                row
                for row in evidence
                if row["evidence_type"] in {"mummer_gap_anchor_pair", "mummer_structural_correction"}
            ]
            self.assertEqual({row["q_version"] for row in mummer_evidence}, {"q1", "q2"})
            self.assertEqual({row["target_sha256"] for row in mummer_evidence}, {donor_hash})
            self.assertTrue(all(row["coordinate_system"] == "mummer_1_based_closed" for row in mummer_evidence))

            events = [
                json.loads(line)
                for line in (server / "metadata/grt_events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            accepted_patch = next(
                event for event in events if event["stage"] == "step2" and event["status"] == "accepted"
            )
            accepted_refill = next(
                event
                for event in events
                if event["stage"] == "step3" and event["action"] == "refill" and event["status"] == "accepted"
            )
            superseded_correction = next(
                event
                for event in events
                if event["stage"] == "step3" and event["action"] == "replace" and event["status"] == "superseded"
            )
            self.assertEqual(accepted_patch["source"]["contig"], "s_unplaced")
            self.assertEqual(accepted_refill["source"]["contig"], "s_unplaced")
            self.assertEqual(accepted_refill["object_id"], accepted_refill["origin_q2_object_id"])
            self.assertNotEqual(accepted_refill["corrected_object_id"], accepted_refill["object_id"])
            self.assertEqual(superseded_correction["superseded_by_event_id"], accepted_refill["event_id"])
            self.assertIn(superseded_correction["event_id"], accepted_refill["superseded_event_ids"])

            refill_evidence = next(
                row for row in evidence if row["evidence_type"] == "corrected_gap_flank_refill"
            )
            self.assertEqual(
                (int(refill_evidence["target_start"]), int(refill_evidence["target_end"])),
                (accepted_refill["q_before"]["start"], accepted_refill["q_before"]["end"]),
            )

            usage = prepare_fixture.read_tsv(server / "metadata/grt_donor_usage.tsv")
            accepted_source_rows = [
                row
                for row in usage
                if row["source_contig"] == "s_unplaced" and row["status"] in {"consumed", "superseded"}
            ]
            intervals = sorted((int(row["source_start"]), int(row["source_end"])) for row in accepted_source_rows)
            for left, right in zip(intervals, intervals[1:]):
                self.assertLess(left[1], right[0])
            self.assertFalse(
                any(
                    row["source_contig"] == "s_unplaced"
                    for row in usage
                    if row["stage"].startswith("step1_")
                )
            )

            q3 = dict(read_fasta(server / "grt/q/q3.fa"))
            self.assertFalse(re.search(r"N{100,}", q3["Chr01"]))
            q2_hash = prepare_fixture.sha256(server / "grt/q/q2.fa")
            q3_hash = prepare_fixture.sha256(server / "grt/q/q3.fa")
            mummer_calls = mummer_log.read_text(encoding="utf-8").splitlines()
            minimap_calls = minimap_log.read_text(encoding="utf-8").splitlines()
            repeated = self.run_step23(server, tools, env)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(mummer_log.read_text(encoding="utf-8").splitlines(), mummer_calls)
            self.assertEqual(minimap_log.read_text(encoding="utf-8").splitlines(), minimap_calls)
            self.assertEqual(prepare_fixture.sha256(server / "grt/q/q3.fa"), q3_hash)

            with (server / "grt/q/q2.fa").open("a", encoding="utf-8", newline="") as handle:
                handle.write("# injected output hash mismatch\n")
            output_invalidated = self.run_step23(server, tools, env)
            self.assertEqual(output_invalidated.returncode, 0, output_invalidated.stderr)
            self.assertIn("GRT step2 complete", output_invalidated.stdout)
            self.assertEqual(len(mummer_log.read_text(encoding="utf-8").splitlines()), 2)
            self.assertEqual(prepare_fixture.sha256(server / "grt/q/q2.fa"), q2_hash)
            self.assertEqual(prepare_fixture.sha256(server / "grt/q/q3.fa"), q3_hash)

            parameter_invalidated = self.run_step23(server, tools, env, threads=3)
            self.assertEqual(parameter_invalidated.returncode, 0, parameter_invalidated.stderr)
            self.assertEqual(len(mummer_log.read_text(encoding="utf-8").splitlines()), 4)
            self.assertEqual(prepare_fixture.sha256(server / "grt/q/q3.fa"), q3_hash)

            nucmer_path = tools["nucmer"]
            nucmer_path.write_text(
                nucmer_path.read_text(encoding="utf-8").replace(
                    "nucmer fixture step23 1",
                    "nucmer fixture step23 2",
                    1,
                ),
                encoding="utf-8",
                newline="",
            )
            tool_invalidated = self.run_step23(server, tools, env, threads=3)
            self.assertEqual(tool_invalidated.returncode, 0, tool_invalidated.stderr)
            self.assertEqual(len(mummer_log.read_text(encoding="utf-8").splitlines()), 6)
            self.assertEqual(prepare_fixture.sha256(server / "grt/q/q3.fa"), q3_hash)

    def test_coords_parser_uses_real_show_coords_columns(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "result.coords"
            path.write_text(
                "NUCMER\n"
                "[S1] [E1] | [S2] [E2] | [LEN 1] [LEN 2] | [% IDY] | [LEN R] [LEN Q] | [TAGS]\n"
                "1 10000 | 20000 10001 | 10000 10000 | 98.75 | 50000 60000 | donor Chr01\n",
                encoding="utf-8",
            )
            rows = parse_mummer_coords(
                path,
                "step3",
                "Chr01",
                60000,
                {
                    "donor": {
                        "member_id": "member-1",
                        "dataset_name": "support",
                        "contig_name": "unplaced",
                    }
                },
                {"donor": 50000},
            )
            self.assertEqual(len(rows), 1)
            self.assertAlmostEqual(rows[0]["identity"], 0.9875)
            self.assertEqual(rows[0]["orientation"], "-")
            self.assertEqual((rows[0]["query_min"], rows[0]["query_max"]), (10001, 20000))

    def test_final_q3_projection_accounts_for_earlier_refill_length_change(self):
        refill = {
            "event_id": "refill-1",
            "chr": "Chr01",
            "status": "accepted",
            "edit": {"input_start": 100, "input_end": 199},
            "q_after": {"start": 100, "end": 149},
        }
        self.assertEqual(
            project_interval_after_refills("Chr01", 300, 399, [refill]),
            (250, 349),
        )
        self.assertEqual(
            project_interval_after_refills("Chr01", 1, 99, [refill]),
            (1, 99),
        )
        with self.assertRaisesRegex(SystemExit, "overlapping refill"):
            project_interval_after_refills("Chr01", 150, 250, [refill])

    def test_candidate_cannot_silently_consume_a_second_gap(self):
        candidates = [
            {
                "candidate_id": "candidate-1",
                "stage": "step2",
                "chr": "Chr01",
                "object_id": "gap-1",
                "input_start": 100,
                "input_end": 400,
                "outcome": "candidate",
                "left_line": 1,
                "right_line": 2,
            }
        ]
        gaps = [
            {"chr": "Chr01", "object_id": "gap-1", "start0": 149, "end0": 249},
            {"chr": "Chr01", "object_id": "gap-2", "start0": 299, "end0": 399},
        ]
        rejections = []
        reject_candidates_spanning_other_gaps(candidates, gaps, rejections)
        self.assertEqual(candidates[0]["outcome"], "rejected")
        self.assertEqual(
            candidates[0]["reason"],
            "target_interval_spans_other_gap:gap-2",
        )
        self.assertEqual(rejections[0]["candidate_id"], "candidate-1")


if __name__ == "__main__":
    unittest.main()
