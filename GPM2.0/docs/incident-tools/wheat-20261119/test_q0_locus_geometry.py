import unittest
from lgz_core.q0_sources import Interval as I
from q0_locus_geometry import LocusIndex, Ranges, map_key
from replay_q0_known_loci import explained


class SignedLocusTests(unittest.TestCase):
    def test_union_within_exact_map_not_an_envelope_across_a_hole(self):
        ix=LocusIndex();ix.add('a','b',I(10,60),I(210,260),'+');ix.add('a','b',I(160,280),I(360,480),'+');ix.seal()
        q,t=I(10,280),I(210,480); cores=Ranges([q])
        self.assertEqual(ix.novel('a','b',q,t,'+',cores,100),'extends_existing_map')
        self.assertIsNone(ix.novel('a','b',q,t,'+',cores,101))
        self.assertIsNone(ix.novel('a','b',q,t,'+',Ranges([I(10,60),I(160,280)]),1))
        self.assertFalse(explained(ix,'a','b',[q],t))
        self.assertTrue(explained(ix,'a','b',[I(10,60),I(160,280)],t))

    def test_reverse_boundaries_and_reciprocal_roles_with_actual_source_offsets(self):
        a,b=I(1200,1500),I(8520,8820);ix=LocusIndex();ix.add('q','t',a,b,'-');ix.add('t','q',b,a,'-');ix.seal()
        s,d=I(1250,1350),I(8670,8770);self.assertEqual(map_key(a,b,'-'),map_key(d,s,'-'))
        self.assertTrue(explained(ix,'q','t',[s],d));self.assertTrue(explained(ix,'t','q',[d],s))
        self.assertFalse(explained(ix,'q','t',[s],I(8671,8770)))
        self.assertEqual(ix.novel('q','t',s,d,'+',Ranges([s]),100),'new_strand_on_existing_pair')
        self.assertEqual(ix.novel('q','t',s,I(8671,8771),'-',Ranges([s]),100),'new_map_on_existing_strand')
        self.assertEqual(ix.novel('q','z',s,d,'-',Ranges([s]),100),'new_source_pair')

    def test_do_not_predict_when_two_maps_already_compete_but_unseen_competition_is_possible(self):
        ix=LocusIndex();q=I(0,100);t=I(500,600);ix.add('q','t',q,t,'+');ix.seal()
        # A second homologous locus inside the same target could be invisible before mapping.
        self.assertTrue(explained(ix,'q','t',[q],I(500,800)))
        self.assertEqual(ix.novel('q','t',q,I(700,800),'+',Ranges([q]),100),'new_map_on_existing_strand')
        both=LocusIndex();both.add('q','t',q,t,'+');both.add('q','t',I(0,20),I(700,720),'+');both.seal()
        self.assertFalse(explained(both,'q','t',[q],I(500,800)))
        self.assertTrue(explained(both,'q','t',[q],t))

    def test_clipped_query_or_adjacent_bases_are_not_100_new_core_bases(self):
        ix=LocusIndex();ix.seal();q=I(0,120);t=I(300,420)
        self.assertIsNone(ix.novel('q','t',q,t,'+',Ranges([I(21,140)]),100))
        self.assertEqual(ix.novel('q','t',q,t,'+',Ranges([I(20,140)]),100),'new_source_pair')
        self.assertIsNone(ix.novel('q','t',q,t,'+',Ranges([I(120,240)]),1))
