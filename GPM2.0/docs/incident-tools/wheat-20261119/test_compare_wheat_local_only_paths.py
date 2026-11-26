from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as S
import unittest
from lgz_core.q0_paths import RequestPathResult
from lgz_core.q0_sources import Interval,SourceKey
from wheat_selection_checkpoint import Store
from compare_wheat_local_only_paths import GROUPS,checkpoint,path_delta,contacted_outcome,axes,footprint_diff


def path(a=20,b=40,orientation='-',kind='reference_unknown',evidence='old',score=1):
    left=S(source=SourceKey('assembly','x'),orientation='+',interval=Interval(0,a),placement_id='left');right=S(source=SourceKey('assembly','y'),orientation=orientation,interval=Interval(25,b),placement_id='right');j=S(kind=kind,n_bp=100,gap_source=None,gap_interval=None,join_id='join-'+evidence);return S(slices=[left,right],joins=[j],score=score)

class WholeDeltaTests(unittest.TestCase):
    def test_score_or_evidence_is_not_a_cut_change(self):
        d=path_delta(path(),path(evidence='new',score=2));self.assertFalse(d['same_path_record']);self.assertTrue(d['same_source_cuts_joins']);self.assertEqual(d['changed_source_cuts'],0)
    def test_reverse_cut_shift_vs_junction_kind_or_replacement(self):
        issue={'id':'join-old','kind':'unproven_join','groups':['1A']}
        out=lambda p:contacted_outcome(issue,[0],{},path(),p)
        self.assertEqual(out(path(kind='sequence_overlap'))['new_join_kinds_at_same_cuts'],['sequence_overlap'])
        self.assertEqual((out(path(b=39))['same_directed_source_pair_count'],out(path(b=39))['new_join_kinds_at_same_cuts']),(1,[]))
        self.assertEqual(out(path(orientation='+'))['same_directed_source_pair_count'],0);self.assertFalse(out(None)['question_still_present'])
        self.assertEqual(path_delta(path(),path(b=39))['changed_source_cuts'],1)
    def test_request_coordinates_not_hulls_or_net_changes(self):
        old=axes([{'spans':[['d','a',0,10],['d','a',7,12],['d','a',19,22]]}]);new=axes([{'spans':[['d','a',2,14],['d','b',2,5]]}]);self.assertEqual(footprint_diff(old,new),dict(old_only_bp=5,new_only_bp=5,both_bp=10,same=False))
    def test_header_trailer_and_binding_for_all_22_even_empty_groups(self):
        with TemporaryDirectory() as d,redirect_stdout(StringIO()):
            folder=Path(d);s=Store(folder,['scope'],False);s.save('admission.jsonl',None,[])
            for i,c in enumerate(GROUPS,1):s.save_group(i,c,RequestPathResult(None))
            sha,_,paths=checkpoint(folder,['scope']);self.assertEqual(sha,s.previous);self.assertEqual(list(paths),list(GROUPS));self.assertIsNone(paths['Un'])
            with self.assertRaisesRegex(ValueError,'scope'):checkpoint(folder,['foreign'])
            last=folder/'group-022.jsonl';last.write_bytes(last.read_bytes()[:-8]);
            with self.assertRaises(ValueError):checkpoint(folder,['scope'])
