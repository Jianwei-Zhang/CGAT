from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_TOOLS = REPO_ROOT / "server/tools"
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/grt_contract_v2/valid/gpm_server"
sys.path.insert(0, str(SERVER_TOOLS))

import grt_app_package  # noqa: E402
from grt_display_evidence import build_display_evidence  # noqa: E402


class GrtAppPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "source"
        shutil.copytree(FIXTURE_ROOT, self.source)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_build_emits_display_contract_schema_three(self) -> None:
        staging = self.root / "staging"
        no_fasta_staging = self.root / "staging-no-fasta"

        grt_app_package.build(self.source, staging, include_fasta=True)
        grt_app_package.build(self.source, no_fasta_staging, include_fasta=False)

        with (staging / "metadata/package.tsv").open(newline="", encoding="utf-8") as handle:
            package = next(csv.DictReader(handle, delimiter="\t"))
        final_path = json.loads((staging / "metadata/grt_final_path.json").read_text(encoding="utf-8"))
        no_fasta_final_path = json.loads(
            (no_fasta_staging / "metadata/grt_final_path.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (staging / "metadata/grt_app_manifest.json").read_text(encoding="utf-8")
        )
        no_fasta_manifest = json.loads(
            (no_fasta_staging / "metadata/grt_app_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(package["final_path_schema_version"], "3")
        self.assertEqual(final_path["schema_version"], "3")
        self.assertEqual(final_path["workflow"], "gpm_grt_app_precomputed_v2")
        self.assertIn("event_id", final_path["chromosomes"][0]["segments"][0])
        self.assertEqual(final_path["chromosomes"][0]["display_evidence"], [])
        self.assertEqual(no_fasta_final_path, final_path)
        self.assertEqual(no_fasta_manifest["final_path_sha256"], manifest["final_path_sha256"])

    def test_projects_only_selected_mummer_and_local_flank_rows(self) -> None:
        root = self.root / "evidence-source"
        metadata = root / "metadata"
        mummer = root / "grt/evidence/step3/mummer"
        refill = root / "grt/evidence/step3/refill/round1"
        metadata.mkdir(parents=True)
        mummer.mkdir(parents=True)
        refill.mkdir(parents=True)
        (metadata / "grt_events.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "event_id": "event-precursor",
                            "stage": "step3",
                            "chr": "Chr01",
                            "action": "delete",
                            "status": "superseded",
                            "evidence_ids": ["ev-mummer"],
                        },
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        {
                            "event_id": "event-final",
                            "stage": "step3",
                            "chr": "Chr01",
                            "action": "refill",
                            "status": "accepted",
                            "evidence_ids": ["ev-local"],
                            "superseded_event_ids": ["event-precursor"],
                        },
                        separators=(",", ":"),
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (metadata / "grt_donor_members.tsv").write_text(
            "donor_set_id\tmember_id\tdataset_name\tcontig_name\tsource_start\tsource_end\torientation\tfasta_record_name\tsequence_sha256\n"
            "d0\tmember-1\tsupport\tdonor1\t1\t1000\t+\tgrt_member-1\thash\n",
            encoding="utf-8",
        )
        (metadata / "grt_q_segments.tsv").write_text(
            "q_version\tchr\tsegment_id\tsegment_kind\tq_start\tq_end\tdataset_name\tcontig_name\tsource_start\tsource_end\torientation\tsource_card_key\tevidence_ids_json\n"
            "q2\tChr01\tq2-primary\tsource\t1\t1000\tprimary\tprimary1\t1\t1000\t+\tprimary:primary1:Chr01:normal\t[]\n",
            encoding="utf-8",
        )
        (metadata / "grt_evidence_registry.tsv").write_text(
            "evidence_id\tevidence_type\tstatus\tq_version\tsource_dataset\tsource_contig\tpreset\traw_artifact_relpath\n"
            "ev-mummer\tmummer_structural_correction\tsuperseded\tq2\tsupport\tdonor1\tmummer-profile\tgrt/evidence/step3/mummer/result.coords\n"
            "ev-local\tcorrected_gap_flank_refill\taccepted\tq2\tsupport\tdonor1\tasm5\tgrt/evidence/step3/refill/round1/result.paf\n",
            encoding="utf-8",
        )
        (root / "grt/evidence/step3/correction_candidates.tsv").write_text(
            "candidate_id\tevent_id\tstage\tchr\tmember_id\tsource_dataset\tsource_contig\toutcome\tleft_line\tright_line\n"
            "correction-1\tevent-precursor\tstep3\tChr01\tmember-1\tsupport\tdonor1\taccepted\t10\t11\n",
            encoding="utf-8",
        )
        (root / "grt/evidence/step3/refill_candidates.tsv").write_text(
            "candidate_id\tevent_id\tstage\tchr\tobject_id\tmember_id\tsource_dataset\tsource_contig\toutcome\tleft_line\tright_line\n"
            "refill-1\tevent-final\tstep3\tChr01\tgap-1\tmember-1\tsupport\tdonor1\taccepted\t1\t2\n",
            encoding="utf-8",
        )
        (mummer / "alignments.tsv").write_text(
            "stage\tchr\tline_number\tmember_id\tsource_dataset\tsource_contig\tref_start\tref_end\tquery_start\tquery_end\torientation\tidentity\n"
            "step3\tChr01\t10\tmember-1\tsupport\tdonor1\t401\t500\t221\t320\t+\t0.999\n"
            "step3\tChr01\t11\tmember-1\tsupport\tdonor1\t501\t600\t401\t500\t+\t0.998\n",
            encoding="utf-8",
        )
        (refill / "result.paf").write_text(
            "flank__gap-1__L\t100\t20\t100\t+\tgrt_member-1\t1000\t420\t500\t79\t81\t60\n"
            "flank__gap-1__R\t100\t0\t90\t+\tgrt_member-1\t1000\t510\t600\t88\t91\t60\n",
            encoding="utf-8",
        )
        final_path = {
            "chromosomes": [
                {
                    "chr": "Chr01",
                    "segments": [
                        {
                            "segment_id": "left",
                            "kind": "source",
                            "source": {
                                "dataset": "primary",
                                "contig": "primary1",
                                "start": 1,
                                "end": 320,
                                "orientation": "+",
                            },
                        },
                        {
                            "segment_id": "patch",
                            "kind": "patch",
                            "event_id": "event-final",
                            "source": {
                                "dataset": "support",
                                "contig": "donor1",
                                "start": 501,
                                "end": 510,
                                "orientation": "+",
                            },
                        },
                        {
                            "segment_id": "right",
                            "kind": "source",
                            "source": {
                                "dataset": "primary",
                                "contig": "primary1",
                                "start": 501,
                                "end": 1000,
                                "orientation": "+",
                            },
                        },
                    ],
                }
            ]
        }
        source_lengths = {("primary", "primary1"): 1000, ("support", "donor1"): 1000}
        cards = {
            ("primary", "primary1", "Chr01"),
            ("support", "donor1", "Chr01"),
        }

        projected = build_display_evidence(root, final_path, source_lengths, cards)["Chr01"]

        self.assertEqual(len(projected), 4)
        self.assertEqual({row["tool"] for row in projected}, {"mummer", "minimap2"})
        self.assertEqual({row["role"] for row in projected}, {"left_anchor", "right_anchor"})
        local_left = next(
            row for row in projected if row["tool"] == "minimap2" and row["role"] == "left_anchor"
        )
        self.assertEqual(local_left["source"]["start"], 421)
        self.assertEqual(local_left["target"], {
            "dataset": "primary",
            "contig": "primary1",
            "start": 241,
            "end": 320,
            "orientation": "+",
        })
        mummer_left = next(
            row for row in projected if row["tool"] == "mummer" and row["role"] == "left_anchor"
        )
        self.assertEqual(mummer_left["association"], "supporting_precursor")
        self.assertEqual(mummer_left["target"]["start"], 221)

    def test_build_rejects_final_path_source_without_display_card(self) -> None:
        assignments = self.source / "metadata/chr_assignments.tsv"
        with assignments.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = [row for row in reader if row["dataset_name"] != "primary"]
            fieldnames = list(reader.fieldnames or [])
        with assignments.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

        with self.assertRaisesRegex(ValueError, "no App display source card for primary:primary1:Chr01"):
            grt_app_package.build(self.source, self.root / "staging", include_fasta=False)

    def test_build_rejects_invalid_display_source_interval(self) -> None:
        final_path_file = self.source / "metadata/grt_final_path.json"
        payload = json.loads(final_path_file.read_text(encoding="utf-8"))
        payload["chromosomes"][0]["segments"][0]["source"]["end"] = 5
        final_path_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="",
        )

        with self.assertRaisesRegex(ValueError, "invalid App source interval"):
            grt_app_package.build(self.source, self.root / "staging", include_fasta=False)


if __name__ == "__main__":
    unittest.main()
