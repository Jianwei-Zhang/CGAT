"""Gap explanations are bound to the committed tool version and original loci."""
import copy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from report_gap_story import degap_geometry, gap_evidence, native_views, checked_json
from test_refinement_path import MemoryCatalog, baseline, segment, source, build, rp
from workspace_layout import WorkspaceLayout


class GapStoryTests(unittest.TestCase):
    def test_joint_geometry_and_direct_join_use_reconstructed_path_not_n_count(self):
        cat = MemoryCatalog({('old','ctg'):'ACATTG', ('fill','x'):'GGT'})
        base = baseline(cat, [segment('a',source('old','ctg',1,2)), segment('gap1',length=2),
                              segment('b',source('old','ctg',3,4)), segment('gap2',length=3), segment('c',source('old','ctg',5,6))])
        ids = tuple(g.gap_id for g in rp.inspect_baseline(base,cat)[0]); self.assertEqual(len(ids),2)
        for src, end in ((source('fill','x',1,3,'-'),5), (None,2)):
            edit = rp.Edit('one','degap','chr1',2,9,src,ids,'fixture',{'local':True})
            final = build(base,cat,[edit]); rows = [dict(r,tools={'degap':'closed'}) for r in final['original_gaps']]
            prov = dict(baseline=final['baseline'],gap_outcomes=[dict(r,status='closed',edit_ids=['one']) for r in rows])
            data = gap_evidence(rows,'degap',prov,final)
            left,right = [data[k]['edits'][0] for k in ids];self.assertEqual(left,right)
            self.assertEqual((left['gap_ids'],left['before'],left['after']), (list(ids),[2,9],[2,end]))
            if src: self.assertEqual(left['source']['strand'],'-')
            else: self.assertIsNone(left['source'])
            bad = copy.deepcopy(rows);bad[1]['end']+=1
            with self.assertRaisesRegex(ValueError,'denominator'):gap_evidence(bad,'degap',prov,final)

    def test_retained_joint_candidate_has_no_admitted_edit_or_invented_n_coordinates(self):
        rows=[dict(chromosome='C',gap_id=g,start=a,end=b,tools={'degap':'unfilled'}) for g,a,b in [('g1',5,7),('g2',12,14)]]
        final=dict(original_gaps=rows,edits=[]);ids=['g1','g2']
        withheld=dict(reason='incomplete_gap_kept_original',gap_ids=ids,edits=[dict(edit_id='x',baseline_interval=[5,14],replacement=source('fill','x',2,8))])
        prov=dict(gap_outcomes=[dict(r,status='unfilled',reason=withheld['reason'],candidate_residual_n_bp=2,edit_ids=[]) for r in rows],execution={'withheld_candidates':[withheld]})
        d=gap_evidence(rows,'degap',prov,final)['g2'];self.assertEqual((d['state'],d['edits'],d['residual_n_bp']),('retained',[],2))
        self.assertEqual(d['candidates'][0]['gap_ids'],ids);self.assertNotIn('n_positions',d)
        prov['gap_outcomes'][0]['status']='partial'
        with self.assertRaisesRegex(ValueError,'outcome mismatch'):gap_evidence(rows,'degap',prov,final)

    def test_degap_paired_exteriors_use_full_candidate_axis_not_patch_axis(self):
        def proof(method,a,b):return dict(method=method,candidate_sha256='a'*64,native_coordinates=dict(gap_start=7,gap_end=8,gap_len=2,left_flank_len=6,right_flank_len=6),anchors=dict(left_bp=a,right_bp=b))
        self.assertEqual(degap_geometry(proof('exact_anchors_gap_repair',6,6),[6,8],4), ([6,10],[[[0,6],[0,6]],[[8,14],[10,16]]]))
        self.assertEqual(degap_geometry(proof('exact_anchors_overlap_closure',6,6),[6,10],0), ([6,6],[[[0,6],[0,6]],[[8,14],[4,10]]]))
        self.assertEqual(degap_geometry(proof('sealed_family_junction',5,5),[5,9],3), ([5,8],[[[0,5],[0,5]],[[9,14],[8,13]]]))
        self.assertEqual(degap_geometry(dict(proof('exact_anchors_joint_repair',6,6),parent_native_edit_id='parent'),[6,8],2),(None,[]))

    def test_degap_only_native_job_global_or_missing_and_committed_bytes(self):
        with TemporaryDirectory() as temp:
            layout=WorkspaceLayout.detect(Path(temp));folder='06_report/tool'; home=layout.root/folder
            views=[]; files={}
            for name in ['job1.html','job2.html','Global.report.html']:
                w='native_visualization/view-'+hashlib.sha256(name.encode()).hexdigest()[:20]+'.html';d='native_visualization/pages/'+name
                for path in (w,d):
                    f=home/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(name);files[path]=hashlib.sha256(f.read_bytes()).hexdigest()
                views.append(dict(name=name,wrapper_path=w,display_path=d))
            jobs=[dict(job_name=n,original_gap_ids=['g']) for n in ('job1','job2')]
            summary=dict(tool='degap',native_visualization={'views':views},native_jobs=jobs)
            by_id,global_link=native_views(layout,folder,summary,files,{'g','other'});self.assertEqual([j['name'] for j in by_id['g']],['job1','job2']);self.assertNotIn('other',by_id);self.assertTrue(global_link)
            (home/views[0]['display_path']).write_text('modified');(home/views[1]['wrapper_path']).unlink()
            self.assertEqual(native_views(layout,folder,summary,files,{'g'}),({},global_link))
            (home/views[2]['display_path']).unlink();self.assertEqual(native_views(layout,folder,summary,files,{'g'}),({},None))
            self.assertEqual(native_views(layout,folder,dict(summary,tool='quartet'),files,{'g'}),({},None))
            with self.assertRaisesRegex(ValueError,'changed'):checked_json(layout,folder,views[0]['display_path'],files)
