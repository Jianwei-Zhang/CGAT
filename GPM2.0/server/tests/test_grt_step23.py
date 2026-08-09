import json
import os
import random
import re
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
import test_grt_step1 as step1_fixture
from grt_prepare_inputs import read_fasta, reverse_complement
from grt_step23 import (
    _longest_exact_suffix_prefix,
    _step3_classify_features,
    _step3_edit_scope_decision,
    apply_corrections,
    arbitrate,
    build_correction_candidates,
    build_correction_events,
    build_step2_fallback_candidates,
    parse_mummer_coords,
    promote_direct_primary_overlap_merges,
    project_interval_after_refills,
    reject_candidates_spanning_other_gaps,
    replay_step3,
    step2_strategy,
)


PREPARE_TOOL = REPO_ROOT / "server/tools/grt_prepare_inputs.py"
STEP1_TOOL = REPO_ROOT / "server/tools/grt_step1.py"
STEP23_TOOL = REPO_ROOT / "server/tools/grt_step23.py"


class GrtStep23Tests(unittest.TestCase):
    @staticmethod
    def source_segment(
        dataset: str,
        contig: str,
        length: int,
        orientation: str,
    ) -> dict[str, object]:
        return {
            "segment_kind": "source",
            "length": length,
            "dataset_name": dataset,
            "contig_name": contig,
            "source_start": 1,
            "source_end": length,
            "orientation": orientation,
            "source_card_key": f"{dataset}:{contig}:Chr05:normal",
            "evidence_ids": [f"assignment-{contig}"],
        }

    @staticmethod
    def gap_segment(length: int = 100) -> dict[str, object]:
        return {
            "segment_kind": "gap",
            "length": length,
            "dataset_name": "",
            "contig_name": "",
            "source_start": None,
            "source_end": None,
            "orientation": "",
            "source_card_key": "",
            "evidence_ids": [],
        }

    def test_grt_server_golden_decisions_match_documented_source_strategies(self):
        golden = json.loads(
            (REPO_ROOT / "server/tests/fixtures/grt_server_golden.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            golden["provenance"]["source"],
            "Genome-Repair-Tools/scripts/gap_analyzer.py",
        )
        for row in golden["step2"]:
            self.assertEqual(
                step2_strategy(
                    row["gap_count"],
                    row["patch_candidate_count"],
                    row["accepted_patch_count"],
                ),
                row["strategy"],
            )
        for row in golden["step3"]:
            error_type, subtype, _features, _score = _step3_classify_features(row["features"])
            self.assertEqual((error_type, subtype), (row["error_type"], row["subtype"]))

    def test_step23_reuses_same_orientation_donor_on_distinct_targets(self):
        def candidate(candidate_id, object_id, chromosome, orientation):
            return {
                "candidate_id": candidate_id,
                "object_id": object_id,
                "chr": chromosome,
                "source_dataset": "support",
                "source_contig": "donor",
                "source_start": 1001,
                "source_end": 2000,
                "orientation": orientation,
                "target_start": 5001,
                "target_end": 5100,
                "input_start": 5001,
                "input_end": 5100,
                "identity": 0.99,
                "aligned_length": 2000,
                "mapq": 60,
                "validation_passed": True,
                "outcome": "candidate",
                "reason": "",
            }

        rows = arbitrate(
            [candidate("c1", "gap-1", "Chr01", "+"), candidate("c2", "gap-2", "Chr02", "+")],
            [],
        )
        self.assertEqual([row["outcome"] for row in rows], ["accepted", "accepted"])
        self.assertEqual(next(row for row in rows if row.get("donor_reuse"))["donor_reuse_of"], "c1")

    def test_step2_controller_selects_all_three_grt_branches(self):
        self.assertEqual(step2_strategy(3, 0, 0), "no_patch_fixer")
        self.assertEqual(step2_strategy(3, 4, 0), "full_fixer_reuse_patches")
        self.assertEqual(step2_strategy(3, 4, 2), "partial_success_no_fixer")

    def test_step2_fallback_reuses_explicit_donor_source(self):
        member = {
            "member_id": "m-d1",
            "dataset_name": "d0",
            "contig_name": "d1",
            "orientation": "+",
            "source_start": "1",
            "source_end": "2000",
        }
        alignment = {
            "chr": "Chr01",
            "line_number": 1,
            "ref_record": "d1",
            "ref_min": 101,
            "ref_max": 500,
            "query_min": 900,
            "query_max": 1200,
            "query_length": 2000,
            "query_aligned": 301,
            "ref_length": 2000,
            "ref_aligned": 400,
            "identity": 0.99,
            "orientation": "+",
        }
        gap = {"chr": "Chr01", "object_id": "gap-1", "start0": 999, "end0": 1099}
        sources = {("d0", "d1"): "ACGT" * 500}
        candidates = build_step2_fallback_candidates(
            [gap], [alignment], {"d1": member}, sources
        )
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]["fallback"])
        self.assertEqual(candidates[0]["action"], "patch")
        self.assertEqual(candidates[0]["fill_sequence"], sources[("d0", "d1")][100:500])
        self.assertEqual(candidates[0]["fallback_strategy"], "correctrefill_source_retry")

    def test_step3_classifies_realizable_anchor_pairs_with_type5_overlap_override(self):
        members = {
            "d1": {
                "member_id": "m-d1",
                "dataset_name": "d0",
                "contig_name": "d1",
                "orientation": "+",
                "source_start": "1",
                "source_end": "200000",
            },
            "d2": {
                "member_id": "m-d2",
                "dataset_name": "d0",
                "contig_name": "d2",
                "orientation": "+",
                "source_start": "1",
                "source_end": "200000",
            },
        }

        def row(line, q_start, q_end, ref_start, ref_end, record="d1", orientation="+"):
            return {
                "chr": "Chr01",
                "line_number": line,
                "ref_record": record,
                "ref_min": ref_start,
                "ref_max": ref_end,
                "query_min": q_start,
                "query_max": q_end,
                "query_length": 10000,
                "query_aligned": q_end - q_start + 1,
                "ref_length": 200000,
                "ref_aligned": ref_end - ref_start + 1,
                "identity": 0.99,
                "orientation": orientation,
            }

        gaps = [
            {"chr": "Chr01", "object_id": f"gap-{index}", "start0": start - 1, "end0": start + 99}
            for index, start in enumerate((1001, 2001, 3001, 4501, 5501, 7001), start=1)
        ]
        alignments = [
            row(1, 900, 1200, 100, 400),  # Type1 crossing
            row(2, 1500, 1900, 1000, 1400),
            row(3, 2100, 2500, 1401, 1800, orientation="-"),  # Type2
            row(4, 2500, 2900, 2000, 2400),
            row(5, 3100, 3500, 2401, 2800, record="d2"),  # Type3
            row(6, 3500, 3900, 3000, 3400),
            row(7, 4100, 4500, 4000, 4400),
            row(8, 4600, 5000, 4395, 4800),  # Type5: any reference overlap
            row(9, 5100, 5500, 5000, 5700),
            row(10, 5600, 6000, 5600, 6300),  # Type5: 101 bp overlap (>10%)
            row(11, 6500, 6900, 7000, 7400),
            row(12, 7100, 7500, 8000, 8400, record="d2", orientation="-"),  # Type6
        ]
        candidates = build_correction_candidates(gaps, alignments, members)
        by_gap = {}
        for candidate in candidates:
            if candidate["outcome"] != "rejected":
                by_gap.setdefault(str(candidate["object_id"]), []).append(candidate)
        self.assertEqual(
            {row["error_type"] for rows in by_gap.values() for row in rows},
            {"type1", "type2", "type3", "type5", "type6"},
        )
        self.assertEqual(by_gap["gap-1"][0]["error_subtype"], "crossing_alignment")
        self.assertTrue(any(row["error_subtype"] == "direction_conflict" for row in by_gap["gap-2"]))
        self.assertTrue(any(row["error_subtype"] == "simple_translocation" for row in by_gap["gap-3"]))
        self.assertTrue(any(row["error_type"] == "type5" for row in by_gap["gap-4"]))
        self.assertTrue(any(row["error_type"] == "type5" for row in by_gap["gap-5"]))
        self.assertTrue(any(row["error_subtype"] == "complex_conflict" for row in by_gap["gap-6"]))
        self.assertTrue(all(row["repair_mode"] == "aggressive" for rows in by_gap.values() for row in rows))

    def test_step3_small_reference_overlap_uses_type5_and_covers_origin_gap(self):
        member = {
            "member_id": "m-d1",
            "dataset_name": "support",
            "contig_name": "donor",
            "orientation": "+",
            "source_start": "1",
            "source_end": "5000",
        }

        def row(line, query_start, query_end, ref_start, ref_end):
            return {
                "chr": "Chr01",
                "line_number": line,
                "ref_record": "d1",
                "ref_min": ref_start,
                "ref_max": ref_end,
                "query_min": query_start,
                "query_max": query_end,
                "query_length": 3000,
                "query_aligned": query_end - query_start + 1,
                "ref_length": 5000,
                "ref_aligned": ref_end - ref_start + 1,
                "identity": 0.99,
                "orientation": "+",
            }

        gap = {"chr": "Chr01", "object_id": "gap-1", "start0": 1000, "end0": 1100}
        candidates = build_correction_candidates(
            [gap],
            [
                row(1, 1, 900, 1, 1000),
                row(2, 1101, 1500, 995, 1300),
            ],
            {"d1": member},
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["error_type"], "type5")
        self.assertEqual(candidate["classification_reason"], "reference_overlap_with_margin")
        self.assertEqual(candidate["input_start"], 1001)
        self.assertEqual(candidate["input_end"], 1208)
        self.assertLessEqual(candidate["input_start"], candidate["target_start"])
        self.assertGreaterEqual(candidate["input_end"], candidate["target_end"])

    def test_step3_real_chr05_overlap_does_not_delete_the_full_shorter_alignment(self):
        member = {
            "member_id": "m-flye-scaffold-50",
            "dataset_name": "flye",
            "contig_name": "scaffold_50",
            "orientation": "+",
            "source_start": "1",
            "source_end": "30370176",
        }

        def row(line, query_start, query_end, ref_start, ref_end):
            return {
                "chr": "Chr05",
                "line_number": line,
                "ref_record": "flye-scaffold-50",
                "ref_min": ref_start,
                "ref_max": ref_end,
                "query_min": query_start,
                "query_max": query_end,
                "query_length": 30424813,
                "query_aligned": query_end - query_start + 1,
                "ref_length": 30370176,
                "ref_aligned": ref_end - ref_start + 1,
                "identity": 0.9999,
                "orientation": "+",
            }

        gap = {
            "chr": "Chr05",
            "object_id": "gap-real-chr05",
            "start0": 27328070,
            "end0": 27328170,
        }
        candidates = build_correction_candidates(
            [gap],
            [
                row(1, 1, 27318714, 4147, 27322873),
                row(2, 27328171, 30219970, 27312687, 30204494),
            ],
            {"flye-scaffold-50": member},
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["error_type"], "type5")
        self.assertEqual(candidate["input_start"], 27328071)
        self.assertEqual(candidate["input_end"], 27338457)
        self.assertLess(candidate["input_end"] - candidate["input_start"] + 1, 20_000)

    def test_step3_direct_primary_overlap_keeps_left_and_trims_right(self):
        rng = random.Random(20260809)
        overlap = "".join(rng.choice("ACGT") for _ in range(19_542))
        left_oriented = "".join(rng.choice("ACGT") for _ in range(2_000)) + overlap
        right_oriented = overlap + "".join(rng.choice("ACGT") for _ in range(3_000))
        sources = {
            ("hifiasm", "ptg000004l"): reverse_complement(left_oriented),
            ("hifiasm", "ptg000011l"): reverse_complement(right_oriented),
        }
        path = [
            self.source_segment("hifiasm", "ptg000004l", len(left_oriented), "-"),
            self.gap_segment(),
            self.source_segment("hifiasm", "ptg000011l", len(right_oriented), "-"),
        ]
        gap = {
            "chr": "Chr05",
            "object_id": "gap-real-shape",
            "start0": len(left_oriented),
            "end0": len(left_oriented) + 100,
        }
        candidate = {
            "candidate_id": "type5-real-shape",
            "chr": "Chr05",
            "object_id": gap["object_id"],
            "error_type": "type5",
            "error_features": ["ref_overlap_10187"],
            "outcome": "candidate",
            "input_start": gap["start0"] + 1,
            "input_end": gap["end0"] + 10_287,
            "trim_left": 0,
            "trim_right": 10_287,
            "fill_length": 100,
        }

        promote_direct_primary_overlap_merges(
            [gap],
            [candidate],
            {"Chr05": path},
            sources,
            "hifiasm",
        )

        self.assertEqual(candidate["junction_policy"], "keep_left_trim_right")
        self.assertEqual(candidate["trim_left"], 0)
        self.assertEqual(candidate["trim_right"], 19_542)
        self.assertEqual(candidate["fill_length"], 0)
        self.assertEqual(candidate["input_start"], len(left_oriented) + 1)
        self.assertEqual(candidate["input_end"], len(left_oriented) + 100 + 19_542)

        candidate["outcome"] = "accepted"
        input_sequence = left_oriented + "N" * 100 + right_oriented
        output_paths, output_records, prototypes, gap_origins = apply_corrections(
            ["Chr05"],
            {"Chr05": path},
            {"Chr05": input_sequence},
            [gap],
            [candidate],
            sources,
        )
        expected = left_oriented + right_oriented[19_542:]
        self.assertEqual(output_records["Chr05"], expected)
        self.assertNotIn("N" * 100, output_records["Chr05"])
        self.assertEqual(gap_origins, {})
        self.assertEqual(prototypes[0]["replacement_length"], 0)
        self.assertEqual(output_paths["Chr05"][0]["source_end"], len(left_oriented))
        self.assertEqual(output_paths["Chr05"][1]["source_start"], 1)
        self.assertEqual(
            output_paths["Chr05"][1]["source_end"],
            len(right_oriented) - 19_542,
        )
        replayed = replay_step3(
            {"Chr05": input_sequence},
            [
                {
                    "status": "accepted",
                    "chr": "Chr05",
                    "edit": {
                        "input_start": candidate["input_start"],
                        "input_end": candidate["input_end"],
                        "replacement_length": 0,
                    },
                }
            ],
            [],
            sources,
        )
        self.assertEqual(replayed, output_records)

    def test_step3_direct_overlap_trims_left_only_without_flush_match(self):
        rng = random.Random(7)
        overlap = "".join(rng.choice("ACGT") for _ in range(1_000))
        left = "".join(rng.choice("ACGT") for _ in range(500)) + overlap + "TTT"
        right = overlap + "".join(rng.choice("ACGT") for _ in range(500))
        sources = {("primary", "left"): left, ("primary", "right"): right}
        path = [
            self.source_segment("primary", "left", len(left), "+"),
            self.gap_segment(),
            self.source_segment("primary", "right", len(right), "+"),
        ]
        gap = {
            "chr": "Chr05",
            "object_id": "gap-shifted",
            "start0": len(left),
            "end0": len(left) + 100,
        }
        candidate = {
            "candidate_id": "type5-shifted",
            "chr": "Chr05",
            "object_id": gap["object_id"],
            "error_type": "type5",
            "error_features": [],
            "outcome": "candidate",
        }
        promote_direct_primary_overlap_merges(
            [gap],
            [candidate],
            {"Chr05": path},
            sources,
            "primary",
            min_overlap=500,
            max_overlap=2_000,
            max_left_trim=5,
        )
        self.assertEqual(candidate["trim_left"], 3)
        self.assertEqual(candidate["trim_right"], 1_000)

    def test_step3_direct_overlap_event_uses_valid_junction_anchor(self):
        gap = {
            "chr": "Chr05",
            "object_id": "gap-direct",
            "start0": 1_000,
            "end0": 1_100,
        }
        candidate = {
            "candidate_id": "candidate-direct",
            "chr": "Chr05",
            "object_id": "gap-direct",
            "outcome": "accepted",
            "action": "delete",
            "classification_reason": "direct_primary_overlap_keep_left_trim_right",
            "input_start": 1_001,
            "input_end": 11_100,
            "source_dataset": "flye",
            "source_contig": "scaffold_50",
            "source_start": 1,
            "source_end": 20_000,
            "orientation": "+",
            "evidence_ids": ["evidence-direct"],
            "usage_ids": ["usage-direct"],
            "error_type": "type5",
            "error_subtype": "medium_ref_overlap",
            "error_features": ["direct_primary_overlap_10000"],
            "confidence": "high",
            "confidence_score": 0.91,
            "gap_in_error_region": True,
            "repair_mode": "aggressive",
            "repair_reason": "conservative_conditions_met",
            "fragment_id": "fragment-flye",
            "junction_policy": "keep_left_trim_right",
            "trim_left": 0,
            "trim_right": 10_000,
            "direct_overlap_bp": 10_000,
            "primary_left_dataset": "hifiasm",
            "primary_left_contig": "ptg000004l",
            "primary_left_orientation": "-",
            "primary_right_dataset": "hifiasm",
            "primary_right_contig": "ptg000011l",
            "primary_right_orientation": "-",
        }
        events, attempts = build_correction_events(
            "run-direct",
            "1" * 64,
            "2" * 64,
            [gap],
            [],
            [candidate],
            [
                {
                    "object_id": "gap-direct",
                    "intermediate_start": 1_001,
                    "intermediate_end": 1_001,
                    "replacement_length": 0,
                }
            ],
            [],
            {},
            {("flye", "scaffold_50"): {"Chr05"}},
        )
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["action"], "delete")
        self.assertEqual((event["q_after"]["start"], event["q_after"]["end"]), (1_001, 1_001))
        self.assertEqual(event["edit"]["replacement_kind"], "none")
        self.assertEqual(event["edit"]["replacement_length"], 0)
        self.assertEqual(event["junction"]["policy"], "keep_left_trim_right")
        self.assertFalse(event["junction"]["support_sequence_inserted"])
        self.assertEqual(attempts[0]["status"], "accepted")

    def test_step3_direct_overlap_rejects_unsafe_or_non_primary_cases(self):
        rng = random.Random(11)
        overlap = "".join(rng.choice("ACGT") for _ in range(1_000))
        suffix = "".join(rng.choice("ACGT") for _ in range(200))

        def candidate(error_type: str = "type5") -> dict[str, object]:
            return {
                "candidate_id": f"candidate-{error_type}",
                "chr": "Chr05",
                "object_id": "gap-guard",
                "error_type": error_type,
                "error_features": [],
                "outcome": "candidate",
            }

        cases = [
            (
                "whole_right_source",
                "primary",
                overlap,
                overlap,
                candidate(),
                500,
            ),
            (
                "non_primary_neighbors",
                "support",
                overlap,
                overlap + suffix,
                candidate(),
                500,
            ),
            (
                "non_type5_candidate",
                "primary",
                overlap,
                overlap + suffix,
                candidate("type4"),
                500,
            ),
            (
                "short_overlap",
                "primary",
                overlap[-100:],
                overlap[-100:] + suffix,
                candidate(),
                500,
            ),
        ]
        for name, dataset, left, right, row, minimum in cases:
            with self.subTest(name=name):
                gap = {
                    "chr": "Chr05",
                    "object_id": "gap-guard",
                    "start0": len(left),
                    "end0": len(left) + 100,
                }
                path = [
                    self.source_segment(dataset, "left", len(left), "+"),
                    self.gap_segment(),
                    self.source_segment(dataset, "right", len(right), "+"),
                ]
                promote_direct_primary_overlap_merges(
                    [gap],
                    [row],
                    {"Chr05": path},
                    {(dataset, "left"): left, (dataset, "right"): right},
                    "primary",
                    min_overlap=minimum,
                    max_overlap=2_000,
                    max_left_trim=5,
                )
                self.assertNotIn("junction_policy", row)

    def test_exact_overlap_matcher_returns_longest_terminal_match(self):
        self.assertEqual(_longest_exact_suffix_prefix("AACCGGTT", "GGTTAA", 20), 4)
        self.assertEqual(_longest_exact_suffix_prefix("aacCGGtt", "GGTTAA", 20), 4)
        self.assertEqual(_longest_exact_suffix_prefix("AACCGGTA", "GGTTAA", 20), 0)

    def test_step3_rejects_large_overlap_edit_without_matching_evidence_scope(self):
        safe, reason = _step3_edit_scope_decision(
            "type4",
            {
                "query_overlap_length": 10_000,
                "ref_overlap_length": 0,
            },
            1,
            2_000_000,
        )
        self.assertFalse(safe)
        self.assertEqual(reason, "automatic_edit_exceeds_overlap_evidence")

        safe, reason = _step3_edit_scope_decision(
            "type5",
            {
                "query_overlap_length": 0,
                "ref_overlap_length": 10_000,
            },
            1,
            20_000,
        )
        self.assertTrue(safe)
        self.assertEqual(reason, "")

    def test_apply_corrections_rejects_edit_that_does_not_cover_origin_gap(self):
        gap_segment = {
            "segment_kind": "gap",
            "length": 3000,
            "dataset_name": "",
            "contig_name": "",
            "source_start": None,
            "source_end": None,
            "orientation": "",
            "source_card_key": "",
            "evidence_ids": [],
        }
        gap = {"chr": "Chr01", "object_id": "gap-1", "start0": 1000, "end0": 1100}
        candidate = {
            "candidate_id": "candidate-1",
            "chr": "Chr01",
            "object_id": "gap-1",
            "input_start": 1101,
            "input_end": 1500,
            "outcome": "accepted",
        }
        with self.assertRaisesRegex(SystemExit, "does not cover associated q2 gap"):
            apply_corrections(
                ["Chr01"],
                {"Chr01": [gap_segment]},
                {"Chr01": "N" * 3000},
                [gap],
                [candidate],
                {},
            )

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
        step23_tool: Path = STEP23_TOOL,
    ):
        return subprocess.run(
            [
                sys.executable,
                str(step23_tool),
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

    def test_step23_runtime_script_hash_invalidates_successful_checkpoints(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server = self.make_server(root)
            tools = self.make_tools(root)
            minimap_log = root / "minimap.log"
            mummer_log = root / "mummer.log"
            env = os.environ.copy()
            env["FAKE_GRT_MINIMAP_LOG"] = str(minimap_log)
            env["FAKE_GRT_MUMMER_LOG"] = str(mummer_log)
            env["PYTHONPATH"] = os.pathsep.join(
                filter(
                    None,
                    [str(REPO_ROOT / "server/tools"), env.get("PYTHONPATH", "")],
                )
            )
            runtime_tool = root / "grt_step23_runtime.py"
            shutil.copy2(STEP23_TOOL, runtime_tool)

            step1 = self.run_step1(server, tools, env)
            self.assertEqual(step1.returncode, 0, step1.stderr)
            first = self.run_step23(server, tools, env, step23_tool=runtime_tool)
            self.assertEqual(first.returncode, 0, first.stderr)
            initial_calls = mummer_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(initial_calls), 2)

            repeated = self.run_step23(server, tools, env, step23_tool=runtime_tool)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(mummer_log.read_text(encoding="utf-8").splitlines(), initial_calls)

            runtime_tool.write_text(
                runtime_tool.read_text(encoding="utf-8") + "\n# runtime fingerprint mutation\n",
                encoding="utf-8",
                newline="",
            )
            changed = self.run_step23(server, tools, env, step23_tool=runtime_tool)
            self.assertEqual(changed.returncode, 0, changed.stderr)
            self.assertEqual(len(mummer_log.read_text(encoding="utf-8").splitlines()), 4)
            checkpoint = json.loads(
                (server / "grt/checkpoints/step3.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                checkpoint["fingerprint_payload"]["engine_sha256"],
                prepare_fixture.sha256(runtime_tool),
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
            strategies = prepare_fixture.read_tsv(server / "metadata/grt_step2_strategies.tsv")
            self.assertEqual(
                {row["strategy"] for row in strategies},
                {"partial_success_no_fixer", "no_gaps"},
            )
            self.assertTrue(all(row["strategy_applied"] == "patcher_result" for row in strategies))
            classifications = prepare_fixture.read_tsv(
                server / "metadata/grt_step3_classifications.tsv"
            )
            self.assertTrue(classifications)
            self.assertTrue(all(row["repair_mode"] == "aggressive" for row in classifications))

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
