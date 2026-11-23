"""Content-bound measurements of accepted patch sources, not a new native run."""
from __future__ import annotations

import csv
from collections import Counter
from contextlib import contextmanager
from itertools import chain
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid

try:
    from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, initialize_workspace, relative_path
    from workspace_migration import durable_json
    from degap_manual_catalog import content_digest, read_object
    from refinement_reports import safe_file
    from refinement_tools import fingerprint
    from refinement_sources import FastaCatalog
    from refinement_source_payload import write_source_fasta
    from refinement_source_marks import annotation_inputs, project, slices, table, SLICE_FIELDS, MARK_FIELDS
    from post_lgz_degap import IndexedFasta
    from annotation_library import verify_snapshot
    from lgz_core.q0_alignments import read_paf
    import tel_scan
    import cen_scan
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, initialize_workspace, relative_path
    from .workspace_migration import durable_json
    from .degap_manual_catalog import content_digest, read_object
    from .refinement_reports import safe_file
    from .refinement_tools import fingerprint
    from .refinement_sources import FastaCatalog
    from .refinement_source_payload import write_source_fasta
    from .refinement_source_marks import annotation_inputs, project, slices, table, SLICE_FIELDS, MARK_FIELDS
    from .post_lgz_degap import IndexedFasta
    from .annotation_library import verify_snapshot
    from .lgz_core.q0_alignments import read_paf
    from . import tel_scan, cen_scan

SCHEMA = "cgat.refinement-source-evidence"
RECEIPT = "receipt.json"
PROJECTION = "metadata/refinement/source_evidence.json"
GENERATORS = ("refinement_source_evidence.py", "refinement_source_marks.py", "refinement_source_payload.py",
              "tel_scan.py", "cen_scan.py", "annotation_library.py", "workspace_layout.py", "refinement_sources.py",
              "refinement_path.py", "post_lgz_degap.py", "lgz_core/q0_alignments.py", "lgz_core/q0_sources.py", "lgz_core/common.py")



class SourceEvidenceError(ValueError):
    def __init__(self, message, diagnostics):
        super().__init__(message + "; retained source diagnostics: " + str(diagnostics))
        self.source_evidence_diagnostics = Path(diagnostics)


@contextmanager
def measurement_workspace(parent, recipe):
    work = Path(tempfile.mkdtemp(prefix=".measure-", dir=parent))
    preserve = False
    try:
        yield work
    except BaseException as error:
        preserve = True
        indexes = work / "indexes"
        if indexes.is_symlink() or indexes.is_file():
            indexes.unlink()
        elif indexes.is_dir():
            shutil.rmtree(indexes)
        if (work / RECEIPT).exists():
            (work / RECEIPT).rename(work / "completion.rejected.json")
        try:
            files, diagnostic_error = inventory(work), None
        except (OSError, ValueError) as diagnostic:
            files, diagnostic_error = {}, str(diagnostic)
        durable_json(work / "failure.json", {"schema": SCHEMA + "-failure", "schema_version": 1,
                     "status": "failed" if isinstance(error, Exception) else "interrupted", "recipe": recipe,
                     "error_type": type(error).__name__, "error": str(error), "files": files,
                     "diagnostics_error": diagnostic_error})
        failed = parent / ("failed-" + fingerprint(recipe)[:20] + "-" + uuid.uuid4().hex)
        work.rename(failed)
        if isinstance(error, Exception):
            raise SourceEvidenceError(str(error), failed) from error
        error.source_evidence_diagnostics = failed
        raise
    finally:
        if not preserve and work.exists():
            shutil.rmtree(work)


def run_job(path, record, execute):
    record = {**record, "status": "running"}
    durable_json(path, record)
    started = time.monotonic()
    try:
        execute()
        record["status"] = "success"
    except BaseException as error:
        record.update(status="failed" if isinstance(error, Exception) else "interrupted",
                      error_type=type(error).__name__, error=str(error))
        raise
    finally:
        record["seconds"] = max(0, time.monotonic() - started)
        durable_json(path, record)
    return record

def write_table(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def binding(path):
    path = Path(path).absolute()
    resolved = path.resolve(strict=True)
    result = {"path": str(path), "resolved": str(resolved), "sha256": content_digest(resolved)}
    if path.resolve(strict=True) != resolved:
        raise ValueError("source evidence input link changed")
    return result


FINAL_INPUTS = ("provenance.json", "final_path.json", "sources.tsv")


def measurement_input(row, recipe, layout=None):
    """Only a reclaimed, run-owned final stage can be substituted by its proven publication."""
    path = Path(row["path"])
    if path.exists() or path.is_symlink() or layout is None or not layout.project_delivery:
        if binding(path) != row:
            raise ValueError("source evidence input changed: " + str(path))
        return path.resolve(strict=True)
    tool, run = recipe["tool"], recipe["run_id"]
    if tool not in TOOL_DIRECTORIES or not re.fullmatch("[a-f0-9]{32}", run):
        raise ValueError("invalid measurement producer identity")
    stage = layout.path(f".runtime/refinement/{TOOL_DIRECTORIES[tool]}/{run}/final")
    if (path.parent != stage or path.name not in FINAL_INPUTS or row["resolved"] != str(path)
            or stage.exists() or stage.is_symlink()):
        raise ValueError("missing source evidence input (not a reclaimed final stage): " + str(path))
    try:
        from refinement_commit import current_publication, targets, committed_final_history
    except ModuleNotFoundError:
        from .refinement_commit import current_publication, targets, committed_final_history
    current = current_publication(layout.root, tool, verify=False)
    if current:
        live = (targets(layout, tool)["final"], current["areas"]["final"]["new"]["files"])
        for directory, files in chain([live], committed_final_history(layout, tool)):
            if files.get("provenance.json") != recipe["provenance_sha256"] or files.get(path.name) != row["sha256"]:
                continue
            provenance = safe_file(directory, "provenance.json")
            if content_digest(provenance) != recipe["provenance_sha256"]:
                raise ValueError("published measurement provenance changed")
            record = read_object(provenance)
            resolved = safe_file(directory, path.name)
            if (record["tool"] != tool or record["run_id"] != run or record["execution"]["status"] != "success"
                    or content_digest(resolved) != row["sha256"]):
                raise ValueError("published measurement input does not match its producer")
            return resolved
    raise ValueError("no committed replacement for measurement input: " + str(path))


def verify_inputs(recipe, root=None):
    layout = WorkspaceLayout.detect(root) if root is not None else None
    for row in recipe["inputs"]:
        measurement_input(row, recipe, layout)
    for name, row in recipe["tools"].items():
        found = shutil.which(name)
        if found is None or str(Path(found).resolve()) != row["resolved"] or binding(found)["sha256"] != row["sha256"]:
            raise ValueError("source evidence executable changed: " + name)
    if generator_hashes() != recipe["generators"]:
        raise ValueError("source evidence helper changed during measurement")


def generator_hashes():
    return {name: content_digest(Path(__file__).parent / name) for name in GENERATORS}


def inventory(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("source evidence contains a link or special file")
        name = path.relative_to(directory).as_posix()
        if path.is_file() and name != RECEIPT:
            result[name] = content_digest(path)
    return result


def load(directory, *, recipe=None):
    directory = Path(directory)
    receipt = read_object(safe_file(directory, RECEIPT))
    if (receipt.get("schema") != SCHEMA or receipt.get("schema_version") != 1
            or receipt.get("generation_sha256") != fingerprint(receipt.get("recipe"))
            or recipe is not None and receipt["recipe"] != recipe or inventory(directory) != receipt.get("files")):
        raise ValueError("source evidence generation is incomplete or changed: " + str(directory))
    for row in receipt["payload"]:
        if receipt["files"].get(relative_path(row["file"])) != row["sha256"]:
            raise ValueError("source evidence delivery member changed")
        relative_path(row["package_path"])
    return receipt


def context(root, result, threads):
    layout = WorkspaceLayout.detect(root)
    tool, run_id = result["tool"], result["run_id"]
    if layout.version != 2 or tool not in TOOL_DIRECTORIES or re.fullmatch(r"[0-9a-f]{32}", run_id) is None or type(threads) is not int or threads < 1:
        raise ValueError("source evidence requires a completed numbered refinement and positive thread budget")
    final = Path(result["staging"]).resolve()
    if not final.is_relative_to(layout.root):
        raise ValueError("accepted source evidence is outside its workspace")
    paths = [safe_file(final, name) for name in ("provenance.json", "final_path.json", "sources.tsv")]
    provenance = read_object(paths[0])
    marker = safe_file(layout.root, layout.relative(f"04_refinement/{TOOL_DIRECTORIES[tool]}/02_jobs/{run_id}/invocation.json"))
    state = read_object(marker)
    if (provenance.get("schema") != "cgat.refinement-publication" or provenance.get("schema_version") != 1
            or provenance.get("tool") != tool or provenance.get("run_id") != run_id
            or provenance.get("execution", {}).get("status") != "success"
            or state.get("status") not in {"staged", "published"} or state.get("tool") != tool or state.get("run_id") != run_id
            or state.get("provenance_sha256") != content_digest(paths[0])):
        raise ValueError("source evidence requires sealed successful accepted refinement")
    for path in paths[1:]:
        if content_digest(path) != provenance["artifacts"][path.name]:
            raise ValueError("accepted source evidence input changed")
    accepted = read_object(paths[1])
    source_rows = table(paths[2])
    known, patches = {}, []
    for row in source_rows:
        key = row["dataset"], row["contig"]
        row["length"] = int(row["length"])
        if key in known or row["length"] < 1:
            raise ValueError("invalid accepted source catalog")
        known[key] = row
        if row["origin"].startswith("refinement:"):
            if row["path_scope"] == "workspace":
                path = layout.path(relative_path(row["fasta_path"]))
            elif row["path_scope"] == "external" and Path(row["fasta_path"]).is_absolute():
                path = Path(row["fasta_path"])
            else:
                raise ValueError("invalid accepted patch source location")
            if content_digest(path) != row["fasta_sha256"]:
                raise ValueError("accepted patch source content changed")
            paths.append(path)
            patches.append(row)
    chromosomes = [row["chr"] for row in accepted["chromosomes"]]
    for name in [*chromosomes, *(row["dataset"] for row in patches)]:
        tel_scan.output_name(name)
    original_marks = annotation_inputs(root, chromosomes)
    paths.extend(row["path"] for row in original_marks)
    options_path = layout.path("metadata/prepare_options.tsv")
    options = {row["key"]: row["value"] for row in table(options_path)} if options_path.exists() else {}
    if options_path.exists():
        paths.append(options_path)
    preset = options.get("minimap_preset", "asm10")
    if preset not in {"asm5", "asm10", "asm20"}:
        raise ValueError("unsupported prepared source-reference minimap preset")
    reference = layout.path("metadata/reference.tsv")
    ref_rows = table(reference)
    if len(ref_rows) != 1:
        raise ValueError("source evidence requires exactly one original reference catalog")
    ref = layout.path(relative_path(ref_rows[0]["fasta_relpath"]))
    paths.extend((reference, ref))
    frozen = {}
    for name in ("tel/rules.tsv", "cen/reference.tsv", "cen/library.fa", "metadata/annotation_library_snapshot.json"):
        path = layout.path(name)
        if path.exists() or path.is_symlink():
            frozen[name] = path
            paths.append(path)
    verify_snapshot(root)
    if any(options.get(kind + "_enabled", "false") not in {"true", "false"} for kind in ("tel", "cen")):
        raise ValueError("invalid prepared annotation enable setting")
    enabled = {kind: options.get(kind + "_enabled", "true" if name in frozen else "false") == "true"
               for kind, name in (("tel", "tel/rules.tsv"), ("cen", "cen/reference.tsv"))}
    if any(enabled[kind] and name not in frozen for kind, name in (("tel", "tel/rules.tsv"), ("cen", "cen/reference.tsv"))):
        raise ValueError("enabled source annotation is missing its prepared rules")
    cen_entries = table(frozen["cen/reference.tsv"]) if enabled["cen"] else []
    commands = {"samtools", "minimap2"} if patches else set()
    if patches and enabled["cen"] and any(row.get("chr_name") in {"*", *chromosomes} for row in cen_entries):
        commands.update(("nucmer", "show-coords"))
    tools = {}
    for name in sorted(commands):
        value = shutil.which(name)
        if not value:
            raise ValueError("required source evidence tool is missing: " + name)
        tools[name] = binding(value)
    recipe = {"schema": "cgat.refinement-source-evidence-recipe", "schema_version": 1, "tool": tool, "run_id": run_id,
              "provenance_sha256": content_digest(paths[0]), "threads": threads, "preset": preset,
              "preset_source": "prepared_options" if "minimap_preset" in options else "legacy_default_asm10",
              "alignment_policy": {"cigar": True, "cs": "long", "secondary": True, "batch_bases": "1G",
                                   "status": "actual_alignment_presence_not_assignment_or_accuracy"},
              "annotation_policy": "frozen-source-scans-and-clipped-final-coordinate-projection-not-final-genome-rescan",
              "annotation_enabled": enabled,
              "annotation_rule_counts": {"tel": len(table(frozen["tel/rules.tsv"])) if enabled["tel"] else 0, "cen": len(cen_entries)},
              "snapshot": "prepared_content_snapshot" if "metadata/annotation_library_snapshot.json" in frozen else "legacy_prepared_without_library_snapshot",
              "annotation_files": {name: content_digest(path) for name, path in frozen.items()},
              "reference_sha256": content_digest(ref),
              "patch_sources": [{key: row[key] for key in ("dataset", "contig", "length", "fasta_sha256")} for row in patches],
              "inputs": [binding(path) for path in sorted(set(paths), key=str)], "tools": tools, "generators": generator_hashes()}
    # Keep the same run-specific receipt identity after publication reclaims its identical
    # staging tree. A live public name alone cannot stand in for this producer and checksum.
    if layout.project_delivery and final == layout.path(f"05_final/{TOOL_DIRECTORIES[tool]}"):
        stage = layout.path(f".runtime/refinement/{TOOL_DIRECTORIES[tool]}/{run_id}/final")
        for row in recipe["inputs"]:
            path = Path(row["path"])
            if path.parent == final and path.name in FINAL_INPUTS:
                row["path"] = row["resolved"] = str(stage / path.name)
                measurement_input(row, recipe, layout)
        recipe["inputs"].sort(key=lambda row: row["path"])
    return layout, accepted, known, patches, ref, frozen, cen_entries, original_marks, recipe


def build(root, result, threads):
    root = Path(root).resolve()
    layout, accepted, known, patches, reference, frozen, cen_entries, original_marks, recipe = context(root, result, threads)
    key = fingerprint(recipe)
    home = layout.path(f"04_refinement/{TOOL_DIRECTORIES[result['tool']]}/04_accepted/{result['run_id']}/01_source_evidence/{key}")
    if home.exists() or home.is_symlink():
        receipt = load(home, recipe=recipe)
        verify_inputs(recipe, root)
        return {"directory": str(home), "receipt_sha256": content_digest(home / RECEIPT), "generation_sha256": key}
    home.parent.mkdir(parents=True, exist_ok=True)
    with measurement_workspace(home.parent, recipe) as work:
        catalog = FastaCatalog(root, work / "indexes/patches")
        datasets = {}
        for row in patches:
            source = layout.path(row["fasta_path"]) if row["path_scope"] == "workspace" else Path(row["fasta_path"])
            catalog.register(row["dataset"], row["contig"], source, origin=row["origin"])
            if catalog.length(row["dataset"], row["contig"]) != row["length"]:
                raise ValueError("accepted patch record length differs from its source catalog")
            datasets.setdefault(row["dataset"], []).append(row)
        payload, statuses, jobs = [], [], []
        def deliver(path, package_path, *, merge=False):
            payload.append({"file": path.relative_to(work).as_posix(), "package_path": package_path,
                            "sha256": content_digest(path), "merge_tsv": merge})
        hits_by_source = {}
        if patches:
            ref_index = IndexedFasta(reference, work / "indexes/reference.fa")
            ref_lengths = {name: row[0] for name, row in ref_index.records.items()}
            for dataset, rows in sorted(datasets.items()):
                query = work / "01_sources" / (fingerprint(dataset)[:24] + ".fa")
                write_source_fasta(query, rows, catalog)
                run = work / "02_reference" / (dataset + "_vs_ref")
                run.mkdir(parents=True)
                command = [recipe["tools"]["minimap2"]["resolved"], "-x", recipe["preset"], "-c", "--cs=long", "--secondary=yes",
                           "-K", "1G", "-t", str(threads), str(reference), str(query)]
                record = {"kind": "source_reference_alignment", "dataset": dataset, "command": command, "cwd": str(Path.cwd()),
                          "validation": "pending", "query_sha256": content_digest(query), "reference_sha256": content_digest(reference),
                          "executable": recipe["tools"]["minimap2"]}
                def align():
                    with (run / "result.paf").open("w") as output, (run / "stderr.log").open("w") as log:
                        subprocess.run(command, check=True, stdout=output, stderr=log)
                record = run_job(run / "command.json", record, align)
                version = subprocess.run([command[0], "--version"], capture_output=True, text=True, check=True)
                (run / "tool_version.txt").write_text(version.stdout + version.stderr)
                count = 0
                for hit in read_paf(run / "result.paf", query_lengths={row["contig"]: row["length"] for row in rows}, target_lengths=ref_lengths):
                    hits_by_source.setdefault((dataset, hit.query_name), Counter())[hit.target_name] += 1
                    count += 1
                record.update(validation="validated", paf_rows=count)
                durable_json(run / "command.json", record)
                jobs.append(record)
                for filename in ("result.paf", "stderr.log", "tool_version.txt", "command.json"):
                    deliver(run / filename, "runs/" + dataset + "_vs_ref/" + filename)
        view = work / "03_annotations/workspace"
        annotation_layout = initialize_workspace(view)
        for relative, source in frozen.items():
            target = annotation_layout.path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        all_marks = list(original_marks)
        usages = {}
        for row in slices(accepted):
            usages.setdefault((row["dataset"], row["contig"]), set()).add(row["chromosome"])
        for chromosome in [row["chr"] for row in accepted["chromosomes"]]:
            selected = []
            for dataset, rows in sorted(datasets.items()):
                used = [row for row in rows if chromosome in usages.get((dataset, row["contig"]), set())]
                if used:
                    fasta = work / "03_annotations/inputs" / fingerprint(chromosome)[:24] / (fingerprint(dataset)[:24] + ".fa")
                    write_source_fasta(fasta, used, catalog)
                    selected.append(dataset + "=" + str(fasta))
            if not selected:
                continue
            enabled = recipe["annotation_enabled"]
            scan_jobs = work / "03_annotations/jobs" / fingerprint(chromosome)[:24]
            if enabled["tel"]:
                record = {"kind": "tel_source_scan", "method": "tel_scan.scan",
                          "arguments": {"root": str(view), "chr": chromosome, "datasets": selected},
                          "annotation_availability": "scanned" if recipe["annotation_rule_counts"]["tel"] else "no_rules",
                          "helper_sha256": recipe["generators"]["tel_scan.py"]}
                record = run_job(scan_jobs / "tel_scan.json", record, lambda: tel_scan.scan(view, chromosome, selected))
                jobs.append(record)
                deliver(scan_jobs / "tel_scan.json", "metadata/refinement/source_jobs/" + fingerprint(chromosome)[:24] + "/tel_scan.json")
                for spec in selected:
                    dataset = spec.split("=", 1)[0]
                    path = annotation_layout.path("tel/chr_" + chromosome + "/" + dataset + ".tsv")
                    deliver(path, "tel/chr_" + chromosome + "/" + dataset + ".tsv")
                    all_marks.append({"kind": "tel", "chromosome": chromosome, "path": path, "origin": "refinement_patch"})
            if enabled["cen"]:
                record = {"kind": "cen_source_scan", "method": "cen_scan.scan",
                          "arguments": {"root": str(view), "chr": chromosome, "datasets": selected, "threads": threads, "run_dir": str(scan_jobs)},
                          "annotation_availability": "scanned" if any(r.get("chr_name") in {"*", chromosome} for r in cen_entries) else "no_chr_library",
                          "helper_sha256": recipe["generators"]["cen_scan.py"]}
                record = run_job(scan_jobs / "cen_scan.json", record, lambda: cen_scan.scan(view, chromosome, selected, threads, scan_jobs))
                jobs.append(record)
                for diagnostic in sorted(scan_jobs.iterdir()):
                    if diagnostic.name == "cen_scan.json" or diagnostic.suffix == ".log" or diagnostic.name.endswith(".coords.tsv"):
                        deliver(diagnostic, "metadata/refinement/source_jobs/" + fingerprint(chromosome)[:24] + "/" + diagnostic.name)
                path = annotation_layout.path("cen/chr_" + chromosome + "/marks.tsv")
                deliver(path, "cen/chr_" + chromosome + "/marks.tsv", merge=True)
                all_marks.append({"kind": "cen", "chromosome": chromosome, "path": path, "origin": "refinement_patch"})
        for row in patches:
            for chromosome in sorted(usages.get((row["dataset"], row["contig"]), set())):
                hits = hits_by_source.get((row["dataset"], row["contig"]), {})
                total, on_chr = sum(hits.values()), hits.get(chromosome, 0)
                status = "no_hit" if not total else "other_chr_only" if not on_chr else "multi_hit" if total > 1 else "hit"
                annotations = {"tel": "disabled" if not recipe["annotation_enabled"]["tel"] else "scanned" if recipe["annotation_rule_counts"]["tel"] else "no_rules",
                               "cen": "disabled" if not recipe["annotation_enabled"]["cen"] else "scanned" if any(r.get("chr_name") in {"*", chromosome} for r in cen_entries) else "no_chr_library"}
                statuses.append({"dataset": row["dataset"], "contig": row["contig"], "chromosome": chromosome, "length": row["length"],
                                 "fasta_sha256": row["fasta_sha256"], "ref_alignment_status": status,
                                 "reference_hits": total, "hits_on_chromosome": on_chr, "annotations": annotations})
        source_slices, projected_marks = project(accepted, {key: row["length"] for key, row in known.items()}, all_marks)
        for filename, fields, rows in (("source_intervals.tsv", SLICE_FIELDS, source_slices), ("final_annotations.tsv", MARK_FIELDS, projected_marks)):
            target = work / "04_projection" / filename
            write_table(target, fields, rows)
            deliver(target, "metadata/refinement/" + filename)
        durable_json(work / "04_projection/summary.json", {"sources": statuses, "jobs": jobs, "final_annotation_rows": len(projected_marks),
                     "annotation_policy": recipe["annotation_policy"], "coordinate_domain": "source 1-based inclusive; final 0-based half-open"})
        deliver(work / "04_projection/summary.json", "metadata/refinement/source_summary.json")
        catalog.verify_unchanged()
        verify_inputs(recipe, root)
        shutil.rmtree(work / "indexes")
        receipt = {"schema": SCHEMA, "schema_version": 1, "generation_sha256": key, "recipe": recipe,
                   "sources": statuses, "payload": payload, "files": inventory(work)}
        durable_json(work / RECEIPT, receipt)
        load(work, recipe=recipe)
        if home.exists() or home.is_symlink():
            raise ValueError("source evidence destination appeared during measurement")
        work.rename(home)
    return {"directory": str(home), "receipt_sha256": content_digest(home / RECEIPT), "generation_sha256": key}
