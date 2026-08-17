import csv
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).parents[2]
TOOL = REPO_ROOT / "server" / "tools" / "grt_prepare_inputs.py"
from server.tools.grt_prepare_inputs import (
    commit_prepared_outputs,
    donor_fragment_rows,
    executable_identity,
)


def write_fasta(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for name, sequence in records:
            handle.write(f">{name}\n{sequence}\n")


def write_tsv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_tsv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GrtPrepareInputsTests(unittest.TestCase):
    def write_version_tool(self, root, name, body):
        path = root / name
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_executable_identity_records_successful_version_output(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            tool = self.write_version_tool(
                Path(temporary_dir),
                "version-ok",
                "printf '\\nfixture 2.1\\nextra detail\\n'\nexit 0\n",
            )

            identity = executable_identity(str(tool))

            self.assertEqual(identity["version"], "fixture 2.1")
            self.assertEqual(identity["sha256"], sha256(tool))

    def test_executable_identity_ignores_failed_probe_error_text(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            tool = self.write_version_tool(
                Path(temporary_dir),
                "version-unsupported",
                "printf 'invalid option -- -\\n' >&2\nexit 1\n",
            )

            identity = executable_identity(str(tool))

            self.assertEqual(identity["version"], "unknown")
            self.assertEqual(identity["sha256"], sha256(tool))

    def test_donor_fragments_split_long_n_runs_without_changing_source_coordinates(self):
        sequence = "A" * 1200 + "N" * 100 + "C" * 1400
        member = {
            "donor_set_id": "d0-test",
            "member_id": "member-test",
            "dataset_name": "support",
            "contig_name": "donor",
            "source_start": 1,
            "source_end": len(sequence),
            "orientation": "+",
            "fasta_record_name": "grt_member-test",
            "sequence_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
        }
        rows = donor_fragment_rows(
            "d0-test", [member], {("support", "donor"): sequence}
        )
        self.assertEqual(
            [(int(row["fragment_start"]), int(row["fragment_end"])) for row in rows],
            [(1, 1200), (1301, 2700)],
        )
        self.assertEqual([int(row["fragment_length"]) for row in rows], [1200, 1400])
        self.assertTrue(all(row["donor_set_id"] == "d0-test" for row in rows))

    def make_server(self, root, reads_qc_enabled=False):
        server = root / "gpm_server"
        metadata = server / "metadata"
        primary_records = [
            ("p_cover", "A" * 1200),
            ("p_redundant", "C" * 1100),
            ("p_partial", "G" * 1200),
            ("p_reverse", "A" * 600 + "C" * 600),
        ]
        support_records = [
            ("s_assigned", "T" * 1500),
            ("s_unplaced", "AC" * 650),
            ("s_tel_short", "TTTAGGG" * 80),
        ]
        write_fasta(server / "data/reference/ref.fa", [("Chr01", "A" * 5000), ("Chr02", "C" * 5000)])
        write_fasta(server / "data/datasets/primary.fa", primary_records)
        write_fasta(server / "data/datasets/support.fa", support_records)
        for relpath in (
            "data/reference/ref.fa.fai",
            "data/datasets/primary.fa.fai",
            "data/datasets/support.fa.fai",
        ):
            path = server / relpath
            path.write_text("fixture\n", encoding="utf-8")

        write_tsv(
            metadata / "package.tsv",
            [
                "workflow",
                "schema_version",
                "package_mode",
                "sequence_layout",
                "preassigned_chr",
                "self_alignment_scope",
                "cross_alignment_scope",
                "chr_assignment_min_coverage_percent",
                "grt_precompute_enabled",
                "recipe_locked",
                "final_path_schema_version",
                "reads_qc_enabled",
            ],
            [
                {
                    "workflow": "gpm_grt_precomputed_v2",
                    "schema_version": "2",
                    "package_mode": "fast",
                    "sequence_layout": "partitioned",
                    "preassigned_chr": "true",
                    "self_alignment_scope": "chr_partition",
                    "cross_alignment_scope": "chr_partition",
                    "chr_assignment_min_coverage_percent": "60",
                    "grt_precompute_enabled": "true",
                    "recipe_locked": "true",
                    "final_path_schema_version": "1",
                    "reads_qc_enabled": str(reads_qc_enabled).lower(),
                }
            ],
        )
        write_tsv(
            metadata / "reference.tsv",
            ["reference_name", "species_name", "assembly_label", "fasta_relpath", "fai_relpath"],
            [
                {
                    "reference_name": "ref",
                    "species_name": "unknown",
                    "assembly_label": "ref",
                    "fasta_relpath": "data/reference/ref.fa",
                    "fai_relpath": "data/reference/ref.fa.fai",
                }
            ],
        )
        datasets = []
        for name in ("primary", "support"):
            datasets.append(
                {
                    "dataset_name": name,
                    "assembler": name,
                    "assembler_version": "",
                    "fasta_relpath": f"data/datasets/{name}.fa",
                    "fai_relpath": f"data/datasets/{name}.fa.fai",
                    "self_alignment_available": "true",
                }
            )
        write_tsv(
            metadata / "datasets.tsv",
            [
                "dataset_name",
                "assembler",
                "assembler_version",
                "fasta_relpath",
                "fai_relpath",
                "self_alignment_available",
            ],
            datasets,
        )
        write_tsv(
            metadata / "prepare_options.tsv",
            ["key", "value"],
            [
                {"key": "alignment_engine", "value": "minimap2"},
                {"key": "minimap_preset", "value": "asm10"},
                {"key": "chr_assignment_min_coverage_percent", "value": "60"},
            ],
        )
        assignments = [
            ("p_cover", 1200, "Chr01", 1200, 1),
            ("p_redundant", 1100, "Chr01", 1000, 101),
            ("p_partial", 1200, "Chr01", 1200, 2001),
            ("p_reverse", 1200, "Chr02", 1200, 100),
        ]
        write_tsv(
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
                    "support_percent": f"{support * 100 / length:.3f}",
                    "anchor_start": anchor,
                }
                for name, length, chromosome, support, anchor in assignments
            ],
        )
        write_tsv(
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
                for index, (name, _length, chromosome, _support, _anchor) in enumerate(assignments, start=1)
            ],
        )
        write_tsv(
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
        primary_paf = server / "runs/primary_vs_ref/result.paf"
        primary_paf.parent.mkdir(parents=True)
        primary_paf.write_text(
            "\n".join(
                [
                    "p_cover\t1200\t0\t1200\t+\tChr01\t5000\t0\t1200\t1200\t1200\t60",
                    "p_redundant\t1100\t0\t1000\t+\tChr01\t5000\t100\t1100\t1000\t1000\t60",
                    "p_partial\t1200\t0\t1200\t+\tChr01\t5000\t2000\t3200\t1200\t1200\t60",
                    "p_reverse\t1200\t0\t1200\t-\tChr02\t5000\t99\t1299\t1200\t1200\t60",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (primary_paf.parent / "tool_version.txt").write_text(
            "minimap2 fixture 1\n", encoding="utf-8", newline=""
        )
        support_paf = server / "runs/support_vs_ref/result.paf"
        support_paf.parent.mkdir(parents=True)
        support_paf.write_text(
            "s_assigned\t1500\t0\t1500\t+\tChr01\t5000\t3000\t4500\t1500\t1500\t60\n",
            encoding="utf-8",
        )
        (support_paf.parent / "tool_version.txt").write_text(
            "minimap2 fixture 1\n", encoding="utf-8", newline=""
        )
        return server

    def run_tool(self, server, *extra, env=None):
        return subprocess.run(
            [sys.executable, str(TOOL), "--server-dir", str(server), *map(str, extra)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_no_reads_builds_traceable_q0_and_frozen_global_donors(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            server = self.make_server(Path(temporary_dir))
            completed = self.run_tool(server)
            self.assertEqual(completed.returncode, 0, completed.stderr)

            q0 = (server / "grt/q/q0.fa").read_text(encoding="utf-8")
            self.assertEqual(
                sha256(server / "grt/q/q0.fa"),
                "e736adbe311565c992046974c889ea48fe9a94605595b9223e84f64d9ee0220e",
            )
            self.assertIn("A" * 80, q0)
            self.assertIn("N" * 80, q0)
            self.assertIn("G" * 80, q0)
            self.assertIn("G" * 80 + "\n", q0)  # reverse-complemented p_reverse starts with G

            q_rows = read_tsv(server / "metadata/grt_q_segments.tsv")
            self.assertEqual([row["segment_kind"] for row in q_rows if row["chr"] == "Chr01"], ["source", "gap", "source"])
            gap = next(row for row in q_rows if row["segment_kind"] == "gap")
            self.assertEqual(int(gap["q_end"]) - int(gap["q_start"]) + 1, 100)
            reverse = next(row for row in q_rows if row["contig_name"] == "p_reverse")
            self.assertEqual(reverse["orientation"], "-")
            evidence = read_tsv(server / "metadata/grt_evidence_registry.tsv")
            self.assertTrue(all(row["tool_version"] == "minimap2 fixture 1" for row in evidence))

            roles = {(row["dataset_name"], row["contig_name"]): row for row in read_tsv(server / "metadata/grt_contig_roles.tsv")}
            self.assertEqual(roles[("primary", "p_redundant")]["q_eligible"], "false")
            self.assertTrue(roles[("primary", "p_redundant")]["q_rejection_reason"].startswith("ref_footprint_covered_by:"))
            self.assertEqual(roles[("support", "s_unplaced")]["donor_eligible"], "true")
            self.assertEqual(roles[("support", "s_tel_short")]["tel_donor_eligible"], "true")

            recipe = read_tsv(server / "metadata/grt_recipe.tsv")[0]
            ordinary = [
                row
                for row in read_tsv(server / "metadata/grt_donor_members.tsv")
                if row["donor_set_id"] == recipe["donor_set_id"]
            ]
            self.assertEqual(
                [(row["dataset_name"], row["contig_name"]) for row in ordinary],
                [("support", "s_assigned"), ("support", "s_unplaced"), ("primary", "p_redundant")],
            )
            self.assertNotIn("p_cover", {row["contig_name"] for row in ordinary})
            fragments = read_tsv(server / "metadata/grt_donor_fragments.tsv")
            self.assertEqual(
                {row["member_id"] for row in fragments},
                {row["member_id"] for row in ordinary},
            )

            ordinary_set = next(
                row
                for row in read_tsv(server / "metadata/grt_donor_sets.tsv")
                if row["donor_set_id"] == recipe["donor_set_id"]
            )
            self.assertEqual(
                sha256(server / ordinary_set["fasta_relpath"]),
                "a15c5b2a58c751b60c77ddb332db7c5036574bbc8697e224dbbe1e5ad58f1f63",
            )
            tracked = [
                server / "grt/q/q0.fa",
                server / ordinary_set["fasta_relpath"],
                server / "metadata/grt_donor_sets.tsv",
                server / "metadata/grt_donor_fragments.tsv",
                server / "metadata/grt_q_segments.tsv",
            ]
            before = {path: sha256(path) for path in tracked}
            repeated = self.run_tool(server)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertIn("are current", repeated.stdout)
            self.assertEqual(before, {path: sha256(path) for path in tracked})

            stale_stage = server / "grt/stages/old/result.txt"
            stale_stage.parent.mkdir(parents=True)
            stale_stage.write_text("stale\n", encoding="utf-8")
            stale_metadata = server / "metadata/grt_events.jsonl"
            stale_metadata.write_text("{}\n", encoding="utf-8")
            with (server / "runs/primary_vs_ref/result.paf").open(
                "a", encoding="utf-8", newline=""
            ) as handle:
                handle.write("# input hash changed\n")
            rebuilt = self.run_tool(server)
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
            self.assertNotIn("are current", rebuilt.stdout)
            self.assertFalse(stale_stage.exists())
            self.assertFalse(stale_metadata.exists())

    def test_q0_consumes_assignment_orientation_without_recomputing_paf_strand(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            server = self.make_server(Path(temporary_dir))
            assignments_path = server / "metadata/chr_assignments.tsv"
            assignments = read_tsv(assignments_path)
            reverse = next(row for row in assignments if row["seq_name"] == "p_reverse")
            reverse["source_orientation"] = "+"
            write_tsv(assignments_path, list(assignments[0]), assignments)

            completed = self.run_tool(server)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            q_rows = read_tsv(server / "metadata/grt_q_segments.tsv")
            reverse_q0 = next(row for row in q_rows if row["contig_name"] == "p_reverse")
            self.assertEqual(reverse_q0["orientation"], "+")

    def test_reads_run_one_meryl_and_per_dataset_merqury_craq(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server = self.make_server(root, reads_qc_enabled=True)
            reads = root / "reads.fastq"
            reads.write_text("@r1\nACGT\n+\n!!!!\n", encoding="utf-8")
            fake_bin = root / "bin"
            fake_bin.mkdir()
            log = root / "qc.log"

            (fake_bin / "meryl").write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--version" ]]; then echo 'meryl fixture 1'; exit 0; fi
printf 'meryl\\n' >> "$FAKE_QC_LOG"
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "output" ]]; then mkdir -p "$2"; exit 0; fi
  shift
done
exit 1
""",
                encoding="utf-8",
            )
            (fake_bin / "merqury.sh").write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--version" ]]; then echo 'merqury fixture 1'; exit 0; fi
printf 'merqury\\n' >> "$FAKE_QC_LOG"
awk '/^>/ { sub(/^>/, "", $1); qv = ($1 == "p_redundant" ? 20 : 35); print $1 " 0 0 " qv }' contigs.fasta > merqury_out.contigs.qv
""",
                encoding="utf-8",
            )
            (fake_bin / "craq").write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--version" ]]; then echo 'craq fixture 1'; exit 0; fi
printf 'craq\\n' >> "$FAKE_QC_LOG"
genome=''
out=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    -g) genome="$2"; shift 2 ;;
    -o) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
mkdir -p "$(dirname "$out")/runAQI_out"
report="$(dirname "$out")/runAQI_out/out_final.Report"
printf '#Chr\\tCovered.Rate\\tLow-confident.Rate\\tAvg.CRH\\tAvg.CSH\\tAvg.CRE(R-AQI)\\tAvg.CSE(S-AQI)\\n' > "$report"
awk '/^>/ { sub(/^>/, "", $1); print $1 " 1 0 0 0 0.1(98.5) 0(100)" }' "$genome" >> "$report"
""",
                encoding="utf-8",
            )
            for executable in fake_bin.iterdir():
                executable.chmod(0o755)
            env = os.environ.copy()
            env["FAKE_QC_LOG"] = str(log)
            completed = self.run_tool(
                server,
                "--reads",
                reads,
                "--meryl",
                fake_bin / "meryl",
                "--merqury",
                fake_bin / "merqury.sh",
                "--craq",
                fake_bin / "craq",
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), ["meryl", "merqury", "craq", "merqury", "craq"])
            quality = read_tsv(server / "metadata/grt_contig_quality.tsv")
            quality_by_contig = {row["contig_name"]: row for row in quality}
            self.assertEqual(quality_by_contig["p_redundant"]["qv"], "20.000000")
            self.assertEqual(quality_by_contig["p_redundant"]["reads_qc_pass"], "false")
            self.assertTrue(
                all(
                    row["qv"] == "35.000000"
                    for row in quality
                    if row["contig_name"] != "p_redundant"
                )
            )
            self.assertTrue(all(row["craq"] == "98.500000" for row in quality))
            next((server / "grt/qc").rglob("*.qv")).unlink()
            rebuilt = self.run_tool(
                server,
                "--reads",
                reads,
                "--meryl",
                fake_bin / "meryl",
                "--merqury",
                fake_bin / "merqury.sh",
                "--craq",
                fake_bin / "craq",
                env=env,
            )
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
            self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 10)

    def test_atomic_publish_restores_previous_outputs_when_metadata_install_fails(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server = root / "gpm_server"
            old_grt = server / "grt"
            old_metadata = server / "metadata"
            old_grt.mkdir(parents=True)
            old_metadata.mkdir(parents=True)
            (old_grt / "old.txt").write_text("old-grt\n", encoding="utf-8")
            (old_metadata / "grt_old.tsv").write_text("old-metadata\n", encoding="utf-8")
            (old_metadata / "package.tsv").write_text("keep\n", encoding="utf-8")

            stage_root = root / "stage"
            stage_grt = stage_root / "grt"
            stage_metadata = stage_root / "metadata"
            stage_grt.mkdir(parents=True)
            stage_metadata.mkdir(parents=True)
            (stage_grt / "new.txt").write_text("new-grt\n", encoding="utf-8")
            (stage_metadata / "grt_new.tsv").write_text("new-metadata\n", encoding="utf-8")

            real_replace = os.replace
            injected = False

            def fail_once_during_metadata_install(source, destination):
                nonlocal injected
                if Path(source).name == "grt_new.tsv" and not injected:
                    injected = True
                    raise OSError("injected metadata install failure")
                return real_replace(source, destination)

            with mock.patch(
                "server.tools.grt_prepare_inputs.os.replace",
                side_effect=fail_once_during_metadata_install,
            ):
                with self.assertRaisesRegex(OSError, "injected metadata install failure"):
                    commit_prepared_outputs(stage_grt, stage_metadata, server)

            self.assertEqual((server / "grt/old.txt").read_text(encoding="utf-8"), "old-grt\n")
            self.assertFalse((server / "grt/new.txt").exists())
            self.assertEqual(
                (server / "metadata/grt_old.tsv").read_text(encoding="utf-8"),
                "old-metadata\n",
            )
            self.assertFalse((server / "metadata/grt_new.tsv").exists())
            self.assertEqual(
                (server / "metadata/package.tsv").read_text(encoding="utf-8"),
                "keep\n",
            )

    def test_rejects_v1_package_instead_of_falling_back(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            server = self.make_server(Path(temporary_dir))
            package = server / "metadata/package.tsv"
            package.write_text(
                package.read_text(encoding="utf-8").replace(
                    "gpm_grt_precomputed_v2", "gpm_grt_precomputed_v1", 1
                ),
                encoding="utf-8",
                newline="",
            )
            completed = self.run_tool(server)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("unsupported package workflow/schema", completed.stderr)


if __name__ == "__main__":
    unittest.main()
