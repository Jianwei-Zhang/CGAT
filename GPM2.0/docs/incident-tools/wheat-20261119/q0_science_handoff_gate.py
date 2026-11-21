"""Resource-ready gate for the NEW wheat only; never stops jobs itself.

Small scheduler/dependency proofs are checked before installing any q0 file.
The normal owner still acquires the normal lock and verifies complete inputs.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import socket
import time
from q0_science_context import checked,digest


def scheduler(row,root):
    path=checked(row)
    if path.parent!=root:raise ValueError('scheduler proof is outside handoff bundle')
    return json.loads(path.read_text())['data']['successData'][0]


def validate_handoff(config,release,root,ready_sha,host):
    if (release.get('status')!='old_job_terminal_and_normal_lock_released'
            or release.get('old_job')!=config['old_job']
            or release.get('protected_baseline')!=config['protected_baseline']
            or release.get('transition_sha256')!=config['transition']['sha256']
            or release.get('ready_sha256')!=ready_sha):
        raise ValueError('q0 handoff identity differs')
    checked(config['transition']);checked(config['initial_preflight'])
    old=scheduler(release['old_scheduler'],root);new=scheduler(release['new_scheduler'],root)
    if str(old['jobId'])!=str(config['old_job']) or old['state'] not in ('SUCCEEDED','FAILED'):
        raise ValueError('prior NEW job is not terminal')
    usages=[usage for group in old['resGroups'] for usage in group.get('nodeResUsages',[])]
    if not usages or any(usage.get('pids') not in ('-','',[]) for usage in usages):
        raise ValueError('prior NEW child processes have not been confirmed gone')
    groups=new['resGroups']
    if (str(new['jobId'])!=str(release['new_job']) or new['state']!='RUNNING' or new['queue']!='x86'
            or new['taskExecNodesCount']!=1 or len(groups)!=1 or new['taskExecNodes']!=host
            or groups[0]['resAlloc']['cpu']<32 or groups[0]['resAlloc']['mem']<327680
            or groups[0]['resLimit']['mem']<327680):
        raise ValueError('new job has no verified single-node 32CPU/320GiB allocation')
    work=Path(config['workspace'])
    if (work/'.run_all/lock').exists():raise ValueError('normal workspace lock is still present')
    if (work/'grt/evidence/q0_prepare/tasks/q0-map-a6056c2d8fcb81f6ca19d1a7/success.json').exists():
        raise ValueError('original whole-source partial completed; re-stage rather than override')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);args=p.parse_args()
    config_path=args.config.resolve(strict=True);root=config_path.parent;config_sha=digest(config_path)
    config=json.loads(config_path.read_text());checked(config['transition'])
    if config['old_job']==config['protected_baseline']:raise ValueError('baseline cannot be the handoff target')
    report=json.loads(checked(config['initial_preflight']).read_text())
    if (report.get('status')!='q0_transition_all_initial_checkpoints_verified_only'
            or report.get('workspace_modified') is not False or len(report.get('initial_checkpoints',[]))!=25):
        raise ValueError('all initial checkpoints must have passed the real read-only preflight')
    ready={'status':'resource_ready_waiting_q0_handoff','config_sha256':config_sha,
           'transition_sha256':config['transition']['sha256'],'old_job':config['old_job'],
           'protected_baseline':config['protected_baseline'],'host':socket.gethostname(),'pid':os.getpid(),
           'at':datetime.datetime.now().astimezone().isoformat()}
    with (root/'ready.json').open('x') as stream:
        json.dump(ready,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    ready_sha=digest(root/'ready.json');print('Q0_RESOURCE_READY',json.dumps(ready),flush=True)
    for _ in range(10800):
        release=root/'handoff.json'
        if release.exists():
            if digest(config_path)!=config_sha:raise ValueError('handoff config changed')
            validate_handoff(config,json.loads(release.read_text()),root,ready_sha,socket.gethostname())
            print('Q0_HANDOFF_ACCEPTED',flush=True)
            from resume_q0_science import execute
            return execute(checked(config['transition']),install_runtime=True,threads=32)
        time.sleep(2)
    raise ValueError('resource-ready wait expired without modifying the workspace')


if __name__=='__main__':raise SystemExit(main())
