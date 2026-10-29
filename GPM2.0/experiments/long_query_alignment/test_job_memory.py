"""Synthetic resource hierarchies; never change host/job memory controls."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import job_memory as jm

M = jm.MIB


class JobMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proc = self.root / "proc"
        (self.proc / "self").mkdir(parents=True)
        self.mount = self.root / "cgroup space"
        self.mount.mkdir()
        self.membership("/job/step")
        self.mountinfo()
        self.level("job", 512*M, 100*M)
        self.level("job/step", "max", 20*M)

    def membership(self, path):
        (self.proc / "self/cgroup").write_text("0::" + path + "\n")

    def mountinfo(self, root="/", mount=None, extra=""):
        escaped = str(mount or self.mount).replace("\\", "\\134").replace(" ", "\\040")
        (self.proc / "self/mountinfo").write_text(f"1 0 0:42 {root} {escaped} rw - cgroup2 cgroup rw\n" + extra)

    def level(self, path, cap, used):
        node = self.mount / path
        node.mkdir(parents=True, exist_ok=True)
        (node / "memory.max").write_text(str(cap) + "\n")
        (node / "memory.current").write_text(str(used) + "\n")

    def snapshot(self, env=None, **kwargs):
        return jm.discover_budget(proc_root=self.proc, environ=env or {}, **kwargs)

    def plan(self, snap, pending, **kwargs):
        return jm.plan_admission(snap, pending, cpu_budget=kwargs.pop("cpu_budget", 8),
                                 baseline_bytes=kwargs.pop("baseline_bytes", 16*M),
                                 reserve_bytes=kwargs.pop("reserve_bytes", 32*M),
                                 now_ns=kwargs.pop("now_ns", snap["observed_at_monotonic_ns"]), **kwargs)

    def test_parent_ceiling_and_parent_usage_control_leaf(self):
        snap = self.snapshot()
        self.assertEqual(snap["errors"], [])
        self.assertEqual(snap["effective_limit_bytes"], 512*M)
        self.assertEqual(snap["observed_headroom_bytes"], 412*M)
        self.assertEqual(len(snap["cgroup_observations"]), 2)
        self.assertFalse(snap["job_memory_reserved"])
        self.assertFalse(snap["host_memory_used_as_budget"])

    def test_different_ancestors_may_control_limit_and_headroom(self):
        self.level("job/step", 400*M, 10*M)
        self.level("job", 512*M, 500*M)
        snap = self.snapshot()
        self.assertEqual(snap["effective_limit_bytes"], 400*M)
        self.assertEqual(snap["observed_headroom_bytes"], 12*M)
        self.assertEqual(self.plan(snap, [jm.Demand("next", 1, M)])["decisions"][0]["decision"], "defer")

    def test_explicit_slurm_cgroup_min_and_mib_units(self):
        snap = self.snapshot({"SLURM_JOB_ID":"3", "SLURM_MEM_PER_NODE":"256"}, explicit_bytes=128*M)
        self.assertEqual(snap["errors"], [])
        self.assertEqual(snap["effective_limit_bytes"], 128*M)
        self.assertEqual([r["limit_bytes"] for r in snap["limits"][:2]], [128*M, 256*M])

    def test_slurm_per_cpu_requires_confirmed_usable_count(self):
        env = {"SLURM_JOB_ID":"3", "SLURM_MEM_PER_CPU":"10", "SLURM_CPUS_ON_NODE":"16",
               "SLURM_CPUS_PER_TASK":"4", "SLURM_JOB_CPUS_PER_NODE":"16(x2)"}
        missing = self.snapshot(env)
        self.assertIn("operator-confirmed", missing["errors"][0])
        snap = self.snapshot(env, slurm_usable_cpus=8)
        self.assertEqual(snap["effective_limit_bytes"], 80*M)
        self.assertEqual(snap["errors"], [])
        self.assertIn("exceeds", self.snapshot(env, slurm_usable_cpus=17)["errors"][0])

    def test_stale_slurm_environment_ignored_without_job(self):
        snap = self.snapshot({"SLURM_MEM_PER_NODE":"1"})
        self.assertEqual(snap["effective_limit_bytes"], 512*M)
        self.assertTrue(any("ignored" in w for w in snap["warnings"]))

    def test_zero_slurm_memory_not_zero_or_infinite_owned_memory(self):
        snap = self.snapshot({"SLURM_JOBID":"2", "SLURM_MEM_PER_NODE":"0"})
        self.assertEqual(snap["effective_limit_bytes"], 512*M)
        self.assertTrue(any("all-node" in w for w in snap["warnings"]))

    def test_invalid_conflicting_or_gpu_slurm_modes_block(self):
        for mode in ({"SLURM_MEM_PER_NODE":"500G"}, {"SLURM_MEM_PER_NODE":"-1"},
                     {"SLURM_MEM_PER_NODE":"500", "SLURM_MEM_PER_CPU":"5"},
                     {"SLURM_MEM_PER_GPU":"500"}):
            with self.subTest(mode=mode):
                snap = self.snapshot({"SLURM_JOB_ID":"2", **mode})
                plan = self.plan(snap, [jm.Demand("q", 1, M)])
                self.assertTrue(plan["blocking_reasons"])
                self.assertEqual(plan["decisions"][0]["decision"], "defer")

    def test_nonroot_mount_and_escaped_mountpoint(self):
        self.mountinfo(root="/outer")
        self.membership("/outer/job/step")
        self.level("", 768*M, 700*M)
        snap = self.snapshot()
        self.assertEqual(snap["errors"], [])
        self.assertEqual(snap["observed_headroom_bytes"], 68*M)
        self.assertEqual(len(snap["cgroup_observations"]), 3)

    def test_widest_mount_keeps_tighter_parent(self):
        leaf = self.mount / "job/step"
        bind = self.root / "bind"
        bind.mkdir()
        self.mountinfo(extra=f"2 0 0:42 /job/step {bind} rw - cgroup2 cgroup rw\n")
        self.assertEqual(self.snapshot()["effective_limit_bytes"], 512*M)
        self.assertEqual(leaf.exists(), True)

    def test_ambiguous_mounts_fail_closed(self):
        other = self.root / "other"
        self.mountinfo(extra=f"2 0 0:42 / {other} rw - cgroup2 cgroup rw\n")
        self.assertIn("ambiguous", self.snapshot()["errors"][0])

    def test_namespace_unresolvable_and_traversal_paths_fail_closed(self):
        for group in ("/../job/step", "/job/../../step", "relative", "//job/step"):
            with self.subTest(group=group):
                self.membership(group)
                self.assertTrue(self.snapshot()["errors"])
        self.membership("/")
        self.mountinfo(root="/hidden/job")
        self.assertIn("cannot be mapped", self.snapshot()["errors"][0])

    def test_v1_memory_or_hybrid_memory_not_mistaken_for_unlimited(self):
        for raw in ("5:memory:/job\n", "5:memory:/job\n0::/job/step\n"):
            (self.proc / "self/cgroup").write_text(raw)
            snap = self.snapshot(explicit_bytes=512*M)
            self.assertIn("v1 memory", snap["errors"][0])
            self.assertEqual(self.plan(snap, [jm.Demand("q", 1, M)])["decisions"][0]["decision"], "defer")

    def test_unlimited_is_unknown_without_finite_operator_or_scheduler_cap(self):
        self.level("job", "max", 100*M)
        snap = self.snapshot()
        self.assertIsNone(snap["effective_limit_bytes"])
        self.assertIsNone(snap["observed_headroom_bytes"])
        self.assertIn("no finite", self.plan(snap, [jm.Demand("q", 1, M)])["blocking_reasons"][0])
        self.assertEqual(self.snapshot(explicit_bytes=512*M)["effective_limit_bytes"], 512*M)

    def test_zero_limit_or_current_over_limit_defers_without_underflow(self):
        for cap, used in ((0, 0), (100*M, 101*M)):
            self.level("job", cap, used)
            snap = self.snapshot()
            self.assertEqual(snap["observed_headroom_bytes"], 0)
            self.assertEqual(self.plan(snap, [jm.Demand("q", 1, M)])["initial_memory_headroom_bytes"], 0)

    def test_missing_malformed_oversized_and_denied_files_block(self):
        path = self.mount / "job/memory.max"
        for raw in ("-1", "infinite", "9"*21, "1\n2", "x"*(jm.MAX_METADATA_BYTES+1)):
            path.write_text(raw)
            self.assertTrue(self.snapshot()["errors"])
        path.unlink()
        self.assertTrue(self.snapshot()["errors"])
        with patch.object(jm, "read_text", side_effect=PermissionError("denied")):
            self.assertIn("denied", self.snapshot()["errors"][0])

    def test_changing_membership_mount_or_limit_blocks_snapshot(self):
        real_read = jm.read_text
        for changed in (self.proc / "self/cgroup", self.proc / "self/mountinfo", self.mount / "job/memory.max"):
            calls = 0
            def changing(path):
                nonlocal calls
                value = real_read(path)
                if Path(path) == changed:
                    calls += 1
                    if calls == 2:
                        return value + "changed"
                return value
            with patch.object(jm, "read_text", side_effect=changing):
                self.assertTrue(self.snapshot()["errors"])

    def test_visible_root_with_interfaces_is_not_skipped(self):
        self.level("", 600*M, 590*M)
        snap = self.snapshot()
        self.assertEqual(snap["observed_headroom_bytes"], 10*M)
        self.assertEqual(len(snap["cgroup_observations"]), 3)

    def test_small_medium_large_budgets_adapt_proposals_not_alignment(self):
        results = []
        for budget_mib in (128, 512, 4096, 512000):
            self.level("job", budget_mib*M, 20*M)
            snap = self.snapshot()
            pending = [jm.Demand(str(i), 2, 128*M) for i in range(4)]
            plan = self.plan(snap, pending)
            results.append(sum(d["decision"] == "eligible_under_snapshot_only" for d in plan["decisions"]))
            for key in ("production_ready", "launch_allowed", "reservations_committed", "running_tasks_changed", "data_skipped"):
                self.assertFalse(plan[key])
        self.assertEqual(results, [0, 3, 4, 4])

    def test_active_full_peak_conservatively_counted_against_observed_headroom(self):
        snap = self.snapshot()
        plan = self.plan(snap, [jm.Demand("next", 2, 128*M)], active=[jm.Demand("active", 4, 256*M)])
        self.assertEqual(plan["initial_memory_headroom_bytes"], 108*M)
        self.assertEqual(plan["remaining_cpus"], 4)
        self.assertEqual(plan["decisions"][0]["decision"], "defer")
        self.assertTrue(plan["active_peak_double_accounting"])

    def test_cpu_budget_not_inferred_from_node_and_pending_fifo_not_bypassed(self):
        snap = self.snapshot()
        plan = self.plan(snap, [jm.Demand("big", 4, M), jm.Demand("small", 1, M)], cpu_budget=2)
        self.assertEqual(plan["decisions"][0]["reason"], "insufficient remaining CPU budget")
        self.assertEqual(plan["decisions"][1]["reason"], "FIFO predecessor deferred")

    def test_unknown_peak_does_not_get_invented_or_skip_work(self):
        snap = self.snapshot()
        plan = self.plan(snap, [jm.Demand("unknown", 1, None), jm.Demand("known", 1, M)])
        self.assertIn("unknown task peak", plan["decisions"][0]["reason"])
        self.assertEqual(plan["decisions"][1]["decision"], "defer")
        plan = self.plan(snap, [jm.Demand("next", 1, M)], active=[jm.Demand("active", 1, None)])
        self.assertIn("unknown peak", plan["blocking_reasons"][0])

    def test_stale_future_and_overallocated_cpu_snapshots_block(self):
        snap = self.snapshot()
        for offset in (-1, 5*10**9+1):
            plan = self.plan(snap, [jm.Demand("q", 1, M)], now_ns=snap["observed_at_monotonic_ns"]+offset)
            self.assertTrue(plan["blocking_reasons"])
        plan = self.plan(snap, [jm.Demand("q", 1, M)], active=[jm.Demand("old", 9, M)])
        self.assertIn("exceed CPU", plan["blocking_reasons"][0])

    def test_input_types_and_duplicate_task_ids_are_rejected(self):
        snap = self.snapshot()
        for pending in ([jm.Demand("x", 0, M)], [jm.Demand("x", True, M)], [jm.Demand("x", 1, 0)],
                        [jm.Demand("x", 1, 1.5)], [jm.Demand("", 1, M)], [jm.Demand("x", 1, M)]*2):
            with self.subTest(pending=pending), self.assertRaises(jm.BudgetError):
                self.plan(snap, pending)
        with self.assertRaises(jm.BudgetError):
            self.snapshot(explicit_bytes=True)

    def test_planning_and_snapshot_leave_inputs_and_resource_files_unchanged(self):
        before = {str(p):p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        snap = self.snapshot()
        saved = copy.deepcopy(snap)
        active, pending = [jm.Demand("running", 1, 32*M)], [jm.Demand("next", 1, 64*M)]
        plan = self.plan(snap, pending, active=active)
        self.assertEqual(plan["decisions"][0]["decision"], "eligible_under_snapshot_only")
        self.assertEqual(snap, saved)
        self.assertEqual(before, {str(p):p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual(active, [jm.Demand("running", 1, 32*M)])


if __name__ == "__main__":
    unittest.main()
