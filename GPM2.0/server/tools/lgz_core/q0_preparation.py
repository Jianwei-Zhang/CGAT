"""Prepare and content-bind alignment evidence for the new q0 path builder.

Raw chr-local alignments are reused; only missing fragment relationships are
mapped here. A ready manifest is published atomically after every task succeeds.
"""
from __future__ import annotations

try:
    from workspace_layout import LayoutError, WorkspaceLayout
except ModuleNotFoundError:
    from ..workspace_layout import LayoutError, WorkspaceLayout


from collections import defaultdict
from contextlib import nullcontext, closing
import csv
import json
from pathlib import Path
import subprocess
import shutil
import stat
import uuid
from typing import Iterable

from .common import canonical_json, executable_identity, read_fasta, sha256_file, stable_id, write_fasta
from .q0_alignments import read_paf, read_paf_observations
from .q0_catalog import (CATALOG_SCHEMA, CandidateCatalog, DISCOVERY_REFERENCE_IDENTITY, DISCOVERY_REFERENCE_MAPQ,
                         add_pairwise_candidates, build_catalog, partial_source_request, supplemental_groups, ObservedSourcePairs)
from .q0_regional_discovery import REGIONAL_POLICY, LocalReferenceCache, enabled as regional_enabled, observe_part_hits, prepare_partial
from .q0_regional_candidates import CANDIDATE_POLICY, CandidatePlan, CompletedNativeScopes, prepare_candidates
from .q0_cigar_policy import WEAK_GLOBAL_SEED_POLICY, weak_global_seed_scope
from .q0_sources import Q0EvidenceError, SourceKey
from .q0_scope_policy import (AUTO_SCOPE, FULL_SCOPE, PROOF_REPAIR_SCOPE, AutoScopePolicy, ScopeDecision,
                              ScopeWorkload, decide_scope)
try:
    from run_orchestration import atomic_write_json, sha256_file as _partition_sha256
    from run_orchestration import file_identity as _file_identity, file_signature, OrchestrationContractError
except ModuleNotFoundError:
    from ..run_orchestration import atomic_write_json, sha256_file as _partition_sha256
    from ..run_orchestration import file_identity as _file_identity, file_signature, OrchestrationContractError

def _default_checkpoint_manager(root):
    # Keep the module-level injection point used by provenance-aware incident
    # readers, without loading the complete workflow just to use regional caches.
    try:
        from run_outer_checkpoints import OuterCheckpointManager as manager
    except ModuleNotFoundError:
        from ..run_outer_checkpoints import OuterCheckpointManager as manager
    return manager(root)


OuterCheckpointManager = _default_checkpoint_manager


SCHEMA = "lgz_q0_evidence_v1"
MANIFEST = "metadata/grt_q0_evidence.json"
MAX_PROOF_REPAIRS = 2
MAPPING_OUTPUT_FILES = ("query.fa", "target.fa", "result.paf", "command.json")
POLICY = {"version": 5, "weak_global_seed": WEAK_GLOBAL_SEED_POLICY, "regional_partial_discovery": REGIONAL_POLICY, "regional_candidate_discovery": CANDIDATE_POLICY, "min_gap": 100, "discovery": "unplaced_to_new_anchors_until_fixed_point",
          "supplement": "out_of_group_split_and_missing_ref_neighbors",
          "partial_source_discovery_min_uncovered_bp": 100,
          "partial_source_reference_identity": DISCOVERY_REFERENCE_IDENTITY,
          "partial_source_reference_mapq": DISCOVERY_REFERENCE_MAPQ,
          "supplement_flags": ["-D", "-P", "--dual=yes", "--no-long-join"]}


def _artifact_member(relative: str) -> Path:
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise Q0EvidenceError(f"invalid q0 artifact path: {relative!r}")
    return path


def workspace_artifact_path(root: Path, relative: str) -> Path:
    try:
        return WorkspaceLayout.detect(root).path(_artifact_member(relative))
    except LayoutError as exc:
        raise Q0EvidenceError(f"invalid q0 workspace artifact {relative!r}: {exc}") from exc


def artifact_path(root: Path, relative: str) -> Path:
    resolved = workspace_artifact_path(root, relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise Q0EvidenceError(f"q0 artifact escapes workspace: {relative}") from exc
    return resolved


def identity(root: Path, relative: str) -> dict:
    path = workspace_artifact_path(root, relative)
    try:
        bound = _file_identity(path, within=root)
    except OrchestrationContractError as exc:
        raise Q0EvidenceError(f"cannot bind q0 artifact {relative}: {exc}") from exc
    # Receipt paths are logical workspace names, not resolved target paths.
    bound["path"] = relative
    return bound


def json_file(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise Q0EvidenceError(f"cannot read q0 JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise Q0EvidenceError(f"q0 JSON must be an object: {path}")
    return value


def table(root: Path, relative: str, fields: Iterable[str]) -> list[dict[str, str]]:
    try:
        with artifact_path(root, relative).open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not set(fields) <= set(reader.fieldnames or ()):
                raise Q0EvidenceError(f"q0 table lacks required fields: {relative}")
            return list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise Q0EvidenceError(f"cannot read q0 table {relative}: {exc}") from exc


def builder_identity() -> str:
    root = Path(__file__).parent
    return stable_id("q0-evidence-builder", [
        [name, sha256_file(root / name)] for name in (
            "q0_preparation.py", "q0_catalog.py", "q0_sources.py", "q0_alignments.py", "q0_paf_io.py", "common.py",
            "q0_query_windows.py", "q0_reference_index.py", "q0_regional_mapping.py",
            "q0_cigar_policy.py", "q0_mapper_guard.py", "q0_native_frontier.py", "q0_frontier_scope.py", "q0_scope_policy.py",
            "q0_regional_discovery.py", "q0_neighbor_requests.py", "q0_regional_candidates.py", "q0_regional_execution.py")])


def supplement_policy(scope: str) -> dict:
    """Bind the explicit Q0-only profile without editing base checkpoint inputs."""
    if scope == "full":
        return POLICY
    from .q0_threshold_acceptance import SCOPE as threshold_scope
    if scope not in ("decision_frontier", PROOF_REPAIR_SCOPE, threshold_scope):
        raise Q0EvidenceError("unsupported q0 supplement scope")
    from .q0_admission import selector_identity
    from .q0_frontier_scope import FRONTIER_FLANK_BP
    frontier = {"version": 2, "flank_bp": FRONTIER_FLANK_BP,
                "selector": selector_identity(), "whole_source_equivalence": False}
    if scope == PROOF_REPAIR_SCOPE:
        frontier["repair"] = {"version": 1, "maximum_rounds": MAX_PROOF_REPAIRS, "requires_no_reads_qc": True}
    if scope == threshold_scope:
        from .q0_threshold_acceptance import contract
        frontier["threshold"] = contract()
    return {**POLICY, "decision_frontier": frontier}


def _request_identity(inputs, tool, policy, builder, scope_decision=None):
    payload = {"inputs": inputs, "tool": tool, "policy": policy, "builder": builder}
    if scope_decision is not None:
        payload["automatic_scope_decision"] = scope_decision
    return stable_id("q0-evidence-input", payload)


def load_verified_evidence(root: Path, *, _draft=None) -> dict:
    """No fallback: consumers must reject missing, stale, or damaged evidence."""
    root = root.resolve()
    # Repair verifies complete private in-memory manifests through the same
    # consumer. Canonical callers never see intermediate scoped generations.
    manifest = json_file(workspace_artifact_path(root, MANIFEST)) if _draft is None else _draft
    policy = manifest.get("policy")
    frontier = policy.get("decision_frontier") if isinstance(policy, dict) else None
    scoped = isinstance(frontier, dict)
    scope = "full"
    from .q0_threshold_acceptance import SCOPE as threshold_scope
    if scoped:
        scope = threshold_scope if "threshold" in frontier else (PROOF_REPAIR_SCOPE if "repair" in frontier else "decision_frontier")
    if (manifest.get("schema") != SCHEMA or manifest.get("status") != "success"
            or policy != supplement_policy(scope) or manifest.get("builder") != builder_identity()):
        raise Q0EvidenceError("q0 evidence manifest has an unsupported or stale identity")
    for field in ("inputs", "outputs"):
        rows = manifest.get(field)
        if not isinstance(rows, list) or not rows:
            raise Q0EvidenceError(f"q0 evidence manifest has no {field}")
        paths = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("path"), str):
                raise Q0EvidenceError(f"invalid q0 {field} identity")
            if row["path"] in paths or identity(root, row["path"]) != row:
                raise Q0EvidenceError(f"q0 evidence changed or duplicated: {row['path']}")
            paths.add(row["path"])
    outputs = {row["path"]: row for row in manifest["outputs"]}
    if manifest.get("catalog") not in outputs:
        raise Q0EvidenceError("q0 candidate catalog is not bound to its manifest")
    catalog = json_file(artifact_path(root, manifest["catalog"]))
    if catalog.get("schema") != CATALOG_SCHEMA:
        raise Q0EvidenceError("unsupported q0 candidate catalog")
    report = catalog.get("supplement_scope")
    if scoped:
        allowed_requests = (scope, AUTO_SCOPE) if scope == PROOF_REPAIR_SCOPE else (scope,)
        if (not isinstance(report, dict) or report.get("requested") not in allowed_requests
                or report.get("effective") not in (("full", "decision_frontier", "base_only") if scope == threshold_scope else ("full", "decision_frontier"))
                or not isinstance(report.get("unsearched_part_intervals"), list)):
            raise Q0EvidenceError("q0 supplemental catalog lacks its bound scope")
        if report.get("requested") == AUTO_SCOPE:
            decision = report.get("decision")
            if (not isinstance(decision, dict)
                    or decision.get("schema") != "lgz_q0_scope_decision_v1"
                    or decision.get("effective_scope") != PROOF_REPAIR_SCOPE):
                raise Q0EvidenceError("automatic Q0 scope decision is not bound to proof repair")
        skipped = 0
        for phase in ("regional_partial_discovery", "regional_candidate_discovery"):
            if phase not in catalog:
                continue
            r = catalog[phase]
            if (not isinstance(r, dict) or r.get("frontier_scope") is not (report["effective"] == "decision_frontier")
                    or type(r.get("frontier_omitted_windows")) is not int or r["frontier_omitted_windows"] < 0):
                raise Q0EvidenceError("q0 regional omission report disagrees with its bound scope")
            skipped += r["frontier_omitted_windows"]
        if (bool(skipped) != bool(report["unsearched_part_intervals"])
                or (report["effective"] == "full" and skipped)):
            raise Q0EvidenceError("q0 scope and its omitted intervals disagree")
    elif report is not None:
        if (not isinstance(report, dict) or report.get("requested") != AUTO_SCOPE
                or report.get("effective") != FULL_SCOPE
                or report.get("unsearched_part_intervals") != []):
            raise Q0EvidenceError("full q0 manifest cannot attest scoped supplemental work")
        decision = report.get("decision")
        if (not isinstance(decision, dict)
                or decision.get("schema") != "lgz_q0_scope_decision_v1"
                or decision.get("effective_scope") != FULL_SCOPE):
            raise Q0EvidenceError("automatic full-scope decision is not bound")
    decision_record = report["decision"] if report and report.get("requested") == AUTO_SCOPE else None
    if manifest.get("input_fingerprint") != _request_identity(
            manifest["inputs"], manifest.get("tool"), policy, manifest["builder"], decision_record):
        raise Q0EvidenceError("q0 evidence input fingerprint is inconsistent")
    if scope == PROOF_REPAIR_SCOPE:
        _readless_package(root)
        required = [row for row in manifest["inputs"] if row["path"] == "metadata/package.tsv"]
        repair_rounds = report.get("proof_repair_rounds")
        if (len(required) != 1 or type(repair_rounds) is not int or not 0 <= repair_rounds <= MAX_PROOF_REPAIRS
                or identity(root, "metadata/package.tsv") != required[0]):
            raise Q0EvidenceError("q0 proof repair lacks a bound no-reads-QC package or repair round")
    if scope == threshold_scope:
        from .q0_threshold_acceptance import validate_catalog
        validate_catalog(root, manifest, catalog)
    expected_outputs = {manifest["catalog"]}
    inputs = {row["path"] for row in manifest["inputs"]}
    try:
        for row in catalog["base_alignments"]:
            if not {row["query_fasta"], row["target_fasta"], row["paf"]} <= inputs:
                raise Q0EvidenceError("q0 base alignment is not bound to its inputs")
        regional_members = None
        junction_ids = set(report.get('junction_review_task_ids', ())) if scope == threshold_scope else set()
        for task in catalog["supplementary_alignments"]:
            if task.get("kind") == "regional_discovery":
                from .q0_regional_mapping import verify_regional_task
                if regional_members is None:
                    regional_members = {row["segment_id"]: (row["interval"]["end"]-row["interval"]["start"], row["sequence_sha256"])
                                        for row in catalog["segments"]}
                receipt = verify_regional_task(root, task, members=regional_members)
                if task['task_id'] in junction_ids:
                    from .q0_junction_review import verify_windows
                    verify_windows(receipt['spec'])
                if (task["receipt"] not in outputs or any(outputs.get(row["path"]) != row for row in receipt["outputs"])):
                    raise Q0EvidenceError("regional evidence dependencies are not bound to the ready manifest")
                expected_outputs.update({task["receipt"]} | {row["path"] for row in receipt["outputs"]})
                continue
            task_id = task["task_id"]
            relative = f"grt/evidence/q0_prepare/tasks/{task_id}"
            receipt_path = f"{relative}/success.json"
            if task["receipt"] != receipt_path or task["paf"] != f"{relative}/result.paf" or receipt_path not in outputs:
                raise Q0EvidenceError("q0 supplementary task is not bound to its manifest")
            receipt = json_file(artifact_path(root, receipt_path))
            spec = receipt["spec"]
            if (receipt.get("status") != "success" or stable_id("q0-map", spec) != task_id
                    or spec["query_ids"] != task["query_ids"] or spec["target_ids"] != task["target_ids"]):
                raise Q0EvidenceError("q0 supplementary task identity changed")
            required = {f"{relative}/{name}" for name in MAPPING_OUTPUT_FILES}
            if len(receipt["outputs"]) != len(required) or {row["path"] for row in receipt["outputs"]} != required:
                raise Q0EvidenceError("q0 supplementary receipt is incomplete")
            if any(outputs.get(row["path"]) != row for row in receipt["outputs"]):
                raise Q0EvidenceError("q0 supplementary artifacts are not fully bound")
            expected_outputs.update(required | {receipt_path})
        if set(outputs) != expected_outputs:
            raise Q0EvidenceError("q0 output inventory differs from the catalog's requirements")
        # Both inventories are already indexed by path. Rebuilding their
        # union for every PAF record turns a linear check into evidence × files.
        for row in catalog["evidence"].values():
            artifact = row["artifact"]
            if artifact not in inputs and artifact not in outputs:
                raise Q0EvidenceError("q0 candidate references an unbound alignment artifact")
    except (KeyError, TypeError) as exc:
        raise Q0EvidenceError(f"invalid q0 evidence dependency inventory: {exc}") from exc
    return manifest


def _dataset_sequences(root, datasets):
    sources = {}
    for dataset in datasets:
        for name, sequence in read_fasta(artifact_path(root, dataset["fasta_relpath"])):
            key = SourceKey(dataset["dataset_name"], name)
            if key in sources:
                raise Q0EvidenceError(f"duplicate q0 source: {key}")
            sources[key] = sequence
    return sources


def _matrix_paf(chromosome: str, left: str, right: str) -> str:
    stem = f"{left}_vs_self" if left == right else f"{left}_vs_{right}"
    return f"runs/chr_{chromosome}/{stem}/result.paf"


def _initial_inputs(root: Path, *, matrix_reader=None):
    layout = WorkspaceLayout.detect(root)
    datasets = table(root, "metadata/datasets.tsv", ("dataset_name", "fasta_relpath"))
    references = table(root, "metadata/reference.tsv", ("fasta_relpath",))
    assignments = table(root, "metadata/chr_assignments.tsv", ("dataset_name", "seq_name", "assigned_chr_name"))
    options = {row["key"]: row["value"] for row in table(root, "metadata/prepare_options.tsv", ("key", "value"))}
    if len(references) != 1 or not datasets:
        raise Q0EvidenceError("q0 requires one reference and at least one dataset")
    names = [row["dataset_name"] for row in datasets]
    if len(names) != len(set(names)):
        raise Q0EvidenceError("q0 dataset names must be unique")
    # This stage uses only names/lengths; do not retain a multi-Gb reference
    # DNA dictionary alongside all de novo sequences. Still parse every record.
    refs = {name: len(sequence) for name,sequence in read_fasta(artifact_path(root, references[0]["fasta_relpath"]))}
    sources = _dataset_sequences(root, datasets)
    paths = {"metadata/datasets.tsv", "metadata/reference.tsv", "metadata/chr_assignments.tsv",
             "metadata/prepare_options.tsv", "metadata/track_member_orders.tsv",
             references[0]["fasta_relpath"]}
    for dataset in datasets:
        paths.add(dataset["fasta_relpath"])
        relative = f"runs/{dataset['dataset_name']}_vs_ref/result.paf"
        paths.update((relative, f"runs/{dataset['dataset_name']}_vs_ref/tool_version.txt"))
    lengths = dict(refs)
    grouped: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in assignments:
        key = SourceKey(row["dataset_name"], row["seq_name"])
        if key not in sources or row["assigned_chr_name"] not in refs:
            raise Q0EvidenceError("q0 assignment refers to an unknown source or chromosome")
        grouped[row["assigned_chr_name"]][row["dataset_name"]].add(row["seq_name"])
    manager = OuterCheckpointManager(root)
    base_alignments = []
    known_pairs = (ObservedSourcePairs({key: len(value) for key,value in sources.items()})
                   if regional_enabled(lengths, options.get("minimap_preset", "asm10")) else set())
    for chromosome in refs:
        relative = f"runs/chr_{chromosome}/q0_alignment_inputs.json"
        descriptor = json_file(artifact_path(root, relative))
        if descriptor.get("version") != 1 or descriptor.get("chromosome") != chromosome:
            raise Q0EvidenceError(f"invalid q0 chr evidence descriptor: {relative}")
        prepared = manager.prepare(f"q0_chr:{chromosome}", f"runs/chr_{chromosome}/q0_command.sh")
        valid, reason = manager.validate(prepared)
        if not valid:
            raise Q0EvidenceError(f"q0 chr evidence is not complete: {chromosome}: {reason}")
        paths.update((relative, prepared.path.relative_to(root).as_posix()))
        # Bind the successful task's actual source, scripts, parameters and outputs,
        # not just its receipt file. This also detects edits after this stage ends.
        paths.update(row["path"] for row in prepared.input_payload["inputs"])
        paths.update(row["path"] for row in json_file(prepared.path)["outputs"])
        rows = descriptor.get("alignments")
        if not isinstance(rows, list):
            raise Q0EvidenceError(f"invalid q0 chr alignment list: {relative}")
        expected = set()
        group = grouped[chromosome]
        dataset_names = sorted(group)
        for i, left in enumerate(dataset_names):
            if len(group[left]) > 1:
                expected.add((left, left))
            for right in dataset_names[i + 1:]:
                expected.add((left, right))
        actual = set()
        # A partition can occur as both self roles and again in a cross pair.
        # Reuse only a successful sequence/group validation of these exact
        # bytes, within this chromosome and this immutable source context.
        validated_partitions = {}
        for row in rows:
            left, right = row["target_dataset"], row["query_dataset"]
            pair = (left, right)
            if pair not in expected or pair in actual:
                raise Q0EvidenceError(f"unexpected or duplicate q0 pair: {chromosome}:{pair}")
            actual.add(pair)
            expected_paf = layout.relative(_matrix_paf(chromosome, left, right))
            # Old descriptors use logical paths; current producers record
            # numbered paths. Require the same exact owned pair/direction.
            if layout.relative(row["paf"]) != expected_paf:
                raise Q0EvidenceError("q0 pair PAF does not match its declared direction")
            for field, dataset in (("query_fasta", right), ("target_fasta", left)):
                partition = artifact_path(root, row[field])
                digest = _partition_sha256(partition)
                validation_key = (dataset, row[field])
                if validated_partitions.get(validation_key) != digest:
                    records = dict(read_fasta(partition))
                    if set(records) != group[dataset] or any(sources[SourceKey(dataset, key)] != seq for key, seq in records.items()):
                        raise Q0EvidenceError("q0 partition FASTA differs from original sources or grouping")
                    if _partition_sha256(partition) != digest:
                        raise Q0EvidenceError("q0 partition FASTA changed during validation")
                    del records
                    validated_partitions[validation_key] = digest
                paths.add(row[field])
            qlengths = {name: len(sources[SourceKey(right, name)]) for name in group[right]}
            tlengths = {name: len(sources[SourceKey(left, name)]) for name in group[left]}
            qkeys = {name: SourceKey(right, name) for name in qlengths}
            tkeys = {name: SourceKey(left, name) for name in tlengths}
            args = dict(query_lengths=qlengths, target_lengths=tlengths, artifact=row["paf"])
            path = artifact_path(root, row["paf"])
            hits = (read_paf_observations(path, **args) if matrix_reader is None else
                    matrix_reader(path, query_dataset=right, target_dataset=left, **args))
            for hit in hits:
                query, target = qkeys[hit.query_name], tkeys[hit.target_name]
                if isinstance(known_pairs, ObservedSourcePairs):
                    known_pairs.observe_alignment(hit, query, target)
                elif any(op in "M=X" for _length, op in hit.cigar):
                    known_pairs.add(tuple(sorted((query, target))))
            paths.add(row["paf"])
            base_alignments.append({**row, "chromosome": chromosome})
        if actual != expected:
            raise Q0EvidenceError(f"missing required q0 pairs for {chromosome}: {sorted(expected - actual)}")
    return sources, lengths, assignments, options, sorted(paths), sorted(base_alignments, key=lambda row: row["paf"]), known_pairs


# Incident adapters can replace _initial_inputs; never pass a new callback to an unknown reader.
_native_initial_inputs = _initial_inputs


def _provisional_frontier(root: Path, sources, reference_lengths, catalog, base_alignments):
    """Build a base-only Q0 graph for an explicit lossy supplement scope.

    Select path coordinates without materializing DNA or a decision report.
    Reference and cross-assembly base PAFs keep their original bounds and
    CIGARs. As before, self matrices are excluded from this planning input.
    A no-path result falls back to full scope.
    """
    from .q0_admission import EvidenceInput, select_q0_paths
    from .q0_frontier_scope import decision_frontier
    from .q0_paths import PairLink
    from .q0_sources import Interval, OriginalAdjacency

    by_dataset = defaultdict(dict)
    for key, sequence in sources.items():
        by_dataset[key.dataset][key.contig] = len(sequence)
    reference_hits = defaultdict(list)
    pair_links = []
    for dataset, lengths in sorted(by_dataset.items()):
        relative = f"runs/{dataset}_vs_ref/result.paf"
        for hit in read_paf(artifact_path(root, relative), query_lengths=lengths,
                            target_lengths=reference_lengths, artifact=relative):
            source = SourceKey(dataset, hit.query_name)
            reference_hits[source].append(hit)
    for descriptor in base_alignments:
        if descriptor["query_dataset"] == descriptor["target_dataset"]:
            continue
        query_dataset = descriptor["query_dataset"]
        target_dataset = descriptor["target_dataset"]
        relative = descriptor["paf"]
        for hit in read_paf(artifact_path(root, relative), query_lengths=by_dataset[query_dataset],
                            target_lengths=by_dataset[target_dataset], artifact=relative):
            query = SourceKey(query_dataset, hit.query_name)
            target = SourceKey(target_dataset, hit.target_name)
            pair_links.append(PairLink(hit, query, target))
    adjacencies = []
    for row in catalog.payload["original_connections"]:
        edge = OriginalAdjacency(**{**row, "source": SourceKey(**row["source"]),
                                    "gap_interval": Interval(**row["gap_interval"])})
        adjacencies.append(edge)
    data = EvidenceInput(dict(sources), dict(catalog.parts), dict(reference_lengths),
                         dict(reference_hits), tuple(pair_links), tuple(adjacencies), {},
                         "provisional-not-published")
    return decision_frontier(select_q0_paths(data))


def _copy_prepared_target(root, catalog, target_ids, destination, template):
    """Copy an exactly bound completed target input, not a mapping result.

    This permits isolated productive work without loading the whole source DNA
    into a second parent heap. No symlink/hardlink is created to mutable caches.
    The source receipt is embedded in the actual new command provenance.
    """
    from .q0_reference_index import _signature
    source_root = Path(template["root"]).resolve(strict=True)
    receipt_identity = template["receipt"]
    if identity(source_root,receipt_identity["path"]) != receipt_identity:
        raise Q0EvidenceError("prepared target source receipt changed")
    receipt = json_file(artifact_path(source_root,receipt_identity["path"]))
    spec = receipt.get("spec",{})
    relative = f"grt/evidence/q0_prepare/tasks/{stable_id('q0-map',spec)}"
    members = dict(spec.get("members",[]))
    if (receipt.get("status") != "success" or spec.get("schema") != "lgz_q0_mapping_v1"
            or receipt_identity["path"] != relative+"/success.json" or spec.get("target_ids") != target_ids
            or any(members.get(key) != catalog.parts[key].sequence_sha256 for key in target_ids)):
        raise Q0EvidenceError("prepared target source inventory differs")
    outputs = receipt.get("outputs",[])
    expected_paths = {relative+"/"+name for name in MAPPING_OUTPUT_FILES}
    if len(outputs)!=len(expected_paths) or {row.get("path") for row in outputs} != expected_paths:
        raise Q0EvidenceError("prepared target source receipt is incomplete")
    expected = next(row for row in outputs if row["path"]==relative+"/target.fa")
    source = artifact_path(source_root,expected["path"])
    if source.resolve() == destination.resolve():
        raise Q0EvidenceError("prepared target copy would overwrite its source")
    signature = _signature(source)
    if _partition_sha256(source) != expected["sha256"] or source.stat().st_size != expected["size"]:
        raise Q0EvidenceError("prepared target bytes differ from the complete receipt")
    if destination.is_symlink(): raise Q0EvidenceError("linked prepared target destination is forbidden")
    if destination.exists() and (_partition_sha256(destination)!=expected["sha256"] or destination.stat().st_size!=expected["size"]):
        destination.rename(destination.with_name(destination.name+".invalid-"+uuid.uuid4().hex))
    if not destination.exists():
        temporary = destination.with_name(destination.name+".copy-"+uuid.uuid4().hex)
        shutil.copyfile(source,temporary)
        temporary.replace(destination)
    if _partition_sha256(destination)!=expected["sha256"] or destination.stat().st_size!=expected["size"]:
        raise Q0EvidenceError("prepared target copy changed bytes")
    if _signature(source)!=signature or identity(source_root,receipt_identity["path"])!=receipt_identity:
        raise Q0EvidenceError("prepared target source changed during copying")
    return {"schema":"lgz_q0_prepared_target_reuse_v1","source_root":str(source_root),
            "source_receipt_identity":receipt_identity,"source_receipt":receipt,"copied_target":expected}


def _supplement(root: Path, catalog: CandidateCatalog, request: dict, tool: dict,
                preset: str, threads: int, *, skip_self: bool = False, cache_only: bool = False, prepared_target: dict | None = None,
                weak_seed_fast: bool = False, reference_bases: int = 0, on_cache_hit=None) -> dict | None:
    if on_cache_hit is not None and not callable(on_cache_hit):
        raise Q0EvidenceError("cached PAF consumer must be callable")
    if _partition_sha256(Path(tool["resolved"])) != tool["sha256"]:
        raise Q0EvidenceError("q0 supplementary aligner changed during preparation")
    query_ids, target_ids = sorted(set(request["query_ids"])), sorted(set(request["target_ids"]))
    if skip_self:
        targets_by_dataset = defaultdict(set)
        for key in target_ids:
            targets_by_dataset[catalog.parts[key].source.dataset].add(key)
        if any(targets_by_dataset[catalog.parts[key].source.dataset] - {key} for key in query_ids):
            raise Q0EvidenceError("--skip-self conflicts with required q0 supplementary same-dataset comparisons")
    flags=POLICY['supplement_flags']
    if type(weak_seed_fast) is not bool:raise Q0EvidenceError('invalid weak-seed profile selector')
    if weak_seed_fast:
        queries,targets=weak_global_seed_scope(catalog.parts,catalog.reference_routable_parts,query_ids,target_ids,
                                              reference_bases=reference_bases,preset=preset)
        if request['kind']!='candidate_unroutable_seed' or not queries or not targets:
            raise Q0EvidenceError('weak global seed profile is outside its limited scope')
        flags=[*flags,'-m',str(WEAK_GLOBAL_SEED_POLICY['minimum_chain_score'])]
    members = [[key, catalog.parts[key].sequence_sha256] for key in sorted(set(query_ids + target_ids))]
    # Raw mapping identity is independent of candidate-selection code and the
    # discovery round that requested it. Revalidate cached geometry, do not rerun
    # an unchanged mapper/input pair just because the q0 builder was updated.
    spec = {"schema": "lgz_q0_mapping_v1", "query_ids": query_ids, "target_ids": target_ids,
            "members": members, "tool": tool, "preset": preset,
            "alignment_flags": flags}
    task_id = stable_id("q0-map", spec)
    relative = f"grt/evidence/q0_prepare/tasks/{task_id}"
    directory = workspace_artifact_path(root, relative)
    cache = directory / "success.json"
    output = directory / "result.paf"
    required_outputs = {f"{relative}/{name}" for name in MAPPING_OUTPUT_FILES}
    cached = False
    if cache.is_file():
        try:
            expected = json_file(cache)
            cached = (expected.get("spec") == spec and expected.get("status") == "success"
                    and {row["path"] for row in expected["outputs"]} == required_outputs
                    and all(identity(root, row["path"]) == row for row in expected["outputs"]))
        except (Q0EvidenceError, KeyError, TypeError):
            pass
    if cached:
        task = {"task_id": task_id, "kind": request["kind"], "request": request,
                "paf": f"{relative}/result.paf", "receipt": f"{relative}/success.json",
                "query_ids": query_ids, "target_ids": target_ids}
        lengths = {"query_lengths":{key:catalog.parts[key].interval.length for key in query_ids},
                   "target_lengths":{key:catalog.parts[key].interval.length for key in target_ids}}
        if on_cache_hit is not None:
            # Identity checks above still read all committed bytes. Fuse only
            # the redundant validation-only CIGAR pass with the mandatory
            # semantic consumer. Keep the final artifact identity, not .tmp or
            # an absolute-path evidence ID. A failed consumer aborts; never
            # rerun a multi-hour mapper after partially updating the catalog.
            hits = read_paf(output, **lengths, artifact=task["paf"])
            try:
                on_cache_hit(task, hits)
                for _hit in hits: pass  # Even an early-returning consumer cannot omit tail validation.
                if (json_file(cache) != expected
                        or any(identity(root,row["path"]) != row for row in expected["outputs"])):
                    raise Q0EvidenceError("cached mapping changed during evidence consumption")
            finally:
                hits.close()
            return task
        try:
            for _hit in read_paf(output, **lengths): pass
            return task
        except (Q0EvidenceError, KeyError, TypeError):
            pass
    if cache_only:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    query, target = directory / "query.fa", directory / "target.fa"
    write_fasta(query, ((key, catalog.sequence(key)) for key in query_ids))
    target_reuse = None
    if prepared_target is None:
        write_fasta(target, ((key, catalog.sequence(key)) for key in target_ids))
    else:
        target_reuse = _copy_prepared_target(root,catalog,target_ids,target,prepared_target)
    temporary = directory / "result.paf.tmp"
    command = [tool["resolved"], "-c", "-x", preset, *flags, "-t", str(threads),
               "-o", str(temporary), str(target), str(query)]
    command_record = {"argv": command, "spec": spec}
    if target_reuse is not None: command_record["prepared_target_reuse"] = target_reuse
    atomic_write_json(directory / "command.json", command_record)
    input_before = [identity(root, f"{relative}/{name}.fa") for name in ("query", "target")]
    with (directory / "stdout.log").open("w", encoding="utf-8") as stdout, (directory / "stderr.log").open("w", encoding="utf-8") as stderr:
        result = subprocess.run(command, cwd=directory, stdout=stdout, stderr=stderr)
    if result.returncode:
        raise Q0EvidenceError(f"q0 supplementary alignment failed ({result.returncode}); see {relative}/stderr.log")
    if input_before != [identity(root, f"{relative}/{name}.fa") for name in ("query", "target")]:
        raise Q0EvidenceError("q0 supplementary FASTA changed during execution")
    for _hit in read_paf(temporary, query_lengths={key: catalog.parts[key].interval.length for key in query_ids},
                          target_lengths={key: catalog.parts[key].interval.length for key in target_ids}):
        pass
    temporary.replace(output)
    outputs = [identity(root, f"{relative}/{name}") for name in MAPPING_OUTPUT_FILES]
    atomic_write_json(cache, {"status": "success", "spec": spec, "outputs": outputs})
    return {"task_id": task_id, "kind": request["kind"], "request": request,
            "paf": f"{relative}/result.paf", "receipt": f"{relative}/success.json",
            "query_ids": query_ids, "target_ids": target_ids}



def _unroutable_seed(root, catalog, request, tool, preset, threads, *, reference_bases, skip_self=False, on_cache_hit=None):
    """Look up both historical profiles; a cold seed is never a native mapper invocation."""
    def probe(fast):
        return _supplement(root,catalog,request,tool,preset,threads,skip_self=skip_self,cache_only=True,
                           weak_seed_fast=fast,reference_bases=reference_bases,on_cache_hit=on_cache_hit)
    task=probe(False)
    if task is not None: return task
    queries,targets=weak_global_seed_scope(catalog.parts,catalog.reference_routable_parts,
        request['query_ids'],request['target_ids'],reference_bases=reference_bases,preset=preset)
    return probe(True) if queries and targets else None


def _complete_unroutable_seeds(root,catalog,index,query_ids,target_ids,tasks,known_pairs,tool,preset,threads,*,reference_bases,skip_self):
    scopes=CompletedNativeScopes(root,catalog,index,tasks,tool,preset)
    seen={task['task_id'] for task in tasks}
    cache_misses=0
    for request in scopes.missing_seed_requests(query_ids,target_ids):
        consumed = False
        def consume_seed(seed,hits):
            nonlocal consumed
            if seed['task_id'] in seen:raise Q0EvidenceError('unroutable seed made no matrix progress')
            seen.add(seed['task_id']);tasks.append(seed);scopes.add_complete_tasks([seed])
            add_pairwise_candidates(catalog,observe_part_hits(catalog,hits,known_pairs),set(seed['query_ids']),set(seed['target_ids']),
                                    include_placed=True,known_pairs=known_pairs)
            consumed = True
        seed=_unroutable_seed(root,catalog,request,tool,preset,threads,reference_bases=reference_bases,
                             skip_self=skip_self,on_cache_hit=consume_seed)
        if seed is None:
            cache_misses+=1
            continue  # Other cohorts may have verified evidence; this one remains unsearched.
        if not consumed:
            hits=read_paf(artifact_path(root, seed['paf']),query_lengths={key:catalog.parts[key].interval.length for key in seed['query_ids']},
                          target_lengths={key:catalog.parts[key].interval.length for key in seed['target_ids']},artifact=seed['paf'])
            consume_seed(seed,hits)
        print(f"LGZ q0 weak seed: completed={seed['task_id']} approximate={seed['task_id'] in scopes.approximate_scope_task_ids} "
              f"queries={len(seed['query_ids'])} targets={len(seed['target_ids'])}",flush=True)
    if cache_misses:
        print(f"LGZ q0 unroutable seed: direct_cache_misses={cache_misses}; missing relationships remain unsearched",flush=True)
    return scopes

def _readless_package(root):
    rows = table(root, "metadata/package.tsv", ("reads_qc_enabled",))
    if len(rows) != 1 or rows[0]["reads_qc_enabled"] != "false":
        raise Q0EvidenceError("q0 proof repair requires a package without reads QC; use full supplemental evidence")


class _ProofRepairInputs:
    """Reuse base validation only within one repair call and one file generation.

    Do not keep a second copy of whole-assembly DNA alive while the selector
    loads its evidence. Later passes reread source FASTAs but not the reference
    FASTA, partition FASTAs, initial PAF parser, or initial checkpoint checks.
    """

    def __init__(self, root):
        self.root = root
        self.base = None

    def _signatures(self):
        return tuple(file_signature(workspace_artifact_path(self.root, path)) for path in self.paths)

    def verify(self):
        if self._signatures() != self.signatures:
            raise Q0EvidenceError("q0 proof repair initial files changed between passes")

    def _read_initial(self):
        return _initial_inputs(self.root)

    def read(self):
        if self.base is None:
            sources, lengths, assignments, options, paths, alignments, known = self._read_initial()
            self.paths = sorted(set(paths) | {"metadata/package.tsv"})
            self.signatures = self._signatures()
            self.identities = [identity(self.root, path) for path in self.paths]
            self.datasets = table(self.root, "metadata/datasets.tsv", ("dataset_name", "fasta_relpath"))
            if ("metadata/datasets.tsv" not in self.paths
                    or any(row["fasta_relpath"] not in self.paths for row in self.datasets)):
                raise Q0EvidenceError("q0 proof repair dataset list is not bound to initial inputs")
            self.source_lengths = {key: len(seq) for key, seq in sources.items()}
            self.base = lengths, assignments, options, alignments, known
        else:
            self.verify()
            sources = _dataset_sequences(self.root, self.datasets)
            if {key: len(seq) for key, seq in sources.items()} != self.source_lengths:
                raise Q0EvidenceError("q0 proof repair source inventory changed between passes")
        self.verify()
        lengths, assignments, options, alignments, known = self.base
        observations = known.fork() if isinstance(known, ObservedSourcePairs) else set(known)
        return sources, lengths, assignments, options, self.paths, alignments, observations, self.identities



def _scope_file(layout: WorkspaceLayout, relative: str):
    path = layout.path(relative)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"not a regular Q0 scope input: {relative}")
    return path, info.st_size


def _scope_index(layout: WorkspaceLayout, relative: str):
    path, _ = _scope_file(layout, relative)
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            fields = line.split("\t", 2)
            if len(fields) < 2 or not fields[0] or any(c.isspace() for c in fields[0]):
                raise ValueError("invalid Q0 FASTA index record")
            length = int(fields[1])
            if length < 1:
                raise ValueError("invalid Q0 FASTA index length")
            yield fields[0], length


def _scope_paf_inventory(layout, chromosomes, datasets):
    """Count only declared base evidence; no workspace walk or PAF content reads."""
    if any(not isinstance(n, str) or not n or "/" in n or "\\" in n or n in {".", ".."}
           for n in (*chromosomes, *datasets)):
        raise ValueError("invalid Q0 inventory name")
    paf_bytes = sum(_scope_file(layout, f"runs/{name}_vs_ref/result.paf")[1] for name in datasets)
    matrix_count = 0
    for chromosome in chromosomes:
        path, _ = _scope_file(layout, f"runs/chr_{chromosome}/q0_alignment_inputs.json")
        descriptor = json_file(path)
        rows = descriptor.get("alignments")
        if (descriptor.get("version") != 1 or descriptor.get("chromosome") != chromosome
                or not isinstance(rows, list)):
            raise ValueError("invalid Q0 scope descriptor")
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("invalid Q0 scope pair")
            left, right = row.get("target_dataset"), row.get("query_dataset")
            if not isinstance(left, str) or not isinstance(right, str) or left not in datasets or right not in datasets:
                raise ValueError("unknown Q0 scope dataset")
            expected = _matrix_paf(chromosome, left, right)
            if expected in seen or layout.relative(row["paf"]) != layout.relative(expected):
                raise ValueError("duplicate or misdirected Q0 scope PAF")
            seen.add(expected)
            paf_bytes += _scope_file(layout, expected)[1]
        matrix_count += len(seen)
    return paf_bytes, matrix_count


def _automatic_scope_decision(root: Path) -> ScopeDecision:
    """Decide before the expensive initial PAF scan; unknown metadata is full."""
    try:
        reference_rows = table(root, "metadata/reference.tsv", ("fasta_relpath", "fai_relpath"))
        dataset_rows = table(root, "metadata/datasets.tsv", ("dataset_name", "fasta_relpath", "fai_relpath"))
        package_rows = table(root, "metadata/package.tsv", ("reads_qc_enabled",))
        option_rows = table(root, "metadata/prepare_options.tsv", ("key", "value"))
        if len(reference_rows) != 1 or len(package_rows) != 1:
            raise ValueError("automatic Q0 scope metadata is incomplete")
        layout = WorkspaceLayout.detect(root)
        refs = {}
        for name, length in _scope_index(layout, reference_rows[0]["fai_relpath"]):
            if name in refs:
                raise ValueError("duplicate Q0 reference record")
            refs[name] = length
        datasets = {row["dataset_name"] for row in dataset_rows}
        if not refs or not datasets or len(datasets) != len(dataset_rows):
            raise ValueError("incomplete Q0 source inventory")
        source_count = source_bp = longest_source_bp = 0
        for row in dataset_rows:
            before = source_count
            for _, length in _scope_index(layout, row["fai_relpath"]):
                source_count += 1
                source_bp += length
                longest_source_bp = max(longest_source_bp, length)
            if source_count == before:
                raise ValueError("empty Q0 source index")
        reference_bp = sum(refs.values())
        options = {row["key"]: row["value"] for row in option_rows}
        preset = options.get("minimap_preset", "asm10")
        reads_value = package_rows[0]["reads_qc_enabled"]
        reads_qc_enabled = {"true": True, "false": False}.get(reads_value)
        paf_bytes, base_alignment_count = _scope_paf_inventory(layout, refs, datasets)
        workload = ScopeWorkload(
            regional_enabled=(preset == REGIONAL_POLICY["preset"]
                              and reference_bp >= REGIONAL_POLICY["reference_bases_at_least"]),
            reads_qc_enabled=reads_qc_enabled,
            reference_bp=reference_bp,
            source_bp=source_bp,
            longest_source_bp=longest_source_bp,
            source_count=source_count,
            paf_bytes=paf_bytes,
            base_alignment_count=base_alignment_count,
        )
    except (OSError, UnicodeError, ValueError, Q0EvidenceError, KeyError):
        workload = ScopeWorkload(False, None, 0, 0, 0, 0, 0, 0)
        return ScopeDecision(AUTO_SCOPE, FULL_SCOPE, "automatic_metadata_unavailable", (),
                             workload, AutoScopePolicy())
    return decide_scope(workload)


def prepare_evidence(root: Path, *, threads: int = 1, minimap2: str = "minimap2",
                     supplement_scope: str = FULL_SCOPE) -> dict:
    root = root.resolve()
    if supplement_scope == AUTO_SCOPE:
        decision = _automatic_scope_decision(root)
        if decision.effective_scope == PROOF_REPAIR_SCOPE:
            return _prepare_with_proof_repair(root, threads=threads, minimap2=minimap2,
                                              requested_scope=AUTO_SCOPE, scope_decision=decision)
        supplement_scope = decision.effective_scope
        requested_scope = AUTO_SCOPE
        scope_decision = decision
    else:
        requested_scope = supplement_scope
        scope_decision = None
    if supplement_scope == "positive_threshold":
        from .q0_threshold_prepare import prepare
        return prepare(root, threads, minimap2)
    if supplement_scope == PROOF_REPAIR_SCOPE:
        return _prepare_with_proof_repair(root, threads=threads, minimap2=minimap2,
                                          requested_scope=requested_scope, scope_decision=scope_decision)
    manifest, _, _ = _prepare_evidence_pass(root, threads=threads, minimap2=minimap2,
                                            supplement_scope=supplement_scope,
                                            requested_scope=requested_scope,
                                            scope_decision=scope_decision)
    return manifest


def _prepare_evidence_pass(root: Path, *, threads, minimap2, supplement_scope,
                           requested_scope=None, scope_decision=None,
                           draft=False, frontier_override=None, repair_round=0, fallback_reason=None,
                           expected_input=None, repair_inputs=None):
    root = root.resolve()
    if threads < 1:
        raise Q0EvidenceError("q0 evidence threads must be positive")
    requested_scope = supplement_scope if requested_scope is None else requested_scope
    # Reject explicit developer/test overrides before touching workspace inputs.
    if supplement_scope == AUTO_SCOPE:
        raise Q0EvidenceError("automatic Q0 scope must be resolved before the evidence pass")
    run_policy = supplement_policy(supplement_scope)
    builder = builder_identity()
    if repair_inputs is None:
        sources, lengths, assignments, options, input_paths, base_alignments, known_pairs = _initial_inputs(root)
        inputs = [identity(root, relative) for relative in input_paths]
    else:
        sources, lengths, assignments, options, input_paths, base_alignments, known_pairs, inputs = repair_inputs.read()
    if "q0_supplement_scope" in options:
        raise Q0EvidenceError("set experimental q0 scope on the evidence command, not prepare_options.tsv")
    if supplement_scope == PROOF_REPAIR_SCOPE:
        _readless_package(root)
    tool = executable_identity(minimap2)
    request_identity = _request_identity(inputs, tool, run_policy, builder,
                                         scope_decision.record() if scope_decision else None)
    if expected_input is not None and expected_input != request_identity:
        raise Q0EvidenceError("q0 proof repair input identity changed between passes")
    if expected_input is None and workspace_artifact_path(root, MANIFEST).is_file():
        try:
            previous = load_verified_evidence(root)
            if previous.get("input_fingerprint") == request_identity:
                print("LGZ q0 evidence cache hit: " + request_identity)
                return previous, None, True
        except Q0EvidenceError:
            pass
    use_regional = regional_enabled(lengths, options.get("minimap_preset", "asm10"))
    reference_pafs = {f"runs/{key.dataset}_vs_ref/result.paf" for key in sources}
    reference_inputs = [row for row in inputs if row["path"] in reference_pafs]
    with (LocalReferenceCache(root, reference_inputs) if use_regional else nullcontext(None)) as cache:
        catalog = build_catalog(root, sources, lengths, assignments, min_gap=POLICY["min_gap"],
                                regional_factory=cache.factory if cache else None)
        if cache: cache.publish()
        from .q0_frontier_scope import UnsearchedWindows
        regional_frontier = None
        unsearched = UnsearchedWindows() if supplement_scope != FULL_SCOPE else None
        scope_report = None
        if requested_scope == AUTO_SCOPE:
            if scope_decision is None:
                raise Q0EvidenceError("automatic Q0 scope lacks its decision record")
            scope_report = {"requested": AUTO_SCOPE, "effective": FULL_SCOPE,
                            "decision": scope_decision.record(),
                            "unsearched_part_intervals": []}
        elif supplement_scope != FULL_SCOPE:
            scope_report = {"requested": supplement_scope, "effective": FULL_SCOPE}
        if supplement_scope == PROOF_REPAIR_SCOPE:
            if scope_report is None:
                scope_report = {"requested": supplement_scope, "effective": FULL_SCOPE}
            scope_report["proof_repair_rounds"] = repair_round
        if unsearched is not None:
            if fallback_reason is not None:
                scope_report["reason"] = fallback_reason
            elif not cache:
                scope_report["reason"] = "regional_route_disabled"
            else:
                regional_frontier = (frontier_override if frontier_override is not None else
                                     _provisional_frontier(root, sources, lengths, catalog, base_alignments))
                if regional_frontier is not None:
                    if scope_report is None:
                        scope_report = {"requested": supplement_scope, "effective": FULL_SCOPE}
                    scope_report["effective"] = "decision_frontier"
                    scope_report["frontier_sources"] = len(regional_frontier)
                    scope_report["frontier_bp"] = sum(i.length for rows in regional_frontier.values() for i in rows)
                else:
                    scope_report["reason"] = "provisional_q0_has_no_path"
        if supplement_scope == "positive_threshold":
            if not draft or repair_inputs is None: raise Q0EvidenceError("threshold generation requires a bound private pass")
            from .q0_threshold_acceptance import SEMANTICS, record
            scope_report.update(acceptance=SEMANTICS, threshold_request=record(regional_frontier))
        if scope_report is not None:
            catalog.payload["supplement_scope"] = scope_report
        from .q0_native_frontier import CACHE_ONLY, RegionalFallbackCache, prefer_cached_whole
        bounded_native = supplement_scope == 'positive_threshold' and bool(regional_frontier)
        native_gate = RegionalFallbackCache(bounded=bounded_native)
        if bounded_native:
            scope_report['native_fallback_policy'] = CACHE_ONLY

        def native_fallbacks(phase, requests):
            def probe(request):
                return _supplement(root,catalog,request,tool,options.get('minimap_preset','asm10'),threads,
                                   skip_self=options.get('skip_self')=='true',cache_only=True)
            return native_gate.dispatch(phase,requests,probe)
        tasks = []
        # Each productive round adds at least one segment to the anchor set. The
        # monotone loop terminates after at most the number of source segments.
        remaining = catalog.unplaced()
        anchors = sorted(set(catalog.parts) - set(remaining))
        while remaining and anchors:
            request = {"kind": "unplaced_discovery", "round": len(catalog.payload["discovery_rounds"]) + 1,
                       "query_ids": remaining, "target_ids": anchors}
            consumed = False; added = None
            def consume_unplaced(task,hits):
                nonlocal consumed, added
                tasks.append(task)
                added = add_pairwise_candidates(catalog, observe_part_hits(catalog,hits,known_pairs),
                    set(task['query_ids']),set(task['target_ids']),known_pairs=known_pairs)
                consumed = True
            task = _supplement(root, catalog, request, tool, options.get("minimap_preset", "asm10"), threads,
                               skip_self=options.get("skip_self") == "true",on_cache_hit=consume_unplaced)
            if not consumed:
                hits = read_paf(artifact_path(root, task['paf']),query_lengths={key:catalog.parts[key].interval.length for key in task['query_ids']},
                                target_lengths={key:catalog.parts[key].interval.length for key in task['target_ids']},artifact=task['paf'])
                consume_unplaced(task,hits)
            catalog.payload["discovery_rounds"].append({"task_id": task["task_id"], "added_segment_ids": sorted(added)})
            if not added:
                break
            remaining, anchors = catalog.unplaced(), sorted(added)
        request = partial_source_request(catalog, minimum_uncovered_bp=POLICY["partial_source_discovery_min_uncovered_bp"])
        partial_tasks = []; partial_consumed = False
        if request:
            preset = options.get("minimap_preset", "asm10")
            # A complete original whole-source mapping has priority, even if it
            # finished while an optimized revision was being staged.
            def consume_native_partial(task,hits):
                nonlocal partial_consumed
                # A complete whole-native cache is this phase's ONLY task.
                # Regional windows retain their one aggregate discovery round.
                partial_tasks.append(task);tasks.append(task)
                add_pairwise_candidates(catalog,observe_part_hits(catalog,hits,known_pairs),
                    set(task['query_ids']),set(task['target_ids']),include_placed=True,known_pairs=known_pairs)
                partial_consumed = True
            task = _supplement(root, catalog, request, tool, preset, threads,
                               skip_self=options.get("skip_self") == "true", cache_only=bool(cache),on_cache_hit=consume_native_partial)
            if task is not None:
                if not partial_consumed:partial_tasks.append(task)
            else:
                # Unroutable reference-bearing sources are small queries, not
                # reasons to remap every large parent against them separately.
                # Seed before partial discovery, so that phase also reuses the
                # complete matrix (including negative results) without repeats.
                reference_ids = sorted({row["segment_id"] for row in catalog.payload["candidates"] if row["placement_kind"] == "reference"})
                weak_queries = sorted(set(reference_ids)-catalog.reference_routable_parts)
                from .q0_reference_index import ReferenceIndex
                with closing(ReferenceIndex.open(cache.path, root, catalog.parts, lengths, local_paf_directory=cache.paf_directory)) as index:
                    if weak_queries:
                        _complete_unroutable_seeds(root,catalog,index,weak_queries,reference_ids,tasks,known_pairs,tool,preset,threads,
                            reference_bases=sum(lengths.values()),skip_self=options.get('skip_self')=='true')
                    regional_tasks, fallback_ids, report = prepare_partial(
                        root, catalog, index, known_pairs, tool, reference_lengths=lengths,
                        preset=preset, threads=threads, skip_self=options.get("skip_self") == "true",
                        complete_tasks=tasks,required_target_ids=request["target_ids"],
                        regional_frontier=regional_frontier, unsearched=unsearched)
                partial_tasks.extend(regional_tasks)
                catalog.payload["regional_partial_discovery"] = report
                if fallback_ids:
                    fallback_request = {**request, "query_ids": fallback_ids}
                    whole = native_fallbacks('regional_partial_discovery',[fallback_request])
                    partial_tasks = prefer_cached_whole(partial_tasks,whole,report)
            if not partial_consumed:tasks.extend(partial_tasks)
            # One discovery round, not one full catalog rebuild per window.
            # Keep each PAF's own declared geometry/artifact while accumulating
            # candidates against the same anchor snapshot as the native round.
            def partial_hits():
                for task in partial_tasks:
                    yield from read_paf(artifact_path(root, task["paf"]),
                        query_lengths={key: catalog.parts[key].interval.length for key in task["query_ids"]},
                        target_lengths={key: catalog.parts[key].interval.length for key in task["target_ids"]}, artifact=task["paf"])
            if partial_tasks and not partial_consumed:
                add_pairwise_candidates(catalog, observe_part_hits(catalog, partial_hits(), known_pairs),
                    {key for task in partial_tasks for key in task["query_ids"]},
                    {key for task in partial_tasks for key in task["target_ids"]},
                    include_placed=True, known_pairs=known_pairs)
        candidate_requests = supplemental_groups(catalog, assignments, known_pairs)
        pending_candidates = []
        for request in candidate_requests:
            task = _supplement(root, catalog, request, tool, options.get("minimap_preset", "asm10"), threads,
                               skip_self=options.get("skip_self") == "true", cache_only=bool(cache))
            if task is not None: tasks.append(task)
            else: pending_candidates.append(request)
        if pending_candidates:
            from .q0_reference_index import ReferenceIndex
            with closing(ReferenceIndex.open(cache.path, root, catalog.parts, lengths, local_paf_directory=cache.paf_directory)) as index:
                preset = options.get("minimap_preset", "asm10")
                planner = CandidatePlan(root,catalog,index,pending_candidates,known_pairs,tasks,tool,preset)
                seed_ids = []; seed_misses = 0
                for seed_request in planner.unroutable_seed_requests():
                    seed = _unroutable_seed(root,catalog,seed_request,tool,preset,threads,
                        reference_bases=sum(lengths.values()),skip_self=options.get("skip_self") == "true")
                    if seed is None:
                        seed_misses += 1
                        continue
                    tasks.append(seed);seed_ids.append(seed["task_id"]);planner.add_complete_tasks([seed])
                regional_tasks, native_requests, report = prepare_candidates(
                    root,catalog,index,pending_candidates,known_pairs,tasks,tool,reference_lengths=lengths,
                    preset=preset,threads=threads,skip_self=options.get("skip_self") == "true",planner=planner,
                    regional_frontier=regional_frontier, unsearched=unsearched)
                report["unroutable_seed_task_ids"] = seed_ids
                if seed_misses:
                    print(f"LGZ q0 candidate seed: direct_cache_misses={seed_misses}; missing relationships remain unsearched",flush=True)
            catalog.payload["regional_candidate_discovery"] = report
            if native_requests:
                whole = native_fallbacks('regional_candidate_discovery',native_requests)
                regional_tasks = prefer_cached_whole(regional_tasks,whole,report)
            tasks.extend(regional_tasks)
        if bounded_native:
            if native_gate.omissions:
                scope_report['deferred_native_matrices'] = native_gate.omissions
            for phase, matrix_ids in native_gate.planned.items():
                catalog.payload[phase]['native_fallback_matrix_ids'] = matrix_ids
        if _partition_sha256(Path(tool["resolved"])) != tool["sha256"]:
            raise Q0EvidenceError("q0 supplementary aligner changed during preparation")
        if repair_inputs is not None:
            repair_inputs.verify()
        if inputs != [identity(root, relative) for relative in input_paths]:
            raise Q0EvidenceError("q0 evidence inputs changed during preparation; no manifest published")
        if builder_identity() != builder:
            raise Q0EvidenceError("q0 evidence builder changed during preparation; no manifest published")
        if supplement_policy(supplement_scope) != run_policy:
            raise Q0EvidenceError("q0 supplement scope changed during preparation; no manifest published")
        if unsearched is not None:
            if scope_report is None:
                raise Q0EvidenceError("q0 scoped preparation lacks a scope report")
            scope_report["unsearched_part_intervals"] = unsearched.record()
        payload = catalog.finish()
        payload["base_alignments"] = base_alignments
        payload["supplementary_alignments"] = tasks
        catalog_name = f"grt/evidence/q0_prepare/{stable_id('catalog', payload)}.json"
        atomic_write_json(workspace_artifact_path(root, catalog_name), payload)
        output_paths = {catalog_name}
        for task in tasks:
            output_paths.add(task["receipt"])
            output_paths.update(row["path"] for row in json_file(artifact_path(root, task["receipt"]))["outputs"])
        outputs = [identity(root, relative) for relative in sorted(output_paths)]
        output_identities = {row["path"]: row for row in outputs}
        # A long later phase must not publish success if any reused earlier
        # output changed after its validation. Reuse the final hashes above.
        for task in tasks:
            if any(output_identities.get(row["path"]) != row for row in json_file(artifact_path(root, task["receipt"]))["outputs"]):
                raise Q0EvidenceError("completed supplementary output changed before publication")
        manifest = {"schema": SCHEMA, "status": "success", "policy": run_policy, "builder": builder,
                    "input_fingerprint": request_identity, "inputs": inputs,
                    "outputs": outputs,
                    "catalog": catalog_name, "tool": tool}
        if not draft:
            atomic_write_json(workspace_artifact_path(root, MANIFEST), manifest)
        action = "draft prepared" if draft else "prepared"
        print(f"LGZ q0 evidence {action}: candidates={len(payload['candidates'])} "
              f"supplementary_tasks={len(tasks)} unplaced_segments={len(payload['unplaced_segment_ids'])}")
        return manifest, regional_frontier, False


def _prepare_with_proof_repair(root, *, threads, minimap2, requested_scope=PROOF_REPAIR_SCOPE, scope_decision=None):
    from .q0_admission import load_evidence_input, select_q0_paths
    from .q0_frontier_scope import UnsearchedQ0Context, audit_selected_scope, selected_proof_frontier
    from .q0_sources import merged_intervals

    _readless_package(root)
    repair_inputs = _ProofRepairInputs(root)
    expected_input, frontier = None, None
    fallback_reason = None
    for iteration in range(MAX_PROOF_REPAIRS + 2):
        manifest, planned, cached = _prepare_evidence_pass(
            root, threads=threads, minimap2=minimap2, supplement_scope=PROOF_REPAIR_SCOPE,
            requested_scope=requested_scope, scope_decision=scope_decision,
            draft=True, expected_input=expected_input, frontier_override=frontier,
            repair_round=min(iteration, MAX_PROOF_REPAIRS), fallback_reason=fallback_reason, repair_inputs=repair_inputs)
        if cached:
            return manifest
        expected_input = manifest["input_fingerprint"]
        paths = tuple(workspace_artifact_path(root, row["path"]) for key in ("inputs", "outputs") for row in manifest[key])
        paths += (Path(manifest["tool"]["resolved"]),)
        before = tuple(file_signature(path) for path in paths)
        if planned is None:
            # No omissions (e.g. native routing or bounded repair exhausted).
            load_verified_evidence(root, _draft=manifest)
            break
        data = load_evidence_input(root, _draft=manifest)
        selection = select_q0_paths(data)
        if not any(row.path is not None for row in selection.paths.values()):
            fallback_reason = "scoped_q0_has_no_path"
        else:
            try:
                audit_selected_scope(data, selection.admission, selection.paths)
            except UnsearchedQ0Context:
                proof = selected_proof_frontier(data, selection.admission, selection.paths)
                frontier = {source: merged_intervals((*planned.get(source, ()), *proof.get(source, ())))
                            for source in planned.keys() | proof.keys()}
                if frontier == planned:
                    raise Q0EvidenceError("q0 proof repair found omissions inside an already requested frontier")
                if iteration >= MAX_PROOF_REPAIRS:
                    fallback_reason = "proof_repair_budget_exhausted"
            else:
                break
        action = fallback_reason or "expand_selected_proof_frontier"
        print(f"LGZ q0 proof repair: pass={iteration} next={action}", flush=True)
        del data, selection
    else:
        raise Q0EvidenceError("q0 proof repair produced no publishable evidence")
    # The verified inputs may not drift while selecting (even if bytes are
    # later restored). Keep this fence process-local, never as a cache receipt.
    if (manifest["builder"] != builder_identity()
            or manifest["policy"] != supplement_policy(PROOF_REPAIR_SCOPE)
            or _partition_sha256(paths[-1]) != manifest["tool"]["sha256"]
            or before != tuple(file_signature(path) for path in paths)):
        raise Q0EvidenceError("q0 proof repair evidence changed during selection; no manifest published")
    atomic_write_json(workspace_artifact_path(root, MANIFEST), manifest)
    print("LGZ q0 evidence proof repair: verified ready published", flush=True)
    return manifest
