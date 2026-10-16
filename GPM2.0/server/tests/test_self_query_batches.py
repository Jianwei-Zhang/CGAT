from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"validation"))
from self_query_batches import plan_batches,validate_raw,publish,valid,Admission
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from alignment_tasks import AlignmentTask

class BatchTests(unittest.TestCase):
    def test_whole_record_order_and_skew(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'in.fa';data=b'>long comment\nAAAAAAAAAAAA\n>small\nCC\n>last\nGG\n';p.write_bytes(data)
            batches=plan_batches(p,root/'parts',5)
            self.assertEqual([b['bases'] for b in batches],[12,4])
            self.assertEqual(b''.join(Path(b['query']).read_bytes() for b in batches),data)
            self.assertEqual(batches,plan_batches(p,root/'parts',5))
    def test_successful_empty_result_and_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'result.paf';p.write_bytes(b'')
            validate_raw(p,[{'name':'q','length':10}],{'t':10})
            self.assertFalse(valid(root,'key',['result.paf']))
            publish(root,'key',['result.paf']);self.assertTrue(valid(root,'key',['result.paf']))
            p.write_text('bad');self.assertFalse(valid(root,'key',['result.paf']))
            with self.assertRaises(ValueError):validate_raw(p,[{'name':'q','length':10}],{'t':10})
    def test_admission_memory_and_cpu(self):
        tasks=[AlignmentTask(str(i),Path('/tmp')/str(i),4) for i in range(3)]
        f={str(i):{'memory':8,'work':30-i,'bases':12,'largest':4} for i in range(3)}
        grants=Admission(f,16)(tasks,8,8,[],3)
        self.assertEqual(len(grants),2);self.assertEqual(sum(n for _,n in grants),6)
        self.assertEqual(Admission(f,16)(tasks[1:],1,8,[{'task':tasks[0],'threads':3}],2),[])
    def test_duplicate_query_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'in.fa';p.write_text('>q\nAA\n>q\nTT\n')
            with self.assertRaises(ValueError):plan_batches(p,root/'parts',5)

class HotspotFixtureTests(unittest.TestCase):
    def test_windows_are_bounded_and_deduplicated(self):
        from self_hotspot_fixture import windows
        self.assertEqual(list(windows(100)), [('100-start', (0, 100))])
        selected = list(windows(60_000_000))
        self.assertEqual(len(selected), 6)
        self.assertTrue(all(0 <= lo < hi <= 60_000_000 for _, (lo, hi) in selected))

    def test_timeout_kills_descendant_not_just_wrapper(self):
        from self_hotspot_fixture import bounded
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            script = "import subprocess,time; p=subprocess.Popen(['sleep','30']); print(p.pid,flush=True); time.sleep(30)"
            result = bounded([sys.executable, '-c', script], root/'run', .3)
            self.assertEqual(result['status'], 'TIMEOUT')
            pid = int((root/'run/raw.paf').read_text().strip())
            status = Path(f'/proc/{pid}/status')
            try:
                lines = status.read_text().splitlines()
            except FileNotFoundError:
                lines = []
            if lines:
                state = next(x for x in lines if x.startswith('State:'))
                self.assertIn('Z', state)  # dead, waiting for its init reaper

    def test_comparison_uses_real_summary_keys(self):
        from self_hotspot_fixture import comparison
        from self_alignment_experiments import paf_summary
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'empty.paf'; p.touch()
            result = comparison(paf_summary(p), paf_summary(p))
            self.assertTrue(result['ordered_equal'])
            self.assertIsNone(result['strong_coverage_retained'])

if __name__=='__main__':unittest.main()
