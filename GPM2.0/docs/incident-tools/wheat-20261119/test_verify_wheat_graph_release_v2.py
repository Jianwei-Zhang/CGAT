import copy
import json
from pathlib import Path
import tempfile
import unittest

import verify_wheat_graph_release_v2 as gate


class GateTests(unittest.TestCase):
    def fixture(self):
        c = dict(revision=gate.REV, bp=9,members=2,chromosome='4D',matrix_bytes=99,ref_records={'h':8},
                 request_sources=1,request_intervals=5, timing={'draft_s':100},
                 scientific=dict(has_path=True,sequences={'4D':'sequence'},paths={'4D':'uncapped'},occupied='original'))
        b=copy.deepcopy(c); b.update(revision='older',timing={'draft_s':50}); b['scientific']['paths']={'4D':'old'}
        d=dict(revision=gate.REV,baseline='older',different=['paths'],equal=False,raw_request_equal=True)
        p=dict(revision=gate.REV,paths={'4D':dict(raw='uncapped',reference='old',with_old_diagnostic_only='old')})
        return c,b,d,p

    def test_slower_run_and_different_fixture_counts_are_not_scientific_vetoes(self):
        c,b,d,p=self.fixture();self.assertEqual(gate.check_4d(c,b,d,p),1)
        self.assertEqual(gate.speed_report(c,b)['status'],'slower'); self.assertFalse(gate.speed_report(c,b)['gate'])
        self.assertEqual(gate.speed_report({'timing':{'draft_s':float('nan')}},b)['status'],'unavailable')

    def test_other_changes_or_weaker_proofs_must_not_pass(self):
        for mutation in ('occupied','input','extra','direction','missing_chrom','failed_for_another_reason','request','revision','raw_path'):
            with self.subTest(mutation=mutation):
                c,b,d,p=self.fixture()
                if mutation=='occupied':c['scientific']['occupied']='overlap'
                if mutation=='input':c['ref_records']['h']-=1
                if mutation=='extra':c['scientific']['extra']=True
                if mutation=='direction':p['paths']['4D']['with_old_diagnostic_only']='reversed'
                if mutation=='missing_chrom':p['paths']={}
                if mutation=='failed_for_another_reason':d['different'].append('records')
                if mutation=='request':d['raw_request_equal']=False
                if mutation=='revision':p['revision']='foreign'
                if mutation=='raw_path':p['paths']['4D']['raw']='other'
                with self.assertRaises(ValueError):gate.check_4d(c,b,d,p)

    def test_launch_requires_the_matching_persisted_admission(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); (root/'placement/control').mkdir(parents=True); (root/'selection').mkdir()
            review=dict(schema='wheat_first_request_science_release_v2',accepted=True,scope='science_only_placement_required',
                        revision=gate.REV,snapshot_sha256=gate.SNAP,audit_sha256=gate.AUDIT,geometry_review_sha256=gate.GEOMETRY)
            h='a'*64; p=dict(admission_sha256=h,revision=gate.REV,snapshot_sha256=gate.SNAP,
                             published_q0=False,stage='global_placement_only')
            with self.assertRaises(ValueError):gate.placement_ready(root,review)
            (root/'placement/control/placement-complete.json').write_text(json.dumps(p))
            file=root/'selection/admission.jsonl'
            with self.assertRaises(ValueError):gate.placement_ready(root,review)
            file.write_text('x'*300+'\n'+json.dumps(['end',9,h])+'\n');self.assertEqual(gate.placement_ready(root,review),9)
            with self.assertRaises(ValueError):gate.placement_ready(root,dict(review,revision='other'))
            file.write_text('header\n'+json.dumps(['end',9,'b'*64])+'\n')
            with self.assertRaises(ValueError):gate.placement_ready(root,review)

if __name__=='__main__':unittest.main()
