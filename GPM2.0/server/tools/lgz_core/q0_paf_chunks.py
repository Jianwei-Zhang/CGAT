"""Ordered CPU lanes for large retained PAFs. The owner alone opens the original text stream."""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from functools import lru_cache
import multiprocessing
import os
import sys
from time import monotonic

from .q0_retained_hits import RetainedHit, _retained_line, retained_geometry_cache
from .q0_sources import Interval, Q0EvidenceError

MIB = 1024**2
MIN_FILE = 8 * MIB
BLOCK_CHARS = 256 * 1024
MAX_ROWS = 1024
MAX_WORKERS = 7  # plus the owner (read, bind, assemble); never one worker per requested CPU
CHILD_AS = 1024 * MIB


def worker_budget(path, threads):
    if threads < 2 or not sys.platform.startswith('linux'):
        return 0
    size = path.stat().st_size
    if size < MIN_FILE:
        return 0
    from .q0_regional_execution import execution_memory_limit, resource
    if not resource or multiprocessing.current_process().daemon:
        return 0
    limit = execution_memory_limit(threads)
    if limit is None:
        return 0
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    spare = limit - peak - max(2048 * MIB, peak // 2)
    cpus = min(threads, len(os.sched_getaffinity(0)))
    return max(0, min(MAX_WORKERS, cpus - 1, size // MIN_FILE, spare // (CHILD_AS + 32 * MIB)))


_geometry = None


def _start_worker():
    import resource
    global _geometry
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    cap = min([CHILD_AS, *(n for n in (soft, hard) if n != resource.RLIM_INFINITY)])
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    _geometry = retained_geometry_cache()


def _decode(artifact, prefix, first, lines):
    rows = []
    for number, line in enumerate(lines, first):
        try:
            row = (None if line.startswith('#') or not line.strip() else
                   _retained_line(line, artifact, number, prefix, None, None, _geometry))
        except (ValueError, KeyError):
            row = None  # owner replays this physical line through the authoritative reader
        rows.append(row)
    return rows


def _blocks(stream):
    first = 1; lines = []; size = 0
    try:
        for number, line in enumerate(stream, 1):
            if lines and (len(lines) >= MAX_ROWS or size + len(line) > BLOCK_CHARS):
                yield first, lines
                lines = []; size = 0; first = number
            if len(line) > BLOCK_CHARS:
                yield number, [line]  # never enqueue an unbounded record to a worker
                first = number + 1
            else:
                lines.append(line); size += len(line)
    except (OSError, UnicodeError):
        if lines:
            yield first, lines
        raise
    if lines:
        yield first, lines


def decode_ordered(stream, artifact, prefix, query_names, target_names, serial, workers):
    pending = deque(); pool = None; available = True

    def use_owner(exc):
        nonlocal available
        if available:
            print(f'LGZ q0 PAF decode: {artifact} reverting to owner ({type(exc).__name__})', flush=True)
        available = False
    decoded = local = 0; started = monotonic()
    # Pickle preserves shared geometry only within a packet. Re-intern small packed CIGARs
    # across packets so a long self matrix doesn't retain one identical bytes object per row.
    shared = lru_cache(maxsize=8192)(lambda value: value)

    def consume(first, lines, future):
        nonlocal decoded, local
        rows = None
        if future is not None:
            try:
                rows = future.result()
            except (BrokenProcessPool, MemoryError) as exc:
                use_owner(exc)  # raw block is still owned here, never reopen or skip a row
        if rows is not None and len(rows) != len(lines):
            raise Q0EvidenceError('retained PAF worker returned an incomplete block')
        for offset, line in enumerate(lines):
            number = first + offset
            row = None if rows is None else rows[offset]
            if row is not None:
                key, digest, q, qlen, q0, q1, strand, t, tlen, t0, t1, matches, length, mq, packed, tags = row
                try:
                    query = query_names[q]; target = target_names[t]
                except (KeyError, ValueError):
                    pass  # canonical parser owns the diagnostic or valid edge case
                else:
                    if query[1] == qlen and target[1] == tlen:
                        if isinstance(packed, bytes) and len(packed) <= 128:
                            packed = shared(packed)
                        decoded += 1
                        yield RetainedHit(key, artifact, number, digest, query[0], query[1], Interval(q0, q1),
                                          strand, target[0], target[1], Interval(t0, t1), matches, length, mq,
                                          packed, tags)
                        continue
            hit = serial(number, line)
            if hit is not None:
                local += 1
                yield hit

    print(f'LGZ q0 PAF decode: {artifact} workers={workers} plus_owner=1', flush=True)
    try:
        try:
            pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn'),
                                       initializer=_start_worker)
        except (OSError, RuntimeError) as exc:
            use_owner(exc)
        blocks = iter(_blocks(stream))
        while True:
            # One queued successor lets even a single worker decode while the owner
            # binds its previous block. Never queue the remainder of the file.
            if len(pending) >= workers + 1:
                yield from consume(*pending.popleft())
            try:
                first, lines = next(blocks)
            except StopIteration:
                break
            except (OSError, UnicodeError):
                while pending:  # surface earlier invalid rows before a later read failure
                    yield from consume(*pending.popleft())
                raise
            if not available or (len(lines) == 1 and len(lines[0]) > BLOCK_CHARS):
                while pending:
                    yield from consume(*pending.popleft())
                yield from consume(first, lines, None)
                continue
            try:
                future = pool.submit(_decode, artifact, prefix, first, lines)
            except (OSError, RuntimeError) as exc:
                future = None
                use_owner(exc)
            pending.append((first, lines, future))
        while pending:
            yield from consume(*pending.popleft())
    finally:
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
    print(f'LGZ q0 PAF decoded: {artifact} worker_rows={decoded} owner_rows={local} '
          f'elapsed_s={monotonic()-started:.1f}', flush=True)
