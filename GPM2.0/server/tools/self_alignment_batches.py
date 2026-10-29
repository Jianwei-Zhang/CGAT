#!/usr/bin/env python3
"""Run one whole-record self-alignment batch and publish a resumable merge."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
try:
    from minimap2_diagnostics import cigar_assertion_hint, log_tail
except ModuleNotFoundError:  # Imported through server.tools.
    from .minimap2_diagnostics import cigar_assertion_hint, log_tail
import sys
import tempfile
from pathlib import Path


INDEX_LIMIT_BASES = 8_000_000_000
OUTPUTS = ("raw.paf", "result.paf", "stderr.log")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


@contextlib.contextmanager
def exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def valid_outputs(directory: Path, key: str, names: tuple[str, ...]) -> bool:
    try:
        record = json.loads((directory / "complete.json").read_text(encoding="utf-8"))
        return (
            record["key"] == key
            and set(record["outputs"]) == set(names)
            and all(sha256(directory / name) == record["outputs"][name] for name in names)
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def publish(directory: Path, key: str, names: tuple[str, ...]) -> None:
    atomic_json(
        directory / "complete.json",
        {"key": key, "outputs": {name: sha256(directory / name) for name in names}},
    )


def fasta_lengths(path: Path) -> dict[str, int]:
    lengths: dict[str, int] = {}
    current = None
    with path.open("rb") as handle:
        for line in handle:
            if line.startswith(b">"):
                current = line[1:].split()[0].decode("utf-8")
                if not current or current in lengths:
                    raise ValueError(f"duplicate or empty FASTA name: {path}")
                lengths[current] = 0
            elif current is None:
                if line.strip():
                    raise ValueError(f"sequence before FASTA header: {path}")
            else:
                lengths[current] += len(line.strip())
    if not lengths or any(length < 1 for length in lengths.values()):
        raise ValueError(f"empty FASTA input: {path}")
    return lengths


def validate_raw(path: Path, queries: dict[str, int], targets: dict[str, int]) -> None:
    ranks = {name: rank for rank, name in enumerate(queries)}
    previous = -1
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 12 or fields[0] not in queries or fields[5] not in targets:
                raise ValueError(f"unexpected or incomplete PAF row: {path}")
            rank = ranks[fields[0]]
            if rank < previous:
                raise ValueError(f"query order changed in PAF: {path}")
            previous = rank
            query_length = int(fields[1])
            target_length = int(fields[6])
            if query_length != queries[fields[0]] or target_length != targets[fields[5]]:
                raise ValueError(f"PAF sequence length changed: {path}")
            if not 0 <= int(fields[2]) <= int(fields[3]) <= query_length:
                raise ValueError(f"invalid PAF query coordinates: {path}")
            if not 0 <= int(fields[7]) <= int(fields[8]) <= target_length:
                raise ValueError(f"invalid PAF target coordinates: {path}")
            if fields[4] not in {"+", "-"} or not any(
                tag.startswith("cg:Z:") for tag in fields[12:]
            ):
                raise ValueError(f"PAF row is missing strand or CIGAR: {path}")


def require_identity(manifest: dict, key: str, path: Path) -> None:
    expected = manifest["identities"][key]
    if sha256(path) != expected:
        raise ValueError(f"self-alignment input changed: {path}")


def ensure_index(manifest: dict, tool: Path, target: Path, cache: Path, threads: int) -> Path:
    index = cache / "target.mmi"
    cache.mkdir(parents=True, exist_ok=True)
    key = identity(
        {
            "tool": manifest["identities"]["tool"],
            "target": manifest["identities"]["target"],
            "preset": manifest["preset"],
            "index_limit": "8G",
        }
    )
    with exclusive_lock(cache / "index.lock"):
        if valid_outputs(cache, key, ("target.mmi", "index.stderr.log")):
            return index
        require_identity(manifest, "target", target)
        for stale in (cache / "complete.json",):
            if stale.exists():
                stale.rename(cache / f"invalid-{stale.name}-{os.getpid()}")
        temporary = cache / f"target.mmi.{os.getpid()}.tmp"
        with (cache / "index.stderr.log").open("wb") as stderr:
            subprocess.run(
                [
                    str(tool), "-x", manifest["preset"], "-I", "8G", "-t",
                    str(max(1, min(2, threads))), "-d", str(temporary), str(target),
                ],
                stdout=subprocess.DEVNULL,
                stderr=stderr,
                check=True,
            )
        if (cache / "index.stderr.log").read_text(errors="replace").count(
            "distinct minimizers:"
        ) != 1:
            temporary.unlink(missing_ok=True)
            raise ValueError("multipart or unknown Minimap2 target index is unsupported")
        os.replace(temporary, index)
        publish(cache, key, ("target.mmi", "index.stderr.log"))
    return index


def merge_if_complete(manifest_path: Path, manifest: dict) -> bool:
    output = Path(manifest["output"])
    marker = output.parent / "self_batch_result.json"
    with exclusive_lock(output.parent / ".self_batch_merge.lock"):
        try:
            merged = json.loads(marker.read_text(encoding="utf-8"))
            if (
                merged["manifest_sha256"] == sha256(manifest_path)
                and output.is_file()
                and merged["result_sha256"] == sha256(output)
            ):
                return True
        except (OSError, ValueError, KeyError, TypeError):
            pass
        sources = []
        for batch in manifest["batches"]:
            directory = Path(batch["directory"])
            if not valid_outputs(directory, batch["key"], OUTPUTS):
                return False
            sources.append(directory / "result.paf")
        temporary = output.with_name(output.name + ".tmp")
        with temporary.open("wb") as destination:
            for source in sources:
                with source.open("rb") as handle:
                    shutil.copyfileobj(handle, destination)
        os.replace(temporary, output)
        atomic_json(
            marker,
            {
                "manifest_sha256": sha256(manifest_path),
                "result_sha256": sha256(output),
                "batches": len(sources),
            },
        )
    return True


def run_batch(manifest_path: Path, batch_index: int) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("version") != 1:
        raise ValueError(f"unsupported self-batch manifest: {manifest_path}")
    if not 0 <= batch_index < len(manifest["batches"]):
        raise ValueError(f"invalid batch index: {batch_index}")
    tool = Path(shutil.which("minimap2") or "")
    if not tool.is_file() or sha256(tool) != manifest["identities"]["tool"]:
        raise ValueError("Minimap2 binary changed after preparation")
    target = Path(manifest["target"])
    name_map = Path(manifest["name_map"])
    restore = Path(manifest["restore"])
    require_identity(manifest, "name_map", name_map)
    require_identity(manifest, "restore", restore)
    target_lengths = {str(name): int(length) for name, length in manifest["target_lengths"].items()}
    if not target_lengths or any(length < 1 for length in target_lengths.values()):
        raise ValueError("invalid target lengths in self-batch manifest")
    if sum(target_lengths.values()) >= INDEX_LIMIT_BASES:
        raise ValueError("multipart Minimap2 target index is unsupported")
    threads = int(os.environ.get("GPM_TASK_THREADS", "1"))
    if threads < 1:
        raise ValueError("GPM_TASK_THREADS must be positive")
    cache = Path(manifest["cache"])
    index = ensure_index(manifest, tool, target, cache, threads)

    batch = manifest["batches"][batch_index]
    directory = Path(batch["directory"])
    query = Path(batch["query"])
    directory.mkdir(parents=True, exist_ok=True)
    if sha256(query) != batch["query_sha256"]:
        raise ValueError(f"self-alignment query batch changed: {query}")
    query_lengths = fasta_lengths(query)
    if list(query_lengths) != [entry["name"] for entry in batch["entries"]]:
        raise ValueError(f"self-alignment query batch order changed: {query}")
    with exclusive_lock(directory / "batch.lock"):
        if valid_outputs(directory, batch["key"], OUTPUTS):
            print(f"SELF_BATCH_CACHE_HIT {batch_index + 1}/{len(manifest['batches'])}", flush=True)
            merge_if_complete(manifest_path, manifest)
            return
        complete = directory / "complete.json"
        if complete.exists():
            complete.rename(directory / f"invalid-complete-{os.getpid()}.json")
        output = Path(manifest["output"])
        with exclusive_lock(output.parent / ".self_batch_merge.lock"):
            (output.parent / "self_batch_result.json").unlink(missing_ok=True)
        attempt = Path(tempfile.mkdtemp(prefix="attempt-", dir=directory))
        command = [
            str(tool), "-c", "-x", manifest["preset"], "-X", "--no-hash-name",
            "-m", str(manifest["min_chain_score"]),
            "-n", str(manifest["minimizers"]),
            "-t", str(min(threads, len(query_lengths))), str(index), str(query),
        ]
        atomic_json(attempt / "command.json", command)
        try:
            with (attempt / "raw.paf").open("wb") as raw, (attempt / "stderr.log").open("wb") as stderr:
                subprocess.run(command, stdout=raw, stderr=stderr, check=True)
        except subprocess.CalledProcessError:
            hint = cigar_assertion_hint(log_tail(attempt / "stderr.log"))
            if hint:
                print(f"{hint} Evidence: {attempt}", file=sys.stderr)
            raise
        validate_raw(attempt / "raw.paf", query_lengths, target_lengths)
        with (attempt / "raw.paf").open("rb") as raw, (attempt / "result.paf").open("wb") as result:
            subprocess.run(
                [sys.executable, str(restore), str(name_map)],
                stdin=raw,
                stdout=result,
                check=True,
            )
        for name in OUTPUTS:
            os.replace(attempt / name, directory / name)
        publish(directory, batch["key"], OUTPUTS)
        print(
            f"SELF_BATCH_COMMITTED {batch_index + 1}/{len(manifest['batches'])} "
            f"threads={min(threads, len(query_lengths))}",
            flush=True,
        )
    merge_if_complete(manifest_path, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--batch-index", required=True, type=int)
    args = parser.parse_args()
    run_batch(args.manifest.resolve(), args.batch_index)


if __name__ == "__main__":
    main()
