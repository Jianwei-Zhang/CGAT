"""Parallel placement screens are a scheduling decision, never a new source of evidence."""
from concurrent.futures import Future
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from dataclasses import replace
from unittest.mock import patch

from server.tests.test_q0_admission import bridge_fixture, dna
from server.tools.lgz_core import q0_admission as adm, q0_source_screen as lanes
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError
from server.tools.lgz_core.q0_threshold_questions import questions


class ScreenTests(unittest.TestCase):
    def test_work_gate_and_budget(self):
        seq = "A" * 2_000_000
        parts = [(i, SimpleNamespace(source=i, interval=Interval(0, len(seq)))) for i in range(8)]
        hits = [SimpleNamespace(query=parts[0][1].interval)]
        data = SimpleNamespace(sources=dict.fromkeys(range(8), seq), reference_hits=dict.fromkeys(range(8), hits))
        allowed = set(range(8))
        with patch.object(lanes.resources, "execution_memory_limit", return_value=40*1024*lanes.MIB) as bound:
            self.assertEqual(lanes._lanes(data, parts, allowed, 1), 1)
            self.assertEqual(lanes._lanes(data, parts, allowed-{4}, 32), 1)
            bound.assert_not_called()
            if lanes.resources.resource and lanes.sys.platform.startswith("linux"):
                self.assertEqual(lanes._lanes(data, parts, allowed, 32), 8)
                self.assertEqual(lanes._lanes(data, parts, allowed, 2), 2)
                for n in (None, lanes.MIB):
                    bound.return_value = n
                    self.assertEqual(lanes._lanes(data, parts, allowed, 32), 1)
        self.assertEqual(lanes._weight(data, SimpleNamespace(source=0, interval=Interval(0, 900_000))), 0)
        data.reference_hits[0] = [SimpleNamespace(query=Interval(1_500_000, 2_000_000))]
        self.assertEqual(lanes._weight(data, SimpleNamespace(source=0, interval=Interval(0, 1_000_000))), 0)

    def mixed(self):
        f, _ = bridge_fixture(reverse=True)
        for i in range(8):
            source = f.source(f"s{i}", dna(600, seed=i) + "N"*100 + dna(600, seed=8+i))
            f.ref(source, (0, 500), (1500, 2000)); f.ref(source, (75, 450), (3000, 3375), strand="-")
            f.ref(source, (725, 1125), (2600, 3000))
        data = f.data()
        for source, hits in data.reference_hits.items():
            data.reference_hits[source] = [lanes.RetainedHit.from_validated(h, h.query_name, h.target_name) for h in hits]
        return data

    def compare(self, data, qc, *patches):
        logs = []
        baseline = adm.select_q0_paths(data, quality_pass=qc)
        with ExitStack() as stack:
            for item in patches: stack.enter_context(item)
            stack.enter_context(patch.object(lanes, "_lanes", return_value=3))
            stack.enter_context(patch.object(lanes, "_weight", return_value=1))
            result = adm.select_q0_paths(data, quality_pass=qc, screen_threads=3, progress=logs.append)
        self.assertEqual(result, baseline)
        self.assertEqual(questions(data, result, []), questions(data, baseline, []))
        return int(next(s for s in logs if "screen complete" in s).rsplit("=", 1)[1])

    @unittest.skipUnless(lanes.resources.resource, "requires worker AS limit")
    def test_real_spawn_preserves_every_selection_and_question(self):
        data = self.mixed(); qc = {s: s.contig != "s4" for s in data.sources}
        self.assertGreater(self.compare(data, qc), 0)

    def test_pool_unavailable_or_bounded_transfer_replans_exactly(self):
        data = self.mixed()
        self.assertEqual(self.compare(data, None, patch.object(lanes, "ProcessPoolExecutor", side_effect=OSError())), 0)
        self.assertEqual(self.compare(data, None, patch.object(lanes, "WIRE_LIMIT", 12)), 0)
        with patch.object(lanes, "WIRE_LIMIT", 12):
            self.assertIsNone(lanes._pack(b"x"*1000))

    def test_oversized_optional_fields_and_unpacked_fallback_stay_in_owner(self):
        data = self.mixed(); part = next(p for p in data.parts.values() if data.reference_hits.get(p.source))
        hit = data.reference_hits[part.source][0]
        with patch.object(lanes, 'WIRE_LIMIT', 8192), patch.object(lanes, '_pack', side_effect=AssertionError('encoded oversized input')):
            for unusual in (replace(hit, _optional_fields='x'*8193), replace(hit, _packed=((500,'M'),))):
                data.reference_hits[part.source] = [unusual]
                self.assertIsNone(lanes._packet(data, part, adm.AdmissionPolicy()))

    def test_broken_worker_replans_but_scientific_error_propagates(self):
        data = self.mixed()
        def failing(error):
            fut = Future(); fut.set_exception(error)
            return patch.object(lanes, "ProcessPoolExecutor", return_value=SimpleNamespace(
                submit=lambda *args: fut, shutdown=lambda **kwargs: None))
        self.assertEqual(self.compare(data, None, failing(lanes.BrokenProcessPool())), 0)
        with self.assertRaisesRegex(Q0EvidenceError, "invalid evidence"):
            self.compare(data, None, failing(Q0EvidenceError("invalid evidence")))
