"""Deliver already completed source measurements without rerunning their producers."""
import csv
from collections import Counter
import json
from pathlib import Path
import shutil

try:
    from refinement_source_evidence import load, verify_inputs, RECEIPT, PROJECTION, SCHEMA, write_table
    from refinement_source_marks import table, annotation_inputs, project, slices
    from refinement_reports import safe_file
    from degap_manual_catalog import content_digest, read_object
    from workspace_layout import relative_path
    from workspace_migration import durable_json
except ModuleNotFoundError:
    from .refinement_source_evidence import load, verify_inputs, RECEIPT, PROJECTION, SCHEMA, write_table
    from .refinement_source_marks import table, annotation_inputs, project, slices
    from .refinement_reports import safe_file
    from .degap_manual_catalog import content_digest, read_object
    from .workspace_layout import relative_path
    from .workspace_migration import durable_json


def apply_to_bundle(evidence, target):
    directory = Path(evidence["directory"])
    if content_digest(safe_file(directory, RECEIPT)) != evidence["receipt_sha256"]:
        raise ValueError("source evidence receipt changed before delivery")
    receipt = load(directory)
    verify_inputs(receipt["recipe"])
    files = {}
    for row in receipt["payload"]:
        source, destination = safe_file(directory, row["file"]), target / relative_path(row["package_path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        if row["merge_tsv"] and destination.exists():
            with destination.open() as stream:
                fields = list(csv.DictReader(stream, delimiter="\t").fieldnames or [])
            with source.open() as stream:
                fields = list(dict.fromkeys([*fields, *(csv.DictReader(stream, delimiter="\t").fieldnames or [])]))
            write_table(destination, fields, [*table(destination), *table(source)])
        else:
            if destination.exists():
                raise ValueError("measured patch evidence collides with original payload: " + row["package_path"])
            shutil.copy2(source, destination)
        files[row["package_path"]] = content_digest(destination)
    projection = {"schema": SCHEMA + "-projection", "schema_version": 1, "generation_sha256": receipt["generation_sha256"],
                  "source_receipt_sha256": evidence["receipt_sha256"], "recipe": receipt["recipe"], "sources": receipt["sources"], "files": files}
    durable_json(target / PROJECTION, projection)
    return projection


def validate_projection(root, manifest, server, cards, report):
    """Old truthful unmeasured packets remain valid; measured cards need proof."""
    capability = manifest.get("source_evidence")
    if capability is None:
        if any(row["placement_mode"] == "refinement" and row["ref_alignment_status"] != "not_measured" for row in cards):
            raise ValueError("measured refinement card lacks source evidence capability")
        return {}
    if not isinstance(capability, dict):
        raise ValueError("invalid measured-source capability type")
    try:
        from refinement_tools import fingerprint
        from lgz_core.q0_alignments import read_paf
    except ModuleNotFoundError:
        from .refinement_tools import fingerprint
        from .lgz_core.q0_alignments import read_paf
    projection = read_object(safe_file(root, PROJECTION))
    if (capability.get("file") != PROJECTION or capability.get("sha256") != content_digest(root / PROJECTION)
            or projection.get("schema") != SCHEMA + "-projection" or projection.get("schema_version") != 1
            or projection.get("generation_sha256") != fingerprint(projection.get("recipe"))):
        raise ValueError("invalid measured-source delivery capability")
    recipe = projection["recipe"]
    if (recipe.get("tool") != manifest["tool"] or recipe.get("run_id") != manifest["run_id"]
            or recipe.get("provenance_sha256") != manifest["provenance_sha256"]
            or report["binding"].get("source_evidence_receipt_sha256") != projection["source_receipt_sha256"]
            or report["binding"].get("source_evidence_generation_sha256") != projection["generation_sha256"]):
        raise ValueError("source measurements/report/accepted provenance differ")
    for relative, sha in projection["files"].items():
        if content_digest(safe_file(root, relative)) != sha:
            raise ValueError("delivered source measurement changed")
    for relative, sha in recipe["annotation_files"].items():
        # The established App protocol does not deliver library FASTA. Its
        # identity is retained in the prepared snapshot, not fabricated locally.
        if relative != "cen/library.fa" and content_digest(safe_file(root, relative)) != sha:
            raise ValueError("delivered annotation rules differ from measured snapshot")
    if any(not isinstance(row, dict) or type(row.get("length")) is not int or row["length"] <= 0
           for row in [*manifest["sources"], *recipe["patch_sources"]]):
        raise ValueError("invalid measured source catalog length")
    patches = {(row["dataset"], row["contig"]): {key: row[key] for key in ("dataset", "contig", "length", "fasta_sha256")}
               for row in manifest["sources"] if row["origin"].startswith("refinement:")}
    declared = {(row["dataset"], row["contig"]): row for row in recipe["patch_sources"]}
    if len(declared) != len(recipe["patch_sources"]) or declared != patches:
        raise ValueError("measured source identities differ from accepted patch sources")
    reference = table(safe_file(root, "metadata/reference.tsv"))
    if len(reference) != 1:
        raise ValueError("measured packet reference is ambiguous")
    if (root / reference[0]["fasta_relpath"]).is_file() and content_digest(safe_file(root, reference[0]["fasta_relpath"])) != recipe["reference_sha256"]:
        raise ValueError("delivered reference differs from measured original reference")
    lengths = {}
    for line in safe_file(root, reference[0]["fai_relpath"]).read_text().splitlines():
        fields = line.split("\t")
        if len(fields) < 5 or fields[0] in lengths or int(fields[1]) < 1:
            raise ValueError("invalid measured reference index")
        lengths[fields[0]] = int(fields[1])
    datasets = {}
    for key, row in patches.items():
        datasets.setdefault(key[0], {})[key[1]] = row["length"]
    hits = {}
    for dataset, queries in datasets.items():
        path = "runs/" + dataset + "_vs_ref/result.paf"
        if path not in projection["files"]:
            raise ValueError("measured source reference PAF is missing")
        for hit in read_paf(safe_file(root, path), query_lengths=queries, target_lengths=lengths):
            hits.setdefault((dataset, hit.query_name), Counter())[hit.target_name] += 1
    measured = {}
    cen_entries = table(safe_file(root, "cen/reference.tsv")) if recipe["annotation_enabled"]["cen"] else []
    tel_rules = table(safe_file(root, "tel/rules.tsv")) if recipe["annotation_enabled"]["tel"] else []
    for row in projection["sources"]:
        key = row["dataset"], row["contig"], row["chromosome"]
        if key in measured or key[:2] not in patches:
            raise ValueError("duplicate or unknown measured source placement")
        expected = patches[key[:2]]
        if any(type(row.get(field)) is not int or row[field] < 0 for field in ("length", "reference_hits", "hits_on_chromosome")):
            raise ValueError("invalid measured source lengths/counts")
        actual = hits.get(key[:2], {})
        total, on_chr = sum(actual.values()), actual.get(key[2], 0)
        status = "no_hit" if not total else "other_chr_only" if not on_chr else "multi_hit" if total > 1 else "hit"
        annotations = {"tel": "disabled" if not recipe["annotation_enabled"]["tel"] else "scanned" if tel_rules else "no_rules",
                       "cen": "disabled" if not recipe["annotation_enabled"]["cen"] else "scanned" if any(r.get("chr_name") in {"*", key[2]} for r in cen_entries) else "no_chr_library"}
        if (row["length"] != expected["length"] or row["fasta_sha256"] != expected["fasta_sha256"]
                or row["ref_alignment_status"] != status or row["reference_hits"] != total
                or row["hits_on_chromosome"] != on_chr or row["annotations"] != annotations):
            raise ValueError("source status does not describe delivered measurements")
        if annotations["tel"] != "disabled" and "tel/chr_" + key[2] + "/" + key[0] + ".tsv" not in projection["files"]:
            raise ValueError("scanned patch telomere marks are missing")
        if annotations["cen"] != "disabled" and "cen/chr_" + key[2] + "/marks.tsv" not in projection["files"]:
            raise ValueError("patch centromere scan state lacks its marks table")
        measured[key] = row
    expected_placements = {(row["dataset"], row["contig"], row["chromosome"]) for row in slices(server)
                           if (row["dataset"], row["contig"]) in patches}
    if set(measured) != expected_placements:
        raise ValueError("measured source placements do not cover accepted patch slices")
    original = {(row["dataset"], row["contig"]): row["length"] for row in manifest["sources"]}
    origins = {key: "refinement_patch" if key in patches else "lgz_source" for key in original}
    expected_intervals, expected_marks = project(server, original, annotation_inputs(root, [row["chr"] for row in server["chromosomes"]]), origins=origins)
    for name, rows in (("source_intervals.tsv", expected_intervals), ("final_annotations.tsv", expected_marks)):
        expected_rows = [{key: str(value) for key, value in row.items()} for row in rows]
        actual_rows = table(safe_file(root, "metadata/refinement/" + name))
        # Source/mark traversal order is not biological evidence.
        normalized = lambda records: sorted(json.dumps(row, sort_keys=True) for row in records)
        if normalized(actual_rows) != normalized(expected_rows):
            raise ValueError("delivered annotation/source coordinates differ from accepted slices")
    return measured
