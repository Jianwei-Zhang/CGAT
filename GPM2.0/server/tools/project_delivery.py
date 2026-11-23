"""Project Full/Light: one LGZ payload plus independent automatic version descriptors.

The two packages share a generation. A tool borrows unchanged metadata from the
LGZ payload by digest; only new objects are carried once. Neither an old single-
tool archive nor a complete patch ZIP is nested inside a project archive.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile

from project_auto_patch import INDEX as PATCH_INDEX, SCHEMA as PATCH_SCHEMA
from refinement_commit import PublicationError, read_json
from refinement_reports import safe_file
from refinement_tools import fingerprint
from run_orchestration import sha256_file

SCHEMA = "cgat.project-delivery"
VERSION_DIR = "project_versions"
INDEX = f"{VERSION_DIR}/index.json"
APP = "metadata/grt_app_manifest.json"
FINAL_PATH = "metadata/grt_final_path.json"


def _encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def generation(baseline, variants):
    return fingerprint({"schema": SCHEMA, "schema_version": 1, "baseline": baseline, "variants": variants})


def _checked_hash(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise PublicationError("invalid object digest in project delivery")
    return value


def project_payload(staging, mode, baseline, patch=None, *, patch_sha=None):
    """Extend an isolated LGZ staging tree (NOT a live workspace or its source files)."""
    if mode not in ("full", "light"):
        raise PublicationError("invalid project package kind")
    app_path = safe_file(staging, APP)
    app = read_json(app_path)
    app_base = safe_file(staging, FINAL_PATH)
    if (app.get("fasta_available") is not (mode == "full") or "project_delivery" in app
            or app.get("q4_artifact_sha256") != _checked_hash(baseline["assembly_sha256"])
            or fingerprint(read_json(app_base)) != app.get("final_path_sha256")):
        raise PublicationError("project payload is not the requested immutable LGZ baseline and mode")
    _checked_hash(baseline["final_path_sha256"])
    output = staging / VERSION_DIR
    output.mkdir(exist_ok=False)
    variants, locators, withheld = {}, {}, set()
    if patch is not None:
        if patch.is_symlink() or sha256_file(patch) != _checked_hash(patch_sha):
            raise PublicationError("project delivery requires the committed automatic patch")
        with zipfile.ZipFile(patch) as archive:
            index = json.loads(archive.read(PATCH_INDEX))
            if (index.get("schema") != PATCH_SCHEMA or index.get("schema_version") != 1
                    or index.get("baseline") != baseline or index.get("baseline_app_path") != sha256_file(app_base)):
                raise PublicationError("automatic versions do not match the project LGZ payload")
            # Only try explicitly named Light metadata as borrowing candidates; never hash a whole
            # original genome just to discover that it is not a patch object.
            candidates = {index["baseline_app_path"]: FINAL_PATH}
            variants = index["variants"]
            checked_names = {}
            for variant in variants.values():
                light = json.loads(archive.read("objects/" + _checked_hash(variant["light_manifest"])))
                for name, sha in light["files"].items():
                    # APP will be replaced below and cannot serve as a borrowed object.
                    if sha not in candidates and name != APP and (staging / name).is_file():
                        if name not in checked_names:
                            checked_names[name] = sha256_file(safe_file(staging, name))
                        if checked_names[name] == sha:
                            candidates[sha] = name
                if mode == "light":
                    withheld.update(variant["accepted_sequence_objects"])
            (output / "objects").mkdir()
            for entry in archive.infolist():
                if entry.filename == PATCH_INDEX:
                    continue
                sha = _checked_hash(entry.filename.removeprefix("objects/"))
                if entry.filename != "objects/" + sha or sha in locators:
                    raise PublicationError("invalid or duplicate project version object")
                if sha in withheld:
                    continue
                if sha in candidates:
                    locators[sha] = candidates[sha]
                    continue
                name = f"{VERSION_DIR}/objects/{sha}"
                digest = hashlib.sha256()
                with archive.open(entry) as src, (staging / name).open("xb") as dst:
                    for block in iter(lambda: src.read(1024 * 1024), b""):
                        digest.update(block)
                        dst.write(block)
                if digest.hexdigest() != sha:
                    raise PublicationError("incorrect project version object content")
                locators[sha] = name
            app_base_sha = index["baseline_app_path"]
    else:
        if patch_sha is not None:
            raise PublicationError("project delivery is missing its automatic patch")
        app_base_sha = sha256_file(app_base)
    manifest = {"schema": SCHEMA, "schema_version": 1, "mode": mode, "baseline": baseline,
                "generation": generation(baseline, variants), "baseline_app_path": app_base_sha,
                "variants": variants, "objects": locators, "omitted_sequences": sorted(withheld)}
    (staging / INDEX).write_bytes(_encoded(manifest))
    # The old single-result reader must reject this archive, not silently open LGZ alone.
    app["workflow"] = "gpm_grt_app_project_v1"
    app["project_delivery"] = {"index": INDEX, "sha256": sha256_file(staging / INDEX), "generation": manifest["generation"]}
    # The rest of staging may safely share inodes with the original LGZ tree.
    # Replace, rather than overwrite, its manifest.
    app_path.unlink()
    with app_path.open("xb") as stream:
        stream.write(_encoded(app))
    return manifest
