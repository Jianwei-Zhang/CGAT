import csv
import hashlib
import json
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
    reads_qc_thread_plan,
    run_command,
)
from server.tools.run_outer_checkpoints import OuterCheckpointManager


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
    def test_failed_command_preserves_bounded_diagnostics_after_temp_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            with self.assertRaises(SystemExit) as raised:
                run_command(
                    [
                        sys.executable,
                        "-c",
                        "import sys; print('probe stdout'); "
                        "sys.stderr.write('old-output\\n' * 2000 + "
                        "'GLIBCXX_3.4.29 not found\\n'); sys.exit(7)",
                    ],
                    root,
                    root / "meryl_count",
                )
        message = str(raised.exception)
        self.assertIn("command failed (7)", message)
        self.assertIn("GLIBCXX_3.4.29 not found", message)
        self.assertIn("probe stdout", message)
        self.assertLess(message.count("old-output"), 25)

    def test_positive_infinite_qv_is_not_converted_to_failed_zero_quality(self):
        import math
        from server.tools.lgz_prepare_inputs import parse_merqury_qv
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quality.qv"
            path.write_text("contig 0 1000 +inf\n")
            value = parse_merqury_qv(path)["contig"]
            self.assertTrue(math.isinf(value))
            self.assertGreater(value, 30)

    def test_reads_qc_thread_plan_caps_and_distributes_total_budget(self):
        with mock.patch.object(
            os, "sched_getaffinity", return_value=set(range(12)), create=True
        ):
            self.assertEqual(reads_qc_thread_plan(10, 3), (3, [4, 3, 3], 10))
            self.assertEqual(reads_qc_thread_plan(20, 2), (2, [6, 6], 12))
            self.assertEqual(reads_qc_thread_plan(4, 6), (4, [1, 1, 1, 1, 1, 1], 4))

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
                    # This fixture invokes the current producer; schema 2 is
                    # supported only by frozen historical delivery fixtures.
                    "schema_version": "4",
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
                {"key": "threads", "value": "10"},
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
        from server.tests.q0_test_support import seed_q0_evidence
        seed_q0_evidence(server)
        return subprocess.run(
            [sys.executable, str(TOOL), "--server-dir", str(server), *map(str, extra)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_no_reads_builds_traceable_q0_and_frozen_global_donors(self):
        from server.tests.test_q0_admission import bridge_fixture
        from server.tests.test_q0_publication import complete_workspace
        from server.tools.lgz_core.q0_publication import validate_prepared_q0
        with tempfile.TemporaryDirectory() as temporary_dir:
            fixture, truth = bridge_fixture()
            server = complete_workspace(fixture, Path(temporary_dir))
            completed = self.run_tool(server)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            lines = [line for line in completed.stdout.splitlines() if line.startswith("LGZ prepare phase: ")]
            self.assertEqual([line.split(" ·")[0] for line in lines], [
                "LGZ prepare phase: loading Q0 alignment evidence", "LGZ prepare phase: placing candidate segments",
                "LGZ prepare phase: building chromosome paths", "LGZ prepare phase: chromosome path 1/1: chr1",
                "LGZ prepare phase: reconstructing Q0 sequences and recording decisions",
                "LGZ prepare phase: writing Q0 and freezing ordinary and telomere donors",
            ])
            from server.tools.lgz_core.common import read_fasta
            self.assertEqual(dict(read_fasta(server / "grt/q/q0.fa")), {"chr1": truth})
            frozen = validate_prepared_q0(server)
            self.assertEqual(frozen["package_schema_version"], "4")
            roles = {row["contig_name"]: row for row in read_tsv(server / "metadata/grt_contig_roles.tsv")}
            self.assertEqual(roles["a"]["donor_eligible"], "true")
            self.assertTrue(all(row["stage"] == "q0_construction" for row in read_tsv(server / "metadata/grt_evidence_registry.tsv")))
            before = sha256(server / "grt/q/q0.fa")
            repeated = self.run_tool(server)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertIn("are current", repeated.stdout)
            self.assertNotIn("placing candidate segments", repeated.stdout)
            for unit_id in ("grt_prepare", "lgz_prepare"):
                valid, reason = OuterCheckpointManager(server).validate_lgz_unit(unit_id)
                self.assertTrue(valid, reason)
            self.assertEqual(sha256(server / "grt/q/q0.fa"), before)

    def test_q0_uses_interval_alignment_orientation_not_whole_assignment(self):
        from server.tests.test_q0_admission import bridge_fixture
        from server.tests.test_q0_publication import complete_workspace
        with tempfile.TemporaryDirectory() as temporary_dir:
            fixture, truth = bridge_fixture(reverse=True)
            server = complete_workspace(fixture, Path(temporary_dir))
            path = server / "metadata/chr_assignments.tsv"
            assignments = read_tsv(path)
            next(row for row in assignments if row["seq_name"] == "c")["source_orientation"] = "+"
            write_tsv(path, list(assignments[0]), assignments)
            original = path.read_bytes()
            completed = self.run_tool(server)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            row = next(row for row in read_tsv(server / "metadata/grt_q_segments.tsv") if row["contig_name"] == "c")
            self.assertEqual(row["orientation"], "-")
            self.assertEqual(path.read_bytes(), original)

    def test_reads_default_skips_craq_and_full_mode_runs_it(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            from server.tests.test_q0_admission import EvidenceFixture, dna
            from server.tests.test_q0_publication import complete_workspace
            fixture = EvidenceFixture()
            genome = dna(5000)
            for name, dataset, start, end in (("p_cover", "primary", 0, 1800),
                                               ("p_redundant", "primary", 2000, 3100),
                                               ("s_assigned", "support", 3500, 5000)):
                sequence = genome[start:end]
                aligned_length = end - start
                if name == "p_redundant":
                    # A real terminal repeat must not bypass failed read QC
                    # when freezing the otherwise eligible Dtel context.
                    sequence = sequence[:-560] + "TTTAGGG" * 80
                    aligned_length -= 560
                source = fixture.source(name, sequence, dataset=dataset)
                fixture.ref(source, (0, aligned_length), (start, start + aligned_length))
            server = complete_workspace(fixture, root)
            package = read_tsv(server / "metadata/package.tsv")
            package[0]["reads_qc_enabled"] = "true"
            write_tsv(server / "metadata/package.tsv", list(package[0]), package)
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
dataset="$(basename "$(dirname "$PWD")")"
printf 'merqury-start:%s:%s\\n' "$dataset" "${OMP_NUM_THREADS:-unset}" >> "$FAKE_QC_LOG"
sleep 0.3
awk '/^>/ { sub(/^>/, "", $1); qv = ($1 == "p_redundant" ? 20 : 35); print $1 " 0 0 " qv }' contigs.fasta > merqury_out.contigs.qv
printf 'merqury-end:%s\\n' "$dataset" >> "$FAKE_QC_LOG"
""",
                encoding="utf-8",
            )
            (fake_bin / "craq").write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--version" ]]; then echo 'craq fixture 1'; exit 0; fi
genome=''
reads=''
out=''
threads=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    -g) genome="$2"; shift 2 ;;
    -sms) reads="$2"; shift 2 ;;
    -t) threads="$2"; shift 2 ;;
    -o) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
dataset="$(basename "$out")"
printf 'craq-start:%s:%s:%s\\n' "$dataset" "$threads" "${OMP_NUM_THREADS:-unset}" >> "$FAKE_QC_LOG"
sleep 0.3
mkdir -p "$(dirname "$out")/runAQI_out"
mkdir -p "$out"
ln -s "$reads" "$out/$(basename "$reads")"
report="$(dirname "$out")/runAQI_out/out_final.Report"
printf '#Chr\\tCovered.Rate\\tLow-confident.Rate\\tAvg.CRH\\tAvg.CSH\\tAvg.CRE(R-AQI)\\tAvg.CSE(S-AQI)\\n' > "$report"
awk '/^>/ { sub(/^>/, "", $1); print $1 " 1 0 0 0 0.1(98.5) 0(100)" }' "$genome" >> "$report"
printf 'craq-end:%s\\n' "$dataset" >> "$FAKE_QC_LOG"
""",
                encoding="utf-8",
            )
            for executable in fake_bin.iterdir():
                executable.chmod(0o755)
            env = os.environ.copy()
            env["FAKE_QC_LOG"] = str(log)
            _, thread_allocations, _ = reads_qc_thread_plan(10, 2)
            dataset_threads = dict(zip(("primary", "support"), thread_allocations))
            standard = self.run_tool(
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
            self.assertEqual(standard.returncode, 0, standard.stderr)
            standard_log = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(standard_log[0], "meryl")
            self.assertEqual(
                set(standard_log[1:3]),
                {
                    f"merqury-start:{dataset}:{threads}"
                    for dataset, threads in dataset_threads.items()
                },
            )
            self.assertEqual(
                set(standard_log[3:5]),
                {"merqury-end:primary", "merqury-end:support"},
            )
            standard_quality = read_tsv(server / "metadata/grt_contig_quality.tsv")
            self.assertTrue(all(row["craq"] == "" for row in standard_quality))

            completed = self.run_tool(
                server,
                "--reads",
                reads,
                "--reads-qc",
                "full",
                "--meryl",
                fake_bin / "meryl",
                "--merqury",
                fake_bin / "merqury.sh",
                "--craq",
                fake_bin / "craq",
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            full_log = log.read_text(encoding="utf-8").splitlines()[len(standard_log):]
            self.assertEqual(full_log[0], "meryl")
            self.assertEqual(
                {line for line in full_log if line.startswith("merqury-start:")},
                {
                    f"merqury-start:{dataset}:{threads}"
                    for dataset, threads in dataset_threads.items()
                },
            )
            self.assertEqual(
                {line for line in full_log if line.startswith("craq-start:")},
                {
                    f"craq-start:{dataset}:{threads}:{threads}"
                    for dataset, threads in dataset_threads.items()
                },
            )
            craq_start_indexes = [
                index for index, line in enumerate(full_log) if line.startswith("craq-start:")
            ]
            craq_end_indexes = [
                index for index, line in enumerate(full_log) if line.startswith("craq-end:")
            ]
            self.assertLess(max(craq_start_indexes), min(craq_end_indexes))
            quality = read_tsv(server / "metadata/grt_contig_quality.tsv")
            quality_by_contig = {row["contig_name"]: row for row in quality}
            self.assertEqual(quality_by_contig["p_redundant"]["qv"], "20.000000")
            self.assertEqual(quality_by_contig["p_redundant"]["reads_qc_pass"], "false")
            roles = {row["contig_name"]: row for row in read_tsv(server / "metadata/grt_contig_roles.tsv")}
            self.assertEqual(roles["p_redundant"]["tel_donor_eligible"], "false")
            self.assertEqual(roles["p_redundant"]["tel_rejection_reason"], "failed_reads_qc")
            self.assertNotIn("p_redundant", {row["contig_name"] for row in read_tsv(server / "metadata/grt_donor_members.tsv")})
            self.assertTrue(
                all(
                    row["qv"] == "35.000000"
                    for row in quality
                    if row["contig_name"] != "p_redundant"
                )
            )
            self.assertTrue(all(row["craq"] == "98.500000" for row in quality))
            self.assertFalse(any(path.is_symlink() for path in (server / "grt/qc").rglob("*")))

            legacy_link = server / "grt/qc/primary/craq_output/primary" / reads.name
            legacy_link.parent.mkdir(parents=True, exist_ok=True)
            legacy_link.symlink_to(reads)
            checkpoint_path = server / "grt/checkpoints/donor_freeze.json"
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            legacy_relpath = legacy_link.relative_to(server).as_posix()
            checkpoint["output_hashes"][legacy_relpath] = sha256(reads)
            checkpoint_path.write_text(
                json.dumps(checkpoint, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            stage_status_path = server / "metadata/grt_stage_status.tsv"
            stage_status = read_tsv(stage_status_path)
            stage_status[0]["checkpoint_sha256"] = sha256(checkpoint_path)
            write_tsv(stage_status_path, list(stage_status[0]), stage_status)
            valid, reason = OuterCheckpointManager(server).validate_grt_unit("grt_prepare")
            self.assertFalse(valid)
            self.assertIn("escapes the Server workspace", reason)
            migrated = self.run_tool(
                server,
                "--reads",
                reads,
                "--reads-qc",
                "full",
                "--meryl",
                fake_bin / "meryl",
                "--merqury",
                fake_bin / "merqury.sh",
                "--craq",
                fake_bin / "craq",
                env={**env, "GPM_RUN_THREADS": "64", "GPM_RUN_QC_MEMORY_GB": "120"},
            )
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            self.assertIn("Removed legacy external CRAQ input links", migrated.stdout)
            self.assertIn("LGZ prepare inputs are current", migrated.stdout)
            self.assertFalse(legacy_link.exists())
            migrated_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertNotIn(legacy_relpath, migrated_checkpoint["output_hashes"])
            self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 14)
            valid, reason = OuterCheckpointManager(server).validate_grt_unit("grt_prepare")
            self.assertTrue(valid, reason)

            cached = self.run_tool(
                server,
                "--reads",
                reads,
                "--reads-qc",
                "full",
                "--threads",
                "8",
                "--meryl",
                fake_bin / "meryl",
                "--merqury",
                fake_bin / "merqury.sh",
                "--craq",
                fake_bin / "craq",
                env=env,
            )
            self.assertEqual(cached.returncode, 0, cached.stderr)
            self.assertEqual(cached.stdout.count("CACHE_HIT"), 2)
            self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 14)

            next((server / "grt/qc").rglob("*.qv")).unlink()
            rebuilt = self.run_tool(
                server,
                "--reads",
                reads,
                "--reads-qc",
                "full",
                "--threads",
                "8",
                "--meryl",
                fake_bin / "meryl",
                "--merqury",
                fake_bin / "merqury.sh",
                "--craq",
                fake_bin / "craq",
                env=env,
            )
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
            self.assertIn("CACHE_HIT", rebuilt.stdout)
            self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 19)

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
