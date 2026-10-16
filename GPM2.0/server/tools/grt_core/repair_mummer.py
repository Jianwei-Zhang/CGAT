"""Shared MUMmer partitioning, numerical caches and bounded task execution."""

from __future__ import annotations

from .repair_common import *


MUMMER_LOG_NAMES = [
    f"{tool}.{suffix}"
    for tool in ("nucmer", "delta_filter", "show_coords")
    for suffix in ("command.txt", "stdout.log", "stderr.log")
]
def grt_mummer_parameters(threads: int) -> dict[str, object]:
    """Return the effective MUMmer contract used by upstream GRT.

    Upstream's observed ``delta-filter -i -r -l 10000`` invocation consumes
    ``-r`` as the value of ``-i`` and therefore does not apply reference-best
    filtering. Express the resulting semantics unambiguously instead of
    copying that malformed command line.
    """
    # Each task has one query record. Spend the CPU budget on independent
    # target partitions; nucmer query workers cannot split that one record.
    parameters = mummer_parameters(
        1,
        min_cluster=MUMMER_MIN_CLUSTER,
        min_match=MUMMER_MIN_MATCH,
        min_alignment=MUMMER_MIN_ALIGNMENT,
    )
    parameters["delta_filter"]["reference_best"] = False
    return parameters



def partition_mummer_targets(
    records: dict[str, str],
) -> list[list[tuple[str, str]]]:
    """Mirror upstream GRT's target partitions before alignment filtering.

    Upstream aligns every >=1 Mb record independently and packs smaller
    records into <=10 Mb chunks.  It then retains every alignment of at least
    10 kb; notably, its effective command does not apply reference-best
    filtering.  Both the partition boundary and the retained repeat hits are
    therefore part of the observed repair semantics.
    """
    large = [
        [(name, sequence)]
        for name, sequence in records.items()
        if len(sequence) >= MUMMER_LARGE_TARGET_BP
    ]
    small = sorted(
        (
            (name, sequence)
            for name, sequence in records.items()
            if len(sequence) < MUMMER_LARGE_TARGET_BP
        ),
        key=lambda row: -len(row[1]),
    )
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_size = 0
    for record in small:
        record_size = len(record[1])
        if current and current_size + record_size > MUMMER_SMALL_CHUNK_BP:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(record)
        current_size += record_size
    if current:
        chunks.append(current)
    return [*large, *chunks]



@dataclass(frozen=True)
class PreparedMummerInput:
    path: Path
    sha256: str



@dataclass
class MummerExecution:
    """One collection's immutable inputs and globally bounded worker pool."""

    records: dict[str, str]
    partitions: list[list[tuple[str, str]]]
    manifest: list[dict[str, object]]
    inputs: dict[int, PreparedMummerInput]
    pool: ThreadPoolExecutor
    workers: int
    cancel_event: Event
    cache_locks: dict[Path, object] = field(default_factory=dict, init=False, repr=False)
    cache_locks_guard: object = field(default_factory=Lock, init=False, repr=False)

    def cache_lock(self, directory: Path):
        # Screen records intentionally omit chromosome names. Equal windows in
        # different chromosomes therefore share a numerical key. Serialize that
        # key's check/build/publish, not the whole worker pool, and parse cached
        # rows in each caller's own coordinate/provenance context.
        with self.cache_locks_guard:
            return self.cache_locks.setdefault(directory, Lock())

    def indices(self, selected: set[int] | None = None) -> list[int]:
        # Scheduling only: aggregation and every line number retain input order.
        indices = range(1, len(self.partitions) + 1) if selected is None else selected
        return sorted(indices, key=lambda i: (
            -sum(len(sequence) for _name, sequence in self.partitions[i - 1]), i))



def mummer_partition_manifest(partitions: list[list[tuple[str, str]]]) -> list[dict[str, object]]:
    return [
        {"partition": index, "records": [
            {"name": name, "length": len(sequence),
             "sha256": sha256_bytes(sequence.encode("ascii"))}
            for name, sequence in partition]}
        for index, partition in enumerate(partitions, start=1)
    ]



def prepare_mummer_inputs(
    server_dir: Path, partitions: list[list[tuple[str, str]]],
    members_by_record: dict[str, dict[str, str]] | None = None,
) -> dict[int, PreparedMummerInput]:
    """Materialize content-addressed FASTA once; verify existing bytes each run.

    Workers only read these files. Never hard-link mutable workspace artifacts.
    The numerical raw-cache key remains identical to the baseline key.
    """
    parent = server_dir / "grt/cache/step23/inputs/v1"
    parent.mkdir(parents=True, exist_ok=True)
    inputs = {}
    for index, partition in enumerate(partitions, start=1):
        payload = fasta_bytes(partition)
        digest = sha256_bytes(payload)
        path = parent / f"{digest}.fa"
        if not path.is_file() or sha256_file(path) != digest:
            descriptor, name = tempfile.mkstemp(prefix=f".{digest}.", dir=parent)
            temporary = Path(name)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        if members_by_record is not None:
            descriptor, name = tempfile.mkstemp(prefix=f".{digest}.manifest.", dir=parent)
            os.close(descriptor)
            temporary = Path(name)
            try:
                write_tsv(temporary, DONOR_MEMBER_FIELDS,
                          [members_by_record[name] for name, _sequence in partition])
                os.replace(temporary, path.with_suffix(".manifest.tsv"))
            finally:
                temporary.unlink(missing_ok=True)
        inputs[index] = PreparedMummerInput(path, digest)
    return inputs



def mummer_screen_windows(
    chromosome: str,
    stage: str,
    sequence: str,
) -> tuple[list[tuple[str, str]], dict[str, dict[str, int]]]:
    """Build conservative local queries used only to select full-Q reruns.

    Step2 patch candidates allow anchors up to ``PATCH_MAX_ANCHOR_DISTANCE``
    apart; Step2 structural fallback and Step3 correction use
    ``CORRECTION_SEARCH_RANGE`` around the gap midpoint. Add one retained
    alignment length beyond the active range so every >=10 kb alignment with
    a relevant endpoint still has enough sequence to survive
    ``delta-filter -l`` in the screen.
    """
    if stage == "step2":
        q_version = "q1"
        margin = PATCH_MAX_ANCHOR_DISTANCE + MUMMER_MIN_ALIGNMENT
    elif stage == "step3":
        q_version = "q2"
        margin = CORRECTION_SEARCH_RANGE + MUMMER_MIN_ALIGNMENT
    else:
        fail(f"gap-screen is unsupported for {stage}")
    intervals = [
        (
            max(1, int(gap["start0"]) + 1 - margin),
            min(len(sequence), int(gap["end0"]) + margin),
        )
        for gap in gap_objects(chromosome, q_version, sequence)
    ]
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    records: list[tuple[str, str]] = []
    windows: dict[str, dict[str, int]] = {}
    for index, (start, end) in enumerate(merged, start=1):
        name = f"screen_{index:04d}_{start}_{end}"
        records.append((name, sequence[start - 1 : end]))
        windows[name] = {"start": start, "end": end}
    return records, windows



def step3_mummer_screen_windows(
    chromosome: str,
    sequence: str,
) -> tuple[list[tuple[str, str]], dict[str, dict[str, int]]]:
    """Compatibility wrapper for the original Step3-only screen helper."""
    return mummer_screen_windows(chromosome, "step3", sequence)



def parse_mummer_screen_coords(
    path: Path,
    windows: dict[str, dict[str, int]],
    members_by_record: dict[str, dict[str, str]],
    donor_lengths: dict[str, int],
) -> list[dict[str, object]]:
    """Parse window-query coords and project them into whole-Q2 coordinates."""
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n")
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("/")
                or stripped.startswith("NUCMER")
                or stripped.startswith("[")
                or stripped.startswith("=")
            ):
                continue
            fields = [value for value in stripped.split() if value != "|"]
            if len(fields) < 11:
                fail(f"invalid MUMmer screen coords row at {path}:{line_number}")
            try:
                ref_start, ref_end, query_start, query_end = map(int, fields[:4])
                ref_aligned, query_aligned = map(int, fields[4:6])
                identity = float(fields[6])
                ref_length, query_length = map(int, fields[7:9])
            except ValueError:
                fail(f"non-numeric MUMmer screen coords row at {path}:{line_number}")
            ref_record, query_record = fields[-2:]
            if ref_record not in members_by_record:
                fail(f"MUMmer screen references unknown D0 member at {path}:{line_number}")
            if query_record not in windows:
                fail(f"MUMmer screen references unknown query window at {path}:{line_number}")
            window = windows[query_record]
            expected_query_length = int(window["end"]) - int(window["start"]) + 1
            if ref_length != donor_lengths[ref_record] or query_length != expected_query_length:
                fail(f"MUMmer screen length columns disagree with FASTA at {path}:{line_number}")
            if not (
                1 <= min(ref_start, ref_end) <= max(ref_start, ref_end) <= ref_length
                and 1 <= min(query_start, query_end) <= max(query_start, query_end) <= query_length
                and ref_aligned >= 1
                and query_aligned >= 1
                and 0 <= identity <= 100
            ):
                fail(f"MUMmer screen has invalid coordinates at {path}:{line_number}")
            offset = int(window["start"]) - 1
            query_start += offset
            query_end += offset
            rows.append(
                {
                    "line_number": line_number,
                    "ref_record": ref_record,
                    "ref_start": ref_start,
                    "ref_end": ref_end,
                    "ref_min": min(ref_start, ref_end),
                    "ref_max": max(ref_start, ref_end),
                    "query_start": query_start,
                    "query_end": query_end,
                    "query_min": min(query_start, query_end),
                    "query_max": max(query_start, query_end),
                    "identity": identity / 100.0,
                    "ref_aligned": ref_aligned,
                    "query_aligned": query_aligned,
                    "raw_line": line,
                }
            )
    return rows



def step3_screen_partition_relevant(
    gaps: list[dict[str, object]],
    rows: list[dict[str, object]],
) -> bool:
    """Preserve crossing hits and every anchor that can affect window choice.

    The structural controller stops at the first window containing *any* left
    and *any* right anchor, before checking whether they share a donor record.
    A one-sided partition can therefore block a more distant pair in another
    partition. It must not be dropped just because it cannot make a pair alone.
    """
    for gap in gaps:
        gap_pos = (int(gap["start0"]) + int(gap["end0"]) + 1) // 2
        for row in rows:
            query_min = int(row["query_min"])
            query_max = int(row["query_max"])
            if query_min <= gap_pos <= query_max:
                return True
            if min(abs(query_min - gap_pos), abs(query_max - gap_pos)) <= CORRECTION_SEARCH_RANGE:
                return True
    return False



def step2_screen_partition_relevant(
    gaps: list[dict[str, object]],
    rows: list[dict[str, object]],
) -> bool:
    """Return whether one partition can contribute any Step2 strategy input."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["ref_record"])].append(row)
    for gap in gaps:
        gap_position = int(gap["start0"]) + 1
        for member_rows in grouped.values():
            lefts = sorted(
                (
                    row
                    for row in member_rows
                    if int(row["query_max"]) <= gap_position + 10
                ),
                key=lambda row: (-int(row["query_max"]), -float(row["identity"])),
            )[:2]
            rights = sorted(
                (
                    row
                    for row in member_rows
                    if int(row["query_min"]) >= gap_position - 10
                ),
                key=lambda row: (int(row["query_min"]), -float(row["identity"])),
            )[:2]
            if any(
                int(right["query_min"]) - int(left["query_max"])
                <= PATCH_MAX_ANCHOR_DISTANCE
                for left in lefts
                for right in rights
            ):
                return True
        if step3_screen_partition_relevant([gap], rows):
            return True
    return False



def mummer_available_memory() -> int:
    """Available bytes, also respecting the current Linux cgroup limit."""
    available = None
    try:
        values = dict(
            line.split(":", 1)
            for line in Path("/proc/meminfo").read_text().splitlines()
        )
        available = int(values["MemAvailable"].split()[0]) * 1024
    except (OSError, KeyError, ValueError):
        pass
    try:
        # The visible root covers containers; the relative group covers hosts
        # with nested systemd limits. Include every visible ancestor limit.
        relative = next(
            line.split(":", 2)[2]
            for line in Path("/proc/self/cgroup").read_text().splitlines()
            if line.startswith("0::")
        )
        root = Path("/sys/fs/cgroup")
        group = root / relative.lstrip("/")
        groups = [root, *[p for p in [group, *group.parents] if root in p.parents]]
        for path in groups:
            try:
                limit = int((path / "memory.max").read_text().strip())
                current = int((path / "memory.current").read_text().strip())
                remaining = max(0, limit - current)
                available = min(available, remaining) if available is not None else remaining
            except (OSError, ValueError):
                continue
    except (OSError, StopIteration):
        pass
    return available if available is not None else 0



def mummer_partition_workers(
    threads: int, partition_sizes: list[int], query_size: int,
    *, available_memory: int | None = None,
) -> int:
    if not partition_sizes:
        return 1
    cpu_count = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    available = mummer_available_memory() if available_memory is None else available_memory
    # Conservative admission estimate, not a hard RSS guarantee. Keep 30% of
    # current headroom for Python, other pipeline processes and the OS.
    per_job = max(512 * 1024**2, 32 * max(partition_sizes) + 4 * query_size)
    memory_workers = max(1, int(available * 0.7) // per_job) if available else 1
    return max(1, min(threads, cpu_count, len(partition_sizes), memory_workers))



def valid_mummer_cache(directory: Path, fingerprint: str, names: list[str]) -> bool:
    try:
        checkpoint = json.loads((directory / "cache.json").read_text(encoding="utf-8"))
        if not isinstance(checkpoint, dict):
            return False
        hashes = checkpoint.get("output_hashes", {})
        return (
            isinstance(hashes, dict)
            and checkpoint.get("status") == "success"
            and checkpoint.get("input_fingerprint") == fingerprint
            and set(hashes) == set(names)
            and all((directory / name).is_file() and sha256_file(directory / name) == expected
                    for name, expected in hashes.items())
        )
    except (OSError, TypeError, ValueError):
        return False



def raw_mummer_cache_identity(
    server_dir: Path,
    partition: list[tuple[str, str]],
    query_sha256: str,
    tools: dict[str, dict[str, str]],
    prepared_input: PreparedMummerInput | None = None,
) -> tuple[bytes | None, dict[str, object], str, Path, list[str]]:
    """Return the exact cache identity shared by full-query MUMmer callers."""
    target_payload = None if prepared_input is not None else fasta_bytes(partition)
    target_sha256 = prepared_input.sha256 if prepared_input is not None else sha256_bytes(target_payload)
    payload = {
        "raw_alignment_version": 1,
        "query_sha256": query_sha256,
        "target_sha256": target_sha256,
        "tools": {name: command_identity(value) for name, value in tools.items()},
        "parameters": grt_mummer_parameters(1),
    }
    fingerprint = json_hash(payload)
    cache_dir = server_dir / "grt/cache/step23/raw_mummer/v1" / fingerprint
    return target_payload, payload, fingerprint, cache_dir, ["result.coords", *MUMMER_LOG_NAMES]



def complete_raw_mummer_cache(
    server_dir: Path,
    chromosome: str,
    q_sequence: str,
    target_partitions: list[list[tuple[str, str]]],
    tools: dict[str, dict[str, str]],
    execution: MummerExecution | None = None,
) -> bool:
    """Return true only when every full-query partition cache is validated."""
    query_sha256 = sha256_bytes(fasta_bytes([(chromosome, q_sequence)]))
    for index, partition in enumerate(target_partitions, start=1):
        _target, _payload, fingerprint, cache_dir, names = raw_mummer_cache_identity(
            server_dir, partition, query_sha256, tools,
            execution.inputs[index] if execution is not None else None,
        )
        if not valid_mummer_cache(cache_dir, fingerprint, names):
            return False
    return bool(target_partitions)



def cached_mummer_partition(
    server_dir: Path, temporary: Path, stage: str, chromosome: str,
    index: int, total: int, partition: list[tuple[str, str]],
    query_sha256: str, query_length: int, target_kind: str,
    members_by_record: dict[str, dict[str, str]], donor_lengths: dict[str, int],
    tools: dict[str, dict[str, str]], cancel_event: Event,
    prepared_input: PreparedMummerInput | None = None,
    execution: MummerExecution | None = None,
) -> tuple[Path, bool, float]:
    """Cache numerical alignments independently of repair stage/provenance."""
    started = time.monotonic()
    label = f"part-{index:04d}"
    target_payload, payload, fingerprint, cache_dir, names = raw_mummer_cache_identity(
        server_dir, partition, query_sha256, tools, prepared_input
    )
    cache_parent = cache_dir.parent
    with execution.cache_lock(cache_dir) if execution is not None else nullcontext():
        if cancel_event.is_set():
            fail("MUMmer partition cancelled")
        if valid_mummer_cache(cache_dir, fingerprint, names):
            parse_mummer_coords(cache_dir / "result.coords", stage, chromosome,
                                query_length, members_by_record, donor_lengths)
            elapsed = time.monotonic() - started
            print(f"GRT {stage} MUMmer {chromosome} {index}/{total}: CACHE_HIT ({elapsed:.2f}s)", flush=True)
            return cache_dir, True, elapsed
        work = temporary / label
        work.mkdir()
        target_path = prepared_input.path if prepared_input is not None else work / "target.fa"
        if prepared_input is None:
            target_path.write_bytes(target_payload)
        del target_payload
        if target_kind == "ordinary_donor" and prepared_input is None:
            write_tsv(target_path.with_suffix(".manifest.tsv"), DONOR_MEMBER_FIELDS,
                      [members_by_record[name] for name, _sequence in partition])
        delta = work / "result.delta"
        filtered = work / "filtered.delta"
        coords = work / "result.coords"
        nucmer_parameters = payload["parameters"]["nucmer"]
        commands = [
            ("nucmer", [tools["nucmer"]["resolved"], "-c", str(nucmer_parameters["min_cluster"]),
                        "-l", str(nucmer_parameters["min_match"]),
                        f"--batch={nucmer_parameters['batch']}", "-t", str(nucmer_parameters["threads"]),
                        "-p", str(work / "result"), str(target_path), str(temporary / "query.fa")], None),
            ("delta_filter", [tools["delta-filter"]["resolved"], "-l",
                              str(payload["parameters"]["delta_filter"]["min_alignment"]), str(delta)], filtered),
            ("show_coords", [tools["show-coords"]["resolved"], "-r", "-l", str(filtered)], coords),
        ]
        print(f"GRT {stage} MUMmer {chromosome} {index}/{total}: START", flush=True)
        header_only_delta = False
        for tool_name, command, output in commands:
            logs = [work / f"{tool_name}.{suffix}" for suffix in ("command.txt", "stdout.log", "stderr.log")]
            if tool_name == "delta_filter":
                if not delta.is_file() or delta.stat().st_size == 0:
                    fail(f"nucmer did not create a non-empty delta for {stage}:{chromosome}:{label}")
                header_only_delta = is_header_only_mummer_delta(delta)
            if tool_name != "nucmer" and header_only_delta:
                output.write_bytes(delta.read_bytes() if tool_name == "delta_filter" else b"")
                write_skipped_command_logs(command, *logs, "nucmer produced no alignments")
            else:
                run_logged(command, work, *logs, output, cancel_event=cancel_event)
        if not filtered.is_file() or not coords.is_file():
            fail(f"partitioned MUMmer did not create filtered coordinates for {stage}:{chromosome}:{label}")
        parse_mummer_coords(coords, stage, chromosome, query_length, members_by_record, donor_lengths)
        elapsed = time.monotonic() - started
        checkpoint = {
            "status": "success", "input_fingerprint": fingerprint,
            "fingerprint_payload": payload, "elapsed_seconds": elapsed,
            "output_hashes": {name: sha256_file(work / name) for name in names},
        }
        # Publish only a fully validated partition. A failed neighbour never
        # removes this checkpoint; partial work remains in the stage diagnostics.
        for path in work.iterdir():
            if path.name not in names:
                path.unlink()
        (work / "cache.json").write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        cache_parent.mkdir(parents=True, exist_ok=True)
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        os.replace(work, cache_dir)
        print(f"GRT {stage} MUMmer {chromosome} {index}/{total}: SUCCESS ({elapsed:.2f}s)", flush=True)
        return cache_dir, False, elapsed



def cached_mummer_screen_partition(
    server_dir: Path,
    temporary: Path,
    stage: str,
    chromosome: str,
    index: int,
    total: int,
    partition: list[tuple[str, str]],
    query_sha256: str,
    windows: dict[str, dict[str, int]],
    members_by_record: dict[str, dict[str, str]],
    donor_lengths: dict[str, int],
    tools: dict[str, dict[str, str]],
    cancel_event: Event,
    prepared_input: PreparedMummerInput | None = None,
    execution: MummerExecution | None = None,
) -> tuple[Path, bool, float, list[dict[str, object]]]:
    """Cache a local-window screen used only to select exact full-Q2 reruns."""
    started = time.monotonic()
    label = f"part-{index:04d}"
    target_payload = None if prepared_input is not None else fasta_bytes(partition)
    payload = {
        "raw_alignment_version": 1,
        "screen_version": 1,
        "query_sha256": query_sha256,
        "target_sha256": prepared_input.sha256 if prepared_input is not None else sha256_bytes(target_payload),
        "tools": {name: command_identity(value) for name, value in tools.items()},
        "parameters": grt_mummer_parameters(1),
    }
    fingerprint = json_hash(payload)
    cache_parent = server_dir / "grt/cache/step23/raw_mummer_screen/v1"
    cache_dir = cache_parent / fingerprint
    names = ["result.coords", *MUMMER_LOG_NAMES]
    with execution.cache_lock(cache_dir) if execution is not None else nullcontext():
        if cancel_event.is_set():
            fail("MUMmer screen partition cancelled")
        if valid_mummer_cache(cache_dir, fingerprint, names):
            rows = parse_mummer_screen_coords(
                cache_dir / "result.coords", windows, members_by_record, donor_lengths
            )
            elapsed = time.monotonic() - started
            print(
                f"GRT {stage} screen {chromosome} {index}/{total}: CACHE_HIT ({elapsed:.2f}s)",
                flush=True,
            )
            return cache_dir, True, elapsed, rows
        work = temporary / label
        work.mkdir()
        target_path = prepared_input.path if prepared_input is not None else work / "target.fa"
        if prepared_input is None:
            target_path.write_bytes(target_payload)
        del target_payload
        delta = work / "result.delta"
        filtered = work / "filtered.delta"
        coords = work / "result.coords"
        parameters = payload["parameters"]
        commands = [
            (
                "nucmer",
                [
                    tools["nucmer"]["resolved"],
                    "-c",
                    str(parameters["nucmer"]["min_cluster"]),
                    "-l",
                    str(parameters["nucmer"]["min_match"]),
                    f"--batch={parameters['nucmer']['batch']}",
                    "-t",
                    "1",
                    "-p",
                    str(work / "result"),
                    str(target_path),
                    str(temporary / "query.fa"),
                ],
                None,
            ),
            (
                "delta_filter",
                [
                    tools["delta-filter"]["resolved"],
                    "-l",
                    str(parameters["delta_filter"]["min_alignment"]),
                    str(delta),
                ],
                filtered,
            ),
            (
                "show_coords",
                [tools["show-coords"]["resolved"], "-r", "-l", str(filtered)],
                coords,
            ),
        ]
        print(f"GRT {stage} screen {chromosome} {index}/{total}: START", flush=True)
        header_only_delta = False
        for tool_name, command, output in commands:
            logs = [
                work / f"{tool_name}.{suffix}"
                for suffix in ("command.txt", "stdout.log", "stderr.log")
            ]
            if tool_name == "delta_filter":
                if not delta.is_file() or delta.stat().st_size == 0:
                    fail(
                        f"nucmer did not create a non-empty screen delta for "
                        f"{stage}:{chromosome}:{label}"
                    )
                header_only_delta = is_header_only_mummer_delta(delta)
            if tool_name != "nucmer" and header_only_delta:
                output.write_bytes(delta.read_bytes() if tool_name == "delta_filter" else b"")
                write_skipped_command_logs(command, *logs, "nucmer screen produced no alignments")
            else:
                run_logged(command, work, *logs, output, cancel_event=cancel_event)
        if not filtered.is_file() or not coords.is_file():
            fail(
                f"partitioned MUMmer screen did not create filtered coordinates for "
                f"{stage}:{chromosome}:{label}"
            )
        rows = parse_mummer_screen_coords(coords, windows, members_by_record, donor_lengths)
        elapsed = time.monotonic() - started
        checkpoint = {
            "status": "success",
            "input_fingerprint": fingerprint,
            "fingerprint_payload": payload,
            "elapsed_seconds": elapsed,
            "output_hashes": {name: sha256_file(work / name) for name in names},
        }
        for path in work.iterdir():
            if path.name not in names:
                path.unlink()
        (work / "cache.json").write_text(
            json.dumps(checkpoint, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        cache_parent.mkdir(parents=True, exist_ok=True)
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        os.replace(work, cache_dir)
        print(
            f"GRT {stage} screen {chromosome} {index}/{total}: SUCCESS ({elapsed:.2f}s)",
            flush=True,
        )
        return cache_dir, False, elapsed, rows



def screen_mummer_partitions(
    server_dir: Path,
    temporary: Path,
    stage: str,
    chromosome: str,
    q_sequence: str,
    target_partitions: list[list[tuple[str, str]]],
    members_by_record: dict[str, dict[str, str]],
    donor_lengths: dict[str, int],
    tools: dict[str, dict[str, str]],
    threads: int,
    execution: MummerExecution | None = None,
) -> tuple[set[int], list[dict[str, object]], list[tuple[str, str]]]:
    """Select partitions, then let the caller rerun them against the full Q."""
    query_records, windows = mummer_screen_windows(chromosome, stage, q_sequence)
    if not query_records:
        return set(), [], []
    query_payload = fasta_bytes(query_records)
    screen_root = temporary / "screen"
    screen_root.mkdir()
    (screen_root / "query.fa").write_bytes(query_payload)
    q_version = "q1" if stage == "step2" else "q2"
    gaps = gap_objects(chromosome, q_version, q_sequence)
    workers = mummer_partition_workers(
        threads,
        [sum(len(sequence) for _name, sequence in part) for part in target_partitions],
        sum(len(sequence) for _name, sequence in query_records),
    )
    print(
        f"GRT {stage} screen {chromosome}: {len(target_partitions)} partitions, "
        f"windows={len(query_records)}, workers={workers}",
        flush=True,
    )
    cancel_event = execution.cancel_event if execution is not None else Event()
    results: dict[int, tuple[Path, bool, float, list[dict[str, object]]]] = {}
    pool = execution.pool if execution is not None else ThreadPoolExecutor(max_workers=workers)
    indices = execution.indices() if execution is not None else range(1, len(target_partitions) + 1)
    futures = {}
    try:
        futures = {
            pool.submit(
                cached_mummer_screen_partition,
                server_dir,
                screen_root,
                stage,
                chromosome,
                index,
                len(target_partitions),
                target_partitions[index - 1],
                sha256_bytes(query_payload),
                windows,
                members_by_record,
                donor_lengths,
                tools,
                cancel_event,
                execution.inputs[index] if execution is not None else None,
                execution,
            ): index
            for index in indices
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    except BaseException:
        cancel_event.set()
        for future in futures:
            future.cancel()
        raise
    finally:
        if execution is None:
            pool.shutdown(wait=True, cancel_futures=True)
    relevant = (
        step2_screen_partition_relevant
        if stage == "step2"
        else step3_screen_partition_relevant
    )
    selected = {
        index
        for index, (_directory, _hit, _elapsed, rows) in results.items()
        if relevant(gaps, rows)
    }
    rows = [
        {
            "partition": str(index),
            "selected": "true" if index in selected else "false",
            "alignment_count": str(len(results[index][3])),
            "cache_hit": "true" if results[index][1] else "false",
            "elapsed_seconds": f"{results[index][2]:.3f}",
        }
        for index in range(1, len(target_partitions) + 1)
    ]
    print(
        f"GRT {stage} screen {chromosome}: selected={len(selected)}/{len(target_partitions)}",
        flush=True,
    )
    shutil.rmtree(screen_root)
    return selected, rows, query_records



def screen_step3_mummer_partitions(
    server_dir: Path,
    temporary: Path,
    chromosome: str,
    q_sequence: str,
    target_partitions: list[list[tuple[str, str]]],
    members_by_record: dict[str, dict[str, str]],
    donor_lengths: dict[str, int],
    tools: dict[str, dict[str, str]],
    threads: int,
) -> tuple[set[int], list[dict[str, object]], list[tuple[str, str]]]:
    """Compatibility wrapper for the original Step3-only screen helper."""
    return screen_mummer_partitions(
        server_dir,
        temporary,
        "step3",
        chromosome,
        q_sequence,
        target_partitions,
        members_by_record,
        donor_lengths,
        tools,
        threads,
    )



def cached_mummer_chromosome(
    server_dir: Path,
    stage: str,
    chromosome: str,
    q_source_sha256: str,
    q_sequence: str,
    q_segment_rows: list[dict[str, object]],
    donor_set: dict[str, str],
    members_by_record: dict[str, dict[str, str]],
    donor_lengths: dict[str, int],
    tools: dict[str, dict[str, str]],
    threads: int,
    should_align: bool,
    target_kind: str = "ordinary_donor",
    mummer_scope: str = DEFAULT_MUMMER_SCOPE,
    execution: MummerExecution | None = None,
    parsed_rows: list[dict[str, object]] | None = None,
) -> tuple[Path, bool, str]:
    if mummer_scope not in MUMMER_SCOPES:
        fail(f"unsupported MUMmer scope: {mummer_scope}")
    if mummer_scope == "gap-screen" and stage not in {"step2", "step3"}:
        fail("gap-screen MUMmer scope is only supported for Step2/Step3")
    query_payload = fasta_bytes([(chromosome, q_sequence)])
    parameters = grt_mummer_parameters(threads)
    target_records = execution.records if execution is not None else dict(
        read_fasta_allow_empty(server_dir / donor_set["fasta_relpath"])
    )
    target_partitions = execution.partitions if execution is not None else partition_mummer_targets(target_records)
    partition_manifest = execution.manifest if execution is not None else mummer_partition_manifest(target_partitions)
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "engine_sha256": ENGINE_SHA256,
        "stage": stage,
        "chr": chromosome,
        "q_source_sha256": q_source_sha256,
        "q_chromosome_sha256": sha256_bytes(q_sequence.encode("ascii")),
        "q_segments_sha256": json_hash(q_segment_rows),
        "query_artifact_sha256": sha256_bytes(query_payload),
        "target_kind": target_kind,
        "target_id": donor_set["donor_set_id"],
        "target_sha256": donor_set["fasta_sha256"],
        "donor_fragment_index_sha256": (
            sha256_file(server_dir / "metadata/grt_donor_fragments.tsv")
            if target_kind == "ordinary_donor"
            else ""
        ),
        "tools": {name: command_identity(value) for name, value in tools.items()},
        "parameters": parameters,
        "mummer_scope": mummer_scope,
        "screen_parameters": (
            {
                "search_range": (
                    PATCH_MAX_ANCHOR_DISTANCE
                    if stage == "step2"
                    else CORRECTION_SEARCH_RANGE
                ),
                "guard_bp": MUMMER_MIN_ALIGNMENT,
                "selection": (
                    "step2_patch_or_structural_candidate"
                    if stage == "step2"
                    else "crossing_or_any_window_affecting_anchor"
                ),
                "final_alignment": f"selected_partitions_against_full_{'q1' if stage == 'step2' else 'q2'}",
            }
            if mummer_scope == "gap-screen"
            else None
        ),
        "target_partitioning": {
            "large_record_min_bp": MUMMER_LARGE_TARGET_BP,
            "small_chunk_max_bp": MUMMER_SMALL_CHUNK_BP,
            "partitions": partition_manifest,
        },
        "should_align": should_align,
    }
    fingerprint = json_hash(fingerprint_payload)
    chromosome_key = stable_id("chr", chromosome, 16)
    cache_parent = server_dir / f"grt/cache/step23/{stage}/mummer/{chromosome_key}"
    cache_dir = cache_parent / fingerprint
    checkpoint_path = cache_dir / "cache.json"
    output_names = [
        "query.fa",
        "result.coords",
        "target_partitions.json",
        "nucmer.command.txt",
        "nucmer.stdout.log",
        "nucmer.stderr.log",
        "delta_filter.command.txt",
        "delta_filter.stdout.log",
        "delta_filter.stderr.log",
        "show_coords.command.txt",
        "show_coords.stdout.log",
        "show_coords.stderr.log",
    ]
    if mummer_scope == "gap-screen":
        output_names.extend(["screen_query.fa", "screen_partitions.tsv"])
    if checkpoint_path.is_file():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            hashes = checkpoint.get("output_hashes", {})
            if (
                checkpoint.get("status") == "success"
                and checkpoint.get("input_fingerprint") == fingerprint
                and set(hashes) == set(output_names)
                and all(
                    (cache_dir / name).is_file()
                    and sha256_file(cache_dir / name) == expected
                    for name, expected in hashes.items()
                )
            ):
                validated_rows = parse_mummer_coords(
                    cache_dir / "result.coords",
                    stage,
                    chromosome,
                    len(q_sequence),
                    members_by_record,
                    donor_lengths,
                )
                if parsed_rows is not None:
                    parsed_rows.extend(validated_rows)
                return cache_dir, True, chromosome_key
        except (OSError, TypeError, ValueError, json.JSONDecodeError, SystemExit):
            pass
    cache_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{fingerprint}.", dir=cache_parent))
    try:
        (temporary / "query.fa").write_bytes(query_payload)
        coords = temporary / "result.coords"
        if should_align:
            selected_partitions = set(range(1, len(target_partitions) + 1))
            if mummer_scope == "gap-screen":
                selected_partitions, screen_rows, screen_query_records = (
                    screen_mummer_partitions(
                        server_dir,
                        temporary,
                        stage,
                        chromosome,
                        q_sequence,
                        target_partitions,
                        members_by_record,
                        donor_lengths,
                        tools,
                        threads,
                        execution,
                    )
                )
                (temporary / "screen_query.fa").write_bytes(
                    fasta_bytes(screen_query_records)
                )
                write_tsv(
                    temporary / "screen_partitions.tsv",
                    [
                        "partition",
                        "selected",
                        "alignment_count",
                        "cache_hit",
                        "elapsed_seconds",
                    ],
                    screen_rows,
                )
            partition_manifest = [
                {**row, "selected": index in selected_partitions}
                for index, row in enumerate(partition_manifest, start=1)
            ]
            (temporary / "target_partitions.json").write_text(
                json.dumps(partition_manifest, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
                newline="",
            )
            aggregate: dict[str, list[bytes]] = {
                f"{tool_name}.{suffix}": []
                for tool_name in ("nucmer", "delta_filter", "show_coords")
                for suffix in ("command.txt", "stdout.log", "stderr.log")
            }
            workers = mummer_partition_workers(
                threads,
                [
                    sum(len(seq) for _name, seq in target_partitions[index - 1])
                    for index in sorted(selected_partitions)
                ],
                len(q_sequence),
            )
            print(f"GRT {stage} MUMmer {chromosome}: {len(selected_partitions)}/"
                  f"{len(target_partitions)} partitions, "
                  f"workers={workers}, nucmer_threads=1, thread_budget={threads}", flush=True)
            cancel_event = execution.cancel_event if execution is not None else Event()
            results: dict[int, tuple[Path, bool, float]] = {}
            pool = execution.pool if execution is not None else ThreadPoolExecutor(max_workers=workers)
            indices = execution.indices(selected_partitions) if execution is not None else sorted(selected_partitions)
            futures = {}
            query_sha256 = sha256_bytes(query_payload)
            try:
                futures = {
                    pool.submit(
                        cached_mummer_partition, server_dir, temporary, stage, chromosome,
                        index, len(target_partitions), target_partitions[index - 1], query_sha256,
                        len(q_sequence), target_kind, members_by_record, donor_lengths,
                        tools, cancel_event,
                        execution.inputs[index] if execution is not None else None,
                        execution,
                    ): index
                    for index in indices
                }
                for future in as_completed(futures):
                    results[futures[future]] = future.result()
            except BaseException:
                cancel_event.set()
                for future in futures:
                    future.cancel()
                raise
            finally:
                if execution is None:
                    pool.shutdown(wait=True, cancel_futures=True)
            # Completion order must never change coordinate line numbers or
            # candidate tie breaking. Aggregate in the original partition order.
            with coords.open("wb") as handle:
                for index in sorted(selected_partitions):
                    part_dir, _hit, _elapsed = results[index]
                    with (part_dir / "result.coords").open("rb") as part_handle:
                        shutil.copyfileobj(part_handle, handle)
                    marker = f"# part-{index:04d}\n".encode("utf-8")
                    for name in aggregate:
                        aggregate[name].extend([marker, (part_dir / name).read_bytes()])
            for name, parts in aggregate.items():
                (temporary / name).write_bytes(b"".join(parts))
        else:
            (temporary / "target_partitions.json").write_text(
                json.dumps(partition_manifest, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
                newline="",
            )
            coords.write_bytes(b"")
            for prefix in ("nucmer", "delta_filter", "show_coords"):
                (temporary / f"{prefix}.command.txt").write_text(
                    f"skipped: no remaining gap or {target_kind} target is empty\n",
                    encoding="utf-8",
                    newline="",
                )
                (temporary / f"{prefix}.stdout.log").write_text("", encoding="utf-8")
                (temporary / f"{prefix}.stderr.log").write_text("", encoding="utf-8")
            if mummer_scope == "gap-screen":
                (temporary / "screen_query.fa").write_bytes(b"")
                write_tsv(
                    temporary / "screen_partitions.tsv",
                    [
                        "partition",
                        "selected",
                        "alignment_count",
                        "cache_hit",
                        "elapsed_seconds",
                    ],
                    [],
                )
        validated_rows = parse_mummer_coords(
            coords,
            stage,
            chromosome,
            len(q_sequence),
            members_by_record,
            donor_lengths,
        )
        checkpoint = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "engine_sha256": ENGINE_SHA256,
            "stage": stage,
            "chr": chromosome,
            "status": "success",
            "input_fingerprint": fingerprint,
            "fingerprint_payload": fingerprint_payload,
            "output_hashes": {name: sha256_file(temporary / name) for name in output_names},
        }
        (temporary / "cache.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        os.replace(temporary, cache_dir)
        if parsed_rows is not None:
            parsed_rows.extend(validated_rows)
        return cache_dir, False, chromosome_key
    except BaseException as error:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"{stage}-mummer-{chromosome_key}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
            if isinstance(error, SystemExit) and isinstance(error.code, str):
                relocated = error.code.replace(str(temporary), str(failed_dir))
                relocated = f"{relocated}; failed_artifacts={failed_dir}"
                error.code = relocated
                error.args = (relocated,)
            else:
                print(
                    f"ERROR: failed MUMmer artifacts preserved at {failed_dir}",
                    file=sys.stderr,
                    flush=True,
                )
        raise



def collect_mummer(
    server_dir: Path,
    temporary: Path,
    artifact_relpath: str,
    stage: str,
    q_source_sha256: str,
    chromosome_order: list[str],
    records: dict[str, str],
    q_rows: list[dict[str, object]],
    donor_set: dict[str, str],
    donor_members: list[dict[str, str]],
    tools: dict[str, dict[str, str]],
    threads: int,
    *,
    target_set: dict[str, str] | None = None,
    target_members: list[dict[str, str]] | None = None,
    target_kind: str = "ordinary_donor",
    mummer_scope: str = DEFAULT_MUMMER_SCOPE,
    execution_profile: str = DEFAULT_EXECUTION_PROFILE,
) -> tuple[list[dict[str, object]], dict[str, dict[str, str]], list[dict[str, object]]]:
    started = time.monotonic()
    if execution_profile not in EXECUTION_PROFILES:
        fail(f"unsupported execution profile: {execution_profile}")
    optimized = execution_profile == "optimized"
    active_set = donor_set if target_set is None else target_set
    active_members = donor_members if target_members is None else target_members
    members_by_record = {row["fasta_record_name"]: row for row in active_members}
    donor_records = dict(read_fasta_allow_empty(server_dir / active_set["fasta_relpath"]))
    if set(members_by_record) != set(donor_records):
        fail(f"{target_kind} FASTA records differ from its alignment target manifest")
    donor_lengths = {name: len(sequence) for name, sequence in donor_records.items()}
    target_partitions = partition_mummer_targets(donor_records)
    q1_records: dict[str, str] = {}
    if stage == "step3" and mummer_scope == "gap-screen":
        q1_records = dict(read_fasta(server_dir / "grt/q/q1.fa"))
    execution = None
    input_seconds = 0.0

    def align(chromosome: str):
        chromosome_rows = [row for row in q_rows if row["chr"] == chromosome]
        should_align = bool(donor_records) and bool(gap_objects(chromosome, stage, records[chromosome]))
        chromosome_scope = mummer_scope
        if chromosome_scope == "gap-screen" and q1_records.get(chromosome) == records[chromosome]:
            if complete_raw_mummer_cache(
                server_dir, chromosome, records[chromosome], target_partitions, tools, execution
            ):
                chromosome_scope = "full"
                print(f"GRT step3 MUMmer {chromosome}: Q2 unchanged from Q1; "
                      "all full-query partition caches validated", flush=True)
            else:
                print(f"GRT step3 MUMmer {chromosome}: Q2 unchanged from Q1 but "
                      "full-query cache is incomplete; using gap-screen", flush=True)
        parsed = [] if optimized else None
        cache_dir, cache_hit, chromosome_key = cached_mummer_chromosome(
            server_dir, stage, chromosome, q_source_sha256, records[chromosome],
            chromosome_rows, active_set, members_by_record, donor_lengths, tools,
            threads, should_align, target_kind, chromosome_scope, execution, parsed,
        )
        print(f"GRT {stage} MUMmer {chromosome}: {'cache hit' if cache_hit else 'computed'}")
        destination = temporary / "mummer" / "by_chr" / chromosome_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy_started = time.monotonic()
        shutil.copytree(cache_dir, destination)
        copy_seconds = time.monotonic() - copy_started
        parse_started = time.monotonic()
        chromosome_alignments = parsed if parsed is not None else parse_mummer_coords(
            destination / "result.coords", stage, chromosome,
            len(records[chromosome]), members_by_record, donor_lengths,
        )
        print(f"GRT {stage} {chromosome} artifact metrics: copy_seconds={copy_seconds:.3f} "
              f"post_copy_parse_seconds={time.monotonic() - parse_started:.3f} "
              f"parse_reused={parsed is not None}", flush=True)
        identity = {
            "query_relpath": f"{artifact_relpath}/mummer/by_chr/{chromosome_key}/query.fa",
            "query_sha256": sha256_file(destination / "query.fa"),
            "coords_relpath": f"{artifact_relpath}/mummer/by_chr/{chromosome_key}/result.coords",
            "coords_sha256": sha256_file(destination / "result.coords"),
        }
        return chromosome_alignments, identity, {
            "chr": chromosome, "chromosome_key": chromosome_key,
            "cache_key": cache_dir.name, **identity,
        }

    collected = {}
    if optimized and target_partitions and chromosome_order:
        input_started = time.monotonic()
        inputs = prepare_mummer_inputs(
            server_dir, target_partitions,
            members_by_record if target_kind == "ordinary_donor" else None,
        )
        manifest = mummer_partition_manifest(target_partitions)
        input_seconds = time.monotonic() - input_started
        workers = mummer_partition_workers(
            threads,
            [sum(len(seq) for _name, seq in part) for part in target_partitions] * len(chromosome_order),
            max(len(records[chromosome]) for chromosome in chromosome_order),
        )
        print(f"GRT {stage} execution: profile=optimized shared_workers={workers} "
              f"chromosomes={len(chromosome_order)} order=largest-target-first", flush=True)
        cancel_event = Event()
        # Separate coordinators never execute nucmer. Only this shared pool does;
        # screen and full-query jobs together cannot exceed the global budget.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            execution = MummerExecution(donor_records, target_partitions, manifest,
                                        inputs, pool, workers, cancel_event)
            with ThreadPoolExecutor(max_workers=min(len(chromosome_order), workers)) as coordinators:
                futures = {coordinators.submit(align, chromosome): chromosome
                           for chromosome in chromosome_order}
                try:
                    for future in as_completed(futures):
                        collected[futures[future]] = future.result()
                except BaseException:
                    cancel_event.set()
                    for future in futures:
                        future.cancel()
                    raise
    else:
        for chromosome in chromosome_order:
            collected[chromosome] = align(chromosome)
    alignments: list[dict[str, object]] = []
    identities: dict[str, dict[str, str]] = {}
    tasks: list[dict[str, object]] = []
    # Publication order is independent of scheduling and completion order.
    for chromosome in chromosome_order:
        chromosome_alignments, identity, task = collected[chromosome]
        alignments.extend(chromosome_alignments)
        identities[chromosome] = identity
        tasks.append(task)
    print(f"GRT {stage} execution metrics: profile={execution_profile} "
          f"input_seconds={input_seconds:.3f} collection_seconds={time.monotonic() - started:.3f}", flush=True)
    write_tsv(
        temporary / "mummer" / "chromosome_tasks.tsv",
        [
            "chr",
            "chromosome_key",
            "cache_key",
            "query_relpath",
            "query_sha256",
            "coords_relpath",
            "coords_sha256",
        ],
        tasks,
    )
    write_tsv(
        temporary / "mummer" / "alignments.tsv",
        MUMMER_ALIGNMENT_FIELDS,
        [
            {
                **{field: row.get(field, "") for field in MUMMER_ALIGNMENT_FIELDS},
                "identity": f"{float(row['identity']):.9f}",
            }
            for row in alignments
        ],
    )
    return alignments, identities, tasks
