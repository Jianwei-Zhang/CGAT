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
import benchmark_server_ordinary_parts as bench


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
            # A changed source fails before mapping rather than reusing the old
            # complete experiment, retrying a mapper or inventing a new layout.
            bad=args.copy();bad[bad.index('--out')+1]=str(root/'bad')
            (runtime/'ordinary_partition_alignment.py').write_text('changed\n')
            result=subprocess.run(bad,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertFalse((root/'bad').exists())


if __name__=='__main__':unittest.main()
