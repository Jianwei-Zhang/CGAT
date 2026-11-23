"""Compare actual coordinate projections, not two implementations using the same locus key."""
import math
import random
import unittest
from unittest.mock import patch

from server.tools.lgz_core import q0_reference_competition as competition
from server.tools.lgz_core.q0_admission import _project, _RefBlock, AdmissionPolicy
from server.tools.lgz_core.q0_sources import Interval, merged_intervals, subtract_intervals


def oracle(blocks, margin):
    masks, ambiguous = [], []
    for b in blocks:
        conflicts = []
        for c in blocks:
            overlap = b.query.intersection(c.query)
            if overlap is None or c.identity + margin < b.identity:
                continue
            if (c.chromosome != b.chromosome or c.strand != b.strand or
                _project(c.query, c.target, c.strand, overlap) != _project(b.query, b.target, b.strand, overlap)):
                conflicts.append(overlap)
        masks.append(subtract_intervals(b.query, conflicts)); ambiguous.extend(conflicts)
    return masks, merged_intervals(ambiguous)


def block(a, b, chr_, strand, offset, score, evidence):
    q = Interval(a,b); t = Interval(a+offset,b+offset) if strand=='+' else Interval(offset-b,offset-a)
    return _RefBlock(q,t,chr_,strand,evidence,score,60)


class ReferenceCompetitionTests(unittest.TestCase):
    def test_dense_and_sparse_compare_to_projection_for_both_strands_and_score_boundaries(self):
        rng = random.Random(8157)
        for n,width in ((0,0),(1,0),(16,40),(90,4),(103,80),(160,250)):
            for margin in (0,.02,.1):
                scores = [.90,.92,math.nextafter(.90+margin,0),.96,1.0]
                rows=[]
                for i in range(n):
                    a=rng.randrange(200);b=a+rng.randrange(1,width+2)
                    rows.append(block(a,b,rng.choice('AB'),rng.choice('+-'),rng.choice((500,540)),rng.choice(scores),str(i)))
                self.assertEqual(competition.reference_masks(rows,margin),oracle(rows,margin))

    def test_long_nesting_uses_dense_algorithm_and_coalesces_unique_pieces(self):
        rows=[block(0,1200,'A','-',1300,1,'strong')]
        rows.extend(block(5*i,5*i+8,'A','-',1300,.96,str(i)) for i in range(100))
        rows.extend(block(i,i+29,'B','+',27,.98,'other') for i in (173,285,600))
        with patch.object(competition,'_dense_masks',wraps=competition._dense_masks) as dense:
            masks,ambiguous=competition.reference_masks(rows,AdmissionPolicy().competing_identity_margin)
            dense.assert_called_once()
        self.assertEqual((masks,ambiguous),oracle(rows,.02))
        self.assertEqual(masks[0],(Interval(0,173),Interval(202,285),Interval(314,600),Interval(629,1200)))

    def test_identity_is_asymmetric_and_same_locus_is_not_a_competitor(self):
        high=block(0,200,'A','+',200,.99,'hi'); duplicate=block(8,182,'A','+',200,.94,'other-evidence')
        weaker=block(20,70,'A','+',201,.96,'lo');touch=block(200,240,'A','-',500,.99,'boundary')
        masks,union=competition.reference_masks([high,duplicate,weaker,touch],.02)
        self.assertEqual(masks,[(high.query,),(Interval(8,20),Interval(70,182)),(),(touch.query,)])
        self.assertEqual(union,(Interval(20,70),))
