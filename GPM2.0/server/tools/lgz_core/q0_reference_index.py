"""Exact reference-record lookup for regional q0 mapper-input planning.

R-tree boxes only find possible records. Every returned interval comes from
validated original M/= CIGAR blocks, not a grid/hull. Search envelopes between
compatible nearest flanks are explicitly proposals, never alignment evidence.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict, OrderedDict
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
import uuid
from typing import Iterable, Mapping

from .q0_alignments import PafAlignment, parse_paf_line
from .q0_catalog import _IntervalUnion, DISCOVERY_REFERENCE_IDENTITY
from .q0_sources import Interval, Q0EvidenceError, SourceKey, SourceSegment, merged_intervals

SCHEMA = "lgz_q0_reference_records_v1"


def _signature(path: Path):
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def _identity(path: Path):
    before = _signature(path); digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            digest.update(block)
    if _signature(path) != before:
        raise Q0EvidenceError("reference input changed while hashing")
    return {"sha256": digest.hexdigest(), "size": before[2]}, before


def _project(query: Interval, target: Interval, strand: str, interval: Interval, *, from_query: bool):
    source = query if from_query else target
    overlap = source.intersection(interval)
    if overlap is None:
        return None
    if from_query:
        return (Interval(target.start+overlap.start-query.start, target.start+overlap.end-query.start)
                if strand == "+" else Interval(target.start+query.end-overlap.end, target.start+query.end-overlap.start))
    return (Interval(query.start+overlap.start-target.start, query.start+overlap.end-target.start)
            if strand == "+" else Interval(query.end-(overlap.end-target.start), query.end-(overlap.start-target.start)))


class ReferenceIndex:
    """Sealed, content-bound index with a bounded parsed-record cache.

    No source DNA is loaded here. All sequence lengths and part IDs come from
    the catalog; original PAF records and record identities remain authoritative.
    """
    @staticmethod
    def bindings(parts: Mapping[str, SourceSegment], refs: Mapping[str, int]) -> dict:
        if any(key != p.segment_id for key, p in parts.items()) or any(type(n) is not int or n < 1 for n in refs.values()):
            raise Q0EvidenceError("invalid reference-index inventory")
        return {"schema": SCHEMA, "minimum_reference_identity": DISCOVERY_REFERENCE_IDENTITY,
                "sources": [[key, p.source.dataset, p.source.contig, p.interval.start, p.interval.end, p.sequence_sha256]
                            for key, p in sorted(parts.items())], "references": sorted(refs.items())}

    def _configure(self, path, root, parts, refs):
        self.path, self.root = Path(path), Path(root).resolve(strict=True)
        self.parts = parts; self.reference_lengths = dict(refs)
        self.binding = self.bindings(parts, refs)
        self.sources = sorted({p.source for p in parts.values()})
        self.source_ids = {key: i for i, key in enumerate(self.sources)}
        self.reference_ids = {key: i for i, key in enumerate(sorted(refs))}
        self.reference_names = sorted(refs)
        self.source_parts = defaultdict(list)
        for part in parts.values(): self.source_parts[part.source].append(part)
        for values in self.source_parts.values(): values.sort(key=lambda p: p.interval)
        self.source_ends = {key: [p.interval.end for p in values] for key, values in self.source_parts.items()}
        self.files = {}; self.file_names = {}; self.signatures = {}; self.handles = {}
        self.mirrors = {}; self.mirror_signatures = {}
        self.pending = []; self.boxes = []; self.count = 0; self.sealed = False
        self.cache = OrderedDict(); self.cache_ops = 0
        self.last_query_report = {}

    def _artifact(self, relative):
        p = Path(relative)
        if not relative or p.is_absolute() or ".." in p.parts or "\\" in relative:
            raise Q0EvidenceError("invalid indexed PAF path")
        result = (self.root/p).resolve(strict=True)
        if not result.is_relative_to(self.root):
            raise Q0EvidenceError("indexed PAF escapes workspace")
        return result

    @classmethod
    def create(cls, path, root, parts, refs):
        binding = cls.bindings(parts, refs)
        path = Path(path); path.touch(exist_ok=False)
        self = cls.__new__(cls); self._configure(path, root, parts, refs)
        self.connection = sqlite3.connect(path)
        self.connection.executescript("""
            PRAGMA journal_mode=DELETE;
            PRAGMA cache_size=-32768;
            PRAGMA temp_store=FILE;
            CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL);
            CREATE TABLE records (id INTEGER PRIMARY KEY, source INTEGER, ref INTEGER,
                qs INTEGER, qe INTEGER, ts INTEGER, te INTEGER, file INTEGER,
                offset INTEGER, size INTEGER, line INTEGER, digest BLOB);
            CREATE VIRTUAL TABLE boxes USING rtree(id, slo, shi, qlo, qhi, rlo, rhi, tlo, thi);
        """)
        self.connection.execute("INSERT INTO metadata VALUES (?,?)", ("bindings", json.dumps(binding, sort_keys=True)))
        self.connection.commit()
        return self

    def register_artifact(self, relative):
        if self.sealed: raise Q0EvidenceError("sealed reference index is immutable")
        if relative not in self.files:
            path = self._artifact(relative); number = len(self.files)
            self.files[relative] = number; self.file_names[number] = relative
            self.signatures[relative] = _signature(path)
            self.connection.execute("INSERT INTO files VALUES (?,?)", (number, relative))

    def observe_record(self, dataset: str, hit: PafAlignment, offset: int, size: int):
        if self.sealed: raise Q0EvidenceError("sealed reference index is immutable")
        self.register_artifact(hit.artifact)
        source = SourceKey(dataset, hit.query_name)
        if source not in self.source_ids or hit.matches/hit.block_length < DISCOVERY_REFERENCE_IDENTITY or not any(op in "M=" for _, op in hit.cigar):
            return
        if type(offset) is not int or type(size) is not int or offset < 0 or size < 1:
            raise Q0EvidenceError("invalid PAF record extent")
        if offset+size > self.signatures[hit.artifact][2] or self.reference_lengths.get(hit.target_name) != hit.target_length:
            raise Q0EvidenceError("indexed PAF extent/reference differs")
        self.count += 1
        sid, rid = self.source_ids[source], self.reference_ids[hit.target_name]
        self.pending.append((self.count, sid, rid, hit.query.start, hit.query.end, hit.target.start, hit.target.end,
                             self.files[hit.artifact], offset, size, hit.line_number, bytes.fromhex(hit.record_sha256)))
        # R-tree coordinates round outwards. Exact integer bounds/CIGAR are
        # checked after retrieval, including at coordinates beyond 2^31.
        self.boxes.append((self.count, sid, sid, hit.query.start, hit.query.end-1,
                           rid, rid, hit.target.start, hit.target.end-1))
        if len(self.pending) >= 5000: self._flush()

    def _flush(self):
        if self.pending:
            self.connection.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", self.pending)
            self.connection.executemany("INSERT INTO boxes VALUES (?,?,?,?,?,?,?,?,?)", self.boxes)
            self.pending.clear(); self.boxes.clear(); self.connection.commit()

    def seal(self):
        if self.sealed: raise Q0EvidenceError("reference index already sealed")
        self._flush(); inputs = {}
        for relative in self.files:
            path = self._artifact(relative)
            if _signature(path) != self.signatures[relative]: raise Q0EvidenceError("PAF changed during index construction")
            identity, signature = _identity(path)
            if signature != self.signatures[relative]: raise Q0EvidenceError("PAF changed before index sealing")
            inputs[relative] = identity
        report = {"schema": SCHEMA, "records": self.count, "reference_inputs": inputs}
        self.connection.executemany("INSERT INTO metadata VALUES (?,?)",
                                   [("sealed", "true"), ("build_report", json.dumps(report, sort_keys=True))])
        self.connection.commit(); self.sealed = True
        return report

    @classmethod
    def open(cls, path, root, parts, refs, *, local_paf_directory=None):
        self = cls.__new__(cls); self._configure(Path(path).resolve(strict=True), root, parts, refs)
        self.connection = sqlite3.connect(self.path.as_uri()+"?mode=ro", uri=True)
        try:
            metadata = dict(self.connection.execute("SELECT name,value FROM metadata"))
            expected = json.loads(json.dumps(self.binding))
            if json.loads(metadata["bindings"]) != expected or metadata.get("sealed") != "true":
                raise Q0EvidenceError("unsealed or differently bound reference index")
            report = json.loads(metadata["build_report"])
            for number, relative in self.connection.execute("SELECT id,path FROM files"):
                identity, signature = _identity(self._artifact(relative))
                if identity != report["reference_inputs"][relative]: raise Q0EvidenceError("indexed PAF content changed")
                self.files[relative] = number; self.file_names[number] = relative; self.signatures[relative] = signature
                if local_paf_directory is not None:
                    directory = Path(local_paf_directory).resolve(strict=True)
                    mirror = directory/(identity["sha256"]+".paf")
                    if mirror.is_symlink(): raise Q0EvidenceError("linked local PAF mirror is forbidden")
                    if not mirror.exists():
                        temporary = directory/(identity["sha256"]+".copy-"+uuid.uuid4().hex)
                        shutil.copyfile(self._artifact(relative), temporary)
                        if _identity(temporary)[0] != identity or _signature(self._artifact(relative)) != signature:
                            raise Q0EvidenceError("reference PAF changed while making local mirror")
                        temporary.rename(mirror)
                    mirrored, mirror_signature = _identity(mirror)
                    if mirrored != identity: raise Q0EvidenceError("local reference PAF bytes differ")
                    self.mirrors[relative] = mirror; self.mirror_signatures[relative] = mirror_signature
            if set(self.files) != set(report["reference_inputs"]): raise Q0EvidenceError("reference input inventory differs")
            self.count = report["records"]; self.sealed = True
            self.connection.execute("PRAGMA cache_size=-32768")
            return self
        except (OSError, ValueError, KeyError, sqlite3.Error):
            self.connection.close(); raise

    def build_report(self):
        if not self.sealed: raise Q0EvidenceError("reference index not sealed")
        return json.loads(self.connection.execute("SELECT value FROM metadata WHERE name='build_report'").fetchone()[0])

    def verify_inputs(self):
        for relative, signature in self.signatures.items():
            if _signature(self._artifact(relative)) != signature:
                raise Q0EvidenceError("indexed reference input changed during lookup")
        for relative, signature in self.mirror_signatures.items():
            if _signature(self.mirrors[relative]) != signature:
                raise Q0EvidenceError("local indexed reference mirror changed during lookup")

    def _hit(self, row):
        number, source, ref, qs, qe, ts, te, file, offset, size, line, digest = row
        cached = self.cache.get(number)
        if cached is not None:
            self.cache.move_to_end(number); return cached
        relative = self.file_names[file]
        if file not in self.handles:
            self.verify_inputs(); self.handles[file] = self.mirrors.get(relative, self._artifact(relative)).open("rb")
        handle = self.handles[file]; handle.seek(offset); raw = handle.read(size)
        hit = parse_paf_line(raw.decode("utf-8"), artifact=relative, line_number=line)
        if (bytes.fromhex(hit.record_sha256) != digest or hit.query_name != self.sources[source].contig
                or hit.target_name != self.reference_names[ref]
                or (hit.query.start, hit.query.end, hit.target.start, hit.target.end) != (qs,qe,ts,te)):
            raise Q0EvidenceError("indexed PAF record/frame differs from its original bytes")
        cost = len(hit.cigar)
        if cost <= 1_000_000:
            while self.cache and (self.cache_ops+cost > 1_000_000 or len(self.cache) >= 2048):
                _, old = self.cache.popitem(last=False); self.cache_ops -= len(old.cigar)
            self.cache[number] = hit; self.cache_ops += cost
        return hit

    def _source_hits(self, source, region):
        sid = self.source_ids[source]
        sql = """SELECT r.* FROM boxes b JOIN records r ON r.id=b.id
                 WHERE b.slo<=? AND b.shi>=? AND b.qlo<=? AND b.qhi>=?"""
        for row in self.connection.execute(sql, (sid, sid, region.end-1, region.start)):
            if row[1] == sid and row[3] < region.end and row[4] > region.start:
                yield self._hit(row)

    def regions(self, segment_id, query: Interval, *, anchor_context: int, reference_context: int, bridge_bases: int = 0):
        if not self.sealed or any(type(n) is not int or n < 0 for n in (anchor_context,reference_context,bridge_bases)):
            raise Q0EvidenceError("invalid reference-index search")
        self.verify_inputs()
        if segment_id not in self.parts: raise Q0EvidenceError("unknown query source part")
        part = self.parts[segment_id]
        if query.end > part.interval.length: raise Q0EvidenceError("query context exceeds source part")
        whole = Interval(query.start+part.interval.start, query.end+part.interval.start)
        search = Interval(max(part.interval.start,whole.start-anchor_context),min(part.interval.end,whole.end+anchor_context))
        regions = defaultdict(list); flanks = {}; records = 0
        for hit in self._source_hits(part.source,search):
            records += 1
            for block in hit.aligned_blocks():
                if block.operation == "X": continue
                clipped = block.query.intersection(part.interval)
                if clipped is None: continue
                target = _project(block.query,block.target,hit.strand,clipped,from_query=True)
                direct = _project(clipped,target,hit.strand,whole,from_query=True)
                if direct is not None: regions[hit.target_name].append(direct); continue
                if anchor_context == 0: continue
                if clipped.end <= whole.start:
                    side, distance = "left", whole.start-clipped.end
                    anchor = Interval(max(clipped.start,clipped.end-max(1,reference_context)),clipped.end)
                else:
                    side, distance = "right", clipped.start-whole.end
                    anchor = Interval(clipped.start,min(clipped.end,clipped.start+max(1,reference_context)))
                if distance > anchor_context: continue
                key = hit.target_name, hit.strand, side
                interval = _project(clipped,target,hit.strand,anchor,from_query=True)
                previous = flanks.get(key)
                if previous is None or distance < previous[0]: flanks[key] = (distance, {interval})
                elif distance == previous[0]: previous[1].add(interval)
        consistent = discordant = 0
        for (chromosome,strand,side),(distance,intervals) in flanks.items():
            regions[chromosome].extend(intervals)
            right = flanks.get((chromosome,strand,"right"))
            if side != "left" or right is None: continue
            right_distance, rights = right
            for left in intervals:
                for other in rights:
                    ordered = left.start <= other.start if strand == "+" else other.start <= left.start
                    hull = Interval(min(left.start,other.start),max(left.end,other.end))
                    if ordered and hull.length <= whole.length+distance+right_distance+anchor_context:
                        regions[chromosome].append(hull); consistent += 1
                    else: discordant += 1
        result = {}
        for chromosome, rows in sorted(regions.items()):
            expanded = merged_intervals(Interval(max(0,i.start-reference_context),min(self.reference_lengths[chromosome],i.end+reference_context)) for i in rows)
            joined = []
            for interval in expanded:
                if joined and interval.start-joined[-1].end <= bridge_bases:
                    joined[-1] = Interval(joined[-1].start,max(joined[-1].end,interval.end))
                else: joined.append(interval)
            result[chromosome] = tuple(joined)
        self.last_query_report = {"records_parsed_or_cached":records,"consistent_flank_pairs":consistent,"discordant_flank_pairs":discordant}
        return result

    def targets(self, regions: Mapping[str, Iterable[Interval]], *, context: int = 10_000, exclude=()):
        if not self.sealed or type(context) is not int or context < 0: raise Q0EvidenceError("invalid target lookup")
        self.verify_inputs()
        excluded = set(exclude)
        if not excluded <= self.parts.keys(): raise Q0EvidenceError("unknown excluded part")
        found = {}
        sql = """SELECT r.* FROM boxes b JOIN records r ON r.id=b.id
                 WHERE b.rlo<=? AND b.rhi>=? AND b.tlo<=? AND b.thi>=?"""
        for chromosome, intervals in regions.items():
            if chromosome not in self.reference_ids: raise Q0EvidenceError("unknown reference region")
            rid = self.reference_ids[chromosome]
            for interval in merged_intervals(intervals):
                if interval.end > self.reference_lengths[chromosome]: raise Q0EvidenceError("reference search exceeds input")
                for row in self.connection.execute(sql,(rid,rid,interval.end-1,interval.start)):
                    if row[2] != rid or row[5] >= interval.end or row[6] <= interval.start: continue
                    hit = self._hit(row); source = self.sources[row[1]]
                    parts = self.source_parts[source]; ends = self.source_ends[source]
                    for block in hit.aligned_blocks():
                        if block.operation == "X": continue
                        projected = _project(block.query,block.target,hit.strand,interval,from_query=False)
                        if projected is None: continue
                        index = bisect_right(ends,projected.start)
                        while index < len(parts) and parts[index].interval.start < projected.end:
                            part = parts[index]; index += 1
                            if part.segment_id in excluded: continue
                            overlap = part.interval.intersection(projected)
                            if overlap is None: continue
                            window = Interval(max(0,overlap.start-part.interval.start-context),min(part.interval.length,overlap.end-part.interval.start+context))
                            union = found.get(part.segment_id)
                            if union is None: union = found[part.segment_id] = _IntervalUnion()
                            union.append(window)
        return {key: tuple(union) for key,union in sorted(found.items())}

    def close(self):
        for handle in self.handles.values(): handle.close()
        self.handles.clear(); self.cache.clear(); self.cache_ops = 0
        self.connection.close()
