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
        with self.assertRaisesRegex(ValueError,'FASTA differs'):supplied_version(self.layout,'degap',{},f,self.direct,quick={},transaction='a',edits=1)

    def test_fail_closed_and_no_preview_row_cap(self):
        rows=[dict(segment_id=f'G{i}',kind='gap',length=1) for i in range(260)];d={'chromosomes':[dict(chr='C',q4_length=260,q4_sha256='a'*64,segments=rows)]};p=project_path(d,{},refined=False)[0];self.assertEqual((len(p['parts']),p['parts'][-1]['end']),(260,260))
        bad=copy.deepcopy(self.edited);bad['chromosomes'][0]['segments'][1]['output_start']+=1
        with self.assertRaisesRegex(ValueError,'discontinuous'):project_path(bad,{},refined=True)
        self.assertEqual(final_versions(self.layout,{},dict(tools=[{'publication_verified':False}]),{'status':'failed'},[], 'full_pipeline'),[])
        vm={'meta':{'mode':'full_pipeline'},'refinement_summary':{'tools':[{'tool':'degap'}],'original_loci':[]},'lgz_summary':{},'final_versions':[]}
        self.assertIn('No verified refined version',final_card(vm));self.assertNotIn('LGZ-only',final_card(vm))
