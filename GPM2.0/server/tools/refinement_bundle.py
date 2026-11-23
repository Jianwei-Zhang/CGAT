"""Build the schema-5 App view of an actual admitted refined Final Path.

No tool runs, native whole-genome substitutions or fabricated reference hits.
The old LGZ projection supplies unchanged source views; this module explicitly
adds patch datasets and projects the authoritative accepted path over that view.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

try:
    from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, workspace_join, relative_path
    from run_orchestration import sha256_file as digest
    from refinement_tools import fingerprint
    from refinement_reports import safe_file, read_bound
    from refinement_path import write_assembly, segment_blocks, inspect_baseline
    from refinement_sources import FastaCatalog
    from refinement_source_payload import write_source_fasta
    from post_lgz_degap import IndexedFasta
    import lgz_app_package
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, workspace_join, relative_path
    from .run_orchestration import sha256_file as digest
    from .refinement_tools import fingerprint
    from .refinement_reports import safe_file, read_bound
    from .refinement_path import write_assembly, segment_blocks, inspect_baseline
    from .refinement_sources import FastaCatalog
    from .refinement_source_payload import write_source_fasta
    from .post_lgz_degap import IndexedFasta
    from . import lgz_app_package

PACKAGE_VERSION = "5"
PATH_VERSION = "4"
FINAL_FASTA = "data/refinement/final.fa"
MANIFEST = "metadata/refinement/manifest.json"
SERVER_PATH = "metadata/refinement/final_path.json"
SCHEMA = "cgat.refinement-app-delivery"
STRIP_SEGMENT = ("evidence_ids", "evidenceIds", "eventId", "source_card_key", "sourceCardKey")


class BundleError(ValueError):
    pass


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def read_table(path):
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        return list(reader.fieldnames or []), list(reader)


def write_table(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def project_path(server, baseline_view):
    projected = copy.deepcopy(server)
    projected.update(workflow=lgz_app_package.APP_WORKFLOW, schema_version=PATH_VERSION, q4_relpath=FINAL_FASTA)
    previous = {row["chr"]: row for row in baseline_view["chromosomes"]}
    retained, dropped = 0, 0
    for chromosome in projected["chromosomes"]:
        original = previous[chromosome["chr"]]
        known = {row["segment_id"]: row for row in original["segments"]}
        accepted = {}
        for segment in chromosome["segments"]:
            old = known.get(segment["segment_id"])
            if old and all(old.get(key) == segment.get(key) for key in ("kind", "length", "orientation", "source", "event_id")):
                accepted[segment["segment_id"]] = segment
            for key in STRIP_SEGMENT:
                segment.pop(key, None)
        evidence = [row for row in original.get("display_evidence", [])
                    if row["final_path_segment_id"] in accepted
                    and accepted[row["final_path_segment_id"]].get("event_id") == row["event_id"]]
        chromosome["display_evidence"] = evidence
        retained += len(evidence)
        dropped += len(original.get("display_evidence", [])) - len(evidence)
        chromosome["q4_length"] = chromosome.pop("length")
        chromosome["q4_sha256"] = chromosome.pop("sha256")
    return projected, {"retained": retained, "omitted_changed_or_split_segment": dropped,
                       "new_patch_alignments": "not_inferred", "coordinate_domain": "original source intervals"}


def verify_projection(server, projected):
    expected = copy.deepcopy(server)
    expected.update(workflow=lgz_app_package.APP_WORKFLOW, schema_version=PATH_VERSION, q4_relpath=FINAL_FASTA)
    actual = copy.deepcopy(projected)
    for row in expected["chromosomes"]:
        row["q4_length"], row["q4_sha256"] = row.pop("length"), row.pop("sha256")
        for segment in row["segments"]:
            for key in STRIP_SEGMENT:
                segment.pop(key, None)
    for row in actual["chromosomes"]:
        row.pop("display_evidence", None)
    if expected != actual:
        raise BundleError("App Final Path differs from the authoritative admitted Server path")


def close_source_payload(root, target, private):
    """Whitelist original sequence files and generate each locator's own FAI."""
    needed = set()
    for name in ("reference.tsv", "datasets.tsv", "reference_chr_locator.tsv", "source_seq_locator.tsv"):
        for row in read_table(target / "metadata" / name)[1]:
            for key in ("fasta_relpath", "fai_relpath"):
                if row.get(key):
                    needed.add(relative_path(row[key]))
    for name in sorted(needed):
        output = target / name
        if not output.is_file():
            source = WorkspaceLayout.detect(root).path(name)
            if not source.is_file():
                raise BundleError("original sequence payload is missing: " + name)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output)
    for path in list((target / "data").rglob("*")):
        if path.is_file() and path.relative_to(target).as_posix() not in needed:
            path.unlink()
    for relative in sorted({row["fasta_relpath"] for row in read_table(target / "metadata/source_seq_locator.tsv")[1]}):
        file = safe_file(target, relative)
        # Never use the complete dataset FAI's offsets for a chromosome partition.
        index_link = private / ("locator-" + fingerprint(relative) + ".fa")
        IndexedFasta(file, index_link)
        shutil.copyfile(Path(str(index_link) + ".fai"), Path(str(file) + ".fai"))
    (target / "metadata/degap_gapfill.json").unlink(missing_ok=True)

def _load_catalog(root, result, private):
    final_dir = Path(result["staging"]).resolve()
    layout = WorkspaceLayout.detect(root)
    if not final_dir.is_relative_to(root):
        raise BundleError("refinement staging is outside its workspace")
    provenance = json.loads((final_dir / "provenance.json").read_text())
    tool, run_id = result["tool"], result["run_id"]
    marker = json.loads(safe_file(root, f"04_refinement/{TOOL_DIRECTORIES[tool]}/02_jobs/{run_id}/invocation.json").read_text())
    if (marker.get("status") not in {"staged", "published"} or marker.get("tool") != tool or marker.get("run_id") != run_id
            or provenance.get("tool") != tool or provenance.get("run_id") != run_id
            or digest(final_dir / "provenance.json") != marker.get("provenance_sha256")
            or provenance.get("execution", {}).get("status") != "success"):
        raise BundleError("refinement bundle requires a completed content-bound attempt")
    for name, expected in provenance["artifacts"].items():
        if digest(safe_file(final_dir, name)) != expected:
            raise BundleError("admitted refinement artifact changed: " + name)
    final = json.loads((final_dir / "final_path.json").read_text())
    if (final.get("schema") != "cgat.refined-final-path" or final.get("schema_version") != 1
            or final.get("tool") != tool or final.get("baseline") != provenance.get("baseline")):
        raise BundleError("unsupported admitted refinement path")
    baseline_path = layout.path("metadata/grt_final_path.json")
    baseline = json.loads(baseline_path.read_text())
    if fingerprint(baseline) != final["baseline"]["final_path_sha256"] or digest(layout.path(baseline["q4_relpath"])) != final["baseline"]["assembly_sha256"]:
        raise BundleError("current LGZ baseline differs from the admitted refinement")
    for relative, sha in provenance["execution"].get("artifacts", {}).items():
        if digest(safe_file(root, relative)) != sha:
            raise BundleError("native refinement evidence changed before delivery")
    for row in provenance["execution"].get("recipe", {}).get("reads", []):
        if not row.get("not_consumed") and digest(Path(row["path"])) != row["sha256"]:
            raise BundleError("consumed refinement reads changed before delivery")
    _, rows = read_table(final_dir / "sources.tsv")
    catalog = FastaCatalog(root, private / "source-indexes")
    for row in rows:
        path = layout.path(row["fasta_path"]) if row["path_scope"] == "workspace" else Path(row["fasta_path"])
        if digest(path) != row["fasta_sha256"]:
            raise BundleError("refinement source changed before delivery")
        catalog.register(row["dataset"], row["contig"], path, origin=row["origin"])
        row["length"] = int(row["length"])
        if catalog.length(row["dataset"], row["contig"]) != row["length"]:
            raise BundleError("refinement source length changed")
    return final_dir, provenance, final, rows, catalog


def build_full(root, result, report, target):
    """Create a genuine full App payload; callers later derive its light view."""
    root, target = Path(root).resolve(), Path(target).absolute()
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2 or result["tool"] not in TOOL_DIRECTORIES:
        raise BundleError("refined App delivery requires a numbered workspace")
    if target.exists() or not target.resolve().is_relative_to(root / ".runtime"):
        raise BundleError("refinement delivery needs fresh private workspace staging")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".bundle-indexes-", dir=target.parent) as private:
        final_dir, provenance, server, sources, catalog = _load_catalog(root, result, Path(private))
        # Exhaustive LGZ validation happens in this repository-owned builder.
        from server_source_identity import write_map
        original_sources = [{"dataset": dataset, "contig": contig, "length": catalog.length(dataset, contig),
                             "fasta_sha256": catalog.files[source["resolved"]]["sha256"]}
                            for (dataset, contig), source in sorted(catalog.sources.items()) if source["origin"] == "lgz"]
        lgz_app_package.build(root, target, True, include_legacy_gapfill=False, server_sources=original_sources)
        close_source_payload(root, target, Path(private))
        metadata = target / "metadata"
        baseline_view = json.loads((metadata / "grt_final_path.json").read_text())
        projected, evidence = project_path(server, baseline_view)
        fields, datasets = read_table(metadata / "datasets.tsv")
        locator_fields, locators = read_table(metadata / "source_seq_locator.tsv")
        order_fields, orders = read_table(metadata / "track_member_orders.tsv")
        n_fields, n_rows = read_table(metadata / "source_seq_n_regions.tsv")
        card_fields, cards = read_table(metadata / "grt_used_contigs.tsv")
        assignments = read_table(metadata / "chr_assignments.tsv")[1]
        known = {(row["dataset_name"], row["seq_name"]) for row in locators}
        dataset_names = {row["dataset_name"] for row in datasets}
        added = {}
        for row in sources:
            key = row["dataset"], row["contig"]
            if key not in known:
                if row["dataset"] in dataset_names or not row["origin"].startswith("refinement:"):
                    raise BundleError("refinement source collides with an original dataset or has unknown origin")
                added.setdefault(row["dataset"], []).append(row)
        for dataset, rows in sorted(added.items()):
            relative = "data/refinement/sources/" + hashlib.sha256(dataset.encode()).hexdigest()[:24] + ".fa"
            write_source_fasta(target / relative, rows, catalog)
            datasets.append({"dataset_name": dataset, "assembler": "CGAT accepted " + result["tool"], "assembler_version": "1",
                             "fasta_relpath": relative, "fai_relpath": relative + ".fai", "self_alignment_available": "false"})
            for row in rows:
                locators.append({"dataset_name": dataset, "seq_name": row["contig"], "fasta_relpath": relative})
            index = IndexedFasta(target / relative, Path(private) / (fingerprint(dataset) + ".fa"))
            for name, start, end in index.gaps():
                n_rows.append({"dataset_name": dataset, "seq_name": name, "start_bp": str(start + 1),
                               "end_bp": str(end), "length_bp": str(end - start)})
        write_table(metadata / "datasets.tsv", fields, datasets)
        write_table(metadata / "source_seq_locator.tsv", locator_fields, locators)
        write_table(metadata / "source_seq_n_regions.tsv", n_fields, n_rows)
        measured = None
        if result.get("source_evidence"):
            try:
                from refinement_source_delivery import apply_to_bundle
            except ModuleNotFoundError:
                from .refinement_source_delivery import apply_to_bundle
            measured = apply_to_bundle(result["source_evidence"], target)
            if measured["recipe"]["provenance_sha256"] != digest(final_dir / "provenance.json"):
                raise BundleError("source evidence belongs to a different accepted result")
        measurements = {(row["dataset"], row["contig"], row["chromosome"]): row for row in measured["sources"]} if measured else {}
        # New patch cards are contextual placements, never fake homology hits.
        original_cards = {(row["dataset_name"], row["seq_name"], row["assigned_chr_name"]): row for row in assignments}
        card_lookup = {(row["dataset_name"], row["contig_name"], row["target_chr"]): row for row in cards}
        context = []
        for chromosome in projected["chromosomes"]:
            name = chromosome["chr"]
            neighbors = []
            for index, segment in enumerate(chromosome["segments"]):
                source = segment.get("source")
                if source:
                    key = source["dataset"], source["contig"], name
                    row = card_lookup.get(key) or original_cards.get(key)
                    if row:
                        neighbors.append((index, row))
            for index, segment in enumerate(chromosome["segments"]):
                source = segment.get("source") or segment.get("refinement_source")
                if not source or source["dataset"] not in added:
                    continue
                key = source["dataset"], source["contig"], name
                if key in card_lookup:
                    continue
                neighbor = min(neighbors, key=lambda row: abs(row[0] - index))[1] if neighbors else None
                anchor = max(1, int(neighbor["anchor_start"])) if neighbor else 1
                row = {field: "" for field in card_fields}
                row.update(source_card_key=":".join((*key, "refinement")), dataset_name=key[0], contig_name=key[1],
                           target_chr=name, placement_mode="refinement", original_assignment="unplaced",
                           ref_alignment_status=measurements[key]["ref_alignment_status"] if measured else "not_measured",
                           anchor_start=str(anchor), orientation=source["orientation"])
                for field in card_fields:
                    if field.endswith("_json"):
                        row[field] = "[]"
                cards.append(row)
                card_lookup[key] = row
                context.append({"source_card_key": row["source_card_key"], "placement_basis": "adjacent_lgz_source_context" if neighbor else "chromosome_context_only",
                                "anchor_start": anchor, "homology_evidence": False,
                                "annotations": measurements[key]["annotations"] if measured else "not_scanned",
                                "reference_measurement": measurements.get(key)})
                # Context-only patch cards are materialized by the App card
                # initializer, not the reference-assignment ordering table.
        write_table(metadata / "grt_used_contigs.tsv", card_fields, cards)
        write_table(metadata / "track_member_orders.tsv", order_fields, orders)
        recipe_fields, recipes = read_table(metadata / "grt_recipe.tsv")
        support = json.loads(recipes[0]["support_datasets_json"])
        recipes[0]["support_datasets_json"] = json.dumps([*support, *sorted(added)])
        recipes[0]["final_q_relpath"] = FINAL_FASTA
        recipes[0]["recipe_id"] += ":refinement:" + result["tool"] + ":" + result["run_id"]
        write_table(metadata / "grt_recipe.tsv", recipe_fields, recipes)
        package_fields, packages = read_table(metadata / "package.tsv")
        packages[0].update(schema_version=PACKAGE_VERSION, final_path_schema_version=PATH_VERSION)
        write_table(metadata / "package.tsv", package_fields, packages)
        (target / SERVER_PATH).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(final_dir / "final_path.json", target / SERVER_PATH)
        write_json(metadata / "grt_final_path.json", projected)
        output = target / FINAL_FASTA
        output.parent.mkdir(parents=True, exist_ok=True)
        write_assembly(server, catalog, output)
        if digest(output) != provenance["artifacts"]["assembly.fa"]:
            raise BundleError("delivery reconstruction differs from the admitted refined FASTA")
        # The legacy projected final genome is not the current result and does
        # not need to be carried a second time into a refined package.
        old_relative = baseline_view["q4_relpath"]
        for suffix in ("", ".fai"):
            (target / (old_relative + suffix)).unlink(missing_ok=True)
        lengths = {row["chr"]: row["length"] for row in server["chromosomes"]}
        lgz_app_package.write_manifest(target, "full", True, projected, digest(output), lengths, schema_version=PACKAGE_VERSION)
        report_directory = Path(report["directory"])
        if digest(safe_file(report_directory, "manifest.json")) != report["manifest_sha256"]:
            raise BundleError("portable refinement report changed before delivery")
        shutil.copytree(report_directory, target / "report")
        all_sources = {(row["dataset"], row["contig"]): row for row in original_sources}
        all_sources.update({(row["dataset"], row["contig"]): {key: row[key] for key in ("dataset", "contig", "length", "fasta_sha256")}
                            for row in sources})
        write_map(target, [all_sources[key] for key in sorted(all_sources)])
        verify_projection(server, projected)
        # Recheck all admitted artifacts (including Final Path) at the same
        # boundary, after every source read and projection has completed.
        catalog.verify_unchanged()
        for name, expected in provenance["artifacts"].items():
            if digest(final_dir / name) != expected:
                raise BundleError("admitted result changed during delivery construction")
        manifest = {"schema": SCHEMA, "schema_version": 1, "tool": result["tool"], "run_id": result["run_id"],
                    "package_version": PACKAGE_VERSION, "final_path_version": PATH_VERSION, "package_mode": "full",
                    "server_final_path_sha256": provenance["artifacts"]["final_path.json"],
                    "provenance_sha256": digest(final_dir / "provenance.json"), "baseline": server["baseline"],
                    "sources": [{k: v for k, v in row.items() if k not in {"fasta_path", "path_scope"}} for row in sources],
                    "display_evidence": evidence, "patch_placements": context,
                    "annotation_policy": measured["recipe"]["annotation_policy"] if measured else "unchanged source coordinates retained; new patches not yet scanned",
                    "source_evidence": {"file": "metadata/refinement/source_evidence.json", "sha256": digest(target / "metadata/refinement/source_evidence.json")} if measured else None,
                    "biological_accuracy_validated": False}
        shutil.copyfile(final_dir / "provenance.json", target / "metadata/refinement/provenance.json")
        seal_manifest(target, manifest)
        return manifest


def seal_manifest(root, manifest):
    manifest["files"] = {path.relative_to(root).as_posix(): digest(path) for path in sorted(root.rglob("*"))
                         if path.is_file() and path.relative_to(root).as_posix() != MANIFEST}
    write_json(root / MANIFEST, manifest)


def build_light(full, target):
    full, target = Path(full), Path(target)
    if target.exists():
        raise BundleError("light payload must use a fresh staging directory")
    manifest = json.loads(safe_file(full, MANIFEST).read_text())
    if manifest.get("schema") != SCHEMA or manifest.get("package_mode") != "full":
        raise BundleError("light derivation requires a sealed full refinement payload")
    target.mkdir(parents=True)
    for name, sha in manifest["files"].items():
        source = safe_file(full, name)
        if digest(source) != sha:
            raise BundleError("full refinement payload changed before light derivation")
        if source.suffix.lower() in {".fa", ".fasta", ".fna", ".fq", ".fastq"}:
            continue
        output = target / name
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
    fields, rows = read_table(target / "metadata/package.tsv")
    rows[0]["package_mode"] = "no_fasta"
    write_table(target / "metadata/package.tsv", fields, rows)
    app = json.loads((target / "metadata/grt_app_manifest.json").read_text())
    app.update(package_kind="no_fasta", fasta_available=False)
    write_json(target / "metadata/grt_app_manifest.json", app)
    manifest["package_mode"] = "light"
    seal_manifest(target, manifest)
    return manifest
