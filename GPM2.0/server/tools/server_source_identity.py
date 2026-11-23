"""Portable source identities and original/refined/manual Server seed resolution."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import tempfile

from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, relative_path, workspace_join
from workspace_migration import durable_json
from run_orchestration import sha256_file as digest
from post_lgz_degap import IndexedFasta
from degap_manual_catalog import content_digest, read_object

MAP = "metadata/server_sources.json"
SCHEMA = "cgat.server-source-identities"
DNA = re.compile(r"^[ACGTRYSWKMBDHVN]+$", re.I)


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def original_bindings(root, lengths):
    layout = WorkspaceLayout.detect(root)
    result = []
    for row in read_rows(layout.path("metadata/source_seq_locator.tsv")):
        key = row["dataset_name"], row["seq_name"]
        source = layout.path(relative_path(row["fasta_relpath"]))
        result.append({"dataset": key[0], "contig": key[1], "length": lengths[key],
                       "fasta_sha256": content_digest(source)})
    return result


def write_map(target, rows):
    keys = [(row["dataset"], row["contig"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate Server source identity")
    durable_json(Path(target) / MAP, {"schema": SCHEMA, "schema_version": 1, "sources": rows})


def completed_refinement_sources(root, dataset, contig):
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2:
        return
    for tool, code in TOOL_DIRECTORIES.items():
        homes = [layout.path(f"05_final/{code}"), *sorted(layout.path(f".runtime/refinement/{code}").glob("*/final"))]
        for final in homes:
            try:
                provenance_path = final / "provenance.json"
                if not provenance_path.is_file() or provenance_path.is_symlink():
                    continue
                provenance = read_object(provenance_path)
                run = provenance.get("run_id", "")
                if not isinstance(run, str) or re.fullmatch(r"[0-9a-f]{32}", run) is None:
                    continue
                marker_path = layout.path(f"04_refinement/{code}/02_jobs/{run}/invocation.json")
                if not marker_path.is_file():
                    continue
                marker = read_object(marker_path)
                if (marker.get("status") not in {"staged", "published"} or marker.get("tool") != tool
                        or marker.get("run_id") != run or marker.get("provenance_sha256") != content_digest(provenance_path)
                        or provenance.get("schema") != "cgat.refinement-publication" or provenance.get("schema_version") != 1
                        or provenance.get("tool") != tool or provenance.get("run_id") != run
                        or provenance.get("execution", {}).get("status") != "success"):
                    continue
                table = final / "sources.tsv"
                if content_digest(table) != provenance.get("artifacts", {}).get("sources.tsv"):
                    continue
                for row in read_rows(table):
                    if (row["dataset"], row["contig"]) != (dataset, contig):
                        continue
                    if row["path_scope"] == "workspace":
                        source = layout.path(relative_path(row["fasta_path"]))
                    elif row["path_scope"] == "external" and Path(row["fasta_path"]).is_absolute():
                        source = Path(row["fasta_path"])
                    else:
                        raise ValueError("invalid admitted source location")
                    yield source, row["fasta_sha256"], "completed_refinement:" + run
            except (OSError, ValueError, KeyError, TypeError):
                # Orphan/changed historical staging is not source authority.
                # Keep looking for an independently sealed matching producer;
                # failure to find one still rejects the requested source.
                continue


def candidates(root, member):
    layout = WorkspaceLayout.detect(root)
    dataset, contig = member["dataset"], member["name"]
    for row in read_rows(layout.path("metadata/source_seq_locator.tsv")):
        if (row["dataset_name"], row["seq_name"]) == (dataset, contig):
            yield layout.path(relative_path(row["fasta_relpath"])), None, "original"
    yield from completed_refinement_sources(root, dataset, contig)
    if layout.version == 2:
        from degap_manual_catalog import bound_current
        catalog, manifest, pointer = bound_current(root)
        if pointer:
            table = WorkspaceLayout.detect(catalog).path("metadata/source_seq_locator.tsv")
            if content_digest(table) != manifest["files"][table.relative_to(catalog).as_posix()]["sha256"]:
                raise ValueError("manual source locator changed")
            for row in read_rows(table):
                if (row["dataset_name"], row["seq_name"]) != (dataset, contig):
                    continue
                source = WorkspaceLayout.detect(catalog).path(relative_path(row["fasta_relpath"]))
                record = manifest["files"].get(source.relative_to(catalog).as_posix())
                if record is None or (source.is_symlink() and source.readlink().as_posix() != record.get("link")):
                    raise ValueError("manual candidate source link changed")
                yield source, record["sha256"], "manual_candidate"


def resolve_seed(root, plan, scratch, *, require_content):
    """Resolve and orient source members without publishing legacy job state."""
    if not isinstance(plan.get("members"), list) or not plan["members"]:
        raise ValueError("seed plan has no source members")
    parts, proofs = [], []
    with tempfile.TemporaryDirectory(prefix=".seed-sources-", dir=scratch) as private:
        indexes = {}
        for member in plan["members"]:
            expected = member.get("fasta_sha256")
            interval_sha = member.get("interval_sha256")
            if interval_sha is not None and (not isinstance(interval_sha, str) or re.fullmatch(r"[0-9a-f]{64}", interval_sha) is None):
                raise ValueError("invalid expected seed interval identity")
            if type(member.get("length")) is not int or member["length"] <= 0:
                raise ValueError("invalid seed source length")
            if expected is not None and re.fullmatch(r"[0-9a-f]{64}", expected) is None:
                raise ValueError("invalid expected Server FASTA identity")
            if require_content and expected is None and interval_sha is None:
                raise ValueError("numbered Server seeds require source identities; re-export from a matching package or restore FASTA")
            selected, known = [], set()
            for source, admitted_sha, origin in candidates(root, member):
                if expected is not None and admitted_sha is not None and expected != admitted_sha:
                    continue
                source = source.resolve(strict=True)
                if source in known:
                    continue
                known.add(source)
                sha = content_digest(source)
                if admitted_sha is not None and sha != admitted_sha:
                    continue
                if expected is not None and sha != expected:
                    continue
                if source not in indexes:
                    indexes[source] = IndexedFasta(source, Path(private) / (hashlib.sha256(str(source).encode()).hexdigest() + ".fa"))
                index = indexes[source]
                if member["name"] not in index.records or index.records[member["name"]][0] != member["length"]:
                    continue
                start, end = member["start"], member["end"]
                if type(start) is not int or type(end) is not int or not 1 <= start <= end <= member["length"]:
                    raise ValueError("invalid exported source slice")
                # CHUNK limits an individual index read, not the exported source interval.
                sequence = b"".join(block.upper() for block in index.blocks(member["name"], start - 1, end))
                actual_interval_sha = hashlib.sha256(sequence).hexdigest()
                if interval_sha is not None and actual_interval_sha != interval_sha:
                    continue
                selected.append((sequence.decode("ascii"), {"dataset": member["dataset"], "name": member["name"],
                                "fasta_sha256": sha, "source": str(source), "origin": origin,
                                "start": start, "end": end, "length": member["length"],
                                "interval_sha256": actual_interval_sha}))
                if expected is not None or interval_sha is not None:
                    # The complete FASTA hash + record identity already fixes
                    # the consumed bytes; unrelated historical catalogs cannot
                    # veto or force rereading a valid original source.
                    break
            if not selected:
                raise ValueError("no content-matching Server source for " + member["dataset"] + ":" + member["name"])
            if len({sequence for sequence, _ in selected}) != 1:
                raise ValueError("ambiguous Server seed source identity")
            parts.append(selected[0][0])
            proofs.append(selected[0][1])
        sequence = "".join(parts)
        start, end = plan["start"], plan["end"]
        if type(start) is not int or type(end) is not int or not 1 <= min(start, end) <= max(start, end) <= len(sequence):
            raise ValueError("invalid assembled seed slice")
        sequence = sequence[min(start, end) - 1:max(start, end)]
        if start > end:
            sequence = sequence.translate(str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN"))[::-1]
        if not DNA.fullmatch(sequence):
            raise ValueError("seed source is not nonempty IUPAC DNA")
        for row in proofs:
            if content_digest(Path(row["source"])) != row["fasta_sha256"]:
                raise ValueError("Server source changed during seed preparation")
    return sequence, proofs


def prepare_seed(recipe, label):
    if (recipe.get("schema") != "gpm.degap.export.v1" or re.fullmatch(r"[0-9a-f]{64}", recipe.get("token", "")) is None
            or label not in {"seqleft", "seqright", "endpoint"}):
        raise ValueError("invalid exported seed receipt")
    root, output = Path(recipe["server_root"]), Path(recipe["out_path"])
    if not root.is_absolute() or not output.is_absolute():
        raise ValueError("seed Server/output paths must be absolute")
    layout = WorkspaceLayout.detect(root)
    owner = read_object(output / ".gpm_degap_inputs.json")
    if owner != {key: value for key, value in recipe.items() if key not in {"token", "project_id"}}:
        raise ValueError("seed output directory belongs to another export; run begin first")
    plan = recipe["seed_plans"][label]
    output.mkdir(parents=True, exist_ok=True)
    sequence, proofs = resolve_seed(root, plan, output, require_content=layout.version == 2)
    with tempfile.TemporaryDirectory(prefix=".seed-write-", dir=output) as private:
        filename = "endpoint.ctg.fa" if label == "endpoint" else label + ".fa"
        target = output / filename
        temporary = Path(private) / filename
        temporary.write_text(">" + label + "\n" + "\n".join(sequence[i:i + 80] for i in range(0, len(sequence), 80)) + "\n")
        with temporary.open("rb") as stream:
            import os
            os.fsync(stream.fileno())
        from workspace_migration import rename_synced
        proof_path = output / ".gpm_degap_source_proof.json"
        receipt = read_object(proof_path) if proof_path.exists() else {"schema": "cgat.degap-seed-sources", "schema_version": 1,
                                                                    "token": recipe["token"], "labels": {}}
        if receipt.get("token") != recipe["token"] or receipt.get("schema") != "cgat.degap-seed-sources":
            raise ValueError("seed source proof belongs to another export")
        rename_synced(temporary, target)
        receipt["labels"][label] = {"plan": plan, "sources": proofs, "seed_sha256": digest(target),
                                    "binding": ("content" if all(row.get("fasta_sha256") for row in plan["members"]) else
                                                "interval_content" if all(row.get("interval_sha256") for row in plan["members"]) else "legacy_identity_only")}
        durable_json(proof_path, receipt)
        return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--label", choices=("seqleft", "seqright", "endpoint"), required=True)
    args = parser.parse_args()
    try:
        print(prepare_seed(read_object(args.recipe), args.label))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, "ERROR: " + str(error) + "\n")


if __name__ == "__main__":
    main()
