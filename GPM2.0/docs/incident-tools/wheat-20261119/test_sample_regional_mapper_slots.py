import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sample_regional_mapper_slots as sample


class MapperSlotsTests(unittest.TestCase):
    def test_counts_only_bound_reader_children_and_distinguishes_launch_from_compute(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, proc = root/'work', root/'proc'
            work.mkdir(); proc.mkdir()
            owner = {'pid':101, 'process_start':'500', 'hostname':'node', 'workspace':str(work), 'run_id':'original'}
            (work/'.run_all/lock').mkdir(parents=True)
            lock = work/'.run_all/lock/owner.json'
            lock.write_text(json.dumps(owner))
            binding = {**owner,'reader_pid':102,'reader_start':502,'reader_command':'/bound/reader.py'}

            def make(path, pid, ppid, start, state, wait='0'):
                path.mkdir(parents=True)
                (path/'stat').write_text(f'{pid} (comm with ) space) {state} {ppid} '+ '0 '*17 +str(start))
                (path/'cgroup').write_text('scope original')
                (path/'wchan').write_text(wait)

            make(proc/'101',101,100,500,'S')
            make(proc/'102',102,101,502,'R')
            (proc/'102/cmdline').write_bytes(b'python3\0/bound/reader.py\0')
            thread = proc/'102/task/102'; make(thread,102,101,502,'S','do_wait')
            (thread/'children').write_text('103 104 105 106 999')
            region = work/'grt/evidence/q0_prepare/regional'
            region.mkdir(parents=True)
            for pid,parent,command,state in (
                    (103,102,b'/tool/minimap2\0-c\0', 'R'),
                    (104,102,b'python3\0/path/guard.py\0--address-space-bytes\0','D'),
                    (105,101,b'/tool/minimap2\0','D'),
                    (106,102,b'/tool/minimap2\0','S')):
                path = proc/str(pid); make(path,pid,parent,600+pid,state,'io_schedule')
                (path/'cmdline').write_bytes(command)
                (path/'cwd').symlink_to(region, target_is_directory=True)
            (proc/'106/cgroup').write_text('not original')
            with patch.object(sample,'PROC',proc), patch.object(sample.socket,'gethostname',return_value='node'):
                actual = sample.snapshot(work,binding)
                self.assertEqual(actual['reader_threads'],{'S':1})
                self.assertEqual(actual['reader_thread_waits'],{'do_wait':1})
                self.assertEqual(actual['reader_children'],[
                    {'kind':'native_precise','state':'R','wait':'running','count':1},
                    {'kind':'python_guard_before_exec','state':'D','wait':'io_schedule','count':1}])
                lock.write_text(json.dumps({**owner,'run_id':'new'}))
                with self.assertRaisesRegex(ValueError,'owner changed'):
                    sample.snapshot(work,binding)


if __name__ == '__main__':
    unittest.main()
