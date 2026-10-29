from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import windowed_alignment as wa


def synthetic_hit(ops, strand="+", target="t"):
    qlen = sum(n for n, op in ops if op in wa.Q_OPS)
    tlen = sum(n for n, op in ops if op in wa.T_OPS)
    return wa.Hit("q", qlen, 0, qlen, strand, target, tlen, 0, tlen,
                  sum(n for n, op in ops if op == "="), sum(n for n, _ in ops), 60, tuple(ops))


def window(length, start, end, alias="w"):
    return wa.Window(alias, "q", length, 0, length, start, end)


def merge_ops(ops):
    merged = []
    for n, op in ops:
        if merged and merged[-1][1] == op:
            merged[-1] = (merged[-1][0] + n, op)
        else:
            merged.append((n, op))
    return tuple(merged)


class WindowGeometryTests(unittest.TestCase):
    def test_window_bounds_own_every_query_base_once(self):
        for length in (1, 10, 11, 19, 20, 21, 100):
            windows = wa.make_windows({"q": {"length": length}}, 10, 3)
            self.assertEqual(windows[0].core_start, 0)
            self.assertEqual(windows[-1].core_end, length)
            self.assertEqual(sum(w.core_end - w.core_start for w in windows), length)
            for i, w in enumerate(windows):
                self.assertTrue(0 <= w.start <= w.core_start < w.core_end <= w.end <= length)
                self.assertLessEqual(w.end - w.start, 16)
                if i:
                    self.assertEqual(windows[i-1].core_end, w.core_start)

    def test_invalid_sizes_and_boundary_limit(self):
        for core, context in ((0, 0), (10, -1), (10, 10), (wa.LIMIT, 1), (wa.LIMIT+1, 0)):
            with self.assertRaises(wa.ExperimentError):
                wa.make_windows({}, core, context)
        self.assertEqual(wa.make_windows({}, wa.LIMIT, 0), [])

    def test_liftover_uses_forward_query_coordinates_on_both_strands(self):
        w = wa.Window("alias", "q", 1000, 400, 500, 410, 490)
        for strand in "+-":
            hit = wa.Hit("alias", 100, 20, 80, strand, "t", 1000, 100, 160, 60, 60, 60, ((60, "="),))
            got = wa.lift(hit, w)
            self.assertEqual((got.query, got.qlen, got.qs, got.qe), ("q", 1000, 420, 480))
            self.assertEqual((got.ts, got.te, got.strand), (100, 160, strand))

    def test_reverse_core_clipping_advances_target_from_query_right(self):
        hit = synthetic_hit([(100, "=")], "-")
        got = wa.clip_to_core(hit, window(100, 10, 30))
        self.assertEqual((got.qs, got.qe, got.ts, got.te, got.ops), (10, 30, 70, 90, ((20, "="),)))

    def test_deletion_boundary_owned_exactly_once_on_both_strands(self):
        for strand in "+-":
            hit = synthetic_hit([(30, "="), (5, "D"), (30, "=")], strand)
            low = wa.clip_to_core(hit, window(60, 0, 30))
            high = wa.clip_to_core(hit, window(60, 30, 60))
            self.assertNotIn((5, "D"), low.ops)
            self.assertIn((5, "D"), high.ops)
            self.assertEqual(sum(h.te-h.ts for h in (low, high)), 65)
            ordered = sorted((low, high), key=lambda h: h.ts)
            self.assertEqual(ordered[0].te, ordered[1].ts)

    def test_insertion_split_and_insertion_only_core_is_not_silently_dropped(self):
        hit = synthetic_hit([(30, "="), (5, "I"), (30, "=")])
        left = wa.clip_to_core(hit, window(65, 0, 32))
        right = wa.clip_to_core(hit, window(65, 32, 65))
        self.assertEqual(left.ops, ((30, "="), (2, "I")))
        self.assertEqual(right.ops, ((3, "I"), (30, "=")))
        with self.assertRaisesRegex(wa.ExperimentError, "insertion-only"):
            wa.clip_to_core(hit, window(65, 30, 35))

    def test_context_only_alignment_returns_none(self):
        hit = wa.Hit("q", 100, 0, 20, "+", "t", 100, 0, 20, 20, 20, 60, ((20, "="),))
        self.assertIsNone(wa.clip_to_core(hit, window(100, 30, 60)))

    def test_every_cut_reconstructs_random_indel_paths_on_both_strands(self):
        rng = random.Random(1729)
        for _ in range(24):
            ops = merge_ops([(7, "=")] + [(rng.randint(1, 8), rng.choice("=XID")) for _ in range(9)] + [(7, "=")])
            for strand in "+-":
                hit = synthetic_hit(ops, strand)
                for cut in range(1, hit.qlen):
                    with self.subTest(strand=strand, cut=cut, ops=ops):
                        parts = [wa.clip_to_core(hit, window(hit.qlen, 0, cut)),
                                 wa.clip_to_core(hit, window(hit.qlen, cut, hit.qlen))]
                        ordered = sorted(parts, key=lambda part: part.ts)
                        self.assertEqual((ordered[0].ts, ordered[-1].te), (0, hit.tlen))
                        self.assertEqual(ordered[0].te, ordered[1].ts)
                        self.assertEqual(merge_ops([op for part in ordered for op in part.ops]), ops)
                        self.assertEqual(sum(part.qe-part.qs for part in parts), hit.qlen)


class FastaAndRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.stores = []

    def tearDown(self):
        for store in self.stores:
            store.close()
        self.temporary.cleanup()

    def store(self, name, content):
        source = self.root / (name + ".fa")
        source.write_bytes(content)
        store = wa.FastaStore(source, self.root / (name + ".bases"))
        self.stores.append(store)
        return store

    def test_wrapping_crlf_iupac_and_no_final_newline(self):
        store = self.store("query", b">q description\r\naCgT\r\nNNR\nA")
        self.assertEqual(store.records["q"]["length"], 8)
        self.assertEqual(store.fetch("q", 1, 8), b"CGTNNRA")
        self.assertTrue(store.unchanged())
        self.assertFalse((self.root / "query.fa.fai").exists())

    def test_long_unwrapped_line_is_bounded_and_not_mistaken_for_header(self):
        sequence = b"A" * (wa.CHUNK + 5)
        store = self.store("unwrapped", b">q\n" + sequence)
        self.assertEqual(store.records["q"]["length"], len(sequence))
        self.assertEqual(store.fetch("q", wa.CHUNK, wa.CHUNK+5), b"AAAAA")

    def test_invalid_duplicate_or_empty_input_fails_without_touching_source(self):
        for i, data in enumerate((b"", b">q\n", b"AAAA\n", b">q\nAC GT\n", b">q\nAC\n>q\nGT\n", b">\nAC\n", b">q\nA1\n")):
            source = self.root / f"bad{i}.fa"
            source.write_bytes(data)
            with self.assertRaises((wa.ExperimentError, UnicodeError)):
                wa.FastaStore(source, self.root / f"bad{i}.bases")
            self.assertEqual(source.read_bytes(), data)

    def test_input_mutation_detected(self):
        store = self.store("query", b">q\nAAAA\n")
        store.source.write_text(">q\nTTTT\n")
        self.assertFalse(store.unchanged())

    def test_stats_validate_cigar_and_ambiguity_on_reverse_strand(self):
        q = self.store("query", b">q\nACGTNR\n")
        t = self.store("target", b">t\nNNACGT\n")
        hit = synthetic_hit([(6, "=")], "-")
        self.assertEqual(wa.checked_statistics(hit, q, t), (4, 4, 2))
        wrong = wa.replace(hit, ops=((6, "X"),))
        with self.assertRaisesRegex(wa.ExperimentError, "X operation"):
            wa.checked_statistics(wrong, q, t)

    def test_parser_rejects_unknown_truncated_or_inconsistent_rows(self):
        valid = "w\t10\t0\t10\t+\tt\t10\t0\t10\t10\t10\t60\tcg:Z:10=\n"
        windows = {"w": window(10, 0, 10)}
        targets = {"t": {"length": 10}}
        self.assertEqual(wa.parse_hit(valid, windows, targets).qs, 0)
        for row in (valid.replace("10=", "10M"), valid.replace("10=", "0=10="), valid.replace("10=", "9="),
                    valid.replace("w\t", "unknown\t"), valid.replace("\tt\t", "\tunknown\t"), valid.rstrip()+"\tcg:Z:10=\n",
                    valid.replace("\t60\t", "\t256\t"), valid.replace("w\t10", "w\t11")):
            with self.assertRaises(wa.ExperimentError):
                wa.parse_hit(row, windows, targets)

    def test_overlap_ownership_dedup_preserves_alternative_placements(self):
        q = self.store("query", b">q\nAAAAAAAAAA\n")
        t = self.store("target", b">t\nAAAAAAAAAA\n>other\nAAAAAAAAAA\n")
        windows = wa.make_windows(q.records, 5, 2)
        raw = self.root / "raw.paf"
        rows = []
        for w in windows:
            n = w.end-w.start
            rows.append(f"{w.alias}\t{n}\t0\t{n}\t+\tt\t10\t{w.start}\t{w.end}\t{n}\t{n}\t60\tcg:Z:{n}=\tAS:i:123\ttp:A:P\n")
        raw.write_text("".join(rows) + rows[0] + rows[0].replace("\tt\t", "\tother\t"))
        output = self.root / "owned.paf"
        report = wa.recover(raw, output, self.root / "provenance.jsonl", windows, q, t)
        self.assertEqual((report["raw_rows"], report["owned_rows"], report["exact_duplicate_rows"]), (4, 3, 1))
        self.assertEqual(report["queries"]["q"]["covered_bases"], 10)
        self.assertEqual(report["targets"]["t"]["covered_bases"], 10)
        self.assertEqual(report["targets"]["other"]["covered_bases"], 5)
        text = output.read_text()
        self.assertNotIn("AS:i", text)
        self.assertNotIn("tp:A", text)
        self.assertEqual({row.split("\t")[11] for row in text.splitlines()}, {"255"})
        self.assertEqual(len((self.root / "provenance.jsonl").read_text().splitlines()), 4)

    def test_stitch_restores_indel_path_on_both_strands_without_double_counting(self):
        t = self.store("target", b">t\n" + b"A"*65 + b"\n")
        for strand in "+-":
            q = self.store("query" + strand, b">q\n" + (b"A" if strand == "+" else b"T")*60 + b"\n")
            hit = synthetic_hit([(30, "="), (5, "D"), (30, "=")], strand)
            windows = [window(60, 0, 30, "left"), window(60, 30, 60, "right")]
            source = self.root / ("owned" + strand + ".paf")
            with source.open("w") as handle:
                for w in windows:
                    part = wa.clip_to_core(hit, w)
                    matches, block, ambiguous = wa.checked_statistics(part, q, t)
                    handle.write(wa.paf_line(wa.replace(part, matches=matches, block=block), w, ambiguous))
            output = self.root / ("stitched" + strand + ".paf")
            report = wa.stitch_owned(source, output, self.root / ("joins"+strand+".jsonl"), windows, q, t)
            self.assertEqual((report["stitched_rows"], report["exact_joins"]), (1, 1))
            self.assertIn("cg:Z:30=5D30=", output.read_text())
            fields = output.read_text().split("\t")
            self.assertEqual(fields[2:9], ["0", "60", strand, "t", "65", "0", "65"])

    def test_stitch_never_bridges_target_gaps_or_ambiguous_connections(self):
        q = self.store("query", b">q\nAAAAAAAAAA\n")
        t = self.store("target", b">t\nAAAAAAAAAAAA\n")
        windows = [window(10, 0, 5, "left"), window(10, 5, 10, "right")]
        first = wa.Hit("q", 10, 0, 5, "+", "t", 12, 0, 5, 5, 5, 255, ((5, "="),))
        second = wa.Hit("q", 10, 5, 10, "+", "t", 12, 7, 12, 5, 5, 255, ((5, "="),))
        source = self.root / "gap.paf"
        source.write_text(wa.paf_line(first, windows[0], 0) + wa.paf_line(second, windows[1], 0))
        report = wa.stitch_owned(source, self.root / "gap.out", self.root / "gap.jsonl", windows, q, t)
        self.assertEqual(report["stitched_rows"], 2)
        # Two possible successors start at exactly the same endpoint: preserve all.
        second = wa.replace(second, ts=5, te=10)
        source = self.root / "fork.paf"
        source.write_text(wa.paf_line(first, windows[0], 0) + wa.paf_line(second, windows[1], 0)*2)
        report = wa.stitch_owned(source, self.root / "fork.out", self.root / "fork.jsonl", windows, q, t)
        self.assertEqual(report["stitched_rows"], 3)
        self.assertEqual(report["exact_joins"], 0)
        self.assertEqual(report["fork_endpoints_not_joined"], 1)

    def test_join_does_not_recreate_over_limit_encoded_operation(self):
        ops = wa.join_operations([(150000000, "="), (150000000, "=")])
        self.assertEqual(ops, ((wa.LIMIT, "="), (300000000-wa.LIMIT, "=")))
        self.assertEqual(sum(n for n, _ in ops), 300000000)
        self.assertTrue(all(n <= wa.LIMIT for n, _ in ops))

    def test_empty_corrupt_and_partial_paf_never_promoted(self):
        q = self.store("query", b">q\nAAAA\n")
        t = self.store("target", b">t\nAAAA\n")
        windows = [window(4, 0, 4)]
        valid = "w\t4\t0\t4\t+\tt\t4\t0\t4\t4\t4\t60\tcg:Z:4=\n"
        for i, text in enumerate(("", valid[:-1], valid.replace("4=", "4X"), valid.replace("4\t4\t60", "3\t4\t60"))):
            raw = self.root / f"raw{i}.paf"
            raw.write_text(text)
            out = self.root / f"out{i}.paf"
            with self.assertRaises(wa.ExperimentError):
                wa.recover(raw, out, self.root / f"audit{i}.jsonl", windows, q, t)
            self.assertFalse(out.exists())
            self.assertEqual(raw.read_text(), text)

    def test_coverage_failure_retains_pending_evidence_but_no_final_candidate(self):
        target = self.root / "t.fa"
        query = self.root / "q.fa"
        target.write_text(">t\nAAAAAAAA\n")
        query.write_text(">q\nAAAAAAAA\n")
        binary = self.root / "fake-minimap2"
        binary.write_text(f"#!{sys.executable}\n" +
                         "import sys\nfrom pathlib import Path\na=sys.argv\n"
                         "if '--version' in a: print('fixture'); sys.exit(0)\n"
                         "if '-d' in a:\n Path(a[a.index('-d')+1]).write_text('index')\n print('distinct minimizers:',file=sys.stderr)\n sys.exit(0)\n"
                         "Path(a[a.index('-o')+1]).write_text('gpm_window_00000000\\t8\\t0\\t4\\t+\\tt\\t8\\t0\\t4\\t4\\t4\\t60\\tcg:Z:4=\\n')\n")
        binary.chmod(0o755)
        out = self.root / "coverage_failure"
        args = argparse.Namespace(target=target, query=query, out=out, minimap2=str(binary), preset="asm10",
                                  core_bases=10, context_bases=1, threads=1, timeout=5, memory_gib=1,
                                  require_full_query_coverage=True)
        with self.assertRaisesRegex(wa.ExperimentError, "full-query-coverage"):
            wa.experiment(args)
        report = json.loads((out / "experiment.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertFalse((out / "owned.experimental.paf").exists())
        self.assertFalse((out / "stitched.experimental.paf").exists())
        self.assertTrue((out / "owned.pending.paf").exists())
        self.assertTrue((out / "raw.windows.paf").exists())
        self.assertEqual(query.read_text(), ">q\nAAAAAAAA\n")
        self.assertEqual(target.read_text(), ">t\nAAAAAAAA\n")

    def test_relation_comparison_ignores_only_fragmentation_not_changed_paths(self):
        from compare_small_fixtures import relation_signature
        baseline = self.root / "baseline.paf"
        split = self.root / "split.paf"
        changed = self.root / "changed.paf"
        baseline.write_text("q\t10\t0\t10\t+\tt\t12\t0\t12\t10\t12\t60\tcg:Z:5=2D5=\n")
        split.write_text("q\t10\t0\t5\t+\tt\t12\t0\t5\t5\t5\t255\tcg:Z:5=\n"
                         "q\t10\t5\t10\t+\tt\t12\t5\t12\t5\t7\t255\tcg:Z:2D5=\n")
        self.assertEqual(relation_signature(baseline), relation_signature(split))
        # Same coverage and lengths, but deletion moved by one base: must differ.
        changed.write_text(baseline.read_text().replace("5=2D5=", "4=2D6="))
        self.assertNotEqual(relation_signature(baseline), relation_signature(changed))
        changed.write_text(baseline.read_text().replace("\tt\t", "\tother\t"))
        self.assertNotEqual(relation_signature(baseline), relation_signature(changed))

    def test_child_failure_preserves_logs_and_command_without_retry(self):
        with self.assertRaisesRegex(wa.ExperimentError, "failed"):
            wa.run_command([sys.executable, "-c", "import sys; print('partial'); print('assertion',file=sys.stderr); sys.exit(134)"], self.root, "failure", 5, 1)
        result = json.loads((self.root / "failure.execution.json").read_text())
        self.assertEqual(result["returncode"], 134)
        self.assertEqual((self.root / "failure.stdout").read_text(), "partial\n")
        self.assertEqual((self.root / "failure.stderr").read_text(), "assertion\n")

    def test_child_timeout_stops_instead_of_publishing_success(self):
        with self.assertRaises(wa.ExperimentError):
            wa.run_command([sys.executable, "-c", "import time; time.sleep(30)"], self.root, "timeout", 1, 1)
        report = json.loads((self.root / "timeout.execution.json").read_text())
        self.assertEqual(report["interrupted"], "TimeoutExpired")
        self.assertNotEqual(report["returncode"], 0)


@unittest.skipUnless(shutil.which("minimap2"), "real minimap2 required for bounded smoke checks")
class RealMinimapTests(unittest.TestCase):
    def test_small_plus_and_reverse_runs_keep_full_coverage(self):
        rng = random.Random(29102026)
        sequence = bytes(rng.choice(b"ACGT") for _ in range(120000))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.fa"
            target.write_bytes(b">target\n" + sequence + b"\n")
            for strand, bases in (("+", sequence), ("-", sequence.translate(wa.RC)[::-1])):
                query = root / ("query" + strand + ".fa")
                query.write_bytes(b">query\n" + bases + b"\n")
                out = root / ("run" + strand)
                args = argparse.Namespace(target=target, query=query, out=out, minimap2="minimap2", preset="asm10",
                                          core_bases=30000, context_bases=3000, threads=1, timeout=30, memory_gib=2,
                                          require_full_query_coverage=True)
                result = wa.experiment(args)
                self.assertEqual(result["status"], "validated_experimental_candidate")
                self.assertFalse(result["production_ready"])
                self.assertEqual(result["coverage"]["queries"]["query"]["covered_bases"], 120000)
                self.assertEqual(result["coverage"]["targets"]["target"]["covered_bases"], 120000)
                self.assertEqual(result["coverage"]["owned_rows"], 4)
                self.assertEqual(result["stitching"]["stitched_rows"], 1)
                self.assertEqual(result["stitching"]["exact_joins"], 3)
                fields = [row.split("\t") for row in (out / "owned.experimental.paf").read_text().splitlines()]
                self.assertEqual({row[4] for row in fields}, {strand})
                self.assertTrue(all(row[0] == "query" and int(row[1]) == 120000 for row in fields))
                # A new experiment must never replace an existing one.
                with self.assertRaises(FileExistsError):
                    wa.experiment(args)


if __name__ == "__main__":
    unittest.main()
