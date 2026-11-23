import hashlib
import io
import unittest
from replay_wheat_partial_queries import GEOM, HEAD, MAGIC, Interval, intersect_census, residual

class QueryReplayTests(unittest.TestCase):
    def test_only_qualifying_gaps_survive_on_original_axis(self):
        holes=(Interval(10,600),Interval(900,1100)); cover=(Interval(0,10),Interval(109,220),Interval(320,421),Interval(600,900),Interval(1000,1200))
        self.assertEqual(residual(holes,cover),(Interval(220,320),Interval(421,600),Interval(900,1000)))
    def test_target_variants_do_not_become_separate_queries(self):
        q=b'a'*12; other=b'c'*12; geom=(0,8,21); plan={q:geom,b'd'*12:(3,0,88)}
        raw=MAGIC+b''.join(HEAD.pack(bytes([i])*12,k,2)+GEOM.pack(*g)+GEOM.pack(i,0,10) for i,k,g in [(1,q,geom),(2,q,geom),(3,other,(1,0,90))]); sha=hashlib.sha256(raw).hexdigest(); v=intersect_census(io.BytesIO(raw),plan,sha)
        self.assertEqual((v['matching_contexts'],v['planned_queries_with_observed_target_sets'],v['planned_queries_without_observed_target_sets'],v['other_contexts']),(2,1,1,1))
        with self.assertRaises(ValueError):intersect_census(io.BytesIO(raw),{q:(1,8,21)},sha)
        with self.assertRaises(ValueError):intersect_census(io.BytesIO(raw[:-1]),plan,sha)
