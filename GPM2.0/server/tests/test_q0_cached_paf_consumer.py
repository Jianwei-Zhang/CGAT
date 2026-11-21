import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from server.tools.lgz_core import q0_preparation as prep
from server.tools.lgz_core.q0_catalog import CandidateCatalog, ObservedSourcePairs, add_pairwise_candidates
from server.tools.lgz_core.q0_regional_discovery import observe_part_hits
from server.tools.lgz_core.q0_sources import SourceKey, split_source, Q0EvidenceError


class CachedConsumerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        sources={SourceKey('a','q'):'A'*1000,SourceKey('b','t'):'A'*1000}
        parts={p.segment_id:p for key,seq in sources.items() for p in split_source(key,seq).segments}
        self.ids={p.source.contig:key for key,p in parts.items()};q,t=self.ids['q'],self.ids['t']
        self.catalog=CandidateCatalog({'candidates':[{'candidate_id':'anchor','segment_id':t,'chromosome':'chr',
            'orientation':'+','placement_kind':'reference'}],'evidence':{}},sources,parts)
        self.request={'kind':'unplaced_discovery','query_ids':[q],'target_ids':[t]}
        script=self.root/'mapper.py'
        script.write_text(f'''#!{sys.executable}
import sys
from pathlib import Path
args=sys.argv[1:]
if '--version' in args:print('cache-test-mapper 1.0');raise SystemExit(0)
def fasta(path):
 rows={{}};key=None
 for line in Path(path).read_text().splitlines():
  if line.startswith('>'):key=line[1:];rows[key]=''
  else:rows[key]+=line
 return rows
q=fasta(args[-1]);t=fasta(args[-2]);qn=next(iter(q));tn=next((name for name in t if name!=qn),next(iter(t)));n=min(len(q[qn]),len(t[tn]))
Path(args[args.index('-o')+1]).write_text(f'{{qn}}\\t{{len(q[qn])}}\\t0\\t{{n}}\\t+\\t{{tn}}\\t{{len(t[tn])}}\\t0\\t{{n}}\\t{{n}}\\t{{n}}\\t60\\tcg:Z:{{n}}M\\n')
''');script.chmod(0o755)
        self.tool=prep.executable_identity(str(script))
        self.task=prep._supplement(self.root,self.catalog,self.request,self.tool,'asm10',1)

    def cached(self,consumer=None):
        return prep._supplement(self.root,self.catalog,self.request,self.tool,'asm10',1,cache_only=True,on_cache_hit=consumer)

    def hits(self,task):
        return prep.read_paf(self.root/task['paf'],query_lengths={self.ids['q']:1000},
                             target_lengths={self.ids['t']:1000},artifact=task['paf'])

    def test_single_parse_matches_old_two_pass_evidence_and_cross_coverage(self):
        before=copy.deepcopy(self.catalog);after=copy.deepcopy(self.catalog)
        lengths={key:len(seq) for key,seq in before.sequences.items()}
        old_observed=ObservedSourcePairs(lengths);new_observed=ObservedSourcePairs(lengths)
        actual=prep.read_paf
        with mock.patch.object(prep,'read_paf',wraps=actual) as reader, \
             mock.patch.object(prep.subprocess,'run',side_effect=AssertionError('cached mapper must not run')):
            task=self.cached()
            old_added=add_pairwise_candidates(before,observe_part_hits(before,self.hits(task),old_observed),
                set(task['query_ids']),set(task['target_ids']),known_pairs=old_observed)
            self.assertEqual(reader.call_count,2)
            reader.reset_mock();captured={}
            def consume(task,hits):
                captured['added']=add_pairwise_candidates(after,observe_part_hits(after,hits,new_observed),
                    set(task['query_ids']),set(task['target_ids']),known_pairs=new_observed)
            fused=self.cached(consume)
            self.assertEqual(reader.call_count,1)
        self.assertEqual(fused,task);self.assertEqual(old_added,captured['added'])
        self.assertEqual(before.payload,after.payload);self.assertEqual(old_observed,new_observed)
        self.assertEqual({k:tuple(v) for k,v in old_observed.cross_coverage.items()},
                         {k:tuple(v) for k,v in new_observed.cross_coverage.items()})
        self.assertTrue(all(v['artifact']==task['paf'] for v in after.payload['evidence'].values()))

    def test_full_catalog_and_manifest_equal_legacy_two_pass_controller(self):
        qkey=next(k for k in self.catalog.sequences if k.contig=='q')
        tkey=next(k for k in self.catalog.sequences if k.contig=='t')
        qref=self.root/'runs/a_vs_ref/result.paf';qref.parent.mkdir(parents=True);qref.write_text('')
        tref=self.root/'runs/b_vs_ref/result.paf';tref.parent.mkdir(parents=True)
        tref.write_text('t\t1000\t0\t1000\t+\tchr\t10000\t0\t1000\t1000\t1000\t60\tcg:Z:1000M\n')
        def initial(root):
            return (self.catalog.sequences,{'chr':10000},[{'dataset_name':'b','seq_name':'t','assigned_chr_name':'chr'}],
                    {'minimap_preset':'asm10','skip_self':'false'},
                    [qref.relative_to(root).as_posix(),tref.relative_to(root).as_posix()],[],
                    ObservedSourcePairs({qkey:1000,tkey:1000}))
        real_supplement=prep._supplement;real_run=prep.subprocess.run
        def legacy(*args,**kwargs):
            kwargs.pop('on_cache_hit',None)
            return real_supplement(*args,**kwargs)
        def only_version(argv,*args,**kwargs):
            self.assertIn('--version',argv,'all cached mappings must be reused')
            return real_run(argv,*args,**kwargs)
        with mock.patch.object(prep,'_initial_inputs',side_effect=initial):
            with mock.patch.object(prep,'_supplement',side_effect=legacy):
                before=prep.prepare_evidence(self.root,minimap2=self.tool['command'])
            before_bytes=(self.root/before['catalog']).read_bytes()
            (self.root/prep.MANIFEST).unlink()  # Only this owned synthetic fixture.
            with mock.patch.object(prep.subprocess,'run',side_effect=only_version):
                after=prep.prepare_evidence(self.root,minimap2=self.tool['command'])
        self.assertEqual(before,after)
        self.assertEqual((self.root/after['catalog']).read_bytes(),before_bytes)
        tasks=json.loads(before_bytes)['supplementary_alignments']
        self.assertEqual(sum(task['kind']=='unplaced_discovery' for task in tasks),1)

    def test_early_consumer_still_validates_malformed_tail_without_mapper_retry(self):
        path=self.root/self.task['paf'];path.write_text(path.read_text()+'bad trailing PAF\n')
        marker=self.root/self.task['receipt'];receipt=json.loads(marker.read_text())
        receipt['outputs']=[prep.identity(self.root,r['path']) for r in receipt['outputs']]
        prep.atomic_write_json(marker,receipt)
        seen=[]
        with mock.patch.object(prep.subprocess,'run',side_effect=AssertionError('must not retry after partial consumption')):
            with self.assertRaises(Q0EvidenceError):self.cached(lambda task,hits:seen.append(next(hits)))
        self.assertEqual(len(seen),1)
        # Ordinary cache-only API keeps its prior invalid-cache behavior.
        self.assertIsNone(self.cached())
        self.assertFalse((self.root/'metadata/grt_q0_evidence.json').exists())

    def test_consumer_exception_aborts_without_recomputing_or_publishing(self):
        def fail(task,hits):
            next(hits);raise RuntimeError('semantic consumer failed')
        with mock.patch.object(prep.subprocess,'run',side_effect=AssertionError('no mapper retry')):
            with self.assertRaisesRegex(RuntimeError,'semantic consumer'):self.cached(fail)
        self.assertEqual(self.cached(),self.task)
        self.assertFalse((self.root/'metadata/grt_q0_evidence.json').exists())

    def test_output_content_and_bound_tool_are_checked_before_consumer(self):
        path=self.root/self.task['paf'];path.write_text(path.read_text().replace('\t60\t','\t59\t'))
        consumer=mock.Mock()
        self.assertIsNone(self.cached(consumer));consumer.assert_not_called()
        script=Path(self.tool['resolved']);script.write_text(script.read_text()+'\n# changed tool\n')
        with self.assertRaisesRegex(Q0EvidenceError,'aligner changed'):self.cached(consumer)
        consumer.assert_not_called()
        with self.assertRaisesRegex(Q0EvidenceError,'callable'):self.cached(True)

    def test_input_mutation_during_consumer_is_rejected_before_cache_return(self):
        receipt=json.loads((self.root/self.task['receipt']).read_text())
        fasta=next(r['path'] for r in receipt['outputs'] if r['path'].endswith('/query.fa'))
        def mutate(task,hits):
            list(hits);p=self.root/fasta;p.write_text(p.read_text().replace('A','C'))
        with mock.patch.object(prep.subprocess,'run',side_effect=AssertionError('no mapper retry')):
            with self.assertRaisesRegex(Q0EvidenceError,'changed during evidence consumption'):
                self.cached(mutate)
        self.assertFalse((self.root/'metadata/grt_q0_evidence.json').exists())

    def test_fused_consumer_receives_final_relative_artifact_and_identical_records(self):
        seen=[]
        self.cached(lambda task,hits:seen.extend(hits))
        expected=list(self.hits(self.task))
        self.assertEqual(seen,expected)
        self.assertEqual(seen[0].artifact,self.task['paf'])


if __name__=='__main__':unittest.main()
