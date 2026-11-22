"""Sample only a verified running wheat reader's own child processes and thread states.

No attachment, signals, open-data inspection, or analysis workspace writes.
Counts are instantaneous and include launching Python guards separately from
native mappers. Samples cannot assign all gap time to one wait channel.
"""
import argparse
from collections import Counter
import datetime
import json
import os
from pathlib import Path
import socket
import time

PROC = Path('/proc')


def proc_stat(path):
    values = (path/'stat').read_text().rsplit(')', 1)[1].split()
    return values[0], int(values[1]), int(values[19])


def wait_site(path):
    try:
        return (path/'wchan').read_text().strip()
    except OSError:
        return 'unavailable'


def snapshot(work, binding):
    owner = json.loads((work/'.run_all/lock/owner.json').read_text())
    if any(owner.get(k) != binding[k] for k in ('pid', 'run_id', 'hostname', 'process_start', 'workspace')):
        raise ValueError('original workspace owner changed')
    if socket.gethostname() != binding['hostname'] or binding['workspace'] != str(work):
        raise ValueError('wrong compute node or workspace')
    reader, controller = (PROC/str(binding[k]) for k in ('reader_pid','pid'))
    if reader.stat().st_uid != os.getuid() or controller.stat().st_uid != os.getuid():
        raise ValueError('not the original own-UID process tree')
    cgroup = (controller/'cgroup').read_bytes()
    if (proc_stat(controller)[2] != int(binding['process_start'])
            or proc_stat(reader)[1:] != (binding['pid'],binding['reader_start'])
            or (reader/'cgroup').read_bytes() != cgroup):
        raise ValueError('original process identity or job cgroup changed')
    argv = (reader/'cmdline').read_bytes().split(b'\0')
    if os.fsencode(binding['reader_command']) not in argv:
        raise ValueError('original reader command changed')
    child_ids = set()
    thread_state, thread_wait = Counter(), Counter()
    for thread in (reader/'task').iterdir():
        try:
            child_ids.update(int(x) for x in (thread/'children').read_text().split())
            state = proc_stat(thread)[0]
            thread_state[state] += 1
            if state != 'R':
                thread_wait[wait_site(thread)] += 1
        except (OSError, ValueError, IndexError):
            continue
    counts = Counter()
    regional = work/'grt/evidence/q0_prepare/regional'
    for pid in sorted(child_ids):
        path = PROC/str(pid)
        try:
            if path.stat().st_uid != os.getuid() or (path/'cgroup').read_bytes() != cgroup:
                continue
            state, parent, started = proc_stat(path)
            if parent != binding['reader_pid']:
                continue
            command = (path/'cmdline').read_bytes().split(b'\0')
            cwd = Path(os.readlink(path/'cwd'))
            if proc_stat(path)[1:] != (parent, started):
                continue
            kind = 'other_reader_child'
            if cwd.is_relative_to(regional):
                if Path(os.fsdecode(command[0])).name.startswith('minimap2'):
                    kind = 'native_precise' if b'-c' in command else 'native_chaining'
                elif any(arg.endswith(b'/guard.py') for arg in command) and b'--address-space-bytes' in command:
                    kind = 'python_guard_before_exec'
                else:
                    kind = 'regional_pre_exec_or_other'
            counts[(kind,state,wait_site(path) if state != 'R' else 'running')] += 1
        except (OSError, ValueError, IndexError):
            continue
    if proc_stat(reader)[1:] != (binding['pid'],binding['reader_start']):
        raise ValueError('reader changed during observation')
    return {'at':datetime.datetime.now().astimezone().isoformat(), 'reader_threads':dict(thread_state),
            'reader_thread_waits':dict(thread_wait),
            'reader_children':[{'kind':k,'state':s,'wait':w,'count':n} for (k,s,w),n in sorted(counts.items())]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config',type=Path)
    args = parser.parse_args()
    config = args.config.resolve(strict=True)
    binding = json.loads(config.read_text())
    work = Path(binding['workspace']).resolve(strict=True)
    if config.parent == work or config.parent.is_relative_to(work):
        raise ValueError('diagnostic output must remain outside the workspace')
    with (config.parent/'samples.jsonl').open('x') as stream:
        for i in range(12):
            row = snapshot(work,binding)
            print(json.dumps(row,sort_keys=True),file=stream,flush=True)
            if i < 11:
                time.sleep(5)


if __name__ == '__main__':
    main()
