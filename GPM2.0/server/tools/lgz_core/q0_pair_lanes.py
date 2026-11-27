"""Bounded spawn lanes for independent candidates of one immutable placement round."""
from collections import deque
from dataclasses import fields
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
import multiprocessing
import pickle
import sys
from time import monotonic, process_time

from . import q0_source_screen as transport
from .q0_pair_transport import SequenceStore, SharedValue, _OBJECTS

MAX_PAIR_LANES = 32
_WORKER_CONTEXT = None
_WORKER_GENERATION = None
_WORKER_REGIONS = {}
_WORKER_MASKS = {}


def _lanes(n, threads):
    if n < 16 or threads < 2 or not sys.platform.startswith("linux") or not transport.resources.resource:
        return 1
    limit = transport.resources.execution_memory_limit(threads)
    if limit is None:
        return 1
    r = transport.resources.resource
    peak = r.getrusage(r.RUSAGE_SELF).ru_maxrss * 1024
    free = limit - peak - max(2 * 1024**3, peak // 2)
    return max(1, min(threads, MAX_PAIR_LANES, 1 + free // (transport.CHILD_AS + 6 * transport.WIRE_LIMIT)))


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


def _wire_placement(anchor):
    # This is an already validated immutable Placement from this owner. Copy
    # its declared fields only; dataclasses.replace would rerun the expensive
    # reference-footprint validation for every candidate/anchor relationship.
    clean = object.__new__(type(anchor))
    clean.__dict__.update((f.name, getattr(anchor, f.name)) for f in fields(anchor))
    return clean


def _packet(part, groups, linked, data, masks, policy, path_policy, store=None):
    # Bound both the bytes copied and pickle bookkeeping before touching DNA. An
    # oversized/unsupported candidate stays on the owner, with ALL of its links.
    refs = sum(map(len, groups.values())); size = part.interval.length + 128 * refs if store is None else 512
    spans = {(part.source, part.interval)}; distinct_links = set()
    for anchor, links in linked:
        span = anchor.source, anchor.interval
        if span not in spans:
            spans.add(span); size += anchor.interval.length if store is None else 256
        size += (128 * (len(anchor.evidence_ids) + len(anchor.reference_blocks) + len(anchor.anchor_intervals))
                 if store is None else 256)
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
    masks = masks if store is None else store.masks
    relevant = {src: masks.get(src, ()) for src, _ in spans}
    if size + (64 * sum(map(len, relevant.values())) if store is None else 256 * len(relevant)) > transport.WIRE_LIMIT:
        return None
    if store is None:
        regions = {(src, span): _Slice(data.sources[src], span) for src, span in spans}
    else:
        regions = {(src, span): store.region(src, span) for src, span in spans}
        if any(value is None for value in regions.values()):
            return None
    # Cached indexes on Placements are accelerators, not scientific fields.
    # Do not serialize them repeatedly with the same immutable anchor.
    if store is None:
        linked = [(_wire_placement(anchor), links) for anchor, links in linked]
    else:
        linked = [(store.metadata(("anchor", anchor.placement_id), _wire_placement(anchor)), links)
                  for anchor, links in linked]
        groups = store.metadata(("groups", part.segment_id), groups)
        relevant = {src: store.metadata(("mask", src), value) for src, value in relevant.items()}
        if groups is None or any(a is None for a, _ in linked) or any(v is None for v in relevant.values()):
            return None
    return transport._pack((part, groups, linked, regions, relevant, policy, path_policy,
                            None if store is None else str(store.root)))


def _work(raw):
    from .q0_admission import _candidate_delta, _RootedContext
    global _WORKER_CONTEXT, _WORKER_GENERATION
    try:
        part, groups, linked, regions, masks, policy, path_policy, epoch = pickle.loads(raw)
        if isinstance(groups, SharedValue):
            groups = groups.load()
            linked = [(anchor.load(), links) for anchor, links in linked]
            masks = {src: value.load() for src, value in masks.items()}
        generation = epoch, policy
        if epoch is None or generation != _WORKER_GENERATION:
            _WORKER_CONTEXT = None
            _WORKER_GENERATION = generation
        _WORKER_REGIONS.clear(); _WORKER_REGIONS.update(regions)
        _WORKER_MASKS.clear(); _WORKER_MASKS.update(masks)
        if _WORKER_CONTEXT is None:
            _WORKER_CONTEXT = _RootedContext(lambda src, span: _WORKER_REGIONS[src, span], _WORKER_MASKS, policy)
        context = _WORKER_CONTEXT
        return transport._pack(_candidate_delta(part, groups, linked, policy, path_policy,
                               lambda spans: context.clean(part.source, part.interval, spans), context))
    except MemoryError:
        _WORKER_CONTEXT = None
        _OBJECTS.clear()
        return None


def ordered_deltas(keys, data, groups, masks, neighbors, policy, path_policy, threads, owner, log, round_number, *, time_phases=False):
    """Compute out of process, consume only in candidate order; fallback never means no evidence."""
    lanes = _lanes(len(keys), threads); pool = store = None; pending = deque(); ix = inflight = 0
    workers = local = relations = whole_bp = tile_bp = 0; geo = rooted = candidate = 0.0; started = reported = monotonic()
    # Elapsed time on the coordinator, not worker CPU. Include candidate transport and
    # the time the generator is suspended in its caller; neither appears in the task counters.
    dispatch_s = owner_s = receive_s = consume_s = 0.0
    cpu_started = process_time() if time_phases else 0.0
    def report():
        phases = (f" dispatch_wall_s={dispatch_s:.1f} owner_wall_s={owner_s:.1f}"
                  f" receive_wall_s={receive_s:.1f} consumer_wall_s={consume_s:.1f}"
                  f" coordinator_cpu_s={process_time()-cpu_started:.1f}" if time_phases else "")
        log(f"placement pair work round={round_number}: owner_parts={local} worker_parts={workers} "
            f"new_relations={relations} geometry_task_s={geo:.1f} complexity_task_s={rooted+candidate:.1f} "
            f"wall_s={monotonic()-started:.1f} anchor_complexity_task_s={rooted:.1f} "
            f"candidate_complexity_task_s={candidate:.1f} anchor_bp_whole_misses={whole_bp} anchor_bp_tile_misses={tile_bp}{phases}")
    try:
        if lanes > 1:
            try:
                store = SequenceStore(data.sources, masks)
                pool = ProcessPoolExecutor(lanes-1, mp_context=multiprocessing.get_context("spawn"),
                                           initializer=transport._limit_child)
            except (OSError, MemoryError):
                lanes = 1
        log(f"placement pair work round={round_number}: cpu_budget={threads} lanes={lanes}")
        usable = pool is not None
        while ix < len(keys) or pending:
            while ix < len(keys) and len(pending) < lanes:
                if time_phases:
                    stamp = monotonic()
                key = keys[ix]; ix += 1; part = data.parts[key]; linked = neighbors.for_source(part.source)
                future = value = None; relations += len(linked)
                if usable and inflight < lanes-1 and linked:
                    try:
                        raw = _packet(part, groups.get(key, {}), linked, data, masks, policy, path_policy, store)
                        if raw is not None:
                            future = pool.submit(_work, raw); inflight += 1
                        del raw
                    except (BrokenProcessPool, OSError, MemoryError):
                        usable = False
                if time_phases:
                    end = monotonic(); dispatch_s += end - stamp
                if future is None:
                    value = owner(key, linked); local += 1
                    if time_phases:
                        owner_s += monotonic() - end
                pending.append((key, future, value))
                if future is None:
                    break
            key, future, value = pending.popleft()
            if future is not None:
                if time_phases:
                    stamp = monotonic()
                inflight -= 1
                try:
                    raw = future.result()
                    if raw is not None:
                        value = pickle.loads(raw); workers += 1
                    del raw
                except (BrokenProcessPool, MemoryError):
                    usable = False
                if time_phases:
                    end = monotonic(); receive_s += end - stamp
                if value is None:
                    value = owner(key, neighbors.for_source(data.parts[key].source)); local += 1
                    if time_phases:
                        owner_s += monotonic() - end
            delta, g, r, c, full, tiled = value
            geo += g; rooted += r; candidate += c; whole_bp += full; tile_bp += tiled
            if monotonic() - reported >= 60:
                report(); reported = monotonic()
            if time_phases:
                stamp = monotonic()
            yield key, delta
            if time_phases:
                consume_s += monotonic() - stamp
    finally:
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
        if store is not None:
            log(f"placement pair shared DNA round={round_number}: sources={len(store.rows)} bytes_written={store.written_bytes} metadata_objects={len(store.values)}")
            store.close()
    report()
