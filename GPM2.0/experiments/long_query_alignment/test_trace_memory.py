"""Budget adaptation must preserve witness values and never assume node RAM."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_post_dp as audit
import stream_seed_trace as st
import trace_memory as tm
import windowed_alignment as wa


class TraceMemoryTests(unittest.TestCase):
    def test_small_medium_large_process_budgets_select_bounded_buffers(self):
        expected = {40:8192, 64:65536, 128:65536, 512:tm.MIB, 4096:tm.MIB, 512000:tm.MIB}
        for mib, size in expected.items():
            with self.subTest(mib=mib):
                plan = tm.choose_buffer(24*tm.MIB, explicit_bytes=mib*tm.MIB)
                self.assertEqual(plan["selected_buffer_bytes"], size)
                self.assertLessEqual(size, plan["allocation_headroom_bytes"])
                self.assertFalse(plan["hard_limit_changed"])
                self.assertFalse(plan["job_memory_reserved"])

    def test_explicit_budget_cannot_override_lower_hard_limit_or_existing_usage(self):
        plan = tm.choose_buffer(24*tm.MIB, 64*tm.MIB, 512000*tm.MIB)
        self.assertEqual(plan["effective_budget_bytes"], 64*tm.MIB)
        tight = tm.choose_buffer(48*tm.MIB, 64*tm.MIB, requested_bytes=16*tm.MIB)
        self.assertEqual(tight["selected_buffer_bytes"], tm.MIB)
        self.assertTrue(tight["buffer_downshifted"])
        roomy = tm.choose_buffer(24*tm.MIB, 512*tm.MIB, requested_bytes=16*tm.MIB)
        self.assertEqual(roomy["selected_buffer_bytes"], 16*tm.MIB)

    def test_unknown_job_allocation_uses_declared_fallback_not_host_or_slurm_memory(self):
        with patch.object(tm, "current_virtual_bytes", return_value=24*tm.MIB), \
             patch.object(tm.resource, "getrlimit", return_value=(-1,-1)), \
             patch.dict("os.environ", {"SLURM_JOB_ID":"test-only", "SLURM_MEM_PER_NODE":"999999999"}):
            plan = tm.process_plan()
        self.assertEqual(plan["effective_budget_bytes"], 128*tm.MIB)
        self.assertTrue(plan["fallback_used"])
        self.assertFalse(plan["slurm_cgroup_allocation_discovery_implemented"])

    def test_invalid_or_insufficient_budget_fails_without_data_skipping(self):
        with self.assertRaisesRegex(wa.ExperimentError, "insufficient.*no data skipped"):
            tm.choose_buffer(60*tm.MIB, explicit_bytes=64*tm.MIB)
        for kwargs in [{"explicit_bytes":0}, {"explicit_bytes":True}, {"address_space_limit":0},
                       {"requested_bytes":True}, {"requested_bytes":17*tm.MIB}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(wa.ExperimentError):
                tm.choose_buffer(24*tm.MIB, **kwargs)
        with self.assertRaises(wa.ExperimentError):
            tm.choose_buffer(0)

    def test_adaptive_profiles_keep_exact_witness_and_refuse_impossible_profile(self):
        coarse = {"query":"q", "query_length":10, "query_start":0, "query_end":10,
                  "target":"decoy", "target_length":10, "target_start":0, "target_end":10,
                  "strand":"+", "minimizers":5, "chain_score":100}
        parts = [{**coarse,"query_end":6,"target_end":6}, {**coarse,"query_start":6,"target_start":6}]
        raw = "QR\tq\t0\t10\n" + "".join(f"CN\t0\tdecoy\t{i}\t+\t{i}\t2\t0\n" for i in (1,3,5,7,9))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"trace";path.write_text(raw)
            reference = None
            with patch.object(tm, "current_virtual_bytes", return_value=24*tm.MIB), \
                 patch.object(tm.resource, "getrlimit", return_value=(-1,-1)):
                for mib in (40,64,128,512,4096,512000):
                    witness = audit.reconstruct_split_scores(path,[coarse],parts,
                                                             trace_budget=st.TraceBudget(process_memory_bytes=mib*tm.MIB))
                    plan = witness.pop("trace_resources")["memory_plan"]
                    self.assertEqual(plan["effective_budget_bytes"], mib*tm.MIB)
                    if reference is None:reference=witness
                    self.assertEqual(witness,reference)
                with self.assertRaisesRegex(wa.ExperimentError,"insufficient"):
                    audit.reconstruct_split_scores(path,[coarse],parts,
                                                   trace_budget=st.TraceBudget(process_memory_bytes=24*tm.MIB))
            self.assertEqual(path.read_text(),raw)
            self.assertEqual(list(Path(temp).iterdir()),[path])

    def test_process_memory_snapshot_must_be_measurable(self):
        self.assertGreater(tm.current_virtual_bytes(),0)
        with patch.object(Path,"open",side_effect=OSError("procfs unavailable")):
            with self.assertRaisesRegex(wa.ExperimentError,"cannot determine"):
                tm.current_virtual_bytes()


if __name__ == "__main__":
    unittest.main()
