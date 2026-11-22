"""Execute and stage the three additional pinned post-LGZ refinement engines.

The outer runner owns locking, independent branch failure handling and publication.
This module executes one native tool, validates native trace/FASTA agreement, and
builds a genuinely refined sourced Final Path. No scheduler jobs are submitted.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
import time
from datetime import datetime, timezone

try:
    from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, workspace_join
    from post_lgz_degap import IndexedFasta, atomic_json, digest, stat_key
    from refinement_tools import load_lock, validate_runtime, fingerprint, source_location, ToolError
    from refinement_recipes import Invocation, make_invocation, prepare_native_reads, select_reads, materialize_native_driver
    from refinement_sources import FastaCatalog
    from refinement_publication import verify_baseline, prepare_publication
    from refinement_path import PathError
    from refinement_degap import materialize_patches, stage_degap
    from refinement_native_trace import retained, verify_trace, normalized_edits, TraceError
    from refinement_native_formats import CandidateStore, parse_tgs, parse_quartet, parse_lr_rows, apply_lr_round
    from refinement_native_checkpoint import execute as execute_native, quartet_empty_outcome
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, workspace_join
    from .post_lgz_degap import IndexedFasta, atomic_json, digest, stat_key
    from .refinement_tools import load_lock, validate_runtime, fingerprint, source_location, ToolError
    from .refinement_recipes import Invocation, make_invocation, prepare_native_reads, select_reads, materialize_native_driver
    from .refinement_sources import FastaCatalog
    from .refinement_publication import verify_baseline, prepare_publication
    from .refinement_path import PathError
    from .refinement_degap import materialize_patches, stage_degap
    from .refinement_native_trace import retained, verify_trace, normalized_edits, TraceError
    from .refinement_native_formats import CandidateStore, parse_tgs, parse_quartet, parse_lr_rows, apply_lr_round
    from .refinement_native_checkpoint import execute as execute_native, quartet_empty_outcome


ADAPTER_FILES = ("refinement_native.py", "refinement_native_formats.py", "refinement_native_trace.py",
                 "refinement_path.py", "refinement_sources.py", "refinement_publication.py",
                 "refinement_degap.py", "refinement_recipes.py", "refinement_reads.py", "refinement_tools.py", "refinement_native_checkpoint.py",
                 "refinement_native_units.py", "refinement_native_runner.py", "refinement_degap_units.py", "refinement_tgs_units.py")

class NamedGenome:
    def __init__(self, index, original_to_native):
        if set(index.records) != set(original_to_native.values()):
            raise TraceError("native assembly has missing or unexpected chromosome identities")
        self.index, self.names = index, original_to_native
        self.records = {original: index.records[native] for original, native in original_to_native.items()}

    def fetch(self, name, start, end):
        return self.index.fetch(self.names[name], start, end)

    def blocks(self, name, start, end):
        yield from self.index.blocks(self.names[name], start, end)


def native_baseline(tool, baseline, input_directory):
    mapping = {name: name for name in baseline.records}
    path = baseline.path
    # The LR Perl protocol uses chromosome names as compound interval strings.
    # Rename only when required; source sequences and original names are retained.
    if tool == "lrgapcloser" and any(re.fullmatch(r"[A-Za-z0-9_.]+", name) is None for name in mapping):
        mapping = {name: f"cgat_chr_{index:06d}" for index, name in enumerate(mapping, 1)}
        path = input_directory / "baseline.fa"
        with path.open("xb") as stream:
            for name, alias in mapping.items():
                stream.write(b">" + alias.encode("ascii") + b"\n")
                for block in baseline.blocks(name, 0, baseline.records[name][0]):
                    stream.write(block.upper())
                stream.write(b"\n")
    atomic_json(input_directory / "chromosome_names.json", {"original_to_native": mapping})
    return path, mapping


def sequence_summary(genome):
    summary = {}
    for name, (length, *_) in genome.records.items():
        sha, n = hashlib.sha256(), 0
        for block in genome.blocks(name, 0, length):
            block = block.upper()
            sha.update(block)
            n += block.count(b"N")
        summary[name] = {"length": length, "sha256": sha.hexdigest(), "n_bases": n}
    return summary


def _stage(root, tool, groups, threads, run_id):
    stage_started = time.monotonic()
    stage_started_at = datetime.now(timezone.utc).isoformat()
    root = Path(root).resolve()
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2 or tool not in {"tgsgapcloser", "quartet", "lrgapcloser"}:
        raise ToolError("additional refinement engines require a numbered workspace and a known tool")
    if type(threads) is not int or threads < 1:
        raise ToolError("refinement threads must be positive")
    lock = load_lock()
    runtime = validate_runtime(lock=lock, tool=tool)
    selection = select_reads(tool, groups)
    runtime_identities = {}
    for group in (runtime.get("tools", {}), runtime.get("dependencies", {})):
        for record in group.values():
            if not record.get("name"):
                continue
            for relative, expected in record.get("files_sha256", {}).items():
                path = Path(sys.prefix) / relative
                before = stat_key(path)
                if digest(path) != expected or stat_key(path) != before:
                    raise ToolError("managed runtime changed after verification")
                runtime_identities[path] = before
    if tool == "quartet" and "quartet" in runtime.get("tools", {}):
        source = source_location(Path(sys.prefix), lock["tools"]["quartet"])
        for relative, expected in runtime["tools"]["quartet"]["files_sha256"].items():
            path = source / "source" / relative
            before = stat_key(path)
            if digest(path) != expected or stat_key(path) != before:
                raise ToolError("quarTeT source changed after verification")
            runtime_identities[path] = before
        runtime_identities[source / "quartet_runner.py"] = stat_key(source / "quartet_runner.py")
    adapter_hashes = {}
    for name in ADAPTER_FILES:
        path = Path(__file__).parent / name
        before = stat_key(path)
        adapter_hashes[name] = digest(path)
        if stat_key(path) != before:
            raise ToolError("refinement adapter changed during setup")
        runtime_identities[path] = before
    code = TOOL_DIRECTORIES[tool]
    paths = {name: layout.path(f"04_refinement/{code}/{name}/{run_id}")
             for name in ("01_inputs", "02_jobs", "03_native", "04_accepted", "05_report")}
    if paths["03_native"].exists() or paths["03_native"].is_symlink():
        raise ToolError("native attempt directory already exists; validated resume must be explicit")
    for name in ("01_inputs", "02_jobs", "04_accepted", "05_report"):
        paths[name].mkdir(parents=True, exist_ok=False)
    private = root / ".runtime/refinement" / code / run_id
    catalog = FastaCatalog(root, private / "indexes")
    catalog.load_workspace()
    final_path_file = workspace_join(root, "metadata/grt_final_path.json")
    before_path = stat_key(final_path_file)
    baseline_payload = json.loads(final_path_file.read_text())
    baseline_path = layout.path(baseline_payload["q4_relpath"])
    baseline = IndexedFasta(baseline_path, catalog.index_directory / "baseline.fa")
    gaps = verify_baseline(baseline_payload, catalog, baseline)
    if stat_key(final_path_file) != before_path:
        raise PathError("LGZ baseline Final Path changed during refinement setup")
    identities = {**runtime_identities, final_path_file: before_path, baseline_path: baseline.identity}
    skip = "no_remaining_gaps" if not gaps else "no_eligible_gaps" if tool == "quartet" and not any(g.end - g.start >= 100 for g in gaps) else None
    reads_manifest = []
    for technology, files in selection["selected"].items():
        for raw in files:
            path = Path(raw)
            if skip:
                if not path.is_file():
                    raise ToolError("requested reads input is missing")
                reads_manifest.append({"technology": technology, "path": str(path), "not_consumed": True, "reason": skip})
                continue
            before = stat_key(path)
            sha = digest(path)
            if stat_key(path) != before:
                raise PathError("reads changed while fingerprinting")
            identities[path] = before
            reads_manifest.append({"technology": technology, "path": str(path), "sha256": sha})
    prepared = ({"original_selection": selection, "prepared": selection["selected"], "conversions": {}} if skip
                else prepare_native_reads(tool, groups, layout.path("data/reads") / "converted"))
    for conversion in prepared["conversions"].values():
        parent = Path(conversion["fasta"]).parent
        for relative in (*conversion["outputs"], "conversion.json"):
            identities[parent / relative] = stat_key(parent / relative)
    actual_input, original_to_native = (baseline.path, {name: name for name in baseline.records}) if skip else native_baseline(tool, baseline, paths["01_inputs"])
    identities[actual_input] = stat_key(actual_input)
    native_to_original = {value: key for key, value in original_to_native.items()}
    # LR writes split fragments in its cwd; isolate that cwd per attempt too.
    native_directory = paths["03_native"] / "output" if tool == "lrgapcloser" else paths["03_native"]
    if skip:
        definition = lock["tools"][tool]
        invocation = Invocation(tool, (), native_directory, {}, (),
                                {"name": definition["recipe"], "tool": tool, "version": definition["version"],
                                 "revision": definition["revision"], "runtime_sha256": fingerprint(runtime),
                                 "parameters": definition["parameters"], "threads": threads})
    else:
        invocation = make_invocation(tool, actual_input, prepared["prepared"], native_directory, threads, runtime=runtime, lock=lock, jobs_dir=paths["02_jobs"])
    recipe = {**invocation.recipe, "original_selection": prepared["original_selection"], "reads": reads_manifest,
              "conversions": {kind: {key: value for key, value in conversion.items() if key != "cache_hit"}
                              for kind, conversion in prepared["conversions"].items()},
              "baseline_source_files": catalog.baseline_bindings(), "baseline_sha256": digest(baseline_path), "baseline_final_path_sha256": digest(final_path_file),
              "native_input_sha256": digest(actual_input), "chromosome_names": original_to_native,
              "adapter_sources": adapter_hashes}
    atomic_json(paths["01_inputs"] / "recipe.json", recipe)
    invocation_record = {"tool": tool, "run_id": run_id, "command": list(invocation.command), "cwd": str(invocation.cwd),
                         "threads": threads, "recipe_sha256": fingerprint(recipe), "status": "running",
                         "timing": {"started_at": stage_started_at}}
    atomic_json(paths["02_jobs"] / "invocation.json", invocation_record)
    native_artifacts, result_file, result_genome = {}, None, None
    native_executed, returncode, completion = False, None, None
    traces = {name: [retained(0, row[0])] for name, row in baseline.records.items()}
    if skip:
        outcome = skip
        receipt = paths["02_jobs"] / "native_noop.json"
        atomic_json(receipt, {"reason": skip, "baseline_sha256": recipe["baseline_sha256"]})
        native_artifacts[receipt.relative_to(root).as_posix()] = digest(receipt)
    else:
        def verify_inputs():
            catalog.verify_unchanged()
            if any(stat_key(path) != expected for path, expected in identities.items()):
                raise PathError("refinement inputs, runtime or native evidence changed during execution")
        input_hashes = {row["path"]: row["sha256"] for row in reads_manifest}
        input_hashes[str(actual_input)] = recipe["native_input_sha256"]
        names_file = paths["01_inputs"] / "chromosome_names.json"
        input_hashes[str(names_file)] = digest(names_file)
        identities[names_file] = stat_key(names_file)
        for conversion in prepared["conversions"].values():
            parent = Path(conversion["fasta"]).parent
            for relative in (*conversion["outputs"], "conversion.json"):
                file = parent / relative
                input_hashes[str(file)] = digest(file)
        files = [path for values in prepared["prepared"].values() for path in values]
        completion = execute_native(root, invocation, recipe, paths, invocation_record, identities, verify_inputs,
                                    chromosomes=set(original_to_native.values()), parameters=lock["tools"][tool]["parameters"],
                                    input_hashes=input_hashes, prepared_files=files, driver_factory=materialize_native_driver)
        native_directory = paths["03_native"] / "output" if tool == "lrgapcloser" else paths["03_native"]
        native_artifacts.update(completion["result"]["artifacts"])
        native_executed, returncode = not completion["reused"], completion["execution"]["returncode"]
        outcome = completion["result"]["outcome"]
        if outcome == "completed":
            if tool == "lrgapcloser":
                maximum = lock["tools"][tool]["parameters"]["iterations"]
                iterations = [i for i in range(1, maximum + 1) if (native_directory / f"iteration-{i}/gapclosed.fasta").is_file()]
                if iterations != list(range(1, len(iterations) + 1)):
                    raise TraceError("LR_Gapcloser iterations are incomplete")
                row_files = [native_directory / f"iteration-{i}/tmp/info_filter2" for i in iterations]
                for number, row_file in enumerate(row_files, 1):
                    for artifact in (row_file, native_directory / f"iteration-{number}/gapclosed.fasta"):
                        before = stat_key(artifact)
                        relative = artifact.relative_to(root).as_posix()
                        if native_artifacts.get(relative) != digest(artifact) or stat_key(artifact) != before:
                            raise TraceError("LR_Gapcloser evidence changed or was not sealed at native completion")
                        identities.setdefault(artifact, before)
                rounds, lookup = parse_lr_rows(row_files, native_to_original, files[0])
                previous = baseline
                for number, rows in enumerate(rounds, 1):
                    path = native_directory / f"iteration-{number}/gapclosed.fasta"
                    index = IndexedFasta(path, catalog.index_directory / f"lr-round-{number}.fa")
                    native = NamedGenome(index, original_to_native)
                    store = CandidateStore(paths["04_accepted"] / f"native-round-{number}.fa", catalog,
                                           f"native_lr_{run_id}_{number}", tool)
                    try:
                        traces = apply_lr_round(traces, rows, baseline, previous, native_to_original, lookup, store, number)
                        store.finish()
                    finally:
                        store.close()
                    for name in traces:
                        verify_trace(traces[name], name, baseline, catalog, native)
                    previous, result_file, result_genome = native, path, native
            else:
                result_file = native_directory / invocation.required_outputs[0]
                result_genome = NamedGenome(IndexedFasta(result_file, catalog.index_directory / "native-result.fa"), original_to_native)
                store = CandidateStore(paths["04_accepted"] / "native-candidates.fa", catalog, f"native_{tool}_{run_id}", tool)
                try:
                    if tool == "tgsgapcloser":
                        traces, original_traces = parse_tgs(native_directory, baseline, native_to_original, store)
                    else:
                        traces = parse_quartet(native_directory, baseline, gaps, native_to_original, files, store)
                    store.finish()
                finally:
                    store.close()
                if tool == "tgsgapcloser":
                    for name in original_traces:
                        verify_trace(original_traces[name], name, baseline, catalog, baseline)
                for name in traces:
                    verify_trace(traces[name], name, baseline, catalog, result_genome)
    edits, rejected, native_summary = [], [], {}
    if result_genome is not None:
        dataset = f"native_result_{tool}_{run_id}"
        for original, native_name in original_to_native.items():
            catalog.register(dataset, native_name, result_file, origin="native:" + tool)
        native_summary = {original: completion["result"]["native_assembly"][native_name]
                          for original, native_name in original_to_native.items()}
        edits, rejected = normalized_edits(tool, traces, baseline, result_genome, gaps, native_dataset=dataset,
                                          native_names=original_to_native, job=native_directory.relative_to(root).as_posix())
        edits = materialize_patches(edits, catalog, paths["04_accepted"], tool=tool)
    catalog.verify_unchanged()
    if any(stat_key(path) != expected for path, expected in identities.items()):
        raise PathError("refinement inputs/native evidence changed during execution")
    invocation_record["timing"].update(before_publication_seconds=time.monotonic() - stage_started,
                                       admission_finished_at=datetime.now(timezone.utc).isoformat())
    execution = {**invocation_record, "status": "success", "baseline_sha256": recipe["baseline_sha256"],
                 "native_executed": native_executed, "native_returncode": returncode, "native_outcome": outcome,
                 "native_assembly": native_summary, "require_native_equality": not rejected and result_genome is not None,
                 "recipe": recipe, "artifacts": native_artifacts}
    atomic_json(paths["02_jobs"] / "execution.json", execution)
    staging = private / "final"
    provenance = prepare_publication(staging, baseline_payload, baseline_path, catalog, edits, execution, rejected)
    if any(stat_key(path) != expected for path, expected in identities.items()):
        raise PathError("refinement inputs/native evidence changed during final reconstruction")
    atomic_json(paths["05_report"] / "report.json", provenance)
    atomic_json(paths["02_jobs"] / "invocation.json", {**invocation_record, "status": "staged", "native_outcome": outcome,
                "provenance_sha256": digest(staging / "provenance.json")})
    return {"tool": tool, "run_id": run_id, "staging": str(staging), "provenance": provenance}


def stage_refinement(root, tool, groups, threads, *, run_id=None):
    if tool == "degap":
        return stage_degap(root, groups, threads, run_id=run_id)
    if tool not in TOOL_DIRECTORIES:
        raise ToolError("unknown refinement tool")
    run_id = run_id or uuid.uuid4().hex
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ToolError("invalid refinement attempt identity")
    receipt = Path(root) / "04_refinement" / TOOL_DIRECTORIES[tool] / "02_jobs" / run_id / "invocation.json"
    if receipt.parent.exists():
        raise ToolError("refinement attempt already exists")
    try:
        return _stage(root, tool, groups, threads, run_id)
    except BaseException as error:
        if receipt.is_file():
            value = json.loads(receipt.read_text())
            value.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
                         error_type=type(error).__name__, error=str(error))
            atomic_json(receipt, value)
        raise
