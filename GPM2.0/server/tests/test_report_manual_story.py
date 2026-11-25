"""Exercise actual project exports, manual publication and byte-isolated 08 overlays."""
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from manual_snapshot import FILE, TASKS
from project_manual_roundtrip_fixture import generate, WorkspaceLock
from refine import MANIFEST, prepare_batch, read_tasks
from refine_run import publish_results
from refine_report import automatic_overview_digest
from report_overview_data import manual_batches
from run_orchestration import sha256_file
from workspace_layout import WorkspaceLayout


def digest(b):return hashlib.sha256(b).hexdigest()


def run_export(root,revision,*,all_retained=False):
    l=WorkspaceLayout.detect(root); base=json.loads(l.path('metadata/grt_final_path.json').read_text());origin=sha256_file(l.path(base['q4_relpath'])); objects={}
    def ctg(sid,payload,start,end):
        h=digest(payload);objects[h]=payload;strand=start>end;n=len(payload)
        w=dict(kind='ctg',segment_id=sid,dataset='App-assembly',contig=sid,start=start,end=end)
        m=dict(dataset='App-assembly',name=sid,length=max(start,end),start=min(start,end),end=max(start,end),fasta_sha256=None,interval_sha256=h)
        return dict(witness=w,plan=dict(members=[m],start=n if strand else 1,end=1 if strand else n))
    left=ctg('flipped-ctg',b'ATG',4,2);right=ctg('trimmed-ctg',b'CA',2,3);extra=ctg('only-in-App',b'ACA',1,3);g=dict(witness=dict(kind='gap',segment_id='app-gap',gap_bp=4),plan=None)
    name='edited-at-export';snapshot=json.dumps(dict(schema='cgat.manual-assembly-snapshot.v1',origin_fasta_sha256=origin,objects={k:len(v) for k,v in objects.items()},chromosomes=[dict(chr=name,segments=[left,g,right]),dict(chr='new-chr-'+revision,segments=[extra])])).encode()
    loci=[]
    for kind,target,src in [('gap','app-gap',g),('tel_left','flipped-ctg',left),('tel_right','trimmed-ctg',right)]:
        lid=digest(json.dumps([name,kind,target],separators=(',',':')).encode()); loc=dict(id=lid,chr=name,target=target,kind=kind,tools=['degap'])
        if kind=='gap':loc.update(gap_bp=4,tools=['degap','lrgapcloser','quartet'],witnesses={k:p['witness'] for k,p in [('seqleft',left),('seqright',right),('target',g)]},seed_plans={'seqleft':left['plan'],'seqright':right['plan']})
        else:loc.update(motif='AC',witnesses={'endpoint':src['witness']},seed_plans={'endpoint':src['plan']})
        loci.append(loc)
    manifest=dict(schema=TASKS,export_id=digest(revision.encode()),origin_fasta_sha256=origin,snapshot_sha256=digest(snapshot),loci=loci,reads={'hifi':[],'ont':[]}); archive=root.parent/(revision+'.zip')
    with ZipFile(archive,'w') as z:
        z.writestr(MANIFEST,json.dumps(manifest));z.writestr(FILE,snapshot)
        for h,v in objects.items():z.writestr('snapshot_objects/'+h,v)
    bid,task=read_tasks(archive);prep=prepare_batch(root,archive);assert all(r['status']=='prepared' for r in prep['loci']),prep
    directory=l.path('04_refinement/manual/'+bid);patches={};rows=[]
    for loc in loci:
        lid=loc['id'];kind=loc['kind']
        for tool in loc['tools']:
            ok=not all_retained and tool!='quartet'; row=dict(locus_id=lid,tool=tool,status=('closed' if kind=='gap' else 'extended') if ok else 'no_candidate',patch=None,reason=None if ok else 'original_gap_unchanged' if kind=='gap' else 'no_positive_terminal_extension')
            if ok:
                original,op,payload={'gap':(b'NNNN','replace_gap',b'ACC' if tool=='degap' else b'AC'),'tel_left':(b'CAT','prepend_tel',b'TT'),'tel_right':(b'CA','append_tel',b'GGG')}[kind]
                path=f'patches/{lid}.{tool}.seq';file=root.parent/(revision+lid+tool+'.seq');file.write_bytes(payload);patches[path]=file
                row['patch']=dict(operation=op,original_length=len(original),original_sha256=digest(original),path=path,length=len(payload),sha256=digest(payload))
            rows.append(row)
    lock=WorkspaceLock(root,'manual-report-fixture');lock.acquire()
    try:out=publish_results(l,directory,bid,rows,patches,manifest=task,reads={})
    finally:lock.release()
    return bid,loci,Path(out['fasta'])


class LegacyReturnTests(unittest.TestCase):
    def test_manual_direct_join_is_a_cut_not_a_colored_patch(self):
        from render_manual_story import _batch
        from report_manual_story import project_snapshot
        left=dict(witness=dict(segment_id='a',kind='ctg',start=1,end=2),plan=dict(start=1,end=2,members=[dict(dataset='ds',name='a',start=1,end=2)]))
        g=dict(witness=dict(segment_id='G',kind='gap',gap_bp=2),plan=None)
        after=dict(witness=dict(segment_id='b',kind='ctg',start=1,end=2),plan=dict(start=1,end=2,members=[dict(dataset='ds',name='b',start=1,end=2)]))
        row=dict(locus_id='g',tool='degap',status='closed',patch=dict(operation='replace_gap',original_length=2,length=0,sha256=digest(b'')))
        story=project_snapshot({'chromosomes':[dict(chr='C',segments=[left,g,after])]},dict(loci=[dict(id='g',chr='C',target='G',kind='gap',tools=['degap'])]),dict(selected={'g':'degap'},chromosomes={'C':dict(length=4,sha256='a'*64)}),[row]);self.assertEqual(story['loci']['g']['after'],[2,2]);html=_batch({'story':story},0)
        self.assertNotIn('data-manual-gap',html.split('</summary>')[0]);self.assertIn('data-manual-gap',html.split('</summary>')[1])

    def test_only_verified_bundle_outcomes_and_its_own_locus_names_are_reported(self):
        from report_manual_story import collect_manual_story
        from refine_report import _batch_dir,manual_patch_path
        from workspace_layout import initialize_workspace
        with TemporaryDirectory() as tmp:
            layout=initialize_workspace(Path(tmp)/'work');batch='a'*64;lid=digest(json.dumps(['染色体','gap','G'],ensure_ascii=False,separators=(',',':')).encode());patch=manual_patch_path(layout,batch);patch.parent.mkdir(parents=True)
            result=dict(schema='cgat.app-refinement-results.v1',batch_sha256=batch,results=[dict(tool='degap',status='no_candidate',patch=None,locus_id=lid)])
            with ZipFile(patch,'w') as z:z.writestr('refinement_results.json',json.dumps(result))
            summary=dict(delivery=patch.relative_to(layout.root).as_posix(),delivery_sha256=sha256_file(patch),results=[dict(tool='degap',status='closed')],loci={lid:dict(chr='染色体',kind='gap',target='G')})
            def story():return collect_manual_story(layout,batch,_batch_dir(layout,batch),summary,{},False)
            self.assertIsNone(story()['tracks']);self.assertEqual((story()['legacy'][0]['chr'],story()['legacy'][0]['status']),('染色体','no_candidate'))
            summary['loci'][lid]['chr']='other';self.assertIsNone(story()['legacy'][0]['chr']);patch.write_bytes(b'changed');self.assertFalse(story()['legacy_verified']);self.assertEqual(story()['legacy'],[])


@unittest.skipUnless(shutil.which('samtools'),'private FASTA indexing requires samtools')
class ManualStoryTests(unittest.TestCase):
    def test_export_adjusted_path_two_tool_winners_both_ends_extra_chr_and_independent_batches(self):
        with TemporaryDirectory() as td:
            root=Path(td)/'job';generate(root);l=WorkspaceLayout.detect(root);page=l.path('06_report/report.html');page.write_text('<main>sealed automatic report</main>');sealed=automatic_overview_digest(page)
            bid,loci,fasta=run_export(root,'v1');self.assertEqual(fasta.read_bytes(),b'>edited-at-export\nTTCATACCCAGGG\n>new-chr-v1\nACA\n');bid2,_,fasta2=run_export(root,'v2',all_retained=True)
            batches={r['batch_sha256']:r['story'] for r in manual_batches(l)};self.assertEqual(set(batches),{bid,bid2});one=batches[bid];two=batches[bid2];a,extra=one['tracks'];self.assertEqual([p['start'] for p in a['before']],[0,3,7]);self.assertEqual(a['before'][0]['members'],[['App-assembly','flipped-ctg',1,4,'-']]);self.assertEqual((a['original_length'],a['length'],a['changed']),(9,13,3));self.assertEqual(extra['changed'],0)
            self.assertEqual([one['loci'][r['id']]['after'] for r in loci],[[5,8],[0,2],[10,13]]);gap=one['loci'][loci[0]['id']];self.assertEqual([r['status'] for r in gap['attempts']],['closed','closed','no_candidate']);self.assertEqual(gap['selected'],'degap');self.assertEqual(two['tracks'][1]['chr'],'new-chr-v2');self.assertEqual(two['tracks'][0]['changed'],0);self.assertIn(b'CATNNNNCA',fasta2.read_bytes());self.assertEqual(automatic_overview_digest(page),sealed)
            html=page.read_text();self.assertEqual(html.count('id="manual-refinement"'),1);self.assertIn('data-manual-select',html);self.assertNotIn('snapshot_objects/',html);self.assertNotIn('已导回 App</',html)
            path=l.path('05_final/details/manual-'+bid[:16]+'/selection.json');path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'selection.json changed'):manual_batches(l)
