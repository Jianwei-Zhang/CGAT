"""Bounded, non-mutating evidence and hints; never tune or retry an alignment."""
from __future__ import annotations

import csv
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess

CIGAR_OPERATION_LIMIT = (1 << 28) - 1
CIGAR_ASSERTION_CODE = "MINIMAP2_CIGAR_ASSERTION"
CIGAR_ASSERTION_HINT = (
    f"{CIGAR_ASSERTION_CODE}: minimap2 reported inconsistent CIGAR/query/reference spans. "
    "A single CIGAR operation exceeding 268435455 bases is one possible cause, "
    "not a confirmed diagnosis or evidence of out-of-memory. Preserve the command, "
    "tool version, stderr and partial PAF; do not remove -c, skip sequences or "
    "automatically retry with different parameters."
)
_ASSERTION = re.compile(r"(?:mm_update_extra|mm_fix_cigar).*Assertion.*qoff.*toff")


def cigar_assertion_hint(text: str) -> str:
    return CIGAR_ASSERTION_HINT if _ASSERTION.search(text) else ""


def log_identity(path: Path) -> tuple[int, int, int, int] | None:
    try:
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
    except OSError:
        return None


def log_tail(path: Path, limit: int = 65536) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - limit))
            return handle.read(limit).decode("utf-8", "replace")
    except OSError:
        return ""


def changed_log_hint(path: Path, before: tuple[int, int, int, int] | None) -> str:
    """For per-command logs, not shared append-only run_all.log."""
    after = log_identity(path)
    if after is None or after == before:
        return ""
    return cigar_assertion_hint(log_tail(path))


def tool_identity(executable: str) -> dict:
    result = {"requested": executable, "evidence": "run_start_snapshot_not_per_process_attestation"}
    resolved = shutil.which(executable)
    if not resolved:
        return {**result, "error": "executable not found"}
    path = Path(resolved).resolve()
    result["path"] = str(path)
    try:
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        result.update(sha256=digest.hexdigest(), size=before.st_size, mtime_ns=before.st_mtime_ns)
        completed = subprocess.run([str(path), "--version"], capture_output=True, text=True,
                                   errors="replace", timeout=5, check=False)
        result.update(version=(completed.stdout + completed.stderr).strip()[:4096],
                      version_exit_code=completed.returncode)
        after = path.stat()
        result["changed_during_probe"] = (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
    return result


def input_summary(root: Path, row: dict, role: str) -> dict:
    result = {"role": role, "name": row.get("reference_name") or row.get("dataset_name"),
              "fasta_relpath": row.get("fasta_relpath"), "fai_relpath": row.get("fai_relpath"),
              "evidence": "existing_fai_not_content_verified"}
    try:
        value = row.get("fai_relpath", "")
        if not value or Path(value).is_absolute():
            raise ValueError("missing or non-relative FAI path")
        path = (root / value).resolve()
        path.relative_to(root.resolve())
        stat = path.stat()
        total = count = largest = over_cigar = over_coordinate = 0
        examples = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                fields = line.rstrip("\r\n").split("\t")
                if len(fields) < 5 or not fields[0] or int(fields[1]) < 0:
                    raise ValueError("invalid FAI row")
                length = int(fields[1])
                total += length
                count += 1
                largest = max(largest, length)
                if length > CIGAR_OPERATION_LIMIT:
                    over_cigar += 1
                    if len(examples) < 20:
                        examples.append({"name": fields[0], "length": length})
                over_coordinate += length > (1 << 31) - 1
        if not count:
            raise ValueError("empty FAI")
        result.update(record_count=count, total_bases=total, max_length=largest,
                      over_cigar_operation_limit=over_cigar, over_int32_coordinate_limit=over_coordinate,
                      long_record_examples=examples, fai_size=stat.st_size, fai_mtime_ns=stat.st_mtime_ns)
        fasta_value = row.get("fasta_relpath", "")
        if fasta_value and not Path(fasta_value).is_absolute():
            fasta = (root / fasta_value).resolve()
            fasta.relative_to(root.resolve())
            if fasta.is_file():
                result["fai_older_than_fasta"] = stat.st_mtime_ns < fasta.stat().st_mtime_ns
    except (OSError, UnicodeError, ValueError) as exc:
        result["error"] = str(exc)
    return result


def runtime_snapshot(root: Path, options: dict[str, str]) -> dict:
    identities = {"PATH": tool_identity("minimap2")}
    configured = options.get("grt_minimap2")
    if configured:
        resolved = shutil.which(configured)
        if resolved and str(Path(resolved).resolve()) == identities["PATH"].get("path"):
            identities["configured_grt_minimap2"] = {**identities["PATH"], "requested": configured}
        else:
            identities["configured_grt_minimap2"] = tool_identity(configured)
    inputs = []
    for filename, role in (("reference.tsv", "reference"), ("datasets.tsv", "dataset")):
        try:
            with (root / "metadata" / filename).open(encoding="utf-8", newline="") as handle:
                inputs.extend(input_summary(root, row, role) for row in csv.DictReader(handle, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as exc:
            inputs.append({"role": role, "error": str(exc)})
    return {"schema_version": 1, "tools": identities, "inputs": inputs,
            "parameters_changed": False, "automatic_retry": False,
            "note": "Long records indicate risk, not an overflowing CIGAR operation. "
                    "This snapshot neither validates FASTA content nor replaces actual per-command logs."}
