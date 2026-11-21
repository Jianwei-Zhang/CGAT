"""Isolated three-window feasibility pilot; never writes or resumes the main job.

Uses the current supplemental target and exact selected segment content identity.
The explicit timeout/AS limit applies ONLY to this disposable pilot mapper.
A successful pilot is not final q0 scientific acceptance or a reusable main task.
"""
from pathlib import Path
import argparse
import dataclasses
import hashlib
import importlib.util
import json
import os
import resource
import signal
import subprocess
import sys
import time


def sha(path):
    path = Path(path); before = signature(path); h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    if before != signature(path): raise ValueError("input changed while hashing")
    return h.hexdigest()


def signature(path):
    s = Path(path).stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def emit(event, **values):
    print(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, **values}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--server-dir", type=Path, required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--segment", required=True)
    p.add_argument("--window-helper", type=Path, required=True)
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--mapper-seconds", type=int, default=900)
    a = p.parse_args()
    work = a.server_dir.resolve(strict=True); out = Path.cwd().resolve()
    if out == work or work in out.parents or a.threads < 1 or a.mapper_seconds < 1:
        raise ValueError("pilot needs an isolated output directory and positive budgets")
    if Path(a.task).name != a.task: raise ValueError("invalid task name")
    task = work / "grt/evidence/q0_prepare/tasks" / a.task
    command_path = task / "command.json"; command_sha = sha(command_path)
    command = json.loads(command_path.read_text()); source_spec = command["spec"]
    mapper = Path(source_spec["tool"]["resolved"])
    if sha(mapper) != source_spec["tool"]["sha256"]: raise ValueError("mapper identity changed")
    if source_spec["alignment_flags"] != ["-D", "-P", "--dual=yes", "--no-long-join"]:
        raise ValueError("pilot does not silently substitute mapper flags")
    if a.segment not in source_spec["query_ids"]: raise ValueError("undeclared selected query")
    expected_segment_sha = dict(source_spec["members"])[a.segment]
    sys.path.insert(0, str(work / ".prepare_lib/tools"))
    from lgz_core.common import write_fasta
    from lgz_core.q0_sources import Interval
    name = "lgz_core.q0_query_windows"
    module_spec = importlib.util.spec_from_file_location(name, a.window_helper.resolve(strict=True))
    helper = importlib.util.module_from_spec(module_spec); sys.modules[name] = helper
    module_spec.loader.exec_module(helper)
    helper_sha = sha(a.window_helper)
    query, target = task / "query.fa", task / "target.fa"
    query_before, target_before = signature(query), signature(target)
    emit("indexing_private_symlinks", main_modified=False)
    for source, stem in [(query, "source-query.fa"), (target, "source-target.fa")]:
        alias = out / stem
        alias.symlink_to(source)
        subprocess.run(["samtools", "faidx", str(alias)], check=True)
    def lengths(path):
        with path.open() as f: return {r[0]: int(r[1]) for r in (line.split("\t") for line in f)}
    qlength = lengths(out / "source-query.fa.fai")[a.segment]
    target_lengths = lengths(out / "source-target.fa.fai")
    if sorted(target_lengths) != source_spec["target_ids"]: raise ValueError("target inventory differs")
    policy = helper.WindowPolicy()
    planned = helper.plan_query_windows({a.segment: qlength}, {a.segment: [Interval(0, qlength)]}, policy=policy)
    if not planned: raise ValueError("selected query does not trigger the candidate policy")
    windows = [planned[i] for i in sorted({0, len(planned)//2, len(planned)-1})]
    chunks = {w.window_id: [] for w in windows}
    digest = hashlib.sha256(); offset = 0
    emit("extracting_and_verifying_selected_segment", length=qlength, windows=len(windows))
    with subprocess.Popen(["samtools", "faidx", "-n", "1000000", str(out / "source-query.fa"), a.segment],
                          stdout=subprocess.PIPE) as child:
        header = child.stdout.readline().rstrip(b"\r\n")
        if header != (">" + a.segment).encode(): raise ValueError("unexpected faidx header")
        for raw in child.stdout:
            bases = raw.rstrip(b"\r\n"); digest.update(bases)
            for w in windows:
                low, high = max(offset, w.start), min(offset + len(bases), w.end)
                if low < high: chunks[w.window_id].append(bases[low-offset:high-offset])
            offset += len(bases)
        if child.wait() != 0: raise ValueError("faidx extraction failed")
    if offset != qlength or digest.hexdigest() != expected_segment_sha:
        raise ValueError("selected source content differs from the live mapping specification")
    rows = []
    for w in windows:
        sequence = b"".join(chunks[w.window_id]).decode("ascii")
        if len(sequence) != w.length: raise ValueError("incomplete pilot window")
        rows.append((w.window_id, sequence))
    write_fasta(out / "windows.fa", rows)
    target_sha = sha(target)
    metadata = {"schema": "wheat_partial_window_pilot_v1", "policy": dataclasses.asdict(policy),
        "original_task": a.task, "original_command_sha256": command_sha,
        "selected_segment_sha256": expected_segment_sha, "selected_segment_length": qlength,
        "target_sha256": target_sha, "target_fasta_bytes": target.stat().st_size,
        "windows": [w.record() for w in windows], "window_helper_sha256": helper_sha,
        "query_sha256": sha(out / "windows.fa"), "scientific_acceptance": False,
        "reusable_main_task": False, "main_workspace_modified": False}
    (out / "plan.json").write_text(json.dumps(metadata, indent=2) + "\n")
    raw_path = out / "raw.paf"
    argv = [str(mapper), "-c", "-x", source_spec["preset"], *source_spec["alignment_flags"],
            "-t", str(a.threads), "-o", str(raw_path), str(target), str(out / "windows.fa")]
    def limit(): resource.setrlimit(resource.RLIMIT_AS, (64*1024**3, 64*1024**3))
    before_usage = resource.getrusage(resource.RUSAGE_CHILDREN); started = time.monotonic()
    emit("mapper_start", argv=argv, address_space_gib=64, diagnostic_timeout_seconds=a.mapper_seconds)
    with (out / "mapper.stdout").open("w") as stdout, (out / "mapper.stderr").open("w") as stderr:
        process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, preexec_fn=limit, start_new_session=True)
        (out / "mapper.pid").write_text(str(process.pid) + "\n")
        try:
            code = process.wait(timeout=a.mapper_seconds)
        except subprocess.TimeoutExpired:
            # Only our newly created process group, never any main-workflow PID.
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait()
            (out / "pilot-timeout.json").write_text(json.dumps({"pid": process.pid,
                "seconds": a.mapper_seconds, "main_action": "none", "partial_result_accepted": False}) + "\n")
            raise RuntimeError("isolated pilot timed out; no main job action or result adoption")
    elapsed = time.monotonic()-started; usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    if code: raise RuntimeError(f"pilot mapper failed: {code}")
    if (query_before != signature(query) or target_before != signature(target)
            or command_sha != sha(command_path) or helper_sha != sha(a.window_helper)
            or sha(mapper) != source_spec["tool"]["sha256"] or target_sha != sha(target)):
        raise ValueError("pilot input or tool changed; no result acceptance")
    by_id = {w.window_id: w for w in windows}; raw_rows=0; kept=0
    with raw_path.open() as src, (out / "projected.paf").open("w") as dest:
        for number, line in enumerate(src, 1):
            raw_rows += 1
            projected = helper.project_window_paf(line, by_id, target_lengths, artifact="raw.paf", line_number=number)
            if projected is not None:
                dest.write(projected + "\n"); kept += 1
    report = {**metadata, "status": "pilot_execution_completed_not_scientific_acceptance",
        "mapper_seconds": elapsed, "mapper_cpu_seconds": (usage.ru_utime + usage.ru_stime
            - before_usage.ru_utime - before_usage.ru_stime),
        "all_child_peak_rss_kib": usage.ru_maxrss, "raw_rows": raw_rows, "projected_rows": kept,
        "raw_sha256": sha(raw_path), "projected_sha256": sha(out / "projected.paf")}
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    emit("completed", mapper_seconds=elapsed, raw_rows=raw_rows, projected_rows=kept,
         child_peak_rss_kib=usage.ru_maxrss, scientific_acceptance=False)


if __name__ == "__main__": main()
