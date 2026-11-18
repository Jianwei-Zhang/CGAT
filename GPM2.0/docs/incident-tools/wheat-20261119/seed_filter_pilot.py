"""Bounded, isolated seed-filter pilot; never changes the analysis workspace.

Uses three disjoint 5 Mb windows from the longest query in each of 1A and 3D.
All scientific computation and full source verification must run in a scheduler
job. Fragment results are NOT a full-chromosome accuracy or speedup guarantee.
"""
import collections
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.home() / "cgat-reads-debug/jm19-compare-614589f-20261118"
HERE = ROOT / "seed-filter-pilot-20261119"
WORK = ROOT / "gpm_server"
WINDOW = 5_000_000
TIMEOUT = 300


def union(intervals):
    result = []
    for lo, hi in sorted(intervals):
        if result and lo <= result[-1][1]:
            result[-1] = (result[-1][0], max(hi, result[-1][1]))
        else:
            result.append((lo, hi))
    return result


def covered(groups):
    return sum(hi - lo for rows in groups.values() for lo, hi in union(rows))


def measure(path):
    all_hits = collections.defaultdict(list)
    primary = collections.defaultdict(list)
    placements = collections.defaultdict(list)
    count = 0
    for line in path.read_text().splitlines():
        f = line.split("\t")
        interval = (int(f[2]), int(f[3]))
        all_hits[f[0]].append(interval)
        if "tp:A:P" in f[12:]:
            primary[f[0]].append(interval)
            placements[(f[0], f[5], f[4])].append(interval)
        count += 1
    return {"paf_rows": count, "query_covered_bases": covered(all_hits),
            "primary_query_covered_bases": covered(primary)}, placements


def shared_primary_support(left, right):
    # A coarse destination/strand check, NOT nucleotide-level equivalence.
    shared = collections.defaultdict(list)
    for key in left.keys() & right.keys():
        for a, b in union(left[key]):
            for c, d in union(right[key]):
                if max(a, c) < min(b, d):
                    shared[key[0]].append((max(a, c), min(b, d)))
    return covered(shared)


def run(command, directory):
    directory.mkdir()
    (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    start = time.monotonic()
    with (directory / "stdout.log").open("wb") as out, (directory / "stderr.log").open("wb") as err:
        try:
            proc = subprocess.run(command, stdout=out, stderr=err, timeout=TIMEOUT)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = 124
    stderr = (directory / "stderr.log").read_text(errors="replace")
    rss = re.findall(r"Peak RSS: ([0-9.]+) GB", stderr)
    occ = re.findall(r"mid_occ = (\d+)", stderr)
    return {"returncode": code, "wall_seconds": time.monotonic() - start,
            "peak_rss_gb_reported": float(rss[-1]) if rss else None,
            "mid_occ": int(occ[-1]) if occ else None}


def extract_longest(source, expected_size, expected_hash, destination):
    # Full stable byte read; never generate an index beside the source FASTA.
    before = source.stat()
    digest = hashlib.sha256()
    name = None
    sequence = bytearray()
    longest = (None, b"")
    with source.open("rb") as handle:
        for line in handle:
            digest.update(line)
            if line.startswith(b">"):
                if len(sequence) > len(longest[1]):
                    longest = (name, bytes(sequence))
                name = line[1:].split()[0].decode()
                sequence = bytearray()
            else:
                sequence.extend(line.strip())
    if len(sequence) > len(longest[1]):
        longest = (name, bytes(sequence))
    after = source.stat()
    def signature(st):
        return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns
    assert signature(before) == signature(after)
    assert before.st_size == expected_size and digest.hexdigest() == expected_hash
    name, sequence = longest
    assert len(sequence) >= 3 * WINDOW
    starts = [0, (len(sequence) - WINDOW) // 2, len(sequence) - WINDOW]
    rows = []
    with destination.open("wb") as handle:
        for index, start in enumerate(starts):
            sample = f"window_{index}"
            handle.write((">" + sample + "\n").encode())
            window = sequence[start:start + WINDOW]
            for offset in range(0, len(window), 80):
                handle.write(window[offset:offset + 80] + b"\n")
            rows.append({"sample": sample, "source_name": name,
                         "source_length": len(sequence), "start": start,
                         "end": start + WINDOW})
    return rows


def main():
    assert HERE.is_dir()
    sys.path.insert(0, str(WORK / ".prepare_lib/tools"))
    from run_orchestration import file_identity, sha256_file, validate_paf
    assignment = json.loads((WORK / ".run_all/checkpoints/assign.80a737d469c64759.json").read_text())
    expected = {row["path"]: row for row in assignment["outputs"]}
    tool = Path(shutil.which("minimap2")).resolve()
    proof = json.loads((ROOT / "memory-resume-20261118/reference.before.json").read_text())
    original = next(t for t in proof["input_payload"]["tools"] if t["command"] == "minimap2")
    assert sha256_file(tool) == original["sha256"]
    report = {"scope": "isolated fragment pilot, not full-chromosome validation",
              "tool_sha256": original["sha256"], "window_bases": WINDOW,
              "alignment_timeout_seconds": TIMEOUT, "main_workspace_modified": False,
              "results": []}
    for chromosome in ("3D", "1A"):
        target = WORK / f"runs/chr_{chromosome}/datasets/JM19_flye_ABD.fa"
        query = WORK / f"runs/chr_{chromosome}/datasets/JM19_hifiasm.fa"
        assert file_identity(target, relative_to=WORK) == expected[str(target.relative_to(WORK))]
        directory = HERE / chromosome
        directory.mkdir()
        query_row = expected[str(query.relative_to(WORK))]
        query_file = directory / "windows.fa"
        windows = extract_longest(query, query_row["size"], query_row["sha256"], query_file)
        (directory / "inputs.json").write_text(json.dumps({"target": expected[str(target.relative_to(WORK))],
            "query": query_row, "windows": windows, "windows_sha256": sha256_file(query_file)}, indent=2) + "\n")
        index = directory / "target.mmi"
        built = run([str(tool), "-x", "asm10", "-t", "3", "-d", str(index), str(target)], directory / "index-build")
        assert built["returncode"] == 0, built
        baseline = None
        baseline_hash = None
        for label, args in (("baseline", []), ("f0001", ["-f", "0.001"]), ("f0005", ["-f", "0.005"])):
            outdir = directory / label
            paf = outdir / "result.paf"
            result = run([str(tool), "-c", "-x", "asm10", "-t", "3", *args,
                          "-o", str(paf), str(index), str(query_file)], outdir)
            result.update(chromosome=chromosome, variant=label)
            if result["returncode"] == 0:
                validate_paf(paf, require_cigar=True)
                metrics, placements = measure(paf)
                result.update(metrics)
                result["paf_sha256"] = sha256_file(paf)
                if label == "baseline":
                    baseline, baseline_hash = placements, result["paf_sha256"]
                elif baseline is not None:
                    result["same_primary_target_strand_supported_bases"] = shared_primary_support(baseline, placements)
                    result["paf_byte_identical_to_baseline"] = result["paf_sha256"] == baseline_hash
            report["results"].append(result)
            (HERE / "results.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(result), flush=True)
    print("PILOT_DONE_NO_PRODUCTION_PARAMETERS_CHANGED", flush=True)


if __name__ == "__main__":
    main()
