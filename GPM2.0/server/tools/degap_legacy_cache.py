"""Receipt-bound adoption of original manual packages after explicit migration."""
from __future__ import annotations

import csv
from dataclasses import dataclass
import io
from pathlib import Path
import shutil
import stat
import zipfile

from workspace_layout import WorkspaceLayout, MIGRATION, relative_path, workspace_join
from migrated_lgz import verified_baseline, PROOF
from degap_manual_catalog import content_digest, read_object
from add_ctg_stage import read_fasta_records


def rows(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8")), delimiter="\t"))


def manifest(data):
    records = list(csv.reader(io.StringIO(data.decode("utf-8")), delimiter="\t"))
    if any(len(row) != 2 for row in records) or len({row[0] for row in records}) != len(records):
        raise ValueError("invalid historical candidate manifest")
    return dict(records)


def binding_matches(path, expected):
    try:
        info = path.lstat()
        return (stat.S_ISREG(info.st_mode) and expected.get("kind") == "file"
                and info.st_size == expected.get("size") and stat.S_IMODE(info.st_mode) == expected.get("mode")
                and content_digest(path) == expected.get("sha256"))
    except FileNotFoundError:
        return False


@dataclass
class Adoption:
    archive: Path
    info_path: Path
    evidence: dict
    bindings: list

    def verify(self):
        for path, expected in self.bindings:
            if not binding_matches(path, expected):
                raise ValueError("historical manual candidate changed during adoption: " + str(path))

    def install(self, server, staged, destination, token):
        cache = workspace_join(staged, ".run_all/degap_packages", token)
        cache.parent.mkdir(parents=True, exist_ok=True)
        result = {"adopted_from": self.evidence}
        for key, source, suffix in (("archive", self.archive, ".zip"), ("info", self.info_path, ".json")):
            target = cache.with_suffix(suffix)
            shutil.copy2(source, target)
            result[key] = (destination / target.relative_to(staged)).relative_to(server).as_posix()
            result[key + "_sha256"] = content_digest(target)
        self.verify()
        return result


def lookup(server, recipe, candidate, receipt):
    """None means no historical cache; present but unproved bytes always fail."""
    layout = WorkspaceLayout.detect(server)
    token = recipe["token"]  # recipes() has already validated the 64-hex token.
    cache = layout.path(".run_all/degap_packages/" + token)
    archive, info_path = cache.with_suffix(".zip"), cache.with_suffix(".json")
    if not any(path.exists() or path.is_symlink() for path in (archive, info_path)):
        return None
    if layout.version != 2 or verified_baseline(layout.root) is None:
        raise ValueError("old manual cache is not bound to a verified completed-LGZ migration")
    journal_path = layout.path(MIGRATION)
    journal = read_object(journal_path)
    entries = {row["source"]: row for row in journal["entries"]}
    bindings = []

    def bind(name):
        row = entries.get(relative_path(name))
        if (row is None or row["before"] != row["after"] or row["after"]["kind"] != "file"):
            raise ValueError("old manual cache/source is absent from the unchanged migration inventory: " + name)
        path = layout.path(row["destination"])
        if not binding_matches(path, row["after"]):
            raise ValueError("migrated manual cache/source changed: " + name)
        bindings.append((path, row["after"]))
        return path

    for path in (journal_path, layout.path(PROOF)):
        bindings.append((path, {"kind": "file", "sha256": content_digest(path),
                                "size": path.stat().st_size, "mode": path.stat().st_mode & 0o7777}))
    archive = bind(".run_all/degap_packages/" + token + ".zip")
    info_path = bind(".run_all/degap_packages/" + token + ".json")
    info = read_object(info_path)
    name = "degap_" + token[:24]
    if (info.get("recipe") != recipe or info.get("sha256") != content_digest(archive)
            or info.get("candidate_sha256") != content_digest(candidate) or info.get("ctg_name") != name
            or info.get("package") != "packages/" + token + ".zip"
            or any(info.get(key) != receipt.get(key) for key in ("seed_sha256", "runtime", "source_proof"))):
        raise ValueError("historical manual package differs from the original task/native receipt")
    locator = bind("metadata/source_seq_locator.tsv")
    selected = [row for row in rows(locator.read_bytes())
                if (row["dataset_name"], row["seq_name"]) == ("derived_ctg", name)]
    if len(selected) != 1:
        raise ValueError("historical candidate source is missing or ambiguous")
    source_name = relative_path(selected[0]["fasta_relpath"])
    source = bind(source_name)
    declared = bind("metadata/add_ctg_manifests/" + name + ".tsv")
    actual_manifest = manifest(declared.read_bytes())
    expected = {"package_type": "add_ctg", "ctg_name": name, "derived_dataset": "derived_ctg",
                "target_chr": recipe["target_chr"], "target_track": recipe["target_track"],
                "source": "DEGAP:" + token + ":" + recipe["job_id"], "contains_fasta": "true"}
    if any(actual_manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("historical candidate placement/provenance differs from its task")
    records = read_fasta_records(source)
    native = read_fasta_records(candidate)
    if len(records) != 1 or records[0][0] != name or len(native) != 1 or records[0][1].upper() != native[0][1].upper():
        raise ValueError("migrated candidate sequence differs from the completed native result")
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate historical candidate ZIP members")
        if (manifest(package.read("add_ctg/manifest.tsv")) != actual_manifest
                or rows(package.read("gpm_server/metadata/source_seq_locator.tsv")) != selected
                or package.read("gpm_server/" + source_name) != source.read_bytes()):
            raise ValueError("historical package does not contain its migrated candidate source")
    evidence = {"schema": "cgat.legacy-manual-cache-adoption", "schema_version": 1,
                "migration_id": journal["id"], "plan_sha256": journal["plan_sha256"],
                "inventory_sha256": journal["inventory_sha256"],
                "archive_sha256": content_digest(archive), "info_sha256": content_digest(info_path),
                "source_sha256": content_digest(source), "candidate_sha256": info["candidate_sha256"]}
    adoption = Adoption(archive, info_path, evidence, bindings)
    adoption.verify()
    return adoption
