#!/usr/bin/env python3

"""Shared execution contract primitives for the generated Server pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import re
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
    "START",
    "SKIP_VALID",
    "CACHE_HIT",
    "RESUME",
    "SUCCESS",
    "FAILED",
    "INTERRUPTED",
    "STALE",
)

ASSIGN_UNIT_ID = "assign"
GRT_PREPARE_UNIT_ID = "grt_prepare"
GRT_STEP1_UNIT_ID = "grt_step1"
GRT_STEP23_UNIT_ID = "grt_step23"
GRT_TELOMERE_FINALIZE_UNIT_ID = "grt_telomere_finalize"
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
            UnitPlanItem(GRT_PREPARE_UNIT_ID, (ASSIGN_UNIT_ID,)),
            UnitPlanItem(GRT_STEP1_UNIT_ID, (GRT_PREPARE_UNIT_ID,)),
            UnitPlanItem(GRT_STEP23_UNIT_ID, (GRT_STEP1_UNIT_ID,)),
            UnitPlanItem(
                GRT_TELOMERE_FINALIZE_UNIT_ID,
                (GRT_STEP23_UNIT_ID,),
            ),
        ]
    )
    items.extend(
        UnitPlanItem(unit_id, (GRT_TELOMERE_FINALIZE_UNIT_ID,))
        for unit_id in chromosome_ids
    )
    items.extend(
        [
            UnitPlanItem(
                FINALIZE_EVIDENCE_UNIT_ID,
                chromosome_ids or (GRT_TELOMERE_FINALIZE_UNIT_ID,),
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_identity(path: Path, *, relative_to: Path | None = None) -> dict[str, object]:
    if not path.is_file():
        raise OrchestrationContractError(f"required file is missing: {path}")
    label = path.relative_to(relative_to).as_posix() if relative_to is not None else str(path)
    return {
        "path": label,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


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


def validate_paf(path: Path) -> PafSummary:
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
    except (OSError, UnicodeError) as exc:
        raise OrchestrationContractError(f"cannot read PAF output {path}: {exc}") from exc
    return PafSummary(record_count=record_count)
