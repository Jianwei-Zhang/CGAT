"""Pinned native-coordinate formats for TGS-GapCloser, quarTeT and LR_Gapcloser.

All ranges returned here are trace components, not automatically accepted edits.
The caller verifies their reconstruction against every native chromosome before
projecting them onto the immutable original LGZ gap inventory.
"""
from __future__ import annotations

from collections import defaultdict
import copy
from pathlib import Path
import re

try:
    from refinement_path import COMPLEMENT, identity
    from refinement_native_trace import TraceError, retained, inserted, trace_slice, apply_changes, verify_trace
except ModuleNotFoundError:
    from .refinement_path import COMPLEMENT, identity
    from .refinement_native_trace import TraceError, retained, inserted, trace_slice, apply_changes, verify_trace


class CandidateStore:
    def __init__(self, path, catalog, dataset, tool):
        self.path, self.catalog, self.dataset, self.tool = Path(path), catalog, dataset, tool
        self.stream = self.path.open("xb")
        self.records = {}

    def add(self, name, sequence):
        sequence = sequence.upper()
        if not sequence or re.search(br"[^ACGTRYSWKMBDHVN]", sequence):
            raise TraceError("native candidate has empty or non-IUPAC sequence")
        identifier = self.tool + "_" + identity(name)[:32]
        if identifier in self.records:
            raise TraceError("duplicate extracted native candidate identity")
        self.records[identifier] = len(sequence)
        self.stream.write(b">" + identifier.encode("ascii") + b"\n" + sequence + b"\n")
        return {"dataset": self.dataset, "contig": identifier, "start": 1, "end": len(sequence), "orientation": "+"}

    def finish(self):
        self.stream.close()
        for name in self.records:
            self.catalog.register(self.dataset, name, self.path, origin="native:" + self.tool)

    def close(self):
        if not self.stream.closed:
            self.stream.close()


class ReadLookup:
    """Index only requested records; never load a whole reads FAI into Python."""
    def __init__(self, requests):
        self.records = {}
        grouped = defaultdict(list)
        for request in requests:
            grouped[Path(request["path"]).resolve()].append(request)
        for path, queries in grouped.items():
            ids = {q["id"] for q in queries if "id" in q}
            ordinals = {q["ordinal"] for q in queries if "ordinal" in q}
            with Path(str(path) + ".fai").open() as stream:
                for ordinal, line in enumerate(stream, 1):
                    fields = line.rstrip("\n").split("\t")
                    if len(fields) < 5:
                        raise TraceError("converted reads FAI is malformed")
                    name = fields[0]
                    if name in ids or ordinal in ordinals:
                        values = tuple(map(int, fields[1:5]))
                        if values[0] <= 0 or values[2] <= 0 or values[3] < values[2]:
                            raise TraceError("converted reads FAI has invalid lengths")
                        entry = (name, *values)
                        if name in ids:
                            self.records[path, name] = entry
                        if ordinal in ordinals:
                            self.records[path, ordinal] = entry
            for query in queries:
                if (path, query.get("id", query.get("ordinal"))) not in self.records:
                    raise TraceError("native read identity is absent from the actual converted input")

    def fetch(self, request, start, end, strand):
        path = Path(request["path"]).resolve()
        key = request.get("id", request.get("ordinal"))
        name, length, offset, bases, width = self.records[path, key]
        split = request.get("split")
        a, b = start - 1, end
        if split:
            raw = self._slice(path, offset, bases, width, 0, length)
            parts = list(re.finditer(br"N{100,}", raw))
            ranges, cursor = [], 0
            for match in parts:
                ranges.append((cursor, match.start()))
                cursor = match.end()
            ranges.append((cursor, len(raw)))
            if not 1 <= split <= len(ranges):
                raise TraceError("quarTeT split-read ordinal is invalid")
            left, right = ranges[split - 1]
            if not 0 <= a < b <= right - left:
                raise TraceError("native split-read interval exceeds its source")
            a, b = a + left, b + left
        if not 0 <= a < b <= length or strand not in {"+", "-"}:
            raise TraceError("native read interval/strand is outside its source")
        sequence = self._slice(path, offset, bases, width, a, b)
        if strand == "-":
            sequence = sequence.translate(COMPLEMENT)[::-1]
        return sequence, {"converted_fasta": str(path), "converted_id": name, "source_start": a + 1,
                          "source_end": b, "orientation": strand, "native_read_ordinal": request.get("ordinal")}

    @staticmethod
    def _slice(path, offset, bases, width, a, b):
        if a == b:
            return b""
        first = offset + a // bases * width + a % bases
        last = offset + (b - 1) // bases * width + (b - 1) % bases + 1
        with path.open("rb") as stream:
            stream.seek(first)
            sequence = stream.read(last - first).replace(b"\n", b"").replace(b"\r", b"").upper()
        if len(sequence) != b - a or re.search(br"[^ACGTRYSWKMBDHVN]", sequence):
            raise TraceError("converted read sequence/index mismatch")
        return sequence


def tgs_rows(path, store=None):
    rows, scaffold = defaultdict(list), None
    with Path(path).open() as stream:
        for line_number, line in enumerate(stream, 1):
            fields = line.split()
            if not fields:
                continue
            if fields[0] == ">scaffold" and len(fields) == 2:
                scaffold = int(fields[1])
                if scaffold in rows:
                    raise TraceError("duplicate TGS scaffold block")
                rows[scaffold] = []
                continue
            if scaffold is None or len(fields) < 7:
                raise TraceError("malformed TGS scaffold info")
            row = {"id": int(fields[0]), "strand": fields[1], "gap": int(fields[2]), "length": int(fields[3]),
                   "start": int(fields[4]) - 1, "index": int(fields[5]), "scaffold": int(fields[6]),
                   "extra": {}, "line": line_number}
            for token in fields[7:]:
                key, value = token.split("=", 1)
                if key in row["extra"]:
                    raise TraceError("duplicate TGS metadata key")
                row["extra"][key] = value
            if "ONT_FILL" in row["extra"]:
                if store is None:
                    raise TraceError("TGS original scaffold unexpectedly contains filled sequence")
                sequence = row["extra"].pop("ONT_FILL").encode("ascii")
                if len(sequence) != row["gap"]:
                    raise TraceError("TGS filler length disagrees with gap size")
                row["filler"] = store.add(["tgs", scaffold, row["id"], line_number], sequence)
            if row["strand"] != "+" or row["scaffold"] != scaffold or row["length"] < 0 or row["start"] < 0:
                raise TraceError("unsupported or invalid TGS original-contig identity")
            rows[scaffold].append(row)
    return dict(rows)


def parse_tgs(directory, baseline, names, store):
    """Use original/updated scaffold rows; cross-check the native detail trace."""
    mapping = {}
    with (directory / "tgs.name_map").open() as stream:
        for line in stream:
            fields = line.split()
            if len(fields) != 2 or fields[1] not in names or int(fields[0]) in mapping:
                raise TraceError("invalid TGS scaffold name map")
            mapping[int(fields[0])] = names[fields[1]]
    original = tgs_rows(directory / "tgs.orignial_scaff_infos")
    updated = tgs_rows(directory / "tgs.updated_scaff_infos", store)
    if set(mapping) != set(original) or set(original) != set(updated) or set(mapping.values()) != set(baseline.records):
        raise TraceError("TGS scaffold records do not cover the baseline")
    traces, original_traces, expected_details = {}, {}, {}
    for sid, old_rows in original.items():
        name, before, after, details, output = mapping[sid], [], [], [], 0
        new_rows = updated[sid]
        if len(old_rows) != len(new_rows):
            raise TraceError("TGS changed scaffold member identities")
        for old, new in zip(old_rows, new_rows):
            if any(old[key] != new[key] for key in ("id", "strand", "length", "start", "index", "scaffold")):
                raise TraceError("TGS changed an original scaffold member identity")
            prev_n = int(old["extra"].get("PREV_N", "0"))
            if prev_n < 0 or new["extra"].get("PREV_N", "0") != old["extra"].get("PREV_N", "0") or old["gap"] < 0:
                raise TraceError("TGS leading/original N coordinates changed")
            start, length = old["start"] - prev_n, old["length"] + prev_n
            if length:
                before.append(retained(start, start + length))
            if old["gap"]:
                before.append({"kind": "gap", "length": old["gap"], "evidence": {}})
            keep = max(0, length + min(0, new["gap"]))
            evidence = {"file": "tgs.updated_scaff_infos", "line": new["line"], "native_contig": new["id"],
                        "original_gap_size": old["gap"], "native_gap_size": new["gap"]}
            if not keep:
                continue  # Same zero-body behavior as the pinned tgsseqgen.
            after.append(retained(start, start + keep, evidence))
            details.append((output, output + keep, "S", start, start + keep))
            output += keep
            if new["gap"] > 0:
                if "filler" in new:
                    after.append(inserted(new["filler"], evidence))
                    kind = "F"
                else:
                    after.append({"kind": "gap", "length": new["gap"], "evidence": evidence})
                    kind = "N"
                details.append((output, output + new["gap"], kind))
                output += new["gap"]
        traces[name], original_traces[name], expected_details[name] = after, before, details
    observed, name = {}, None
    with (directory / "tgs.gap_fill_detail").open() as stream:
        for line in stream:
            fields = line.split()
            if not fields:
                continue
            if fields[0].startswith(">"):
                raw = fields[0][1:]
                if raw not in names or names[raw] in observed:
                    raise TraceError("unknown/duplicate TGS detail chromosome")
                name = names[raw]
                observed[name] = []
            elif name is not None and len(fields) in {3, 5}:
                row = (int(fields[0]) - 1, int(fields[1]), fields[2])
                if fields[2] == "S" and len(fields) == 5:
                    row += (int(fields[3]) - 1, int(fields[4]))
                elif fields[2] not in {"F", "N"} or len(fields) != 3:
                    raise TraceError("invalid TGS detail coordinates")
                observed[name].append(row)
            else:
                raise TraceError("malformed TGS native detail")
    if observed != expected_details:
        raise TraceError("TGS detail disagrees with original/updated scaffold evidence")
    return traces, original_traces


def quartet_request(raw, prepared, directory):
    file, name = raw.rsplit("@", 1)
    requested = Path(file)
    allowed = {str(Path(path).resolve()): Path(path).resolve() for path in prepared}
    resolved = str((directory / requested).resolve()) if not requested.is_absolute() else str(requested.resolve())
    if resolved in allowed:
        return {"path": allowed[resolved], "id": name}
    for path in allowed.values():
        if resolved == str((directory / "tmp" / (path.name + ".splitcontig.fasta")).resolve()):
            match = re.fullmatch(r"(.+)_tig([1-9][0-9]*)", name)
            if match:
                return {"path": path, "id": match[1], "split": int(match[2])}
            # Reads without long N runs retain their original ID in the split file.
            return {"path": path, "id": name}
    raise TraceError("quarTeT filler is outside the actual selected reads")


def parse_quartet(directory, baseline, gaps, names, prepared, store):
    rows, requests = defaultdict(list), []
    with (directory / "quartet.genome.filled.modified.agp").open() as stream:
        for line_number, line in enumerate(stream, 1):
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 9 or fields[0] not in names:
                raise TraceError("invalid quarTeT native AGP row")
            row = {"fields": fields, "line": line_number}
            if fields[4] == "W":
                row["request"] = quartet_request(fields[5], prepared, directory)
                requests.append(row["request"])
            rows[names[fields[0]]].append(row)
    lookup = ReadLookup(requests)
    details = {}
    with (directory / "quartet.genome.filled.detail").open() as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 3 or fields[0] not in names or fields[2] not in {"Closed", "Not_closed"}:
                raise TraceError("malformed quarTeT filling detail")
            key = names[fields[0]], int(fields[1])
            if key in details:
                raise TraceError("duplicate quarTeT gap identity")
            details[key] = (fields, line_number)
    by_chr = defaultdict(list)
    for gap in gaps:
        by_chr[gap.chromosome].append(gap)
    traces, used = {}, set()
    for name, (length, *_) in baseline.records.items():
        if name not in rows:
            traces[name] = [retained(0, length)]
            continue
        trace, cursor, previous_end, part = [], 0, 0, 0
        for row in rows[name]:
            fields, line_number = row["fields"], row["line"]
            start, end = int(fields[1]) - 1, int(fields[2])
            part += 1
            if start != cursor or end <= start or int(fields[3]) != part:
                raise TraceError("noncontiguous quarTeT native AGP")
            kind, size = fields[4], end - start
            evidence = {"file": "quartet.genome.filled.modified.agp", "line": line_number}
            if kind == "P":
                if fields[5] not in names or names[fields[5]] != name or fields[8] != "+":
                    raise TraceError("quarTeT original source identity changed")
                a, b = int(fields[6]) - 1, int(fields[7])
                if b - a != size or a != previous_end or b > length:
                    raise TraceError("quarTeT original source interval is invalid")
                trace.append(retained(a, b, evidence))
                previous_end = b
            elif kind == "W":
                start_read, end_read, strand = int(fields[6]), int(fields[7]), fields[8]
                sequence, origin = lookup.fetch(row["request"], start_read, end_read, strand)
                if len(sequence) != size:
                    raise TraceError("quarTeT read interval length differs from native AGP")
                possible = [gap for gap in by_chr[name] if gap.start == previous_end]
                if len(possible) != 1:
                    raise TraceError("quarTeT filler has no original gap boundary")
                gap = possible[0]
                ordinal = by_chr[name].index(gap) + 1
                detail = details.get((name, ordinal))
                if (detail is None or len(detail[0]) != 8 or detail[0][2] != "Closed"
                        or detail[0][3] != fields[5] or detail[0][4] != f"{start_read}-{end_read}"
                        or int(detail[0][5]) != size or detail[0][6] != strand):
                    raise TraceError("quarTeT gap/detail identity disagrees with its actual replacement")
                used.add((name, ordinal))
                evidence.update(read_origin=origin, native_detail_line=detail[1], original_gap_id=gap.gap_id)
                trace.append(inserted(store.add([name, part], sequence), evidence))
                previous_end = gap.end
            elif kind in {"N", "U"}:
                if int(fields[5]) != size:
                    raise TraceError("quarTeT gap component length mismatch")
                if previous_end + size > length or any(block.upper().strip(b"N") for block in baseline.blocks(name, previous_end, previous_end + size)):
                    raise TraceError("quarTeT unfilled component is not the original gap")
                trace.append({"kind": "gap", "length": size, "evidence": evidence})
                previous_end += size
            else:
                raise TraceError("unsupported quarTeT native AGP component")
            cursor = end
        # Join mode is disabled. No sequence may vanish without a W replacement.
        if previous_end != length:
            raise TraceError("quarTeT AGP does not account for the complete original chromosome")
        traces[name] = trace
    if used != {key for key, (fields, _) in details.items() if fields[2] == "Closed"}:
        raise TraceError("quarTeT reports candidates not applied to their original gap identities")
    return traces


def lr_interval(text, names=None, read=False):
    fields = text.split("(:")
    if len(fields) != (3 if read else 2):
        raise TraceError("malformed LR_Gapcloser interval identity")
    match = re.fullmatch(r"([1-9][0-9]*)-([1-9][0-9]*)", fields[1])
    if not match:
        raise TraceError("malformed LR_Gapcloser interval")
    a, b = sorted(map(int, match.groups()))
    if read:
        ordinal = re.fullmatch(r"LR([1-9][0-9]*)", fields[0])
        if not ordinal or fields[2] not in {"+", "-"}:
            raise TraceError("LR_Gapcloser read identity/strand is unsupported")
        return int(ordinal[1]), a, b, fields[2]
    if fields[0] not in names:
        raise TraceError("LR_Gapcloser chromosome is absent from its native input")
    return names[fields[0]], a - 1, b


def parse_lr_rows(paths, names, prepared):
    rounds, requests = [], []
    for path in paths:
        rows, first, prefix = [], {}, set()
        with path.open() as stream:
            for number, line in enumerate(stream, 1):
                fields = line.rstrip("\n").split("\t")
                if len(fields) != 3:
                    raise TraceError("malformed LR_Gapcloser replacement record")
                gap = lr_interval(fields[0], names)
                read = lr_interval(fields[1], read=True)
                region = lr_interval(fields[2], names)
                if gap[0] != region[0]:
                    raise TraceError("LR_Gapcloser gap and replacement chromosome differ")
                request = {"path": Path(prepared), "ordinal": read[0]}
                requests.append(request)
                row = {"fields": fields, "gap": gap, "read": read, "region": region,
                       "request": request, "line": number}
                # Reproduce the pinned writer's duplicate-gap prefix selection.
                if fields[0] not in first:
                    first[fields[0]] = row
                elif region[2] > first[fields[0]]["region"][2]:
                    prefix.add(fields[1])
                else:
                    prefix.add(first[fields[0]]["fields"][1])
                rows.append(row)
        for row in rows:
            # Pinned negative-strand branch stores its pre-prefix reverse result.
            row["prefix_n"] = 100 if row["fields"][1] in prefix and row["read"][3] == "+" else 0
        rounds.append(rows)
    return rounds, ReadLookup(requests)


def apply_lr_round(trace, rows, baseline, previous, names, lookup, store, round_number):
    changes = defaultdict(list)
    for row in rows:
        chromosome, start, end = row["region"]
        gap_chr, gap_start, gap_end = row["gap"]
        if not 0 <= start < end <= previous.records[chromosome][0] or not 0 <= gap_start < gap_end <= previous.records[chromosome][0]:
            raise TraceError("LR_Gapcloser replacement exceeds its preceding assembly")
        if not (start < gap_end and gap_start < end):
            raise TraceError("LR_Gapcloser replacement does not intersect its declared gap")
        for block in previous.blocks(gap_chr, gap_start, gap_end):
            if block.upper().strip(b"N"):
                raise TraceError("LR_Gapcloser gap identity is not an N interval")
        _, a, b, strand = row["read"]
        sequence, origin = lookup.fetch(row["request"], a, b, strand)
        evidence = {"file": f"iteration-{round_number}/tmp/info_filter2", "line": row["line"],
                    "native_gap": list(row["gap"]), "native_replacement": list(row["region"]),
                    "read_origin": origin, "native_prefix_n": row["prefix_n"],
                    "replaced_parent_trace": trace_slice(trace[chromosome], start, end)}
        pieces = []
        if row["prefix_n"]:
            pieces.append({"kind": "gap", "length": row["prefix_n"], "evidence": evidence})
        pieces.append(inserted(store.add([round_number, row["line"]], sequence), evidence))
        changes[chromosome].append((start, end, pieces))
    return {name: apply_changes(pieces, changes.get(name, [])) for name, pieces in trace.items()}
