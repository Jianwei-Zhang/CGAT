"""Cold application-index cost, not mapper-only or OS-cache-cold claims."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import benchmark_ordinary_preprocessing as prep
import ordinary_batch_performance as perf


class PreprocessingTests(unittest.TestCase):
    def test_plan_only_starts_no_mapper_and_creates_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'not-created'
            with patch.object(prep,'execute',side_effect=AssertionError('not plan-only')),redirect_stdout(io.StringIO()) as text:
                self.assertEqual(prep.main(['--target','ref','--query','q','--out',str(out)]),0)
            plan=json.loads(text.getvalue())
            self.assertFalse(plan['mapper_started']);self.assertFalse(out.exists())
            self.assertEqual(plan['plan']['batch_bases'],1_000_000_000)
            self.assertFalse(plan['production_admission'])

    def test_bounded_resources_and_expected_hash_are_checked_before_execution(self):
        for flags in (['--threads','0'],['--parallel-parts','9'],['--timeout','0'],
                      ['--expected-paf-sha256','nope'],['--control-index-bases','0']):
            with self.subTest(flags=flags),redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                prep.main(['--target','r','--query','q','--out','o',*flags])

    def test_default_policy_has_no_index_override_and_test_override_is_explicit(self):
        self.assertEqual(prep.index_flags(argparse.Namespace(control_index_bases=None)),[])
        self.assertEqual(prep.index_flags(argparse.Namespace(control_index_bases=600000000)),['-I','600000000'])

    def test_native_layout_conserves_reference_records_in_order(self):
        records=[{'name':str(i),'length':100} for i in range(5)]
        with patch.object(prep.perf,'parse_log',return_value={'parts':[{'target_records':3},{'target_records':2}]}),patch.object(prep.parts,'check_native_log') as check:
            log=unittest.mock.Mock();log.read_text.return_value='actual completion'
            layout=prep.native_layout(log,records,[],100)
            self.assertEqual(layout,[{'part_index':0,'records':records[:3]},{'part_index':1,'records':records[3:]}])
            self.assertEqual(check.call_count,1)
        for counts in ([3,3],[3],[0,5]):
            with patch.object(prep.perf,'parse_log',return_value={'parts':[{'target_records':i} for i in counts]}),self.assertRaises(ValueError):
                prep.native_layout(log,records,[],100)

    def test_preparation_is_not_hidden_in_mapper_only_speedup(self):
        runs=[{'mode':'native-fasta','execution_stage_wall_seconds':100,'preparation_wall_seconds':0,
               'mapping_and_merge_wall_seconds':98,'output_validation_wall_seconds':2},
              {'mode':'prepared-index','execution_stage_wall_seconds':120,'preparation_wall_seconds':60,
               'mapping_and_merge_wall_seconds':58,'output_validation_wall_seconds':2}]
        result=prep.summarize(runs)
        self.assertFalse(result['candidate_faster_in_this_control'])
        self.assertAlmostEqual(result['wall_reduction_percent'],-20)
        self.assertTrue(result['not_complete_CGAT_workflow_time'])
        self.assertTrue(result['not_OS_cache_cold_measurement'])
        with self.assertRaises(ValueError):prep.summarize(runs[:1])

    def test_source_content_or_execution_code_mutation_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.fa';source.write_text('>a\nACGT\n')
            row=prep.existing.catalog(source)
            prep.source_guard({'reference':row},{'tool':{'path':str(source),'sha256':perf.sha256(source)}})
            source.write_text('>a\nTCGT\n')
            with self.assertRaises(ValueError):prep.source_guard({'reference':row},{})
            with self.assertRaises(ValueError):prep.source_guard({},{'tool':{'path':str(source),'sha256':row['sha256']}})


class RealPreprocessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm=os.environ.get('CGAT_MINIMAP2_BINARY')
        if not cls.mm:raise unittest.SkipTest('explicit pinned mapper required')

    def args(self, root, target, query, **changes):
        args=argparse.Namespace(target=target,query=query,out=root/'comparison',minimap2=self.mm,
            threads=2,parallel_parts=2,memory_mib=4096,timeout=60,batch_bases=1_000_000_000,
            repeats=2,expected_parts=1,expected_paf_sha256=None,control_index_bases=None,min_free_gib=0)
        vars(args).update(changes)
        return args

    def test_fresh_default_single_index_total_cost_and_counterbalance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target,query=perf.generate(root,4,200000)
            with redirect_stdout(io.StringIO()):report=prep.execute(self.args(root,target,query))
            self.assertEqual(report['status'],'completed_same_layout_initial_reference_stage_comparison')
            self.assertEqual([r['mode'] for r in report['runs']],['native-fasta','prepared-index','prepared-index','native-fasta'])
            self.assertEqual(len({r['paf_sha256'] for r in report['runs']}),1)
            self.assertTrue(report['original_default_index_policy'])
            self.assertFalse(report['production_admission'])
            for row in report['runs']:
                self.assertGreaterEqual(row['execution_stage_wall_seconds'],row['preparation_wall_seconds']+row['mapping_and_merge_wall_seconds'])
                self.assertNotIn('-f',row['mapping']['command'])
                self.assertNotIn('-I',row['mapping']['command'])
                if row['mode']=='prepared-index':
                    self.assertTrue(row['index_context']['single_part_file_reused'])
                    self.assertFalse((Path(row['paf_path']).parent/'index-parts').exists())

    def test_wrong_independent_expected_output_fails_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target,query=perf.generate(root,4,200000)
            args=self.args(root,target,query,repeats=1,expected_paf_sha256='0'*64)
            with self.assertRaisesRegex(ValueError,'independently established'):prep.execute(args)
            report=json.loads((args.out/'benchmark.json').read_text())
            self.assertEqual(report['status'],'failed_no_recommendation')
            self.assertFalse((args.out/'r00-prepared-index').exists())
