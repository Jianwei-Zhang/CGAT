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
import shutil
import uuid
from typing import Iterable

from .common import canonical_json, executable_identity, read_fasta, sha256_file, stable_id, write_fasta
from .q0_alignments import read_paf
from .q0_catalog import (CATALOG_SCHEMA, CandidateCatalog, DISCOVERY_REFERENCE_IDENTITY, DISCOVERY_REFERENCE_MAPQ,
                         add_pairwise_candidates, build_catalog, partial_source_request, supplemental_groups, ObservedSourcePairs)
from .q0_regional_discovery import REGIONAL_POLICY, LocalReferenceCache, enabled as regional_enabled, observe_part_hits, prepare_partial
from .q0_regional_candidates import CANDIDATE_POLICY, CandidatePlan, CompletedNativeScopes, prepare_candidates
from .q0_cigar_policy import WEAK_GLOBAL_SEED_POLICY, weak_global_seed_scope
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
POLICY = {"version": 5, "weak_global_seed": WEAK_GLOBAL_SEED_POLICY, "regional_partial_discovery": REGIONAL_POLICY, "regional_candidate_discovery": CANDIDATE_POLICY, "min_gap": 100, "discovery": "unplaced_to_new_anchors_until_fixed_point",
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
    return {"path": relative, "sha256": _partition_sha256(path), "size": path.stat().st_size}


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
            "q0_cigar_policy.py", "q0_mapper_guard.py", "q0_regional_discovery.py", "q0_neighbor_requests.py", "q0_regional_candidates.py", "q0_regional_execution.py")])


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
        # Both inventories are already indexed by path. Rebuilding their
        # union for every PAF record turns a linear check into evidence × files.
        for row in catalog["evidence"].values():
            artifact = row["artifact"]
            if artifact not in inputs and artifact not in outputs:
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
    # This stage uses only names/lengths; do not retain a multi-Gb reference
    # DNA dictionary alongside all de novo sequences. Still parse every record.
    refs = {name: len(sequence) for name,sequence in read_fasta(artifact_path(root, references[0]["fasta_relpath"]))}
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
    if sha256_file(Path(tool["resolved"])) != tool["sha256"]:
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
    directory = root / relative
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



def _unroutable_seed(root, catalog, request, tool, preset, threads, *, reference_bases, skip_self=False, prepared_target=None, on_cache_hit=None):
    task=_supplement(root,catalog,request,tool,preset,threads,skip_self=skip_self,cache_only=True,on_cache_hit=on_cache_hit)
    if task is not None:return task
    queries,targets=weak_global_seed_scope(catalog.parts,catalog.reference_routable_parts,
        request['query_ids'],request['target_ids'],reference_bases=reference_bases,preset=preset)
    fast=bool(queries and targets)
    # Dense native repeats can exhaust memory even with a tiny target. The
    # short-side completion uses a separate bounded worker budget, not 32 by default.
    if request.get('native_short_targets_as_queries'):threads=min(threads,8)
    return _supplement(root,catalog,request,tool,preset,threads,skip_self=skip_self,
                       prepared_target=prepared_target,weak_seed_fast=fast,reference_bases=reference_bases,on_cache_hit=on_cache_hit)


def _complete_unroutable_seeds(root,catalog,index,query_ids,target_ids,tasks,known_pairs,tool,preset,threads,*,reference_bases,skip_self):
    scopes=CompletedNativeScopes(root,catalog,index,tasks,tool,preset)
    seen={task['task_id'] for task in tasks}
    while True:
        request=scopes.next_missing_seed(query_ids,target_ids)
        if request is None:break
        template_task=next((task for task in tasks if task['kind']!='regional_discovery'
                            and task['target_ids']==request['target_ids']),None)
        template=({'root':str(root),'receipt':identity(root,template_task['receipt'])} if template_task else None)
        consumed = False
        def consume_seed(seed,hits):
            nonlocal consumed
            if seed['task_id'] in seen:raise Q0EvidenceError('unroutable seed made no matrix progress')
            seen.add(seed['task_id']);tasks.append(seed);scopes.add_complete_tasks([seed])
            add_pairwise_candidates(catalog,observe_part_hits(catalog,hits,known_pairs),set(seed['query_ids']),set(seed['target_ids']),
                                    include_placed=True,known_pairs=known_pairs)
            consumed = True
        seed=_unroutable_seed(root,catalog,request,tool,preset,threads,reference_bases=reference_bases,
                             skip_self=skip_self,prepared_target=template,on_cache_hit=consume_seed)
        if not consumed:
            hits=read_paf(root/seed['paf'],query_lengths={key:catalog.parts[key].interval.length for key in seed['query_ids']},
                          target_lengths={key:catalog.parts[key].interval.length for key in seed['target_ids']},artifact=seed['paf'])
            consume_seed(seed,hits)
        print(f"LGZ q0 weak seed: completed={seed['task_id']} approximate={seed['task_id'] in scopes.approximate_scope_task_ids} "
              f"queries={len(seed['query_ids'])} targets={len(seed['target_ids'])}",flush=True)
    return scopes

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
                hits = read_paf(root/task['paf'],query_lengths={key:catalog.parts[key].interval.length for key in task['query_ids']},
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
                        complete_tasks=tasks,required_target_ids=request["target_ids"])
                partial_tasks.extend(regional_tasks)
                catalog.payload["regional_partial_discovery"] = report
                if fallback_ids:
                    fallback_request = {**request, "query_ids": fallback_ids}
                    partial_tasks.append(_supplement(root, catalog, fallback_request, tool, preset, threads,
                                                    skip_self=options.get("skip_self") == "true"))
            if not partial_consumed:tasks.extend(partial_tasks)
            # One discovery round, not one full catalog rebuild per window.
            # Keep each PAF's own declared geometry/artifact while accumulating
            # candidates against the same anchor snapshot as the native round.
            def partial_hits():
                for task in partial_tasks:
                    yield from read_paf(root / task["paf"],
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
                seed_ids = []
                while (seed_request := planner.next_unroutable_seed()) is not None:
                    seed = _unroutable_seed(root,catalog,seed_request,tool,preset,threads,
                        reference_bases=sum(lengths.values()),skip_self=options.get("skip_self") == "true")
                    tasks.append(seed);seed_ids.append(seed["task_id"]);planner.add_complete_tasks([seed])
                regional_tasks, native_requests, report = prepare_candidates(
                    root,catalog,index,pending_candidates,known_pairs,tasks,tool,reference_lengths=lengths,
                    preset=preset,threads=threads,skip_self=options.get("skip_self") == "true",planner=planner)
                report["unroutable_seed_task_ids"] = seed_ids
            tasks.extend(regional_tasks)
            catalog.payload["regional_candidate_discovery"] = report
            for request in native_requests:
                tasks.append(_supplement(root,catalog,request,tool,options.get("minimap_preset", "asm10"),threads,
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
        outputs = [identity(root, relative) for relative in sorted(output_paths)]
        output_identities = {row["path"]: row for row in outputs}
        # A long later phase must not publish success if any reused earlier
        # output changed after its validation. Reuse the final hashes above.
        for task in tasks:
            if any(output_identities.get(row["path"]) != row for row in json_file(root/task["receipt"])["outputs"]):
                raise Q0EvidenceError("completed supplementary output changed before publication")
        manifest = {"schema": SCHEMA, "status": "success", "policy": POLICY, "builder": builder,
                    "input_fingerprint": request_identity, "inputs": inputs,
                    "outputs": outputs,
                    "catalog": catalog_name, "tool": tool}
        atomic_write_json(root / MANIFEST, manifest)
        print(f"LGZ q0 evidence prepared: candidates={len(payload['candidates'])} "
              f"supplementary_tasks={len(tasks)} unplaced_segments={len(payload['unplaced_segment_ids'])}")
        return manifest
