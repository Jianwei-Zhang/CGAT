import json
import os
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
from grt_step1 import (
    apply_filter,
    reconcile_filtered_round1_events,
    replay_filter_records,
)


PREPARE_TOOL = REPO_ROOT / "server/tools/grt_prepare_inputs.py"
STEP1_TOOL = REPO_ROOT / "server/tools/grt_step1.py"


class GrtStep1Tests(unittest.TestCase):
    def make_server(self, root: Path) -> Path:
        helper = prepare_fixture.GrtPrepareInputsTests(
            "test_no_reads_builds_traceable_q0_and_frozen_global_donors"
        )
        server = helper.make_server(root)
        metadata = server / "metadata"
        primary_records = [
            ("p_cover", "A" * 12_000),
            ("p_redundant", "C" * 11_000),
            ("p_partial", "G" * 12_000),
            ("p_third", "T" * 12_000),
            ("p_reverse", "A" * 6_000 + "C" * 6_000),
        ]
        support_records = [
            ("s_assigned", ("ACGT" * 12_500)),
            ("s_unplaced", "AC" * 6_500),
            ("s_tel_short", "TTTAGGG" * 80),
        ]
        prepare_fixture.write_fasta(
            server / "data/reference/ref.fa",
            [("Chr01", "A" * 60_000), ("Chr02", "C" * 60_000)],
        )
        prepare_fixture.write_fasta(server / "data/datasets/primary.fa", primary_records)
        prepare_fixture.write_fasta(server / "data/datasets/support.fa", support_records)
        assignments = [
            ("p_cover", 12_000, "Chr01", 12_000, 1),
            ("p_redundant", 11_000, "Chr01", 11_000, 101),
            ("p_partial", 12_000, "Chr01", 12_000, 20_001),
            ("p_third", 12_000, "Chr01", 12_000, 40_001),
            ("p_reverse", 12_000, "Chr02", 12_000, 100),
        ]
        prepare_fixture.write_tsv(
            metadata / "chr_assignments.tsv",
            [
                "dataset_name",
                "seq_name",
                "seq_length_bp",
                "assigned_chr_name",
                "support_bp",
                "support_percent",
                "anchor_start",
            ],
            [
                {
                    "dataset_name": "primary",
                    "seq_name": name,
                    "seq_length_bp": length,
                    "assigned_chr_name": chromosome,
                    "support_bp": support,
                    "support_percent": "100.000",
                    "anchor_start": anchor,
                }
                for name, length, chromosome, support, anchor in assignments
            ],
        )
        prepare_fixture.write_tsv(
            metadata / "track_member_orders.tsv",
            ["target_track", "target_chr", "member_dataset", "member_ctg", "member_order"],
            [
                {
                    "target_track": "primary",
                    "target_chr": chromosome,
                    "member_dataset": "primary",
                    "member_ctg": name,
                    "member_order": index,
                }
                for index, (name, _length, chromosome, _support, _anchor) in enumerate(
                    assignments, start=1
                )
            ],
        )
        prepare_fixture.write_tsv(
            metadata / "source_seq_locator.tsv",
            ["dataset_name", "seq_name", "fasta_relpath"],
            [
                {
                    "dataset_name": dataset,
                    "seq_name": name,
                    "fasta_relpath": f"data/datasets/{dataset}.fa",
                }
                for dataset, records in (("primary", primary_records), ("support", support_records))
                for name, _sequence in records
            ],
        )
        (server / "runs/primary_vs_ref/result.paf").write_text(
            "\n".join(
                [
                    "p_cover\t12000\t0\t12000\t+\tChr01\t60000\t0\t12000\t12000\t12000\t60",
                    "p_redundant\t11000\t0\t11000\t+\tChr01\t60000\t100\t11100\t11000\t11000\t60",
                    "p_partial\t12000\t0\t12000\t+\tChr01\t60000\t20000\t32000\t12000\t12000\t60",
                    "p_third\t12000\t0\t12000\t+\tChr01\t60000\t40000\t52000\t12000\t12000\t60",
                    "p_reverse\t12000\t0\t12000\t-\tChr02\t60000\t99\t12099\t12000\t12000\t60",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (server / "runs/support_vs_ref/result.paf").write_text(
            "s_assigned\t50000\t0\t50000\t+\tChr01\t60000\t0\t50000\t50000\t50000\t60\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [sys.executable, str(PREPARE_TOOL), "--server-dir", str(server)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return server

    def make_minimap(self, root: Path) -> tuple[Path, Path]:
        executable = root / "fake_minimap2.py"
        log = root / "minimap_calls.log"
        executable.write_text(
            """#!/usr/bin/env python3
import os
import sys

if '--version' in sys.argv:
    print('minimap2 fixture step1 1')
    raise SystemExit(0)

args = sys.argv[1:]
out = args[args.index('-o') + 1]
target = args[-2]
query = args[-1]
log = os.environ['FAKE_MINIMAP_LOG']
with open(log, 'a', encoding='utf-8') as handle:
    handle.write('call\\n')
with open(log, encoding='utf-8') as handle:
    call = len(handle.readlines())

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

targets = fasta(target)
queries = fasta(query)
target_name, target_sequence = targets[0]
target_length = len(target_sequence)
lines = []
if len(queries) > 2:
    selected = queries[:2]
    coords = [(0, 10000), (10200, 20200)]
    for (name, sequence), (start, end) in zip(selected, coords):
        qlen = len(sequence)
        lines.append(
            f'{name}\\t{qlen}\\t0\\t{qlen}\\t+\\t{target_name}\\t{target_length}'
            f'\\t{start}\\t{end}\\t{qlen}\\t{qlen}\\t60\\tcg:Z:{qlen}M'
        )
elif queries:
    left, right = queries[:2]
    for name, sequence, start, end, identity, mapq in [
        (left[0], left[1], 0, 10000, 1.0, 60),
        (right[0], right[1], 10200, 20200, 1.0, 60),
        (left[0], left[1], 20000, 30000, 0.9, 50),
        (right[0], right[1], 30200, 40200, 0.9, 50),
    ]:
        qlen = len(sequence)
        matches = int(qlen * identity)
        lines.append(
            f'{name}\\t{qlen}\\t0\\t{qlen}\\t+\\t{target_name}\\t{target_length}'
            f'\\t{start}\\t{end}\\t{matches}\\t{qlen}\\t{mapq}\\tcg:Z:{qlen}M'
        )
with open(out, 'w', encoding='utf-8', newline='') as handle:
    if lines:
        handle.write('\\n'.join(lines) + '\\n')
""",
            encoding="utf-8",
            newline="",
        )
        executable.chmod(0o755)
        return executable, log

    def run_step1(self, server: Path, minimap: Path, log: Path):
        env = os.environ.copy()
        env["FAKE_MINIMAP_LOG"] = str(log)
        return subprocess.run(
            [
                sys.executable,
                str(STEP1_TOOL),
                "--server-dir",
                str(server),
                "--minimap2",
                str(minimap),
                "--threads",
                "2",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_two_round_cache_global_interval_ledger_and_resume(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server = self.make_server(root)
            minimap, log = self.make_minimap(root)
            completed = self.run_step1(server, minimap, log)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), ["call", "call"])

            recipe = prepare_fixture.read_tsv(server / "metadata/grt_recipe.tsv")[0]
            stages = prepare_fixture.read_tsv(server / "metadata/grt_stage_status.tsv")
            self.assertEqual(
                [row["stage"] for row in stages],
                ["donor_freeze", "step1_round1", "step1_filter", "step1_round2"],
            )
            self.assertEqual(stages[1]["q_input_version"], "q0")
            self.assertEqual(stages[1]["q_output_version"], "q0r1")
            self.assertEqual(stages[3]["q_input_version"], "q0f")
            self.assertEqual(stages[3]["q_output_version"], "q1")
            self.assertTrue(all(row["donor_set_id"] == recipe["donor_set_id"] for row in stages))

            usage = prepare_fixture.read_tsv(server / "metadata/grt_donor_usage.tsv")
            consumed = [row for row in usage if row["status"] == "consumed"]
            conflicted = [row for row in usage if row["status"] == "conflicted"]
            self.assertEqual(len(consumed), 2)
            self.assertTrue(conflicted)
            first = (int(consumed[0]["source_start"]), int(consumed[0]["source_end"]))
            second = (int(consumed[1]["source_start"]), int(consumed[1]["source_end"]))
            self.assertLess(first[1], second[0])
            self.assertTrue(
                any(
                    int(row["source_start"]) <= first[1] and int(row["source_end"]) >= first[0]
                    for row in conflicted
                )
            )
            evidence = prepare_fixture.read_tsv(server / "metadata/grt_evidence_registry.tsv")
            round_evidence = [row for row in evidence if row["stage"].startswith("step1_")]
            donor_hash = next(
                row["fasta_sha256"]
                for row in prepare_fixture.read_tsv(server / "metadata/grt_donor_sets.tsv")
                if row["donor_set_id"] == recipe["donor_set_id"]
            )
            self.assertEqual(
                {row["target_sha256"] for row in round_evidence}, {donor_hash}
            )
            self.assertEqual(
                {row["q_version"] for row in round_evidence}, {"q0", "q0f"}
            )
            for row in round_evidence:
                self.assertEqual(
                    row["q_source_sha256"],
                    prepare_fixture.sha256(server / f"grt/q/{row['q_version']}.fa"),
                )
                self.assertEqual(
                    row["query_sha256"],
                    prepare_fixture.sha256(server / row["query_artifact_relpath"]),
                )
                self.assertEqual(
                    row["raw_artifact_sha256"],
                    prepare_fixture.sha256(server / row["raw_artifact_relpath"]),
                )
            self.assertNotEqual(
                prepare_fixture.sha256(server / "grt/evidence/step1/round1/flanks.fa"),
                prepare_fixture.sha256(server / "grt/evidence/step1/round2/flanks.fa"),
            )
            events = [
                json.loads(line)
                for line in (server / "metadata/grt_events.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertTrue(
                any(
                    event["stage"] == "step1_round1"
                    and event["status"] == "unresolved"
                    for event in events
                )
            )

            q1_before = prepare_fixture.sha256(server / "grt/q/q1.fa")
            repeated = self.run_step1(server, minimap, log)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 2)
            self.assertEqual(q1_before, prepare_fixture.sha256(server / "grt/q/q1.fa"))

            donor_resume = subprocess.run(
                [sys.executable, str(PREPARE_TOOL), "--server-dir", str(server)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(donor_resume.returncode, 0, donor_resume.stderr)
            self.assertIn("are current", donor_resume.stdout)
            after_donor_resume = self.run_step1(server, minimap, log)
            self.assertEqual(after_donor_resume.returncode, 0, after_donor_resume.stderr)
            self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 2)
            self.assertEqual(q1_before, prepare_fixture.sha256(server / "grt/q/q1.fa"))

            (server / "grt/checkpoints/step1_round2.json").unlink()
            resumed = self.run_step1(server, minimap, log)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 2)

            round2_cache_paf = next(
                path
                for path in (server / "grt/cache/step1/step1_round2").glob(
                    "*/*/result.paf"
                )
                if path.stat().st_size > 0
            )
            with round2_cache_paf.open("a", encoding="utf-8", newline="") as handle:
                handle.write("non-exact chromosome cache\n")
            (server / "grt/checkpoints/step1_round2.json").unlink()
            chromosome_rebuilt = self.run_step1(server, minimap, log)
            self.assertEqual(chromosome_rebuilt.returncode, 0, chromosome_rebuilt.stderr)
            self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 3)

            with (server / "grt/evidence/step1/round1/result.paf").open(
                "a", encoding="utf-8", newline=""
            ) as handle:
                handle.write("non-exact historical PAF\n")
            round1_cache_paf = next(
                path
                for path in (server / "grt/cache/step1/step1_round1").glob(
                    "*/*/result.paf"
                )
                if path.stat().st_size > 0
            )
            with round1_cache_paf.open("a", encoding="utf-8", newline="") as handle:
                handle.write("non-exact chromosome cache\n")
            invalidated = self.run_step1(server, minimap, log)
            self.assertEqual(invalidated.returncode, 0, invalidated.stderr)
            self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 4)
            self.assertEqual(q1_before, prepare_fixture.sha256(server / "grt/q/q1.fa"))

    def test_filter_removes_only_isolated_components_below_threshold(self):
        sources = {
            ("primary", "left"): "A" * 100_000,
            ("primary", "small"): "C" * 99_999,
            ("primary", "right"): "G" * 100_001,
        }
        def segment(name):
            sequence = sources[("primary", name)]
            return {
                "segment_kind": "source",
                "length": len(sequence),
                "dataset_name": "primary",
                "contig_name": name,
                "source_start": 1,
                "source_end": len(sequence),
                "orientation": "+",
                "source_card_key": f"primary:{name}:Chr01:normal",
                "evidence_ids": [f"ev-{name}"],
            }
        gap = {
            "segment_kind": "gap",
            "length": 100,
            "dataset_name": "",
            "contig_name": "",
            "source_start": None,
            "source_end": None,
            "orientation": "",
            "source_card_key": "",
            "evidence_ids": [],
        }
        paths = {"Chr01": [segment("left"), gap, segment("small"), gap, segment("right")]}
        records = {
            "Chr01": "A" * 100_000 + "N" * 100 + "C" * 99_999 + "N" * 100 + "G" * 100_001
        }
        output_paths, output_records, events = apply_filter(
            "run-filter", ["Chr01"], paths, records, "0" * 64, sources
        )
        self.assertEqual(
            output_records["Chr01"], "A" * 100_000 + "N" * 100 + "G" * 100_001
        )
        self.assertEqual(events[0]["status"], "accepted")
        self.assertEqual(events[0]["edit"]["removed_intervals"], [[100101, 200099]])
        self.assertEqual(replay_filter_records(records, events), output_records)
        self.assertEqual(len(output_paths["Chr01"]), 3)

    def test_filter_marks_removed_accepted_donor_trace_as_superseded(self):
        round1 = {
            "q_rows": [
                {
                    "chr": "Chr01",
                    "q_start": 101,
                    "q_end": 300,
                    "evidence_ids_json": '["ev-fill"]',
                }
            ],
            "events": [
                {
                    "event_id": "event-fill",
                    "status": "accepted",
                    "reason": "accepted_by_global_interval_arbitration",
                    "evidence_ids": ["ev-fill"],
                    "final_path_segment_id": "segment-fill",
                }
            ],
            "evidence_rows": [{"evidence_id": "ev-fill", "status": "accepted"}],
            "usage_rows": [
                {
                    "event_id": "event-fill",
                    "status": "consumed",
                    "final_path_segment_id": "segment-fill",
                    "reason": "accepted_by_global_interval_arbitration",
                }
            ],
        }
        filter_result = {
            "events": [
                {
                    "event_id": "event-filter",
                    "chr": "Chr01",
                    "status": "accepted",
                    "edit": {"removed_intervals": [[1, 500]]},
                }
            ]
        }
        reconcile_filtered_round1_events(round1, filter_result)
        self.assertEqual(round1["events"][0]["status"], "superseded")
        self.assertEqual(round1["events"][0]["final_path_segment_id"], "")
        self.assertEqual(round1["evidence_rows"][0]["status"], "superseded")
        self.assertEqual(round1["usage_rows"][0]["status"], "superseded")
        self.assertEqual(
            filter_result["events"][0]["superseded_event_ids"], ["event-fill"]
        )


if __name__ == "__main__":
    unittest.main()
