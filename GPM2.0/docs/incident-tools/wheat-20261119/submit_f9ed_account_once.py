"""Single accounting handoff for 43054692; never submits a mapper or a wheat producer."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

JOB = '43054692'
REV = 'f9ed324f3984efc41eb780159f8294b5f4db2545'
SNAP = '451a42a602e5359a3783e1fc139620ba3a1b47d74bfe55b46e1d8c94e66e9512'
BATCH = 'account_f9ed_whole_request.dsub'
BATCH_SHA = '0d0b9937b31936dd586294c4f8f1f457848c43d5da2164644ad221361c5f2dcf'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def tail(path, n):
    with path.open('rb') as f:
        f.seek(max(0, os.fstat(f.fileno()).st_size - n))
        return f.read()


def scheduler(*args):
    reply = json.loads(subprocess.check_output(['djob', *args], timeout=40))
    require(reply['code'] == 'success', 'scheduler query unsuccessful')
    return reply


def small(path, cap):
    require(path.resolve() == path and path.is_file() and 0 < path.stat().st_size <= cap, str(path))
    with path.open('rb') as f:
        data = f.read(cap + 1)
    require(0 < len(data) <= cap, 'input grew during read')
    return data


def record(path, doc):
    # O_EXCL on the shared mount: never retry a submission with an ambiguous reply.
    with path.open('x') as f:
        json.dump(doc, f, sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())


def submit():
    run = Path.home()/'cgat-reads-debug/jm19-compare-614589f-20261118/q0-request-ready.f9ed324f'
    out = run/'accounting'; os.umask(0o077)
    require(socket.gethostname().split('.')[0] == 'cli-X86-01' and run.resolve() == run and out.resolve() == out, 'wrong host or directory')
    job, = scheduler('-ll', '-J', JOB)['data']['successData']
    require((job['jobId'], job['jobName'], job['user'], job['queue'], job['state'], job['exitCode'], job['taskExecNodes'], job['execPath'], job['cmd']) ==
            (JOB, 'jm19_whole_request_f9ed', 'xbzhang26', 'x86', 'SUCCEEDED', 0, 'agent-X86-64', str(run), str(run/'retry-x86-pool/whole.dsub')), 'producer identity or result differs')
    sha = lambda data: hashlib.sha256(data).hexdigest()
    require(small(run/'whole.jobid', 32).strip() == JOB.encode() and sha(small(run/'control/snapshot.json', 256 << 10)) == SNAP, 'wrong fork')
    raw = small(run/'control/global-first-request.json', 64 << 20); req = json.loads(raw); digest = sha(raw)
    require(req['schema'] == 'wheat_threshold_global_first_request_v1' and req['revision'] == REV and req['snapshot_sha256'] == SNAP and
            req['published_q0'] is False and type(req['mapper_calls']) is int and req['mapper_calls'] == 0 and type(req['has_path']) is bool and
            (req['request'] is None or isinstance(req['request'], list)), 'not a whole-wheat first request')
    require((digest + '  control/global-first-request.json').encode() in tail(run/('whole_'+JOB+'.out'), 65536).splitlines(), 'producer did not attest these exact bytes')
    require(sha(small(out/BATCH, 16384)) == BATCH_SHA and os.access(out/BATCH, os.X_OK), 'accounting batch changed')
    require(not os.path.lexists(out/'result') and not list(out.glob('account_[0-9]*.out')) and not os.path.lexists(out/'submit-reply.json'), 'accounting already attempted')
    require(scheduler('-u','xbzhang26','-n','jm19_f9ed_first_demand','-s','all','-J')['totalElements'] == 0, 'accounting job already present')
    record(out/'submit-intent.json', {'producer': JOB, 'request_sha256': digest, 'batch_sha256': BATCH_SHA})
    response = subprocess.run(['dsub','-s',BATCH], cwd=str(out), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    text = response.stdout.decode(errors='replace'); match = re.fullmatch(r'\s*Submit job <([0-9]+)> successfully\.\s*', text)
    accepted = match.group(1) if response.returncode == 0 and match else None
    record(out/'submit-reply.json', {'code':response.returncode, 'message':text, 'job':accepted})
    require(accepted is not None, 'submission was not confirmed; inspect the intent and scheduler before any manual action')
    print('ACCOUNT_SUBMITTED', accepted, digest, flush=True)


def watch():
    # Reuse the read-only service's existing samples. No new Donau polling while the producer is running.
    log = Path.home()/'.cache/cgat-wheat-watch'/JOB/'progress.log'
    while True:
        sample = tail(log, 16384).rsplit(b'\nSAMPLE ', 1)[-1].splitlines()
        if any(row.startswith(b'POLL_FAILED ') for row in sample):
            time.sleep(60); continue
        states = [row.split()[2] for row in sample if row.startswith(b'STATE 43054692 ')]
        if states == [b'SUCCEEDED']:
            break  # SSH rechecks the real terminal state, identity and request, not just this hint.
        if len(states) == 1 and states[0] in {b'FAILED',b'ENDED',b'LOST',b'CANCELED',b'CANCELLED'}:
            print('NO_ACCOUNT_FOR_TERMINAL_PRODUCER', states[0].decode(), flush=True); return
        time.sleep(60)
    with Path(__file__).open('rb') as script:
        subprocess.run(['rtk','proxy','ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-p','18083','180',
                        "bash -lc 'python3 - submit'"], stdin=script, check=True, timeout=240)


if __name__ == '__main__':
    require(sys.argv[1:] in (['watch'], ['submit']), 'use watch locally or submit on the verified Donau login')
    watch() if sys.argv[1] == 'watch' else submit()
