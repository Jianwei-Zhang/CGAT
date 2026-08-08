#!/usr/bin/env python3

"""Hash-validated outer checkpoints for non-GRT Server execution units."""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from run_orchestration import (
    CHECKPOINT_SCHEMA_VERSION,
    EXECUTION_ENGINE_VERSION,
    OrchestrationContractError,
    atomic_write_json,
    file_identity,
    fingerprint,
    sha256_file,
    validate_paf,
)


WORKFLOW = "gpm_run_outer_v1"


@dataclass(frozen=True)
class PreparedOuterCheckpoint:
    unit_id: str
    kind: str
    path: Path
    input_payload: dict[str, object]
    input_fingerprint: str


class OuterCheckpointManager:
    def __init__(self, server_dir: Path):
        self.server_dir = server_dir.resolve()
        self.checkpoint_dir = self.server_dir / ".run_all/checkpoints"
        self._options: dict[str, str] | None = None
        self._tool_cache: dict[str, dict[str, object]] = {}

    def prepare(
        self, unit_id: str, command_relpath: str
    ) -> PreparedOuterCheckpoint | None:
        if unit_id.startswith("ref:"):
            kind = "reference_alignment"
            inputs = self._reference_inputs(unit_id.removeprefix("ref:"), command_relpath)
        elif unit_id == "assign":
            kind = "assignment"
            inputs = self._assignment_inputs(command_relpath)
        elif unit_id.startswith("chr:") and unit_id.count(":") == 1:
            kind = "chromosome_local"
            inputs = self._chromosome_inputs(unit_id.removeprefix("chr:"), command_relpath)
        else:
            return None
        input_payload = {
            "workflow": WORKFLOW,
            "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
            "execution_engine_version": EXECUTION_ENGINE_VERSION,
            "unit_id": unit_id,
            "kind": kind,
            **inputs,
        }
        digest = fingerprint(unit_id)
        slug = "".join(character if character.isalnum() else "-" for character in unit_id)
        checkpoint_path = self.checkpoint_dir / f"{slug[:48]}.{digest[:16]}.json"
        return PreparedOuterCheckpoint(
            unit_id=unit_id,
            kind=kind,
            path=checkpoint_path,
            input_payload=input_payload,
            input_fingerprint=fingerprint(input_payload),
        )

    def validate(self, prepared: PreparedOuterCheckpoint) -> tuple[bool, str]:
        if not prepared.path.is_file():
            return False, "checkpoint missing"
        try:
            checkpoint = json.loads(prepared.path.read_text(encoding="utf-8"))
            if not isinstance(checkpoint, dict):
                return False, "checkpoint is not an object"
            if (
                checkpoint.get("workflow") != WORKFLOW
                or checkpoint.get("checkpoint_schema_version") != CHECKPOINT_SCHEMA_VERSION
                or checkpoint.get("execution_engine_version") != EXECUTION_ENGINE_VERSION
                or checkpoint.get("unit_id") != prepared.unit_id
                or checkpoint.get("kind") != prepared.kind
                or checkpoint.get("status") != "success"
                or checkpoint.get("input_fingerprint") != prepared.input_fingerprint
            ):
                return False, "checkpoint identity or input fingerprint changed"
            expected_outputs = checkpoint.get("outputs")
            if not isinstance(expected_outputs, list):
                return False, "checkpoint output manifest is invalid"
            current_outputs = self._output_identities(prepared)
            if current_outputs != expected_outputs:
                return False, "checkpoint output manifest or hash changed"
            return True, "checkpoint and outputs are valid"
        except (OSError, UnicodeError, json.JSONDecodeError, OrchestrationContractError) as exc:
            return False, f"checkpoint validation failed: {exc}"

    def commit(self, prepared: PreparedOuterCheckpoint) -> Path:
        outputs = self._output_identities(prepared)
        checkpoint = {
            "workflow": WORKFLOW,
            "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
            "execution_engine_version": EXECUTION_ENGINE_VERSION,
            "unit_id": prepared.unit_id,
            "kind": prepared.kind,
            "status": "success",
            "input_fingerprint": prepared.input_fingerprint,
            "input_payload": prepared.input_payload,
            "outputs": outputs,
        }
        atomic_write_json(prepared.path, checkpoint)
        return prepared.path

    def _read_options(self) -> dict[str, str]:
        if self._options is not None:
            return self._options
        path = self.server_dir / "metadata/prepare_options.tsv"
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as exc:
            raise OrchestrationContractError(f"cannot read prepare options {path}: {exc}") from exc
        options = {row.get("key", ""): row.get("value", "") for row in rows}
        if not options.get("alignment_engine") or not options.get("threads"):
            raise OrchestrationContractError(f"prepare options are incomplete: {path}")
        self._options = options
        return options

    def _selected_options(self, keys: Iterable[str]) -> dict[str, str]:
        options = self._read_options()
        return {key: options.get(key, "") for key in keys}

    def _read_single_tsv(self, relpath: str) -> dict[str, str]:
        path = self.server_dir / relpath
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as exc:
            raise OrchestrationContractError(f"cannot read {path}: {exc}") from exc
        if len(rows) != 1:
            raise OrchestrationContractError(f"expected one row in {path}")
        return rows[0]

    def _read_datasets(self) -> list[dict[str, str]]:
        path = self.server_dir / "metadata/datasets.tsv"
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as exc:
            raise OrchestrationContractError(f"cannot read {path}: {exc}") from exc
        if not rows:
            raise OrchestrationContractError(f"datasets table is empty: {path}")
        return rows

    def _identities(self, paths: Iterable[Path]) -> list[dict[str, object]]:
        unique = sorted({path.resolve() for path in paths}, key=str)
        return [file_identity(path, relative_to=self.server_dir) for path in unique]

    def _tool_identity(self, command: str) -> dict[str, object]:
        cached = self._tool_cache.get(command)
        if cached is not None:
            return cached
        resolved_value = shutil.which(command)
        if not resolved_value:
            raise OrchestrationContractError(f"required checkpoint tool is missing: {command}")
        resolved = Path(resolved_value).resolve()
        if not resolved.is_file():
            raise OrchestrationContractError(f"checkpoint tool is not a file: {resolved}")
        identity = {
            "command": command,
            "resolved": str(resolved),
            "size": resolved.stat().st_size,
            "sha256": sha256_file(resolved),
        }
        self._tool_cache[command] = identity
        return identity

    def _alignment_tools(self) -> list[dict[str, object]]:
        engine = self._read_options()["alignment_engine"]
        commands = {
            "minimap2": ["minimap2"],
            "blastn": ["makeblastdb", "blastn", "python3"],
            "winnowmap": ["meryl", "winnowmap"],
        }.get(engine)
        if commands is None:
            raise OrchestrationContractError(f"unsupported alignment engine: {engine}")
        return [self._tool_identity(command) for command in commands]

    def _alignment_options(self) -> dict[str, str]:
        return self._selected_options(
            [
                "alignment_engine",
                "threads",
                "minimap_preset",
                "blastn_task",
                "blastn_evalue",
                "blastn_dust",
                "winnowmap_preset",
                "winnowmap_kmer",
                "winnowmap_repeat_fraction",
            ]
        )

    def _reference_inputs(self, dataset_name: str, command_relpath: str) -> dict[str, object]:
        reference = self._read_single_tsv("metadata/reference.tsv")
        dataset = next(
            (row for row in self._read_datasets() if row.get("dataset_name") == dataset_name),
            None,
        )
        if dataset is None:
            raise OrchestrationContractError(f"unknown reference-alignment dataset: {dataset_name}")
        paths = [
            self.server_dir / command_relpath,
            self.server_dir / "metadata/reference.tsv",
            self.server_dir / "metadata/datasets.tsv",
            self.server_dir / reference["fasta_relpath"],
            self.server_dir / reference["fai_relpath"],
            self.server_dir / dataset["fasta_relpath"],
            self.server_dir / dataset["fai_relpath"],
        ]
        if self._read_options()["alignment_engine"] == "blastn":
            paths.append(self.server_dir / ".prepare_lib/tools/blast6_to_paf.py")
        return {
            "parameters": self._alignment_options(),
            "tools": self._alignment_tools(),
            "inputs": self._identities(paths),
        }

    def _assignment_inputs(self, command_relpath: str) -> dict[str, object]:
        reference = self._read_single_tsv("metadata/reference.tsv")
        datasets = self._read_datasets()
        paths = [
            self.server_dir / command_relpath,
            self.server_dir / ".prepare_lib/tools/track_member_order.py",
            self.server_dir / "metadata/package.tsv",
            self.server_dir / "metadata/prepare_options.tsv",
            self.server_dir / "metadata/reference.tsv",
            self.server_dir / "metadata/datasets.tsv",
            self.server_dir / reference["fasta_relpath"],
            self.server_dir / reference["fai_relpath"],
        ]
        for dataset in datasets:
            paths.extend(
                [
                    self.server_dir / dataset["fasta_relpath"],
                    self.server_dir / dataset["fai_relpath"],
                    self.server_dir / f"runs/{dataset['dataset_name']}_vs_ref/result.paf",
                    self.server_dir / f"runs/{dataset['dataset_name']}_vs_ref/tool_version.txt",
                ]
            )
        for optional in [
            self.server_dir / "tel/rules.tsv",
            self.server_dir / "cen/reference.tsv",
        ]:
            if optional.is_file():
                paths.append(optional)
        centromere_dir = self.server_dir / "data/centromere"
        if centromere_dir.is_dir():
            paths.extend(path for path in centromere_dir.rglob("*") if path.is_file())
        return {
            "parameters": self._selected_options(
                [
                    "chr_assignment_min_coverage_percent",
                    "alignment_engine",
                    "threads",
                    "minimap_preset",
                    "blastn_task",
                    "blastn_evalue",
                    "blastn_dust",
                    "winnowmap_preset",
                    "winnowmap_kmer",
                    "winnowmap_repeat_fraction",
                    "skip_self",
                    "tel_enabled",
                    "cen_enabled",
                    "cen_min_len",
                    "cen_min_identity",
                ]
            ),
            "tools": [self._tool_identity("python3")],
            "inputs": self._identities(paths),
        }

    def _chromosome_inputs(self, chromosome: str, command_relpath: str) -> dict[str, object]:
        run_dir = self.server_dir / f"runs/chr_{chromosome}"
        paths = [
            self.server_dir / command_relpath,
            run_dir / "generated_command.sh",
            self.server_dir / "metadata/prepare_options.tsv",
            self.server_dir / "metadata/chr_assignments.tsv",
            self.server_dir / "metadata/track_member_orders.tsv",
        ]
        datasets_dir = run_dir / "datasets"
        if datasets_dir.is_dir():
            paths.extend(path for path in datasets_dir.rglob("*") if path.is_file())
        for child in run_dir.iterdir():
            if not child.is_dir() or child.name in {"datasets", "add_ctg"}:
                continue
            command = child / "command.sh"
            if command.is_file():
                paths.append(command)
            paths.extend(path for path in child.glob("*.fa") if path.is_file())
        for optional in [
            self.server_dir / "tel/rules.tsv",
            self.server_dir / "cen/reference.tsv",
        ]:
            if optional.is_file():
                paths.append(optional)
        centromere_dir = self.server_dir / "data/centromere"
        if centromere_dir.is_dir():
            paths.extend(path for path in centromere_dir.rglob("*") if path.is_file())
        tools = self._alignment_tools()
        if any((run_dir / name).is_dir() for name in ("tel_scan", "cen_scan")):
            tools = [*tools, self._tool_identity("python3")]
        return {
            "parameters": self._selected_options(
                [
                    "alignment_engine",
                    "threads",
                    "minimap_preset",
                    "blastn_task",
                    "blastn_evalue",
                    "blastn_dust",
                    "winnowmap_preset",
                    "winnowmap_kmer",
                    "winnowmap_repeat_fraction",
                    "skip_self",
                    "tel_enabled",
                    "cen_enabled",
                    "cen_min_len",
                    "cen_min_identity",
                ]
            ),
            "tools": tools,
            "inputs": self._identities(paths),
        }

    def _output_identities(
        self, prepared: PreparedOuterCheckpoint
    ) -> list[dict[str, object]]:
        if prepared.kind == "reference_alignment":
            dataset_name = prepared.unit_id.removeprefix("ref:")
            paths = [
                self.server_dir / f"runs/{dataset_name}_vs_ref/result.paf",
                self.server_dir / f"runs/{dataset_name}_vs_ref/tool_version.txt",
            ]
        elif prepared.kind == "assignment":
            paths = self._assignment_output_paths()
        elif prepared.kind == "chromosome_local":
            chromosome = prepared.unit_id.removeprefix("chr:")
            paths = self._chromosome_output_paths(chromosome)
        else:
            raise OrchestrationContractError(f"unsupported checkpoint kind: {prepared.kind}")
        for path in paths:
            if path.suffix.lower() == ".paf":
                validate_paf(path)
        return self._identities(paths)

    def _assignment_output_paths(self) -> list[Path]:
        paths = [
            self.server_dir / "metadata/chr_assignments.tsv",
            self.server_dir / "metadata/track_member_orders.tsv",
            self.server_dir / "metadata/source_seq_locator.tsv",
            self.server_dir / "metadata/source_seq_n_regions.tsv",
            self.server_dir / "metadata/reference_chr_locator.tsv",
        ]
        for root_relpath in ["data/reference/chrs", "data/partitions"]:
            root = self.server_dir / root_relpath
            if not root.is_dir():
                raise OrchestrationContractError(f"assignment output directory is missing: {root}")
            paths.extend(path for path in root.rglob("*") if path.is_file())
        locator_rows = self._read_tsv("metadata/reference_chr_locator.tsv")
        chromosome_names = [row.get("reference_chr_name", "") for row in locator_rows]
        if not chromosome_names or any(not name for name in chromosome_names):
            raise OrchestrationContractError(
                "reference chromosome locator contains no valid chromosome names"
            )
        chr_dirs = [self.server_dir / f"runs/chr_{name}" for name in chromosome_names]
        for run_dir in chr_dirs:
            for required in [run_dir / "command.sh", run_dir / "generated_command.sh"]:
                paths.append(required)
            datasets_dir = run_dir / "datasets"
            if datasets_dir.is_dir():
                paths.extend(path for path in datasets_dir.rglob("*") if path.is_file())
            for child in run_dir.iterdir():
                if not child.is_dir() or child.name in {"datasets", "add_ctg"}:
                    continue
                command = child / "command.sh"
                if command.is_file():
                    paths.append(command)
                paths.extend(path for path in child.glob("*.fa") if path.is_file())
        return paths

    def _read_tsv(self, relpath: str) -> list[dict[str, str]]:
        path = self.server_dir / relpath
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                return list(csv.DictReader(handle, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as exc:
            raise OrchestrationContractError(f"cannot read {path}: {exc}") from exc

    def _chromosome_output_paths(self, chromosome: str) -> list[Path]:
        run_dir = self.server_dir / f"runs/chr_{chromosome}"
        paths: list[Path] = []
        operation_dirs = [
            child
            for child in run_dir.iterdir()
            if child.is_dir() and child.name not in {"datasets", "add_ctg"}
        ]
        for operation in operation_dirs:
            if operation.name == "tel_scan":
                tel_outputs = sorted((self.server_dir / f"tel/chr_{chromosome}").glob("*.tsv"))
                if not tel_outputs:
                    raise OrchestrationContractError(
                        f"telomere scan outputs are missing for chromosome {chromosome}"
                    )
                paths.extend(tel_outputs)
                continue
            paf_paths = sorted(operation.glob("result*.paf"))
            if not paf_paths:
                raise OrchestrationContractError(
                    f"alignment output is missing for chromosome operation: {operation}"
                )
            paths.extend(paf_paths)
            if operation.name == "cen_scan":
                paths.append(self.server_dir / f"cen/chr_{chromosome}/marks.tsv")
        return paths
