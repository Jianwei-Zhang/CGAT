"""Final installed engine benchmark controls, not a substitute for large inputs."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import benchmark_ordinary_existing as existing
import audit_server_ordinary_parts as audit
import benchmark_server_ordinary_parts as bench
import replay_native_cell_merge as replay


class HarnessTests(unittest.TestCase):
    def test_plan_only_creates_nothing_and_starts_no_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);output=root/'not-created'
            args=['--target','absent.fa','--query','absent-query.fa','--out',str(output),
                  '--runtime-root','absent-runtime','--expected-runtime-profile','a'*64]
            with patch.object(subprocess,'Popen',side_effect=AssertionError('PLAN ONLY started process')),contextlib.redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(bench.main(args),0)
            self.assertFalse(output.exists());self.assertEqual(list(root.iterdir()),[])
            self.assertFalse(json.loads(stream.getvalue())['mapping_started'])

    def test_merge_replay_plan_needs_no_inputs_and_starts_no_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'not-created'
            with patch.object(subprocess,'Popen',side_effect=AssertionError('must not execute')),contextlib.redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(replay.main(['--runtime-root','absent','--profile','absent',
                    '--case-root','absent','--out',str(out)]),0)
            self.assertFalse(out.exists());self.assertFalse(json.loads(stream.getvalue())['mapping_started'])

    def test_whole_record_copies_preserve_case_wrapping_and_final_newline_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input.fa'
            original=b'>a comment\nacgt\nNn\n>b\nTGCA'
            source.write_bytes(original);catalog=existing.catalog(source,ordinary_query=True)
            result,proof=bench.copied_queries(catalog,root/'copies.fa',2)
            self.assertEqual(source.read_bytes(),original)
            self.assertEqual(result['total_bases'],2*catalog['total_bases'])
            self.assertEqual(result['records'],[{'name':'copy0000|a','length':6},{'name':'copy0000|b','length':4},
                {'name':'copy0001|a','length':6},{'name':'copy0001|b','length':4}])
            expected=b'>copy0000|a comment\nacgt\nNn\n>copy0000|b\nTGCA\n>copy0001|a comment\nacgt\nNn\n>copy0001|b\nTGCA'
            self.assertEqual((root/'copies.fa').read_bytes(),expected);self.assertTrue(proof['whole_records_preserved'])

    def test_single_copy_does_not_duplicate_original_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'q.fa';source.write_bytes(b'>q\nACGT\n')
            catalog=existing.catalog(source,ordinary_query=True)
            same,proof=bench.copied_queries(catalog,root/'copy.fa',1)
            self.assertEqual(same,catalog);self.assertFalse((root/'copy.fa').exists());self.assertFalse(proof['derived'])

    def test_independent_paf_audit_rejects_cigar_span_and_foreign_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.paf'
            valid='q\t4\t0\t4\t+\tt\t4\t0\t4\t4\t4\t60\tcg:Z:4M\n'
            path.write_text(valid)
            self.assertEqual(audit.paf(path,{'q':4},{'t':4},{'t':0}),1)
            for bad in (valid.replace('4M','3M'),valid.replace('\tt\t','\tforeign\t'),valid.rstrip('\n')):
                path.write_text(bad)
                with self.assertRaises(ValueError):audit.paf(path,{'q':4},{'t':4},{'t':0})

    def test_independent_log_audit_rejects_skipped_query_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.stderr'
            path.write_text('[M::main::0.1] loaded/built the index for 1 target sequence(s)\n'
                '[M::mm_mapopt_update::0.1] mid_occ = 500\n'
                '[M::worker_pipeline::0.2] mapped 3 sequences\n'
                '[M::main] Real time: 0.2 sec; CPU: 0.4 sec; Peak RSS: 0.1 GB\n')
            with self.assertRaisesRegex(ValueError,'batches'):
                audit.native_log(path,[{'records':[{'name':'t','length':100}]}],[{'length':60}]*3,100)

    def test_independent_checksum_manifest_rejects_corruption_duplicates_and_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);payload=root/'payload';payload.write_bytes(b'frozen')
            line=hashlib.sha256(payload.read_bytes()).hexdigest()+'  payload\n'
            manifest=root/'SHA256SUMS';manifest.write_text(line)
            self.assertEqual(audit.checksum_manifest(root,'SHA256SUMS'),{'payload':audit.sha(payload)})
            for text in (line+line,line.replace('payload','../payload'),''):
                manifest.write_text(text)
                with self.assertRaises(ValueError):audit.checksum_manifest(root,'SHA256SUMS')
            manifest.write_text(line);payload.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'bytes changed'):audit.checksum_manifest(root,'SHA256SUMS')
            payload.unlink();payload.symlink_to(root/'SHA256SUMS')
            with self.assertRaises(ValueError):audit.checksum_manifest(root,'SHA256SUMS')
            with self.assertRaises(ValueError):audit.checksum_manifest(root,'../SHA256SUMS')

    def test_independent_allocation_checks_grants_not_affinity_or_requested_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'allocation.json'
            grant={'resReq':{'cpu':64,'mem':224000},'resAlloc':{'cpu':64,'mem':224000},
                   'resLimit':{'cpu':0,'mem':327680}}
            def save():path.write_text(json.dumps([{'jobId':'40886112','resource_grants':[grant]}]))
            save();result=audit.allocation(root,64,192*1024**3)
            self.assertEqual(result['reported_memory_limit_MB'],327680)
            self.assertEqual(result['allocated_memory_MB'],224000)
            grant['resAlloc']['cpu']=32;save()
            with self.assertRaisesRegex(ValueError,'CPU differ'):audit.allocation(root,64,192*1024**3)
            grant['resAlloc']['cpu']=64;grant['resLimit']['mem']=100000;save()
            with self.assertRaisesRegex(ValueError,'budget'):audit.allocation(root,64,192*1024**3)

    def test_runtime_source_corruption_is_rejected_without_importing_or_executing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);file=root/'ordinary_partition_alignment.py';file.write_text('raise AssertionError("must not import")\n')
            files={file.name:hashlib.sha256(file.read_bytes()).hexdigest()}
            profile=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            (root/'branch-runtime.json').write_text(json.dumps({'files_sha256':files}))
            file.write_text('changed\n')
            with self.assertRaisesRegex(ValueError,'source changed'):bench.runtime(root,profile)


class RealEngineHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm=os.environ.get('CGAT_MINIMAP2_BINARY')
        if not cls.mm:raise unittest.SkipTest('explicit pinned mapper required')

    def test_fresh_installed_sources_real_two_part_comparison_and_source_mutation_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runtime=root/'runtime';runtime.mkdir()
            installed=Path(__file__).resolve().parents[2]/'server/tools/long_cigar_recovery'
            manifest=json.loads((installed/'branch-runtime.json').read_text())
            for name in manifest['files_sha256']:shutil.copyfile(installed/name,runtime/name)
            shutil.copyfile(installed/'branch-runtime.json',runtime/'branch-runtime.json')
            profile=hashlib.sha256(json.dumps(manifest['files_sha256'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
            rng=random.Random(2311302);sequence=bytes(rng.choices(b'ACGT',k=120000))
            target=root/'ref.fa';target.write_bytes(b'>t1\n'+sequence+b'\n>t2\n'+bytes(rng.choices(b'ACGT',k=120000))+b'\n')
            query=root/'q.fa';query.write_bytes(b''.join(b'>q'+str(i).encode()+b'\n'+sequence[1000+i:41000+i]+b'\n' for i in range(6)))
            args=[sys.executable,'-B',str(Path(bench.__file__).resolve()),'--target',str(target),'--query',str(query),
                '--out',str(root/'comparison'),'--runtime-root',str(runtime),'--expected-runtime-profile',profile,
                '--minimap2',self.mm,'--threads','4','--memory-mib','8192','--batch-bases','100000',
                '--control-index-bases','100000','--expected-parts','2','--repeats','2','--min-free-gib','0','--execute']
            result=subprocess.run(args,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr[-8000:])
            report=json.loads((root/'comparison/benchmark.json').read_text())
            self.assertEqual(report['status'],'complete_equal');self.assertEqual(len(report['runs']),4)
            self.assertEqual([r['mode'] for r in report['runs']],['native-mmi','server-original-parts','server-original-parts','native-mmi'])
            self.assertEqual(len({r['paf_sha256'] for r in report['runs']}),1)
            self.assertTrue(all(r['combination']['all_cells_completed'] for r in report['runs']))
            self.assertTrue(all(r['private_digest_memo_reset'] for r in report['runs']))
            self.assertFalse(report['automatic_memory_discovery_tested'])
            independently=audit.case(root/'comparison')
            self.assertEqual(independently['paf_sha256'],report['runs'][0]['paf_sha256'])
            self.assertEqual(independently['paf_rows'],[r['paf_rows'] for r in report['runs']])
            replay_out=root/'replayed'
            replay_command=[sys.executable,'-B',str(Path(replay.__file__)),
                '--runtime-root',str(runtime),'--profile',profile,
                '--case-root',str(root/'comparison'),'--out',str(replay_out),'--execute']
            replayed=subprocess.run(replay_command,capture_output=True,text=True,timeout=30)
            self.assertEqual(replayed.returncode,0,replayed.stderr+replayed.stdout)
            replay_report=json.loads((replay_out/'replay.json').read_text())
            self.assertEqual(replay_report['paf_sha256'],report['runs'][0]['paf_sha256'])
            self.assertFalse(replay_report['mapping_started'])
            self.assertEqual((replay_out/'complete.paf').read_bytes(),Path(report['runs'][0]['output_path']).read_bytes())
            final=Path(report['runs'][0]['output_path']);original=final.read_bytes();final.write_bytes(original+b'corrupt\n')
            with self.assertRaises(ValueError):audit.case(root/'comparison')
            final.write_bytes(original)
            # A changed source fails before mapping rather than reusing the old
            # complete experiment, retrying a mapper or inventing a new layout.
            bad=args.copy();bad[bad.index('--out')+1]=str(root/'bad')
            (runtime/'ordinary_partition_alignment.py').write_text('changed\n')
            result=subprocess.run(bad,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertFalse((root/'bad').exists())


if __name__=='__main__':unittest.main()
