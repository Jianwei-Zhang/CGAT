"""Recover genuine ONT qualities once per input set, shared by both families.

Ordinary gzip and multiple FASTQ inputs are streamed into a compressed SQLite
lookup once. No made-up qualities, ID-only joins, or per-round full read scans.
"""
import fcntl
import gzip
import os
from pathlib import Path
import sqlite3
import tempfile
import zlib

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqIO.QualityIO import FastqGeneralIterator

from ExtensionFamilies import atomic_json, fingerprint, read_json
from FamilyTools import content_hash


def source_contract(sources):
    if isinstance(sources, (str, Path)):
        sources = [sources]
    return [{"path": str(Path(p).resolve()), "sha256": content_hash(p)} for p in (sources or [])]


def original_ont(base):
    info = dict(getattr(base, "original_reads_info", None) or {})
    info.update(getattr(base, "reads_info", None) or {})
    return info.get("original_ont")


def _quality_index(contract, directory):
    if not contract:
        raise ValueError("ONT-only assembly requires original FASTQ with genuine qualities; "
                         "ONT FASTA alone is not supported. Supply --ont reads.fastq[.gz].")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    identity = fingerprint({"schema": 1, "sources": contract})
    database = directory / (identity + ".sqlite")
    receipt = directory / (identity + ".json")
    with (directory / (identity + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for source in contract:
            if content_hash(source["path"]) != source["sha256"]:
                raise ValueError("Original ONT FASTQ changed: " + source["path"])
        if receipt.exists():
            saved = read_json(receipt)
            if saved.get("sources") != contract or saved.get("sha256") != content_hash(database):
                raise ValueError("ONT quality cache changed: " + str(database))
            return database
        fd, temporary = tempfile.mkstemp(prefix=".ont-qualities-", dir=directory)
        os.close(fd)
        try:
            connection = sqlite3.connect(temporary)
            try:
                connection.execute("CREATE TABLE reads (id TEXT PRIMARY KEY, record BLOB NOT NULL)")
                count = 0
                for source in contract:
                    path = source["path"]
                    opener = gzip.open if path.endswith((".gz", ".bgz")) else open
                    with opener(path, "rt") as stream:
                        try:
                            for title, sequence, quality in FastqGeneralIterator(stream):
                                if not sequence or any(not 33 <= ord(c) <= 126 for c in quality):
                                    raise ValueError("Invalid ONT sequence or Phred+33 quality: " + title)
                                read_id = title.split()[0]
                                payload = zlib.compress((sequence + "\n" + quality).encode("ascii"))
                                try:
                                    connection.execute("INSERT INTO reads VALUES (?, ?)", (read_id, payload))
                                except sqlite3.IntegrityError as error:
                                    raise ValueError("Duplicate ONT read ID across original inputs: " + read_id) from error
                                count += 1
                        except ValueError as error:
                            raise ValueError("ONT-only assembly requires valid original FASTQ with genuine "
                                             "qualities (not FASTA): " + path + ": " + str(error)) from error
                    if content_hash(path) != source["sha256"]:
                        raise ValueError("Original ONT FASTQ changed while indexing: " + path)
                if not count:
                    raise ValueError("Original ONT FASTQ is empty")
                connection.commit()
            finally:
                connection.close()
            os.replace(temporary, database)
            atomic_json(receipt, {"sources": contract, "sha256": content_hash(database), "reads": count})
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return database


def _selected_quality(selected, original, quality, read_id):
    # Preserve the selected sequence and order, not just the source read ID.
    selected, original = selected.upper(), original.upper()
    reverse = str(Seq(original).reverse_complement())
    if selected == original:
        return quality
    if selected == reverse:
        return quality[::-1]
    matches = []
    for sequence, scores in ((original, quality), (reverse, quality[::-1])):
        start = sequence.find(selected)
        if start >= 0:
            if sequence.find(selected, start + 1) >= 0:
                raise ValueError("Ambiguous ONT read trimming: " + read_id)
            matches.append(scores[start:start + len(selected)])
    if len(matches) != 1:
        raise ValueError("Selected ONT sequence mismatches source or has ambiguous trimming: " + read_id)
    return matches[0]


def restore_fastq(selected_fasta, contract, output_fastq, cache_directory):
    database = _quality_index(contract, cache_directory)
    output = Path(output_fastq)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ont-selected-", dir=output.parent)
    try:
        connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        try:
            seen = set()
            with os.fdopen(fd, "w") as stream:
                for record in SeqIO.parse(selected_fasta, "fasta"):
                    if record.id in seen or not len(record):
                        raise ValueError("Duplicate or empty selected ONT read: " + record.id)
                    seen.add(record.id)
                    row = connection.execute("SELECT record FROM reads WHERE id=?", (record.id,)).fetchone()
                    if row is None:
                        raise ValueError("Selected ONT read missing from original FASTQ: " + record.id)
                    original, quality = zlib.decompress(row[0]).decode("ascii").split("\n")
                    scores = _selected_quality(str(record.seq), original, quality, record.id)
                    stream.write("@" + record.id + "\n" + str(record.seq) + "\n+\n" + scores + "\n")
                if not seen:
                    raise ValueError("Selected ONT reads are empty")
            os.replace(temporary, output)
        finally:
            connection.close()
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return str(output)


def prepare_ont_fastq(selected_fasta, base, output_fastq):
    contract = getattr(base, "ont_quality_sources", None)
    if contract is None:
        contract = source_contract(original_ont(base))
    cache = Path(getattr(base, "ont_quality_cache", Path(base.out) / "ont-quality-cache"))
    return restore_fastq(selected_fasta, contract, output_fastq, cache)
