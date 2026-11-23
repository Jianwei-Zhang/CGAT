"""Runtime-only CPU lanes for the original per-part reference admission rule."""
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from io import BytesIO
import multiprocessing
import pickle
import sys
from types import SimpleNamespace
from time import monotonic

from . import q0_regional_execution as resources
from .q0_retained_hits import RetainedHit

MIB = 1024**2
MAX_LANES = 8  # largest measured budget
CHILD_AS = 1024*MIB
WIRE_LIMIT = 12*MIB
MIN_PART_BP = 750_000
MIN_BATCH_BP = 16_000_000
MIN_SOURCES = 8


def _weight(data, part):
    """Cheap routing estimate, never an exclusion from admission; no CIGAR expansion."""
    size = len(data.sources[part.source]); span = part.interval
    hits = data.reference_hits.get(part.source, ())
    if not (MIN_PART_BP <= span.length and span.length * 2 >= size and size <= 8*MIB and 0 < len(hits) <= 2048):
        return 0  # at most two packets may carry the same original source
    covered = 0
    for hit in hits:
        covered += max(0, min(span.end, hit.query.end) - max(span.start, hit.query.start))
        if covered >= span.length:
            break
    return min(covered, span.length) if covered >= MIN_PART_BP else 0


def _lanes(data, ordered, allowed, threads):
    if threads < 2 or not sys.platform.startswith("linux") or not resources.resource or len(allowed) < MIN_SOURCES:
        return 1
    sources = set(); total = 0
    for key, part in ordered:
        if key in allowed and (weight := _weight(data, part)):
            total += weight; sources.add(part.source)
            if len(sources) >= MIN_SOURCES and total >= MIN_BATCH_BP:
                break
    else:
        return 1
    limit = resources.execution_memory_limit(threads)
    if limit is None:
        return 1
    peak = resources.resource.getrusage(resources.resource.RUSAGE_SELF).ru_maxrss * 1024
    free = limit - peak - max(2*1024*MIB, peak//2)
    # Reserve each child AS plus the bounded transport/result copies in the owner.
    return max(1, min(MAX_LANES, threads, 1 + free//(CHILD_AS + 6*WIRE_LIMIT)))


def _limit_child():
    r = resources.resource
    limits = r.getrlimit(r.RLIMIT_AS)
    cap = min([CHILD_AS, *(n for n in limits if n != r.RLIM_INFINITY)])
    r.setrlimit(r.RLIMIT_AS, (cap, cap))


class _BoundedBuffer(BytesIO):
    def write(self, block):
        if self.tell() + len(block) > WIRE_LIMIT:
            raise BufferError("reference screen packet too large")
        return super().write(block)


def _pack(value):
    try:
        buf = _BoundedBuffer()
        pickle.Pickler(buf, protocol=5).dump(value)
        return buf.getvalue()
    except (BufferError, MemoryError):
        return None


def _packet(data, part, policy):
    # Do not let pickle encode a huge optional tag or traverse unbounded fallback CIGARs
    # before the wire cap can act. The threshold reader normally provides packed bytes.
    dna = data.sources[part.source]; hits = data.reference_hits[part.source]
    size = len(dna)
    for hit in hits:
        if not isinstance(hit, RetainedHit) or not isinstance(hit._packed, bytes):
            return None
        size += len(hit._packed) + len(hit._optional_fields) + len(hit.artifact) + len(hit.query_name) + len(hit.target_name)
        if size > WIRE_LIMIT:
            return None
    return _pack((part, dna, hits, policy))


def _run(payload):
    from .q0_admission import _reference_groups
    try:
        part, sequence, hits, policy = pickle.loads(payload)
        view = SimpleNamespace(sources={part.source: sequence}, reference_hits={part.source: hits})
        return _pack(_reference_groups(view, part, policy))
    except MemoryError:
        return None  # exact owner evaluation; never translate resource limits into a verdict


def ordered_screens(data, ordered, allowed, policy, threads, screen, log):
    """Always yield in segment order. Only process-private, bounded bytes cross spawn."""
    lanes = _lanes(data, ordered, allowed, threads)
    log(f"reference screen: parts={len(ordered)} cpu_budget={threads} lanes={lanes}")
    pool = None; workers_done = 0; lo = 0; reported = monotonic()
    try:
        if lanes > 1:
            try:
                pool = ProcessPoolExecutor(lanes-1, mp_context=multiprocessing.get_context("spawn"), initializer=_limit_child)
            except (OSError, MemoryError):
                pass
        usable = pool is not None
        while lo < len(ordered):
            hi = lo; futures = {}; local = {}
            # One wave holds at most lanes-1 future payloads and one owner result.
            while usable and hi < len(ordered):
                i = hi; hi += 1; key, part = ordered[i]
                if key not in allowed or not _weight(data, part):
                    continue
                if len(futures) >= lanes-1:
                    local[i] = screen(data, part, policy)
                    break
                payload = _packet(data, part, policy)
                if payload is None:
                    continue
                try:
                    futures[i] = pool.submit(_run, payload)
                except (BrokenProcessPool, OSError, MemoryError):
                    usable = False
                del payload
            if not usable:
                hi = len(ordered)
            for i in range(lo, hi):
                key, part = ordered[i]; value = local.pop(i, None)
                if i in futures:
                    try:
                        raw = futures.pop(i).result()
                    except (BrokenProcessPool, MemoryError):
                        raw = None; usable = False
                    if raw is not None:
                        try:
                            value = pickle.loads(raw); workers_done += 1
                        except MemoryError:
                            pass  # retry the identical part in the owner
                    del raw
                if value is None and key in allowed:
                    value = screen(data, part, policy)
                if monotonic() - reported >= 60:
                    log(f"reference screen: completed={i+1}/{len(ordered)} worker_parts={workers_done}")
                    reported = monotonic()
                yield key, part, value
            lo = hi
    finally:
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
    log(f"reference screen complete: parts={len(ordered)} worker_parts={workers_done}")
