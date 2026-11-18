import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).parents[2]
from server.tests import test_grt_prepare_inputs as prepare_fixture
from server.tools.lgz_core import (
    apply_filter,
    arbitrate_candidates,
    filter_paths,
    replay_filter_records,
)


PREPARE_TOOL = REPO_ROOT / "server/tools/grt_prepare_inputs.py"


class GrtStep1Tests(unittest.TestCase):
    def test_donor_interval_reuse_is_allowed_across_targets_but_not_orientations(self):
        def candidate(candidate_id, object_id, chromosome, orientation):
            return {
                "candidate_id": candidate_id,
                "stage": "step1_round1",
                "chr": chromosome,
                "object_id": object_id,
                "source_dataset": "support",
                "source_contig": "donor",
                "source_start": 1001,
                "source_end": 2000,
                "orientation": orientation,
                "identity": 0.99,
                "aligned_length": 2000,
                "mapq": 60,
            }

        accepted = arbitrate_candidates(
            [candidate("c1", "gap-1", "Chr01", "+"), candidate("c2", "gap-2", "Chr02", "+")],
            [],
        )
        self.assertEqual([row["outcome"] for row in accepted], ["accepted", "accepted"])
        reused = next(row for row in accepted if row.get("donor_reuse"))
        self.assertEqual(reused["donor_reuse_of"], "c1")

        conflicted = arbitrate_candidates(
            [candidate("c1", "gap-1", "Chr01", "+"), candidate("c2", "gap-2", "Chr02", "-")],
            [],
        )
        self.assertEqual(
            sorted(row["outcome"] for row in conflicted),
            ["accepted", "conflicted"],
        )
        self.assertTrue(
            any(row["reason"] == "source_interval_reuse_orientation_conflict" for row in conflicted)
        )

    def make_server(self, root: Path) -> Path:
        helper = prepare_fixture.GrtPrepareInputsTests(
            "test_no_reads_builds_traceable_q0_and_frozen_global_donors"
        )
        server = helper.make_server(root)
        metadata = server / "metadata"
        from server.tests.test_q0_admission import dna
        # Controlled stage fixture, not a measured alignment result. Give q0
        # three distinct anchored pieces and two unknown joins; unanchored
        # donors remain available for later-stage evidence, not a first-ds bias.
        primary_records = [
            ("p_cover", dna(12_000, 801)),
            ("p_redundant", dna(11_000, 802)),
            ("p_partial", dna(12_000, 803)),
            ("p_third", dna(12_000, 804)),
            ("p_reverse", dna(12_000, 805)),
        ]
        support_records = [
            ("s_assigned", dna(50_000, 806)),
            ("s_unplaced", dna(13_000, 807)),
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
                "source_orientation",
                "orientation_source",
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
                    "source_orientation": "-" if name == "p_reverse" else "+",
                    "orientation_source": "ref_alignment",
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
                    "p_partial\t12000\t0\t12000\t+\tChr01\t60000\t20000\t32000\t12000\t12000\t60",
                    "p_third\t12000\t0\t12000\t+\tChr01\t60000\t40000\t52000\t12000\t12000\t60",
                    "p_reverse\t12000\t0\t12000\t-\tChr02\t60000\t99\t12099\t12000\t12000\t60",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (server / "runs/support_vs_ref/result.paf").write_text(
            "",
            encoding="utf-8",
        )
        from server.tests.q0_test_support import seed_q0_evidence
        seed_q0_evidence(server)
        completed = subprocess.run(
            [sys.executable, str(PREPARE_TOOL), "--server-dir", str(server)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return server

    def test_prepared_q0_has_no_legacy_identity_versions(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            server = self.make_server(Path(temporary_dir))
            self.assertEqual(sorted(p.stem for p in (server / "grt/q").glob("*.fa")), ["q0"])
            self.assertEqual(
                [row["stage"] for row in prepare_fixture.read_tsv(server / "metadata/grt_stage_status.tsv")],
                ["donor_freeze"],
            )

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

    def test_post_fill_filter_connector_preserves_collapsed_gap_origins(self):
        sources = {
            ("primary", "left"): "A" * 100_000,
            ("primary", "small"): "C" * 20_000,
            ("primary", "right"): "G" * 100_000,
        }

        def source(name):
            return {
                "segment_kind": "source",
                "length": len(sources[("primary", name)]),
                "dataset_name": "primary",
                "contig_name": name,
                "source_start": 1,
                "source_end": len(sources[("primary", name)]),
                "orientation": "+",
                "source_card_key": f"primary:{name}:Chr01:normal",
                "evidence_ids": [],
            }

        def gap(object_id):
            return {
                "segment_kind": "gap",
                "length": 100,
                "dataset_name": "",
                "contig_name": "",
                "source_start": None,
                "source_end": None,
                "orientation": "",
                "source_card_key": "",
                "evidence_ids": [],
                "origin_object_ids": [object_id],
            }

        path = [
            source("left"),
            gap("gap-1"),
            source("small"),
            gap("gap-2"),
            source("right"),
        ]
        records = {
            "Chr01": "A" * 100_000
            + "N" * 100
            + "C" * 20_000
            + "N" * 100
            + "G" * 100_000
        }
        output_paths, output_records, prototypes = filter_paths(
            ["Chr01"], {"Chr01": path}, records, sources
        )
        connector = next(
            segment
            for segment in output_paths["Chr01"]
            if segment["segment_kind"] == "gap"
        )
        self.assertEqual(connector["origin_object_ids"], ["gap-1", "gap-2"])
        self.assertEqual(len(output_records["Chr01"]), 200_100)
        self.assertEqual(prototypes[0]["status"], "accepted")



if __name__ == "__main__":
    unittest.main()
