"""Scheduling/cache changes must preserve exact grids, source bytes and admission fields."""
import os
import pickle
import random
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server.tests.test_q0_admission import EvidenceFixture, dna
from server.tools.lgz_core import q0_admission as adm, q0_pair_lanes as lanes
from server.tools.lgz_core import q0_pair_transport as transport
from server.tools.lgz_core.q0_paths import PathPolicy, PairLink
from server.tools.lgz_core.q0_sources import Interval, SourceKey
from server.tools.lgz_core.q0_retained_hits import RetainedHit


class ExactCacheTests(unittest.TestCase):
    def test_origins_short_tails_masks_eviction_and_extension(self):
        source = SourceKey("d", "s")
        sequence = dna(2600) + "A"*1100 + dna(1700, 37) + "nacgt"*80
        policy = adm.AdmissionPolicy()
        cache = adm._ComplexityCache(policy)
        cache.MAX_BLOCKS = 2; cache.MAX_SHORT = 2; cache.BLOCK_WINDOWS = 4
        rng = random.Random(91)
        spans = [Interval(i, min(i+207, len(sequence))) for i in range(100)]
        spans += [Interval(a, rng.randrange(a+1, len(sequence)+1)) for a in
                  (rng.randrange(len(sequence)) for _ in range(130))]
        for span in spans + spans[::-1]:
            self.assertEqual(cache.intervals(sequence, source, span), adm._complex_intervals(sequence, span, policy))
        masks = {source: (Interval(2571, 2617), Interval(3902, 4001))}
        ctx = adm._RootedContext(lambda *_: sequence, masks, policy)
        for spans in ([Interval(0, len(sequence))], [Interval(31, 4999)], [Interval(0, len(sequence))]):
            self.assertEqual(ctx.clean(source, Interval(0,len(sequence)), spans),
                             adm._clean_source_intervals(sequence, masks[source], spans, policy))
        ctx.clear(keep_complexity=True)
        misses = ctx.complexity.misses
        ctx.clean(source, Interval(0,len(sequence)), [Interval(0,len(sequence))])
        self.assertEqual(ctx.complexity.misses, misses)
        self.assertGreater(ctx.complexity.hits, 0)

    def test_large_fragmented_anchor_is_cached_losslessly(self):
        source = SourceKey("d", "s"); span = Interval(0, 30_000_000)
        anchor = SimpleNamespace(source=source, interval=span)
        ctx = adm._RootedContext(lambda *_: None, {}, adm.AdmissionPolicy())
        rows = tuple(Interval(200*i,200*i+100) for i in range(140_000))
        with patch.object(ctx, "_full", return_value=rows) as screen:
            self.assertEqual(tuple(ctx(anchor, [span])), rows)
            self.assertEqual(tuple(ctx(anchor, [span])), rows)
        self.assertEqual(screen.call_count, 1)
        self.assertEqual(ctx.cached_bytes, len(rows)*16)
        self.assertEqual(ctx._tile.cache_info().maxsize, 65536)
        self.assertEqual(ctx.whole[source,span][-1], rows[-1])


class SharedDNATests(unittest.TestCase):
    def tearDown(self):
        transport._READS.clear(); transport._OBJECTS.clear()

    def test_exact_case_original_coordinates_and_cross_block_access(self):
        source = SourceKey("d", "s"); sequence = "aCGTn"*120000
        store = transport.SequenceStore({source: sequence}, {})
        try:
            region = store.region(source, Interval(91, len(sequence)-7))
            self.assertEqual(len(region), len(sequence))
            for start,end in [(91,92),(262140,262160),(91,599993)]:
                self.assertEqual(region[start:end], sequence[start:end])
            for key in (slice(90,100), slice(91,len(sequence)), slice(100,99), slice(91,100,2), 10):
                with self.assertRaises(ValueError): region[key]
            self.assertLess(len(pickle.dumps(region)), 1024)
            self.assertEqual(store.written_bytes,len(sequence))
            self.assertEqual(store.region(source, Interval(100,200))[100:200], sequence[100:200])
        finally: store.close()
        self.assertFalse(store.root.exists())

    def test_mutation_fails_closed_on_read_and_completion(self):
        source = SourceKey("d", "s"); store = transport.SequenceStore({source:"A"*900000},{})
        region = store.region(source, Interval(0,900000))
        self.assertEqual(region[0:100],"A"*100)
        os.chmod(region.path,0o600)
        with open(region.path,"r+b") as out: out.write(b"T")
        with self.assertRaisesRegex(ValueError,"changed"): region[400000:400010]
        with self.assertRaisesRegex(ValueError,"changed"): store.close()
        self.assertFalse(store.root.exists())

    def test_shared_metadata_is_exact_bounded_and_owner_sealed(self):
        source=SourceKey("d","s"); store=transport.SequenceStore({source:"ACGT"},{})
        value={source:(Interval(1,3),)}
        try:
            ref=store.metadata(("mask",source),value)
            self.assertEqual(ref.load(),value)
            self.assertIs(store.metadata(("mask",source),value),ref)
            with patch.object(transport._BoundedFile,"LIMIT",2):
                self.assertIsNone(store.metadata(("mask","oversize"),value))
            os.chmod(ref.path,0o600)
            with self.assertRaisesRegex(ValueError,"metadata changed"):store.verify()
            # Put the original owner seal back only for controlled cleanup.
        finally:
            with self.assertRaises(ValueError):store.close()

    def test_capacity_io_and_non_ascii_use_owner_fallback(self):
        source=SourceKey("d","s")
        for sequence,error in [("ACG",OSError("unavailable")),("ACG",None),("AéG",False)]:
            store=transport.SequenceStore({source:sequence},{})
            try:
                if error is False:
                    self.assertIsNone(store.region(source,Interval(0,3)))
                else:
                    with patch.object(transport.shutil,"disk_usage",side_effect=error,
                                      return_value=SimpleNamespace(free=0)):
                        self.assertIsNone(store.region(source,Interval(0,3)))
                self.assertFalse(store.rows)
                self.assertEqual(store.written_bytes,0)
            finally: store.close()


class PairSchedulingTests(unittest.TestCase):
    def test_order_and_round_completion_without_pool_or_store(self):
        from unittest.mock import Mock
        keys = [13, 2, 8] * 20
        data = SimpleNamespace(parts={k: SimpleNamespace(source=k) for k in keys})
        neighbors = Mock(); neighbors.for_source.side_effect = lambda key: [key]
        calls = []; logs = []
        def owner(key, linked):
            calls.append((key, linked)); return key, 0, 0, 0, 0, 0
        with patch("concurrent.futures.ProcessPoolExecutor", side_effect=AssertionError), \
             patch.object(transport, "SequenceStore", side_effect=AssertionError):
            result = list(lanes.ordered_deltas(keys, data, {}, {}, neighbors, None, None,
                                               32, owner, logs.append, 1, time_phases=True))
        self.assertEqual(result, list(zip(keys, keys)))
        self.assertEqual(calls, [(key, [key]) for key in keys]); self.assertEqual(neighbors.for_source.call_count,len(keys))
        self.assertIn("owner_parts=60 worker_parts=0", logs[-1])

    def test_all_admission_fields_independent_of_thread_budget(self):
        f=EvidenceFixture();seq=dna(6000);root=f.source("root",seq);f.ref(root,(0,3000),(0,3000))
        for i in range(20):
            child=f.source("child%02d"%i,seq[3000:5000])
            f.pair(child,root,(0,2000),(3000,5000))
        data=f.data();data=replace(data,pair_links=tuple(PairLink(RetainedHit.from_validated(l.hit,l.hit.query_name,l.hit.target_name),l.query_source,l.target_source) for l in data.pair_links))
        baseline = adm.admit_placements(data); logs = []
        self.assertEqual(adm.admit_placements(data, screen_threads=32, screen_progress=logs.append), baseline)
        self.assertTrue(any("lanes=1 mode=owner_only" in row for row in logs))
