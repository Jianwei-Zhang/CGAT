"""Stage a resource-only overlay, preserving every existing scientific profile.

Never regenerate the original self profiles once approximate markers exist.
No workspace writes, submission or cancellation. Two completed guarded-policy
calibrations are required; output hashes and actual mapper logs are checked.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import sys

HERE=Path(__file__).resolve().parent
SCHEMA='incident_self_resource_overlay_v1'
LIMIT=64*1024**3


def digest(path):
    path=Path(path);before=path.stat();sha=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):sha.update(chunk)
    after=path.stat();sig=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if sig(before)!=sig(after):raise ValueError('file changed while hashing')
    return sha.hexdigest()


def record(path):
    path=Path(path).resolve(strict=True)
    return {'path':str(path),'sha256':digest(path)}


def file_record(path):
    result=record(path);result['size']=Path(path).stat().st_size;return result


def verify_transition(plan,origin):
    if (plan.get('resource_overlay_schema')!=SCHEMA or plan.get('preview_only') is not False
            or origin.get('preview_only') is not False or origin.get('resource_guard')
            or plan.get('workspace')!=origin.get('workspace') or plan.get('schema')!=origin.get('schema')
            or len(plan['operations'])!=len(origin['operations'])):
        raise ValueError('resource overlay does not match an unguarded final self plan')
    guard=plan['resource_guard']
    if guard.get('scope')!='per_process_virtual_address_space' or guard.get('limit_bytes')!=LIMIT:
        raise ValueError('wrong guard scope or limit')
    seen=set()
    for new,old in zip(plan['operations'],origin['operations']):
        if ({k:v for k,v in new.items() if k!='scripts'}!={k:v for k,v in old.items() if k!='scripts'}
                or set(new['scripts'])!=set(old['scripts'])):
            raise ValueError('resource migration changed scientific profile, commands or operation inventory')
        for i,row in new['scripts'].items():
            proof=guard['scripts'].get(row['path'],{})
            if proof!={'guarded_script_sha256':row['sha256'],'source':old['scripts'][i]}:
                raise ValueError('guard does not preserve the original executed script')
            seen.add(row['path'])
    if seen!=set(guard['scripts']):raise ValueError('unexpected guarded script inventory')
    for name,row in origin['dependencies'].items():
        if name not in ('admission','launcher') and plan['dependencies'].get(name)!=row:
            raise ValueError('scientific execution dependency changed: '+name)


def calibrations(origin):
    result=[]
    for row in origin['operations']:
        if digest(row['profile']['path'])!=row['profile']['sha256']:raise ValueError('origin profile changed')
        spec=json.loads(Path(row['profile']['path']).read_text())
        if digest(spec['native_manifest']['path'])!=spec['native_manifest']['sha256']:raise ValueError('native manifest changed')
        native=json.loads(Path(spec['native_manifest']['path']).read_text())
        if spec['policy'].get('seed_fraction')!='0.005':
            if spec['selected_batches']:raise ValueError('only f0.005 scientific profiles may use two lanes')
            continue
        for i in spec['selected_batches']:
            directory=Path(native['batches'][i]['directory'])
            if not (directory/'complete.json').exists():continue
            proof=json.loads((directory/'self-profile-receipt.json').read_text())
            marker=json.loads((directory/'complete.json').read_text())
            expected={'status':'complete','profile_sha256':row['profile']['sha256'],
                'native_key':native['batches'][i]['key'],'batch_index':i,'policy':spec['policy']}
            if (any(proof.get(k)!=v for k,v in expected.items()) or proof.get('mapping',{}).get('returncode')!=0
                    or marker.get('key')!=proof.get('key') or marker.get('outputs')!=proof.get('outputs')
                    or set(marker.get('outputs',{}))!={'raw.paf','result.paf','stderr.log'}
                    or proof.get('command',[])[-4:-2]!=['-f','0.005']):
                raise ValueError('incomplete or mismatched production calibration')
            if any(digest(directory/name)!=sha for name,sha in marker['outputs'].items()):
                raise ValueError('production calibration output changed')
            peaks=re.findall(r'Peak RSS: ([0-9.]+) GB',(directory/'stderr.log').read_text())
            if len(peaks)!=1 or not 0<float(peaks[0])<=16:
                raise ValueError('completed self peak is missing or outside two-lane pilot envelope')
            result.append({'profile':row['profile'],'batch_index':i,'receipt':record(directory/'self-profile-receipt.json'),
                'complete_marker':record(directory/'complete.json'),'query_sha256':native['batches'][i]['query_sha256'],
                'observed_peak_rss_gb':float(peaks[0]),'query_bases':sum(e['length'] for e in native['batches'][i]['entries']),
                'target_bases':sum(native['target_lengths'].values()),'basis':'completed_outputs_rehashed; source identities from bound manifest'})
    if len({r['query_sha256'] for r in result})<2:
        raise ValueError('two distinct completed production self calibrations are required')
    return result


def stage(origin_path,output):
    origin_path=origin_path.resolve(strict=True);raw=origin_path.read_bytes();origin=json.loads(raw)
    work=Path(origin['workspace']).resolve(strict=True);output=output.resolve()
    if (output.exists() or output.is_relative_to(work) or work.is_relative_to(output)
            or origin.get('schema')!='incident_self_dispatch_v1' or origin.get('preview_only') is not False
            or origin.get('resource_guard') or origin['resource_policy']['max_fast']!=1):
        raise ValueError('new isolated overlay of the current final single-lane plan required')
    if (work/'metadata/grt_q0_evidence.json').exists():raise ValueError('q0 evidence is already published')
    for row in origin['dependencies'].values():
        if digest(row['path'])!=row['sha256']:raise ValueError('origin execution dependency changed')
    measured=calibrations(origin)
    sys.path.insert(0,str(work/'.prepare_lib/tools'))
    spec=importlib.util.spec_from_file_location('guarded_admission_for_staging',HERE/'self_two_lane_admission.py')
    admission=importlib.util.module_from_spec(spec);spec.loader.exec_module(admission)
    plan=copy.deepcopy(origin);plan['resource_overlay_schema']=SCHEMA
    deps=plan['dependencies']
    deps.update(admission=record(HERE/'self_two_lane_admission.py'),memory_guard=record(HERE/'self_memory_guard.py'),
        resource_entry=record(HERE/'resume_self_resources.py'),resource_stager=record(Path(__file__)),
        resource_origin=record(origin_path))
    output.mkdir();(output/'commands').mkdir()
    plan_path=output/'self-plan.json';guard={'scope':'per_process_virtual_address_space','limit_bytes':LIMIT,'scripts':{}}
    for row in plan['operations']:
        for i,original in list(row['scripts'].items()):
            if file_record(original['path'])!=original:raise ValueError('original selected script changed')
            path=output/'commands'/(row['operation'].replace('/','__')+'__'+i+'.sh')
            path.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexec python3 -B -u '+shlex.quote(deps['memory_guard']['path'])
                +' --limit-bytes '+str(LIMIT)+' --script '+shlex.quote(original['path'])+' --sha256 '+original['sha256']+'\n')
            path.chmod(0o755);row['scripts'][i]=file_record(path)
            guard['scripts'][str(path)]={'guarded_script_sha256':row['scripts'][i]['sha256'],'source':original}
    plan['resource_guard']=guard
    plan['resource_policy']={'reservation_policy':admission.POLICY,'max_fast':2,
        'calibration':{'completed_production_batches':measured,'interpretation':'per-process AS guard, not cgroup RSS or whole-workflow accuracy guarantee'}}
    launcher=output/'prepare_q0_evidence.sh';reader=Path(deps['reader']['path'])
    launcher.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexport PYTHONDONTWRITEBYTECODE=1\n'
        +'(cd '+shlex.quote(str(reader.parent))+' && sha256sum -c code.sha256)\n'
        +'exec python3 -B -u '+shlex.quote(str(reader))+' --plan '+shlex.quote(str(plan_path))
        +' --server-dir '+shlex.quote(str(work))+' --threads 32 --minimap2 minimap2\n')
    deps['launcher']=record(launcher);plan['prior_launcher']=record(work/'prepare_q0_evidence.sh')
    verify_transition(plan,origin)
    if origin_path.read_bytes()!=raw:raise ValueError('origin plan changed during resource staging')
    plan_path.write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
    proof={'status':'resource_only_overlay_staged_not_installed','plan':record(plan_path),
        'origin_plan':record(origin_path),'scientific_profiles_preserved':True,'guarded_scripts':len(guard['scripts']),
        'completed_calibrations':len(measured),'max_fast':2}
    (output/'staging-receipt.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
    print(json.dumps(proof,indent=2),flush=True);return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin-plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();stage(args.origin_plan,args.output)
