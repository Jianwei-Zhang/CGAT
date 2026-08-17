from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .common import fail

def command_identity(identity: dict[str, str]) -> dict[str, str]:
    return {
        "resolved": identity["resolved"],
        "sha256": identity["sha256"],
        "version": identity["version"],
    }


def mummer_parameters(
    threads: int,
    *,
    min_cluster: int = 1_000,
    min_match: int = 100,
    min_alignment: int = 10_000,
) -> dict[str, object]:
    return {
        "nucmer": {
            "min_cluster": min_cluster,
            "min_match": min_match,
            "batch": 500_000_000,
            "threads": threads,
        },
        "delta_filter": {"reference_best": True, "min_alignment": min_alignment},
        "show_coords": {"reference_sorted": True, "include_lengths": True},
    }

def run_logged(
    command: list[str],
    cwd: Path,
    command_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    stdout_redirect: Path | None = None,
) -> None:
    command_path.write_text(shlex.join(command) + "\n", encoding="utf-8", newline="")
    with stderr_path.open("w", encoding="utf-8", newline="") as stderr_handle:
        if stdout_redirect is None:
            with stdout_path.open("w", encoding="utf-8", newline="") as stdout_handle:
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    check=False,
                )
        else:
            stdout_path.write_text("redirected to " + stdout_redirect.name + "\n", encoding="utf-8")
            with stdout_redirect.open("w", encoding="utf-8", newline="") as output_handle:
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    stdout=output_handle,
                    stderr=stderr_handle,
                    check=False,
                )
    if completed.returncode != 0:
        fail(
            f"command failed with exit code {completed.returncode}; "
            f"command={command_path}, stderr={stderr_path}"
        )

def parse_mummer_coords(
    path: Path,
    stage: str,
    chromosome: str,
    chromosome_length: int,
    members_by_record: dict[str, dict[str, str]],
    donor_lengths: dict[str, int],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n")
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("/")
                or stripped.startswith("NUCMER")
                or stripped.startswith("[")
                or stripped.startswith("=")
            ):
                continue
            fields = [value for value in stripped.split() if value != "|"]
            if len(fields) < 11:
                fail(f"invalid MUMmer coords row at {path}:{line_number}")
            try:
                ref_start, ref_end, query_start, query_end = map(int, fields[:4])
                ref_aligned, query_aligned = map(int, fields[4:6])
                identity = float(fields[6])
                ref_length, query_length = map(int, fields[7:9])
            except ValueError:
                fail(f"non-numeric MUMmer coords row at {path}:{line_number}")
            ref_record, query_record = fields[-2:]
            if ref_record not in members_by_record:
                fail(f"MUMmer coords references unknown D0 member at {path}:{line_number}")
            if query_record != chromosome:
                fail(f"MUMmer coords query is not {chromosome} at {path}:{line_number}")
            if ref_length != donor_lengths[ref_record] or query_length != chromosome_length:
                fail(f"MUMmer coords length columns disagree with FASTA at {path}:{line_number}")
            if not (
                1 <= min(ref_start, ref_end) <= max(ref_start, ref_end) <= ref_length
                and 1 <= min(query_start, query_end) <= max(query_start, query_end) <= query_length
                and ref_aligned >= 1
                and query_aligned >= 1
                and 0 <= identity <= 100
            ):
                fail(f"MUMmer coords has invalid coordinates at {path}:{line_number}")
            member = members_by_record[ref_record]
            orientation = "+" if (ref_end - ref_start) * (query_end - query_start) >= 0 else "-"
            rows.append(
                {
                    "stage": stage,
                    "chr": chromosome,
                    "line_number": line_number,
                    "member_id": member["member_id"],
                    "source_dataset": member["dataset_name"],
                    "source_contig": member["contig_name"],
                    "ref_record": ref_record,
                    "ref_start": ref_start,
                    "ref_end": ref_end,
                    "ref_min": min(ref_start, ref_end),
                    "ref_max": max(ref_start, ref_end),
                    "query_start": query_start,
                    "query_end": query_end,
                    "query_min": min(query_start, query_end),
                    "query_max": max(query_start, query_end),
                    "orientation": orientation,
                    "identity": identity / 100.0,
                    "ref_aligned": ref_aligned,
                    "query_aligned": query_aligned,
                    "ref_length": ref_length,
                    "query_length": query_length,
                    "raw_line": line,
                }
            )
    return rows
