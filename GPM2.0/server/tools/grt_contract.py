#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath


DEFAULT_SCHEMA_PATH = Path(__file__).parents[1] / "contracts" / "grt_precomputed_v1.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TRUE_VALUES = {"true"}
FALSE_VALUES = {"false"}


class ContractError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self):
        return f"{self.code}: {self.message}"


def fail(code, message):
    raise ContractError(code, message)


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_sha256(value, label):
    if not SHA256_RE.fullmatch(value or ""):
        fail("INVALID_VALUE", f"{label} must be a lowercase SHA-256")


def parse_bool(value, label):
    normalized = (value or "").strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    fail("INVALID_VALUE", f"{label} must be true or false")


def parse_int(value, label, minimum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        fail("INVALID_VALUE", f"{label} must be an integer")
    if minimum is not None and parsed < minimum:
        fail("INVALID_COORDINATE" if minimum == 1 else "INVALID_VALUE", f"{label} must be >= {minimum}")
    return parsed


def parse_float(value, label, minimum=None, maximum=None):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        fail("INVALID_VALUE", f"{label} must be numeric")
    if minimum is not None and parsed < minimum:
        fail("INVALID_VALUE", f"{label} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        fail("INVALID_VALUE", f"{label} must be <= {maximum}")
    return parsed


def parse_json(value, label, expected_type=None):
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        fail("INVALID_JSON", f"{label}: {exc}")
    if expected_type is not None and not isinstance(parsed, expected_type):
        fail("INVALID_JSON", f"{label} must contain {expected_type.__name__}")
    return parsed


def event_is_path_producing(event):
    return event["action"] in {
        "fill",
        "patch",
        "refill",
        "extend_telomere",
    } or (
        event["action"] == "replace"
        and event.get("edit", {}).get("replacement_kind") == "source"
    )


def safe_relative_path(value, label):
    if not value:
        fail("INVALID_PATH", f"{label} is empty")
    if "\\" in value:
        fail("INVALID_PATH", f"{label} contains a backslash")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        fail("INVALID_PATH", f"{label} is not a safe relative path: {value}")
    return path


def bundle_path(bundle_root, relpath, label, required=True):
    relative = safe_relative_path(relpath, label)
    path = bundle_root.joinpath(*relative.parts)
    if required and (not path.exists() or not path.is_file()):
        fail("MISSING_REQUIRED_FILE", f"{label} does not exist: {relpath}")
    try:
        path.resolve().relative_to(bundle_root.resolve())
    except ValueError:
        fail("INVALID_PATH", f"{label} escapes bundle root: {relpath}")
    return path


def read_tsv(bundle_root, relpath, table_spec):
    path = bundle_path(bundle_root, relpath, relpath)
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            header = list(reader.fieldnames or [])
            expected_header = table_spec["header"]
            if header != expected_header:
                fail("INVALID_TSV", f"{relpath} header must be {expected_header}, got {header}")
            rows = list(reader)
    except UnicodeDecodeError as exc:
        fail("INVALID_TSV", f"{relpath} is not UTF-8: {exc}")
    minimum = table_spec.get("min_rows", 0)
    maximum = table_spec.get("max_rows")
    if len(rows) < minimum:
        fail("INVALID_TSV", f"{relpath} requires at least {minimum} data rows")
    if maximum is not None and len(rows) > maximum:
        fail("INVALID_TSV", f"{relpath} allows at most {maximum} data rows")
    return rows


def read_json_file(bundle_root, relpath):
    path = bundle_path(bundle_root, relpath, relpath)
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("INVALID_JSON", f"{relpath}: {exc}")


def read_jsonl(bundle_root, relpath):
    path = bundle_path(bundle_root, relpath, relpath)
    rows = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    fail("INVALID_JSON", f"{relpath}:{line_number}: {exc}")
                if not isinstance(value, dict):
                    fail("INVALID_JSON", f"{relpath}:{line_number} must contain an object")
                rows.append(value)
    except UnicodeDecodeError as exc:
        fail("INVALID_JSON", f"{relpath} is not UTF-8: {exc}")
    return rows


def read_fasta(path, label, allow_empty=False):
    records = {}
    current_name = None
    chunks = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith(">"):
                    if current_name is not None:
                        records[current_name] = "".join(chunks).upper()
                    current_name = stripped[1:].split()[0]
                    if not current_name or current_name in records:
                        fail("INVALID_FASTA", f"{label}:{line_number} has an empty or duplicate record")
                    chunks = []
                else:
                    if current_name is None:
                        fail("INVALID_FASTA", f"{label}:{line_number} has sequence before header")
                    sequence = "".join(stripped.split()).upper()
                    if not re.fullmatch(r"[ACGTRYSWKMBDHVN]+", sequence):
                        fail("INVALID_FASTA", f"{label}:{line_number} has unsupported bases")
                    chunks.append(sequence)
    except UnicodeDecodeError as exc:
        fail("INVALID_FASTA", f"{label} is not UTF-8: {exc}")
    if current_name is not None:
        records[current_name] = "".join(chunks).upper()
    if not records and allow_empty:
        return records
    if not records or any(not sequence for sequence in records.values()):
        fail("INVALID_FASTA", f"{label} has no non-empty records")
    return records


def unique_index(rows, key, relpath):
    result = {}
    for row_number, row in enumerate(rows, start=2):
        value = (row.get(key) or "").strip()
        if not value:
            fail("INVALID_VALUE", f"{relpath}:{row_number} has empty {key}")
        if value in result:
            fail("DUPLICATE_ID", f"{relpath} duplicates {key}={value}")
        result[value] = row
    return result


def validate_interval(start_value, end_value, label):
    start = parse_int(start_value, f"{label}.start", 1)
    end = parse_int(end_value, f"{label}.end", 1)
    if end < start:
        fail("INVALID_COORDINATE", f"{label} must satisfy start <= end")
    return start, end


def validate_artifact(bundle_root, relpath, expected_sha, label):
    validate_sha256(expected_sha, f"{label}.sha256")
    path = bundle_path(bundle_root, relpath, label)
    actual = sha256_file(path)
    if actual != expected_sha:
        fail("CHECKSUM_MISMATCH", f"{label} expected {expected_sha}, got {actual}")
    return path


def source_catalog(bundle_root, locator_rows):
    catalog = {}
    fasta_cache = {}
    for row_number, row in enumerate(locator_rows, start=2):
        dataset = (row["dataset_name"] or "").strip()
        contig = (row["seq_name"] or "").strip()
        if not dataset or not contig:
            fail("INVALID_VALUE", f"metadata/source_seq_locator.tsv:{row_number} has empty source identity")
        key = (dataset, contig)
        if key in catalog:
            fail("DUPLICATE_ID", f"duplicate source locator for {dataset}:{contig}")
        relpath = row["fasta_relpath"]
        path = bundle_path(bundle_root, relpath, f"source locator {dataset}:{contig}")
        if relpath not in fasta_cache:
            fasta_cache[relpath] = read_fasta(path, relpath)
        if contig not in fasta_cache[relpath]:
            fail("BROKEN_REFERENCE", f"source locator {dataset}:{contig} is absent from {relpath}")
        catalog[key] = fasta_cache[relpath][contig]
    return catalog


def reverse_complement(sequence):
    return sequence.translate(
        str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")
    )[::-1]


def validate_contract(bundle_root, schema_path=DEFAULT_SCHEMA_PATH):
    bundle_root = Path(bundle_root).resolve()
    if not bundle_root.is_dir():
        fail("MISSING_BUNDLE", f"bundle directory does not exist: {bundle_root}")
    try:
        with Path(schema_path).open("r", encoding="utf-8") as handle:
            schema = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        fail("INVALID_SCHEMA", f"cannot load contract schema: {exc}")

    for relpath in schema["required_files"]:
        bundle_path(bundle_root, relpath, relpath)

    tables = {
        relpath: read_tsv(bundle_root, relpath, table_spec)
        for relpath, table_spec in schema["tables"].items()
    }
    enums = schema["enums"]

    package = tables["metadata/package.tsv"][0]
    if package["workflow"] != schema["workflow"] or package["schema_version"] != schema["schema_version"]:
        fail(
            "UNSUPPORTED_SCHEMA",
            f"expected workflow={schema['workflow']} schema_version={schema['schema_version']}",
        )
    if package["final_path_schema_version"] != schema["final_path_schema_version"]:
        fail("UNSUPPORTED_SCHEMA", "unsupported final_path_schema_version")
    if not parse_bool(package["grt_precompute_enabled"], "package.grt_precompute_enabled"):
        fail("INVALID_VALUE", "package.grt_precompute_enabled must be true")
    if not parse_bool(package["recipe_locked"], "package.recipe_locked"):
        fail("INVALID_VALUE", "package.recipe_locked must be true")
    reads_qc_enabled = parse_bool(package["reads_qc_enabled"], "package.reads_qc_enabled")
    parse_bool(package["preassigned_chr"], "package.preassigned_chr")
    parse_float(
        package["chr_assignment_min_coverage_percent"],
        "package.chr_assignment_min_coverage_percent",
        0,
        100,
    )

    dataset_rows = tables["metadata/datasets.tsv"]
    dataset_names = set()
    for row_number, row in enumerate(dataset_rows, start=2):
        dataset_name = row["dataset_name"].strip()
        if not dataset_name or dataset_name in dataset_names:
            fail("DUPLICATE_ID", f"metadata/datasets.tsv:{row_number} has empty or duplicate dataset_name")
        dataset_names.add(dataset_name)
        bundle_path(bundle_root, row["fasta_relpath"], f"dataset {dataset_name} FASTA")
        bundle_path(bundle_root, row["fai_relpath"], f"dataset {dataset_name} FAI")
        parse_bool(row["self_alignment_available"], f"dataset {dataset_name}.self_alignment_available")

    reference = tables["metadata/reference.tsv"][0]
    bundle_path(bundle_root, reference["fasta_relpath"], "reference FASTA")
    bundle_path(bundle_root, reference["fai_relpath"], "reference FAI")
    sources = source_catalog(bundle_root, tables["metadata/source_seq_locator.tsv"])

    recipe = tables["metadata/grt_recipe.tsv"][0]
    if recipe["primary_dataset"] not in dataset_names:
        fail("BROKEN_REFERENCE", "recipe primary_dataset is absent from datasets.tsv")
    support_datasets = parse_json(recipe["support_datasets_json"], "recipe.support_datasets_json", list)
    if any(not isinstance(value, str) or value not in dataset_names for value in support_datasets):
        fail("BROKEN_REFERENCE", "recipe support_datasets_json references an unknown dataset")
    if recipe["primary_dataset"] in support_datasets or len(support_datasets) != len(set(support_datasets)):
        fail("INVALID_VALUE", "recipe support datasets must be unique and exclude primary")
    recipe_dataset_names = {recipe["primary_dataset"], *support_datasets}
    if parse_bool(recipe["reads_qc_enabled"], "recipe.reads_qc_enabled") != reads_qc_enabled:
        fail("INVALID_VALUE", "recipe and package reads_qc_enabled disagree")
    q0_path = bundle_path(bundle_root, recipe["q0_relpath"], "recipe.q0_relpath")
    q4_path = bundle_path(bundle_root, recipe["final_q_relpath"], "recipe.final_q_relpath")
    if recipe["q0_relpath"] != "grt/q/q0.fa" or recipe["final_q_relpath"] != "grt/q/q4.fa":
        fail("INVALID_VALUE", "recipe q paths must identify q0.fa and q4.fa")

    role_keys = set()
    for row_number, row in enumerate(tables["metadata/grt_contig_roles.tsv"], start=2):
        key = (row["dataset_name"], row["contig_name"])
        if key not in sources:
            fail("BROKEN_REFERENCE", f"contig role references unknown source {key[0]}:{key[1]}")
        if key in role_keys:
            fail("DUPLICATE_ID", f"duplicate contig role for {key[0]}:{key[1]}")
        role_keys.add(key)
        for field in ("q_eligible", "donor_eligible", "tel_donor_eligible"):
            parse_bool(row[field], f"grt_contig_roles.tsv:{row_number}.{field}")
    expected_role_keys = {key for key in sources if key[0] in recipe_dataset_names}
    if role_keys != expected_role_keys:
        fail(
            "BROKEN_REFERENCE",
            "contig roles must cover every source from the locked initial recipe exactly once",
        )

    q_segment_rows = tables["metadata/grt_q_segments.tsv"]
    q_segment_ids = set()
    q_segments_by_record = defaultdict(list)
    q_segment_evidence = {}
    for row_number, row in enumerate(q_segment_rows, start=2):
        q_version = row["q_version"]
        chr_name = row["chr"]
        segment_id = row["segment_id"]
        segment_kind = row["segment_kind"]
        if not q_version or not chr_name or not segment_id:
            fail("INVALID_VALUE", f"grt_q_segments.tsv:{row_number} has empty identity")
        if segment_kind not in enums["q_segment_kind"]:
            fail("INVALID_VALUE", f"q segment {segment_id} has invalid segment_kind")
        if segment_id in q_segment_ids:
            fail("DUPLICATE_ID", f"duplicate q segment_id={segment_id}")
        q_segment_ids.add(segment_id)
        q_start, q_end = validate_interval(row["q_start"], row["q_end"], f"q segment {segment_id}.q")
        evidence_ids = parse_json(
            row["evidence_ids_json"], f"q segment {segment_id}.evidence_ids_json", list
        )
        if segment_kind == "gap":
            source_fields = [
                row["dataset_name"],
                row["contig_name"],
                row["source_start"],
                row["source_end"],
                row["orientation"],
                row["source_card_key"],
            ]
            if any(source_fields) or evidence_ids:
                fail("INVALID_VALUE", f"q gap segment {segment_id} cannot carry source/evidence")
            sequence = "N" * (q_end - q_start + 1)
        else:
            source_start, source_end = validate_interval(
                row["source_start"], row["source_end"], f"q segment {segment_id}.source"
            )
            source_key = (row["dataset_name"], row["contig_name"])
            if source_key not in sources:
                fail("BROKEN_REFERENCE", f"q segment {segment_id} references unknown source")
            if source_end > len(sources[source_key]) or q_end - q_start != source_end - source_start:
                fail("INVALID_COORDINATE", f"q segment {segment_id} q/source lengths differ")
            if row["orientation"] not in enums["orientation"]:
                fail("INVALID_VALUE", f"q segment {segment_id} has invalid orientation")
            if not row["source_card_key"]:
                fail("BROKEN_REFERENCE", f"q segment {segment_id} lacks source_card_key")
            if not evidence_ids:
                fail("BROKEN_REFERENCE", f"q segment {segment_id} lacks source evidence")
            sequence = sources[source_key][source_start - 1 : source_end]
            if row["orientation"] == "-":
                sequence = reverse_complement(sequence)
        q_segment_evidence[segment_id] = evidence_ids
        q_segments_by_record[(q_version, chr_name)].append((q_start, q_end, sequence, segment_id))

    q_fasta_cache = {}
    for (q_version, chr_name), segments in q_segments_by_record.items():
        q_path = bundle_path(bundle_root, f"grt/q/{q_version}.fa", f"q segment version {q_version}")
        if q_version not in q_fasta_cache:
            q_fasta_cache[q_version] = read_fasta(q_path, f"grt/q/{q_version}.fa")
        if chr_name not in q_fasta_cache[q_version]:
            fail("BROKEN_REFERENCE", f"q segments reference missing {q_version}:{chr_name}")
        segments.sort(key=lambda value: value[0])
        expected_start = 1
        rebuilt = []
        for q_start, q_end, sequence, segment_id in segments:
            if q_start != expected_start:
                fail("INVALID_COORDINATE", f"q segment {segment_id} is not contiguous")
            expected_start = q_end + 1
            rebuilt.append(sequence)
        if "".join(rebuilt) != q_fasta_cache[q_version][chr_name]:
            fail("FINAL_PATH_MISMATCH", f"q segments do not reconstruct {q_version}:{chr_name}")
    q0_records = read_fasta(q0_path, recipe["q0_relpath"])
    q0_segment_records = {chr_name for q_version, chr_name in q_segments_by_record if q_version == "q0"}
    if q0_segment_records != set(q0_records):
        fail("BROKEN_REFERENCE", "q0 segment mapping does not cover every q0 record")

    donor_sets = unique_index(tables["metadata/grt_donor_sets.tsv"], "donor_set_id", "metadata/grt_donor_sets.tsv")
    donor_kinds = Counter()
    donor_fasta_records = {}
    for donor_set_id, row in donor_sets.items():
        donor_kind = row["donor_kind"]
        if donor_kind not in enums["donor_kind"]:
            fail("INVALID_VALUE", f"unknown donor_kind={donor_kind}")
        donor_kinds[donor_kind] += 1
        parse_int(row["member_count"], f"donor set {donor_set_id}.member_count", 0)
        donor_fasta_path = validate_artifact(
            bundle_root,
            row["fasta_relpath"],
            row["fasta_sha256"],
            f"donor set {donor_set_id} FASTA",
        )
        donor_fasta_records[donor_set_id] = read_fasta(
            donor_fasta_path, f"donor set {donor_set_id} FASTA", allow_empty=True
        )
        bundle_path(bundle_root, row["manifest_relpath"], f"donor set {donor_set_id} manifest")
    if donor_kinds != Counter({"ordinary": 1, "telomere": 1}):
        fail("INVALID_VALUE", "contract requires exactly one ordinary and one telomere donor set")
    for field in ("donor_set_id", "tel_donor_set_id"):
        if recipe[field] not in donor_sets:
            fail("BROKEN_REFERENCE", f"recipe {field} references unknown donor set")
    if donor_sets[recipe["donor_set_id"]]["donor_kind"] != "ordinary":
        fail("BROKEN_REFERENCE", "recipe donor_set_id must reference ordinary donor set")
    if donor_sets[recipe["tel_donor_set_id"]]["donor_kind"] != "telomere":
        fail("BROKEN_REFERENCE", "recipe tel_donor_set_id must reference telomere donor set")

    member_rows = tables["metadata/grt_donor_members.tsv"]
    members = {}
    members_by_set = defaultdict(list)
    for row_number, row in enumerate(member_rows, start=2):
        donor_set_id = row["donor_set_id"]
        if donor_set_id not in donor_sets:
            fail("BROKEN_REFERENCE", f"donor member references unknown donor_set_id={donor_set_id}")
        member_id = row["member_id"]
        member_key = (donor_set_id, member_id)
        if not member_id or member_key in members:
            fail("DUPLICATE_ID", f"duplicate donor member {donor_set_id}:{member_id}")
        source_key = (row["dataset_name"], row["contig_name"])
        if source_key not in sources:
            fail("BROKEN_REFERENCE", f"donor member references unknown source {source_key[0]}:{source_key[1]}")
        start, end = validate_interval(row["source_start"], row["source_end"], f"donor member {member_id}")
        if end > len(sources[source_key]):
            fail("INVALID_COORDINATE", f"donor member {member_id} exceeds source length")
        if row["orientation"] not in enums["orientation"]:
            fail("INVALID_VALUE", f"donor member {member_id} has invalid orientation")
        validate_sha256(row["sequence_sha256"], f"donor member {member_id}.sequence_sha256")
        source_slice = sources[source_key][start - 1 : end]
        if row["orientation"] == "-":
            source_slice = reverse_complement(source_slice)
        if sha256_bytes(source_slice.encode("ascii")) != row["sequence_sha256"]:
            fail("CHECKSUM_MISMATCH", f"donor member {member_id} sequence_sha256 does not match source slice")
        fasta_record_name = row["fasta_record_name"]
        if fasta_record_name not in donor_fasta_records[donor_set_id]:
            fail("BROKEN_REFERENCE", f"donor member {member_id} FASTA record is missing")
        if donor_fasta_records[donor_set_id][fasta_record_name] != source_slice:
            fail("CHECKSUM_MISMATCH", f"donor member {member_id} FASTA sequence differs from source")
        members[member_key] = row
        members_by_set[donor_set_id].append(row)
    for donor_set_id, donor_set in donor_sets.items():
        expected_count = parse_int(donor_set["member_count"], f"donor set {donor_set_id}.member_count", 0)
        if len(members_by_set[donor_set_id]) != expected_count:
            fail("COUNT_MISMATCH", f"donor set {donor_set_id} member_count does not match metadata rows")
        manifest_path = bundle_path(bundle_root, donor_set["manifest_relpath"], f"donor set {donor_set_id} manifest")
        with manifest_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if list(reader.fieldnames or []) != schema["tables"]["metadata/grt_donor_members.tsv"]["header"]:
                fail("INVALID_TSV", f"donor set {donor_set_id} manifest header is invalid")
            manifest_rows = list(reader)
        if manifest_rows != members_by_set[donor_set_id]:
            fail("BROKEN_REFERENCE", f"donor set {donor_set_id} manifest differs from member registry")
        expected_records = {row["fasta_record_name"] for row in members_by_set[donor_set_id]}
        if set(donor_fasta_records[donor_set_id]) != expected_records:
            fail("BROKEN_REFERENCE", f"donor set {donor_set_id} FASTA records differ from manifest")

    evidence_rows = tables["metadata/grt_evidence_registry.tsv"]
    evidence = unique_index(evidence_rows, "evidence_id", "metadata/grt_evidence_registry.tsv")
    for evidence_id, row in evidence.items():
        if row["stage"] not in enums["evidence_stage"]:
            fail("INVALID_VALUE", f"evidence {evidence_id} has invalid stage")
        if row["status"] not in enums["evidence_status"]:
            fail("INVALID_VALUE", f"evidence {evidence_id} has invalid status")
        if row["coordinate_system"] not in enums["coordinate_system"]:
            fail("INVALID_VALUE", f"evidence {evidence_id} has invalid coordinate_system")
        if row["projection_status"] not in enums["projection_status"]:
            fail("INVALID_VALUE", f"evidence {evidence_id} has invalid projection_status")
        parse_json(row["parameters_json"], f"evidence {evidence_id}.parameters_json", dict)
        source_fields = [row["source_dataset"], row["source_contig"], row["source_start"], row["source_end"]]
        if any(source_fields):
            if not all(source_fields):
                fail("INVALID_VALUE", f"evidence {evidence_id} has partial source identity")
            source_key = (row["source_dataset"], row["source_contig"])
            if source_key not in sources:
                fail("BROKEN_REFERENCE", f"evidence {evidence_id} references unknown source")
            start, end = validate_interval(row["source_start"], row["source_end"], f"evidence {evidence_id}.source")
            if end > len(sources[source_key]):
                fail("INVALID_COORDINATE", f"evidence {evidence_id} source exceeds source length")
            if row["orientation"] not in enums["orientation"]:
                fail("INVALID_VALUE", f"evidence {evidence_id} has invalid orientation")
        target_fields = [row["target_start"], row["target_end"]]
        if any(target_fields):
            if not all(target_fields) or not row["target_chr"]:
                fail("INVALID_VALUE", f"evidence {evidence_id} has partial target interval")
            validate_interval(row["target_start"], row["target_end"], f"evidence {evidence_id}.target")
        for path_field, hash_field in (
            ("query_artifact_relpath", "query_sha256"),
            ("target_artifact_relpath", "target_sha256"),
        ):
            if row[path_field] or row[hash_field]:
                if not row[path_field] or not row[hash_field]:
                    fail("INVALID_VALUE", f"evidence {evidence_id} has partial artifact identity")
                validate_artifact(
                    bundle_root,
                    row[path_field],
                    row[hash_field],
                    f"evidence {evidence_id}.{path_field}",
                )
        validate_artifact(
            bundle_root,
            row["raw_artifact_relpath"],
            row["raw_artifact_sha256"],
            f"evidence {evidence_id}.raw_artifact",
        )
        if row["q_version"]:
            q_path = bundle_path(
                bundle_root,
                f"grt/q/{row['q_version']}.fa",
                f"evidence {evidence_id} q source",
            )
            validate_sha256(row["q_source_sha256"], f"evidence {evidence_id}.q_source_sha256")
            if sha256_file(q_path) != row["q_source_sha256"]:
                fail("CHECKSUM_MISMATCH", f"evidence {evidence_id} q source hash mismatch")
        elif row["q_source_sha256"]:
            fail("INVALID_VALUE", f"evidence {evidence_id} has q hash without q_version")
        if row["donor_set_id"]:
            if row["donor_set_id"] not in donor_sets:
                fail("BROKEN_REFERENCE", f"evidence {evidence_id} references unknown donor set")
            if row["target_sha256"] != donor_sets[row["donor_set_id"]]["fasta_sha256"]:
                fail("CHECKSUM_MISMATCH", f"evidence {evidence_id} target hash differs from donor set")

    for segment_id, evidence_ids in q_segment_evidence.items():
        if any(evidence_id not in evidence for evidence_id in evidence_ids):
            fail("BROKEN_REFERENCE", f"q segment {segment_id} references unknown evidence")

    usage_rows = tables["metadata/grt_donor_usage.tsv"]
    usage = unique_index(usage_rows, "usage_id", "metadata/grt_donor_usage.tsv")
    for usage_id, row in usage.items():
        member_key = (row["donor_set_id"], row["member_id"])
        if member_key not in members:
            fail("BROKEN_REFERENCE", f"usage {usage_id} references unknown donor member")
        if row["status"] not in enums["usage_status"]:
            fail("INVALID_VALUE", f"usage {usage_id} has invalid status")
        if row["stage"] not in enums["event_stage"]:
            fail("INVALID_VALUE", f"usage {usage_id} has invalid stage")
        start, end = validate_interval(row["source_start"], row["source_end"], f"usage {usage_id}.source")
        member = members[member_key]
        if (row["source_dataset"], row["source_contig"]) != (member["dataset_name"], member["contig_name"]):
            fail("BROKEN_REFERENCE", f"usage {usage_id} source identity differs from donor member")
        member_start = int(member["source_start"])
        member_end = int(member["source_end"])
        if start < member_start or end > member_end:
            fail("INVALID_COORDINATE", f"usage {usage_id} is outside donor member interval")
        if row["status"] in {"accepted", "consumed"} and not row["event_id"]:
            fail("BROKEN_REFERENCE", f"usage {usage_id} accepted/consumed row lacks event")

    events = unique_index(read_jsonl(bundle_root, "metadata/grt_events.jsonl"), "event_id", "metadata/grt_events.jsonl")
    required_event_fields = set(schema["event_required_fields"])
    for event_id, event in events.items():
        missing = sorted(required_event_fields - set(event))
        if missing:
            fail("INVALID_JSON", f"event {event_id} is missing fields: {missing}")
        if event["status"] not in enums["event_status"]:
            fail("INVALID_VALUE", f"event {event_id} has invalid status")
        if event["stage"] not in enums["event_stage"]:
            fail("INVALID_VALUE", f"event {event_id} has invalid stage")
        if event["action"] not in enums["event_action"]:
            fail("INVALID_VALUE", f"event {event_id} has invalid action")
        if not isinstance(event["evidence_ids"], list) or not isinstance(event["usage_ids"], list):
            fail("INVALID_JSON", f"event {event_id} evidence_ids and usage_ids must be arrays")
        for evidence_id in event["evidence_ids"]:
            if evidence_id not in evidence:
                fail("BROKEN_REFERENCE", f"event {event_id} references unknown evidence {evidence_id}")
        for usage_id in event["usage_ids"]:
            if usage_id not in usage:
                fail("BROKEN_REFERENCE", f"event {event_id} references unknown usage {usage_id}")
        for q_field in ("q_before", "q_after"):
            q_value = event[q_field]
            if not isinstance(q_value, dict) or set(q_value) != {"version", "start", "end", "sha256"}:
                fail("INVALID_JSON", f"event {event_id}.{q_field} has invalid shape")
            validate_interval(q_value["start"], q_value["end"], f"event {event_id}.{q_field}")
            validate_sha256(q_value["sha256"], f"event {event_id}.{q_field}.sha256")
            q_path = bundle_path(
                bundle_root,
                f"grt/q/{q_value['version']}.fa",
                f"event {event_id}.{q_field} q artifact",
            )
            if sha256_file(q_path) != q_value["sha256"]:
                fail("CHECKSUM_MISMATCH", f"event {event_id}.{q_field} q hash mismatch")
            q_records = read_fasta(q_path, f"event {event_id}.{q_field} q artifact")
            if event["chr"] not in q_records or int(q_value["end"]) > len(q_records[event["chr"]]):
                fail("INVALID_COORDINATE", f"event {event_id}.{q_field} exceeds q chromosome")
        source = event["source"]
        if source is not None:
            expected_source_fields = {
                "dataset",
                "contig",
                "start",
                "end",
                "orientation",
                "original_assignment",
            }
            if not isinstance(source, dict) or set(source) != expected_source_fields:
                fail("INVALID_JSON", f"event {event_id}.source has invalid shape")
            source_key = (source["dataset"], source["contig"])
            if source_key not in sources:
                fail("BROKEN_REFERENCE", f"event {event_id} references unknown source")
            start, end = validate_interval(source["start"], source["end"], f"event {event_id}.source")
            if end > len(sources[source_key]):
                fail("INVALID_COORDINATE", f"event {event_id} source exceeds source length")
            if (
                source["orientation"] not in enums["orientation"]
                or source["original_assignment"] not in enums["original_assignment"]
            ):
                fail("INVALID_VALUE", f"event {event_id} source enum is invalid")

    for usage_id, row in usage.items():
        if row["event_id"] and row["event_id"] not in events:
            fail("BROKEN_REFERENCE", f"usage {usage_id} references unknown event {row['event_id']}")

    for event_id, event in events.items():
        superseded_by = event.get("superseded_by_event_id")
        if event["status"] == "superseded":
            if not isinstance(superseded_by, str) or superseded_by not in events:
                fail("BROKEN_REFERENCE", f"superseded event {event_id} lacks its replacing event")
            replacement = events[superseded_by]
            if replacement["status"] != "accepted" or replacement["action"] not in {
                "filter_component",
                "delete",
                "replace",
                "correct_boundary",
                "patch",
                "refill",
                "extend_telomere",
            }:
                fail("BROKEN_REFERENCE", f"superseded event {event_id} has an invalid replacing event")
            if event_id not in replacement.get("superseded_event_ids", []):
                fail("BROKEN_REFERENCE", f"superseded event {event_id} is not linked bidirectionally")
        elif superseded_by is not None:
            fail("INVALID_VALUE", f"non-superseded event {event_id} declares superseded_by_event_id")
        superseded_ids = event.get("superseded_event_ids", [])
        if not isinstance(superseded_ids, list):
            fail("INVALID_JSON", f"event {event_id}.superseded_event_ids must be an array")
        for superseded_id in superseded_ids:
            if (
                superseded_id not in events
                or events[superseded_id].get("superseded_by_event_id") != event_id
            ):
                fail("BROKEN_REFERENCE", f"event {event_id} has an invalid superseded event link")

    final_path = read_json_file(bundle_root, "metadata/grt_final_path.json")
    if (
        final_path.get("workflow") != schema["workflow"]
        or str(final_path.get("schema_version")) != schema["final_path_schema_version"]
    ):
        fail("UNSUPPORTED_SCHEMA", "grt_final_path.json has unsupported workflow/schema")
    if final_path.get("q4_relpath") != recipe["final_q_relpath"]:
        fail("BROKEN_REFERENCE", "grt_final_path q4_relpath differs from recipe")
    chromosomes = final_path.get("chromosomes")
    if not isinstance(chromosomes, list) or not chromosomes:
        fail("INVALID_JSON", "grt_final_path chromosomes must be a non-empty array")
    q4_records = read_fasta(q4_path, recipe["final_q_relpath"])
    segment_ids = set()
    segment_event = {}
    chromosome_names = set()
    for chromosome in chromosomes:
        if not isinstance(chromosome, dict):
            fail("INVALID_JSON", "final path chromosome must be an object")
        chr_name = chromosome.get("chr")
        if not chr_name or chr_name in chromosome_names or chr_name not in q4_records:
            fail("BROKEN_REFERENCE", f"invalid or duplicate final path chromosome: {chr_name}")
        chromosome_names.add(chr_name)
        q4_sequence = q4_records[chr_name]
        if parse_int(chromosome.get("q4_length"), f"final path {chr_name}.q4_length", 1) != len(q4_sequence):
            fail("FINAL_PATH_MISMATCH", f"final path {chr_name} q4 length mismatch")
        validate_sha256(chromosome.get("q4_sha256"), f"final path {chr_name}.q4_sha256")
        if sha256_bytes(q4_sequence.encode("ascii")) != chromosome["q4_sha256"]:
            fail("CHECKSUM_MISMATCH", f"final path {chr_name} q4 sequence hash mismatch")
        segments = chromosome.get("segments")
        if not isinstance(segments, list) or not segments:
            fail("INVALID_JSON", f"final path {chr_name}.segments must be a non-empty array")
        rebuilt = []
        for segment in segments:
            if not isinstance(segment, dict):
                fail("INVALID_JSON", f"final path {chr_name} segment must be an object")
            segment_id = segment.get("segment_id")
            kind = segment.get("kind")
            if not segment_id or segment_id in segment_ids:
                fail("DUPLICATE_ID", f"invalid or duplicate Final Path segment_id={segment_id}")
            segment_ids.add(segment_id)
            if kind not in enums["segment_kind"]:
                fail("INVALID_VALUE", f"segment {segment_id} has invalid kind")
            length = parse_int(segment.get("length"), f"segment {segment_id}.length", 1)
            evidence_ids = segment.get("evidence_ids")
            if not isinstance(evidence_ids, list):
                fail("INVALID_JSON", f"segment {segment_id}.evidence_ids must be an array")
            for evidence_id in evidence_ids:
                if evidence_id not in evidence:
                    fail("BROKEN_REFERENCE", f"segment {segment_id} references unknown evidence {evidence_id}")
            event_id = segment.get("event_id")
            if event_id:
                if event_id not in events:
                    fail("BROKEN_REFERENCE", f"segment {segment_id} references unknown event {event_id}")
                if events[event_id]["status"] != "accepted":
                    fail("BROKEN_REFERENCE", f"segment {segment_id} references a non-accepted event")
                segment_event[segment_id] = event_id
            if kind == "gap":
                if segment.get("source") is not None or event_id:
                    fail("INVALID_VALUE", f"gap segment {segment_id} cannot have source/event")
                rebuilt.append("N" * length)
                continue
            if segment.get("orientation") not in enums["orientation"]:
                fail("INVALID_VALUE", f"segment {segment_id} has invalid orientation")
            source = segment.get("source")
            if not isinstance(source, dict) or set(source) != {"dataset", "contig", "start", "end", "orientation"}:
                fail("INVALID_JSON", f"segment {segment_id}.source has invalid shape")
            source_key = (source["dataset"], source["contig"])
            if source_key not in sources:
                fail("BROKEN_REFERENCE", f"segment {segment_id} references unknown source")
            start, end = validate_interval(source["start"], source["end"], f"segment {segment_id}.source")
            if end > len(sources[source_key]) or end - start + 1 != length:
                fail("INVALID_COORDINATE", f"segment {segment_id} source interval does not match length")
            orientation = source["orientation"]
            if orientation not in enums["orientation"]:
                fail("INVALID_VALUE", f"segment {segment_id} has invalid source orientation")
            if segment["orientation"] != orientation:
                fail("INVALID_VALUE", f"segment {segment_id} orientation differs from source")
            sequence = sources[source_key][start - 1 : end]
            rebuilt.append(sequence if orientation == "+" else reverse_complement(sequence))
            if kind in {"patch", "correction", "telomere"} and not event_id:
                fail("BROKEN_REFERENCE", f"GRT segment {segment_id} lacks accepted event")
        if "".join(rebuilt) != q4_sequence:
            fail("FINAL_PATH_MISMATCH", f"Final Path segments do not reconstruct q4 chromosome {chr_name}")
    if chromosome_names != set(q4_records):
        fail("FINAL_PATH_MISMATCH", "Final Path chromosome set differs from q4 FASTA")

    for event_id, event in events.items():
        segment_id = event["final_path_segment_id"]
        if event["status"] == "accepted" and segment_id:
            if segment_id not in segment_ids:
                fail("BROKEN_REFERENCE", f"accepted event {event_id} references an unknown Final Path segment")
            if segment_event.get(segment_id) != event_id:
                fail("BROKEN_REFERENCE", f"accepted event {event_id} and segment {segment_id} are not bidirectional")
        elif event["status"] == "accepted" and event_is_path_producing(event):
            fail("BROKEN_REFERENCE", f"accepted path-producing event {event_id} lacks a Final Path segment")

    for usage_id, row in usage.items():
        if row["final_path_segment_id"] and row["final_path_segment_id"] not in segment_ids:
            fail("BROKEN_REFERENCE", f"usage {usage_id} references unknown Final Path segment")
        if row["status"] in {"accepted", "consumed"}:
            event = events[row["event_id"]]
            if event_is_path_producing(event) and not row["final_path_segment_id"]:
                fail("BROKEN_REFERENCE", f"usage {usage_id} for a path-producing event lacks a segment")

    used_contigs = unique_index(
        tables["metadata/grt_used_contigs.tsv"],
        "source_card_key",
        "metadata/grt_used_contigs.tsv",
    )
    for source_card_key, row in used_contigs.items():
        source_key = (row["dataset_name"], row["contig_name"])
        if source_key not in sources:
            fail("BROKEN_REFERENCE", f"used contig {source_card_key} references unknown source")
        for field, enum_name in (
            ("original_assignment", "original_assignment"),
            ("placement_mode", "placement_mode"),
            ("ref_alignment_status", "ref_alignment_status"),
            ("orientation", "orientation"),
        ):
            if row[field] not in enums[enum_name]:
                fail("INVALID_VALUE", f"used contig {source_card_key} has invalid {field}")
        parse_int(row["anchor_start"], f"used contig {source_card_key}.anchor_start")
        event_ids = parse_json(
            row["accepted_event_ids_json"],
            f"used contig {source_card_key}.accepted_event_ids_json",
            list,
        )
        final_segment_ids = parse_json(
            row["final_path_segment_ids_json"],
            f"used contig {source_card_key}.final_path_segment_ids_json",
            list,
        )
        pairwise_ids = parse_json(
            row["pairwise_evidence_ids_json"],
            f"used contig {source_card_key}.pairwise_evidence_ids_json",
            list,
        )
        if not event_ids or not final_segment_ids or not pairwise_ids:
            fail("BROKEN_REFERENCE", f"used contig {source_card_key} has an incomplete trace chain")
        if any(value not in events or events[value]["status"] != "accepted" for value in event_ids):
            fail("BROKEN_REFERENCE", f"used contig {source_card_key} references invalid accepted event")
        if any(value not in segment_ids for value in final_segment_ids):
            fail("BROKEN_REFERENCE", f"used contig {source_card_key} references unknown segment")
        if any(value not in evidence for value in pairwise_ids):
            fail("BROKEN_REFERENCE", f"used contig {source_card_key} references unknown pairwise evidence")
        if any(evidence[value]["stage"] != "display_pairwise" for value in pairwise_ids):
            fail("BROKEN_REFERENCE", f"used contig {source_card_key} pairwise evidence has the wrong role")
        if row["original_assignment"] == "unplaced" and row["placement_mode"] != "grt_promoted":
            fail("INVALID_VALUE", f"unplaced used contig {source_card_key} must be grt_promoted")
        if row["ref_alignment_status"] == "no_hit" and row["anchor_start"] == "":
            fail("BROKEN_REFERENCE", f"no-hit used contig {source_card_key} requires GRT-derived anchor")

    for event_id, event in events.items():
        if (
            event["status"] != "accepted"
            or event["source"] is None
            or not event_is_path_producing(event)
        ):
            continue
        source_card_key = event["source_card_key"]
        if source_card_key not in used_contigs:
            fail("BROKEN_REFERENCE", f"accepted event {event_id} lacks a used-contig card")
        card = used_contigs[source_card_key]
        source = event["source"]
        if (card["dataset_name"], card["contig_name"], card["target_chr"]) != (
            source["dataset"],
            source["contig"],
            event["chr"],
        ):
            fail("BROKEN_REFERENCE", f"accepted event {event_id} and used-contig card disagree")
        if event_id not in parse_json(
            card["accepted_event_ids_json"],
            f"used contig {source_card_key}.accepted_event_ids_json",
            list,
        ):
            fail("BROKEN_REFERENCE", f"used-contig card does not point back to event {event_id}")
        if event["final_path_segment_id"] not in parse_json(
            card["final_path_segment_ids_json"],
            f"used contig {source_card_key}.final_path_segment_ids_json",
            list,
        ):
            fail("BROKEN_REFERENCE", f"used-contig card does not point to event {event_id} segment")

    for usage_id, row in usage.items():
        if row["status"] not in {"accepted", "consumed"}:
            continue
        event = events[row["event_id"]]
        if usage_id not in event["usage_ids"]:
            fail("BROKEN_REFERENCE", f"event {row['event_id']} does not point back to usage {usage_id}")
        if event["final_path_segment_id"] != row["final_path_segment_id"]:
            fail("BROKEN_REFERENCE", f"usage {usage_id} and event Final Path segments disagree")

    attempts = unique_index(tables["metadata/grt_gap_attempts.tsv"], "attempt_id", "metadata/grt_gap_attempts.tsv")
    for attempt_id, row in attempts.items():
        if row["stage"] not in enums["event_stage"]:
            fail("INVALID_VALUE", f"gap attempt {attempt_id} has invalid stage")
        if row["status"] not in enums["event_status"]:
            fail("INVALID_VALUE", f"gap attempt {attempt_id} has invalid status")
        parse_int(row["candidate_count"], f"gap attempt {attempt_id}.candidate_count", 0)
        if row["accepted_event_id"] and row["accepted_event_id"] not in events:
            fail("BROKEN_REFERENCE", f"gap attempt {attempt_id} references unknown event")

    stage_rows = tables["metadata/grt_stage_status.tsv"]
    transitions = schema["stage_transitions"]
    observed = [(row["stage"], row["q_input_version"], row["q_output_version"]) for row in stage_rows]
    if observed != [tuple(value) for value in transitions]:
        fail("INVALID_VALUE", "grt_stage_status.tsv does not match the required stage transition order")
    for row in stage_rows:
        stage = row["stage"]
        if row["status"] not in enums["stage_status"]:
            fail("INVALID_VALUE", f"stage {stage} is not successful")
        q_input_path = bundle_path(bundle_root, f"grt/q/{row['q_input_version']}.fa", f"stage {stage} q input")
        q_output_path = bundle_path(bundle_root, f"grt/q/{row['q_output_version']}.fa", f"stage {stage} q output")
        for label, path, value in (
            ("input", q_input_path, row["q_input_sha256"]),
            ("output", q_output_path, row["q_output_sha256"]),
        ):
            validate_sha256(value, f"stage {stage} q {label} SHA-256")
            if sha256_file(path) != value:
                fail("CHECKSUM_MISMATCH", f"stage {stage} q {label} hash mismatch")
        if stage == "step4_telomere":
            expected_donor = recipe["tel_donor_set_id"]
        elif stage == "finalize":
            expected_donor = ""
        else:
            expected_donor = recipe["donor_set_id"]
        if row["donor_set_id"] != expected_donor:
            fail("BROKEN_REFERENCE", f"stage {stage} uses unexpected donor set")
        validate_artifact(
            bundle_root,
            row["checkpoint_relpath"],
            row["checkpoint_sha256"],
            f"stage {stage} checkpoint",
        )

    return {
        "workflow": schema["workflow"],
        "schema_version": schema["schema_version"],
        "datasets": len(dataset_names),
        "sources": len(sources),
        "donor_sets": len(donor_sets),
        "evidence": len(evidence),
        "events": len(events),
        "segments": len(segment_ids),
        "q0_sha256": sha256_file(q0_path),
        "q4_sha256": sha256_file(q4_path),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate a GPM GRT precomputed package contract")
    parser.add_argument("--bundle", required=True, type=Path, help="Path to the gpm_server bundle root")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    args = parser.parse_args(argv)
    try:
        summary = validate_contract(args.bundle, args.schema)
    except ContractError as exc:
        print(f"ERROR {exc.code}: {exc.message}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
