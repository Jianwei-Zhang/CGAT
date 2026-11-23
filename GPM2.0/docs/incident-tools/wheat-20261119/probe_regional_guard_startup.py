"""Time the regional mapper launch path with a tiny non-mapper child.

Compare constant memory/process-group semantics; this is not a scientific
benchmark. Never changes production files or limits. No sequence input.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time


LIMIT = 4 * 1024**3
MODES = ('current', 'no_site', 'local_guard', 'prlimit')
CHILD = ['/bin/bash', '--noprofile', '--norc', '-c',
         'read -r pid comm state ppid pgrp rest < /proc/self/stat; '
         'printf "%s\\n" "$pid" "$pgrp" "$(ulimit -S -v)" "$(ulimit -H -v)"']


def argv_for(mode, guard, local_guard, python, prlimit):
    if mode == 'prlimit':
        return [str(prlimit), f'--as={LIMIT}:{LIMIT}', '--', *CHILD]
    if mode not in MODES:
        raise ValueError('unknown launch mode')
    path = local_guard if mode == 'local_guard' else guard
    return [str(python), *(['-S'] if mode == 'no_site' else []), str(path),
            '--address-space-bytes', str(LIMIT), '--', *CHILD]


def validate_child(stdout, child_pid, parent_group):
    values = [int(s) for s in stdout.splitlines()]
    if values != [child_pid, parent_group, LIMIT//1024, LIMIT//1024]:
        raise ValueError(f'guard did not exec with the inherited process group and both limits: {values}')


def run_one(root, local, source, mode, index, prlimit):
    t = time.monotonic()
    path = root / str(index)
    path.mkdir()
    guard = path / 'guard.py'; local_guard = local / f'guard-{index}.py'
    shutil.copyfile(source, guard)
    if mode == 'local_guard': shutil.copyfile(source, local_guard)
    cmd = argv_for(mode, guard, local_guard, sys.executable, prlimit)
    (path / 'command.json').write_text(json.dumps(cmd)+'\n')
    recorded = time.monotonic()
    with (path / 'stdout').open('wb') as output, (path / 'stderr').open('wb') as error:
        opened = time.monotonic()
        child = subprocess.Popen(cmd, cwd=path, stdout=output, stderr=error)
        spawned = time.monotonic()
        try:
            code = child.wait(timeout=90)
        except subprocess.TimeoutExpired:
            child.kill(); child.wait(); raise
        exited = time.monotonic()
    if code != 0: raise RuntimeError(f'{mode} launch failed: {path}/stderr ({code})')
    validate_child((path / 'stdout').read_text(), child.pid, os.getpgrp())
    return {'ordinal':index,'mode':mode,'prepare_seconds':recorded-t,'open_seconds':opened-recorded,
            'popen_seconds':spawned-opened,'child_seconds':exited-spawned,
            'after_record_seconds':exited-recorded,'total_seconds':time.monotonic()-t}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--guard', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args(); guard=a.guard.resolve(strict=True); out=a.output.resolve()
    prlimit=Path('/usr/bin/prlimit')
    modes=[m for m in MODES if m!='prlimit' or prlimit.is_file()]
    out.mkdir(exist_ok=False)
    rows=[]
    # One batch of four, then reversed, always inside the four-core allocation.
    with tempfile.TemporaryDirectory(prefix='cgat-guard-probe-',dir='/tmp') as scratch:
        local=Path(scratch)
        with ThreadPoolExecutor(max_workers=len(modes)) as pool:
            for phase,order in enumerate((modes,list(reversed(modes)),modes)):
                futures=[pool.submit(run_one,out,local,guard,m,phase*len(modes)+i,prlimit)
                         for i,m in enumerate(order)]
                for f in futures:
                    row=f.result(); rows.append(row); print(json.dumps(row),flush=True)
    fields=('prepare_seconds','open_seconds','popen_seconds','child_seconds','after_record_seconds','total_seconds')
    medians={m:{k:statistics.median(r[k] for r in rows if r['mode']==m) for k in fields} for m in modes}
    report={'status':'diagnostic_launch_comparison_NOT_production_validation','host':socket.gethostname(),
            'guard_sha256':hashlib.sha256(guard.read_bytes()).hexdigest(),'python':sys.executable,
            'child_pid_process_group_and_soft_hard_as_verified':True,'mapper_input_read':False,
            'main_workspace_modified':False,'rows':rows,'medians':medians}
    (out/'summary.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'medians':medians}),flush=True)


if __name__=='__main__': main()
