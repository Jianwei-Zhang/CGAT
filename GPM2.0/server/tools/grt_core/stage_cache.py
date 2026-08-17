from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .common import *
from .stage_schema import *
from .stage_io import *
from .stage_alignment import *
from .stage_replay import *

def fasta_bytes(records: Iterable[tuple[str, str]]) -> bytes:
    payload = bytearray()
    for name, sequence in records:
        payload.extend(f">{name}\n".encode("utf-8"))
        for start in range(0, len(sequence), 80):
            payload.extend((sequence[start : start + 80] + "\n").encode("utf-8"))
    return bytes(payload)

def checkpoint_result(
    server_dir: Path,
    stage: str,
    fingerprint: str,
) -> dict[str, object] | None:
    checkpoint_path = server_dir / f"grt/checkpoints/{stage}.json"
    if not checkpoint_path.is_file():
        return None
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("workflow") != WORKFLOW or checkpoint.get("stage") != stage:
            return None
        if checkpoint.get("status") != "success" or checkpoint.get("input_fingerprint") != fingerprint:
            return None
        output_hashes = checkpoint.get("output_hashes")
        if not isinstance(output_hashes, dict) or not output_hashes:
            return None
        for relpath, expected_hash in output_hashes.items():
            path = server_dir / relpath
            if not path.is_file() or sha256_file(path) != expected_hash:
                return None
        result_path = server_dir / str(checkpoint["result_relpath"])
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("stage") != stage or result.get("input_fingerprint") != fingerprint:
            return None
        return result
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None

def commit_stage_directory(temporary: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    os.replace(temporary, destination)

def invalidate_step1_from(server_dir: Path, stage: str) -> None:
    order = ["step1_round1", "step1_filter", "step1_round2"]
    q_outputs = {
        "step1_round1": "q0r1",
        "step1_filter": "q0f",
        "step1_round2": "q1",
    }
    artifact_paths = {
        "step1_round1": server_dir / "grt/evidence/step1/round1",
        "step1_filter": server_dir / "grt/evidence/step1/filter",
        "step1_round2": server_dir / "grt/evidence/step1/round2",
    }
    start = order.index(stage)
    for invalid_stage in order[start:]:
        checkpoint = server_dir / f"grt/checkpoints/{invalid_stage}.json"
        checkpoint.unlink(missing_ok=True)
        q_path = server_dir / f"grt/q/{q_outputs[invalid_stage]}.fa"
        q_path.unlink(missing_ok=True)
        artifact = artifact_paths[invalid_stage]
        if artifact.is_dir():
            shutil.rmtree(artifact)
    for downstream_stage, q_output in (
        ("step2", "q2"),
        ("step3", "q3"),
        ("step4_telomere", "q4"),
        ("finalize", ""),
    ):
        (server_dir / f"grt/checkpoints/{downstream_stage}.json").unlink(missing_ok=True)
        if q_output:
            (server_dir / f"grt/q/{q_output}.fa").unlink(missing_ok=True)
    for downstream_artifact in ("step2", "step3", "step4_telomere"):
        path = server_dir / f"grt/evidence/{downstream_artifact}"
        if path.is_dir():
            shutil.rmtree(path)
    (server_dir / "metadata/grt_final_path.json").unlink(missing_ok=True)


def invalidate_step23_from(server_dir: Path, stage: str) -> None:
    order = ["step2", "step3"]
    outputs = {"step2": "q2", "step3": "q3"}
    start = order.index(stage)
    for invalid_stage in order[start:]:
        (server_dir / f"grt/checkpoints/{invalid_stage}.json").unlink(missing_ok=True)
        (server_dir / f"grt/q/{outputs[invalid_stage]}.fa").unlink(missing_ok=True)
        artifact = server_dir / f"grt/evidence/{invalid_stage}"
        if artifact.is_dir():
            shutil.rmtree(artifact)
    invalidate_step4(server_dir)


def invalidate_step4(server_dir: Path) -> None:
    for stage in ("step4_telomere", "finalize"):
        (server_dir / f"grt/checkpoints/{stage}.json").unlink(missing_ok=True)
    (server_dir / "grt/q/q4.fa").unlink(missing_ok=True)
    (server_dir / "metadata/grt_final_path.json").unlink(missing_ok=True)
    artifact = server_dir / "grt/evidence/step4_telomere"
    if artifact.is_dir():
        shutil.rmtree(artifact)

def write_checkpoint(
    server_dir: Path,
    stage: str,
    fingerprint: str,
    fingerprint_payload: dict[str, object],
    result_relpath: str,
    output_relpaths: list[str],
) -> Path:
    checkpoint_path = server_dir / f"grt/checkpoints/{stage}.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": stage,
        "status": "success",
        "input_fingerprint": fingerprint,
        "fingerprint_payload": fingerprint_payload,
        "result_relpath": result_relpath,
        "output_hashes": {
            relpath: sha256_file(server_dir / relpath) for relpath in sorted(output_relpaths)
        },
    }
    temporary = checkpoint_path.with_name(f".{checkpoint_path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    os.replace(temporary, checkpoint_path)
    return checkpoint_path

def run_minimap(
    executable: str,
    threads: int,
    donor_fasta: Path,
    flank_fasta: Path,
    paf_path: Path,
    stage_dir: Path,
) -> None:
    command = [
        executable,
        "-x",
        PRESET,
        "-t",
        str(threads),
        "-c",
        "-o",
        str(paf_path),
        str(donor_fasta),
        str(flank_fasta),
    ]
    (stage_dir / "command.txt").write_text(shlex.join(command) + "\n", encoding="utf-8", newline="")
    with (stage_dir / "stdout.log").open("w", encoding="utf-8", newline="") as stdout_handle, (
        stage_dir / "stderr.log"
    ).open("w", encoding="utf-8", newline="") as stderr_handle:
        completed = subprocess.run(command, stdout=stdout_handle, stderr=stderr_handle, check=False)
    if completed.returncode != 0:
        fail(
            f"minimap2 failed for {stage_dir.name} with exit code {completed.returncode}; "
            f"command={stage_dir / 'command.txt'}, stderr={stage_dir / 'stderr.log'}"
        )
    if not paf_path.is_file():
        fail(f"minimap2 did not create the expected PAF: {paf_path}")

def cached_chromosome_alignment(
    server_dir: Path,
    stage: str,
    chromosome: str,
    q_input_sha256: str,
    q_chromosome_sha256: str,
    q_segment_rows: list[dict[str, object]],
    flank_records: list[tuple[str, str]],
    query_map: dict[str, tuple[dict[str, object], str]],
    donor_set: dict[str, str],
    donor_has_records: bool,
    target_lengths: dict[str, int],
    minimap: dict[str, str],
    parameters: dict[str, object],
    threads: int,
    cache_scope: str = "step1",
) -> tuple[Path, bool, str]:
    flank_payload = fasta_bytes(flank_records)
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": stage,
        "chr": chromosome,
        "q_source_sha256": q_input_sha256,
        "q_chromosome_sha256": q_chromosome_sha256,
        "q_segments_sha256": json_hash(q_segment_rows),
        "flank_query_sha256": sha256_bytes(flank_payload),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "tool": minimap,
        "parameters": parameters,
    }
    fingerprint = json_hash(fingerprint_payload)
    chromosome_key = stable_id("chr", chromosome, 16)
    cache_parent = server_dir / f"grt/cache/{cache_scope}/{stage}/{chromosome_key}"
    cache_dir = cache_parent / fingerprint
    checkpoint_path = cache_dir / "cache.json"
    if checkpoint_path.is_file():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            output_hashes = checkpoint.get("output_hashes", {})
            if (
                checkpoint.get("input_fingerprint") == fingerprint
                and checkpoint.get("status") == "success"
                and output_hashes
                and all(
                    (cache_dir / name).is_file()
                    and sha256_file(cache_dir / name) == expected_hash
                    for name, expected_hash in output_hashes.items()
                )
            ):
                try:
                    parse_paf(cache_dir / "result.paf", query_map, target_lengths)
                    return cache_dir, True, chromosome_key
                except SystemExit:
                    pass
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    cache_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{fingerprint}.", dir=cache_parent))
    try:
        flank_path = temporary / "flanks.fa"
        flank_path.write_bytes(flank_payload)
        paf_path = temporary / "result.paf"
        if flank_records and donor_has_records:
            run_minimap(
                str(minimap["resolved"]),
                threads,
                server_dir / donor_set["fasta_relpath"],
                flank_path,
                paf_path,
                temporary,
            )
        else:
            paf_path.write_bytes(b"")
            (temporary / "command.txt").write_text(
                "skipped: chromosome has no valid flank query or frozen D0 is empty\n",
                encoding="utf-8",
                newline="",
            )
            (temporary / "stdout.log").write_text("", encoding="utf-8")
            (temporary / "stderr.log").write_text("", encoding="utf-8")
        parse_paf(paf_path, query_map, target_lengths)
        output_names = ["flanks.fa", "result.paf", "command.txt", "stdout.log", "stderr.log"]
        checkpoint = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "stage": stage,
            "chr": chromosome,
            "status": "success",
            "input_fingerprint": fingerprint,
            "fingerprint_payload": fingerprint_payload,
            "output_hashes": {
                name: sha256_file(temporary / name) for name in output_names
            },
        }
        (temporary / "cache.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        os.replace(temporary, cache_dir)
        return cache_dir, False, chromosome_key
    except BaseException:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"{stage}-{chromosome_key}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise
