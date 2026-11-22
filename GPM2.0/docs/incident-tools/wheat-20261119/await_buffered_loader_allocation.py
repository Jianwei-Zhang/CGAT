"""After the real buffered preflight, request one waiting-only x86 allocation.

Never stops jobs, releases a handoff, or writes the analysis workspace. Keep
submission intent across errors: an ambiguous dsub return is not repeatable.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from await_buffered_preflight_retry import ObservationUnavailable, exclusive_json, query
from prepare_q0_loader_launch import prepare, record
from probe_q0_loader_allocation import checked

SUBMISSION = re.compile(r'\s*Submit job <([1-9][0-9]*)> successfully\.\s*')
ACTIVE = frozenset(('PENDING', 'WAITING', 'RUNNING'))


def read(path):
    if path.is_symlink():
        raise ValueError('linked incident metadata')
    return json.loads(path.read_text())


def live_owner(stage, work, watched):
    main, baseline = (query(watched[key]) for key in ('running_job', 'baseline_job'))
    if main['state'] != 'RUNNING' or baseline['state'] != 'RUNNING':
        raise ValueError('current NEW or protected baseline changed state')
    owner = read(work/'.run_all/lock/owner.json')
    if (owner.get('run_id') != watched['running_run_id'] or owner.get('workspace') != str(work)
            or owner.get('hostname') != main.get('taskExecNodes')
            or (work/'metadata/grt_q0_evidence.json').exists() or (stage/'handoff.json').exists()):
        raise ValueError('current workspace or phase changed')
    return owner


def advance(stage, buffered, environment, watched):
    match = SUBMISSION.fullmatch((buffered/'submit.txt').read_text())
    if not match:
        raise ValueError('buffered preflight has no unambiguous submit receipt')
    job_id = match[1]
    if job_id in {str(watched[k]) for k in ('running_job', 'baseline_job', 'preflight_job', 'smoke_job')}:
        raise ValueError('buffered diagnostic cannot stand in for another job')
    preflight = query(job_id)
    if preflight['state'] in ACTIVE:
        return 'waiting_for_same_preflight_terminal', None
    if (preflight['state'] != 'SUCCEEDED' or preflight.get('jobExitCode') != 0
            or preflight.get('endTime') in (None, '-')
            or Path(preflight['cmd']) != buffered/'run.dsub' or Path(preflight['execPath']) != buffered):
        raise ValueError('buffered preflight did not finish successfully at its bound path')
    proof = buffered/'buffered-proof.json'
    if not proof.exists():
        return 'waiting_for_committed_buffered_proof', None
    smoke = query(watched['smoke_job'])
    if smoke['state'] != 'SUCCEEDED' or smoke.get('jobExitCode') != 0:
        raise ValueError('frozen writer smoke is not a confirmed success')
    transition = read(checked(watched['transition'], stage))
    checked(watched['loader_smoke'], stage)
    candidate = read(checked(watched['candidate'], stage))
    work = Path(transition['workspace']).resolve(strict=True)
    if (stage.is_relative_to(work) or buffered.is_relative_to(work) or stage.parent != buffered.parent
            or candidate['transition'] != watched['transition']
            or candidate['previous_job'] != watched['running_job']
            or candidate['protected_baseline'] != watched['baseline_job']
            or record(environment) != watched['environment']):
        raise ValueError('prepare scope drifted')
    owner = live_owner(stage, work, watched)
    for name in ('validation.json', 'handoff-config.json', 'resume.dsub', 'resource-launch.sha256',
                 'loader-resource-submit-intent.json', 'loader-resource-submitted.json',
                 'loader-ready.json', 'ready.json', 'handoff.json'):
        marker = stage/name
        if marker.exists() or marker.is_symlink():
            raise ValueError('handoff has already advanced: '+name)
    intent = stage/'loader-resource-submit-intent.json'
    scheduler = buffered/f'terminal-{job_id}.json'
    # Store the actual detailed Donau row in the format the independently
    # staged verifier expects. A pre-existing receipt is never overwritten.
    exclusive_json(scheduler, {'data': {'successData': [preflight]}})
    exclusive_json(intent, {'state': 'submit_once_waiting_only_buffered_preflight',
        'buffered_proof': record(proof), 'buffered_scheduler': record(scheduler), 'old_owner': owner})
    result = prepare(stage, environment, buffered_proof=proof, buffered_scheduler=scheduler, allocation_replay=True)
    if live_owner(stage, work, watched) != owner:
        raise ValueError('original owner changed while preparing; no submit attempted')
    script = checked(result['script'], stage)
    stdout = subprocess.check_output(['dsub','-s',str(script)], cwd=stage, text=True, timeout=60)
    submitted = SUBMISSION.fullmatch(stdout)
    if submitted is None:
        raise ValueError('ambiguous dsub result; inspect Donau, do not retry')
    receipt = {'state': 'resource_job_submitted_waiting_only', 'resource_job': int(submitted[1]),
               'running_job': watched['running_job'], 'baseline_job': watched['baseline_job'],
               'preflight_job': int(job_id), 'config': result['config'], 'intent': record(intent)}
    exclusive_json(stage/'loader-resource-submitted.json', receipt)
    return 'waiting_resource_submitted_not_released', receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', type=Path, required=True)
    p.add_argument('--buffered', type=Path, required=True)
    p.add_argument('--environment', type=Path, required=True)
    p.add_argument('--watched-sha256', required=True)
    p.add_argument('--rounds', type=int, choices=range(1, 91), default=60)
    a = p.parse_args()
    stage, buffered, environment = (x.resolve(strict=True) for x in (a.stage, a.buffered, a.environment))
    original = stage/'loader-watcher-3h-config.json'
    watched = read(checked({'path': str(original), 'sha256': a.watched_sha256}, stage))
    if len({str(watched[k]) for k in ('running_job','baseline_job','preflight_job','smoke_job')}) != 4:
        raise ValueError('original watcher scope differs')
    for i in range(a.rounds):
        checked({'path': str(original), 'sha256': a.watched_sha256}, stage)
        try:
            state, receipt = advance(stage, buffered, environment, watched)
        except ObservationUnavailable:
            if (stage/'loader-resource-submit-intent.json').exists():
                raise
            state, receipt = 'waiting_for_authoritative_donau_observation', None
        print(json.dumps({'state': state, 'receipt': receipt}), flush=True)
        if receipt is not None:
            return
        if i+1 < a.rounds:
            time.sleep(45)
    print(json.dumps({'state': 'bounded_observation_ended_no_resource_submitted'}), flush=True)


if __name__ == '__main__':
    main()
