"""Exact old/new profile parity, bounded spill and prepared native integration."""
from collections import defaultdict
from pathlib import Path
import os
import random
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

import adaptive_screening as policy

# Frozen in-memory oracle from aeaad58; do not call the new parser/aggregator.
record_lengths = policy.record_lengths
union_length = policy.union_length

def legacy_profile(path, records):
    """Read only a separately validated PAF; retain competing target coverage.

    Reject oversized audit inputs rather than silently truncate them. MAPQ is
    not used as a stand-alone confidence signal for multipart reference mapping.
    """
    if path.stat().st_size > 64 * 1024**2:
        raise ValueError("audit PAF exceeds 64 MiB; no automatic recommendation")
    lengths = record_lengths(records)
    spans, targets = defaultdict(list), defaultdict(lambda: defaultdict(list))
    target_strands = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    qualified = defaultdict(lambda: defaultdict(lambda: {"spans": [], "anchors": [], "anchors_by_strand": {"+": [], "-": []}, "weights": {"+": 0, "-": 0}}))
    with path.open() as stream:
        for line in stream:
            f = line.rstrip("\n").split("\t")
            if len(f) < 12 or f[0] not in lengths or int(f[1]) != lengths[f[0]]:
                raise ValueError("PAF query identity mismatch")
            start, end = int(f[2]), int(f[3])
            if f[4] not in ("+", "-") or not 0 <= start < end <= lengths[f[0]]:
                raise ValueError("PAF query range invalid")
            spans[f[0]].append((start, end))
            targets[f[0]][f[5]].append((start, end))
            target_strands[f[0]][f[5]][f[4]].append((start, end))
            block = int(f[10])
            # Match assign_chr_groups.py: small hits must cover >=25% of the
            # query; otherwise the block must be >=1000 bp. Every qualifying
            # chromosome can be assigned, not just the best-scoring target.
            if block >= 1000 or block * 4 >= lengths[f[0]]:
                bucket = qualified[f[0]][f[5]]
                bucket["spans"].append((start, end))
                anchor = int(f[7]) - start + 1 if f[4] == "+" else int(f[7]) + 1 - lengths[f[0]] + end
                bucket["anchors"].append((anchor, block))
                bucket["anchors_by_strand"][f[4]].append((anchor, block))
                bucket["weights"][f[4]] += block
    return {q: {"length": n, "covered": union_length(spans[q]),
                "targets": {t: union_length(s) for t, s in sorted(targets[q].items())},
                "target_strands": {t: {strand: union_length(s) for strand, s in sorted(by_strand.items())}
                                   for t, by_strand in sorted(target_strands[q].items())},
                "assignment_candidates": {t: {"covered": union_length(b["spans"]),
                    "strand_weights": b["weights"], "anchor_start": weighted_anchor(b["anchors"]),
                    "anchor_spans": {strand: weighted_anchor_span(values) for strand, values in b["anchors_by_strand"].items() if values}}
                    for t, b in sorted(qualified[q].items())}}
            for q, n in lengths.items()}


def weighted_anchor(values):
    threshold = sum(w for _, w in values) // 2 + 1
    cumulative = 0
    for position, weight in sorted(values):
        cumulative += weight
        if cumulative >= threshold:
            return position
    raise ValueError("positive anchor weights required")


def weighted_anchor_span(values):
    """10th/90th block-weighted anchor quantiles; not a native chain proof."""
    total = sum(w for _, w in values)
    if total <= 0:raise ValueError("positive anchor weights required")
    low = high = None; cumulative = 0
    for position, weight in sorted(values):
        cumulative += weight
        if low is None and cumulative * 10 >= total:low = position
        if cumulative * 10 >= total * 9:
            high = position; break
    return [low, high]


class DiskProfileTests(unittest.TestCase):
    def fixture(self, root, count=2500):
        rng=random.Random(240117)
        records=[{"name":"q"+str(i),"length":10000+i*100} for i in range(7)]
        records.append({"name":"no_hits","length":30})
        lines=[]
        for i in range(count):
            record=rng.choice(records[:-1]); q=record["name"]; n=record["length"]
            start=rng.randrange(n); end=rng.randrange(start+1,n+1)
            strand=rng.choice(["+","-"]); target=rng.choice(["chr1","chr10","chr2","chrX"])
            tstart=rng.randrange(20000); block=end-start
            lines.append(f"{q}\t{n}\t{start}\t{end}\t{strand}\t{target}\t50000\t{tstart}\t{tstart+block}\t{block}\t{block}\t255\tcg:Z:{block}M" + ("\r\n" if i%3==0 else "\n"))
        path=root/"source.paf"; path.write_bytes("".join(lines).rstrip("\r\n").encode())
        return path, records

    def test_exact_old_memory_and_disk_parity_with_all_rows_and_no_hits(self):
        with tempfile.TemporaryDirectory() as directory:
            path,records=self.fixture(Path(directory)); before=path.read_bytes()
            expected=legacy_profile(path,records)
            self.assertEqual(policy.coverage_profile(path,records),expected)
            with patch.object(policy,"IN_MEMORY_PROFILE_BYTES",0):
                actual=policy.coverage_profile(path,records)
            self.assertEqual(actual,expected)
            self.assertEqual(path.read_bytes(),before)
            for coverage in (0,.60,.80,1):
                limits=policy.assignment_limits(coverage)
                self.assertEqual(policy.screen_candidate_projection(actual,limits),
                                 policy.screen_candidate_projection(expected,limits))
                self.assertEqual(policy.assess_loss(expected,actual,limits),
                                 policy.assess_loss(expected,expected,limits))

    def test_empty_spill_preserves_all_no_hit_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"empty.paf";path.touch()
            records=[{"name":"zero","length":100}]
            self.assertEqual(policy._coverage_profile_disk(path,{"zero":100}),legacy_profile(path,records))

    def test_large_optional_tags_do_not_require_large_python_row_buffers(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"large.paf"
            # >64 MiB total; individual rows stay below the native validator line cap.
            fields=b"q\t10000\t0\t10000\t+\tchr1\t10000\t0\t10000\t10000\t10000\t60"
            with path.open("wb") as stream:
                for _ in range(65):stream.write(fields+b"\tcg:Z:10000M\tzz:Z:"+b"x"*(1024**2)+b"\n")
                stream.write(fields)
            small=Path(directory)/"small.paf";small.write_bytes((fields+b"\n")*65+fields)
            records=[{"name":"q","length":10000}]
            expected=legacy_profile(small,records)
            tracemalloc.start()
            try:
                with patch.object(policy,"_coverage_profile_disk",wraps=policy._coverage_profile_disk) as spill:
                    actual=policy.coverage_profile(path,records)
                _,peak=tracemalloc.get_traced_memory()
            finally:tracemalloc.stop()
            self.assertEqual(spill.call_count,1)
            self.assertEqual(actual,expected)
            self.assertLess(peak,4*1024**2)  # Python allocations; not a SQLite/RSS claim.

    def test_spill_rejects_bad_rows_and_cleans_only_its_own_scratch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path,records=self.fixture(root,count=2)
            scratch=root/"scratch";scratch.mkdir();(scratch/"keep").write_text("unrelated")
            original=policy.tempfile.TemporaryDirectory
            def temp(*args,**kwargs):return original(*args,dir=scratch,**kwargs)
            with patch.object(policy.tempfile,"TemporaryDirectory",side_effect=temp), patch.object(policy,"IN_MEMORY_PROFILE_BYTES",0):
                policy.coverage_profile(path,records)
                for invalid in (b"bad\n",b"unknown\t10000\t0\t10\t+\tchr1\t10000\t0\t10\t10\t10\t60\n",
                                b"q0\t10000\t9\t8\t+\tchr1\t10000\t0\t10\t10\t10\t60\n"):
                    path.write_bytes(invalid)
                    with self.assertRaises(ValueError):policy.coverage_profile(path,records)
                    self.assertEqual(list(scratch.iterdir()),[scratch/"keep"])
            self.assertEqual((scratch/"keep").read_text(),"unrelated")

    def test_mandatory_columns_may_cross_read_chunk_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"wide.paf"; name="q"*70000
            line=f"{name}\t1000\t0\t1000\t-\tchr1\t2000\t0\t1000\t1000\t1000\t60\tcg:Z:1000M"
            path.write_text(line); records=[{"name":name,"length":1000}]
            expected=legacy_profile(path,records)
            with patch.object(policy,"IN_MEMORY_PROFILE_BYTES",0):
                self.assertEqual(policy.coverage_profile(path,records),expected)


if __name__ == "__main__":unittest.main()
