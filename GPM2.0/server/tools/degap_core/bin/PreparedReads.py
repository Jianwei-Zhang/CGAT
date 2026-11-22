"""Bind normalized FASTA to the original ordered, content-verified inputs."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from ExtensionFamilies import atomic_json, read_json
from FamilyTools import content_hash


def sources(paths):
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    resolved = [Path(path).resolve() for path in paths or ()]
    return [{"path": str(path), "sha256": content_hash(path)} for path in resolved]


def contract(hifi, ont):
    converter = shutil.which("seqkit")
    if converter is None:
        raise FileNotFoundError("seqkit is required to prepare and verify reads")
    converter = Path(converter).resolve()
    return {"schema": "prepared-reads-v1",
            "converter": {"path": str(converter), "sha256": content_hash(converter)},
            "sources": {"hifi": sources(hifi), "ont": sources(ont)}}


def prepare(directory, expected):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    receipt = directory / "manifest.json"
    outputs = {kind: directory / f"{kind}_reads.fa"
               for kind, entries in expected["sources"].items() if entries}
    def completed():
        if not receipt.is_file():
            return False
        saved = read_json(receipt)
        if saved.get("contract") != expected:
            raise ValueError(f"Original read inputs or converter changed; use a new output directory: {receipt}")
        artifacts = saved["artifacts"]
        if artifacts is None:
            return False
        if set(artifacts) != set(outputs) or any(
                not path.is_file() or artifacts[kind] != content_hash(path)
                for kind, path in outputs.items()):
            raise ValueError(f"Prepared reads changed; use a new output directory: {directory}")
        return True

    # Completed FASTA is immutable. Avoid serializing the full-file checks
    # when AutoGapfiller workers share this directory through a symlink.
    if completed():
        return outputs
    with (directory / ".prepare.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if completed():
            return outputs
        if not receipt.exists():
            if any(os.path.lexists(directory / f"{kind}_reads.fa") for kind in ("hifi", "ont")):
                raise ValueError(f"Prepared reads lack an input manifest; use a new output directory: {directory}")
            # Record the input contract before conversion. A same-input restart can
            # regenerate uncommitted outputs, but may not adopt unrelated FASTA.
            atomic_json(receipt, {"contract": expected, "artifacts": None})
        artifacts = {}
        for kind, path in outputs.items():
            entries = expected["sources"][kind]
            with tempfile.TemporaryDirectory(prefix=".prepare-", dir=directory) as work:
                pending = Path(work) / path.name
                subprocess.run([expected["converter"]["path"], "fq2fa", "-o", str(pending),
                                *(entry["path"] for entry in entries)], check=True)
                if not pending.is_file() or not pending.stat().st_size:
                    raise ValueError(f"No {kind} reads were produced during FASTA preparation")
                if any(content_hash(e["path"]) != e["sha256"] for e in entries):
                    raise ValueError(f"Original {kind} reads changed during FASTA preparation")
                artifacts[kind] = content_hash(pending)
                os.replace(pending, path)
        atomic_json(receipt, {"contract": expected, "artifacts": artifacts})
    return outputs
