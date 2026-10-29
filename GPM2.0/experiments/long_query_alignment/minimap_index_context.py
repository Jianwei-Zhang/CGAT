"""Pinned minimap2 v2.31 MMI partition reader/copy, not a minimap2 patch.

Format is from upstream index.c::mm_idx_dump/mm_idx_load. Retain serialized
partition bytes/order; never guess FASTA boundaries from an -I size. No hash
bucket or sequence payload is loaded in Python. Execution validation deferred.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import struct
import sys

MAGIC = b"MMI\x02"
CHUNK = 1024**2
MAX_PARTS = 10000
MAX_RECORDS = 1000000
MAX_BUCKET_BITS = 20


class IndexContextError(ValueError):
    pass


def identity(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def read_catalog(path, expected_records=None):
    """Return byte extents/record membership for every serialized index part."""
    if sys.byteorder != "little":
        raise IndexContextError("pinned MMI reader supports little-endian hosts only")
    path = Path(path)
    parts, records = [], []
    fd = os.open(path, os.O_RDONLY | getattr(os,"O_NONBLOCK",0))
    with os.fdopen(fd,"rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise IndexContextError("MMI input must be a regular file")
        end = before.st_size
        def read(size):
            if size < 0 or size > CHUNK or stream.tell()+size > end:
                raise IndexContextError("truncated or oversized MMI metadata")
            raw = stream.read(size)
            if len(raw) != size:
                raise IndexContextError("truncated MMI metadata")
            return raw
        def u32():
            return struct.unpack("<I",read(4))[0]
        def skip(size):
            if size < 0 or stream.tell()+size > end:
                raise IndexContextError("MMI payload extent exceeds file size")
            stream.seek(size,os.SEEK_CUR)
        while stream.tell() < end:
            if len(parts) >= MAX_PARTS:
                raise IndexContextError("too many MMI partitions")
            start = stream.tell()
            if read(4) != MAGIC:
                raise IndexContextError("unsupported MMI magic or trailing bytes")
            w,k,b,nseq,flags = struct.unpack("<IIIII",read(20))
            if not (1 <= w <= 255 and 1 <= k <= 28 and 0 <= b <= MAX_BUCKET_BITS and
                    1 <= nseq <= MAX_RECORDS-len(records)):
                raise IndexContextError("unsupported MMI header/record budget")
            # Only ordinary asm10 indexing is supported here. Reject HPC,
            # missing names/sequences and future flags rather than misparse them.
            if flags != 0:
                raise IndexContextError("index must retain non-HPC names and target sequences")
            names, total = [], 0
            for _ in range(nseq):
                n = read(1)[0]
                try:
                    name = read(n).decode("ascii")
                except UnicodeError as exc:
                    raise IndexContextError("non-ASCII MMI target name") from exc
                length = u32()
                if not name or any(not 33 <= ord(c) <= 126 for c in name) or not 0 < length <= 2147483647:
                    raise IndexContextError("invalid MMI target identity/length")
                names.append({"name":name,"length":length})
                records.append((name,length))
                total += length
            for _ in range(1<<b):
                positions = u32()
                skip(8*positions)
                keys = u32()
                skip(16*keys)
            skip(4*((total+7)//8))
            parts.append({"part_index":len(parts),"start":start,"end":stream.tell(),
                          "window":w,"kmer":k,"bucket_bits":b,"flags":flags,
                          "records":names,"total_bases":total})
        if not parts or len({name for name,_ in records}) != len(records):
            raise IndexContextError("empty index or duplicated target IDs across index parts")
        if expected_records is not None and records != [(name,row["length"]) for name,row in expected_records.items()]:
            raise IndexContextError("index target IDs/lengths/order differ from original reference")
        if identity(before) != identity(os.fstat(stream.fileno())) or identity(before) != identity(path.stat()):
            raise IndexContextError("MMI changed during catalog scan")
    return {"format":"minimap2_v2.31_MMI2_little_endian","parts":parts,
            "size_bytes":end,"index_identity":list(identity(before)),
            "target_record_count":len(records),"partition_boundaries_guessed":False}


def copy_parts(path, output_dir, expected_records):
    """Copy complete original MMI parts byte-for-byte into a fresh private folder."""
    path, output_dir = Path(path),Path(output_dir)
    catalog = read_catalog(path,expected_records)
    output_dir.mkdir(mode=0o700)
    entire = hashlib.sha256()
    with path.open("rb") as source:
        if list(identity(os.fstat(source.fileno()))) != catalog["index_identity"]:
            raise IndexContextError("MMI changed before copying")
        for row in catalog["parts"]:
            destination = output_dir/f"part-{row['part_index']:04d}.mmi"
            digest = hashlib.sha256()
            source.seek(row["start"])
            remaining = row["end"]-row["start"]
            with destination.open("xb") as out:
                while remaining:
                    block = source.read(min(CHUNK,remaining))
                    if not block:
                        raise IndexContextError("truncated MMI payload during copy")
                    out.write(block)
                    digest.update(block); entire.update(block)
                    remaining -= len(block)
            row.update(path=str(destination.resolve()),sha256=digest.hexdigest())
        if (list(identity(os.fstat(source.fileno()))) != catalog["index_identity"] or
                list(identity(path.stat())) != catalog["index_identity"]):
            raise IndexContextError("MMI changed during part copying")
    catalog["sha256"] = entire.hexdigest()
    catalog["serialized_bytes_preserved"] = True
    catalog["global_mapq_restored"] = False
    return catalog


def validate_part_context(context, *, reference_sha256, tool_sha256, preset, target_records):
    """Validate an internally built part before the window/guidance passes."""
    required = {"path","sha256","reference_sha256","tool_sha256","preset","part_index","records","mid_occ"}
    if type(context) is not dict or not required <= context.keys():
        raise IndexContextError("missing internal index context")
    if type(context["mid_occ"]) is not int or not 1 <= context["mid_occ"] <= 2147483647:
        raise IndexContextError("missing/invalid inherited first-part minimizer threshold")
    if (context["reference_sha256"] != reference_sha256 or context["tool_sha256"] != tool_sha256 or
            context["preset"] != preset):
        raise IndexContextError("index context reference/tool/preset mismatch")
    path = Path(context["path"])
    catalog = read_catalog(path)
    if len(catalog["parts"]) != 1 or catalog["parts"][0]["records"] != context["records"]:
        raise IndexContextError("context is not one complete original index part")
    if any(row["name"] not in target_records or target_records[row["name"]]["length"] != row["length"] for row in context["records"]):
        raise IndexContextError("index part has unknown reference records")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        before = identity(os.fstat(stream.fileno()))
        for block in iter(lambda:stream.read(CHUNK),b""):
            digest.update(block)
        if (before != identity(os.fstat(stream.fileno())) or before != identity(path.stat()) or
                list(before) != catalog["index_identity"] or digest.hexdigest() != context["sha256"]):
            raise IndexContextError("index context hash/identity changed")
    return path
