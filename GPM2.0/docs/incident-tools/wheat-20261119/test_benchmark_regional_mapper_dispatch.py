import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest

path=Path(__file__).with_name('benchmark_regional_mapper_dispatch.py')
spec=importlib.util.spec_from_file_location('mapper_dispatch_control',path)
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)


class MapperDispatchControlTests(unittest.TestCase):
    def test_replay_waits_for_fifo_head_and_reclaims_any_ready_slot(self):
        self.assertEqual(control.replay([8.,1.,1.,1.],2,'ordered'),9.)
        self.assertEqual(control.replay([8.,1.,1.,1.],2,'completed'),8.)
        for workers in (1,2,7,14):
            self.assertEqual(control.replay([2.]*28,workers,'ordered'),control.replay([2.]*28,workers,'completed'))
        self.assertEqual(control.replay([0.,0.],2,'completed'),0.)

    def test_bad_budget_or_service_times_are_fatal(self):
        for values,workers,mode in (([],1,'ordered'),([True],1,'ordered'),([float('nan')],1,'ordered'),
            ([-1],1,'completed'),([1],True,'ordered'),([1],0,'ordered'),([1],1,'unknown')):
            with self.subTest(args=(values,workers,mode)),self.assertRaises(ValueError):control.replay(values,workers,mode)

    def test_window_reconstruction_lf_crlf_and_uppercase(self):
        for newline in (b'\n',b'\r\n'):
            with self.subTest(newline=newline),tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'source.fa';p.write_bytes(b'>s'+newline+b'acgt'+newline+b'tgaa'+newline+b'CC'+newline)
                for start,end in ((0,10),(0,4),(3,8),(4,5),(8,10)):
                    self.assertEqual(control.window_bytes(p,(10,2+len(newline),4,4+len(newline)),start,end),'ACGTTGAACC'[start:end])
                with self.assertRaises(ValueError):control.window_bytes(p,(10,2+len(newline),4,4+len(newline)),0,11)
                with self.assertRaises(ValueError):control.window_bytes(p,(10,2+len(newline),0,4),0,1)
                p.write_bytes(b'>s\nAC')
                with self.assertRaises(ValueError):control.window_bytes(p,(10,3,4,5),0,10)

    def test_completed_dispatch_replenishes_with_original_result_order(self):
        last=threading.Event();active=peak=0;lock=threading.Lock()
        def run(ordinal,case):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            try:
                if ordinal==0:self.assertTrue(last.wait(3),'slow first task must not block admission')
                if ordinal==2:last.set()
                return case
            finally:
                with lock:active-=1
        result,order=control.dispatch(['a','b','c'],run,2,'completed')
        self.assertEqual(result,['a','b','c']);self.assertEqual(order[0],1);self.assertLessEqual(peak,2)
        self.assertEqual(active,0)

    def test_both_modes_propagate_failure_and_keep_serial_result_order(self):
        for mode in ('ordered','completed'):
            result,_=control.dispatch([3,2,1],lambda _i,x:x,1,mode)
            self.assertEqual(result,[3,2,1])
            def bad(*_args):raise RuntimeError('native stdout changed')
            with self.assertRaisesRegex(RuntimeError,'native stdout changed'):control.dispatch([1,2],bad,2,mode)

    def test_input_bounds_and_escapes_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'input.json';p.write_text('{}')
            self.assertEqual(control.read_json(p),{})
            with self.assertRaises(ValueError):control.read_json(p,1)
            for name in ('../input.json',str(p)):
                with self.assertRaises(ValueError):control.within(root,name)
            link=root/'linked.json';link.symlink_to(p)
            with self.assertRaises(ValueError):control.read_json(link)


if __name__=='__main__':unittest.main()
