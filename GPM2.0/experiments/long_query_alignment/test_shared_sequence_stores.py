"""Ownership, mutation and allocation regressions for sequential store reuse."""
import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import guided_alignment as ga
import windowed_alignment as wa


class SharedStoresTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.t = self.root / "t.fa"
        self.q = self.root / "q.fa"
        self.t.write_bytes(b">t\nACGTN\n")
        self.q.write_bytes(b">q\nACGTA\n")

    def test_borrow_preserves_handles_and_never_copies(self):
        with wa.sequence_stores(self.t, self.q, self.root) as stores:
            target, query = stores
            nested = self.root / "nested"
            nested.mkdir()
            with wa.sequence_stores(self.t, self.q, nested, shared_target=target, shared_query=query) as borrowed:
                self.assertEqual(borrowed, stores)
                self.assertEqual(query.fetch("q", 1, 4), b"CGT")
            self.assertEqual(list(nested.iterdir()), [])
            self.assertFalse(target.handle.closed)
            self.assertFalse(query.handle.closed)
        self.assertTrue(target.handle.closed)
        self.assertTrue(query.handle.closed)

    def test_mixed_ownership_failure_only_closes_new_store(self):
        with wa.sequence_stores(self.t, self.q, self.root) as stores:
            nested = self.root / "nested"
            nested.mkdir()
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                with wa.sequence_stores(self.t, self.q, nested, shared_target=stores[0]) as mixed:
                    raise RuntimeError("cancelled")
            self.assertFalse(stores[0].handle.closed)
            self.assertTrue(mixed[1].handle.closed)

    def test_wrong_source_closed_and_mutated_source_are_refused(self):
        with wa.sequence_stores(self.t, self.q, self.root) as stores:
            with self.assertRaises(wa.ExperimentError):
                stores[0].check_binding(self.q)
            self.t.write_bytes(b">t\nTCGTN\n")
            self.assertFalse(stores[0].unchanged())
            with self.assertRaises(wa.ExperimentError):
                stores[0].check_binding(self.t)
        with self.assertRaises(wa.ExperimentError):
            stores[1].check_binding(self.q)

    def test_spool_edit_is_detected_even_same_size(self):
        with wa.sequence_stores(self.t, self.q, self.root) as stores:
            stores[0].spool.write_bytes(b"TCGTN")
            self.assertFalse(stores[0].unchanged())
            with self.assertRaises(wa.ExperimentError):
                stores[0].check_binding(self.t)

    def test_spool_replacement_is_detected(self):
        with wa.sequence_stores(self.t, self.q, self.root) as stores:
            replacement = self.root / "replacement"
            replacement.write_bytes(b"ACGTN")
            replacement.replace(stores[0].spool)
            self.assertFalse(stores[0].unchanged())

    def test_failed_second_input_closes_first(self):
        self.q.write_bytes(b"invalid\n")
        real = wa.FastaStore
        made = []
        def create(source, spool):
            store = real(source, spool)
            made.append(store)
            return store
        with patch.object(wa, "FastaStore", side_effect=create):
            with self.assertRaises(wa.ExperimentError):
                with wa.sequence_stores(self.t, self.q, self.root):
                    self.fail("invalid query accepted")
        self.assertEqual(len(made), 1)
        self.assertTrue(made[0].handle.closed)

    def test_guided_owns_once_and_window_receives_same_stores_on_failure(self):
        args = argparse.Namespace(target=self.t, query=self.q, out=self.root / "guided",
                                  guide_slack=0, context_bases=2, preset="asm10")
        observed = []
        def window(options, *, shared_target, shared_query):
            observed.extend((shared_target, shared_query))
            self.assertEqual(shared_target.fetch("t", 0, 5), b"ACGTN")
            self.assertEqual(shared_query.fetch("q", 0, 5), b"ACGTA")
            self.assertFalse(options.out.exists())
            raise wa.ExperimentError("injected window failure")
        with patch.object(wa, "experiment", side_effect=window):
            with self.assertRaisesRegex(wa.ExperimentError, "injected window failure"):
                ga.experiment(args)
        self.assertEqual(len(list(args.out.glob("*.bases"))), 2)
        self.assertTrue(all(s.handle.closed for s in observed))
        self.assertFalse((args.out / "guided.experimental.paf").exists())


if __name__ == "__main__":
    unittest.main()
