"""Lossless threshold short-circuits: compare with the exhaustive definitions."""
from collections import Counter
from dataclasses import replace
from itertools import permutations
import math
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from server.tools.lgz_core import q0_admission as a
from server.tools.lgz_core.q0_sources import Interval, merged_intervals, subtract_intervals


def exhaustive(seq, span, policy):
    passing = []
    for start in range(span.start, span.end, policy.minimum_anchor_bp):
        end = min(start + policy.minimum_anchor_bp, span.end)
        text = seq[start:end].upper()
        if len(text) < min(policy.kmer_size, len(seq)) or set(text) - set("ACGT"):
            continue
        entropy = -sum((n/len(text))*math.log2(n/len(text)) for n in Counter(text).values())
        k = min(len(text), policy.kmer_size)
        words = [text[i:i+k] for i in range(len(text)-k+1)]
        if entropy >= policy.minimum_base_entropy and len(set(words))/len(words) >= policy.minimum_distinct_kmer_fraction:
            passing.append(Interval(start, end))
    return merged_intervals(passing)


class AdmissionScreenTests(unittest.TestCase):
    def test_exact_grid_endpoints_and_custom_thresholds(self):
        rng = random.Random(35)
        for stride in (1, 7, 100, 256, 257, 501):
            for k in (1, 3, 15, 255, 600):
                seq = ("AaGT"*130 + "".join(rng.choices("ACGT", k=503)) + "R"*17 + "A"*300)
                for fraction in (.01, .5, 1.0):
                    p = replace(a.AdmissionPolicy(), minimum_anchor_bp=stride, kmer_size=k,
                                minimum_base_entropy=rng.choice([0., 1.2, 2.]), minimum_distinct_kmer_fraction=fraction)
                    span = Interval(3, len(seq)-1)
                    self.assertEqual(a._complex_intervals(seq, span, p), exhaustive(seq, span, p))
        for seq in ("a", "AAA", "NG", "acgt", "TGCA"*25):
            p = a.AdmissionPolicy(); span = Interval(0, len(seq))
            self.assertEqual(a._complex_intervals(seq, span, p), exhaustive(seq, span, p))

    def test_exact_fraction_and_entropy_at_equality_and_either_side(self):
        for n in (79, 256, 257):
            seq = ("TGTGAC"*50)[:n]; k = 3
            frac = len({seq[i:i+k] for i in range(n-k+1)}) / (n-k+1)
            entropy = -sum((v/n)*math.log2(v/n) for v in Counter(seq).values())
            for f in (math.nextafter(frac, 0), frac, math.nextafter(frac, 1)):
                for h in (math.nextafter(entropy, 0), entropy, math.nextafter(entropy, 2)):
                    policy = replace(a.AdmissionPolicy(), kmer_size=k, minimum_distinct_kmer_fraction=f,
                                     minimum_base_entropy=h, minimum_anchor_bp=n)
                    span = Interval(0, n)
                    self.assertEqual(a._complex_intervals(seq, span, policy), exhaustive(seq, span, policy))

    def test_native_histogram_preserves_first_occurrence_order_and_invalid_bases(self):
        for n in (63, 64, 100, 256, 257):
            counts = (1, 3, n//4, n - 4 - n//4)
            for order in permutations(range(4)):
                seq = ''.join('ACGT'[i] * counts[i] for i in order)
                entropy = -sum((v/n)*math.log2(v/n) for v in Counter(seq).values())
                for bound in (math.nextafter(entropy, 0), entropy, math.nextafter(entropy, 2)):
                    p = replace(a.AdmissionPolicy(), minimum_base_entropy=bound,
                                kmer_size=1, minimum_distinct_kmer_fraction=.001)
                    self.assertEqual(a._passes_complexity(seq, p), entropy >= bound)
            for text in ('A'*n, ('CA'*n)[:n], 'G'*(n-1)+'N', 'G'*(n-1)+'Ω'):
                p = replace(a.AdmissionPolicy(), minimum_base_entropy=0, kmer_size=1,
                            minimum_distinct_kmer_fraction=.001)
                self.assertEqual(a._passes_complexity(text,p), set(text)<=set('ACGT'))

    def test_sorted_mask_matches_full_subtraction(self):
        rng = random.Random(7)
        for _ in range(100):
            mask = merged_intervals(Interval(x, x+rng.randrange(1, 9)) for x in rng.choices(range(90), k=rng.randrange(22)))
            for x in range(100):
                s = Interval(x, x + rng.randrange(1, 21))
                self.assertEqual(tuple(a._outside_merged_mask(s, mask)), subtract_intervals(s, mask))

    def test_touching_reference_hit_does_not_need_cigar_expansion(self):
        part = SimpleNamespace(source="s", interval=Interval(100, 200))
        hits = [SimpleNamespace(query=i, aligned_blocks=Mock(side_effect=AssertionError("disjoint hit decoded")))
                for i in (Interval(25, 100), Interval(200, 205))]
        data = SimpleNamespace(reference_hits={"s": hits})
        self.assertEqual(a._reference_groups(data, part, a.AdmissionPolicy()), ({}, set(), ()))
