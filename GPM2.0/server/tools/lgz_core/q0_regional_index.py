"""Disk-backed reference/source-cell index for bounded q0 search proposals.

Cells and bridged regions only select mapper inputs. They are never alignment
coverage, placement evidence or permission to edit a source. Every actual
source/source relationship still requires independently validated CIGAR output.
"""
from __future__ import annotations

from collections import defaultdict
from bisect import bisect_left, bisect_right
import json
from pathlib import Path
import sqlite3
from typing import Iterable, Mapping

from .q0_sources import Interval, Q0EvidenceError, SourceSegment, merged_intervals

SCHEMA = "lgz_q0_regional_cells_v1"
DEFAULT_CELL_BASES = 100_000


def paired_cells(query: Interval, target: Interval, strand: str,
                 cell_bases: int) -> Iterable[tuple[int, int]]:
    """Grid cells actually touched by a paired run, not its Cartesian hull."""
    if (query.length != target.length or strand not in {"+", "-"}
            or type(cell_bases) is not int or cell_bases < 1):
        raise Q0EvidenceError("invalid paired-cell geometry")
    q = query.start if strand == "+" else query.end
    t = target.start
    while t < target.end:
        qc = q // cell_bases if strand == "+" else (q-1) // cell_bases
        tc = t // cell_bases
        n = min(target.end-t, (qc+1)*cell_bases-q if strand == "+" else q-qc*cell_bases,
                (tc+1)*cell_bases-t)
        yield qc, tc
        q += n if strand == "+" else -n
        t += n


def search_regions(intervals: Iterable[Interval], *, bridge_bases: int = 0) -> tuple[Interval, ...]:
    """Conservative SEARCH envelopes; bridged gaps are not aligned bases."""
    if type(bridge_bases) is not int or bridge_bases < 0:
        raise Q0EvidenceError("invalid routing bridge")
    result = []
    for interval in merged_intervals(intervals):
        if result and interval.start-result[-1].end <= bridge_bases:
            result[-1] = Interval(result[-1].start, max(result[-1].end, interval.end))
        else:
            result.append(interval)
    return tuple(result)


class RegionalIndex:
    """An immutable sealed index; callers must content-bind a reused database.

    Creating an index never replaces an existing file. `open` validates exact
    source/reference bindings, but does not replace the caller's content hash
    check or success-receipt validation. SQLite keeps the all-genome grid out of
    the Python heap; only the current local target set is materialized there.
    """
    @staticmethod
    def bindings(parts: Mapping[str, SourceSegment], reference_lengths: Mapping[str, int], cell_bases: int) -> dict:
        if type(cell_bases) is not int or cell_bases < 1:
            raise Q0EvidenceError("invalid regional cell size")
        if any(type(n) is not int or n < 1 for n in reference_lengths.values()):
            raise Q0EvidenceError("invalid reference lengths")
        if any(key != part.segment_id for key, part in parts.items()):
            raise Q0EvidenceError("source-part index key differs from its identity")
        return {"schema": SCHEMA, "cell_bases": cell_bases,
                "sources": [[key, p.source.dataset, p.source.contig, p.interval.start,
                             p.interval.end, p.sequence_sha256] for key, p in sorted(parts.items())],
                "references": [[key, length] for key, length in sorted(reference_lengths.items())]}

    def _configure(self, binding: dict) -> None:
        self.binding = binding
        self.cell_bases = binding["cell_bases"]
        self.sources = {row[0]: (i, row[4]-row[3]) for i, row in enumerate(binding["sources"])}
        self.source_ids = [row[0] for row in binding["sources"]]
        self.references = {row[0]: (i, row[1]) for i, row in enumerate(binding["references"])}
        self.reference_ids = [row[0] for row in binding["references"]]
        self._pending: set[tuple[int, int, int, int, int]] = set()
        self.sealed = False
        self.observed_blocks = self.proposed_links = self.cached_duplicates = 0
        self._last_source = None
        self._source_links: set[tuple[int, int, int, int, int]] = set()

    @classmethod
    def create(cls, path: Path, parts: Mapping[str, SourceSegment], reference_lengths: Mapping[str, int],
               *, cell_bases: int = DEFAULT_CELL_BASES) -> RegionalIndex:
        binding = cls.bindings(parts, reference_lengths, cell_bases)
        path = Path(path)
        path.touch(exist_ok=False)
        self = cls.__new__(cls)
        self.path = path
        self._configure(binding)
        self.connection = sqlite3.connect(path)
        self.connection.executescript("""
            PRAGMA journal_mode=DELETE;
            PRAGMA cache_size=-32768;
            PRAGMA temp_store=FILE;
            CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE links (ref INTEGER NOT NULL, cell INTEGER NOT NULL,
                                source INTEGER NOT NULL, tile INTEGER NOT NULL, strand INTEGER NOT NULL,
                                PRIMARY KEY(ref,cell,source,tile,strand)) WITHOUT ROWID;
        """)
        self.connection.execute("INSERT INTO metadata VALUES (?,?)", ("bindings", json.dumps(binding, sort_keys=True)))
        self.connection.commit()
        return self

    @classmethod
    def open(cls, path: Path, parts: Mapping[str, SourceSegment], reference_lengths: Mapping[str, int],
             *, cell_bases: int = DEFAULT_CELL_BASES) -> RegionalIndex:
        self = cls.__new__(cls)
        self.path = Path(path).resolve(strict=True)
        self._configure(cls.bindings(parts, reference_lengths, cell_bases))
        self.connection = sqlite3.connect(self.path.as_uri()+"?mode=ro", uri=True)
        try:
            rows = dict(self.connection.execute("SELECT name,value FROM metadata"))
            if json.loads(rows["bindings"]) != self.binding or rows.get("sealed") != "true":
                raise Q0EvidenceError("unsealed or differently bound regional index")
        except (KeyError, ValueError, sqlite3.Error) as exc:
            self.connection.close()
            raise Q0EvidenceError("invalid regional index identity") from exc
        self.connection.execute("PRAGMA cache_size=-32768")
        self.sealed = True
        return self

    def observe(self, segment_id: str, chromosome: str, query: Interval, target: Interval, strand: str) -> None:
        if self.sealed:
            raise Q0EvidenceError("cannot modify a sealed regional index")
        try:
            source, length = self.sources[segment_id]
            ref, ref_length = self.references[chromosome]
        except KeyError as exc:
            raise Q0EvidenceError("unknown regional source or reference") from exc
        if query.end > length or target.end > ref_length:
            raise Q0EvidenceError("regional paired geometry exceeds input")
        if self._last_source != source:
            self._source_links.clear()
            self._last_source = source
        for tile, cell in paired_cells(query, target, strand, self.cell_bases):
            link = (ref, cell, source, tile, 0 if strand == "+" else 1)
            self.proposed_links += 1
            if link in self._source_links:
                self.cached_duplicates += 1
                continue
            # This is a bounded insertion memo, not a scientific cutoff. Every
            # unseen link is stored; clearing the memo merely permits reinserts.
            if len(self._source_links) >= 250_000:
                self._source_links.clear()
            self._source_links.add(link)
            self._pending.add(link)
            if len(self._pending) >= 50_000:
                self._flush()
        self.observed_blocks += 1

    def _flush(self) -> None:
        if self._pending:
            self.connection.executemany("INSERT OR IGNORE INTO links VALUES (?,?,?,?,?)", sorted(self._pending))
            self._pending.clear()
            self.connection.commit()

    def seal(self) -> dict:
        if self.sealed:
            raise Q0EvidenceError("regional index was already sealed")
        self._flush()
        self.connection.execute("CREATE INDEX by_source ON links(source,tile,ref,strand,cell)")
        count = self.connection.execute("SELECT count(*) FROM links").fetchone()[0]
        report = {"observed_paired_blocks": self.observed_blocks, "proposed_links": self.proposed_links,
                  "stored_links": count, "cached_duplicate_links": self.cached_duplicates, "schema": SCHEMA}
        self.connection.executemany("INSERT INTO metadata VALUES (?,?)",
                                   [("sealed", "true"), ("build_report", json.dumps(report, sort_keys=True))])
        self.connection.commit()
        self.sealed = True
        return report

    def regions(self, segment_id: str, query: Interval, *, anchor_context: int,
                reference_context: int, bridge_bases: int) -> dict[str, tuple[Interval, ...]]:
        if not self.sealed or any(type(n) is not int or n < 0 for n in (anchor_context, reference_context, bridge_bases)):
            raise Q0EvidenceError("unsealed index or invalid regional context")
        try:
            source, length = self.sources[segment_id]
        except KeyError as exc:
            raise Q0EvidenceError("unknown regional query") from exc
        if query.end > length:
            raise Q0EvidenceError("regional query exceeds source")
        low = max(0, query.start-anchor_context)//self.cell_bases
        high = (min(length, query.end+anchor_context)-1)//self.cell_bases
        direct_low = query.start//self.cell_bases
        direct_high = (query.end-1)//self.cell_bases
        found: dict[str, list[Interval]] = defaultdict(list)
        nearest = {}
        def add(ref, start, end):
            name = self.reference_ids[ref]; _, limit = self.references[name]
            found[name].append(Interval(max(0, start-reference_context), min(limit, end+reference_context)))
        for ref, cell, tile, strand in self.connection.execute(
                "SELECT ref,cell,tile,strand FROM links WHERE source=? AND tile BETWEEN ? AND ?", (source, low, high)):
            if direct_low <= tile <= direct_high:
                add(ref, cell*self.cell_bases, (cell+1)*self.cell_bases)
            else:
                side = "left" if tile < direct_low else "right"
                key = ref, strand, side
                previous = nearest.get(key)
                if previous is None or (tile > previous[0] if side == "left" else tile < previous[0]):
                    nearest[key] = (tile, {cell})
                elif tile == previous[0]:
                    previous[1].add(cell)
        for (ref, strand, side), (tile, cells) in nearest.items():
            for cell in cells:
                add(ref, cell*self.cell_bases, (cell+1)*self.cell_bases)
            if side != "left" or (ref, strand, "right") not in nearest:
                continue
            right_tile, right_cells = nearest[ref, strand, "right"]
            # Search-only hulls between consistently ordered nearest flanks.
            # Find the outermost compatible opposite flank without a Cartesian
            # loop over repetitive alternatives; retain all unpaired flanks too.
            maximum = (query.length + max(0, query.start-(tile+1)*self.cell_bases)
                       + max(0, right_tile*self.cell_bases-query.end) + anchor_context + 2*self.cell_bases)
            reach = max(0, maximum//self.cell_bases-1)
            rights = sorted(right_cells)
            for left in cells:
                if strand == 0:
                    index = bisect_right(rights, left+reach)-1
                    if index >= 0 and rights[index] >= left:
                        add(ref, left*self.cell_bases, (rights[index]+1)*self.cell_bases)
                else:
                    index = bisect_left(rights, left-reach)
                    if index < len(rights) and rights[index] <= left:
                        add(ref, rights[index]*self.cell_bases, (left+1)*self.cell_bases)
        return {name: search_regions(rows, bridge_bases=bridge_bases) for name, rows in sorted(found.items())}

    def targets(self, regions: Mapping[str, Iterable[Interval]], *, context: int = 10_000,
                exclude: Iterable[str] = ()) -> dict[str, tuple[Interval, ...]]:
        if not self.sealed or type(context) is not int or context < 0:
            raise Q0EvidenceError("unsealed index or invalid target context")
        excluded = set(exclude)
        if not excluded <= self.sources.keys():
            raise Q0EvidenceError("unknown excluded source part")
        tiles: dict[int, set[int]] = defaultdict(set)
        for name, intervals in regions.items():
            if name not in self.references:
                raise Q0EvidenceError("unknown target reference")
            ref, limit = self.references[name]
            for interval in intervals:
                if interval.end > limit:
                    raise Q0EvidenceError("target reference region exceeds input")
                lo, hi = interval.start//self.cell_bases, (interval.end-1)//self.cell_bases
                for source, tile in self.connection.execute("SELECT source,tile FROM links WHERE ref=? AND cell BETWEEN ? AND ?", (ref, lo, hi)):
                    if self.source_ids[source] not in excluded:
                        tiles[source].add(tile)
        result = {}
        for source, values in sorted(tiles.items()):
            key = self.source_ids[source]; _, limit = self.sources[key]
            result[key] = merged_intervals(Interval(max(0, tile*self.cell_bases-context),
                min(limit, (tile+1)*self.cell_bases+context)) for tile in values)
        return result

    def build_report(self) -> dict:
        if not self.sealed:
            raise Q0EvidenceError("regional index is not sealed")
        row = self.connection.execute("SELECT value FROM metadata WHERE name='build_report'").fetchone()
        if row is None:
            raise Q0EvidenceError("regional build report is missing")
        return json.loads(row[0])

    def close(self) -> None:
        self.connection.close()
