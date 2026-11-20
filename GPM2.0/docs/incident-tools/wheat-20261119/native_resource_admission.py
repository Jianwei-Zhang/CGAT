"""Candidate resource-only admission; never edit a running frozen dispatcher.

Only commands verified by NativeBindings enter the native pool. CPU grants retain
AdaptiveDispatcher.desired; memory limits and the available CPU budget determine
concurrency, not a fixed four-lane cap. The existing fast pool remains unchanged.
"""
from pathlib import Path

from alignment_tasks import AdaptiveDispatcher
import native_batch_guard as guard
import self_two_lane_admission as fast_admission

POLICY = {**fast_admission.POLICY,
          "native_reservation_gib": guard.POLICY["reservation_bytes"] // guard.GIB,
          "maximum_native_query_bases": guard.POLICY["maximum_query_bases"],
          "native_process_policy": guard.POLICY.copy(),
          "maximum_processes": 16, "maximum_native_processes": 16}


class SelfDispatcher(fast_admission.SelfDispatcher):
    def __init__(self, bindings, native_exclusive, *, max_fast):
        plan = bindings.plan
        for role, module in (("fast_admission", fast_admission), ("native_guard", guard)):
            record = plan["dependencies"][role]
            if guard.checked(record).resolve() != Path(module.__file__).resolve():
                raise ValueError("unbound resource admission dependency: " + role)
        if plan["resource_policy"]["reservation_policy"] != POLICY:
            raise ValueError("native admission policy differs from the immutable plan")
        # A plan listing paths alone is not sufficient. The resource bindings
        # must validate canonical wrappers, specs, native keys and full inventory.
        bindings.verify_native_resources()
        super().__init__(bindings, native_exclusive, max_fast=max_fast)
        self.native = set()
        for row in bindings.rows.values():
            for record in row["native_scripts"].values():
                path = guard.checked(record)
                if path in self.native or path in self.fast or path in self.exclusive:
                    raise ValueError("native resource command is duplicated or overlaps fast work")
                self.native.add(path)

    def kind(self, task):
        if task.command in self.native:
            return "native"
        # In particular, an original unguarded native command is exclusive.
        return "fast" if task.command in self.fast else "exclusive"

    def __call__(self, pending, available, budget, active, slots):
        if available <= 0 or budget <= 0 or slots <= 0:
            return []
        if any(type(item.get("threads")) is not int or item["threads"] < 1 for item in active):
            raise ValueError("active thread grants are required for native CPU accounting")
        available = min(available, budget - sum(item["threads"] for item in active))
        if available <= 0:
            return []
        kinds = {self.kind(item["task"]) for item in active}
        if "exclusive" in kinds or len(kinds) > 1:
            return []
        ordered = sorted(pending, key=lambda t: t.work or t.priority, reverse=True)
        if not ordered:
            return []
        pool = next(iter(kinds)) if kinds else self.kind(ordered[0])
        if pool != "native":
            return super().__call__(pending, available, budget, active, slots)
        reservation = POLICY["native_reservation_gib"]
        capacity = min(POLICY["maximum_native_processes"],
                       POLICY["reservation_pool_gib"] // reservation)
        slots = min(slots, capacity - len(active))
        if slots <= 0:
            return []
        selected = []
        seen = {id(item["task"]) for item in active}
        for task in ordered:
            if self.kind(task) != "native" or id(task) in seen:
                continue
            need = AdaptiveDispatcher.desired(task, budget)
            if need > available:
                # Do not leave cores idle behind an eight-thread queue head
                # when a compatible one-thread native batch is ready.
                continue
            selected.append((task, need))
            seen.add(id(task))
            available -= need
            if available == 0 or len(selected) == slots:
                break
        return selected
