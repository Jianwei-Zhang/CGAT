"""Ordered owner-side evaluation against one immutable placement frontier."""
from time import monotonic, process_time


def ordered_deltas(keys, data, groups, masks, neighbors, policy, path_policy, threads, owner, log, round_number, *, time_phases=False):
    # The caller retains its rooted complexity cache across candidates and rounds.
    # Reference screening and PAF decoding have separate concurrency budgets.
    local = relations = whole_bp = tile_bp = 0
    geo = rooted = candidate = dispatch_s = owner_s = consume_s = 0.0
    started = reported = monotonic()
    cpu_started = process_time() if time_phases else 0.0

    def report():
        phases = (f" dispatch_wall_s={dispatch_s:.1f} owner_wall_s={owner_s:.1f}"
                  f" receive_wall_s=0.0 consumer_wall_s={consume_s:.1f}"
                  f" coordinator_cpu_s={process_time()-cpu_started:.1f}" if time_phases else "")
        log(f"placement pair work round={round_number}: owner_parts={local} worker_parts=0 "
            f"new_relations={relations} geometry_task_s={geo:.1f} complexity_task_s={rooted+candidate:.1f} "
            f"wall_s={monotonic()-started:.1f} anchor_complexity_task_s={rooted:.1f} "
            f"candidate_complexity_task_s={candidate:.1f} anchor_bp_whole_misses={whole_bp} anchor_bp_tile_misses={tile_bp}{phases}")

    log(f"placement pair work round={round_number}: cpu_budget={threads} lanes=1 mode=owner_only")
    for key in keys:
        if time_phases:
            stamp = monotonic()
        linked = neighbors.for_source(data.parts[key].source)
        relations += len(linked)
        if time_phases:
            end = monotonic()
            dispatch_s += end - stamp
        delta, g, r, c, full, tiled = owner(key, linked)
        local += 1
        geo += g; rooted += r; candidate += c; whole_bp += full; tile_bp += tiled
        now = monotonic()
        if time_phases:
            owner_s += now - end
        if now - reported >= 60:
            report()
            reported = now
        if time_phases:
            stamp = monotonic()
        yield key, delta
        if time_phases:
            consume_s += monotonic() - stamp
    report()
