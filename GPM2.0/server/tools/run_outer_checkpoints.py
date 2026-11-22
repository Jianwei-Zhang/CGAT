#!/usr/bin/env python3

"""Hash-validated outer checkpoints for non-LGZ Server execution units."""

from __future__ import annotations

try:
    from workspace_layout import workspace_join
except ModuleNotFoundError:
    from .workspace_layout import workspace_join


import csv
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from delivery_archive import validate_delivery_staging
    from lgz_contract import ContractError, validate_contract
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
except ModuleNotFoundError:  # Imported as server.tools.run_outer_checkpoints.
    from .delivery_archive import validate_delivery_staging
    from .lgz_contract import ContractError, validate_contract
    from .run_orchestration import (
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
LGZ_WORKFLOW = "gpm_grt_precomputed_v2"
LGZ_STAGE_MAP = {
    "grt_prepare": ("donor_freeze",),
    "grt_step1": ("step1",),
    "grt_step2": ("step2",),
    "grt_step12": ("step1", "step2"),
    "grt_step3": ("step3", "finalize"),
}


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
        self.checkpoint_dir = workspace_join(self.server_dir, ".run_all/checkpoints")
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
        elif unit_id.startswith("q0_chr:") and unit_id.count(":") == 1:
            kind = "q0_chromosome_alignments"
            inputs = self._chromosome_inputs(unit_id.split(":", 1)[1], command_relpath, alignment_only=True)
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
            "alignment_geometry_version": 2,
            **inputs,
        }
        if kind == "q0_chromosome_alignments":
            input_payload["command_relpath"] = command_relpath
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

    def migrate_reference_runtime(self, prepared: PreparedOuterCheckpoint, command_relpath: str,
                                  runtime: dict, *, dry_run: bool = False) -> tuple[bool, str]:
        """Rebind only an explicitly reviewed code-only completed-reference update.

        Scientific inputs, parameters, tools, native assets and all outputs must
        still match. Keep the original checkpoint before replacing metadata.
        The dedicated allowlist is narrower than partial native-cache migration.
        """
        if (type(dry_run) is not bool or prepared.kind != "reference_alignment"
                or not prepared.path.is_file() or prepared.path.is_symlink() or prepared.path.parent.is_symlink()):
            return False, "not a completed reference checkpoint"
        prefix = ".prepare_lib/tools/long_cigar_recovery/"
        try:
            original_bytes = prepared.path.read_bytes()
            checkpoint = json.loads(original_bytes)
            if (not isinstance(checkpoint, dict) or checkpoint.get("workflow") != WORKFLOW
                    or checkpoint.get("checkpoint_schema_version") != CHECKPOINT_SCHEMA_VERSION
                    or checkpoint.get("execution_engine_version") != EXECUTION_ENGINE_VERSION
                    or checkpoint.get("unit_id") != prepared.unit_id or checkpoint.get("kind") != prepared.kind
                    or checkpoint.get("status") != "success"):
                return False, "completed checkpoint contract differs"
            previous = checkpoint.get("input_payload")
            current = prepared.input_payload
            if not isinstance(previous, dict) or checkpoint.get("input_fingerprint") != fingerprint(previous):
                return False, "completed checkpoint input binding differs"
            if {k:v for k,v in previous.items() if k != "inputs"} != {k:v for k,v in current.items() if k != "inputs"}:
                return False, "reference parameters or tools changed"
            old = {row["path"]: row for row in previous["inputs"]}
            new = {row["path"]: row for row in current["inputs"]}
            if (len(old) != len(previous["inputs"]) or len(new) != len(current["inputs"])
                    or set(old) != set(new)):
                return False, "reference input inventory changed"
            code = runtime.get("files_sha256", {})
            if not code or any(prefix + name not in old for name in code):
                return False, "completed runtime code inventory missing"
            old_profile = fingerprint({name: old[prefix + name]["sha256"] for name in code})
            new_profile = fingerprint(code)
            if [old_profile, new_profile] not in runtime.get("completed_reference_resume_source_profiles", []):
                return False, "completed reference runtime transition is not reviewed"
            if any(new[prefix + name]["sha256"] != digest for name, digest in code.items()):
                return False, "current runtime code differs from its validated manifest"
            if (new.get(prefix + "branch-runtime.json", {}).get("sha256") != runtime.get("sha256")
                    or new.get(prefix + "resume-base.json", {}).get("sha256") != runtime.get("handoff_base_sha256")):
                return False, "current runtime metadata binding differs"
            mutable = {prefix + name for name in code} | {prefix + "branch-runtime.json", prefix + "resume-base.json"}
            changed = [name for name in old if old[name] != new[name]]
            if not changed or any(name not in mutable for name in changed):
                return False, "non-runtime reference input or native asset changed"
            outputs = checkpoint.get("outputs")
            if not isinstance(outputs, list) or self._output_identities(prepared) != outputs:
                return False, "completed reference outputs changed"
            refreshed = self.prepare(prepared.unit_id, command_relpath)
            if (refreshed is None or refreshed.input_fingerprint != prepared.input_fingerprint
                    or prepared.path.read_bytes() != original_bytes):
                return False, "reference inputs or checkpoint changed during migration validation"
            if not isinstance(checkpoint.get("runtime_transitions", []), list):
                return False, "completed checkpoint transition history is invalid"
            reason = f"reviewed runtime-only reference transition {old_profile} -> {new_profile}"
            if dry_run:
                return True, reason + " (read only)"
            backup = prepared.path.with_name(prepared.path.name + ".before-runtime-" + uuid.uuid4().hex)
            with backup.open("xb") as handle:
                handle.write(original_bytes)
            updated = dict(checkpoint)
            updated.update(input_payload=current, input_fingerprint=prepared.input_fingerprint)
            updated["runtime_transitions"] = [*checkpoint.get("runtime_transitions", []),
                {"from_source_profile":old_profile, "to_source_profile":new_profile,
                 "previous_input_fingerprint":checkpoint["input_fingerprint"],
                 "previous_checkpoint":str(backup.relative_to(self.server_dir)),
                 "outputs_unchanged":True}]
            try:
                atomic_write_json(prepared.path, updated)
                valid, detail = self.validate(prepared)
                if not valid:
                    raise OrchestrationContractError(detail)
            except BaseException:
                atomic_write_json(prepared.path, checkpoint)
                raise
            return True, reason
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, OrchestrationContractError) as exc:
            return False, f"completed reference runtime migration refused: {exc}"

    def commit(self, prepared: PreparedOuterCheckpoint) -> Path:
        outputs = self._output_identities(prepared)
        if prepared.kind == "q0_chromosome_alignments":
            # Bind outputs to the inputs captured BEFORE execution, including
            # manual runs. A new manager also refreshes tool/option identities.
            current = OuterCheckpointManager(self.server_dir).prepare(
                prepared.unit_id, str(prepared.input_payload["command_relpath"]))
            if current is None or current.input_fingerprint != prepared.input_fingerprint:
                raise OrchestrationContractError("q0 alignment inputs changed during execution")
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

    def validate_grt_unit(self, unit_id: str) -> tuple[bool, str]:
        """Compatibility method for existing runner integrations."""
        return self.validate_lgz_unit(unit_id)

    def validate_lgz_unit(self, unit_id: str) -> tuple[bool, str]:
        stages = LGZ_STAGE_MAP.get(unit_id)
        if stages is None:
            return True, "no LGZ checkpoint validation required"
        status_rows = self._read_tsv("metadata/grt_stage_status.tsv")
        for stage in stages:
            checkpoint_path = workspace_join(self.server_dir, f"grt/checkpoints/{stage}.json")
            if not checkpoint_path.is_file():
                return False, f"LGZ checkpoint is missing: {checkpoint_path}"
            try:
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                return False, f"LGZ checkpoint cannot be read: {checkpoint_path}: {exc}"
            if not isinstance(checkpoint, dict):
                return False, f"LGZ checkpoint is not an object: {checkpoint_path}"
            if (
                checkpoint.get("workflow") != LGZ_WORKFLOW
                or checkpoint.get("stage") != stage
                or checkpoint.get("status") != "success"
                or not isinstance(checkpoint.get("input_fingerprint"), str)
                or not checkpoint.get("input_fingerprint")
            ):
                return False, f"LGZ checkpoint identity/status is invalid: {checkpoint_path}"
            output_hashes = checkpoint.get("output_hashes")
            if not isinstance(output_hashes, dict) or not output_hashes:
                return False, f"LGZ checkpoint output manifest is invalid: {checkpoint_path}"
            for relpath, expected_hash in output_hashes.items():
                if not isinstance(relpath, str) or not isinstance(expected_hash, str):
                    return False, f"LGZ checkpoint output entry is invalid: {checkpoint_path}"
                try:
                    output_path = self._server_artifact(relpath)
                except OrchestrationContractError as exc:
                    return False, str(exc)
                if not output_path.is_file():
                    return False, f"LGZ checkpoint output is missing: {output_path}"
                if sha256_file(output_path) != expected_hash:
                    return False, f"LGZ checkpoint output hash changed: {output_path}"
            required_directories = checkpoint.get("required_directories", [])
            if not isinstance(required_directories, list):
                return False, f"LGZ checkpoint directory manifest is invalid: {checkpoint_path}"
            for relpath in required_directories:
                try:
                    directory = self._server_artifact(relpath) if isinstance(relpath, str) else None
                except OrchestrationContractError as exc:
                    return False, str(exc)
                if directory is None or not directory.is_dir():
                    return False, f"LGZ checkpoint directory is missing: {directory}"
            matching_rows = [row for row in status_rows if row.get("stage") == stage]
            if len(matching_rows) != 1 or matching_rows[0].get("status") != "success":
                return False, f"LGZ stage status is incomplete: {stage}"
            row = matching_rows[0]
            if row.get("checkpoint_relpath") != f"grt/checkpoints/{stage}.json":
                return False, f"LGZ stage checkpoint path is invalid: {stage}"
            if row.get("checkpoint_sha256") != sha256_file(checkpoint_path):
                return False, f"LGZ stage checkpoint hash changed: {stage}"
        return True, f"LGZ checkpoints valid: {', '.join(stages)}"

    def validate_evidence(self) -> tuple[bool, str]:
        required = [
            workspace_join(self.server_dir, "metadata/grt_contract_summary.json"),
            workspace_join(self.server_dir, "metadata/grt_used_contigs.tsv"),
            workspace_join(self.server_dir, "metadata/grt_final_path.json"),
        ]
        missing = next((path for path in required if not path.is_file()), None)
        if missing is not None:
            return False, f"evidence output is missing: {missing}"
        try:
            summary = validate_contract(self.server_dir)
            recorded = json.loads(
                (workspace_join(self.server_dir, "metadata/grt_contract_summary.json")).read_text(encoding="utf-8")
            )
            if not isinstance(recorded, dict):
                return False, "evidence contract summary is not an object"
            for key in ("workflow", "schema_version", "q0_sha256", "q4_sha256"):
                if recorded.get(key) != summary.get(key):
                    return False, f"evidence contract summary disagrees for {key}"
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, ContractError) as exc:
            return False, f"evidence contract validation failed: {exc}"
        return True, "evidence and Server contract are valid"

    def _server_artifact(self, relpath: str) -> Path:
        path = Path(relpath)
        if not relpath or path.is_absolute() or ".." in path.parts or "\\" in relpath:
            raise OrchestrationContractError(f"invalid LGZ artifact path: {relpath!r}")
        resolved = (workspace_join(self.server_dir, path)).resolve()
        try:
            resolved.relative_to(self.server_dir)
        except ValueError as exc:
            raise OrchestrationContractError(
                f"LGZ artifact escapes the Server workspace: {relpath!r}"
            ) from exc
        return resolved

    def validate_package(self, package_kind: str) -> tuple[bool, str]:
        if package_kind not in {"full", "light"}:
            return False, f"unsupported delivery package kind: {package_kind}"
        return validate_delivery_staging(self.server_dir, package_kind)

    def _read_options(self) -> dict[str, str]:
        if self._options is not None:
            return self._options
        path = workspace_join(self.server_dir, "metadata/prepare_options.tsv")
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
        path = workspace_join(self.server_dir, relpath)
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as exc:
            raise OrchestrationContractError(f"cannot read {path}: {exc}") from exc
        if len(rows) != 1:
            raise OrchestrationContractError(f"expected one row in {path}")
        return rows[0]

    def _read_datasets(self) -> list[dict[str, str]]:
        path = workspace_join(self.server_dir, "metadata/datasets.tsv")
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

    @staticmethod
    def _repeat_cen_scan(operation: Path) -> bool:
        command = operation / "command.sh"
        return command.is_file() and "/tools/cen_scan.py" in command.read_text(encoding="utf-8")

    def _alignment_tools(self) -> list[dict[str, object]]:
        engine = self._read_options()["alignment_engine"]
        if engine != "minimap2":
            raise OrchestrationContractError(
                f"unsupported alignment engine: {engine}; only minimap2 is supported"
            )
        return [self._tool_identity("minimap2")]

    def _alignment_options(self) -> dict[str, str]:
        return self._selected_options(
            [
                "alignment_engine",
                "threads",
                "minimap_preset",
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
            workspace_join(self.server_dir, command_relpath),
            workspace_join(self.server_dir, "metadata/reference.tsv"),
            workspace_join(self.server_dir, "metadata/datasets.tsv"),
            workspace_join(self.server_dir, reference["fasta_relpath"]),
            workspace_join(self.server_dir, reference["fai_relpath"]),
            workspace_join(self.server_dir, dataset["fasta_relpath"]),
            workspace_join(self.server_dir, dataset["fai_relpath"]),
        ]
        branch_runtime = workspace_join(self.server_dir, ".prepare_lib/tools/long_cigar_recovery")
        if (branch_runtime.is_dir() and "long_cigar_recovery/server_alignment.py"
                in (workspace_join(self.server_dir, command_relpath)).read_text(encoding="utf-8")):
            paths.extend(sorted(p for p in branch_runtime.rglob("*")
                                if p.is_file() and "__pycache__" not in p.parts))
        manifest = (workspace_join(self.server_dir, command_relpath)).parent / "alignment_tasks.json"
        if manifest.is_file():
            paths.append(manifest)
        parameters = self._alignment_options()
        fraction = self._read_options().get("minimap_filter", "default")
        if fraction != "default":
            parameters["minimap_filter"] = fraction
        return {
            "parameters": parameters,
            "tools": self._alignment_tools(),
            "inputs": self._identities(paths),
        }

    def _assignment_inputs(self, command_relpath: str) -> dict[str, object]:
        reference = self._read_single_tsv("metadata/reference.tsv")
        datasets = self._read_datasets()
        paths = [
            workspace_join(self.server_dir, command_relpath),
            workspace_join(self.server_dir, ".prepare_lib/tools/track_member_order.py"),
            workspace_join(self.server_dir, "metadata/package.tsv"),
            workspace_join(self.server_dir, "metadata/prepare_options.tsv"),
            workspace_join(self.server_dir, "metadata/reference.tsv"),
            workspace_join(self.server_dir, "metadata/datasets.tsv"),
            workspace_join(self.server_dir, reference["fasta_relpath"]),
            workspace_join(self.server_dir, reference["fai_relpath"]),
        ]
        for dataset in datasets:
            paths.extend(
                [
                    workspace_join(self.server_dir, dataset["fasta_relpath"]),
                    workspace_join(self.server_dir, dataset["fai_relpath"]),
                    workspace_join(self.server_dir, f"runs/{dataset['dataset_name']}_vs_ref/result.paf"),
                    workspace_join(self.server_dir, f"runs/{dataset['dataset_name']}_vs_ref/tool_version.txt"),
                ]
            )
        for optional in [
            workspace_join(self.server_dir, ".prepare_lib/tools/assign_chr_groups.py"),
            workspace_join(self.server_dir, ".prepare_lib/tools/alignment_tasks.py"),
            workspace_join(self.server_dir, ".prepare_lib/tools/self_alignment_batches.py"),
            workspace_join(self.server_dir, "tel/rules.tsv"),
            workspace_join(self.server_dir, "cen/reference.tsv"),
            workspace_join(self.server_dir, "cen/library.fa"),
            workspace_join(self.server_dir, "metadata/annotation_library_snapshot.json"),
            workspace_join(self.server_dir, ".prepare_lib/tools/tel_scan.py"),
            workspace_join(self.server_dir, ".prepare_lib/tools/cen_scan.py"),
            workspace_join(self.server_dir, ".prepare_lib/tools/annotation_library.py"),
        ]:
            if optional.is_file():
                paths.append(optional)
        centromere_dir = workspace_join(self.server_dir, "data/centromere")
        if centromere_dir.is_dir():
            paths.extend(path for path in centromere_dir.rglob("*") if path.is_file())
        return {
            "parameters": self._selected_options(
                [
                    "chr_assignment_min_coverage_percent",
                    "alignment_engine",
                    "threads",
                    "minimap_preset",
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

    @staticmethod
    def _chromosome_operations(run_dir: Path, *, alignment_only: bool = False) -> list[Path]:
        # Old prepared chr commands retain their all-in-one checkpoint shape.
        # New workspaces have separate q0 alignment and later annotation units.
        split = (run_dir / "q0_command.sh").is_file()
        operations = []
        declared = None
        descriptor = run_dir / "q0_alignment_inputs.json"
        if descriptor.is_file():
            if alignment_only:
                rows = json.loads(descriptor.read_text(encoding="utf-8"))["alignments"]
                declared = {Path(row["run_dir"]).name for row in rows}
            else:
                rows = json.loads((run_dir / "alignment_tasks.json").read_text(encoding="utf-8"))["tasks"]
                declared = {Path(row["command"]).parent.name for row in rows}
        for child in sorted(run_dir.iterdir()):
            if declared is not None and child.name not in declared:
                continue
            if not child.is_dir() or child.name in {"datasets", "add_ctg"}:
                continue
            scan = child.name in {"tel_scan", "cen_scan"}
            if alignment_only and scan:
                continue
            if not alignment_only and split and not scan:
                continue
            operations.append(child)
        return operations

    def _chromosome_inputs(self, chromosome: str, command_relpath: str,
                           *, alignment_only: bool = False) -> dict[str, object]:
        run_dir = workspace_join(self.server_dir, f"runs/chr_{chromosome}")
        split = (run_dir / "q0_command.sh").is_file()
        paths = [
            workspace_join(self.server_dir, command_relpath),
            run_dir / ("q0_generated_command.sh" if alignment_only else "generated_command.sh"),
            workspace_join(self.server_dir, "metadata/prepare_options.tsv"),
            workspace_join(self.server_dir, "metadata/chr_assignments.tsv"),
            workspace_join(self.server_dir, "metadata/track_member_orders.tsv"),
        ]
        manifest = run_dir / ("q0_alignment_tasks.json" if alignment_only else "alignment_tasks.json")
        if alignment_only or split or manifest.is_file():
            paths.append(manifest)
        descriptor = run_dir / "q0_alignment_inputs.json"
        if alignment_only and descriptor.is_file():
            paths.append(descriptor)
        datasets_dir = run_dir / "datasets"
        if datasets_dir.is_dir():
            paths.extend(path for path in datasets_dir.rglob("*") if path.is_file())
        operations = self._chromosome_operations(run_dir, alignment_only=alignment_only)
        for child in operations:
            command = child / "command.sh"
            if command.is_file():
                paths.append(command)
            paths.extend(path for path in child.glob("*.fa") if path.is_file())
            batch_manifest = child / "self_batch_manifest.json"
            if batch_manifest.is_file():
                paths.append(batch_manifest)
                paths.extend(
                    path
                    for pattern in ("batches/batch-*/command.sh", "batches/batch-*/query.fa")
                    for path in child.glob(pattern)
                    if path.is_file()
                )
            for support_name in ("self_name_map.tsv", "restore_self_paf.py"):
                support_path = child / support_name
                if support_path.is_file():
                    paths.append(support_path)
        optional_names = [".prepare_lib/tools/self_alignment_batches.py"] if alignment_only else [
            ".prepare_lib/tools/self_alignment_batches.py",
            "tel/rules.tsv", "cen/reference.tsv", "cen/library.fa",
            "metadata/annotation_library_snapshot.json",
            ".prepare_lib/tools/tel_scan.py", ".prepare_lib/tools/cen_scan.py", ".prepare_lib/tools/annotation_library.py",
        ]
        for name in optional_names:
            path = workspace_join(self.server_dir, name)
            if path.is_file():
                paths.append(path)
        if not alignment_only:
            centromere_dir = workspace_join(self.server_dir, "data/centromere")
            if centromere_dir.is_dir():
                paths.extend(path for path in centromere_dir.rglob("*") if path.is_file())
        has_alignment = any(child.name not in {"tel_scan", "cen_scan"} for child in operations)
        cen_scan = next((child for child in operations if child.name == "cen_scan"), None)
        repeat_scan = cen_scan is not None and self._repeat_cen_scan(cen_scan)
        tools = self._alignment_tools() if has_alignment or (cen_scan and not repeat_scan) else []
        if repeat_scan:
            tools.extend([self._tool_identity("nucmer"), self._tool_identity("show-coords")])
        uses_python = any(child.name in {"tel_scan", "cen_scan"}
                          or (child / "restore_self_paf.py").is_file() for child in operations)
        if uses_python:
            tools.append(self._tool_identity("python3"))
        return {
            "parameters": self._selected_options([
                "alignment_engine", "threads", "minimap_preset", "skip_self",
                "tel_enabled", "cen_enabled", "cen_min_len", "cen_min_identity",
            ]),
            "tools": tools,
            "inputs": self._identities(paths),
        }

    def _output_identities(
        self, prepared: PreparedOuterCheckpoint
    ) -> list[dict[str, object]]:
        if prepared.kind == "reference_alignment":
            dataset_name = prepared.unit_id.removeprefix("ref:")
            paths = [
                workspace_join(self.server_dir, f"runs/{dataset_name}_vs_ref/result.paf"),
                workspace_join(self.server_dir, f"runs/{dataset_name}_vs_ref/tool_version.txt"),
            ]
        elif prepared.kind == "assignment":
            paths = self._assignment_output_paths()
        elif prepared.kind == "q0_chromosome_alignments":
            chromosome = prepared.unit_id.split(":", 1)[1]
            paths = self._chromosome_output_paths(chromosome, alignment_only=True)
        elif prepared.kind == "chromosome_local":
            chromosome = prepared.unit_id.removeprefix("chr:")
            paths = self._chromosome_output_paths(chromosome)
        else:
            raise OrchestrationContractError(f"unsupported checkpoint kind: {prepared.kind}")
        for path in paths:
            if path.suffix.lower() == ".paf":
                validate_paf(path, require_cigar=True)
        return self._identities(paths)

    def _assignment_output_paths(self) -> list[Path]:
        paths = [
            workspace_join(self.server_dir, "metadata/chr_assignments.tsv"),
            workspace_join(self.server_dir, "metadata/track_member_orders.tsv"),
            workspace_join(self.server_dir, "metadata/source_seq_locator.tsv"),
            workspace_join(self.server_dir, "metadata/source_seq_n_regions.tsv"),
            workspace_join(self.server_dir, "metadata/reference_chr_locator.tsv"),
        ]
        for root_relpath in ["data/reference/chrs", "data/partitions"]:
            root = workspace_join(self.server_dir, root_relpath)
            if not root.is_dir():
                raise OrchestrationContractError(f"assignment output directory is missing: {root}")
            paths.extend(path for path in root.rglob("*") if path.is_file())
        locator_rows = self._read_tsv("metadata/reference_chr_locator.tsv")
        chromosome_names = [row.get("reference_chr_name", "") for row in locator_rows]
        if not chromosome_names or any(not name for name in chromosome_names):
            raise OrchestrationContractError(
                "reference chromosome locator contains no valid chromosome names"
            )
        chr_dirs = [workspace_join(self.server_dir, f"runs/chr_{name}") for name in chromosome_names]
        for run_dir in chr_dirs:
            for required in [run_dir / "command.sh", run_dir / "generated_command.sh"]:
                paths.append(required)
            manifest = run_dir / "alignment_tasks.json"
            if manifest.is_file():
                paths.append(manifest)
            if (run_dir / "q0_command.sh").is_file():
                paths.extend(run_dir / name for name in (
                    "q0_command.sh", "q0_generated_command.sh", "q0_alignment_tasks.json"))
            datasets_dir = run_dir / "datasets"
            if datasets_dir.is_dir():
                paths.extend(path for path in datasets_dir.rglob("*") if path.is_file())
            descriptor = run_dir / "q0_alignment_inputs.json"
            if descriptor.is_file():
                paths.append(descriptor)
                operation_dirs = sorted(set(self._chromosome_operations(run_dir, alignment_only=True)
                                            + self._chromosome_operations(run_dir)))
            else:
                operation_dirs = [child for child in run_dir.iterdir()
                                  if child.is_dir() and child.name not in {"datasets", "add_ctg"}]
            for child in operation_dirs:
                command = child / "command.sh"
                if command.is_file():
                    paths.append(command)
                paths.extend(path for path in child.glob("*.fa") if path.is_file())

                for support_name in ("self_name_map.tsv", "restore_self_paf.py"):

                    support_path = child / support_name

                    if support_path.is_file():

                        paths.append(support_path)
        return paths

    def _read_tsv(self, relpath: str) -> list[dict[str, str]]:
        path = workspace_join(self.server_dir, relpath)
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                return list(csv.DictReader(handle, delimiter="\t"))
        except (OSError, UnicodeError, csv.Error) as exc:
            raise OrchestrationContractError(f"cannot read {path}: {exc}") from exc

    def _chromosome_output_paths(self, chromosome: str, *, alignment_only: bool = False) -> list[Path]:
        run_dir = workspace_join(self.server_dir, f"runs/chr_{chromosome}")
        paths: list[Path] = []
        operation_dirs = self._chromosome_operations(run_dir, alignment_only=alignment_only)
        for operation in operation_dirs:
            if operation.name == "tel_scan":
                tel_outputs = sorted((workspace_join(self.server_dir, f"tel/chr_{chromosome}")).glob("*.tsv"))
                if not tel_outputs:
                    raise OrchestrationContractError(
                        f"telomere scan outputs are missing for chromosome {chromosome}"
                    )
                paths.extend(tel_outputs)
                continue
            if operation.name == "cen_scan" and self._repeat_cen_scan(operation):
                paths.append(workspace_join(self.server_dir, f"cen/chr_{chromosome}/marks.tsv"))
                coords = sorted(operation.glob("dataset_*.coords.tsv"))
                if not coords:
                    raise OrchestrationContractError(f"centromere scan outputs are missing: {operation}")
                paths.extend(coords)
                continue
            paf_paths = sorted(operation.glob("result*.paf"))
            if not paf_paths:
                raise OrchestrationContractError(
                    f"alignment output is missing for chromosome operation: {operation}"
                )
            paths.extend(paf_paths)
            if operation.name == "cen_scan":
                paths.append(workspace_join(self.server_dir, f"cen/chr_{chromosome}/marks.tsv"))
        return paths


# Compatibility constants; persisted values remain unchanged.
GRT_WORKFLOW = LGZ_WORKFLOW
GRT_STAGE_MAP = LGZ_STAGE_MAP


def main() -> None:
    """Run a manual q0 chromosome command against a pre-execution input snapshot.

    The adaptive runner commits the same checkpoint after all leaf tasks succeed.
    This entrypoint keeps prepare.sh's printed per-stage commands equivalent.
    """
    import argparse
    import subprocess
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--server-dir", required=True, type=Path)
    parser.add_argument("--run-q0-chr", required=True)
    args = parser.parse_args()
    # Match the ordinary plan's name restrictions before constructing a path.
    try:
        from run_orchestration import q0_chromosome_unit_id
    except ModuleNotFoundError:
        from .run_orchestration import q0_chromosome_unit_id
    try:
        unit = q0_chromosome_unit_id(args.run_q0_chr)
        manager = OuterCheckpointManager(args.server_dir)
        prepared = manager.prepare(unit, f"runs/chr_{args.run_q0_chr}/q0_command.sh")
        assert prepared is not None
        run_dir = manager.server_dir / f"runs/chr_{args.run_q0_chr}"
        result = subprocess.run(["bash", str(run_dir / "q0_generated_command.sh")], cwd=run_dir)
        if result.returncode:
            raise SystemExit(result.returncode if result.returncode > 0 else 128 - result.returncode)
        manager.commit(prepared)
    except (OSError, ValueError, OrchestrationContractError) as exc:
        parser.exit(1, f"q0 alignment checkpoint failed: {exc}\n")


if __name__ == "__main__":
    main()
