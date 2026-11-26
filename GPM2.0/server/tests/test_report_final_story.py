"""Proof and geometry for the two adaptive Final Path cards."""
from pathlib import Path
from tempfile import TemporaryDirectory
import copy
import json
import unittest

from report_final_story import project_path, supplied_version, final_versions
from render_final_story import final_card
from refinement_commit import inventory
from workspace_layout import initialize_workspace
import test_refinement_path as path_fixture
from test_refinement_path import source, build, rp


class FinalStoryTests(unittest.TestCase):
    def setUp(self):
        f=path_fixture.RefinementPathTests('test_zero_edits_preserves_sequence_but_is_not_success_receipt'); f.setUp();self.f=f
        self.edited=build(f.base,f.catalog,[f.edit(replacement=source('degap','joint',1,3,'-'))]);self.direct=build(f.base,f.catalog,[f.edit(end=10)])
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.layout=initialize_workspace(Path(self.temp.name)/'moved')

    def publication(self,final):
        layout=self.layout;folder=layout.path('05_final/01_degap');folder.mkdir(parents=True,exist_ok=True)
        (folder/'assembly.fa').write_bytes(b'>chr1\n'+b''.join(z for p in final['chromosomes'][0]['segments'] for z in rp.segment_blocks(p,self.f.catalog))+b'\n');(folder/'final_path.json').write_text(json.dumps(final))
        (folder/'sources.tsv').write_text('dataset\tcontig\tlength\nold\tright\t6\nold\tleft\t4\ndegap\tjoint\t3\n');return inventory(folder)['files']

    def test_reverse_slice_direct_join_and_copy_only_the_server_path(self):
        files=self.publication(self.edited);v=supplied_version(self.layout,'degap',{'server_final_directory':'/original/server-job/05_final'},files,self.edited,quick={},transaction='a',edits=1)
        p=v['tracks'][0]['parts'][1];self.assertEqual((p['start'],p['end'],p['source']['strand'],p['source']['length']),(4,7,'-',3));self.assertTrue(v['absolute']);self.assertEqual(v['fasta'],'/original/server-job/05_final/01_degap/assembly.fa')
        f=self.publication(self.direct);v2=supplied_version(self.layout,'degap',{},f,self.direct,quick={},transaction='a',edits=1);self.assertFalse(v2['absolute']);self.assertEqual([p['kind'] for p in v2['tracks'][0]['parts']],['source','source']);self.assertEqual(v2['tracks'][0]['length'],8)
        vm={'meta':{'mode':'full_pipeline'},'lgz_summary':{'inputs':{'assemblies':[]},'reference_tracks':{'chr1':{'length_bp':14}}},'refinement_summary':{'tools':[{'tool':'degap'}],'original_loci':self.edited['original_gaps']},'final_versions':[v]}
        html=final_card(vm);self.assertIn('data-copy="/original/server-job',html);self.assertIn('data-tool-index="0"',html);self.assertNotIn(' open',html);self.assertNotIn('download',html);self.assertIn('source-body',html)
        (self.layout.path('05_final/01_degap/assembly.fa')).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'FASTA differs'):supplied_version(self.layout,'degap',{},f,self.direct,quick={},transaction='a',edits=1,verify_content=True)

    def test_zero_edit_tool_delivery_keeps_gaps_and_gets_its_own_fasta(self):
        final=build(self.f.base,self.f.catalog,[]); files=self.publication(final)
        v=supplied_version(self.layout,'degap',{},files,final,quick={},transaction='t',edits=0)
        self.assertEqual(v['tracks'][0]['length'],self.f.base['chromosomes'][0]['q4_length'])
        self.assertEqual([p['kind'] for p in v['tracks'][0]['parts']],['source','gap','source'])
        vm={'meta':{'mode':'full_pipeline'},'lgz_summary':{'inputs':{'assemblies':[]}},'refinement_summary':{'tools':[{'tool':'degap'}],'original_loci':final['original_gaps']},'final_versions':[v]}
        html=final_card(vm);self.assertIn('No new edits',html);self.assertIn('01_degap/assembly.fa',html);self.assertNotIn('data-tool-index=',html)

    def test_fail_closed_and_no_preview_row_cap(self):
        rows=[dict(segment_id=f'G{i}',kind='gap',length=1) for i in range(260)];d={'chromosomes':[dict(chr='C',q4_length=260,q4_sha256='a'*64,segments=rows)]};p=project_path(d,{},refined=False)[0];self.assertEqual((len(p['parts']),p['parts'][-1]['end']),(260,260))
        bad=copy.deepcopy(self.edited);bad['chromosomes'][0]['segments'][1]['output_start']+=1
        with self.assertRaisesRegex(ValueError,'discontinuous'):project_path(bad,{},refined=True)
        self.assertEqual(final_versions(self.layout,{},dict(tools=[{'publication_verified':False}]),{'status':'failed'},[], 'full_pipeline'),[])
        vm={'meta':{'mode':'full_pipeline'},'refinement_summary':{'tools':[{'tool':'degap'}],'original_loci':[]},'lgz_summary':{},'final_versions':[]}
        self.assertIn('No verified refined version',final_card(vm));self.assertNotIn('LGZ-only',final_card(vm))

    def test_auto_selects_highest_closed_version_with_priority_tiebreak_and_header_path(self):
        files=self.publication(self.edited)
        v_tgs=supplied_version(self.layout,'degap',{'server_final_directory':'/srv/run/05_final'},files,self.edited,quick={},transaction='a',edits=0)
        v_tgs['tool']='tgsgapcloser';v_tgs['fasta']='/srv/run/05_final/02_tgsgapcloser/assembly.fa'
        v_lr=copy.deepcopy(v_tgs);v_lr['tool']='lrgapcloser';v_lr['edits']=3;v_lr['fasta']='/srv/run/05_final/04_lrgapcloser/assembly.fa'
        v_degap=copy.deepcopy(v_tgs);v_degap['tool']='degap';v_degap['edits']=2;v_degap['fasta']='/srv/run/05_final/01_degap/assembly.fa'
        # LR has 2 closed + 1 partial; DEGAP has 2 closed -> tie on closed count, DEGAP wins by priority.
        tools=[
            {'tool':'tgsgapcloser','gap_decisions':{'g1':{'state':'retained'},'g2':{'state':'retained'},'g3':{'state':'retained'}}},
            {'tool':'lrgapcloser','gap_decisions':{'g1':{'state':'closed'},'g2':{'state':'closed'},'g3':{'state':'partial'}}},
            {'tool':'degap','gap_decisions':{'g1':{'state':'closed'},'g2':{'state':'closed'},'g3':{'state':'retained'}}},
        ]
        vm={'meta':{'mode':'full_pipeline'},'lgz_summary':{'inputs':{'assemblies':[]},'reference_tracks':{'chr1':{'length_bp':14}}},
            'refinement_summary':{'tools':tools,'original_loci':self.edited['original_gaps']},'final_versions':[v_tgs,v_lr,v_degap]}
        html=final_card(vm)
        self.assertIn('LGZ + DEGAP',html)
        self.assertIn('data-copy="/srv/run/05_final/01_degap/assembly.fa"',html)
        self.assertIn('class="final-head-fasta"',html)
        self.assertNotIn('data-final-version',html)
        self.assertNotIn('class="preview-label"',html)
        self.assertIn('class="preview-part-txt"',html)
