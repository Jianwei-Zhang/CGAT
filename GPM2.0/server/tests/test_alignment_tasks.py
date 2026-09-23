from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from alignment_tasks import AlignmentTask, allocate_threads, run_tasks


class AlignmentTasksTests(unittest.TestCase):
    def test_allocation_returns_capacity_from_single_query_jobs(self):
        self.assertEqual(allocate_threads([1, 32, 1], 32), [1, 30, 1])
        self.assertEqual(allocate_threads([1] * 36, 32), [1] * 32)
        self.assertEqual(allocate_threads([32, 32], 1), [1])

    def test_actual_processes_overlap_without_exceeding_thread_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            worker = root / "worker.py"
            worker.write_text('''import fcntl, json, os, time
from pathlib import Path
root = Path.cwd()
name = os.environ['GPM_REPORT_UNIT_ID']
threads = int(os.environ['GPM_TASK_THREADS'])
def update(delta):
    with (root/'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root/'usage.json'
        data = json.loads(path.read_text()) if path.exists() else {'active':0,'peak':0}
        data['active'] += delta
        data['peak'] = max(data['peak'], data['active'])
        path.write_text(json.dumps(data))
update(threads)
(root/(name+'.ready')).touch()
deadline = time.monotonic()+10
while len(list(root.glob('*.ready'))) < 3:
    if time.monotonic() > deadline: raise RuntimeError('tasks did not overlap')
    time.sleep(.01)
print(name, threads, flush=True)
update(-threads)
''')
            command = root / "command.sh"
            command.write_text(f'exec "{sys.executable}" "{worker}"\n')
            children, lines, finished = {}, [], []
            code = run_tasks(
                [AlignmentTask(str(index), command, cap) for index, cap in enumerate([1, 4, 1])],
                4, children, lambda: None, lambda *_: None,
                lambda task, line: lines.append((task.unit_id, line)),
                lambda task, status, _: finished.append(status), os.environ.copy(),
            )
            self.assertEqual(code, 0)
            self.assertEqual(finished, [0, 0, 0])
            self.assertEqual(json.loads((root / "usage.json").read_text()), {"active": 0, "peak": 4})
            self.assertEqual(len(lines), 3)
            self.assertFalse(children)

    def test_failure_cancels_sibling_and_does_not_start_pending_task(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bodies = [
                'sleep 30 &\nwhile [[ ! -f peer.ready ]]; do sleep .01; done\nexit 17\n',
                'touch peer.ready\nsleep 30\ntouch should_not_finish\n',
                'touch should_not_start\n',
            ]
            tasks = []
            for index, body in enumerate(bodies):
                path = root / f"{index}.sh"
                path.write_text(body)
                tasks.append(AlignmentTask(str(index), path, 1))
            finished = []
            started = time.monotonic()
            code = run_tasks(tasks, 2, {}, lambda: None, lambda *_: None,
                             lambda *_: None, lambda task, status, _: finished.append((task.unit_id, status)),
                             os.environ.copy())
            self.assertEqual(code, 17)
            self.assertLess(time.monotonic() - started, 5, "failed descendant retained stdout")
            self.assertEqual(dict(finished)["0"], 17)
            self.assertNotEqual(dict(finished)["1"], 0)
            self.assertFalse((root / "should_not_start").exists())
            self.assertFalse((root / "should_not_finish").exists())


if __name__ == "__main__":
    unittest.main()
