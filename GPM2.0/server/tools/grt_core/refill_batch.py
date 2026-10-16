"""Exact same-target refill batching with content-validated minimap2 indexes.

Only a chromosome numerical-cache miss triggers a batch. Original query names,
record order and within-query PAF hit order are retained. No mapping thresholds
change. Index identity includes exact target bytes, preset and executable hash.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time

from .common import fail, sha256_bytes, sha256_file
from .stage_io import json_hash
from .stage_alignment import parse_paf
from .stage_cache import fasta_bytes
from .stage_schema import PRESET


@contextmanager
def cache_lock(path: Path):
    # Server execution is POSIX (Bash); locks are released even on process exit.
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def valid_cache(directory: Path, key: str, names: tuple[str, ...]) -> bool:
    try:
        marker = json.loads((directory / "cache.json").read_text())
        hashes = marker.get("output_hashes", {})
        return (marker.get("status") == "success"
                and marker.get("input_fingerprint") == key
                and all(name in hashes and (directory / name).is_file()
                        and sha256_file(directory / name) == hashes[name] for name in names))
    except (OSError, ValueError, TypeError):
        return False


def publish(directory: Path, destination: Path, payload: dict, names: tuple[str, ...]):
    marker = {"status": "success", "input_fingerprint": json_hash(payload),
              "fingerprint_payload": payload,
              "output_hashes": {name: sha256_file(directory / name) for name in names}}
    (directory / "cache.json").write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n")
    if destination.exists():
        shutil.rmtree(destination)
    os.replace(directory, destination)


class RefillBatchAlignment:
    def __init__(self, server_dir, stage, donor_set, minimap, threads,
                 flank_records, query_map, target_lengths, artifact_dir):
        self.server_dir = Path(server_dir)
        self.stage = stage
        self.donor_set = donor_set
        self.minimap = minimap
        self.threads = threads
        self.flank_records = flank_records
        self.query_map = query_map
        self.target_lengths = target_lengths
        self.artifact_dir = Path(artifact_dir)
        self.rows = None
        self.cache_dir = None
        self.provenance = None

    def _prepare(self):
        query_payload = fasta_bytes(self.flank_records)
        names = [name for name, _sequence in self.flank_records]
        if len(names) != len(set(names)) or set(names) != set(self.query_map):
            fail("refill batch requires unique original query IDs and a complete query map")
        tool = dict(self.minimap)
        executable = Path(tool["resolved"])
        tool["sha256"] = sha256_file(executable)
        payload = {"schema_version": 1, "stage": self.stage, "tool": tool,
                   "target_sha256": self.donor_set["fasta_sha256"],
                   "query_sha256": sha256_bytes(query_payload),
                   "mapping": {"preset": PRESET, "cigar": True, "threads": self.threads}}
        key = json_hash(payload)
        parent = self.server_dir / f"grt/cache/step23/raw_refill_batch/v1/{self.stage}"
        parent.mkdir(parents=True, exist_ok=True)
        destination = parent / key
        outputs = ("flanks.fa", "result.paf", "command.txt", "stdout.log", "stderr.log", "provenance.json")
        with cache_lock(parent / f"{key}.lock"):
            if valid_cache(destination, key, outputs):
                try:
                    parse_paf(destination / "result.paf", self.query_map, self.target_lengths)
                    self.cache_dir = destination
                except SystemExit:
                    pass
            if self.cache_dir is None:
                temporary = Path(tempfile.mkdtemp(prefix=f".{key}.", dir=parent))
                try:
                    (temporary / "flanks.fa").write_bytes(query_payload)
                    target = self.server_dir / self.donor_set["fasta_relpath"]
                    if sha256_file(target) != self.donor_set["fasta_sha256"]:
                        fail("refill target FASTA changed since donor validation")
                    index_payload = {"schema_version": 1,
                                     "target_sha256": payload["target_sha256"], "tool": tool,
                                     "index_options": ["-x", PRESET]}
                    index_key = json_hash(index_payload)
                    index_parent = self.server_dir / "grt/cache/minimap_index/v1"
                    index_parent.mkdir(parents=True, exist_ok=True)
                    index_dir = index_parent / index_key
                    with cache_lock(index_parent / f"{index_key}.lock"):
                        index_hit = valid_cache(index_dir, index_key, ("target.mmi",))
                        index_temporary = None
                        command = [str(executable), "-x", PRESET, "-t", str(self.threads),
                                   "-c", "-o", str(temporary / "result.paf")]
                        if index_hit:
                            mapping_target = index_dir / "target.mmi"
                        else:
                            index_temporary = Path(tempfile.mkdtemp(prefix=f".{index_key}.", dir=index_parent))
                            # Official -d can dump the freshly built index while
                            # mapping. Do not build once and reload on a cold miss.
                            command += ["-d", str(index_temporary / "target.mmi")]
                            mapping_target = target
                        command += [str(mapping_target), str(temporary / "flanks.fa")]
                        started = time.monotonic()
                        (temporary / "command.txt").write_text(shlex.join(command) + "\n")
                        try:
                            with (temporary / "stdout.log").open("wb") as stdout, (temporary / "stderr.log").open("wb") as stderr:
                                subprocess.run(command, stdout=stdout, stderr=stderr, check=True)
                            parse_paf(temporary / "result.paf", self.query_map, self.target_lengths)
                            if index_temporary is not None:
                                if not (index_temporary / "target.mmi").is_file():
                                    fail("minimap2 did not publish the requested refill index")
                                publish(index_temporary, index_dir, index_payload, ("target.mmi",))
                        finally:
                            if index_temporary is not None and index_temporary.exists():
                                shutil.rmtree(index_temporary)
                    provenance = {"mode": "same_target_batch", "query_count": len(names),
                                  "index_cache_hit": index_hit, "index_fingerprint": index_key,
                                  "index_relpath": index_dir.relative_to(self.server_dir).as_posix(),
                                  "query_sha256": payload["query_sha256"],
                                  "target_sha256": payload["target_sha256"], "tool": tool,
                                  "mapping_seconds": time.monotonic() - started}
                    (temporary / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
                    publish(temporary, destination, payload, outputs)
                    self.cache_dir = destination
                except BaseException:
                    failed = self.server_dir / "grt/failed"
                    failed.mkdir(parents=True, exist_ok=True)
                    if temporary.exists():
                        os.replace(temporary, failed / temporary.name)
                    raise
        self.provenance = json.loads((self.cache_dir / "provenance.json").read_text())
        self.provenance["batch_cache_relpath"] = self.cache_dir.relative_to(self.server_dir).as_posix()
        self.provenance["batch_fingerprint"] = key
        self.rows = {name: [] for name in names}
        with (self.cache_dir / "result.paf").open("rb") as handle:
            for line in handle:
                if not line.strip():
                    continue
                query = line.split(b"\t", 1)[0].decode("utf-8")
                if query not in self.rows:
                    fail(f"unexpected refill batch query: {query}")
                self.rows[query].append(line)
        self.artifact_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.cache_dir, self.artifact_dir)
        print(f"GRT {self.stage}: same-target batch queries={len(names)} "
              f"index_cache_hit={self.provenance['index_cache_hit']}", flush=True)

    def __call__(self, query_fasta: Path, paf_path: Path, stage_dir: Path):
        if self.rows is None:
            self._prepare()
        # Restore original per-chromosome query-record order; preserve every PAF
        # byte and within-query hit order, including optional tags and CIGAR.
        names = [line[1:].split()[0] for line in query_fasta.read_text().splitlines()
                 if line.startswith(">")]
        with paf_path.open("wb") as handle:
            for name in names:
                if name not in self.rows:
                    fail(f"missing original query in refill batch: {name}")
                handle.writelines(self.rows[name])
        for name in ("command.txt", "stdout.log", "stderr.log"):
            shutil.copyfile(self.cache_dir / name, stage_dir / name)
        (stage_dir / "batch_provenance.json").write_text(json.dumps(self.provenance, indent=2, sort_keys=True) + "\n")
