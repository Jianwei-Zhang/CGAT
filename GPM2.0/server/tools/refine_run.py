"""Run content-bound local refinement jobs and publish a project return archive."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid
from zipfile import ZIP_DEFLATED, ZipFile

from degap_manual_catalog import content_digest
from post_lgz_degap import IndexedFasta, stat_key
from post_lgz_refinement import run_child_group
from refinement_degap import verify_engine
from refinement_native_checkpoint import capture, fasta_facts
from refinement_path import PathError
from refinement_presets import degap_args, effective as degap_preset
from refinement_recipes import make_invocation, materialize_native_driver, prepare_native_reads, select_reads
from refinement_tools import ToolError, fingerprint, load_lock, validate_runtime, verify_directory_links
from run_resources import execution_threads, prepared_resources
from run_orchestration import sha256_file
from workspace_migration import durable_json, rename_synced, sync_directories

RESULTS = "cgat.app-refinement-results.v1"
MANIFEST = "refinement_results.json"
MAX_PATCH_BP = 100_000_000
BLOCK = 1024 * 1024


def fact(path):
    before = stat_key(path)
    digest = content_digest(path)
    if stat_key(path) != before:
        raise ValueError("input changed while hashing")
    return digest, before


class ReadsUnavailable(ValueError):
    pass


def select_checked_reads(tool, provided, override):
    groups = {kind: [row["path"] for row in provided[kind]] if override.get(kind) is None else override[kind]
              for kind in ("hifi", "ont")}
    if not any(groups.values()):
        raise ReadsUnavailable("Provide HiFi and/or ONT reads on the Server")
    selection = select_reads(tool, groups)
    fingerprints, identities = [], {}
    for kind, paths in selection["selected"].items():
        expected = {str(Path(row["path"]).resolve()): row["sha256"] for row in provided[kind]}
        for value in paths:
            path = Path(value)
            try:
                if not path.is_file():
                    raise FileNotFoundError(path)
                value_sha, before = fact(path)
            except OSError as exc:
                raise ReadsUnavailable(f"Unreadable {kind} reads; check the Server path") from exc
            if expected.get(value) not in (None, value_sha):
                raise ReadsUnavailable(f"The content of the recorded {kind} reads changed; check the inputs")
            fingerprints.append({"technology": kind, "path": value, "sha256": value_sha})
            identities[path] = before
    return selection["selected"], fingerprints, identities


def length(genome, name):
    if set(genome.records) != {name}:
        raise PathError("native/local FASTA does not have exactly the requested record")
    return genome.records[name][0]


def equal_interval(a, aname, start, b, bname, other, size):
    for offset in range(0, size, BLOCK):
        n = min(size - offset, BLOCK)
        if a.fetch(aname, start + offset, start + offset + n).upper() != b.fetch(bname, other + offset, other + offset + n).upper():
            return False
    return True


def indexed(path, attempt, label):
    if path.is_symlink() or not path.is_file():
        raise PathError("native FASTA is missing or not a regular file")
    return IndexedFasta(path, attempt / f"{label}.fai-work.fa")


def gap_patch(attempt, locus, seeds, terminal):
    original = indexed(seeds / "local.fa", attempt, "local")
    native = indexed(terminal, attempt, "native")
    size, after = length(original, "locus"), length(native, "locus")
    start = abs(locus["witnesses"]["seqleft"]["start"] - locus["witnesses"]["seqleft"]["end"]) + 1
    tail = abs(locus["witnesses"]["seqright"]["start"] - locus["witnesses"]["seqright"]["end"]) + 1
    gap = locus["gap_bp"]
    if size != start + gap + tail:
        raise PathError("prepared Gap span does not match the local input")
    before = hashlib.sha256()
    for offset in range(0, gap, BLOCK):
        block = original.fetch("locus", start + offset, start + min(gap, offset + BLOCK)).upper()
        if block.count(b"N") != len(block):
            raise PathError("target Gap is not an N run")
        before.update(block)
    if (after < start + tail or not equal_interval(original, "locus", 0, native, "locus", 0, start)
            or not equal_interval(original, "locus", size - tail, native, "locus", after - tail, tail)):
        return "rejected", "native_candidate_requires_flank_change", None
    size_new = after - tail - start
    if size_new > MAX_PATCH_BP:
        return "rejected", "native_patch_exceeds_size_limit", None
    sequence = b"".join(block.upper() for block in native.blocks("locus", start, after - tail))
    if len(sequence) == gap and sequence.count(b"N") == gap:
        return "no_candidate", "original_gap_unchanged", None
    if sequence and sequence.count(b"N") == len(sequence):
        return "no_candidate", "native_candidate_contains_only_ns", None
    if b"N" in sequence:
        return "rejected", "incomplete_gap_kept_original", None
    return "closed", None, ("replace_gap", gap, before.hexdigest(), sequence)


def tel_patch(attempt, locus, seeds, directory):
    end = "L" if locus["kind"] == "tel_left" else "R"
    statuses = directory / "result/status.tsv"
    if statuses.is_symlink() or not statuses.is_file():
        raise PathError("TelSeeker did not complete an endpoint status")
    with statuses.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != 1 or rows[0].get("ctg_id") != "endpoint" or rows[0].get("end") != end:
        raise PathError("TelSeeker result does not match the requested endpoint")
    row = rows[0]
    artifacts = {statuses: sha256_file(statuses)}
    if row["status"] != "success":
        reason = row.get("stop_reason", "no_candidate")
        return ("no_candidate", reason if re.fullmatch(r"[a-z0-9_]+", reason) else "native_no_candidate", None), artifacts
    terminal = directory / "telseeker_ctg.jobs" / f"endpoint.{end}" / "result/extended.ctg.fa"
    if terminal.is_symlink() or not terminal.is_file():
        raise PathError("missing expected TelSeeker contig result")
    original = indexed(seeds / "endpoint.fa", attempt, "endpoint")
    native = indexed(terminal, attempt, "native-tel")
    size, after = length(original, "endpoint"), length(native, "endpoint")
    if row.get("original_length") != str(size) or row.get("final_length") != str(after):
        raise PathError("TelSeeker status does not bind the original and resulting endpoint lengths")
    artifacts[terminal] = sha256_file(terminal)
    extension = after - size
    if extension <= 0:
        return ("no_candidate", "no_positive_terminal_extension", None), artifacts
    if extension > MAX_PATCH_BP:
        return ("rejected", "native_patch_exceeds_size_limit", None), artifacts
    if not equal_interval(original, "endpoint", 0, native, "endpoint", extension if end == "L" else 0, size):
        return ("rejected", "native_candidate_changes_original_endpoint", None), artifacts
    sequence = b"".join(block.upper() for block in native.blocks(
        "endpoint", 0 if end == "L" else size, extension if end == "L" else after))
    if b"N" in sequence:
        return ("rejected", "terminal_extension_contains_ns", None), artifacts
    _, facts, _ = fasta_facts(seeds / "endpoint.fa", {"endpoint"})
    return ("extended", None, ("prepend_tel" if end == "L" else "append_tel", size, facts["endpoint"]["sha256"], sequence)), artifacts


def safe_input_paths(layout, seeds, prepared):
    # Receipts record scientific source files and generated inputs. Check them
    # at execution time, not just on preparation; don't rely on cache mtimes.
    identities = {}
    for rows in prepared["sources"].values():
        for row in rows:
            path = Path(row["source"])
            actual, stat = fact(path)
            if actual != row["fasta_sha256"]:
                raise PathError("the source for a prepared locus has changed")
            identities[path] = stat
    for name, expected in prepared["files"].items():
        path = layout.path((seeds / name).relative_to(layout.root).as_posix())
        actual, stat = fact(path)
        if path.is_symlink() or actual != expected:
            raise PathError("the prepared locus sequence has changed")
        identities[path] = stat
    return identities


def check_identities(identities):
    if any(stat_key(path) != initial for path, initial in identities.items()):
        raise PathError("reads or locus sources changed during execution")


def output_row(locus, tool, status, *, reason=None, patch=None, **run):
    return {"locus_id": locus["id"], "tool": tool, "status": status, "reason": reason, "patch": patch, **run}


def run_tool(layout, batch_dir, locus, tool, seeds, prepared, groups, reads_binding, read_ids, threads, lock, runtime,
             tool_override=None):
    attempt_id = uuid.uuid4().hex
    attempt = layout.path((batch_dir / "02_jobs" / locus["id"] / tool / attempt_id).relative_to(layout.root).as_posix())
    attempt.mkdir(parents=True, exist_ok=False)
    identities = {**safe_input_paths(layout, seeds, prepared), **read_ids}
    definition = lock["tools"][tool]
    override_params = dict(tool_override) if isinstance(tool_override, dict) else {}
    profile = {**degap_preset(layout.root), **override_params} if tool == "degap" else None
    converted = prepare_native_reads(tool, groups, batch_dir / "01_inputs" / "reads_cache")
    prepared_reads = [path for paths in converted["prepared"].values() for path in paths]
    for value in prepared_reads:
        identities.setdefault(Path(value), stat_key(Path(value)))
    native = attempt / "native"
    if locus["kind"] != "gap":
        # Reuse the same validated environment and read selection as DEGAP Gap.
        invocation = make_invocation(tool, seeds / "endpoint.fa", converted["prepared"], native, threads,
                                     runtime=runtime, lock=lock, degap_parameters=profile)
        entry = Path(__file__).with_name("degap_core") / "bin" / "DEGAP.py"
        if entry.is_symlink() or not entry.is_file():
            raise PathError("pinned TelSeeker entry point is missing")
        command = [invocation.command[0], "-B", str(entry), "--mode", "telseeker_ctg", "--ctg",
                   str(seeds / "endpoint.fa"), "L" if locus["kind"] == "tel_left" else "R",
                   "--motif", locus["motif"], "--out", str(native), "--thread", str(threads), *degap_args(profile)]
        if profile.get("kmer_size") is not None:
            command.extend(("--kmer_size", str(profile["kmer_size"])))
        if profile.get("kmer_num") is not None:
            command.extend(("--kmer_num", str(profile["kmer_num"])))
        if profile.get("edge") is not None:
            command.extend(("--edge", str(profile["edge"])))
        if profile.get("tel_n") is not None:
            command.extend(("--tel-n", str(profile["tel_n"])))
        if profile.get("tel_r") is not None:
            command.extend(("--tel-r", str(profile["tel_r"])))
        if profile.get("tel_mm") is not None:
            command.extend(("--tel-mm", str(profile["tel_mm"])))
        for kind, paths in converted["prepared"].items():
            if paths:
                command += ["--" + kind, *paths]
        driver = None
        cwd = attempt
    else:
        invocation = make_invocation(tool, seeds / "local.fa", converted["prepared"], native, threads,
                                     runtime=runtime, lock=lock, jobs_dir=attempt, degap_parameters=profile,
                                     tool_parameters=override_params or None)
        command, cwd = invocation.command, invocation.cwd
        driver = materialize_native_driver(invocation)
    cwd.mkdir(parents=True, exist_ok=True)
    native_log = attempt / "native.log"
    version = definition["version"]
    revision = definition["revision"]
    durable_json(attempt / "invocation.json", {"schema": "cgat.manual-refinement-execution.v1", "locus_id": locus["id"],
                 "attempt_id": attempt_id, "tool": tool, "version": version, "revision": revision,
                 "command": list(command), "recipe": invocation.recipe, "inputs": prepared["files"], "reads": reads_binding,
                 "preset": profile, "tool_parameters": override_params or None, "runtime_sha256": fingerprint(runtime)})
    check_identities(identities)
    verify_directory_links(runtime)
    try:
        with native_log.open("xb") as log:
            code = run_child_group(command, environment=invocation.environment, cwd=cwd, output=log)
        if code in (130, 143):
            raise KeyboardInterrupt
        if locus["kind"] != "gap":
            if code:
                raise PathError(f"TelSeeker exited with status {code}")
            (status, reason, payload), artifacts = tel_patch(attempt, locus, seeds, native)
            artifacts[native_log] = sha256_file(native_log)
        else:
            native_result_dir = native / "output" if tool == "lrgapcloser" else native
            capture_parameters = dict(definition.get("parameters", {}))
            if tool == "lrgapcloser":
                capture_parameters.update(override_params)
            capture_result, _ = capture(layout.root, tool, attempt_id, native_result_dir, invocation, code, native_log,
                                        {"locus"}, capture_parameters, prepared_reads, driver,
                                        manual_attempt=attempt)
            artifacts = {layout.path(key): value for key, value in capture_result["artifacts"].items()}
            terminal = capture_result.get("terminal")
            if terminal is None:
                status, reason, payload = "no_candidate", capture_result["outcome"], None
            else:
                status, reason, payload = gap_patch(attempt, locus, seeds, layout.path(terminal))
        check_identities(identities)
        verify_directory_links(runtime)
        if any(path.is_symlink() or sha256_file(path) != expected for path, expected in artifacts.items()):
            raise PathError("native evidence changed during local admission")
        patch = None
        if payload is not None:
            operation, original_length, original_sha, sequence = payload
            if sequence and re.fullmatch(rb"[ACGTRYSWKMBDHVN]+", sequence) is None:
                raise PathError("native patch is not IUPAC DNA")
            patch = {"operation": operation, "original_length": original_length, "original_sha256": original_sha,
                     "path": f"patches/{locus['id']}.{tool}.seq", "length": len(sequence),
                     "sha256": hashlib.sha256(sequence).hexdigest()}
            (attempt / "patch.seq").write_bytes(sequence)
        row = output_row(locus, tool, status, reason=reason, patch=patch, version=version, revision=revision, attempt_id=attempt_id)
        durable_json(attempt / "completion.json", {"schema": "cgat.manual-refinement-completion.v1", "row": row,
                     "native_exit": code, "artifacts": {str(path.relative_to(layout.root)): sha for path, sha in artifacts.items()}})
        return row, attempt / "patch.seq" if patch else None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Paths and native error payloads stay on the Server, not in a result
        # bundle that can be sent to a different host/user.
        durable_json(attempt / "failure.json", {"type": type(exc).__name__, "reason": str(exc)})
        return output_row(locus, tool, "failed", reason="native_execution_or_evidence_failed", version=version,
                          revision=revision, attempt_id=attempt_id), None


def write_result_zip(staged,data,rows,patches):
    with ZipFile(staged, "x", compression=ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        for row in rows:
            patch = row["patch"]
            if patch:
                payload = patches[patch["path"]].read_bytes()
                if len(payload) != patch["length"] or hashlib.sha256(payload).hexdigest() != patch["sha256"]:
                    raise PathError("admitted patch changed before packaging")
                archive.writestr(patch["path"], payload)
    with staged.open("rb") as stream:
        os.fsync(stream.fileno())


def publish_results(layout, batch_dir, batch, rows, patches, *, manifest, reads):
    from manual_snapshot import TASKS
    if manifest["schema"] == TASKS:
        from manual_genome import publish
        return publish(layout,batch_dir,batch,manifest,rows,patches,reads)
    data = {"schema": RESULTS, "batch_sha256": batch, "results": rows}
    from refine_report import manual_patch_path
    output = manual_patch_path(layout, batch)
    report = layout.path((batch_dir / "03_report/summary.json").relative_to(layout.root).as_posix())
    if any(path.is_symlink() or (path.exists() and not path.is_file()) for path in (output, report)):
        raise PathError("manual result destinations must be regular files")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".results-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        write_result_zip(staged,data,rows,patches)
        if layout.project_delivery:
            # A return already sent to an App must remain reproducible. A rerun can
            # repair an interrupted first publication, not silently replace its decisions.
            receipt_file = layout.path((batch_dir / "manual-delivery.json").relative_to(layout.root).as_posix())
            if receipt_file.is_symlink():
                raise PathError("manual delivery receipt cannot be a link")
            prior = json.loads(receipt_file.read_text()) if receipt_file.exists() else None
            identity = {"batch":batch,"relative":output.relative_to(layout.root).as_posix(),"result":fingerprint(data)}
            if prior is not None and any(prior.get(k) != v for k,v in identity.items()):
                raise PathError("this manual batch already has different published results; export a new batch")
            if output.exists():
                if not prior or sha256_file(output) != prior.get("sha256"):
                    raise PathError("manual patch is unowned or has changed; not replacing it")
            else:
                if prior and prior.get("state") == "committed":
                    raise PathError("previously published manual patch is missing")
                prior = {**identity,"sha256":sha256_file(staged),"state":"prepared","reads":reads}
                durable_json(receipt_file,prior)
                os.link(staged,output)
                sync_directories(output.parent)
            if prior.get("state") != "committed":
                durable_json(receipt_file,{**prior,"state":"committed"})
        else:
            if output.exists():
                with ZipFile(output) as existing:
                    old = json.loads(existing.read(MANIFEST))
                if old.get("schema") != RESULTS or old.get("batch_sha256") != batch:
                    raise PathError("existing result ZIP is not owned by this manual batch")
            rename_synced(staged, output)
    from refine_report import publish_manual_report
    report_paths = publish_manual_report(layout, batch_dir, manifest, data, reads, output)
    return {"delivery": str(output), **report_paths, "results": rows}


def existing_manual_delivery(layout,batch_dir,batch,manifest,override):
    if not layout.project_delivery:
        return None
    from manual_snapshot import TASKS
    if manifest["schema"] == TASKS:
        from manual_genome import finish
        return finish(layout,batch_dir,batch,manifest,override=override)
    from refine_report import manual_patch_path, publish_manual_report
    receipt = batch_dir / "manual-delivery.json"
    patch = manual_patch_path(layout,batch)
    if receipt.is_symlink() or patch.is_symlink():
        raise PathError("unexpected link at manual publication destination")
    if not receipt.exists():
        if patch.exists():
            raise PathError("unowned manual patch or abbreviated batch-name collision")
        return None
    owner = json.loads(receipt.read_text())
    if owner.get("batch") != batch or owner.get("relative") != patch.relative_to(layout.root).as_posix():
        raise PathError("manual patch belongs to a different batch")
    if not patch.exists() and owner.get("state") == "prepared":
        return None
    if not patch.is_file() or sha256_file(patch) != owner.get("sha256"):
        raise PathError("published manual return is missing or has changed")
    if any(override.get(k) is not None for k in ("hifi","ont")):
        raise PathError("this manual batch is already published; export a new batch to change reads")
    with ZipFile(patch) as archive:
        data = json.loads(archive.read(MANIFEST))
    if data.get("batch_sha256") != batch or data.get("schema") != RESULTS or fingerprint(data) != owner.get("result"):
        raise PathError("manual patch manifest differs from its receipt")
    if owner.get("state") == "prepared":
        durable_json(receipt,{**owner,"state":"committed"})
    elif owner.get("state") != "committed":
        raise PathError("unsupported manual delivery receipt")
    report = publish_manual_report(layout,batch_dir,manifest,data,owner["reads"],patch)
    return {"delivery":str(patch),**report,"results":data["results"]}


def execute_manual(layout, batch_dir, preparation, manifest, override, threads):
    from refine import verify_prepared
    budget = threads or prepared_resources(layout.root)["threads"]
    budget = min(execution_threads(budget, root=layout.root), len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1)
    lock = load_lock()
    runtimes, checks = {}, {}
    rows, patches = [], {}
    batch = preparation["batch_sha256"]
    by_id = {row["id"]: row for row in preparation["loci"]}
    for locus in manifest["loci"]:
        state = by_id[locus["id"]]
        for tool in locus["tools"]:
            def execute_one():
                if state["status"] != "prepared":
                    return output_row(locus, tool, "input_unavailable", reason="locus_preparation_failed"), None
                if tool not in checks:
                    checks[tool] = select_checked_reads(tool, manifest["reads"], override)
                if tool not in runtimes:
                    runtimes[tool] = validate_runtime(lock=lock, tool=tool)
                    if tool == "degap":
                        verify_engine(Path(__file__).with_name("degap_core"))
                seeds = layout.path(state["receipt"]).parent
                prepared = verify_prepared(seeds, batch, locus)
                tool_override = (manifest.get("tool_parameters") or {}).get(tool)
                return run_tool(layout, batch_dir, locus, tool, seeds, prepared, *checks[tool], budget, lock, runtimes[tool],
                                tool_override=tool_override)
            try:
                row, patch_file = execute_one()
            except ReadsUnavailable as exc:
                row, patch_file = output_row(locus, tool, "missing_reads", reason=str(exc)), None
            except (OSError, ValueError, KeyError, TypeError, ToolError) as exc:
                print(f"[MANUAL REFINEMENT] {locus['id']} {tool}: {exc}", file=sys.stderr, flush=True)
                row, patch_file = output_row(locus, tool, "failed", reason="runtime_or_input_check_failed"), None
            rows.append(row)
            if patch_file is not None:
                patches[row["patch"]["path"]] = patch_file
    reads = {tool: checked[1]
             for tool, checked in checks.items()}
    return publish_results(layout, batch_dir, batch, rows, patches, manifest=manifest, reads=reads)
