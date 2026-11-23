"""Positive threshold is a distinct, bound final search contract, never a bypass for old scopes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from server.tests.test_q0_admission import EvidenceFixture, bridge_fixture, dna
from server.tools.lgz_core import q0_admission as adm, q0_preparation as prep
from server.tools.lgz_core.common import stable_id
from server.tools.lgz_core.q0_frontier_scope import UnsearchedQ0Context, audit_selected_scope
from server.tools.lgz_core.q0_sources import Q0EvidenceError
from server.tools.lgz_core.q0_threshold_acceptance import SCOPE, SEMANTICS, VerifiedScope, record
from server.tools.lgz_core.q0_threshold_questions import questions


def with_scope(data, frontier, omitted=(), *, mode='decision_frontier'):
    report={'requested':SCOPE, 'effective':mode, 'acceptance':SEMANTICS,
            'threshold_request':record(frontier),'unsearched_part_intervals':list(omitted)}
    return replace(data,catalog={'supplement_scope':report}, ready_manifest_identity='unit-test-receipt',
                   threshold_scope=VerifiedScope('unit-test-receipt',(),stable_id('threshold-search',report)))


class ThresholdAcceptanceTests(unittest.TestCase):
    def test_strong_exact_cut_survives_unsearched_rival_but_old_contract_still_rejects(self):
        f, truth=bridge_fixture(reverse=True); data=f.data(); key=next(p.segment_id for p in data.parts.values() if p.source.contig=='c')
        scoped=with_scope(data,{next(iter(data.parts.values())).source:(next(iter(data.parts.values())).interval,)},[[key,[[0,1200]]]])
        chosen=adm.construct_q0(scoped)
        self.assertEqual(chosen.records['chr1'],truth)
        self.assertEqual(chosen.decisions['supplement_acceptance']['decision_counts']['sequence_overlap_stop'],2)
        self.assertFalse(chosen.decisions['supplement_acceptance']['alternatives_exhaustive'])
        with self.assertRaises(UnsearchedQ0Context): audit_selected_scope(scoped,chosen.admission,chosen.paths)
        with self.assertRaisesRegex(Q0EvidenceError,'verified scope'): adm.construct_q0(replace(scoped,threshold_scope=None))
        with self.assertRaisesRegex(Q0EvidenceError,'changed after verification'):
            adm.construct_q0(replace(scoped,catalog={'supplement_scope':{**scoped.catalog['supplement_scope'],'effective':'full'}}))

    def test_weak_join_must_be_requested_and_not_overlap_omissions_on_either_axis(self):
        f,_=bridge_fixture(); data=replace(f.data(),pair_links=()); need,_=questions(data,adm.select_q0_paths(data),[])
        for source in need:
            part=next(p for p in data.parts.values() if p.source==source)
            cut=need[source][0].start-part.interval.start
            with self.assertRaisesRegex(UnsearchedQ0Context,'overlaps an unsearched'):
                adm.construct_q0(with_scope(data,need,[[part.segment_id,[[cut,cut+1]]]]))
            incomplete={s:spans for s,spans in need.items() if s!=source}
            with self.assertRaisesRegex(UnsearchedQ0Context,'not requested'):
                adm.construct_q0(with_scope(data,incomplete))
        accepted=adm.construct_q0(with_scope(data,need))
        self.assertEqual([j.kind for j in accepted.paths['chr1'].path.joins],['reference_unknown'])
        self.assertGreater(accepted.decisions['supplement_acceptance']['decision_counts']['unproven_join'],0)
        with self.assertRaises(UnsearchedQ0Context): adm.construct_q0(with_scope(data,{},mode='base_only'))

    def test_regular_scope_reuses_complete_enumeration_but_not_an_omitted_weak_shoulder(self):
        f,_=bridge_fixture(); data=replace(f.data(),pair_links=()); need,_=questions(data,adm.select_q0_paths(data),[])
        first,second=need; part=next(p for p in data.parts.values() if p.source==second)
        def graph(omit):
            v=with_scope(data,{first:need[first]},omit)
            return replace(v,catalog={**v.catalog,'regional_partial_discovery':{'frontier_scope':True,'completed_regional_tasks':0,'frontier_omitted_windows':len(omit)},
                        'regional_candidate_discovery':{'frontier_scope':True,'completed_regional_tasks':0,'frontier_omitted_windows':0},'supplementary_alignments':[]})
        ok=adm.construct_q0(graph([])); self.assertGreater(ok.decisions['supplement_acceptance']['decision_counts']['expanded_intervals_already_covered_by_planner'],0)
        lo=need[second][0].start-part.interval.start
        with self.assertRaisesRegex(UnsearchedQ0Context,'overlaps an unsearched'):
            adm.construct_q0(graph([[part.segment_id,[[lo,lo+1]]]]))
        bad=graph([]);bad.catalog['regional_partial_discovery']['completed_regional_tasks']=1
        with self.assertRaisesRegex(Q0EvidenceError,'differs from tasks'): adm.construct_q0(bad)

    def test_canonical_cli_zero_dispatch_close_cache_and_no_reads_restriction(self):
        with tempfile.TemporaryDirectory() as t:
            f,truth=bridge_fixture(); root=f.workspace(t); pkg=root/'metadata/package.tsv';pkg.write_text('reads_qc_enabled\nfalse\n')
            fake=Path(t)/'q0-fixture-bin'; tool=str(fake/'minimap2'); env={**os.environ,'PATH':str(fake)+os.pathsep+os.environ['PATH']}
            # An external invocation, with real outer receipts and source/reference FASTAs, not a panel adapter.
            args=[sys.executable,str(Path(prep.__file__).parents[1]/'lgz_prepare_evidence.py'),'--server-dir',str(root),'--minimap2',tool,'--supplement-scope',SCOPE]
            subprocess.run(args,env=env,check=True,capture_output=True,text=True)
            with patch.dict(os.environ,env):
                r=prep.load_verified_evidence(root); cat=prep.json_file(root/r['catalog']); self.assertEqual(cat['supplement_scope']['effective'],'base_only')
                self.assertFalse(cat['supplementary_alignments']); cached=(root/prep.MANIFEST).stat().st_mtime_ns
                with patch.object(prep,'_prepare_evidence_pass',side_effect=AssertionError('cold work on cache hit')):
                    self.assertEqual(prep.prepare_evidence(root,minimap2=tool,supplement_scope=SCOPE),r)
                self.assertEqual((root/prep.MANIFEST).stat().st_mtime_ns,cached)
                self.assertEqual(adm.build_q0(root).records['chr1'],truth)
                with self.assertRaisesRegex(Q0EvidenceError,'reads QC'):
                    adm.build_q0(root,quality_pass={s:True for s in f.sources})
                pkg.write_text('reads_qc_enabled\ntrue\n'); before=(root/prep.MANIFEST).read_bytes()
                with self.assertRaises(Q0EvidenceError): prep.load_verified_evidence(root)
                with self.assertRaises(Q0EvidenceError): prep.prepare_evidence(root,minimap2=tool,supplement_scope=SCOPE)
                self.assertEqual((root/prep.MANIFEST).read_bytes(),before)

    def test_real_grt_prepare_inputs_and_donor_freeze_consume_threshold_generation(self):
        from server.tests.test_q0_publication import complete_workspace, run_prepare
        from server.tools.lgz_core.common import read_fasta
        from server.tools.lgz_core.q0_publication import validate_prepared_q0
        with tempfile.TemporaryDirectory() as t:
            f, truth=bridge_fixture(reverse=True); root=complete_workspace(f,Path(t)); fake=Path(t)/'q0-fixture-bin'
            with patch.dict(os.environ,{'PATH':str(fake)+os.pathsep+os.environ['PATH']}):
                prep.prepare_evidence(root,minimap2=str(fake/'minimap2'),supplement_scope=SCOPE)
                run=run_prepare(root); self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(dict(read_fasta(root/'grt/q/q0.fa')),{'chr1':truth})
            freeze=validate_prepared_q0(root)
            self.assertEqual(next(r['available'] for r in freeze['sources'] if r['source']['contig']=='c'),
                             [{'start':0,'end':200},{'start':1000,'end':1200}])

    def test_weak_join_does_not_build_a_discarded_catalog_or_reread_the_source_fasta_for_dispatch(self):
        f,_=bridge_fixture(); f.links.clear(); f.raw={k:v for k,v in f.raw.items() if '_vs_ref/' in k}
        with tempfile.TemporaryDirectory() as t:
            root=f.workspace(t); (root/'metadata/package.tsv').write_text('reads_qc_enabled\nfalse\n'); fake=Path(t)/'q0-fixture-bin'
            with (patch.dict(os.environ,{'PATH':str(fake)+os.pathsep+os.environ['PATH']}),
                  patch.object(prep,'build_catalog',wraps=prep.build_catalog) as catalogs,
                  patch.object(prep,'_dataset_sequences',wraps=prep._dataset_sequences) as reads):
                manifest=prep.prepare_evidence(root,minimap2=str(fake/'minimap2'),supplement_scope=SCOPE)
                self.assertEqual(catalogs.call_count,1); self.assertEqual(reads.call_count,1)
                report=prep.json_file(root/manifest['catalog'])['supplement_scope']; self.assertEqual(report['effective'],'full')
                out=adm.build_q0(root); self.assertEqual(out.decisions['supplement_acceptance']['decision_counts'],{'full_discovery':True})

    def test_no_reference_seed_does_not_publish_a_successful_selection(self):
        f=EvidenceFixture(); f.source('not_on_reference',dna(700))
        with tempfile.TemporaryDirectory() as t:
            root=f.workspace(t); (root/'metadata/package.tsv').write_text('reads_qc_enabled\nfalse\n'); old=(root/prep.MANIFEST).read_bytes()
            fake=Path(t)/'q0-fixture-bin'
            with patch.dict(os.environ,{'PATH':str(fake)+os.pathsep+os.environ['PATH']}), self.assertRaisesRegex(Q0EvidenceError,'no chromosome'):
                prep.prepare_evidence(root,minimap2=str(fake/'minimap2'),supplement_scope=SCOPE)
            self.assertEqual((root/prep.MANIFEST).read_bytes(),old)

    def test_new_scope_is_not_a_resume_resource_switch(self):
        code = """from pathlib import Path
import server_run as run
opts=run.parse_options(['--q0-supplement-scope','positive_threshold'],Path.cwd())
run.check_resume_options(opts,opts,{})
try: run.check_resume_options(opts,{}, {})
except run.RunnerError: pass
else: raise AssertionError('threshold override accepted on a full workspace resume')
"""
        subprocess.run([sys.executable,'-c',code],cwd=Path(prep.__file__).parents[1],check=True)
