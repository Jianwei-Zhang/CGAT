"""Real refined App payload validation, including sourced sequence reconstruction."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re

try:
    from refinement_bundle import (BundleError, SCHEMA, MANIFEST, SERVER_PATH, FINAL_FASTA,
                                   PACKAGE_VERSION, PATH_VERSION, read_table, verify_projection)
    from refinement_reports import safe_file, stat_key
    from refinement_path import segment_blocks
    from refinement_tools import fingerprint
    from run_orchestration import sha256_file as digest
except ModuleNotFoundError:
    from .refinement_bundle import (BundleError, SCHEMA, MANIFEST, SERVER_PATH, FINAL_FASTA,
                                    PACKAGE_VERSION, PATH_VERSION, read_table, verify_projection)
    from .refinement_reports import safe_file, stat_key
    from .refinement_path import segment_blocks
    from .refinement_tools import fingerprint
    from .run_orchestration import sha256_file as digest

BLOCK = 1024 * 1024
DNA = re.compile(br"[^ACGTRYSWKMBDHVNacgtryswkmbdhvn]")


class DeliveryCatalog:
    """Use sealed FAI byte positions, never a subprocess or whole-genome dict."""
    def __init__(self, root):
        self.root, self.sources, self.identities, self.indexes = root, {}, {}, {}
        datasets = read_table(root / "metadata/datasets.tsv")[1]
        for dataset in datasets:
            name = dataset["dataset_name"]
            if name in self.indexes:
                raise BundleError("duplicate delivery dataset")
            fai = safe_file(root, dataset["fai_relpath"])
            rows = {}
            for line in fai.read_text(encoding="utf-8").splitlines():
                fields = line.split("\t")
                if len(fields) < 5 or fields[0] in rows:
                    raise BundleError("invalid delivery FAI")
                length, offset, bases, width = map(int, fields[1:5])
                if length <= 0 or offset < 0 or bases <= 0 or width < bases or width > bases + 2:
                    raise BundleError("invalid delivery FAI coordinates")
                rows[fields[0]] = length, offset, bases, width
            self.indexes[name] = rows
        self.byte_rows, local_indexes = {}, {}
        for row in read_table(root / "metadata/source_seq_locator.tsv")[1]:
            key = row["dataset_name"], row["seq_name"]
            if key in self.sources or key[0] not in self.indexes or key[1] not in self.indexes[key[0]]:
                raise BundleError("duplicate/unknown delivery source locator")
            relative = row["fasta_relpath"]
            if relative not in local_indexes:
                records = {}
                for line in safe_file(root, relative + ".fai").read_text(encoding="utf-8").splitlines():
                    fields = line.split("\t")
                    if len(fields) < 5 or fields[0] in records:
                        raise BundleError("invalid source-local FAI")
                    record = tuple(map(int, fields[1:5]))
                    if record[0] <= 0 or record[1] < 0 or record[2] <= 0 or not record[2] <= record[3] <= record[2] + 2:
                        raise BundleError("invalid source-local FAI coordinates")
                    records[fields[0]] = record
                local_indexes[relative] = records
            record = local_indexes[relative].get(key[1])
            if record is None or record[0] != self.indexes[key[0]][key[1]][0]:
                raise BundleError("local source FAI length differs from dataset catalog")
            self.byte_rows[key] = record
            path = root / relative
            # Light packages deliberately retain an unavailable FASTA locator.
            if path.exists() or path.is_symlink():
                path = safe_file(root, relative)
                self.identities[path] = stat_key(path)
            self.sources[key] = path

    def length(self, dataset, contig):
        if (dataset, contig) not in self.sources:
            raise BundleError("refined path references an unknown source")
        return self.indexes[dataset][contig][0]

    def fetch(self, dataset, contig, start, end):
        path = self.sources[dataset, contig]
        if path not in self.identities:
            raise BundleError("source FASTA is unavailable in light delivery")
        if stat_key(path) != self.identities[path]:
            raise BundleError("delivery source changed while reconstructing")
        length, offset, bases, width = self.byte_rows[dataset, contig]
        if not 0 <= start < end <= length or end - start > BLOCK:
            raise BundleError("invalid delivery source interval")
        first = offset + start // bases * width + start % bases
        last = offset + (end - 1) // bases * width + (end - 1) % bases + 1
        with path.open("rb") as stream:
            stream.seek(first)
            data = stream.read(last - first).replace(b"\n", b"").replace(b"\r", b"")
        if len(data) != end - start or DNA.search(data):
            raise BundleError("delivery FASTA/index does not describe the source interval")
        return data


def validate_payload(root, *, full=None):
    root = Path(root).resolve()
    manifest = json.loads(safe_file(root, MANIFEST).read_text())
    if (manifest.get("schema") != SCHEMA or manifest.get("schema_version") != 1
            or manifest.get("package_version") != PACKAGE_VERSION or manifest.get("final_path_version") != PATH_VERSION
            or manifest.get("package_mode") not in {"full", "light"}):
        raise BundleError("unsupported refined App delivery schema")
    available = manifest["package_mode"] == "full"
    if full is not None and available != full:
        raise BundleError("refined delivery has the wrong full/light mode")
    observed = {}
    identities = {}
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise BundleError("refined delivery contains an unsupported file")
        if path.is_file() and path.relative_to(root).as_posix() != MANIFEST:
            identities[path] = stat_key(path)
            observed[path.relative_to(root).as_posix()] = digest(path)
    if observed != manifest.get("files"):
        raise BundleError("refined delivery file inventory/hash mismatch")
    if not available and any(Path(name).suffix.lower() in {".fa", ".fasta", ".fna", ".fq", ".fastq"} for name in observed):
        raise BundleError("light delivery unexpectedly includes sequence files")
    server = json.loads(safe_file(root, SERVER_PATH).read_text())
    projected = json.loads(safe_file(root, "metadata/grt_final_path.json").read_text())
    if digest(root / SERVER_PATH) != manifest["server_final_path_sha256"]:
        raise BundleError("authoritative refined path hash mismatch")
    if (server.get("schema") != "cgat.refined-final-path" or server.get("schema_version") != 1
            or server.get("tool") != manifest.get("tool") or server.get("baseline") != manifest.get("baseline")):
        raise BundleError("refinement manifest and Server path disagree")
    verify_projection(server, projected)
    provenance = json.loads(safe_file(root, "metadata/refinement/provenance.json").read_text())
    if (digest(root / "metadata/refinement/provenance.json") != manifest["provenance_sha256"]
            or provenance.get("tool") != manifest["tool"] or provenance.get("run_id") != manifest["run_id"]
            or provenance.get("artifacts", {}).get("final_path.json") != manifest["server_final_path_sha256"]
            or provenance.get("execution", {}).get("status") != "success"):
        raise BundleError("refined delivery provenance is not the completed admitted result")
    report = json.loads(safe_file(root, "report/manifest.json").read_text())
    report_files = {name[len("report/"):]: sha for name, sha in observed.items()
                    if name.startswith("report/") and name != "report/manifest.json"}
    if (report.get("schema") != "cgat.refinement-report" or report.get("schema_version") != 1
            or report.get("binding", {}).get("provenance_sha256") != manifest["provenance_sha256"]
            or report.get("files") != report_files or "report.html" not in report_files):
        raise BundleError("archived refinement report inventory/provenance mismatch")
    _, packages = read_table(root / "metadata/package.tsv")
    if len(packages) != 1 or any(packages[0].get(key) != value for key, value in {
            "workflow": "gpm_grt_app_precomputed_v2", "schema_version": PACKAGE_VERSION,
            "final_path_schema_version": PATH_VERSION, "package_mode": "full" if available else "no_fasta"}.items()):
        raise BundleError("refined package table disagrees with delivery manifest")
    app = json.loads(safe_file(root, "metadata/grt_app_manifest.json").read_text())
    expected_lengths = {row["chr"]: row["length"] for row in server["chromosomes"]}
    if (app.get("schema_version") != PACKAGE_VERSION or app.get("fasta_available") is not available
            or app.get("workflow") != "gpm_grt_app_precomputed_v2"
            or app.get("package_kind") != ("full" if available else "no_fasta")
            or app.get("q4_artifact_sha256") != provenance["artifacts"]["assembly.fa"]
            or app.get("q4_chromosome_lengths") != expected_lengths
            or app.get("q4_length_bp") != sum(expected_lengths.values())
            or app.get("q4_relpath") != FINAL_FASTA or app.get("final_path_sha256") != fingerprint(projected)):
        raise BundleError("refined App manifest does not bind the projected path")
    catalog = DeliveryCatalog(root)
    cards = read_table(root / "metadata/grt_used_contigs.tsv")[1]
    try:
        from refinement_source_delivery import validate_projection
    except ModuleNotFoundError:
        from .refinement_source_delivery import validate_projection
    measured = validate_projection(root, manifest, server, cards, report)
    placements = {row["source_card_key"]: row for row in manifest.get("patch_placements", [])}
    if len(placements) != len(manifest.get("patch_placements", [])):
        raise BundleError("duplicate contextual refinement placement")
    assigned = {(row["dataset_name"], row["seq_name"], row["assigned_chr_name"]) for row in read_table(root / "metadata/chr_assignments.tsv")[1]}
    seen_cards, refinement_cards = set(), set()
    for card in cards:
        key = card["dataset_name"], card["contig_name"], card["target_chr"]
        expected_key = ":".join((*key, card["placement_mode"]))
        if card["source_card_key"] != expected_key or expected_key in seen_cards:
            raise BundleError("invalid or duplicated source card identity")
        seen_cards.add(expected_key)
        if card["placement_mode"] == "refinement":
            placement = placements.get(expected_key, {})
            has_measurements = manifest.get("source_evidence") is not None
            if has_measurements and key not in measured:
                raise BundleError("refinement card lacks its measured-source proof")
            expected_status = measured[key]["ref_alignment_status"] if has_measurements else "not_measured"
            if (has_measurements and (placement.get("reference_measurement") != measured[key]
                             or placement.get("annotations") != measured[key]["annotations"])):
                raise BundleError("refinement context does not bind its independent source measurement")
            if (key in assigned or card["ref_alignment_status"] != expected_status
                    or placement.get("homology_evidence") is not False
                    or placement.get("anchor_start") != int(card["anchor_start"])
                    or int(card["anchor_start"]) < 1):
                raise BundleError("refinement card falsely claims reference assignment or lacks contextual provenance")
            refinement_cards.add(expected_key)
    if refinement_cards != set(placements):
        raise BundleError("dangling refinement placement provenance")
    recipe = read_table(root / "metadata/grt_recipe.tsv")[1]
    if len(recipe) != 1 or recipe[0]["final_q_relpath"] != FINAL_FASTA:
        raise BundleError("App recipe does not select the refined final result")
    assemblies = {}
    ids = set()
    for chromosome in server["chromosomes"]:
        sha, length = hashlib.sha256(), 0
        for segment in chromosome["segments"]:
            sid = segment["segment_id"]
            if sid in ids or segment.get("output_start") != length or type(segment.get("length")) is not int or segment["length"] <= 0:
                raise BundleError("invalid refined path placement or duplicate segment")
            ids.add(sid)
            source = segment.get("source") if segment["kind"] != "gap" else segment.get("refinement_source")
            if source:
                source_length = catalog.length(source["dataset"], source["contig"])
                if (source.get("orientation") not in {"+", "-"} or type(source.get("start")) is not int
                        or type(source.get("end")) is not int or not 1 <= source["start"] <= source["end"] <= source_length
                        or source["end"] - source["start"] + 1 != segment["length"]):
                    raise BundleError("invalid refined source interval")
            if available:
                for block in segment_blocks(segment, catalog):
                    sha.update(block)
            length += segment["length"]
            if segment.get("output_end") != length:
                raise BundleError("refined output coordinate mismatch")
        if length != chromosome["length"] or (available and sha.hexdigest() != chromosome["sha256"]):
            raise BundleError("source reconstruction differs from the refined chromosome")
        if chromosome["chr"] in assemblies:
            raise BundleError("duplicate refined chromosome")
        assemblies[chromosome["chr"]] = {"length": length, "sha256": chromosome["sha256"]}
    if available and digest(safe_file(root, FINAL_FASTA)) != provenance["artifacts"]["assembly.fa"]:
        raise BundleError("delivered final FASTA differs from admitted assembly")
    if any(stat_key(path) != expected for path, expected in identities.items()):
        raise BundleError("refined delivery changed during validation")
    return {"tool": manifest["tool"], "run_id": manifest["run_id"], "mode": manifest["package_mode"],
            "final_path_sha256": manifest["server_final_path_sha256"], "assemblies": assemblies,
            "provenance_sha256": manifest["provenance_sha256"],
            "report_manifest_sha256": observed.get("report/manifest.json"),
            "source_evidence_receipt_sha256": json.loads(safe_file(root, "metadata/refinement/source_evidence.json").read_text())["source_receipt_sha256"] if manifest.get("source_evidence") else None}
