#!/usr/bin/env python3
"""Optional, provenance-bound post-LGZ gap filling. Never rewrites LGZ/Final Path.

The bundled engine proposes replacements. Admission here only replaces maximal
internal N runs, retaining every original non-gap base. Native process success
and its integrated FASTA are deliberately not acceptance evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from run_resources import execution_threads
from run_orchestration import sha256_file

PURPOSE = "post_lgz_degap_v1"
OUTPUT = "data/degap/post_lgz.fa"
REPORT = "metadata/degap_gapfill.json"
CHECKPOINT = "degap/checkpoint.json"
CHUNK = 1024 * 1024
NATIVE_COMMANDS = ("python", "samtools", "minimap2", "seqkit", "hifiasm", "parallel", "rg")


def check_native_paths(root: Path, reads=()) -> None:
    # The pinned native job writer interpolates resolved paths into shell scripts.
    # Reject unsupported paths instead of executing shell metacharacters or silently
    # running in a different directory. Native per-gap scripts also interpolate
    # the original reads paths, despite the outer invocation using an argv list.
    for path in (root.resolve(), Path(__file__).resolve().parent, *(Path(p).resolve() for p in reads)):
        if re.fullmatch(r"[A-Za-z0-9_./-]+", str(path)) is None:
            raise ValueError("bundled DEGAP requires workspace/runtime/reads paths without spaces or shell metacharacters")


def check_environment(root: Path, reads=()) -> None:
    check_native_paths(root, reads)
    missing = [name for name in NATIVE_COMMANDS if not shutil.which(name)]
    for name in ("Bio", "pysam", "numpy", "matplotlib", "scipy"):
        try:
            importlib.import_module(name)
        except (ImportError, OSError):
            missing.append("Python " + name)
    if missing:
        raise ValueError("DEGAP environment unavailable: " + ", ".join(missing)
                         + "; activate the shared Server environment and run install.sh --check")


def digest(path: Path) -> str:
    # Shared process-local memo: only stable byte reads populate it. Never trust
    # a persistent stat-only receipt, or rehash the same artifact in one process.
    return sha256_file(path)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def stat_key(path: Path) -> tuple:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def input_binding(root: Path, engine: Path) -> tuple[str, dict[Path, tuple]]:
    config = load_json(root / "metadata/degap_inputs.json")
    if (config.get("schema_version") != 1 or config.get("purpose") != PURPOSE
            or config.get("reads_type") not in {"hifi", "ont"}
            or not isinstance(config.get("reads"), list) or not config["reads"]
            or any(not isinstance(p, str) or not Path(p).is_absolute() for p in config["reads"])):
        raise ValueError("invalid post-LGZ reads contract; do not reinterpret legacy reads QC")
    check_native_paths(root, config["reads"])
    paths = [root / "metadata/degap_inputs.json", root / "grt/q/q3.fa",
             root / "metadata/grt_final_path.json", Path(__file__).resolve()]
    paths += [Path(p) for p in config["reads"]]
    tool_paths = {name: shutil.which(name) for name in NATIVE_COMMANDS}
    paths += [Path(path).resolve() for path in tool_paths.values() if path]
    # Bind actual pinned code, not just the revision claimed by SOURCE.json.
    paths += sorted(p for p in engine.parent.parent.rglob("*")
                    if p.is_file() and (p.suffix == ".py" or p.name == "SOURCE.json"))
    identities = {}
    hashes = []
    for path in paths:
        before = stat_key(path)
        hashes.append([str(path), digest(path)])
        if stat_key(path) != before:
            raise ValueError(f"input changed during hashing: {path}")
        identities[path] = before
    signature = hashlib.sha256(json.dumps([PURPOSE, config, hashes, tool_paths, sys.version, sys.executable], sort_keys=True).encode()).hexdigest()
    return signature, identities


class IndexedFasta:
    """Bounded-memory sequence access; index lives in the private attempt folder."""
    def __init__(self, source: Path, link: Path):
        self.identity = stat_key(source)
        link.symlink_to(source.resolve())
        subprocess.run(["samtools", "faidx", str(link)], check=True)
        self.records = {}
        for line in Path(str(link) + ".fai").read_text().splitlines():
            name, length, offset, bases, width, *_ = line.split("\t")
            row = tuple(map(int, (length, offset, bases, width)))
            if name in self.records or row[0] <= 0 or row[2] <= 0 or row[3] < row[2]:
                raise ValueError("invalid FASTA index")
            self.records[name] = row
        if not self.records:
            raise ValueError("empty FASTA")
        self.path = source
        if stat_key(source) != self.identity:
            raise ValueError("FASTA changed during indexing")

    def fetch(self, name: str, start: int, end: int) -> bytes:
        if stat_key(self.path) != self.identity:
            raise ValueError("FASTA changed after indexing")
        length, offset, bases, width = self.records[name]
        if not 0 <= start <= end <= length or end - start > CHUNK:
            raise ValueError("invalid or unbounded FASTA slice")
        if start == end:
            return b""
        first = offset + start // bases * width + start % bases
        last = offset + (end - 1) // bases * width + (end - 1) % bases + 1
        with self.path.open("rb") as stream:
            stream.seek(first)
            block = stream.read(last - first).replace(b"\n", b"").replace(b"\r", b"")
        if len(block) != end - start or re.search(br"[^ACGTRYSWKMBDHVNacgtryswkmbdhvn]", block):
            raise ValueError("FASTA/index mismatch or non-IUPAC sequence")
        return block

    def blocks(self, name: str, start: int, end: int):
        for offset in range(start, end, CHUNK):
            yield self.fetch(name, offset, min(end, offset + CHUNK))

    def gaps(self):
        for name, (length, *_) in self.records.items():
            pending = None
            for offset in range(0, length, CHUNK):
                block = self.fetch(name, offset, min(length, offset + CHUNK))
                for match in re.finditer(br"[Nn]+", block):
                    start, end = offset + match.start(), offset + match.end()
                    if pending and pending[1] == start:
                        pending = (pending[0], end)
                    else:
                        if pending:
                            yield name, *pending
                        pending = (start, end)
                if pending and pending[1] < offset + len(block):
                    yield name, *pending
                    pending = None
            if pending:
                yield name, *pending


def same_region(left: IndexedFasta, lname: str, lstart: int,
                right: IndexedFasta, rname: str, rstart: int, length: int) -> bool:
    for offset in range(0, length, CHUNK):
        size = min(CHUNK, length - offset)
        a = left.fetch(lname, lstart + offset, lstart + offset + size).upper()
        b = right.fetch(rname, rstart + offset, rstart + offset + size).upper()
        if a != b or b"N" in a:
            return False
    return True


def admit(genome: IndexedFasta, gap: tuple, row: dict, attempt: Path, index: int):
    """Return a bridge slice, or a stable reason; all coordinates are half-open."""
    name, start, end = gap
    length = genome.records[name][0]
    if start == 0 or end == length:
        return None, "terminal_gap_not_supported"
    if row.get("filled") is not True:
        return None, "native_unfilled"
    required = ("gap_start", "gap_end", "gap_len", "left_flank_len", "right_flank_len",
                "replace_start", "replace_end", "replace_len")
    if any(type(row.get(key)) is not int for key in required):
        return None, "invalid_coordinates"
    left, right = row["left_flank_len"], row["right_flank_len"]
    if (row["chromosome"] != name or row["gap_start"] != start or row["gap_end"] != end - 1
            or row["gap_len"] != end - start or left <= 0 or right <= 0
            or row["replace_start"] != start - left or row["replace_end"] != end + right - 1
            or row["replace_len"] != left + end - start + right
            or start - left < 0 or end + right > length):
        return None, "invalid_coordinates"
    raw = row.get("final_sequence_file")
    if not isinstance(raw, str) or not raw:
        return None, "missing_candidate"
    candidate_path = Path(raw)
    if not candidate_path.is_absolute():
        candidate_path = attempt / candidate_path
    candidate_path = candidate_path.resolve()
    if not candidate_path.is_relative_to(attempt.resolve()) or not candidate_path.is_file():
        return None, "candidate_outside_attempt_or_missing"
    try:
        candidate = IndexedFasta(candidate_path, attempt / f"candidate-{index}.fa")
        if len(candidate.records) != 1:
            return None, "ambiguous_candidate_records"
        cname, (clength, *_) = next(iter(candidate.records.items()))
        if clength <= left + right:
            return None, "no_positive_bridge"
        if (not same_region(genome, name, start - left, candidate, cname, 0, left)
                or not same_region(genome, name, end, candidate, cname, clength - right, right)):
            return None, "flanks_changed_or_ambiguous"
        bridge_hash = hashlib.sha256()
        for block in candidate.blocks(cname, left, clength - right):
            if re.search(br"[^ACGTacgt]", block):
                return None, "ambiguous_bridge"
            bridge_hash.update(block.upper())
        return (candidate, cname, left, clength - right, bridge_hash.hexdigest()), "accepted"
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None, "invalid_candidate_fasta"


def validate_result(root: Path, signature: str | None = None) -> tuple[bool, str]:
    try:
        checkpoint = load_json(root / CHECKPOINT)
        if checkpoint.get("schema_version") != 1 or (signature is not None and checkpoint.get("signature") != signature):
            return False, "DEGAP inputs changed"
        artifacts = checkpoint.get("artifacts")
        if not isinstance(artifacts, dict) or artifacts.keys() != {OUTPUT, REPORT}:
            return False, "incomplete DEGAP receipt"
        for relative, expected in artifacts.items():
            if digest(root / relative) != expected:
                return False, f"DEGAP artifact changed: {relative}"
        report = load_json(root / REPORT)
        if report.get("input_signature") != checkpoint["signature"]:
            return False, "DEGAP report binding differs"
        return True, "validated post-LGZ DEGAP output"
    except (OSError, ValueError, KeyError, TypeError):
        return False, "missing or invalid DEGAP output"


def run(root: Path, threads: int) -> dict:
    root = root.resolve()
    check_native_paths(root)
    engine = Path(__file__).resolve().parent / "degap_core/bin/AutoGapfiller.py"
    if not engine.is_file():
        raise ValueError("bundled AutoGapfiller is missing")
    signature, identities = input_binding(root, engine)
    valid, _ = validate_result(root, signature)
    if valid:
        print("DEGAP gapfill cache hit: validated inputs and outputs", flush=True)
        return load_json(root / REPORT)
    attempt = root / "degap/attempts" / uuid.uuid4().hex
    attempt.mkdir(parents=True)
    if (root / CHECKPOINT).is_file():
        shutil.copy2(root / CHECKPOINT, attempt / "previous-checkpoint.json")
    # Retain old artifacts for diagnosis, but do not report/deliver them as this attempt.
    atomic_json(root / CHECKPOINT, {"schema_version": 1, "signature": signature, "status": "running"})
    genome = IndexedFasta(root / "grt/q/q3.fa", attempt / "input.fa")
    gaps = list(genome.gaps())
    config = load_json(root / "metadata/degap_inputs.json")
    rows = []
    # No-gap tasks do not preprocess reads or launch the native engine.
    if any(start > 0 and end < genome.records[name][0] and end - start >= 20
           for name, start, end in gaps):
        command = [sys.executable, str(engine), "--genome", str(root / "grt/q/q3.fa"),
                   "--output", str(attempt / "native"), "--work", "1", "--thread", str(threads),
                   "--" + config["reads_type"], *config["reads"]]
        atomic_json(attempt / "invocation.json", {"input_signature": signature, "command": command})
        # Failed attempts are retained for diagnosis, never adopted or overwritten.
        subprocess.run(command, check=True)
        result = load_json(attempt / "native/03.gap_filling/gap_filling_results.json")
        rows = result.get("gaps")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("invalid native gap results")
    known = set(gaps)
    by_gap = {}
    merged_gaps = set()
    for row in rows:
        if (not isinstance(row.get("chromosome"), str)
                or type(row.get("gap_start")) is not int or type(row.get("gap_end")) is not int):
            raise ValueError("invalid native gap identity")
        key = row["chromosome"], row["gap_start"], row["gap_end"] + 1
        if key not in known:
            covered = [gap for gap in gaps if gap[0] == key[0] and key[1] <= gap[1] < gap[2] <= key[2]]
            if len(covered) < 2 or covered[0][1] != key[1] or covered[-1][2] != key[2]:
                raise ValueError("native result does not identify original N runs")
            # Native AutoGapfiller merges nearby gaps. Do not erase the intervening LGZ sequence.
            merged_gaps.update(covered)
            continue
        by_gap.setdefault(key, []).append(row)
    decisions, accepted = [], {}
    for index, gap in enumerate(gaps):
        proposals = by_gap.get(gap, [])
        bridge = None
        if gap[1] == 0 or gap[2] == genome.records[gap[0]][0]:
            reason = "terminal_gap_not_supported"
        elif gap in merged_gaps:
            reason = "native_merged_gaps_not_admitted"
        elif gap[2] - gap[1] < 20:
            reason = "below_native_minimum_20bp"
        elif len(proposals) != 1:
            reason = "missing_candidate" if not proposals else "duplicate_candidates"
        else:
            bridge, reason = admit(genome, gap, proposals[0], attempt, index)
        decision = {"chromosome": gap[0], "start": gap[1], "end": gap[2], "reason": reason}
        if bridge:
            accepted[gap] = bridge
            decision.update(bridge_bp=bridge[3] - bridge[2], bridge_sha256=bridge[4])
        decisions.append(decision)
    temporary = attempt / "post_lgz.fa"
    with temporary.open("wb") as stream:
        for name, (length, *_) in genome.records.items():
            stream.write(b">" + name.encode() + b"\n")
            cursor = 0
            # An unwrapped sequence is intentional: writes stay bounded, even for wheat chromosomes.
            for gap in gaps:
                if gap[0] != name or gap not in accepted:
                    continue
                for block in genome.blocks(name, cursor, gap[1]):
                    stream.write(block)
                candidate, cname, start, end, _ = accepted[gap]
                for block in candidate.blocks(cname, start, end):
                    stream.write(block.upper())
                cursor = gap[2]
            for block in genome.blocks(name, cursor, length):
                stream.write(block)
            stream.write(b"\n")
    if any(stat_key(path) != expected for path, expected in identities.items()):
        raise ValueError("inputs changed while DEGAP was running; result not published")
    report = {"schema_version": 1, "purpose": PURPOSE, "input_signature": signature,
              "coordinates": "0-based half-open in original LGZ q3", "lgz_unchanged": True,
              "reads_type": config["reads_type"], "gap_count": len(gaps),
              "accepted_count": len(accepted), "unfilled_count": len(gaps) - len(accepted),
              "output_fasta": OUTPUT, "output_sha256": digest(temporary), "decisions": decisions,
              "acceptance": "exact non-N flanks and positive ACGT bridge; not independent biological validation"}
    (root / OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    os.replace(temporary, root / OUTPUT)
    atomic_json(root / REPORT, report)
    # Commit marker last. An interrupted publish is not a reusable stage result.
    atomic_json(root / CHECKPOINT, {"schema_version": 1, "signature": signature,
                "artifacts": {OUTPUT: report["output_sha256"], REPORT: digest(root / REPORT)}})
    print(f"DEGAP gapfill: accepted={len(accepted)} unfilled={len(gaps) - len(accepted)}; LGZ unchanged", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument("--check-environment", action="store_true")
    parser.add_argument("--reads", nargs="+", default=[])
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    try:
        if args.check_environment:
            check_environment(args.server_dir, args.reads)
        else:
            run(args.server_dir, execution_threads(args.threads))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"ERROR: post-LGZ DEGAP failed: {error}\n")


if __name__ == "__main__":
    main()
