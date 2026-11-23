"""Checked MUMmer overlap adapter for immutable extension-family versions."""
import hashlib
import math
import os
from pathlib import Path
import shutil
import subprocess
from dataclasses import replace

from ExtensionFamilies import Connection, atomic_json, fingerprint, read_json


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_sequence(path):
    """Read one full sequence; input identities are validated by FamilySearch."""
    sequence = []
    headers = 0
    with open(path) as stream:
        for line in stream:
            text = line.strip()
            if not text:
                continue
            if text.startswith(">"):
                headers += 1
            elif headers != 1 or any(c.isspace() for c in text):
                raise ValueError(f"Invalid single-record FASTA: {path}")
            else:
                sequence.append(text)
    if headers != 1 or not sequence:
        raise ValueError(f"Expected one nonempty FASTA record: {path}")
    return "".join(sequence)


def parse_coords(path, left, right, *, left_offset, left_tail_length,
                 right_tail_length, edge, min_overlap=10000, allow_containment=False, diagnostics=None):
    """Reference is right prefix; query is left suffix, as in old linkgap.

    Reject inverted overlaps. Return full sequence, zero-based half-open
    coordinates. The old initial direct check required identity >=80%; later
    linkgap did not impose that extra threshold. Keep that distinction explicit.
    """
    matches = []
    blocks = []
    stats = diagnostics if diagnostics is not None else {}
    stats.update(blocks=0, short=0, nonterminal=0, inverted=0)
    initial = left.number == right.number == 0
    with open(path) as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            fields = line.rstrip().split("\t")
            try:
                if len(fields) != 13:
                    raise ValueError("expected show-coords -TrHcl fields")
                a, b, c, d, ref_span, qry_span = map(int, fields[:6])
                identity = float(fields[6])
                ref_length, qry_length = map(int, fields[7:9])
                if (ref_length != right_tail_length or qry_length != left_tail_length or
                        fields[11:] != ["right", "left"] or
                        not math.isfinite(identity) or not 0 <= identity <= 100 or
                        not all(1 <= n <= ref_length for n in (a, b)) or
                        not all(1 <= n <= qry_length for n in (c, d)) or
                        ref_span != abs(b - a) + 1 or qry_span != abs(d - c) + 1):
                    raise ValueError("inconsistent coordinates or sequence identities")
            except (ValueError, IndexError) as error:
                raise ValueError(f"Invalid MUMmer coordinates at {path}:{line_number}: {error}") from error
            stats["blocks"] += 1
            if a > b or c > d:
                stats["inverted"] += 1
                continue
            if initial and identity < 80:
                continue
            blocks.append((c - 1 + left_offset, d + left_offset, a - 1, b, identity))
            if ref_span < min_overlap:
                stats["short"] += 1
                continue
            left_start, left_end = c - 1 + left_offset, d + left_offset
            right_start, right_end = a - 1, b
            # Old direct connection used zero-based endpoint distance; linkgap
            # used one-based reference start <= edge. Do not silently relax it.
            allowed_right_start = edge if initial else edge - 1
            terminal = left.length-left_end <= edge and right_start <= allowed_right_start
            contained = allow_containment and (
                (left_start <= edge and left.length-left_end <= edge) or
                (right_start <= edge and right.length-right_end <= edge))
            if not terminal and not contained:
                stats["nonterminal"] += 1
                continue
            matches.append(Connection(
                left.family, left.number, right.family, right.number,
                identity, ref_span, left.length - left_end + right_start,
                left_start, left_end, right_start, right_end,
                {"alignment_type": "containment"} if contained and not terminal else None))
    # Chains must be monotone and nonoverlapping in BOTH sequences. Missing
    # intervals never count as aligned support. Bound small interruptions instead
    # of joining arbitrary repeat blocks into an invented bridge.
    blocks.sort()
    chains = []
    for index, block in enumerate(blocks):
        ls, le, rs, re, ident = block
        weight = min(le - ls, re - rs)
        options = [([block], weight, ident * weight)]
        for chain, covered, score in chains:
            prev = chain[-1]
            lg, rg = ls - prev[1], rs - prev[3]
            if (0 <= lg <= edge and 0 <= rg <= edge and
                    abs(lg - rg) <= max(20, int(0.05 * max(lg, rg)))):
                options.append((chain + [block], covered + weight, score + ident * weight))
        # Keep the best path ending here; do not enumerate exponentially many chains.
        best = max(options, key=lambda item: (item[1], item[2] / item[1]))
        chains.append(best)
        chain, covered, score = best
        if len(chain) < 2 or covered < min_overlap:
            continue
        first, last = chain[0], chain[-1]
        allowed = edge if initial else edge - 1
        if left.length - last[1] > edge or first[2] > allowed:
            continue
        matches.append(Connection(left.family, left.number, right.family, right.number,
                                  score / covered, covered, left.length - last[1] + first[2],
                                  first[0], last[1], first[2], last[3],
                                  {"alignment_type": "collinear_chain", "blocks": len(chain),
                                   "unresolved_bases": sum(max(b[0]-a[1], b[2]-a[3])
                                                           for a, b in zip(chain, chain[1:]))}))
    return matches


class MummerOverlap:
    """Cache seed-end extraction and completed tool stages, not mutable histories."""

    def __init__(self, directory, edge, *, tools=None):
        if type(edge) is not int or edge < 0:
            raise ValueError("edge must be a nonnegative integer")
        self.directory = Path(directory)
        self.edge = edge
        self.tail_length = edge + 20000
        self.tools = {}
        for name in ("nucmer", "delta-filter", "show-coords"):
            executable = (tools or {}).get(name) or shutil.which(name)
            if not executable:
                raise FileNotFoundError(f"Required overlap tool is unavailable: {name}")
            self.tools[name] = str(Path(executable).resolve())
        self.contract = {
            "adapter": "family-mummer-v2", "chaining": "bounded-collinear-v1", "fallback": "full-sequence", "edge": edge, "min_overlap": 10000,
            "tail_length": self.tail_length,
            "tools": {name: {"path": path, "sha256": file_hash(path)}
                      for name, path in self.tools.items()},
        }
        self.ends = {}
        self.validator = None
        self.diagnostics = {}

    def _end(self, version, side):
        key = (version, side)
        stat = os.stat(version.path)
        stamp = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        if key in self.ends and self.ends[key][0] == stamp:
            return self.ends[key][1:]
        # One verification/extraction per immutable version, not per opposite
        # historical version. Keep only the small tail in memory.
        version.verify()
        sequence = read_sequence(version.path)
        if len(sequence) != version.length:
            raise ValueError("FASTA length changed while extracting its endpoint")
        tail = sequence[-self.tail_length:] if side == "left" else sequence[:self.tail_length]
        offset = version.length - len(tail) if side == "left" else 0
        self.ends[key] = (stamp, tail, offset)
        return tail, offset

    def _stage(self, directory, name, command, inputs, output, *, generated=None):
        receipt_file = directory / (name + ".json")
        identity = fingerprint({"contract": self.contract, "name": name,
                                "command": command, "inputs": {str(p): file_hash(p) for p in inputs}})
        if receipt_file.exists():
            receipt = read_json(receipt_file)
            if (receipt.get("identity") != identity or not output.exists() or
                    receipt.get("sha256") != file_hash(output)):
                raise ValueError(f"Invalid completed overlap stage: {receipt_file}")
            return
        temporary = output.with_name(output.name + ".pending")
        with (directory / (name + ".stderr.log")).open("wb") as errors:
            if generated is not None:
                subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=errors)
                if not generated.is_file() or generated.stat().st_size == 0:
                    raise ValueError(f"Overlap tool did not produce a delta file: {name}")
                os.replace(generated, output)
            else:
                with temporary.open("wb") as stream:
                    subprocess.run(command, check=True, stdout=stream, stderr=errors)
                if name == "delta-filter" and temporary.stat().st_size == 0:
                    raise ValueError("delta-filter produced an invalid empty delta file")
                os.replace(temporary, output)
        atomic_json(receipt_file, {"identity": identity, "sha256": file_hash(output)})

    def configure_boundaries(self, base, seeds):
        from JunctionRepair import BoundaryVerifier
        self.validator = BoundaryVerifier(base, seeds, self.directory / "junctions")

    def diagnostic(self, left, right):
        return self.diagnostics.get((left, right), {})

    def __call__(self, left, right):
        stages = []
        accepted = []
        # An empty clipped comparison is not proof of no full-sequence overlap.
        for full in (False, True):
            matches, directory, stats = self._compare(left, right, full=full)
            reasons = []
            for candidate in matches:
                details = dict(candidate.evidence or {})
                details.update(stage="full" if full else "fast", adapter=self.contract["adapter"])
                candidate = replace(candidate, evidence=details)
                if self.validator:
                    candidate, reason = self.validator(candidate, left, right, directory)
                    if candidate is None:
                        reasons.append(reason)
                        continue
                accepted.append(candidate)
            stages.append({"stage": "full" if full else "fast", "blocks": stats["blocks"], "rejections": stats,
                "candidates": len(accepted), "reason": "; ".join(sorted(set(reasons))) or (
                    "eligible_connection" if accepted else (
                        "non_terminal_alignment" if stats["nonterminal"] else
                        "overlap_below_minimum" if stats["short"] else
                        "inverted_alignment" if stats["inverted"] else "no_alignment"))})
            if accepted or (left.length <= self.tail_length and right.length <= self.tail_length):
                break
        info = {"left_family": left.family, "left_version": left.number,
                "right_family": right.family, "right_version": right.number,
                "stages": stages, "status": "eligible" if accepted else "rejected",
                "reason": stages[-1]["reason"]}
        self.diagnostics[(left, right)] = info
        return accepted

    def _compare(self, left, right, *, full):
        if full:
            left.verify(); right.verify()
            left_tail, right_tail, offset = read_sequence(left.path), read_sequence(right.path), 0
        else:
            left_tail, offset = self._end(left, "left")
            right_tail, _ = self._end(right, "right")
        pair_id = fingerprint([left.sha256, left.length, right.sha256, right.length,
                               self.contract, "full" if full else "fast"])
        directory = self.directory / pair_id
        directory.mkdir(parents=True, exist_ok=True)
        paths = {}
        for side, sequence in (("left", left_tail), ("right", right_tail)):
            path = directory / (side + ".fa")
            content = f">{side}\n{sequence}\n"
            if path.exists():
                if path.read_text() != content:
                    raise ValueError(f"Cached overlap endpoint changed: {path}")
            else:
                path.write_text(content)
            paths[side] = path
        prefix = directory / "nucmer.pending"
        delta = directory / "alignment.delta"
        self._stage(directory, "nucmer",
                    [self.tools["nucmer"], "-c", "90", "-l", "40", "-p", str(prefix),
                     str(paths["right"]), str(paths["left"])],
                    [paths["right"], paths["left"]], delta,
                    generated=Path(str(prefix) + ".delta"))
        filtered = directory / "alignment.filtered.delta"
        self._stage(directory, "delta-filter",
                    [self.tools["delta-filter"], "-m", str(delta)], [delta], filtered)
        coords = directory / "alignment.coords"
        self._stage(directory, "show-coords",
                    [self.tools["show-coords"], "-TrHcl", str(filtered)], [filtered], coords)
        stats = {}
        matches = parse_coords(coords, left, right, left_offset=offset,
                               left_tail_length=len(left_tail), right_tail_length=len(right_tail),
                               edge=self.edge, allow_containment=(full or (offset == 0 and len(right_tail) == right.length)), diagnostics=stats)
        return matches, directory, stats


def joined_sequence(connection, left, right):
    """Keep the left overlap copy and right continuation, using full coordinates.

    Trim tolerated unaligned gap-facing overhangs; never cut by overlap length
    alone (gapped alignments need not have equal spans).
    """
    from ExtensionFamilies import FamilySearch
    FamilySearch._validate_connection(connection, left, right)
    left.verify()
    right.verify()
    if (connection.evidence or {}).get("plan_path"):
        from JunctionRepair import load_plan, plan_sequence
        return plan_sequence(load_plan(connection.evidence))
    a, b = read_sequence(left.path), read_sequence(right.path)
    return a[:connection.left_end] + b[connection.right_end:]
