"""Same-generation reuse removes ranking, not evidence/acceptance/publication checks."""
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server.tests.test_q0_admission import bridge_fixture
from server.tools.lgz_core import q0_admission as adm, q0_preparation as prep
from server.tools.lgz_core import q0_selection_cache as cache, q0_threshold_prepare as threshold
from server.tools.lgz_core.q0_sources import Q0EvidenceError
from server.tools.lgz_core.q0_paths import PathPolicy
from server.tools.lgz_core.common import stable_id


class AcceptedSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.fixture,self.truth=bridge_fixture(reverse=True)
        self.root=self.fixture.workspace(self.temp.name)
        (self.root/'metadata/package.tsv').write_text('reads_qc_enabled\nfalse\n')
        fake=Path(self.temp.name)/'q0-fixture-bin';self.mapper=str(fake/'minimap2')
        env=patch.dict(os.environ,{'PATH':str(fake)+os.pathsep+os.environ['PATH']});env.start();self.addCleanup(env.stop)
        self.manifest=prep.prepare_evidence(self.root,minimap2=self.mapper,supplement_scope='positive_threshold')

    def test_formal_downstream_and_warm_prepare_do_not_select_again(self):
        data=adm.load_evidence_input(self.root)
        expected=adm.construct_q0(data)
        ready=self.root/prep.MANIFEST;before=ready.stat().st_mtime_ns
        with patch.object(adm,'select_q0_paths',side_effect=AssertionError('duplicate selection')):
            got=adm.build_q0(self.root)
            reused=prep.prepare_evidence(self.root,minimap2=self.mapper,supplement_scope='positive_threshold')
        self.assertEqual(got,expected)
        self.assertEqual(got.records,{'chr1':self.truth})
        self.assertEqual(reused,self.manifest)
        self.assertEqual(ready.stat().st_mtime_ns,before)
        self.assertIn(self.manifest[cache.FIELD],{r['path'] for r in self.manifest['outputs']})

    def test_file_damage_is_rejected_not_a_silent_cache_miss(self):
        p=self.root/self.manifest[cache.FIELD];p.write_bytes(p.read_bytes()[:-8])
        with self.assertRaises(Q0EvidenceError):adm.build_q0(self.root)

    def test_rebound_header_from_another_generation_is_rejected(self):
        p=self.root/self.manifest[cache.FIELD];rows=p.read_text().splitlines()
        head=json.loads(rows[0]);head[1]['input_fingerprint']='foreign';rows[0]=json.dumps(head)
        p.write_text('\n'.join(rows)+'\n')
        self.manifest['outputs']=[prep.identity(self.root,r['path']) if r['path']==self.manifest[cache.FIELD] else r for r in self.manifest['outputs']]
        (self.root/prep.MANIFEST).write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(Q0EvidenceError,'header differs'):adm.build_q0(self.root)

    def test_identity_and_policy_drift_cannot_reuse_verified_object(self):
        data=adm.load_evidence_input(self.root);accepted=cache.load(self.root,self.manifest,data)
        with self.assertRaisesRegex(Q0EvidenceError,'generation or policies'):
            adm.construct_q0(replace(data,input_fingerprint='changed'),_accepted=accepted)
        with self.assertRaisesRegex(Q0EvidenceError,'generation or policies'):
            adm.construct_q0(data,path_policy=replace(PathPolicy(),beam_width=9),_accepted=accepted)
        with self.assertRaisesRegex(Q0EvidenceError,'reads QC'):
            adm.construct_q0(data,quality_pass={},_accepted=accepted)

    def test_planning_checkpoint_is_never_an_accepted_selection(self):
        data=adm.load_evidence_input(self.root);draft=adm.select_request_paths(data)
        with self.assertRaisesRegex(Q0EvidenceError,'complete same-generation formal'):
            cache.store(self.root,self.manifest,data,draft)
        with self.assertRaisesRegex(Q0EvidenceError,'verified accepted'):
            adm.construct_q0(data,_accepted=draft)

    def test_reuse_still_executes_independent_acceptance(self):
        from server.tools.lgz_core import q0_threshold_acceptance as acceptance
        with patch.object(acceptance,'audit',side_effect=Q0EvidenceError('final acceptance stopped')):
            with self.assertRaisesRegex(Q0EvidenceError,'final acceptance stopped'):
                adm.build_q0(self.root)

    def test_no_sidecar_uses_ordinary_selection_without_losing_compatibility(self):
        base=cache.base_manifest(self.manifest)
        (self.root/prep.MANIFEST).write_text(json.dumps(base))
        with patch.object(adm,'select_q0_paths',wraps=adm.select_q0_paths) as select:
            result=adm.build_q0(self.root)
        self.assertEqual(select.call_count,1);self.assertEqual(result.records,{'chr1':self.truth})

    def test_codec_preserves_lists_tuples_maps_and_rejects_executable_types(self):
        value={'tuple':(1,2),'list':[1,2],'float':1.2,'source':next(iter(self.fixture.sources))}
        self.assertEqual(cache.decode(json.loads(json.dumps(cache.encode(value)))),value)
        with self.assertRaises(Q0EvidenceError):cache.decode({'object':['system',['unsafe']]})

    def test_cached_source_occupancy_is_rechecked(self):
        data=adm.load_evidence_input(self.root);accepted=cache.load(self.root,self.manifest,data)
        search=next(iter(accepted.selection.paths.values()))
        from collections import defaultdict
        occupied=defaultdict(list)
        adm._occupy_path(data,search,occupied)
        with self.assertRaisesRegex(Q0EvidenceError,'multiple chromosomes|more than once'):
            adm._occupy_path(data,search,occupied)


class LegacyIdentityTests(unittest.TestCase):
    def test_old_outer_signature_keeps_containment_and_stable_identity(self):
        from server.tools import run_orchestration as outer
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'x').write_text('x')
            def old_identity(path):return outer.file_identity(path)
            with patch.object(prep,'_IDENTITY_HAS_WITHIN',False),patch.object(prep,'_file_identity',old_identity):
                self.assertEqual(prep.identity(root,'x'),outer.file_identity(root/'x',relative_to=root))
                outside=root.parent/(root.name+'-outside');outside.write_text('outside')
                try:
                    (root/'escape').symlink_to(outside)
                    with self.assertRaisesRegex(Q0EvidenceError,'escapes workspace'):prep.identity(root,'escape')
                finally:outside.unlink()

    def test_old_identity_rejects_retarget_during_hashing(self):
        from server.tools import run_orchestration as outer
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'x').write_text('old');(root/'y').write_text('new');(root/'alias').symlink_to(root/'x')
            def old_identity(path):
                result=outer.file_identity(path);path.unlink();path.symlink_to(root/'y');return result
            with patch.object(prep,'_IDENTITY_HAS_WITHIN',False),patch.object(prep,'_file_identity',old_identity):
                with self.assertRaisesRegex(Q0EvidenceError,'changed while binding'):prep.identity(root,'alias')


if __name__=='__main__':unittest.main()
