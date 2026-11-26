"""Small, standard-library-only primitives for portable server reports."""
from __future__ import annotations

try:
    from workspace_layout import workspace_join
except ModuleNotFoundError:
    from .workspace_layout import workspace_join


import csv
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from run_orchestration import sha256_file
except ModuleNotFoundError:
    from .run_orchestration import sha256_file

SCHEMA = "cgat_server_report_v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path: Path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_tsv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def digest(path: Path) -> str:
    # Share actual reads with outer checkpoints in this process; never seed a
    # content digest from a persisted report/cache receipt.
    return sha256_file(path)


def local_path(root: Path, relative: str) -> Path:
    path = (workspace_join(root, relative)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"report data path escapes its directory: {relative}")
    return path


def fasta_stats(path: Path, *, gap_positions=False) -> dict | None:
    """Stream FASTA; N runs span physical lines. Never retain whole sequences."""
    if not path.is_file():
        return None
    records = []
    current = None
    n_run = 0

    def finish_gap(end):
        nonlocal n_run
        if current is not None and n_run >= 100:
            current["gap_count"] += 1
            current["gap_bp"] += n_run
            if gap_positions:
                current["gap_intervals"].append([end - n_run, end])
        n_run = 0

    with path.open(encoding="ascii") as handle:
        for raw in handle:
            if raw.startswith(">"):
                finish_gap(current["length_bp"] if current else 0)
                name = raw[1:].split()[0]
                current = {"sequence": name, "length_bp": 0, "n_bp": 0,
                           "gap_count": 0, "gap_bp": 0}
                if gap_positions:
                    current["gap_intervals"] = []
                records.append(current)
                continue
            sequence = "".join(raw.split()).upper()
            if not sequence:
                continue
            if current is None:
                raise ValueError(f"FASTA sequence has no header: {path}")
            offset = current["length_bp"]
            current["length_bp"] += len(sequence)
            current["n_bp"] += sequence.count("N")
            for match in re.finditer(r"N+|[^N]+", sequence):
                if match[0][0] == "N":
                    n_run += len(match[0])
                else:
                    finish_gap(offset + match.start())
    finish_gap(current["length_bp"] if current else 0)
    lengths = sorted((row["length_bp"] for row in records), reverse=True)
    total = sum(lengths)
    cumulative = 0
    n50 = 0
    for length in lengths:
        cumulative += length
        if cumulative * 2 >= total:
            n50 = length
            break
    return {"sequence_count": len(records), "length_bp": total,
            "n_bp": sum(row["n_bp"] for row in records),
            "gap_count": sum(row["gap_count"] for row in records),
            "gap_bp": sum(row["gap_bp"] for row in records), "n50_bp": n50,
            "gap_definition": "maximal consecutive N/n runs of at least 100 bp",
            "sha256": digest(path), "sequences": records}


def layout_descriptor(layout):
    from workspace_layout import JOB_OUTPUT_SCHEMA, LAYOUT_SCHEMA, PROJECT_OUTPUT_SCHEMA
    return {"version": layout.version, "schema": (PROJECT_OUTPUT_SCHEMA if layout.project_delivery else
            JOB_OUTPUT_SCHEMA if layout.result_prefix else LAYOUT_SCHEMA),
            "result_prefix": layout.result_prefix, "project_delivery": layout.project_delivery}


def stage_location(layout, unit):
    prefix = unit.partition(":")[0]
    if prefix in {"ref", "assign", "chr", "q0_chr", "q0_evidence"}:
        stage, directory = "alignment", "runs"
    elif unit.startswith("package_"):
        stage, directory = "delivery", "07_delivery" if layout.version == 2 else None
    elif unit == "refinement":
        stage, directory = "refinement", "04_refinement" if layout.version == 2 else "degap"
    elif unit == "prepare":
        stage, directory = "inputs", "data/reference"
    elif unit in {"lgz_prepare", "grt_prepare", "prepare_lgz_inputs", "prepare_grt_inputs"}:
        stage, directory = "q0", "grt/donors"
    else:
        stage, directory = "lgz", "grt"
    if layout.version == 2:
        directory = {"grt_step1":"03_lgz/02_step1", "grt_step2":"03_lgz/03_step2", "grt_step3":"03_lgz/04_step3",
                     "finalize_evidence":"03_lgz/05_evidence", "lgz_prepare":"03_lgz/01_q0", "grt_prepare":"03_lgz/01_q0"}.get(unit,directory)
    return stage, layout.relative(directory) if directory else None


def timing_summary(layout, records):
    """Unit-seconds may overlap. Wall span is separate; missing clocks are null."""
    from collections import Counter, defaultdict
    units, groups = [], defaultdict(list)
    for record in records:
        unit = record['stage_id']
        stage, directory = stage_location(layout, unit)
        rt = record.get('runtime') or {}
        status = record.get('status', 'pending')
        rt = rt if isinstance(rt,dict) else {}
        execution = record.get('execution')
        group = unit.partition(':')[0] if ':' in unit else None
        secs = rt.get('elapsed_seconds')
        try:
            secs = float(secs) if secs not in (None, '') else None
            if secs is not None and not 0 <= secs < float('inf'):
                secs = None
        except (ValueError, TypeError):
            secs = None
        rss_mb = rt.get('peak_rss_mb')
        try:
            rss_mb = float(rss_mb) if rss_mb not in (None, '') else None
            if rss_mb is not None and not 0 < rss_mb < float('inf'):
                rss_mb = None
        except (ValueError, TypeError):
            rss_mb = None
        row = dict(unit=unit, stage=stage, output_directory=directory, status=status,
                   execution=('failed' if status in ('failed', 'interrupted') else execution if execution in
                              ('computed', 'cache_reused', 'frozen_original_lgz') else 'pending'),
                   elapsed_seconds=secs, peak_rss_mb=rss_mb, started_at=rt.get('started_at') or None,
                   ended_at=rt.get('ended_at') or None, exit_code=rt.get('exit_code') or None,
                   parallel_group=group, reason=(record.get('not_executed_reason') or
                        (record.get('failure_reason')[:500] if isinstance(record.get('failure_reason'),str) and '/' not in record['failure_reason'] and '\\' not in record['failure_reason'] else None) or
                        (f"{status}: exit_code={rt.get('exit_code') or 'unknown'}" if status in ('failed','interrupted') else None)))
        units.append(row)
        groups[('stage', stage)].append(row)
        if group:
            groups[('parallel', group)].append(row)
    def aggregate(key, rows):
        starts = [r['started_at'] for r in rows if r['started_at']]
        ends = [r['ended_at'] for r in rows if r['ended_at']]
        seconds = [r['elapsed_seconds'] for r in rows if r['elapsed_seconds'] is not None]
        rss_vals = [r['peak_rss_mb'] for r in rows if r['peak_rss_mb'] is not None]
        try:
            span = (max(map(datetime.fromisoformat, ends))-min(map(datetime.fromisoformat, starts))).total_seconds()
        except (ValueError, TypeError):
            span = None
        return dict(id=key, unit_count=len(rows), measured_unit_count=len(seconds), unit_seconds=sum(seconds) if seconds else None,
                    peak_rss_mb=max(rss_vals) if rss_vals else None,
                    observed_span_seconds=span, statuses=dict(Counter(r['status'] for r in rows)),
                    executions=dict(Counter(r['execution'] for r in rows)))
    all_rss = [r['peak_rss_mb'] for r in units if r['peak_rss_mb'] is not None]
    return {'units': units, 'peak_rss_mb': max(all_rss) if all_rss else None,
            **{name: [aggregate(key, rows) for (kind,key),rows in groups.items() if kind == want]
               for name,want in [('stages','stage'), ('parallel_groups','parallel')]}}
