#!/usr/bin/env python3
"""DEGAP task runner and provenance-preserving App candidate delivery.

Adds candidates to Server metadata with rollback, never edits Final Path. Only known
mode outputs are collected, never arbitrary FASTA files found recursively.
"""
from __future__ import annotations

try:
    from workspace_layout import workspace_join, WorkspaceLayout, initialize_workspace
except ModuleNotFoundError:
    from .workspace_layout import workspace_join, WorkspaceLayout, initialize_workspace

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import zipfile
import uuid
from run_all_runner import WorkspaceLock, RunnerError

import add_ctg_stage as stage
import add_ctg_package as package
import track_member_order as ordering
import degap_manual_catalog as manual_catalog
from run_resources import execution_threads


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".degap-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def recipe_at(path):
    value = json.loads(Path(path).read_text())
    if value.get("schema") != "gpm.degap.export.v1" or not re.fullmatch(r"[0-9a-f]{64}", value.get("token", "")):
        raise ValueError("Invalid DEGAP task receipt")
    for key in ("out_path", "server_root"):
        if not Path(value[key]).is_absolute():
            raise ValueError(f"{key} must be an absolute Server path")
    for key in ("target_chr", "target_track"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value[key]) or value[key] in (".", ".."):
            raise ValueError(f"Unsafe {key}: {value[key]}")
    return value


def safe_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"Unsafe relative path: {relative}")
    path = workspace_join(root, relative)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path leaves root: {relative}")
    return path


def input_identity(recipe):
    return {k: v for k, v in recipe.items() if k not in ("token", "project_id")}


def seed_hashes(recipe):
    out = Path(recipe["out_path"])
    names = ("endpoint.ctg.fa",) if recipe["job_type"] == "telseeker_ctg" else ("seqleft.fa", "seqright.fa")
    return {name: digest(out / name) for name in names}


def begin(recipe):
    out = Path(recipe["out_path"])
    marker = out / ".gpm_degap_inputs.json"
    if marker.exists():
        if json.loads(marker.read_text()) != input_identity(recipe):
            raise ValueError("DEGAP output directory belongs to different inputs/settings; choose a new output directory")
    elif any(out.glob("*.final.fa")) or (out / "result/status.tsv").exists():
        raise ValueError("Existing DEGAP results have no matching GPM provenance; choose a new output directory")
    atomic_json(marker, input_identity(recipe))
    (out / ".gpm_degap_result.json").unlink(missing_ok=True)
    (out / ".gpm_degap_seed.json").unlink(missing_ok=True)
    (out / ".gpm_degap_source_proof.json").unlink(missing_ok=True)


def output_signatures(recipe):
    out = Path(recipe["out_path"])
    paths = ([out / f"{out.name}.final.fa", out / f"{out.name}.direct.final.fa"]
             if recipe["job_type"] == "gapfiller" else
             [out / "telseeker_ctg.jobs" / f"endpoint.{recipe['endpoint_end']}" / "result/extended.ctg.fa"])
    return {p.relative_to(out).as_posix(): {"size": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns,
                                           "sha256": digest(p)} for p in paths if p.is_file()}


def seed(recipe):
    hashes = seed_hashes(recipe)
    source_proof = None
    if "seed_plans" in recipe:
        source_proof = json.loads((Path(recipe["out_path"]) / ".gpm_degap_source_proof.json").read_text())
        if (source_proof.get("schema") != "cgat.degap-seed-sources" or source_proof.get("schema_version") != 1
                or source_proof.get("token") != recipe["token"] or set(source_proof.get("labels", {})) != set(recipe["seed_plans"])):
            raise ValueError("exported seed plans lack matching resolved source proofs")
        for label, plan in recipe["seed_plans"].items():
            proof = source_proof["labels"][label]
            name = "endpoint.ctg.fa" if label == "endpoint" else label + ".fa"
            if proof.get("plan") != plan or proof.get("seed_sha256") != hashes[name]:
                raise ValueError("resolved DEGAP seed changed before native execution")
    atomic_json(Path(recipe["out_path"]) / ".gpm_degap_seed.json", {
        "token": recipe["token"], "sha256": hashes, "previous_outputs": output_signatures(recipe),
        "source_proof": source_proof})


def candidate(recipe):
    out = Path(recipe["out_path"])
    if recipe["job_type"] == "gapfiller":
        candidates = [p for p in (out / f"{out.name}.direct.final.fa", out / f"{out.name}.final.fa")
                      if p.is_file() and p.stat().st_size]
        if len(candidates) != 1:
            raise ValueError(f"Expected exactly one GapFiller final candidate, found {len(candidates)} in {out}")
        return candidates[0], "candidate"  # A final sequence is not proof of gap closure.
    if recipe["job_type"] != "telseeker_ctg":
        raise ValueError("Unsupported DEGAP job type")
    status = out / "result/status.tsv"
    with status.open(newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(rows) != 1 or rows[0].get("ctg_id") != "endpoint" or rows[0].get("end") != recipe["endpoint_end"]:
        raise ValueError("TelSeeker result does not match the requested endpoint")
    if rows[0].get("status") != "success":
        return None, rows[0].get("stop_reason", "no_candidate")
    return out / "telseeker_ctg.jobs" / f"endpoint.{recipe['endpoint_end']}" / "result/extended.ctg.fa", "candidate"


def record(recipe):
    out = Path(recipe["out_path"])
    if json.loads((out / ".gpm_degap_inputs.json").read_text()) != input_identity(recipe):
        raise ValueError("DEGAP input provenance changed during this run")
    seed_record = json.loads((out / ".gpm_degap_seed.json").read_text())
    if seed_record.get("token") != recipe["token"]:
        raise ValueError("DEGAP seed snapshot does not belong to this run")
    settings = recipe.get("settings", {})
    custom = settings.get("degap_path", "")
    if custom:
        runtime = {"kind": "custom", "path": custom, "sha256": digest(custom)}
    else:
        runtime_source = Path(__file__).resolve().parent / "degap_core/SOURCE.json"
        runtime = {"kind": "bundled", "revision": json.loads(runtime_source.read_text())["revision"],
                   "source_sha256": digest(runtime_source)}
    result, status = candidate(recipe)
    entry = {"recipe": recipe, "status": status, "seed_sha256": seed_record["sha256"], "runtime": runtime}
    if "seed_plans" in recipe:
        proof = seed_record.get("source_proof")
        if (seed_hashes(recipe) != seed_record["sha256"] or not isinstance(proof, dict) or proof.get("token") != recipe["token"]
                or json.loads((out / ".gpm_degap_source_proof.json").read_text()) != proof):
            raise ValueError("DEGAP seed/source proof changed during native execution")
        entry["source_proof"] = seed_record["source_proof"]
    if result is not None:
        key = result.relative_to(out).as_posix()
        if key in seed_record["previous_outputs"] and seed_record["previous_outputs"][key] == output_signatures(recipe).get(key):
            raise ValueError("DEGAP did not produce a new candidate in this run; use the existing result package instead of admitting a stale FASTA")
        records = stage.read_fasta_records(result)
        if len(records) != 1 or not records[0][1] or not re.fullmatch(r"[ACGTRYSWKMBDHVNacgtryswkmbdhvn]+", records[0][1]):
            raise ValueError(f"Invalid single-sequence candidate: {result}")
        saved = out / ".gpm_degap_candidate.fa"
        # Immutable-to-collector snapshot; its hash is verified again before packaging.
        stage.write_single_record_fasta(saved, "degap_candidate", records[0][1])
        entry.update({"fasta": saved.name, "sha256": digest(saved)})
    atomic_json(out / ".gpm_degap_result.json", entry)


def recipes(jobs):
    with jobs.open(newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise ValueError("No DEGAP tasks in jobs.tsv")
    result = []
    seen = set()
    outputs = set()
    for row in rows:
        script = safe_path(jobs.parent, row["script_path"])
        recipe = recipe_at(script.with_suffix(".json"))
        if recipe["token"] in seen or row["job_id"] != recipe["job_id"] or row["out_path"] != recipe["out_path"]:
            raise ValueError("Duplicate or mismatched task in jobs.tsv")
        output = Path(recipe["out_path"]).resolve()
        if output in outputs:
            raise ValueError("Multiple DEGAP tasks share one output directory")
        outputs.add(output)
        seen.add(recipe["token"])
        result.append((script, recipe))
    return result


def seed_stage(server, target, selected, *, owner_root=None):
    """Copy mutable metadata, link immutable alignment inputs; never write through links."""
    owner_root = Path(owner_root or server).resolve()
    if WorkspaceLayout.detect(server).version == 2:
        initialize_workspace(target)
    shutil.copytree(workspace_join(server, "metadata"), workspace_join(target, "metadata"))
    paths = {row["fasta_relpath"] for row in stage.read_tsv(workspace_join(server, "metadata/reference_chr_locator.tsv"))[0]}
    # Prior manual candidates remain source-addressable after another collection;
    # aggregates alone are not substitutes for their unique source locators.
    paths.update(row["fasta_relpath"] for row in stage.read_tsv(workspace_join(server, "metadata/source_seq_locator.tsv"))[0]
                 if row["dataset_name"] == stage.DERIVED_DATASET)
    for recipe in selected:
        for dataset in stage.chr_dataset_names(server, recipe["target_chr"]):
            paths.add(f"runs/chr_{recipe['target_chr']}/datasets/{dataset}.fa")
    # Existing derived aggregates can be appended by add_ctg_stage, so copy them.
    paths.add("data/datasets/derived_ctg.fa")
    for recipe in selected:
        paths.add(f"runs/chr_{recipe['target_chr']}/datasets/derived_ctg.fa")
    for relative in paths:
        relative = str(relative)
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Unsafe alignment input: " + relative)
        original = workspace_join(server, relative)
        if not original.resolve().is_relative_to(owner_root):
            raise ValueError("Alignment input leaves the owned Server workspace: " + relative)
        if not original.is_file():
            if original.name == "derived_ctg.fa":
                continue
            raise ValueError(f"Missing alignment input: {original}")
        dest = workspace_join(target, relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.name == "derived_ctg.fa":
            shutil.copy2(original, dest)
        else:
            dest.symlink_to(original.resolve())


def zip_directory(root, output):
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())


def publish(staged, server, archives, temporary_zip, output):
    """Back up changed targets before publishing; immutable alignment links are skipped."""
    changes = []
    for path in sorted(staged.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(staged)
        if relative.parts[0] not in ("metadata", "data", "runs"):
            raise ValueError(f"Unexpected staged candidate path: {relative}")
        destination = server / relative
        if destination.is_symlink():
            raise ValueError(f"Refusing to overwrite a symlink: {destination}")
        if path.suffix == ".sh":
            path.write_text(path.read_text().replace(str(staged), str(server)))
        if not destination.exists() or digest(path) != digest(destination):
            changes.append((path, destination))
    changes.extend(archives)
    changes.append((Path(temporary_zip), output))
    backup_root = Path(tempfile.mkdtemp(prefix="degap-publish-", dir=server / ".run_all"))
    journal = []
    try:
        for index, (source, destination) in enumerate(changes):
            if destination.is_symlink() or any(p.is_symlink() for p in destination.parents):
                raise ValueError(f"Refusing publication through a symlink: {destination}")
            backup = backup_root / str(index)
            if destination.exists():
                shutil.copy2(destination, backup)
            journal.append({"target": str(destination), "backup": str(backup) if backup.exists() else None})
        atomic_json(backup_root / "journal.json", {"status": "prepared", "files": journal})
        for source, destination in changes:
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".degap-publish-", dir=destination.parent)
            os.close(fd)
            try:
                shutil.copy2(source, temporary)
                os.replace(temporary, destination)
            finally:
                Path(temporary).unlink(missing_ok=True)
        atomic_json(backup_root / "journal.json", {"status": "complete", "files": journal})
    except BaseException:
        for item in reversed(journal):
            target = Path(item["target"])
            if item["backup"]:
                shutil.copy2(item["backup"], target)
            else:
                target.unlink(missing_ok=True)
        atomic_json(backup_root / "journal.json", {"status": "rolled_back", "files": journal})
        raise
    print(f"Server candidate publication backup: {backup_root}")


def collect(jobs):
    tasks = recipes(jobs)
    roots = {r["server_root"] for _, r in tasks}
    if len(roots) != 1:
        raise ValueError("A result collection must belong to one Server project")
    server = Path(next(iter(roots))).resolve()
    for name in ("prepare_options.tsv", "source_seq_locator.tsv", "reference_chr_locator.tsv"):
        if not workspace_join(server, "metadata", name).is_file():
            raise ValueError(f"Not a prepared Server project: missing metadata/{name}")
    lock = WorkspaceLock(server, "degap-collect-" + uuid.uuid4().hex)
    lock.acquire()
    try:
        if WorkspaceLayout.detect(server).version == 2:
            manual_catalog.recover(server, lock)
        return collect_locked(jobs, lock=lock)
    finally:
        lock.release()


def collect_locked(jobs, *, lock=None):
    tasks = recipes(jobs)
    roots = {r["server_root"] for _, r in tasks}
    if len(roots) != 1:
        raise ValueError("A result collection must belong to one Server project")
    server = Path(next(iter(roots))).resolve()
    entries, notes, receipt_bindings = [], [], []
    for _, recipe in tasks:
        path = Path(recipe["out_path"]) / ".gpm_degap_result.json"
        if not path.exists():
            notes.append({"job_id": recipe["job_id"], "status": "not_completed"})
            continue
        receipt_bytes = path.read_bytes()
        entry = json.loads(receipt_bytes)
        receipt_bindings.append((path, hashlib.sha256(receipt_bytes).hexdigest()))
        if entry.get("recipe") != recipe:
            raise ValueError(f"Stale result receipt: {recipe['job_id']}")
        if entry["status"] != "candidate":
            notes.append({"job_id": recipe["job_id"], "status": entry["status"]})
            continue
        fasta = safe_path(Path(recipe["out_path"]), entry["fasta"])
        if digest(fasta) != entry["sha256"]:
            raise ValueError(f"Candidate checksum changed: {fasta}")
        entries.append((recipe, fasta, entry))
    if not entries:
        raise ValueError("No completed DEGAP candidates to import; inspect job logs/status.tsv")
    output = jobs.parent / "degap_results.zip"
    numbered = WorkspaceLayout.detect(server).version == 2
    if numbered:
        catalog, catalog_manifest, catalog_pointer = manual_catalog.current(server)
        published_root = manual_catalog.new_path(server)
        package_registry = dict(catalog_manifest["packages"])
    else:
        catalog, published_root = server, server
    with tempfile.TemporaryDirectory(prefix="gpm-degap-collect-") as temporary:
        root = Path(temporary)
        staged, delivery = workspace_join(root, "stage"), workspace_join(root, "delivery")
        seed_stage(catalog, staged, [r for r, _, _ in entries], owner_root=server)
        input_links = ({name: row for name, row in manual_catalog.inventory(staged, server).items() if "link" in row}
                       if numbered else {})
        if numbered:
            options_path = workspace_join(staged, "metadata/prepare_options.tsv")
            options = stage.read_key_values(options_path)
            options["threads"] = str(execution_threads(int(options.get("threads", "10")), root=server))
            stage.write_tsv(options_path, ["key", "value"], [{"key": key, "value": value} for key, value in options.items()])
        (delivery / "packages").mkdir(parents=True)
        results = []
        cache_updates = []
        for index, (recipe, fasta, run_receipt) in enumerate(entries):
            name = "degap_" + recipe["token"][:24]
            registered = package_registry.get(recipe["token"]) if numbered else None
            if registered:
                cached_archive, cached_info = manual_catalog.package_paths(server, registered)
                cache = cached_archive.with_suffix("")
            else:
                cache = workspace_join(staged if numbered else server, ".run_all/degap_packages", recipe["token"])
                cached_info = cache.with_suffix(".json")
            archive = delivery / "packages" / f"{recipe['token']}.zip"
            if cached_info.exists():
                info = json.loads(cached_info.read_text())
                if info["recipe"] != recipe or info["sha256"] != digest(cache.with_suffix(".zip")):
                    raise ValueError("Published DEGAP candidate cache has changed")
                if info.get("candidate_sha256") != digest(fasta):
                    raise ValueError("A published task now has different sequence content; export a new task before publishing it")
                shutil.copy2(cache.with_suffix(".zip"), archive)
                results.append(info)
                continue
            args = SimpleNamespace(server_dir=str(staged), ctg=name, chr=recipe["target_chr"],
                                   track=recipe["target_track"], input=str(fasta),
                                   source="DEGAP:" + recipe["token"] + ":" + recipe["job_id"])
            stage.command_prepare(args)
            commands = [workspace_join(staged, "runs/add_ctg", f"{name}_vs_ref/command.sh")]
            commands += sorted(workspace_join(staged, "runs", f"chr_{recipe['target_chr']}", "add_ctg").glob(f"*_vs_{name}/command.sh"))
            for command in commands:
                subprocess.run(["bash", str(command)], check=True)
            stage.command_finalize(args)
            order_path, rows = ordering.build_member_rows(staged)
            ordering.write_atomic_tsv(order_path, rows)
            package_dir = workspace_join(root, f"package-{index}")
            package.main(["add_ctg_package.py", str(staged), str(package_dir), name])
            archive = delivery / "packages" / f"{recipe['token']}.zip"
            for command in package_dir.rglob("*.sh"):
                command.write_text(command.read_text().replace(str(staged), str(published_root)))
            zip_directory(package_dir, archive)
            info = {"candidate_sha256": digest(fasta), "recipe": recipe,
                    "seed_sha256": run_receipt["seed_sha256"], "runtime": run_receipt["runtime"], "ctg_name": name,
                    "package": archive.relative_to(delivery).as_posix(), "sha256": digest(archive)}
            if "source_proof" in run_receipt:
                info["source_proof"] = run_receipt["source_proof"]
            results.append(info)
            info_path = workspace_join(root, f"cached-{index}.json")
            atomic_json(info_path, info)
            if numbered:
                cache.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(archive, cache.with_suffix(".zip"))
                shutil.copy2(info_path, cached_info)
                package_registry[recipe["token"]] = {
                    "archive": (published_root / cache.with_suffix(".zip").relative_to(staged)).relative_to(server).as_posix(),
                    "archive_sha256": digest(archive),
                    "info": (published_root / cached_info.relative_to(staged)).relative_to(server).as_posix(),
                    "info_sha256": digest(info_path)}
            else:
                cache_updates.extend([(archive, cache.with_suffix(".zip")), (info_path, cached_info)])
        for path, expected in receipt_bindings:
            if digest(path) != expected:
                raise ValueError("DEGAP result receipt changed during collection")
        if any(digest(fasta) != receipt["sha256"] for _, fasta, receipt in entries):
            raise ValueError("DEGAP candidate sequence changed during collection")
        if numbered:
            now = manual_catalog.inventory(staged, server)
            if any(now.get(name) != expected for name, expected in input_links.items()):
                raise ValueError("immutable alignment input changed during manual collection")
        atomic_json(delivery / "degap_results.json", {"schema": "gpm.degap.results.v1", "results": results, "notes": notes})
        # Write next to the destination so replacing the final archive is atomic.
        fd, temporary_zip = tempfile.mkstemp(prefix=".degap-results-", suffix=".zip", dir=jobs.parent)
        os.close(fd)
        try:
            zip_directory(delivery, Path(temporary_zip))
            if numbered:
                pointer = (manual_catalog.seal(server, staged, published_root, catalog_manifest["base"], package_registry)
                           if package_registry != catalog_manifest["packages"] else catalog_pointer)
                manual_catalog.publish(server, lock, pointer, temporary_zip, output)
                print(f"Manual candidates only; Final Path unchanged. Catalog: {server / pointer['catalog']}")
            else:
                publish(staged, server, cache_updates, temporary_zip, output)
        finally:
            Path(temporary_zip).unlink(missing_ok=True)
    print(f"App candidate package: {output} ({len(entries)} candidates, {len(notes)} without candidates)")
    return output


def run(jobs):
    tasks = recipes(jobs)
    subprocess.run(["bash", str(jobs.parent / "prepare_degap_shared.sh")], check=True)
    failed = []
    for script, recipe in tasks:
        if subprocess.run(["bash", str(script)]).returncode:
            failed.append(recipe["job_id"])
    collect(jobs)
    if failed:
        raise ValueError("Completed candidates packaged, but some jobs failed: " + ", ".join(failed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("begin", "seed", "record"):
        sub.add_parser(name).add_argument("--recipe", required=True, type=Path)
    for name in ("run", "collect"):
        sub.add_parser(name).add_argument("--jobs", required=True, type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("terminated")))
    try:
        if args.action in ("begin", "seed", "record"):
            globals()[args.action](recipe_at(args.recipe))
        else:
            globals()[args.action](args.jobs.resolve())
    except (ValueError, OSError, subprocess.CalledProcessError, RunnerError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
