#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch contig-end TelSeeker workflow."""

import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord


STATUS_FIELDS = [
    "ctg_file",
    "ctg_id",
    "safe_ctg_id",
    "end",
    "job_dir",
    "status",
    "connection_type",
    "connected_read",
    "round_num",
    "seed_length",
    "extension_length",
    "original_length",
    "final_length",
    "stop_reason",
]


def _normalize_file_list(values) -> List[str]:
    if not values:
        return []
    if isinstance(values, (list, tuple)):
        return [str(Path(v).resolve()) for v in values if v]
    return [str(Path(values).resolve())]


def _manifest_payload(read_inputs: Dict, motif: str, tel_params: Dict) -> Dict:
    return {
        "hifi": _normalize_file_list(read_inputs.get("hifi")),
        "ont": _normalize_file_list(read_inputs.get("ont")),
        "motif": motif,
        "tel_n": int(tel_params.get("tel_n", 100)),
        "tel_r": float(tel_params.get("tel_r", 0.6)),
        "tel_mm": int(tel_params.get("tel_mm", 0)),
    }


def validate_shared_manifest_compatibility(out_dir, read_inputs: Dict, motif: str, tel_params: Dict):
    """Reject incompatible reuse of an existing telseeker_ctg output directory."""
    out_path = Path(out_dir)
    manifest_file = out_path / "telseeker_ctg.input" / "cache_manifest.json"
    if not manifest_file.exists():
        return

    try:
        existing = json.loads(manifest_file.read_text())
    except Exception as exc:
        raise ValueError(f"Could not read existing telseeker_ctg cache manifest: {manifest_file}: {exc}")

    requested = _manifest_payload(read_inputs, motif, tel_params)
    conflicts = []
    for key, requested_value in requested.items():
        existing_value = existing.get(key)
        if existing_value != requested_value:
            conflicts.append((key, existing_value, requested_value))

    if not conflicts:
        return

    lines = [
        "Existing telseeker_ctg workspace is incompatible with this run.",
        f"Output directory: {out_path}",
        "",
        "Conflicts:",
    ]
    for key, existing_value, requested_value in conflicts:
        lines.append(f"  {key}:")
        lines.append(f"    existing: {existing_value}")
        lines.append(f"    requested: {requested_value}")
    lines.extend([
        "",
        "Use a new --out directory, or manually clear the old telseeker_ctg workspace.",
    ])
    raise ValueError("\n".join(lines))


def _safe_id(record_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", record_id).strip("._")
    return safe or "ctg"


def _count_fasta_records(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path) as handle:
        return sum(1 for _ in SeqIO.parse(handle, "fasta"))


def _read_first_record(path: Path):
    with open(path) as handle:
        records = list(SeqIO.parse(handle, "fasta"))
    if len(records) != 1:
        raise ValueError(f"--ctg requires exactly one FASTA record: {path} has {len(records)}")
    return records[0]


def _read_single_fasta_seq(path: Path):
    with open(path) as handle:
        record = next(SeqIO.parse(handle, "fasta"))
    return record.seq


class TelSeekerCtg:
    """Run TelSeeker extension for one or more contig endpoints."""

    def __init__(self, parameter: list, kparameters: list):
        if len(parameter) < 23:
            raise ValueError(f"Expected at least 23 parameters, got {len(parameter)}")

        self.mode = parameter[0]
        if self.mode != "telseeker_ctg":
            raise ValueError(f"Invalid mode for TelSeekerCtg: {self.mode}")

        self.remove = parameter[1]
        self.thread = int(parameter[2]) if parameter[2] else 20
        self.reads = parameter[3]
        self.out = Path(parameter[4])
        self.ctg_inputs = parameter[5]
        self.motif = parameter[6]
        self.work = int(parameter[7]) if parameter[7] else 1
        self.edge = parameter[8]
        self.MaximumExtensionLength = parameter[11]
        self.MaximumExtensionRound = parameter[12]
        self.data_type = parameter[13]
        self.ont_reads = parameter[14]
        self.tel_params = parameter[15]
        self.read_inputs = parameter[16]
        self.readsDict = parameter[17]
        self.maxReadsLen = parameter[18]
        self.hifiSeedLen = parameter[19]
        self.ontSeedLen = parameter[20]
        self.original_reads_info = parameter[21]
        self.ont_readsdict = parameter[22]

        self.kmer_size = kparameters[0]
        self.kmer_num = kparameters[1]
        self.kmer_filter = kparameters[2] if len(kparameters) >= 3 else False

        self.input_dir = self.out / "telseeker_ctg.input"
        self.jobs_dir = self.out / "telseeker_ctg.jobs"
        self.aggregate_result_dir = self.out / "result"
        self.part1_dir = self.out / "part1.telo.reads"
        self.ctgs_fasta = self.input_dir / "ctgs.fa"
        self.tasks_tsv = self.input_dir / "ctg_tasks.tsv"
        self.manifest_file = self.input_dir / "cache_manifest.json"
        self.need_extension_file = self.out / "genome.telomere.check" / "need_extension_chr_end.txt"

        self.tasks = []
        self.status_rows = []

    def run(self):
        print("\n" + "=" * 80)
        print("Starting TelSeeker Ctg Endpoint Workflow")
        print("=" * 80 + "\n")

        self._validate_parameters()
        self._prepare_task_inputs()
        self._ensure_manifest()
        self._extract_telomeric_reads_once()
        runnable = self._classify_tel_read_availability()
        if runnable:
            self._run_part2_for_tasks(runnable)
            self._collect_runnable_results(runnable)
        self._write_aggregate_status()

        print("\n" + "=" * 80)
        print("TelSeeker Ctg Endpoint Workflow Completed")
        print("=" * 80)
        print(f"Output directory: {self.out}")
        print(f"Aggregate status: {self.aggregate_result_dir / 'status.tsv'}")
        print("=" * 80 + "\n")

    def _validate_parameters(self):
        if not self.ctg_inputs:
            raise ValueError("telseeker_ctg requires one or more --ctg <fasta> <L|R> entries")
        if not self.motif or not all(c in "ACGT" for c in self.motif):
            raise ValueError(f"Invalid motif: {self.motif}")
        if self.work <= 0:
            raise ValueError(f"Invalid work parameter: {self.work}")
        if self.thread <= 0:
            raise ValueError(f"Invalid thread count: {self.thread}")
        if self.edge < 0:
            raise ValueError(f"Invalid edge: {self.edge}")
        if self.tel_params["tel_n"] <= 0:
            raise ValueError("tel-n must be greater than 0")
        if not (0 < self.tel_params["tel_r"] <= 1):
            raise ValueError("tel-r must be in the interval (0, 1]")
        if self.tel_params["tel_mm"] not in [0, 1]:
            raise ValueError("tel-mm must be 0 or 1")

    def _prepare_task_inputs(self):
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.aggregate_result_dir.mkdir(parents=True, exist_ok=True)

        seen = set()
        tasks = []
        records = []
        for ctg_file, end in self.ctg_inputs:
            end = end.upper()
            if end not in {"L", "R"}:
                raise ValueError(f"Invalid --ctg endpoint '{end}' for {ctg_file}; expected L or R")
            ctg_path = Path(ctg_file)
            if not ctg_path.exists() or ctg_path.stat().st_size == 0:
                raise FileNotFoundError(f"Contig FASTA not found or empty: {ctg_path}")

            record = _read_first_record(ctg_path)
            safe_ctg_id = _safe_id(record.id)
            chr_end = f"{safe_ctg_id}.{end}"
            if chr_end in seen:
                raise ValueError(f"Duplicate telseeker_ctg endpoint in this run: {chr_end}")
            seen.add(chr_end)

            job_dir = self.jobs_dir / chr_end
            task = {
                "ctg_file": str(ctg_path),
                "ctg_id": record.id,
                "safe_ctg_id": safe_ctg_id,
                "end": end,
                "chr_end": chr_end,
                "job_dir": str(job_dir),
                "original_length": len(record.seq),
                "seq": record.seq,
            }
            tasks.append(task)
            records.append(SeqRecord(record.seq, id=safe_ctg_id, description=f"original_id={record.id}"))

        SeqIO.write(records, self.ctgs_fasta, "fasta")
        self._write_tasks_tsv(tasks)
        self.tasks = tasks

    def _write_tasks_tsv(self, tasks):
        with open(self.tasks_tsv, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["ctg_file", "ctg_id", "safe_ctg_id", "end", "chr_end", "job_dir", "original_length"],
                delimiter="\t",
            )
            writer.writeheader()
            for task in tasks:
                writer.writerow({k: task[k] for k in writer.fieldnames})

    def _ensure_manifest(self):
        payload = _manifest_payload(self.read_inputs, self.motif, self.tel_params)
        payload["shared_artifacts"] = {
            "processed_reads": str(self.out / "processed_reads"),
            "hifi_reads_idx": str(self.out / "hifi_reads.idx"),
            "ont_reads_idx": str(self.out / "ont_reads.idx"),
            "hifi_reads_part": str(self.out / "hifi_reads_part"),
            "ont_reads_part": str(self.out / "ont_reads_part"),
            "part1_telo_reads": str(self.part1_dir),
        }
        if self.manifest_file.exists():
            return
        self.manifest_file.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def _extract_telomeric_reads_once(self):
        global_left = self.part1_dir / "Global.left.telo.reads.fa"
        global_right = self.part1_dir / "Global.right.telo.reads.fa"
        if self.manifest_file.exists() and global_left.exists() and global_right.exists():
            print("[TelSeekerCtg] Reusing existing part1.telo.reads outputs")
            return

        from TelSeekerPart1 import TeloReadsExtractor

        extractor = TeloReadsExtractor(
            output_dir=str(self.out),
            motif=self.motif,
            threads=self.thread,
            batch_size=1000,
            overlapping=False,
            tel_n=self.tel_params["tel_n"],
            tel_r=self.tel_params["tel_r"],
            tel_mm=self.tel_params["tel_mm"],
        )
        extractor.run()

    def _classify_tel_read_availability(self):
        left_count = _count_fasta_records(self.part1_dir / "Global.left.telo.reads.fa")
        right_count = _count_fasta_records(self.part1_dir / "Global.right.telo.reads.fa")
        runnable = []
        for task in self.tasks:
            existing = self._read_existing_status(task)
            if existing:
                self.status_rows.append(existing)
                continue

            if left_count + right_count == 0:
                self._write_failure(task, "no_tel_reads")
            elif task["end"] == "L" and left_count == 0:
                self._write_failure(task, "no_tel_reads_for_target_end")
            elif task["end"] == "R" and right_count == 0:
                self._write_failure(task, "no_tel_reads_for_target_end")
            else:
                runnable.append(task)
        return runnable

    def _read_existing_status(self, task) -> Optional[Dict]:
        status_file = Path(task["job_dir"]) / "result" / "status.tsv"
        if not status_file.exists():
            return None
        with open(status_file, newline="") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        return rows[0] if rows else None

    def _write_failure(self, task, stop_reason: str):
        row = self._base_status_row(task)
        row.update({
            "status": "failed",
            "stop_reason": stop_reason,
            "final_length": task["original_length"],
        })
        result_dir = Path(task["job_dir"]) / "result"
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / "failed.reason.txt").write_text(stop_reason + "\n")
        self._write_status_file(result_dir / "status.tsv", [row])
        self.status_rows.append(row)

    def _run_part2_for_tasks(self, runnable):
        self.need_extension_file.parent.mkdir(parents=True, exist_ok=True)
        self.need_extension_file.write_text("".join(f"{task['chr_end']}\n" for task in runnable))

        from TelSeekerPart2 import (
            DirectConnectionChecker,
            ParallelExtensionManager,
            WorkspaceBuilder,
            select_chr_ends_for_extension,
        )

        builder = WorkspaceBuilder(str(self.out), str(self.ctgs_fasta), work_base_name="telseeker_ctg.jobs")
        builder.setup_workspace()

        checker = DirectConnectionChecker(
            work_base_dir=builder.work_base_dir,
            chr_ends=builder.chr_ends,
            work_paths=builder.work_paths,
            max_workers=self.work,
            edge=self.edge,
        )
        direct_results = checker.run_checks()
        extension_chr_ends = select_chr_ends_for_extension(builder.chr_ends, direct_results)

        if not extension_chr_ends:
            return

        manager = ParallelExtensionManager(
            chr_ends=extension_chr_ends,
            work_paths=builder.work_paths,
            out_dir=self.out,
            kmer_num=self.kmer_num,
            kmer_size=self.kmer_size,
            threads=self.thread,
            edge=self.edge,
            max_workers=self.work,
            max_rounds=self.MaximumExtensionRound,
            max_extension_length=self.MaximumExtensionLength,
            original_hifi=self.original_reads_info.get("original_hifi"),
            original_ont=self.original_reads_info.get("original_ont"),
            kmer_filter=self.kmer_filter,
        )
        manager.run_parallel_extension()

    def _collect_runnable_results(self, runnable):
        for task in runnable:
            row = self._status_from_job(task)
            result_dir = Path(task["job_dir"]) / "result"
            result_dir.mkdir(parents=True, exist_ok=True)
            if row["status"] == "success":
                self._write_extended_contig(task, result_dir, row)
            else:
                (result_dir / "failed.reason.txt").write_text(row["stop_reason"] + "\n")
            self._write_status_file(result_dir / "status.tsv", [row])
            self.status_rows.append(row)

    def _status_from_job(self, task):
        row = self._base_status_row(task)
        job_dir = Path(task["job_dir"])
        linker_file = job_dir / "linker.fa"
        linker_info = job_dir / "linker.info"
        seed_file = job_dir / "seed.fa"
        if seed_file.exists():
            row["seed_length"] = str(len(_read_single_fasta_seq(seed_file)))

        if linker_file.exists() and linker_info.exists():
            info = self._parse_linker_info(linker_info)
            row.update({
                "status": "success",
                "connection_type": info.get("connection_type", "NA"),
                "connected_read": info.get("connected_read", "NA"),
                "round_num": info.get("round_num", "NA"),
                "extension_length": info.get("extension_length", "0"),
                "stop_reason": "connection_found",
            })
            return row

        summary = job_dir / "extension" / "extension.summary"
        if summary.exists():
            summary_info = self._parse_summary(summary)
            row["round_num"] = summary_info.get("Total Rounds", "NA")
            row["extension_length"] = self._strip_bp(summary_info.get("Total Extension Length", "0"))
            stop_reason = summary_info.get("Stop Reason", "connection_not_found")
            row["stop_reason"] = self._normalize_stop_reason(stop_reason)
        elif self.MaximumExtensionRound == 0:
            row["stop_reason"] = "round0_no_connection"
            row["round_num"] = "0"
        else:
            row["stop_reason"] = "connection_not_found"
        return row

    def _write_extended_contig(self, task, result_dir: Path, row: Dict):
        job_dir = Path(task["job_dir"])
        seed_len = int(row["seed_length"]) if row["seed_length"] != "NA" else 0
        linker_seq = _read_single_fasta_seq(job_dir / "linker.fa")
        original_seq = task["seq"]
        if task["end"] == "L":
            final_seq = linker_seq + original_seq[seed_len:]
        else:
            final_seq = original_seq[:-seed_len] + linker_seq if seed_len else original_seq + linker_seq
        row["final_length"] = str(len(final_seq))
        record = SeqRecord(
            final_seq,
            id=task["ctg_id"],
            description=(
                f"telseeker_ctg_extended end={task['end']} "
                f"method={row['connection_type']} connected_read={row['connected_read']}"
            ),
        )
        SeqIO.write([record], result_dir / "extended.ctg.fa", "fasta")

    def _base_status_row(self, task):
        return {
            "ctg_file": task["ctg_file"],
            "ctg_id": task["ctg_id"],
            "safe_ctg_id": task["safe_ctg_id"],
            "end": task["end"],
            "job_dir": task["job_dir"],
            "status": "failed",
            "connection_type": "NA",
            "connected_read": "NA",
            "round_num": "NA",
            "seed_length": "NA",
            "extension_length": "0",
            "original_length": str(task["original_length"]),
            "final_length": str(task["original_length"]),
            "stop_reason": "connection_not_found",
        }

    def _parse_linker_info(self, linker_info: Path):
        fields = {}
        for line in linker_info.read_text().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        method = fields.get("Connection Method", "NA")
        rounds = fields.get("Extension Rounds", "0" if method == "direct" else "NA")
        extension_length = self._strip_bp(fields.get("Total Extension Length", "0"))
        return {
            "connection_type": method,
            "connected_read": fields.get("Connected Read", "NA"),
            "round_num": rounds,
            "extension_length": extension_length,
        }

    def _parse_summary(self, summary: Path):
        fields = {}
        for line in summary.read_text().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        return fields

    def _strip_bp(self, value: str) -> str:
        return str(value).replace("bp", "").strip()

    def _normalize_stop_reason(self, reason: str) -> str:
        normalized = (reason or "").strip()
        if normalized in {"unknown", ""}:
            return "connection_not_found"
        return normalized

    def _write_status_file(self, path: Path, rows: List[Dict]):
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=STATUS_FIELDS, delimiter="\t")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_aggregate_status(self):
        self.aggregate_result_dir.mkdir(parents=True, exist_ok=True)
        ordered = []
        by_endpoint = {
            (row["safe_ctg_id"], row["end"]): row
            for row in self.status_rows
        }
        for task in self.tasks:
            row = by_endpoint.get((task["safe_ctg_id"], task["end"]))
            if row:
                ordered.append(row)
        self._write_status_file(self.aggregate_result_dir / "status.tsv", ordered)
