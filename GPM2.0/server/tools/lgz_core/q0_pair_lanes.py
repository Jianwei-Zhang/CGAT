"""Bounded spawn lanes for independent candidates of one immutable placement round."""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
import multiprocessing
import pickle
import sys
from time import monotonic

from . import q0_source_screen as transport


def _lanes(n, threads):
    if n < 16 or threads < 2 or not sys.platform.startswith("linux") or not transport.resources.resource:
        return 1
    limit = transport.resources.execution_memory_limit(threads)
    if limit is None:
        return 1
    r = transport.resources.resource
    peak = r.getrusage(r.RUSAGE_SELF).ru_maxrss * 1024
    free = limit - peak - max(2 * 1024**3, peak // 2)
    return max(1, min(threads, transport.MAX_LANES, 1 + free // (transport.CHILD_AS + 6 * transport.WIRE_LIMIT)))


class _Slice:
    """Read-only window with the original indexing and length for the complexity rule."""
    def __init__(self, sequence, span):
        self.start, self.total, self.text = span.start, len(sequence), sequence[span.start:span.end]

    def __len__(self):
        return self.total

    def __getitem__(self, key):
        if key.step is not None or not self.start <= key.start <= key.stop <= self.start + len(self.text):
            raise ValueError("pair worker DNA access outside its declared interval")
        return self.text[key.start-self.start:key.stop-self.start]


def _packet(part, groups, linked, data, masks, policy, path_policy):
    # Bound both the bytes copied and pickle bookkeeping before touching DNA. An
    # oversized/unsupported candidate stays on the owner, with ALL of its links.
    refs = sum(map(len, groups.values())); size = part.interval.length + 128 * refs
    spans = {(part.source, part.interval)}; distinct_links = set()
    for anchor, links in linked:
        span = anchor.source, anchor.interval
        if span not in spans:
            spans.add(span); size += anchor.interval.length
        size += 128 * (len(anchor.evidence_ids) + len(anchor.reference_blocks) + len(anchor.anchor_intervals))
        if id(links) not in distinct_links:
            distinct_links.add(id(links)); size += len(links) * 512
            if size > transport.WIRE_LIMIT:
                return None
            for link in links:
                h = link.hit
                if not isinstance(h, transport.RetainedHit) or not isinstance(h._packed, bytes):
                    return None
                size += len(h._packed) + len(h._optional_fields)
        if size > transport.WIRE_LIMIT:
            return None
    relevant = {src: masks.get(src, ()) for src, _ in spans}
    if size + 64 * sum(map(len, relevant.values())) > transport.WIRE_LIMIT:
        return None
    regions = {(src, span): _Slice(data.sources[src], span) for src, span in spans}
    return transport._pack((part, groups, linked, regions, relevant, policy, path_policy))


def _work(raw):
    from .q0_admission import _candidate_delta, _clean_source_intervals
    try:
        part, groups, linked, regions, masks, policy, path_policy = pickle.loads(raw)
        cache = {}
        def clean(src, span, intervals):
            return _clean_source_intervals(regions[src, span], masks[src], intervals, policy)
        def context(anchor):
            key = anchor.source, anchor.interval
            if key not in cache:
                cache[key] = clean(*key, (anchor.interval,))
            return cache[key]
        return transport._pack(_candidate_delta(part, groups, linked, policy, path_policy,
                               lambda spans: clean(part.source, part.interval, spans), context))
    except MemoryError:
        return None


def ordered_deltas(keys, data, groups, masks, neighbors, policy, path_policy, threads, owner, log, round_number):
    """Compute out of process, consume only in candidate order; fallback never means no evidence."""
    lanes = _lanes(len(keys), threads); pool = None; pending = deque(); ix = inflight = 0
    workers = local = relations = 0; geo = complexity = 0.0; started = reported = monotonic()
    def report():
        log(f"placement pair work round={round_number}: owner_parts={local} worker_parts={workers} "
            f"new_relations={relations} geometry_task_s={geo:.1f} complexity_task_s={complexity:.1f} "
            f"wall_s={monotonic()-started:.1f}")
    try:
        if lanes > 1:
            try:
                pool = ProcessPoolExecutor(lanes-1, mp_context=multiprocessing.get_context("spawn"),
                                           initializer=transport._limit_child)
            except (OSError, MemoryError):
                lanes = 1
        log(f"placement pair work round={round_number}: cpu_budget={threads} lanes={lanes}")
        usable = pool is not None
        while ix < len(keys) or pending:
            while ix < len(keys) and len(pending) < lanes:
                key = keys[ix]; ix += 1; part = data.parts[key]; linked = neighbors.for_source(part.source)
                future = value = None; relations += len(linked)
                if usable and inflight < lanes-1 and linked:
                    try:
                        raw = _packet(part, groups.get(key, {}), linked, data, masks, policy, path_policy)
                        if raw is not None:
                            future = pool.submit(_work, raw); inflight += 1
                        del raw
                    except (BrokenProcessPool, OSError, MemoryError):
                        usable = False
                if future is None:
                    value = owner(key, linked); local += 1
                pending.append((key, future, value))
                if future is None:
                    break
            key, future, value = pending.popleft()
            if future is not None:
                inflight -= 1
                try:
                    raw = future.result()
                    if raw is not None:
                        value = pickle.loads(raw); workers += 1
                    del raw
                except (BrokenProcessPool, MemoryError):
                    usable = False
                if value is None:
                    value = owner(key, neighbors.for_source(data.parts[key].source)); local += 1
            delta, g, c = value; geo += g; complexity += c
            if monotonic() - reported >= 60:
                report(); reported = monotonic()
            yield key, delta
    finally:
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
    report()
