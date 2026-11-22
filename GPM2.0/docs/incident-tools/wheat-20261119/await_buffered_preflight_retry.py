"""Submit one isolated buffered preflight only after verified timeout, never cut over."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


class ObservationUnavailable(ValueError):
    pass


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('unexpected packet path: '+str(path))
    return json.loads(path.read_text())


def exclusive_json(path, value):
    with path.open('x') as stream:
        json.dump(value,stream,sort_keys=True,indent=2)
        stream.write('\n')


def query(job):
    try:
        raw = subprocess.check_output(['djob','-J','-ll',str(job)],timeout=30)
        rows = json.loads(raw)['data']['successData']
    except (subprocess.SubprocessError, ValueError, KeyError) as exc:
        raise ObservationUnavailable('no authoritative Donau result') from exc
    if len(rows) != 1 or str(rows[0]['jobId']) != str(job):
        raise ObservationUnavailable('ambiguous Donau query')
    return rows[0]


def maybe_retry(root, config):
    watched = Path(config['existing_watch']).resolve(strict=True)
    if sha(watched) != config['existing_watch_sha256']:
        raise ValueError('original watcher configuration changed')
    original = json_file(watched)
    stage = watched.parent
    prior = query(original['preflight_job'])
    if not prior.get('endTime') or prior['endTime'] == '-':
        return 'waiting_for_same_preflight', None
    if prior['state'] != 'FAILED' or prior.get('jobExitCode') != 124:
        return 'original_preflight_terminal_not_retryable', None
    original_launch = json_file(stage/'preflight-3h-retry-submitted.json')
    if (str(original_launch['new_preflight']) != str(prior['jobId'])
            or original_launch['scope'] != 'read_only_same_25_checks'
            or sha(stage/'preflight-3h.dsub') != original_launch['script_sha256']
            or Path(prior['execPath']).resolve() != stage
            or Path(prior['cmd']).resolve() != stage/'preflight-3h.dsub'):
        raise ValueError('timeout is not the expected original diagnostic')
    usages = [u for g in prior['resGroups'] for u in g.get('nodeResUsages', [])]
    if not usages or any(u.get('pids') not in ('-', '', []) for u in usages):
        return 'waiting_for_old_diagnostic_processes_to_exit', None
    for mark in ('validation.json','loader-resource-submit-intent.json','loader-resource-submitted.json',
                 'loader-ready.json','ready.json','handoff.json'):
        p = stage/mark
        if p.exists() or p.is_symlink():
            raise ValueError('existing transition already has '+mark)
    main, old = [query(original[k]) for k in ('running_job','baseline_job')]
    smoke = query(original['smoke_job'])
    if (main['state'] != 'RUNNING' or old['state'] != 'RUNNING'
            or smoke['state'] != 'SUCCEEDED' or smoke.get('jobExitCode') != 0):
        raise ValueError('main, baseline, or original smoke state changed')
    packet = root/'config.json'
    stage_row = json_file(packet)['original_staged_transition']
    if stage_row != original['transition'] or sha(Path(stage_row['path'])) != stage_row['sha256']:
        raise ValueError('buffered probe is for a different loader transition')
    work = Path(json_file(Path(stage_row['path']))['workspace']).resolve(strict=True)
    if root == work or root.is_relative_to(work) or (work/'metadata/grt_q0_evidence.json').exists():
        raise ValueError('Q0 stage has changed or the diagnostic is not isolated')
    owner = json_file(work/'.run_all/lock/owner.json')
    if (owner.get('workspace') != str(work) or owner.get('run_id') != original['running_run_id']
            or owner.get('hostname') != main.get('taskExecNodes')):
        raise ValueError('current NEW workspace owner changed')
    for name in ('job.sha256','config.sha256'):
        if sha(root/name) != config[name]:
            raise ValueError('buffered probe packet changed: '+name)
        subprocess.run(['sha256sum','-c',name],cwd=root,check=True,timeout=60)
    if (root/'buffered-proof.json').exists() or (root/'submit.txt').exists():
        raise ValueError('probe already has output or a scheduler receipt')
    # Seals the one observation and prevents a duplicate submit on transport loss.
    exclusive_json(root/'submission.intent',{'operation':'once_read_only_after_timeout','prior':prior,
                                             'main_job':main['jobId'],'protected_baseline':old['jobId']})
    submitted = subprocess.run(['dsub','-s','run.dsub'],cwd=root,check=True,text=True,
                               stdout=subprocess.PIPE,timeout=60).stdout
    match = re.fullmatch(r'\s*Submit job <([1-9][0-9]*)> successfully\.\s*',submitted)
    if match is None:
        raise ValueError('ambiguous dsub result; inspect Donau, do not retry')
    with (root/'submit.txt').open('x') as stream:
        stream.write(submitted)
    return 'new_buffered_probe_submitted',int(match[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config',type=Path)
    parser.add_argument('--rounds',type=int,choices=range(1,61),default=55,metavar='1..60')
    args = parser.parse_args()
    path = args.config.resolve(strict=True)
    config, identity = json_file(path), sha(path)
    for i in range(args.rounds):
        if sha(path) != identity or (path.parent/'submission.intent').exists():
            raise ValueError('launcher config drifted or prior submission intent exists')
        try:
            status, job = maybe_retry(path.parent,config)
        except ObservationUnavailable:
            status, job = 'waiting_for_authoritative_observation', None
        if i % 5 == 0 or not status.startswith('waiting_'):
            print(json.dumps({'at':datetime.datetime.now().astimezone().isoformat(),'status':status,'job_id':job}),flush=True)
        if not status.startswith('waiting_'):
            return
        if i+1 < args.rounds:
            time.sleep(60)
    print(json.dumps({'status':'bounded_observation_expired_no_job_changed'}),flush=True)


if __name__ == '__main__':
    main()
