"""Prepare and content-bind alignment evidence for the new q0 path builder.

Raw chr-local alignments are reused; only missing fragment relationships are
mapped here. A ready manifest is published atomically after every task succeeds.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import nullcontext, closing
import csv
import json
from pathlib import Path
import subprocess
from typing import Iterable

from .common import canonical_json, executable_identity, read_fasta, sha256_file, stable_id, write_fasta
from .q0_alignments import read_paf
from .q0_catalog import (CATALOG_SCHEMA, CandidateCatalog, DISCOVERY_REFERENCE_IDENTITY, DISCOVERY_REFERENCE_MAPQ,
                         add_pairwise_candidates, build_catalog, partial_source_request, supplemental_groups, ObservedSourcePairs)
from .q0_regional_discovery import REGIONAL_POLICY, LocalReferenceCache, enabled as regional_enabled, observe_part_hits, prepare_partial
from .q0_sources import Q0EvidenceError, SourceKey
try:
    from run_orchestration import atomic_write_json, sha256_file as _partition_sha256
except ModuleNotFoundError:
    from ..run_orchestration import atomic_write_json, sha256_file as _partition_sha256

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
MAPPING_OUTPUT_FILES = ("query.fa", "target.fa", "result.paf", "command.json")
POLICY = {"version": 3, "regional_partial_discovery": REGIONAL_POLICY, "min_gap": 100, "discovery": "unplaced_to_new_anchors_until_fixed_point",
          "supplement": "out_of_group_split_and_missing_ref_neighbors",
          "partial_source_discovery_min_uncovered_bp": 100,
          "partial_source_reference_identity": DISCOVERY_REFERENCE_IDENTITY,
          "partial_source_reference_mapq": DISCOVERY_REFERENCE_MAPQ,
          "supplement_flags": ["-D", "-P", "--dual=yes", "--no-long-join"]}


def artifact_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise Q0EvidenceError(f"invalid q0 artifact path: {relative!r}")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise Q0EvidenceError(f"q0 artifact escapes workspace: {relative}") from exc
    return resolved


def identity(root: Path, relative: str) -> dict:
    path = artifact_path(root, relative)
    if not path.is_file():
        raise Q0EvidenceError(f"required q0 artifact missing: {relative}")
    return {"path": relative, "sha256": sha256_file(path), "size": path.stat().st_size}


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
            "q0_preparation.py", "q0_catalog.py", "q0_sources.py", "q0_alignments.py", "common.py",
            "q0_query_windows.py", "q0_reference_index.py", "q0_regional_mapping.py",
            "q0_cigar_policy.py", "q0_mapper_guard.py", "q0_regional_discovery.py")])


def load_verified_evidence(root: Path) -> dict:
    """No fallback: consumers must reject missing, stale, or damaged evidence."""
    root = root.resolve()
    manifest = json_file(root / MANIFEST)
    if (manifest.get("schema") != SCHEMA or manifest.get("status") != "success"
            or manifest.get("policy") != POLICY or manifest.get("builder") != builder_identity()):
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
    expected_input = stable_id("q0-evidence-input", {"inputs": manifest["inputs"],
                               "tool": manifest.get("tool"), "policy": POLICY, "builder": manifest["builder"]})
    if manifest.get("input_fingerprint") != expected_input:
        raise Q0EvidenceError("q0 evidence input fingerprint is inconsistent")
    outputs = {row["path"]: row for row in manifest["outputs"]}
    if manifest.get("catalog") not in outputs:
        raise Q0EvidenceError("q0 candidate catalog is not bound to its manifest")
    catalog = json_file(artifact_path(root, manifest["catalog"]))
    if catalog.get("schema") != CATALOG_SCHEMA:
        raise Q0EvidenceError("unsupported q0 candidate catalog")
    expected_outputs = {manifest["catalog"]}
    inputs = {row["path"] for row in manifest["inputs"]}
    try:
        for row in catalog["base_alignments"]:
            if not {row["query_fasta"], row["target_fasta"], row["paf"]} <= inputs:
                raise Q0EvidenceError("q0 base alignment is not bound to its inputs")
        regional_members = None
        for task in catalog["supplementary_alignments"]:
            if task.get("kind") == "regional_discovery":
                from .q0_regional_mapping import verify_regional_task
                if regional_members is None:
                    regional_members = {row["segment_id"]: (row["interval"]["end"]-row["interval"]["start"], row["sequence_sha256"])
                                        for row in catalog["segments"]}
                receipt = verify_regional_task(root, task, members=regional_members)
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
        if any(row["artifact"] not in inputs | set(outputs) for row in catalog["evidence"].values()):
            raise Q0EvidenceError("q0 candidate references an unbound alignment artifact")
    except (KeyError, TypeError) as exc:
        raise Q0EvidenceError(f"invalid q0 evidence dependency inventory: {exc}") from exc
    return manifest


def _initial_inputs(root: Path):
    datasets = table(root, "metadata/datasets.tsv", ("dataset_name", "fasta_relpath"))
    references = table(root, "metadata/reference.tsv", ("fasta_relpath",))
    assignments = table(root, "metadata/chr_assignments.tsv", ("dataset_name", "seq_name", "assigned_chr_name"))
    options = {row["key"]: row["value"] for row in table(root, "metadata/prepare_options.tsv", ("key", "value"))}
    if len(references) != 1 or not datasets:
        raise Q0EvidenceError("q0 requires one reference and at least one dataset")
    names = [row["dataset_name"] for row in datasets]
    if len(names) != len(set(names)):
        raise Q0EvidenceError("q0 dataset names must be unique")
    refs = dict(read_fasta(artifact_path(root, references[0]["fasta_relpath"])))
    sources = {}
    paths = {"metadata/datasets.tsv", "metadata/reference.tsv", "metadata/chr_assignments.tsv",
             "metadata/prepare_options.tsv", "metadata/track_member_orders.tsv",
             references[0]["fasta_relpath"]}
    for dataset in datasets:
        paths.add(dataset["fasta_relpath"])
        for name, sequence in read_fasta(artifact_path(root, dataset["fasta_relpath"])):
            key = SourceKey(dataset["dataset_name"], name)
            if key in sources:
                raise Q0EvidenceError(f"duplicate q0 source: {key}")
            sources[key] = sequence
        relative = f"runs/{dataset['dataset_name']}_vs_ref/result.paf"
        paths.update((relative, f"runs/{dataset['dataset_name']}_vs_ref/tool_version.txt"))
    lengths = {name: len(sequence) for name, sequence in refs.items()}
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
            stem = f"{left}_vs_self" if left == right else f"{left}_vs_{right}"
            if row["paf"] != f"runs/chr_{chromosome}/{stem}/result.paf":
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
                    validated_partitions[validation_key] = digest
                paths.add(row[field])
            qlengths = {name: len(sources[SourceKey(right, name)]) for name in group[right]}
            tlengths = {name: len(sources[SourceKey(left, name)]) for name in group[left]}
            for hit in read_paf(artifact_path(root, row["paf"]), query_lengths=qlengths,
                                target_lengths=tlengths, artifact=row["paf"]):
                if isinstance(known_pairs, ObservedSourcePairs):
                    known_pairs.observe_alignment(hit, SourceKey(right, hit.query_name), SourceKey(left, hit.target_name))
                elif any(hit.aligned_blocks()):
                    known_pairs.add(tuple(sorted((SourceKey(right, hit.query_name),
                                                  SourceKey(left, hit.target_name)))))
            paths.add(row["paf"])
            base_alignments.append({**row, "chromosome": chromosome})
        if actual != expected:
            raise Q0EvidenceError(f"missing required q0 pairs for {chromosome}: {sorted(expected - actual)}")
    return sources, lengths, assignments, options, sorted(paths), sorted(base_alignments, key=lambda row: row["paf"]), known_pairs


def _supplement(root: Path, catalog: CandidateCatalog, request: dict, tool: dict,
                preset: str, threads: int, *, skip_self: bool = False, cache_only: bool = False) -> dict | None:
    if sha256_file(Path(tool["resolved"])) != tool["sha256"]:
        raise Q0EvidenceError("q0 supplementary aligner changed during preparation")
    query_ids, target_ids = sorted(set(request["query_ids"])), sorted(set(request["target_ids"]))
    if skip_self:
        targets_by_dataset = defaultdict(set)
        for key in target_ids:
            targets_by_dataset[catalog.parts[key].source.dataset].add(key)
        if any(targets_by_dataset[catalog.parts[key].source.dataset] - {key} for key in query_ids):
            raise Q0EvidenceError("--skip-self conflicts with required q0 supplementary same-dataset comparisons")
    members = [[key, catalog.parts[key].sequence_sha256] for key in sorted(set(query_ids + target_ids))]
    # Raw mapping identity is independent of candidate-selection code and the
    # discovery round that requested it. Revalidate cached geometry, do not rerun
    # an unchanged mapper/input pair just because the q0 builder was updated.
    spec = {"schema": "lgz_q0_mapping_v1", "query_ids": query_ids, "target_ids": target_ids,
            "members": members, "tool": tool, "preset": preset,
            "alignment_flags": POLICY["supplement_flags"]}
    task_id = stable_id("q0-map", spec)
    relative = f"grt/evidence/q0_prepare/tasks/{task_id}"
    directory = root / relative
    cache = directory / "success.json"
    output = directory / "result.paf"
    required_outputs = {f"{relative}/{name}" for name in MAPPING_OUTPUT_FILES}
    if cache.is_file():
        try:
            expected = json_file(cache)
            if (expected.get("spec") == spec and expected.get("status") == "success"
                    and {row["path"] for row in expected["outputs"]} == required_outputs
                    and all(identity(root, row["path"]) == row for row in expected["outputs"])):
                for _hit in read_paf(output, query_lengths={key: catalog.parts[key].interval.length for key in query_ids},
                                     target_lengths={key: catalog.parts[key].interval.length for key in target_ids}):
                    pass
                return {"task_id": task_id, "kind": request["kind"], "request": request,
                        "paf": f"{relative}/result.paf", "receipt": f"{relative}/success.json",
                        "query_ids": query_ids, "target_ids": target_ids}
        except (Q0EvidenceError, KeyError, TypeError):
            pass
    if cache_only:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    query, target = directory / "query.fa", directory / "target.fa"
    write_fasta(query, ((key, catalog.sequence(key)) for key in query_ids))
    write_fasta(target, ((key, catalog.sequence(key)) for key in target_ids))
    temporary = directory / "result.paf.tmp"
    command = [tool["resolved"], "-c", "-x", preset, *POLICY["supplement_flags"], "-t", str(threads),
               "-o", str(temporary), str(target), str(query)]
    atomic_write_json(directory / "command.json", {"argv": command, "spec": spec})
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


def prepare_evidence(root: Path, *, threads: int = 1, minimap2: str = "minimap2") -> dict:
    root = root.resolve()
    if threads < 1:
        raise Q0EvidenceError("q0 evidence threads must be positive")
    builder = builder_identity()
    sources, lengths, assignments, options, input_paths, base_alignments, known_pairs = _initial_inputs(root)
    inputs = [identity(root, relative) for relative in input_paths]
    tool = executable_identity(minimap2)
    request_identity = stable_id("q0-evidence-input", {"inputs": inputs, "tool": tool,
                                "policy": POLICY, "builder": builder})
    if (root / MANIFEST).is_file():
        try:
            previous = load_verified_evidence(root)
            if previous.get("input_fingerprint") == request_identity:
                print("LGZ q0 evidence cache hit: " + request_identity)
                return previous
        except Q0EvidenceError:
            pass
    use_regional = regional_enabled(lengths, options.get("minimap_preset", "asm10"))
    reference_pafs = {f"runs/{key.dataset}_vs_ref/result.paf" for key in sources}
    reference_inputs = [row for row in inputs if row["path"] in reference_pafs]
    with (LocalReferenceCache(root, reference_inputs) if use_regional else nullcontext(None)) as cache:
        catalog = build_catalog(root, sources, lengths, assignments, min_gap=POLICY["min_gap"],
                                regional_factory=cache.factory if cache else None)
        if cache: cache.publish()
        tasks = []
        # Each productive round adds at least one segment to the anchor set. The
        # monotone loop terminates after at most the number of source segments.
        remaining = catalog.unplaced()
        anchors = sorted(set(catalog.parts) - set(remaining))
        while remaining and anchors:
            request = {"kind": "unplaced_discovery", "round": len(catalog.payload["discovery_rounds"]) + 1,
                       "query_ids": remaining, "target_ids": anchors}
            task = _supplement(root, catalog, request, tool, options.get("minimap_preset", "asm10"), threads,
                               skip_self=options.get("skip_self") == "true")
            tasks.append(task)
            hits = read_paf(root / task["paf"], query_lengths={key: catalog.parts[key].interval.length for key in remaining},
                            target_lengths={key: catalog.parts[key].interval.length for key in anchors}, artifact=task["paf"])
            added = add_pairwise_candidates(catalog, observe_part_hits(catalog, hits, known_pairs), set(remaining), set(anchors),
                                            known_pairs=known_pairs)
            catalog.payload["discovery_rounds"].append({"task_id": task["task_id"], "added_segment_ids": sorted(added)})
            if not added:
                break
            remaining, anchors = catalog.unplaced(), sorted(added)
        request = partial_source_request(catalog, minimum_uncovered_bp=POLICY["partial_source_discovery_min_uncovered_bp"])
        partial_tasks = []
        if request:
            preset = options.get("minimap_preset", "asm10")
            # A complete original whole-source mapping has priority, even if it
            # finished while an optimized revision was being staged.
            task = _supplement(root, catalog, request, tool, preset, threads,
                               skip_self=options.get("skip_self") == "true", cache_only=bool(cache))
            if task is not None:
                partial_tasks.append(task)
            else:
                from .q0_reference_index import ReferenceIndex
                with closing(ReferenceIndex.open(cache.path, root, catalog.parts, lengths, local_paf_directory=cache.paf_directory)) as index:
                    regional_tasks, fallback_ids, report = prepare_partial(
                        root, catalog, index, known_pairs, tool, reference_lengths=lengths,
                        preset=preset, threads=threads, skip_self=options.get("skip_self") == "true")
                partial_tasks.extend(regional_tasks)
                catalog.payload["regional_partial_discovery"] = report
                if fallback_ids:
                    fallback_request = {**request, "query_ids": fallback_ids}
                    partial_tasks.append(_supplement(root, catalog, fallback_request, tool, preset, threads,
                                                    skip_self=options.get("skip_self") == "true"))
            tasks.extend(partial_tasks)
            # One discovery round, not one full catalog rebuild per window.
            # Keep each PAF's own declared geometry/artifact while accumulating
            # candidates against the same anchor snapshot as the native round.
            def partial_hits():
                for task in partial_tasks:
                    yield from read_paf(root / task["paf"],
                        query_lengths={key: catalog.parts[key].interval.length for key in task["query_ids"]},
                        target_lengths={key: catalog.parts[key].interval.length for key in task["target_ids"]}, artifact=task["paf"])
            if partial_tasks:
                add_pairwise_candidates(catalog, observe_part_hits(catalog, partial_hits(), known_pairs),
                    {key for task in partial_tasks for key in task["query_ids"]},
                    {key for task in partial_tasks for key in task["target_ids"]},
                    include_placed=True, known_pairs=known_pairs)
        for request in supplemental_groups(catalog, assignments, known_pairs):
            tasks.append(_supplement(root, catalog, request, tool, options.get("minimap_preset", "asm10"), threads,
                                     skip_self=options.get("skip_self") == "true"))
        if sha256_file(Path(tool["resolved"])) != tool["sha256"]:
            raise Q0EvidenceError("q0 supplementary aligner changed during preparation")
        if inputs != [identity(root, relative) for relative in input_paths]:
            raise Q0EvidenceError("q0 evidence inputs changed during preparation; no manifest published")
        if builder_identity() != builder:
            raise Q0EvidenceError("q0 evidence builder changed during preparation; no manifest published")
        payload = catalog.finish()
        payload["base_alignments"] = base_alignments
        payload["supplementary_alignments"] = tasks
        catalog_name = f"grt/evidence/q0_prepare/{stable_id('catalog', payload)}.json"
        atomic_write_json(root / catalog_name, payload)
        output_paths = {catalog_name}
        for task in tasks:
            output_paths.add(task["receipt"])
            output_paths.update(row["path"] for row in json_file(root / task["receipt"])["outputs"])
        manifest = {"schema": SCHEMA, "status": "success", "policy": POLICY, "builder": builder,
                    "input_fingerprint": request_identity, "inputs": inputs,
                    "outputs": [identity(root, relative) for relative in sorted(output_paths)],
                    "catalog": catalog_name, "tool": tool}
        atomic_write_json(root / MANIFEST, manifest)
        print(f"LGZ q0 evidence prepared: candidates={len(payload['candidates'])} "
              f"supplementary_tasks={len(tasks)} unplaced_segments={len(payload['unplaced_segment_ids'])}")
        return manifest
