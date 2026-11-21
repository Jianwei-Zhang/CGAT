"""Content-bound FASTA preparation for tools that do not consume FASTQ.

DEGAP keeps its native typed inputs. Other tools reuse these conversions across
runs; FASTA/FASTQ (plain or gzip) and wrapping are detected from content. No read
correction, filtering or sequence trimming is performed. Reversible record IDs
avoid cross-file collisions in native tools that use FASTA names as map keys.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import os
from pathlib import Path
import re
import tempfile

try:
    from run_orchestration import sha256_file
    from refinement_tools import ToolError, fingerprint
except ModuleNotFoundError:
    from .run_orchestration import sha256_file
    from .refinement_tools import ToolError, fingerprint

RECIPE = "cgat.reads-to-fasta.v1"


def file_identity(path):
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def open_reads(path):
    with path.open("rb") as stream:
        magic = stream.read(2)
    return gzip.open(path, "rt", encoding="ascii", newline=None) if magic == b"\x1f\x8b" else path.open("r", encoding="ascii", newline=None)


def checked_sequence(lines):
    sequence = "".join(line.rstrip("\r\n") for line in lines).upper()
    if not sequence or re.search(r"[^ACGTRYSWKMBDHVN]", sequence):
        raise ToolError("reads must contain nonempty IUPAC DNA sequences without whitespace")
    return sequence


def read_records(stream):
    header = stream.readline()
    while header and not header.strip():
        header = stream.readline()
    if header.startswith(">"):
        lines = []
        while True:
            line = stream.readline()
            if not line or line.startswith(">"):
                identifier = header[1:].strip().split()
                if not identifier:
                    raise ToolError("empty FASTA read identifier")
                yield identifier[0], checked_sequence(lines)
                if not line:
                    break
                header, lines = line, []
            elif line.strip():
                lines.append(line)
    elif header.startswith("@"):
        while header:
            if not header.startswith("@") or not header[1:].strip():
                raise ToolError("invalid FASTQ read header")
            identifier = header[1:].strip().split()[0]
            lines = []
            while True:
                line = stream.readline()
                if not line:
                    raise ToolError("FASTQ sequence is missing its + separator")
                if line.startswith("+"):
                    repeated_id = line[1:].strip().split()
                    if repeated_id and repeated_id[0] != identifier:
                        raise ToolError("FASTQ + separator disagrees with its read header")
                    break
                lines.append(line)
            sequence = checked_sequence(lines)
            quality_length = 0
            while quality_length < len(sequence):
                line = stream.readline()
                if not line:
                    raise ToolError("truncated FASTQ quality")
                quality = line.rstrip("\r\n")
                if any(ord(char) < 33 or ord(char) > 126 for char in quality):
                    raise ToolError("invalid FASTQ quality character")
                quality_length += len(quality)
            if quality_length != len(sequence):
                raise ToolError("FASTQ sequence and quality lengths differ")
            yield identifier, sequence
            header = stream.readline()
    else:
        raise ToolError("reads file is empty or not FASTA/FASTQ")


def prepare_fasta(inputs: list[str], destination_root: Path) -> dict:
    """Combine a selected technology's files once, under the caller's workspace lock.

    Cache identity binds input bytes, paths/order, conversion recipe and outputs.
    Source paths are not copied, renamed, edited, or deleted. Failed temporary
    conversion is removed, while a prior cache with wrong content is rejected.
    """
    paths = [Path(path).resolve(strict=True) for path in inputs]
    if not paths or len(set(paths)) != len(paths):
        raise ToolError("FASTA preparation requires unique input files")
    identities, records = {}, []
    for path in paths:
        before = file_identity(path)
        sha256 = sha256_file(path)
        if file_identity(path) != before:
            raise ToolError("reads changed during input fingerprinting")
        identities[path] = before
        records.append({"path": str(path), "sha256": sha256})
    binding = {"recipe": RECIPE, "converter_sha256": sha256_file(Path(__file__).resolve()), "inputs": records, "id_recipe": "cgat_<binding16>_<input_index>_<record_index>"}
    key = fingerprint(binding)
    destination_root = Path(destination_root)
    destination = destination_root / key
    fasta_name = "reads_" + key[:16] + ".fa"
    if destination.exists() or destination.is_symlink():
        receipt_path = destination / "conversion.json"
        if not receipt_path.is_file():
            raise ToolError("incomplete existing reads conversion; preserve it for inspection instead of silently reusing")
        saved = json.loads(receipt_path.read_text())
        if (saved.get("binding") != binding or set(saved.get("outputs", {})) != {fasta_name, "read_ids.tsv.gz"}
                or any(sha256_file(destination / name) != digest for name, digest in saved["outputs"].items())):
            raise ToolError("existing reads conversion content changed; not reusable")
        if any(file_identity(path) != expected for path, expected in identities.items()):
            raise ToolError("reads changed while validating converted cache")
        return {**saved, "fasta": str(destination / fasta_name), "cache_hit": True}
    destination_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reads-", dir=destination_root) as temporary:
        temporary = Path(temporary)
        reads_count, bases = 0, 0
        with (temporary / fasta_name).open("x", encoding="ascii", newline="\n") as output:
            with (temporary / "read_ids.tsv.gz").open("xb") as raw_mapping:
                # Fixed gzip header makes the derived mapping content deterministic.
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw_mapping, mtime=0, compresslevel=1) as compressed:
                    with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as mapping:
                        writer = csv.writer(mapping, delimiter="\t", lineterminator="\n")
                        writer.writerow(("converted_id", "input_index", "record_index", "original_id"))
                        for input_index, path in enumerate(paths, 1):
                            count = 0
                            with open_reads(path) as stream:
                                for count, (original_id, sequence) in enumerate(read_records(stream), 1):
                                    record_id = f"cgat_{key[:16]}_{input_index}_{count}"
                                    output.write(f">{record_id}\n{sequence}\n")
                                    writer.writerow((record_id, input_index, count, original_id))
                                    reads_count += 1
                                    bases += len(sequence)
                            if count == 0:
                                raise ToolError(f"reads file has no records: {path}")
        if any(file_identity(path) != expected for path, expected in identities.items()):
            raise ToolError("reads changed during conversion")
        receipt = {"schema": "cgat.refinement-reads", "schema_version": 1, "binding": binding,
                   "reads": reads_count, "bases": bases,
                   "outputs": {name: sha256_file(temporary / name) for name in (fasta_name, "read_ids.tsv.gz")}}
        (temporary / "conversion.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        if destination.exists() or destination.is_symlink():
            raise ToolError("reads conversion appeared concurrently; rerun under the workspace lock")
        # Move the complete directory as a unit. TemporaryDirectory only cleans up
        # its old path; the published conversion is retained for other tools.
        os.rename(temporary, destination)
    return {**receipt, "fasta": str(destination / fasta_name), "cache_hit": False}
