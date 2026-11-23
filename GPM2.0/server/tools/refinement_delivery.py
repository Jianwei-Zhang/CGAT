"""Create and validate real full/light refinement archives for publication."""
from __future__ import annotations

import json
import gzip
import copy
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile
import zipfile

try:
    from refinement_bundle import build_full, build_light, BundleError, write_json
    from refinement_bundle_validate import validate_payload
    from refinement_reports import safe_file
    from refinement_tools import fingerprint
    from run_orchestration import sha256_file as digest
    from delivery_archive import archive_options, create_archive
    from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES
except ModuleNotFoundError:
    from .refinement_bundle import build_full, build_light, BundleError, write_json
    from .refinement_bundle_validate import validate_payload
    from .refinement_reports import safe_file
    from .refinement_tools import fingerprint
    from .run_orchestration import sha256_file as digest
    from .delivery_archive import archive_options, create_archive
    from .workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES

SCHEMA = "cgat.refinement-delivery-archives"
_VALIDATED = {}
# Serialization and its source/path helpers have a revision independent of the
# native/admission recipe. Updating these must refresh delivery, not the science.
GENERATOR_FILES = ("refinement_delivery.py", "refinement_bundle.py", "refinement_bundle_validate.py",
                   "lgz_app_package.py", "lgz_display_evidence.py", "server_source_identity.py", "delivery_archive.py", "workspace_layout.py",
                   "refinement_path.py", "refinement_sources.py", "post_lgz_degap.py",
                   "refinement_reports.py", "refinement_tools.py", "run_orchestration.py",
                   "refinement_source_payload.py", "refinement_source_delivery.py", "refinement_source_marks.py")
VALIDATOR_FILES = ("refinement_bundle_validate.py", "refinement_source_delivery.py", "refinement_source_marks.py",
                   "lgz_core/q0_alignments.py", "lgz_core/q0_sources.py")


def delivery_generation(root, result, report):
    final, directory = Path(result["staging"]), Path(report["directory"])
    if digest(safe_file(directory, "manifest.json")) != report["manifest_sha256"]:
        raise BundleError("portable refinement report changed before delivery")
    evidence = result.get("source_evidence")
    if not evidence:
        raise BundleError("complete accepted-source measurements before creating refinement delivery")
    try:
        from refinement_source_evidence import load, verify_inputs, RECEIPT
    except ModuleNotFoundError:
        from .refinement_source_evidence import load, verify_inputs, RECEIPT
    receipt = load(evidence["directory"])
    verify_inputs(receipt["recipe"])
    if (digest(safe_file(Path(evidence["directory"]), RECEIPT)) != evidence["receipt_sha256"]
            or receipt["recipe"]["provenance_sha256"] != digest(safe_file(final, "provenance.json"))):
        raise BundleError("source measurements do not bind this admitted refinement")
    report_binding = json.loads(safe_file(directory, "manifest.json").read_text())["binding"]
    if report_binding.get("source_evidence_receipt_sha256") != evidence["receipt_sha256"]:
        raise BundleError("report lacks the current accepted-source measurements")
    format_name, _ = archive_options(root)
    return {"schema": "cgat.refinement-delivery-generation", "schema_version": 1,
            "source_evidence_receipt_sha256": evidence["receipt_sha256"],
            "provenance_sha256": digest(safe_file(final, "provenance.json")),
            "report_manifest_sha256": report["manifest_sha256"], "archive_format": format_name,
            "generators": {name: digest(Path(__file__).with_name(name)) for name in GENERATOR_FILES}}


def _extract(archive, target):
    """Extract only single-root regular files/dirs; never use extractall()."""
    seen, roots = set(), set()
    def member(name):
        if "\\" in name or name.startswith("/") or ":" in name:
            raise BundleError("unsafe refinement archive member")
        parts = name.rstrip("/").split("/")
        if not parts or any(value in {"", ".", ".."} for value in parts):
            raise BundleError("unsafe refinement archive relative path")
        if name.rstrip("/") in seen:
            raise BundleError("duplicate refinement archive member")
        seen.add(name.rstrip("/"))
        roots.add(parts[0])
        if len(roots) != 1:
            raise BundleError("refined archive must contain one independent project root")
        return target.joinpath(*parts)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as stream:
            for item in stream.infolist():
                path = member(item.filename)
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
                    raise BundleError("refined archive contains links or special files")
                if item.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with stream.open(item) as source, path.open("xb") as output:
                        shutil.copyfileobj(source, output, 1024 * 1024)
    elif archive.name.endswith(".tar.gz"):
        with gzip.open(archive, "rb") as compressed:
            with tarfile.open(fileobj=compressed, mode="r|") as stream:
                for item in stream:
                    path = member(item.name)
                    if not (item.isfile() or item.isdir()):
                        raise BundleError("refined tar contains links or special files")
                    if item.isdir():
                        path.mkdir(parents=True, exist_ok=True)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with stream.extractfile(item) as source, path.open("xb") as output:
                            shutil.copyfileobj(source, output, 1024 * 1024)
            # Consume the gzip trailer too; a valid tar prefix is not enough.
            while compressed.read(1024 * 1024):
                pass
    else:
        raise BundleError("unsupported refinement archive extension")
    if len(roots) != 1:
        raise BundleError("empty refinement archive")
    return target / next(iter(roots))


def validate_delivery(directory, final):
    directory, final = Path(directory), Path(final)
    definition = json.loads(safe_file(directory, "delivery.json").read_text())
    path_file = safe_file(final, "final_path.json")
    server = json.loads(path_file.read_text())
    provenance = json.loads(safe_file(final, "provenance.json").read_text())
    if (definition.get("schema") != SCHEMA or definition.get("schema_version") != 1
            or definition.get("tool") != server["tool"] or definition.get("run_id") != provenance["run_id"]
            or definition.get("server_final_path_sha256") != digest(path_file)
            or set(definition.get("archives", {})) != {"full", "light"}):
        raise BundleError("refinement archive set does not bind the current admitted result")
    files = {"delivery.json"}
    hashes = []
    for mode in ("full", "light"):
        row = definition["archives"][mode]
        source = safe_file(directory, row["file"])
        files.add(row["file"])
        if digest(source) != row["sha256"]:
            raise BundleError("refinement archive changed: " + mode)
        hashes.append(row["sha256"])
    if {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()} != files:
        raise BundleError("unknown files in refinement delivery publication")
    generation = definition.get("generation")
    if generation is not None and (not isinstance(generation, dict)
            or generation.get("schema") != "cgat.refinement-delivery-generation"
            or generation.get("schema_version") != 1
            or generation.get("provenance_sha256") != digest(final / "provenance.json")
            or generation.get("archive_format") not in {"zip", "tar.gz"}):
        raise BundleError("refinement delivery generation does not bind this provenance")
    identity = tuple(hashes) + (digest(path_file), digest(final / "provenance.json"), provenance["run_id"], fingerprint(definition),
                               digest(Path(__file__)), fingerprint({name: digest(Path(__file__).parent / name) for name in VALIDATOR_FILES}))
    # A process-local content cache avoids decompressing the exact same two
    # archives again after their filesystem rename in a publication transaction.
    if identity in _VALIDATED:
        return copy.deepcopy(_VALIDATED[identity])
    proofs = []
    for mode in ("full", "light"):
        source = safe_file(directory, definition["archives"][mode]["file"])
        with tempfile.TemporaryDirectory(prefix="cgat-refined-archive-check-") as temp:
            payload = _extract(source, Path(temp))
            proof = validate_payload(payload, full=mode == "full")
            if proof["tool"] != server["tool"] or proof["run_id"] != provenance["run_id"] or proof["final_path_sha256"] != digest(path_file):
                raise BundleError("archived App payload is not this admitted refinement")
            if proof["provenance_sha256"] != digest(final / "provenance.json"):
                raise BundleError("archived App payload has different admitted provenance")
            if generation is not None and (proof["report_manifest_sha256"] != generation.get("report_manifest_sha256")
                    or proof.get("source_evidence_receipt_sha256") != generation.get("source_evidence_receipt_sha256")
                    or not source.name.endswith("." + generation["archive_format"])):
                raise BundleError("archived App report/format differs from its delivery generation")
            proofs.append(proof)
    if proofs[0]["report_manifest_sha256"] != proofs[1]["report_manifest_sha256"]:
        raise BundleError("full and light archives contain different refinement reports")
    if proofs[0].get("source_evidence_receipt_sha256") != proofs[1].get("source_evidence_receipt_sha256"):
        raise BundleError("full and light archives contain different source measurements")
    if proofs[0]["assemblies"] != proofs[1]["assemblies"]:
        raise BundleError("full and light archives describe different refined sequences")
    proof = {"schema": "cgat.refinement-delivery-validation", "schema_version": 1,
             "validator": "cgat.refinement-archive-and-sources.v1", "tool": server["tool"], "run_id": provenance["run_id"],
             "modes": ["full", "light"], "final_path_sha256": digest(path_file), "assemblies": proofs[0]["assemblies"],
             "provenance_sha256": proofs[0]["provenance_sha256"],
             "report_manifest_sha256": proofs[0]["report_manifest_sha256"],
             "source_evidence_receipt_sha256": proofs[0].get("source_evidence_receipt_sha256"),
             "generation_sha256": fingerprint(generation) if generation is not None else None}
    expected = {row["chr"]: {"length": row["length"], "sha256": row["sha256"]} for row in server["chromosomes"]}
    if proof["assemblies"] != expected:
        raise BundleError("archive source reconstruction differs from accepted chromosomes")
    _VALIDATED[identity] = copy.deepcopy(proof)
    return proof


def build_delivery(root, result, report):
    root = Path(root).resolve()
    layout = WorkspaceLayout.detect(root)
    tool, run_id = result["tool"], result["run_id"]
    if layout.version != 2 or tool not in TOOL_DIRECTORIES:
        raise BundleError("refined delivery requires a numbered workspace")
    final = Path(result["staging"])
    format_name, threads = archive_options(root)
    generation = delivery_generation(root, result, report)
    key = fingerprint(generation)
    home = layout.path(f".runtime/refinement/delivery/{tool}/{run_id}/{key}")
    if home.exists():
        if validate_delivery(home, final)["generation_sha256"] != key:
            raise BundleError("cached delivery belongs to a different artifact generation")
        return home
    home.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".build-", dir=home.parent) as temporary:
        temporary = Path(temporary)
        bundle_name = root.name + "." + tool
        full, light = temporary / "full" / bundle_name, temporary / "light" / bundle_name
        build_full(root, result, report, full)
        build_light(full, light)
        archive_set = temporary / "archives"
        archive_set.mkdir()
        definition = {"schema": SCHEMA, "schema_version": 1, "tool": tool, "run_id": run_id,
                      "server_final_path_sha256": digest(final / "final_path.json"), "generation": generation, "archives": {}}
        for mode, payload in (("full", full), ("light", light)):
            filename = bundle_name + (".light" if mode == "light" else "") + "." + format_name
            output = archive_set / filename
            create_archive(payload, output, format_name, threads)
            definition["archives"][mode] = {"file": filename, "sha256": digest(output)}
        write_json(archive_set / "delivery.json", definition)
        validate_delivery(archive_set, final)
        if delivery_generation(root, result, report) != generation:
            raise BundleError("delivery inputs or serializer changed during archive construction")
        archive_set.rename(home)
    return home
