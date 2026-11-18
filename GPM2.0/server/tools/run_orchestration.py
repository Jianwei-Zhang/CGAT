#!/usr/bin/env python3

"""Shared execution contract primitives for the generated Server pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


CHECKPOINT_SCHEMA_VERSION = 1
EXECUTION_ENGINE_VERSION = 1

RUN_STATES = (
    "pending",
    "running",
    "success",
    "failed",
    "interrupted",
    "stale",
)

LOG_EVENTS = (
    "PREFLIGHT",
    "START",
    "PARALLEL",
    "TASK_START",
    "TASK_END",
    "SKIP_VALID",
    "CACHE_HIT",
    "RESUME",
    "SUCCESS",
    "FAILED",
    "INTERRUPTED",
    "STALE",
)

ASSIGN_UNIT_ID = "assign"
LGZ_PREPARE_UNIT_ID = "grt_prepare"
LGZ_STEP1_UNIT_ID = "grt_step1"
LGZ_STEP2_UNIT_ID = "grt_step2"
LGZ_STEP3_UNIT_ID = "grt_step3"
LGZ_TELOMERE_FINALIZE_UNIT_ID = "grt_telomere_finalize"
FINALIZE_EVIDENCE_UNIT_ID = "finalize_evidence"
PACKAGE_FULL_UNIT_ID = "package_full"
PACKAGE_LIGHT_UNIT_ID = "package_light"

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class OrchestrationContractError(ValueError):
    """Raised when orchestration metadata or an output artifact is invalid."""


@dataclass(frozen=True)
class UnitPlanItem:
    unit_id: str
    dependencies: tuple[str, ...]


@dataclass(frozen=True)
class PafSummary:
    record_count: int


def validate_name(value: str, label: str) -> str:
    if not value or _NAME_RE.fullmatch(value) is None:
        raise OrchestrationContractError(
            f"invalid {label} {value!r}; use letters, numbers, dot, underscore, or hyphen"
        )
    return value


def reference_unit_id(dataset_name: str) -> str:
    return f"ref:{validate_name(dataset_name, 'dataset name')}"


def chromosome_unit_id(chromosome: str) -> str:
    return f"chr:{validate_name(chromosome, 'chromosome name')}"


def chromosome_self_unit_id(chromosome: str, dataset_name: str) -> str:
    return (
        f"{chromosome_unit_id(chromosome)}:self:"
        f"{validate_name(dataset_name, 'dataset name')}"
    )


def chromosome_pair_unit_id(chromosome: str, left_dataset: str, right_dataset: str) -> str:
    left = validate_name(left_dataset, "left dataset name")
    right = validate_name(right_dataset, "right dataset name")
    if left == right:
        raise OrchestrationContractError("chromosome pair datasets must be distinct")
    return f"{chromosome_unit_id(chromosome)}:pair:{left}:{right}"


def chromosome_scan_unit_id(chromosome: str, scan_kind: str) -> str:
    if scan_kind not in {"telomere", "centromere"}:
        raise OrchestrationContractError(f"unsupported chromosome scan kind: {scan_kind!r}")
    return f"{chromosome_unit_id(chromosome)}:{scan_kind}_scan"


def _unique_names(values: Iterable[str], label: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        validated = validate_name(value, label)
        if validated in seen:
            raise OrchestrationContractError(f"duplicate {label}: {validated}")
        seen.add(validated)
        result.append(validated)
    return tuple(result)


def build_unit_plan(
    dataset_names: Iterable[str], chromosome_names: Iterable[str]
) -> tuple[UnitPlanItem, ...]:
    datasets = _unique_names(dataset_names, "dataset name")
    chromosomes = _unique_names(chromosome_names, "chromosome name")
    if not datasets:
        raise OrchestrationContractError("at least one dataset is required")
    if not chromosomes:
        raise OrchestrationContractError("at least one chromosome is required")

    reference_ids = tuple(reference_unit_id(name) for name in datasets)
    chromosome_ids = tuple(chromosome_unit_id(name) for name in chromosomes)
    items = [UnitPlanItem(unit_id, ()) for unit_id in reference_ids]
    items.extend(
        [
            UnitPlanItem(ASSIGN_UNIT_ID, reference_ids),
            UnitPlanItem(LGZ_PREPARE_UNIT_ID, (ASSIGN_UNIT_ID,)),
            UnitPlanItem(LGZ_STEP1_UNIT_ID, (LGZ_PREPARE_UNIT_ID,)),
            UnitPlanItem(LGZ_STEP2_UNIT_ID, (LGZ_STEP1_UNIT_ID,)),
            UnitPlanItem(LGZ_STEP3_UNIT_ID, (LGZ_STEP2_UNIT_ID,)),
            UnitPlanItem(
                LGZ_TELOMERE_FINALIZE_UNIT_ID,
                (LGZ_STEP3_UNIT_ID,),
            ),
        ]
    )
    items.extend(
        UnitPlanItem(unit_id, (LGZ_TELOMERE_FINALIZE_UNIT_ID,))
        for unit_id in chromosome_ids
    )
    items.extend(
        [
            UnitPlanItem(
                FINALIZE_EVIDENCE_UNIT_ID,
                chromosome_ids or (LGZ_TELOMERE_FINALIZE_UNIT_ID,),
            ),
            UnitPlanItem(PACKAGE_FULL_UNIT_ID, (FINALIZE_EVIDENCE_UNIT_ID,)),
            UnitPlanItem(PACKAGE_LIGHT_UNIT_ID, (PACKAGE_FULL_UNIT_ID,)),
        ]
    )
    return tuple(items)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


_SHA256_CACHE_LIMIT = 256
_SHA256_CACHE = OrderedDict()
_SHA256_CACHE_LOCK = threading.RLock()


def _stat_signature(resolved: Path, value: os.stat_result) -> tuple:
    return (str(resolved), value.st_dev, value.st_ino, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def file_signature(path: Path) -> tuple:
    try:
        resolved = Path(path).resolve(strict=True)
        value = resolved.stat()
    except FileNotFoundError as exc:
        raise OrchestrationContractError(f"required file is missing: {path}") from exc
    if not stat.S_ISREG(value.st_mode):
        raise OrchestrationContractError(f"required regular file is missing: {path}")
    return _stat_signature(resolved, value)


def _sha256_read(signature: tuple) -> str:
    """Only an actual stable byte read may populate the process-local memo."""
    path = Path(signature[0])
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        if _stat_signature(path, os.fstat(handle.fileno())) != signature:
            raise OrchestrationContractError(f"file changed before hashing: {path}")
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        if _stat_signature(path, os.fstat(handle.fileno())) != signature:
            raise OrchestrationContractError(f"file changed during hashing: {path}")
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    signature = file_signature(path)
    with _SHA256_CACHE_LOCK:
        cached = _SHA256_CACHE.get(signature)
        if cached is not None:
            _SHA256_CACHE.move_to_end(signature)
    if cached is not None:
        if file_signature(path) != signature:
            raise OrchestrationContractError(f"file changed during hash reuse: {path}")
        return cached
    digest = _sha256_read(signature)
    if file_signature(path) != signature:
        raise OrchestrationContractError(f"file changed while hashing: {path}")
    with _SHA256_CACHE_LOCK:
        _SHA256_CACHE[signature] = digest
        _SHA256_CACHE.move_to_end(signature)
        while len(_SHA256_CACHE) > _SHA256_CACHE_LIMIT:
            _SHA256_CACHE.popitem(last=False)
    return digest


def file_identity(path: Path, *, relative_to: Path | None = None) -> dict[str, object]:
    signature = file_signature(path)
    label = path.relative_to(relative_to).as_posix() if relative_to is not None else str(path)
    digest = sha256_file(path)
    if file_signature(path) != signature:
        raise OrchestrationContractError(f"file identity changed while hashing: {path}")
    return {"path": label, "size": signature[3], "sha256": digest}


def atomic_write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _parse_nonnegative_integer(value: str, label: str, line_number: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise OrchestrationContractError(
            f"invalid PAF {label} on line {line_number}: {value!r}"
        ) from exc
    if parsed < 0:
        raise OrchestrationContractError(
            f"negative PAF {label} on line {line_number}: {parsed}"
        )
    return parsed


def validate_paf(path: Path, *, require_cigar: bool = False) -> PafSummary:
    if not path.is_file():
        raise OrchestrationContractError(f"PAF output is missing: {path}")

    record_count = 0
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.rstrip("\r\n")
                if not line or line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) < 12:
                    raise OrchestrationContractError(
                        f"PAF line {line_number} has {len(fields)} fields; expected at least 12"
                    )
                if not fields[0] or not fields[5]:
                    raise OrchestrationContractError(
                        f"PAF line {line_number} has an empty query or target name"
                    )
                query_length = _parse_nonnegative_integer(
                    fields[1], "query length", line_number
                )
                query_start = _parse_nonnegative_integer(fields[2], "query start", line_number)
                query_end = _parse_nonnegative_integer(fields[3], "query end", line_number)
                if fields[4] not in {"+", "-"}:
                    raise OrchestrationContractError(
                        f"invalid PAF strand on line {line_number}: {fields[4]!r}"
                    )
                target_length = _parse_nonnegative_integer(
                    fields[6], "target length", line_number
                )
                target_start = _parse_nonnegative_integer(
                    fields[7], "target start", line_number
                )
                target_end = _parse_nonnegative_integer(fields[8], "target end", line_number)
                residue_matches = _parse_nonnegative_integer(
                    fields[9], "residue matches", line_number
                )
                alignment_length = _parse_nonnegative_integer(
                    fields[10], "alignment length", line_number
                )
                mapping_quality = _parse_nonnegative_integer(
                    fields[11], "mapping quality", line_number
                )
                if query_length < 1 or not 0 <= query_start <= query_end <= query_length:
                    raise OrchestrationContractError(
                        f"invalid PAF query interval on line {line_number}"
                    )
                if target_length < 1 or not 0 <= target_start <= target_end <= target_length:
                    raise OrchestrationContractError(
                        f"invalid PAF target interval on line {line_number}"
                    )
                if residue_matches > alignment_length:
                    raise OrchestrationContractError(
                        f"PAF residue matches exceed alignment length on line {line_number}"
                    )
                if mapping_quality > 255:
                    raise OrchestrationContractError(
                        f"PAF mapping quality exceeds 255 on line {line_number}"
                    )
                record_count += 1
                if require_cigar:
                    cigar = next((tag[5:] for tag in fields[12:] if tag.startswith("cg:Z:")), "")
                    ops = re.findall(r"([1-9][0-9]*)([MIDN=X])", cigar)
                    if not ops or "".join(length + op for length, op in ops) != cigar:
                        raise OrchestrationContractError(f"missing or invalid CIGAR on PAF line {line_number}: {path}")
                    query_span = sum(int(length) for length, op in ops if op in "MI=X")
                    target_span = sum(int(length) for length, op in ops if op in "MDN=X")
                    if query_span != query_end - query_start or target_span != target_end - target_start:
                        raise OrchestrationContractError(f"CIGAR span mismatch on PAF line {line_number}: {path}")
    except (OSError, UnicodeError) as exc:
        raise OrchestrationContractError(f"cannot read PAF output {path}: {exc}") from exc
    return PafSummary(record_count=record_count)


# Compatibility constants; persisted values remain unchanged.
GRT_PREPARE_UNIT_ID = LGZ_PREPARE_UNIT_ID
GRT_STEP1_UNIT_ID = LGZ_STEP1_UNIT_ID
GRT_STEP2_UNIT_ID = LGZ_STEP2_UNIT_ID
GRT_STEP3_UNIT_ID = LGZ_STEP3_UNIT_ID
GRT_TELOMERE_FINALIZE_UNIT_ID = LGZ_TELOMERE_FINALIZE_UNIT_ID
