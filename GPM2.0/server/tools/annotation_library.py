#!/usr/bin/env python3
"""Official + user-local + one-run annotation inputs, locked into each project.

No run/resume path reads an installation library: only prepare calls snapshot().
The CLI never writes library/; all user edits are serialized under local/library/.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile

TEL_FIELDS = ("id", "motif", "min_repeat", "note")
CEN_FIELDS = ("id", "note")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
DNA_RE = re.compile(r"[ACGTRYSWKMBDHVN]+\Z")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_tsv(path: Path, fields, rows) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, delimiter="\t", lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(path, buffer.getvalue().encode())


def read_tsv(path: Path, fields, optional=False) -> list[dict]:
    if not path.exists() and optional:
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t", strict=True)
        if (not reader.fieldnames or len(reader.fieldnames) != len(fields)
                or set(reader.fieldnames) != set(fields)):
            raise ValueError(f"{path}: expected exactly one of each column {fields}")
        rows = list(reader)
    seen = set()
    for row in rows:
        if None in row or any(row.get(field) is None for field in fields):
            raise ValueError(f"{path}: wrong number of TSV fields; notes cannot contain unescaped tabs")
        entry_id = row.get("id", "")
        if not ID_RE.fullmatch(entry_id) or entry_id in seen:
            raise ValueError(f"{path}: invalid or duplicate id {entry_id!r}")
        seen.add(entry_id)
        validate_note(row.get("note"))
    return rows


def validate_note(note):
    if note is None or any(c in note for c in "\t\r\n\x00"):
        raise ValueError("note must be a single line (no tabs/NUL); empty is allowed")


def tel_rule(motif, minimum):
    motif = motif.upper()
    if not re.fullmatch(r"[ACGT]+", motif):
        raise ValueError("tel motif must contain only A/C/G/T")
    if not re.fullmatch(r"[1-9][0-9]*", str(minimum)):
        raise ValueError("min_repeat must be a positive integer")
    return motif, int(minimum)


def fasta_records(path: Path, *, content: bytes | None = None):
    if content is None:
        opener = gzip.open if path.suffix == ".gz" else open
        stream = opener(path, "rt", encoding="utf-8")
    else:
        if path.suffix == ".gz":
            content = gzip.decompress(content)
        stream = io.StringIO(content.decode("utf-8"))
    name, sequence, seen = None, [], set()
    with stream as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name is not None:
                    yield name, validate_sequence("".join(sequence), path)
                parts = line[1:].split()
                if not parts or parts[0] in seen:
                    raise ValueError(f"{path}: empty or duplicate FASTA name")
                name, sequence = parts[0], []
                seen.add(name)
            elif name is None:
                raise ValueError(f"{path}: sequence before FASTA header")
            else:
                sequence.append(line.upper())
    if name is None:
        raise ValueError(f"{path}: empty FASTA")
    yield name, validate_sequence("".join(sequence), path)


def validate_sequence(sequence, path):
    if not DNA_RE.fullmatch(sequence) or not any(base in sequence for base in "ACGT"):
        raise ValueError(f"{path}: empty/invalid DNA sequence")
    return sequence


def fasta_bytes(records):
    return "".join(f">{name}\n" + "\n".join(seq[i:i+80] for i in range(0, len(seq), 80)) + "\n"
                   for name, seq in records).encode()


@contextlib.contextmanager
def local_lock(server: Path, *, exclusive=False):
    root = server / "local/library"
    if exclusive:
        root.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        yield
        return
    with (root / ".lock").open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield


def load_entries(root: Path, source: str, *, optional=False):
    tel = []
    for row in read_tsv(root / "tel.tsv", TEL_FIELDS, optional):
        motif, minimum = tel_rule(row["motif"], row["min_repeat"])
        tel.append({**row, "motif": motif, "min_repeat": minimum, "source": source,
                    "sha256": sha256(f"{motif}\t{minimum}\n".encode())})
    cen = []
    for row in read_tsv(root / "cen/cen.tsv", CEN_FIELDS, optional):
        path = root / "cen" / (row["id"] + ".fa")
        # Hash and parse the same captured bytes, even if another process replaces
        # the input path between operations. The sequence and its source must agree.
        content = path.read_bytes()
        records = list(fasta_records(path, content=content))
        cen.append({**row, "source": source, "sha256": sha256(content), "records": records})
    return tel, cen


def provenance(entry, **extra):
    return {key: entry[key] for key in ("source", "id", "sha256", "note")} | extra


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot(server: Path, workspace: Path, explicit_tel, explicit_cen, min_len, min_identity):
    with local_lock(server):
        official_tel, official_cen = load_entries(server / "library", "official")
        local_tel, local_cen = load_entries(server / "local/library", "local", optional=True)
    tel, cen = official_tel + local_tel, official_cen + local_cen
    for index, (motif, minimum) in enumerate(explicit_tel, 1):
        motif, minimum = tel_rule(motif, minimum)
        tel.append({"id": f"parameter_tel_{index}", "source": "parameter", "note": "",
                    "motif": motif, "min_repeat": minimum,
                    "sha256": sha256(f"{motif}\t{minimum}\n".encode())})
    if explicit_cen:
        path = Path(explicit_cen)
        content = path.read_bytes()
        cen.append({"id": "parameter_cen", "source": "parameter", "note": "",
                    "sha256": sha256(content), "records": list(fasta_records(path, content=content))})
    tel_groups, cen_groups = {}, {}
    for entry in tel:
        key = entry["sha256"]
        group = tel_groups.setdefault(key, {"rule_id": "tel_" + key, "motif": entry["motif"],
                    "min_repeat": entry["min_repeat"], "reverse_complement": "true", "entries": []})
        group["entries"].append(provenance(entry))
    for entry in cen:
        for name, sequence in entry["records"]:
            digest = sha256(sequence.encode())
            group = cen_groups.setdefault(digest, {"cen_id": "cen_" + digest, "sequence": sequence, "entries": []})
            group["entries"].append(provenance(entry, sequence_name=name, sequence_sha256=digest))
    tel_rows = [{**group, "provenance": json_text(group["entries"])} for group in tel_groups.values()]
    cen_rows = [{"cen_id": group["cen_id"], "chr_name": "*", "sequence_name": group["cen_id"],
                 "fasta_relpath": "cen/library.fa", "min_len": min_len, "min_identity": min_identity,
                 "provenance": json_text(group["entries"])} for group in cen_groups.values()]
    # Validate all input before replacing any prepared input. Re-prepare is explicit.
    write_tsv(workspace / "tel/rules.tsv", ("rule_id", "motif", "min_repeat", "reverse_complement", "provenance"), tel_rows)
    atomic_write(workspace / "cen/library.fa", fasta_bytes((g["cen_id"], g["sequence"]) for g in cen_groups.values()))
    write_tsv(workspace / "cen/reference.tsv", ("cen_id", "chr_name", "sequence_name", "fasta_relpath", "min_len", "min_identity", "provenance"), cen_rows)
    manifest = {"schema_version": 1, "tel": [{k: v for k, v in g.items() if k != "provenance"} for g in tel_rows],
                "cen": [{"cen_id": g["cen_id"], "sequence_sha256": digest,
                         "length": len(g["sequence"]), "entries": g["entries"]} for digest, g in cen_groups.items()]}
    manifest["files"] = {relative: sha256((workspace / relative).read_bytes())
                         for relative in ("tel/rules.tsv", "cen/reference.tsv", "cen/library.fa")}
    atomic_write(workspace / "metadata/annotation_library_snapshot.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())


def verify_snapshot(workspace: Path):
    """Fail closed on edited/partial new snapshots, but leave legacy projects alone."""
    path = workspace / "metadata/annotation_library_snapshot.json"
    if not path.exists():
        rules = workspace / "tel/rules.tsv"
        if rules.is_file():
            with rules.open(encoding="utf-8") as handle:
                if "provenance" in handle.readline().rstrip("\n").split("\t"):
                    raise ValueError("annotation snapshot is incomplete; explicitly prepare again")
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected = {"tel/rules.tsv", "cen/reference.tsv", "cen/library.fa"}
    if manifest.get("schema_version") != 1 or set(manifest.get("files", {})) != expected:
        raise ValueError("unsupported or incomplete annotation library snapshot")
    for relative, digest in manifest["files"].items():
        if sha256((workspace / relative).read_bytes()) != digest:
            raise ValueError(f"prepared annotation input changed: {relative}; explicitly prepare again")


def manage(args):
    server = args.server_root.resolve()
    with local_lock(server, exclusive=args.command != "list"):
        official_tel, official_cen = load_entries(server / "library", "official")
        local = server / "local/library"
        tel, cen = load_entries(local, "local", optional=True)
        if args.command == "list":
            import sys
            writer = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")
            writer.writerow(("type", "source", "id", "motif", "min_repeat", "note"))
            for kind, entries in (("tel", official_tel + tel), ("cen", official_cen + cen)):
                if args.kind and args.kind != kind:
                    continue
                for row in entries:
                    writer.writerow((kind, row["source"], row["id"], row.get("motif", ""), row.get("min_repeat", ""), row["note"]))
            return
        if args.command.startswith("add-"):
            validate_note(args.note)
            if args.command == "add-tel":
                motif, minimum = tel_rule(args.motif, args.min_repeat)
                digest = sha256(f"{motif}\t{minimum}\n".encode())
                entry_id = "local_tel_" + digest[:24]
                row = {"id": entry_id, "motif": motif, "min_repeat": minimum, "note": args.note}
                path, fields, rows = local / "tel.tsv", TEL_FIELDS, tel
            else:
                records = list(fasta_records(args.fasta))
                data = fasta_bytes(records)
                entry_id = "local_cen_" + sha256(data)[:24]
                row = {"id": entry_id, "note": args.note}
                path, fields, rows = local / "cen/cen.tsv", CEN_FIELDS, cen
                if not any(r["id"] == entry_id for r in rows):
                    atomic_write(local / "cen" / (entry_id + ".fa"), data)
            if any(r["id"] == entry_id for r in rows):
                raise ValueError(f"already in local library: {entry_id}; remove then add to edit its note")
            write_tsv(path, fields, rows + [row])
            print(entry_id)
            return
        entry_id = args.id
        if any(row["id"] == entry_id for row in official_tel + official_cen):
            raise ValueError("official library entries cannot be removed")
        if any(row["id"] == entry_id for row in tel):
            write_tsv(local / "tel.tsv", TEL_FIELDS, [r for r in tel if r["id"] != entry_id])
        elif any(row["id"] == entry_id for row in cen):
            write_tsv(local / "cen/cen.tsv", CEN_FIELDS, [r for r in cen if r["id"] != entry_id])
            (local / "cen" / (entry_id + ".fa")).unlink()
        else:
            raise ValueError(f"unknown local entry: {entry_id}")
        print(f"Removed {entry_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("kind", nargs="?", choices=("tel", "cen"))
    add = commands.add_parser("add-tel")
    add.add_argument("motif")
    add.add_argument("min_repeat")
    add.add_argument("--note", default="")
    add = commands.add_parser("add-cen")
    add.add_argument("fasta", type=Path)
    add.add_argument("--note", default="")
    commands.add_parser("remove").add_argument("id")
    prepare = commands.add_parser("snapshot", help=argparse.SUPPRESS)
    prepare.add_argument("--workspace", type=Path, required=True)
    prepare.add_argument("--tel", nargs=2, action="append", default=[])
    prepare.add_argument("--cen")
    prepare.add_argument("--cen-min-len", type=int, default=10000)
    prepare.add_argument("--cen-min-identity", type=float, default=80)
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            if args.cen_min_len < 1 or not 0 <= args.cen_min_identity <= 100:
                raise ValueError("invalid cen thresholds")
            snapshot(args.server_root, args.workspace, args.tel, args.cen, args.cen_min_len, args.cen_min_identity)
        else:
            manage(args)
    except (ValueError, OSError, csv.Error) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
