"""Versioned q0 publication and interval-aware donor freeze.

Package schema 3 is intentional: an old reader must reject new source-selection
semantics instead of interpreting them as whole-contig reference assignments.
This module validates the prepared transaction, not the later q4/App delivery.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import json
from pathlib import Path

from .common import (CHR_ASSIGNMENT_FIELDS, DONOR_MEMBER_FIELDS, EVIDENCE_FIELDS, Q_SEGMENT_FIELDS, canonical_json, read_fasta, read_tsv,
                     reverse_complement, sha256_bytes, sha256_file, stable_id, write_tsv)
from .q0_admission import Construction, selector_identity
from .q0_preparation import artifact_path
from .q0_sources import Interval, Q0EvidenceError, SourceKey, merged_intervals, split_source, subtract_intervals
from .stage_replay import source_assignment

PACKAGE_SCHEMA_VERSION = "4"
SELECTION = "metadata/grt_q0_selection.json"
FREEZE = "metadata/grt_q0_freeze.json"
SELECTION_SCHEMA = "lgz_q0_selection_artifact_v1"
FREEZE_SCHEMA = "lgz_q0_donor_freeze_v2"


def publication_identity():
    return stable_id("q0-publication", [selector_identity(), sha256_file(Path(__file__)),
                                      sha256_file(Path(__file__).with_name("stage_replay.py")),
                                      sha256_file(Path(__file__).parent.parent / "lgz_prepare_inputs.py")])


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def canonical_rows(rows, fields):
    return [{field: str(row[field]) for field in fields} for row in rows]


def row_hash(rows, fields):
    return sha256_bytes(canonical_json(canonical_rows(rows, fields)).encode("utf-8"))


def source_occupancy(construction: Construction):
    return {SourceKey(**row["source"]): tuple(Interval(**i) for i in row["intervals"])
            for row in construction.decisions["occupied_intervals"]}


def available_intervals(sequences, occupied):
    result = {}
    for key, sequence in sequences.items():
        source = SourceKey(*key)
        try:
            parts = split_source(source, sequence).segments
        except Q0EvidenceError:
            parts = ()
        result[key] = tuple(interval for part in parts
                            for interval in subtract_intervals(part.interval, occupied.get(source, ())))
    return result


def q0_rows(decisions, assignments):
    assigned = defaultdict(set)
    for row in assignments:
        assigned[(row["dataset_name"], row["seq_name"])].add(row["assigned_chr_name"])
    result = []
    for chromosome, search in sorted(decisions["searches"].items()):
        path = search["path"]
        if path is None:
            continue
        cursor = 1
        for index, item in enumerate(path["slices"]):
            source, interval = item["source"], Interval(**item["interval"])
            segment_id = stable_id("q0-source", [chromosome, index, item["placement_id"],
                                                 interval.start, interval.end, item["orientation"]])
            _, _, card = source_assignment(assigned, {"source_dataset": source["dataset"],
                                                      "source_contig": source["contig"], "chr": chromosome})
            evidence_id = stable_id("ev-q0-selection", [segment_id, decisions["selector_identity"]])
            result.append({"q_version": "q0", "chr": chromosome, "segment_id": segment_id,
                           "segment_kind": "source", "q_start": cursor, "q_end": cursor + interval.length - 1,
                           "dataset_name": source["dataset"], "contig_name": source["contig"],
                           "source_start": interval.start + 1, "source_end": interval.end,
                           "orientation": item["orientation"], "source_card_key": card,
                           "evidence_ids_json": canonical_json([evidence_id])})
            cursor += interval.length
            if index < len(path["joins"]):
                join = path["joins"][index]
                if join["n_bp"]:
                    row = {field: "" for field in Q_SEGMENT_FIELDS}
                    row.update({"q_version": "q0", "chr": chromosome,
                                "segment_id": stable_id("q0-gap", join["join_id"]), "segment_kind": "gap",
                                "q_start": cursor, "q_end": cursor + join["n_bp"] - 1, "evidence_ids_json": "[]"})
                    result.append(row)
                    cursor += join["n_bp"]
    return canonical_rows(result, Q_SEGMENT_FIELDS)


def stage_selection(server_dir, stage_root, construction, datasets, assignments):
    artifacts = {record.get("artifact") or record.get("catalog")
                 for record in construction.decisions["evidence"].values()}
    artifacts.discard(None)
    envelope = {"schema": SELECTION_SCHEMA, "construction": construction.decisions,
                "artifact_hashes": {name: sha256_file(artifact_path(server_dir, name)) for name in sorted(artifacts)}}
    selection_path = stage_root / SELECTION
    write_json(selection_path, envelope)
    selection_hash = sha256_file(selection_path)
    rows = q0_rows(construction.decisions, assignments)
    dataset_paths = {row["dataset_name"]: row["fasta_relpath"] for row in datasets}
    source_hashes = {name: sha256_file(artifact_path(server_dir, relative)) for name, relative in dataset_paths.items()}
    q0_hash = sha256_file(stage_root / "grt/q/q0.fa")
    evidence = []
    for row in rows:
        if row["segment_kind"] != "source":
            continue
        item = {field: "" for field in EVIDENCE_FIELDS}
        item.update({"evidence_id": json.loads(row["evidence_ids_json"])[0], "stage": "q0_construction",
                     "evidence_type": "q0_path_selection", "status": "accepted", "q_version": "q0",
                     "q_source_sha256": q0_hash, "query_artifact_relpath": dataset_paths[row["dataset_name"]],
                     "query_sha256": source_hashes[row["dataset_name"]], "source_dataset": row["dataset_name"],
                     "source_contig": row["contig_name"], "source_start": row["source_start"],
                     "source_end": row["source_end"], "orientation": row["orientation"], "target_chr": row["chr"],
                     "tool": "lgz_q0_selector", "tool_version": "1", "preset": "evidence_guided_q0",
                     "parameters_json": canonical_json({"selection_schema": SELECTION_SCHEMA,
                                                         "selector_identity": construction.decisions["selector_identity"],
                                                         "q_segment_id": row["segment_id"]}),
                     "raw_artifact_relpath": SELECTION, "raw_artifact_sha256": selection_hash,
                     "coordinate_system": "source_0_based_half_open", "projection_status": "projected"})
        evidence.append(item)
    return rows, evidence


def freeze_manifest(stage_root, construction, sequences, datasets, donor_sets, members, available, evidence_rows):
    occupied = source_occupancy(construction)
    source_rows = [{"source": asdict(SourceKey(*key)), "length": len(sequence),
                    "sequence_sha256": sha256_bytes(sequence.encode("ascii")),
                    "occupied": [asdict(i) for i in occupied.get(SourceKey(*key), ())],
                    "available": [asdict(i) for i in available[key]],
                    "informative_intervals": [asdict(i) for i in available_intervals({key: sequence}, {})[key]]}
                   for key, sequence in sorted(sequences.items())]
    member_rows = []
    for member in members:
        key = (member["dataset_name"], member["contig_name"])
        # Frozen members remain complete source context; the separate intervals
        # authorize *new additions*, not anchors or duplication of occupied DNA.
        if int(member["source_start"]) != 1 or int(member["source_end"]) != len(sequences[key]) or member["orientation"] != "+":
            raise Q0EvidenceError("q0 donor context must remain the complete forward source")
        member_rows.append({"donor_set_id": member["donor_set_id"], "member_id": member["member_id"],
                            "source": asdict(SourceKey(*key)), "available_member_intervals": [asdict(i) for i in available[key]]})
    immutable_paths = [SELECTION, "grt/q/q0.fa", "metadata/grt_recipe.tsv", "metadata/grt_contig_roles.tsv",
                       "metadata/grt_donor_sets.tsv", "metadata/grt_donor_members.tsv", "metadata/grt_donor_fragments.tsv",
                       "metadata/grt_contig_quality.tsv", "metadata/grt_telomere_rules.tsv"]
    immutable_paths.extend(row[field] for row in donor_sets for field in ("fasta_relpath", "manifest_relpath"))
    payload = {"schema": FREEZE_SCHEMA, "package_schema_version": PACKAGE_SCHEMA_VERSION,
               "scope": "q0_donor_freeze", "publication_identity": publication_identity(),
               "selection": SELECTION, "selection_sha256": sha256_file(stage_root / SELECTION),
               "q0_rows_sha256": row_hash(read_tsv(stage_root / "metadata/grt_q_segments.tsv", Q_SEGMENT_FIELDS), Q_SEGMENT_FIELDS),
               "q0_evidence_sha256": row_hash(evidence_rows, EVIDENCE_FIELDS),
               "sources": source_rows, "members": member_rows,
               "source_fastas": {row["dataset_name"]: row["fasta_relpath"] for row in datasets},
               "artifacts": {name: sha256_file(stage_root / name) for name in sorted(set(immutable_paths))}}
    write_json(stage_root / FREEZE, payload)
    return payload


def validate_prepared_q0(root: Path, *, source_root: Path | None = None, expected: Construction | None = None):
    """Check a serialized freeze and reconstruct q0. This is not q4 delivery validation."""
    root = root.resolve()
    source_root = (source_root or root).resolve()
    def resolve(relative):
        local = artifact_path(root, relative)
        return local if local.is_file() else artifact_path(source_root, relative)
    def load(relative):
        try:
            value = json.loads(resolve(relative).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise Q0EvidenceError(f"invalid q0 publication JSON: {relative}: {exc}") from exc
        if not isinstance(value, dict):
            raise Q0EvidenceError(f"invalid q0 publication object: {relative}")
        return value
    package = read_tsv(resolve("metadata/package.tsv"))
    if len(package) != 1 or package[0]["schema_version"] not in {"3", PACKAGE_SCHEMA_VERSION}:
        raise Q0EvidenceError("q0 publication requires evidence-guided package schema 3 or 4")
    frozen = load(FREEZE)
    if frozen.get("schema") != FREEZE_SCHEMA or frozen.get("package_schema_version") != package[0]["schema_version"]:
        raise Q0EvidenceError("unsupported q0 donor freeze schema")
    donor_sets = read_tsv(resolve("metadata/grt_donor_sets.tsv"))
    required_artifacts = {SELECTION, "grt/q/q0.fa", "metadata/grt_recipe.tsv", "metadata/grt_contig_roles.tsv",
                          "metadata/grt_donor_sets.tsv", "metadata/grt_donor_members.tsv", "metadata/grt_donor_fragments.tsv",
                          "metadata/grt_contig_quality.tsv", "metadata/grt_telomere_rules.tsv"}
    required_artifacts.update(row[field] for row in donor_sets for field in ("fasta_relpath", "manifest_relpath"))
    if set(frozen["artifacts"]) != required_artifacts:
        raise Q0EvidenceError("incomplete frozen artifact inventory")
    # Added project datasets are not retroactive inputs to the locked q0 run.
    # The frozen recipe hash below prevents silently changing that input set.
    recipe = read_tsv(resolve("metadata/grt_recipe.tsv"))[0]
    initial_datasets = {recipe["primary_dataset"], *json.loads(recipe["support_datasets_json"])}
    expected_fastas = {row["dataset_name"]: row["fasta_relpath"] for row in read_tsv(resolve("metadata/datasets.tsv"))
                       if row["dataset_name"] in initial_datasets}
    if set(expected_fastas) != initial_datasets or frozen["source_fastas"] != expected_fastas:
        raise Q0EvidenceError("q0 source FASTA inventory differs from locked recipe datasets")
    for relative, digest in frozen["artifacts"].items():
        if sha256_file(resolve(relative)) != digest:
            raise Q0EvidenceError(f"q0 frozen artifact changed: {relative}")
    envelope = load(SELECTION)
    if envelope.get("schema") != SELECTION_SCHEMA or frozen["selection"] != SELECTION or sha256_file(resolve(SELECTION)) != frozen["selection_sha256"]:
        raise Q0EvidenceError("invalid q0 selection artifact identity")
    decisions = envelope["construction"]
    if expected is not None and canonical_json(decisions) != canonical_json(expected.decisions):
        raise Q0EvidenceError("serialized q0 decision differs from the actual selection")
    raw_evidence = {record.get("artifact") or record.get("catalog") for record in decisions["evidence"].values()}
    raw_evidence.discard(None)
    if set(envelope["artifact_hashes"]) != raw_evidence:
        raise Q0EvidenceError("incomplete q0 raw evidence inventory")
    for relative, digest in envelope["artifact_hashes"].items():
        if sha256_file(resolve(relative)) != digest:
            raise Q0EvidenceError(f"q0 raw alignment evidence changed: {relative}")
    sources = {(dataset, name): sequence for dataset, relative in frozen["source_fastas"].items()
               for name, sequence in read_fasta(resolve(relative))}
    if len(frozen["sources"]) != len(sources) or {(r["source"]["dataset"], r["source"]["contig"]) for r in frozen["sources"]} != set(sources):
        raise Q0EvidenceError("q0 freeze sources do not cover original FASTAs")
    actual_occupied = defaultdict(list)
    by_source = {}
    for row in frozen["sources"]:
        source = SourceKey(**row["source"])
        sequence = sources[(source.dataset, source.contig)]
        if row["length"] != len(sequence) or row["sequence_sha256"] != sha256_bytes(sequence.encode("ascii")):
            raise Q0EvidenceError("q0 frozen source changed")
        by_source[source] = row
    assignments = read_tsv(resolve("metadata/chr_assignments.tsv"), CHR_ASSIGNMENT_FIELDS)
    rows = [row for row in read_tsv(resolve("metadata/grt_q_segments.tsv"), Q_SEGMENT_FIELDS) if row["q_version"] == "q0"]
    if rows != q0_rows(decisions, assignments) or row_hash(rows, Q_SEGMENT_FIELDS) != frozen["q0_rows_sha256"]:
        raise Q0EvidenceError("q0 source mapping differs from selected paths")
    reconstructed = defaultdict(list)
    for row in rows:
        length = int(row["q_end"]) - int(row["q_start"]) + 1
        if row["segment_kind"] == "gap":
            reconstructed[row["chr"]].append("N" * length)
            continue
        source = SourceKey(row["dataset_name"], row["contig_name"])
        interval = Interval(int(row["source_start"]) - 1, int(row["source_end"]))
        sequence = sources[(source.dataset, source.contig)]
        if interval.end > len(sequence) or interval.length != length:
            raise Q0EvidenceError("q0 source mapping exceeds original FASTA")
        if any(interval.intersection(other) for other in actual_occupied[source]):
            raise Q0EvidenceError("q0 repeats an occupied source interval")
        actual_occupied[source].append(interval)
        piece = sequence[interval.start:interval.end]
        reconstructed[row["chr"]].append(piece if row["orientation"] == "+" else reverse_complement(piece))
    for search in decisions["searches"].values():
        if search["path"] is None:
            continue
        for join in search["path"]["joins"]:
            if join["kind"] == "input_assembly_gap":
                source, interval = SourceKey(**join["gap_source"]), Interval(**join["gap_interval"])
                sequence = sources[(source.dataset, source.contig)][interval.start:interval.end]
                if len(sequence) != join["n_bp"] or set(sequence) != {"N"} or any(interval.intersection(i) for i in actual_occupied[source]):
                    raise Q0EvidenceError("invalid or repeated original q0 N interval")
                actual_occupied[source].append(interval)
    if {chromosome: "".join(parts) for chromosome, parts in reconstructed.items()} != dict(read_fasta(resolve("grt/q/q0.fa"))):
        raise Q0EvidenceError("q0 cannot be reconstructed from selected original sources")
    available = available_intervals(sources, actual_occupied)
    for source, row in by_source.items():
        key = (source.dataset, source.contig)
        if row.get("informative_intervals") != [asdict(i) for i in available_intervals({key: sources[key]}, {})[key]]:
            raise Q0EvidenceError("frozen informative source intervals differ from original sequence")
        if row["occupied"] != [asdict(i) for i in merged_intervals(actual_occupied[source])] or row["available"] != [asdict(i) for i in available[(source.dataset, source.contig)]]:
            raise Q0EvidenceError("q0 donor availability differs from actual source occupancy")
    member_map = {(row["donor_set_id"], row["member_id"]): row for row in read_tsv(resolve("metadata/grt_donor_members.tsv"), DONOR_MEMBER_FIELDS)}
    if len(frozen["members"]) != len(member_map):
        raise Q0EvidenceError("q0 donor availability member inventory is incomplete")
    donor_sets = read_tsv(resolve("metadata/grt_donor_sets.tsv"), ["donor_set_id", "donor_kind", "manifest_relpath", "fasta_relpath", "fasta_sha256", "member_count"])
    donor_records = {}
    if len({row["donor_set_id"] for row in donor_sets}) != len(donor_sets):
        raise Q0EvidenceError("duplicate frozen donor set")
    for donor_set in donor_sets:
        set_id = donor_set["donor_set_id"]
        rows_for_set = [row for (candidate_set, _), row in member_map.items() if candidate_set == set_id]
        if len(rows_for_set) != int(donor_set["member_count"]):
            raise Q0EvidenceError("frozen donor member count differs from its set")
        if read_tsv(resolve(donor_set["manifest_relpath"]), DONOR_MEMBER_FIELDS) != rows_for_set:
            raise Q0EvidenceError("frozen donor manifest differs from member registry")
        fasta = resolve(donor_set["fasta_relpath"])
        records = dict(read_fasta(fasta)) if fasta.stat().st_size else {}
        if set(records) != {row["fasta_record_name"] for row in rows_for_set}:
            raise Q0EvidenceError("frozen donor FASTA inventory differs from its manifest")
        donor_records[set_id] = records
    seen = set()
    for row in frozen["members"]:
        key = (row["donor_set_id"], row["member_id"])
        member = member_map.get(key)
        source = SourceKey(**row["source"])
        if key in seen or member is None or (member["dataset_name"], member["contig_name"]) != (source.dataset, source.contig):
            raise Q0EvidenceError("invalid q0 donor availability member")
        seen.add(key)
        sequence = sources[(source.dataset, source.contig)]
        if (member["source_start"] != "1" or member["source_end"] != str(len(sequence)) or member["orientation"] != "+"
                or donor_records[key[0]].get(member["fasta_record_name"]) != sequence
                or member["sequence_sha256"] != sha256_bytes(sequence.encode("ascii"))):
            raise Q0EvidenceError("donor context differs from complete original source")
        if row["available_member_intervals"] != [asdict(i) for i in available[(source.dataset, source.contig)]]:
            raise Q0EvidenceError("q0 donor member authorization differs from source availability")
    q0_evidence = [row for row in read_tsv(resolve("metadata/grt_evidence_registry.tsv"), EVIDENCE_FIELDS) if row["stage"] == "q0_construction"]
    if row_hash(q0_evidence, EVIDENCE_FIELDS) != frozen["q0_evidence_sha256"]:
        raise Q0EvidenceError("q0 selection evidence registry changed")
    return frozen
