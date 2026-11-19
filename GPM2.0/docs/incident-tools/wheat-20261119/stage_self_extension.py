"""Stage an explicit >=10-Mb self extension without changing primary results.

Run on a compute node: candidate/input/output identities are read in full.
Does not stop/submit jobs, install readers, or write the analysis workspace.
"""
import argparse
import copy
import json
from pathlib import Path
import shlex
import sys

from self_extension_context import SCHEMA, digest

# A frozen validation bundle can also contain an old pilot copy. The actual
# scientific parent binds its original path, not that same-bytes copied path.
if __name__ == '__main__':
    early=argparse.ArgumentParser(add_help=False)
    early.add_argument('--parent-plan',type=Path,required=True)
    early_args,_=early.parse_known_args()
    bound=json.loads(early_args.parent_plan.read_text())
    for dependency in bound['dependencies'].values():
        if digest(dependency['path'])!=dependency['sha256']:
            raise ValueError('parent dependency changed before loading the frozen pilot')
    sys.path[:0]=[str(Path(bound['workspace'])/'.prepare_lib/tools'),
                  str(Path(bound['dependencies']['pilot']['path']).parent)]

import composite_self_profile as profiles
import extended_self_seed_profile as extension

HERE=Path(__file__).resolve().parent
LIMIT=64*1024**3
CHANGED_DEPENDENCIES={'admission','launcher','audit_exporter'}
MODULES={'profile_factory':'composite_self_profile.py','extension_runtime':'extended_self_seed_profile.py',
    'extension_bootstrap':'self_extension_context.py','extension_stager':'stage_self_extension.py',
    'extension_entry':'resume_self_extension.py','extension_reader':'read_self_extension.py',
    'audit_exporter':'self_extension_audit.py','admission':'self_two_lane_admission.py'}


def record(path):
    path=Path(path).resolve(strict=True)
    return {'path':str(path),'sha256':digest(path)}


def file_record(path):
    row=record(path);row['size']=Path(path).stat().st_size;return row


def verify_transition(plan,parent):
    if (plan.get('extension_schema')!=SCHEMA or plan.get('preview_only') is not False
            or parent.get('preview_only') is not False or parent.get('extension_schema')
            or plan.get('workspace')!=parent.get('workspace') or plan.get('schema')!=parent.get('schema')
            or len(plan['operations'])!=len(parent['operations'])):
        raise ValueError('invalid self extension parent or operation inventory')
    for name,row in parent['dependencies'].items():
        if name not in CHANGED_DEPENDENCIES and plan['dependencies'].get(name)!=row:
            raise ValueError('original scientific execution dependency changed: '+name)
    if (plan['resource_policy']['max_fast']!=2
            or plan['resource_policy']['reservation_policy']!=parent['resource_policy']['reservation_policy']
            or plan['resource_guard']['scope']!='per_process_virtual_address_space'
            or plan['resource_guard']['limit_bytes']!=LIMIT):
        raise ValueError('extension must retain the measured two-lane resource envelope')
    scripts=set()
    for row,old in zip(plan['operations'],parent['operations']):
        if {k:v for k,v in row.items() if k not in ('profile','scripts')}!={k:v for k,v in old.items() if k not in ('profile','scripts')}:
            raise ValueError('extension changed native commands, task manifest or operation')
        profile=profiles.Profile(profiles.checked(row['profile']))
        if row['profile']!=old['profile']:
            if (not isinstance(profile,profiles.CompositeProfile)
                    or profile.spec['primary_profile']!=old['profile']
                    or profile.spec['runtime']!=plan['dependencies']['profile_factory']
                    or profile.extension.spec['dependencies']['runtime']!=plan['dependencies']['extension_runtime']):
                raise ValueError('extension does not preserve the exact primary profile')
            for i in profile.extension.selected:
                marker=Path(profile.native['batches'][i]['directory'])/'complete.json'
                if marker.exists() and json.loads(marker.read_text()).get('key')!=profile.manifest['batches'][i]['key']:
                    raise ValueError('native batch completed since staging; restage without discarding it')
        if set(row['scripts'])!={str(i) for i in profile.selected}:
            raise ValueError('extension script inventory differs from composite selection')
        for i,script in old['scripts'].items():
            if row['scripts'].get(i)!=script or plan['resource_guard']['scripts'].get(script['path'])!=parent['resource_guard']['scripts'][script['path']]:
                raise ValueError('original guarded execution script changed')
        for script in row['scripts'].values():
            if file_record(script['path'])!=script:raise ValueError('guarded extension script changed')
            guard=plan['resource_guard']['scripts'].get(script['path'],{})
            if guard.get('guarded_script_sha256')!=script['sha256']:
                raise ValueError('missing script address-space guard binding')
            profiles.checked(guard['source']);scripts.add(script['path'])
    if scripts!=set(plan['resource_guard']['scripts']):raise ValueError('unexpected guard inventory')


def calibration(path,parent):
    path=Path(path).resolve(strict=True);data=json.loads(path.read_text())
    pilot=extension.pilot
    if (path.is_relative_to(Path(parent['workspace']))
            or data.get('scope')!='one_complete_self_query_candidate_only'
            or data.get('status')!='candidate_complete_not_compared_not_adopted'
            or data.get('analysis_workspace_modified') is not False
            or data.get('candidate_adopted') is not False
            or data.get('mapping',{}).get('returncode')!=0
            or data.get('driver_sha256')!=digest(parent['dependencies']['pilot']['path'])
            or Path(pilot.__file__).resolve()!=Path(parent['dependencies']['pilot']['path']).resolve()):
        raise ValueError('a complete bound sub100 f0.005 candidate is required')
    inputs=pilot.identities([Path(p) for p in data['inputs']]);outputs=pilot.identities([Path(p) for p in data['outputs']])
    if inputs!=data['inputs'] or outputs!=data['outputs']:
        raise ValueError('candidate inputs or outputs changed')
    if set(outputs)!={str(path.parent/name) for name in (*extension.OUTPUTS,'restore.stderr.log')}:
        raise ValueError('candidate output inventory differs')
    matches=[]
    for row in parent['operations']:
        primary=profiles.Profile(profiles.checked(row['profile']))
        for i,batch in enumerate(primary.native['batches']):
            if batch['key']!=data.get('native_batch_key'):continue
            if (len(batch['entries'])!=1 or not 10_000_000<=batch['entries'][0]['length']<100_000_000
                    or pilot.candidate_command(primary.native,batch,data['native_command'])!=data['command']
                    or inputs.get(str(primary.source),{}).get('sha256')!=primary.spec['native_manifest']['sha256']
                    or inputs.get(batch['query'],{}).get('sha256')!=batch['query_sha256']):
                raise ValueError('candidate is not the declared complete sub100 native query')
            queries={e['name']:e['length'] for e in batch['entries']}
            primary.helper.validate_raw(path.parent/'raw.paf',queries,primary.native['target_lengths'])
            primary.contract.validate_paf(path.parent/'result.paf',require_cigar=True)
            pilot.verify_completion(path.parent/'stderr.log',1)
            matches.append((row['operation'],i))
    if len(matches)!=1:raise ValueError('candidate does not identify one native batch')
    return matches[0],{'report':record(path),'mapping':data['mapping'],
        'scope':'runtime calibration only; no completed native comparison or whole-workflow accuracy claim'}


def stage(parent_path,output,candidate_path):
    parent_path=Path(parent_path).resolve(strict=True);parent_bytes=parent_path.read_bytes();parent=json.loads(parent_bytes)
    work=Path(parent['workspace']).resolve(strict=True);output=Path(output).resolve()
    if (output.exists() or output.is_relative_to(work) or work.is_relative_to(output)
            or parent.get('extension_schema') or parent.get('preview_only') is not False
            or parent.get('resource_guard',{}).get('limit_bytes')!=LIMIT):
        raise ValueError('new isolated extension of a final guarded self plan required')
    if (work/'metadata/grt_q0_evidence.json').exists():raise ValueError('q0 evidence is already published')
    for row in parent['dependencies'].values():profiles.checked(row)
    key,measurement=calibration(candidate_path,parent)
    sys.path.insert(0,str(work/'.prepare_lib/tools'))
    import self_two_lane_admission as admission
    if admission.POLICY!=parent['resource_policy']['reservation_policy']:
        raise ValueError('resource envelope differs from current two-lane plan')
    plan=copy.deepcopy(parent);plan['extension_schema']=SCHEMA
    deps=plan['dependencies'];deps.update({name:record(HERE/filename) for name,filename in MODULES.items()})
    deps.update(extension_parent=record(parent_path),extension_calibration=record(candidate_path))
    plan['extension_policy']={'policy':extension.POLICY,'calibration':measurement,
        'primary_profiles_and_keys_preserved':True,'completed_native_batches_preserved':True}
    output.mkdir();(output/'profiles').mkdir();(output/'commands').mkdir()
    excluded=[];count=0
    for row in plan['operations']:
        primary=profiles.Profile(profiles.checked(row['profile']));selected=[]
        for i,batch in enumerate(primary.native['batches']):
            if i in primary.selected or len(batch['entries'])!=1 or batch['entries'][0]['length']<extension.POLICY['minimum_query_bases']:continue
            marker=Path(batch['directory'])/'complete.json'
            if marker.exists():
                if not primary.validate_batch(i):raise ValueError('existing native result does not verify')
                excluded.append({'operation':row['operation'],'batch_index':i,'marker':record(marker)});continue
            selected.append(i)
        if not selected:continue
        stem=row['operation'].replace('/','__');leaf=output/'profiles'/(stem+'-extension.json')
        spec={'schema':extension.SCHEMA,'policy':extension.POLICY,'workspace':str(work),
            'native_manifest':primary.spec['native_manifest'],'selected_batches':selected,
            'dependencies':{**primary.spec['dependencies'],'runtime':deps['extension_runtime']},'adoptions':{}}
        if key[0]==row['operation'] and key[1] in selected:spec['adoptions'][str(key[1])]=record(candidate_path)
        leaf.write_text(json.dumps(spec,indent=2,sort_keys=True)+'\n')
        combined=output/'profiles'/(stem+'-composite.json')
        combined.write_text(json.dumps({'schema':profiles.SCHEMA,'workspace':str(work),
            'native_manifest':primary.spec['native_manifest'],'primary_profile':row['profile'],
            'extension_profile':record(leaf),'runtime':deps['profile_factory']},indent=2,sort_keys=True)+'\n')
        row['profile']=record(combined)
        for i in selected:
            raw=output/'commands'/(stem+'__'+str(i)+'-raw.sh')
            raw.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexport PYTHONPATH='+shlex.quote(str(Path(deps['pilot']['path']).parent))+':"${PYTHONPATH:-}"\nexec python3 -B -u '+shlex.quote(deps['extension_runtime']['path'])
                +' --profile '+shlex.quote(str(leaf))+' --batch-index '+str(i)+'\n');raw.chmod(0o755)
            guarded=output/'commands'/(stem+'__'+str(i)+'.sh');source=file_record(raw)
            guarded.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexec python3 -B -u '+shlex.quote(deps['memory_guard']['path'])
                +' --limit-bytes '+str(LIMIT)+' --script '+shlex.quote(str(raw))+' --sha256 '+source['sha256']+'\n');guarded.chmod(0o755)
            row['scripts'][str(i)]=file_record(guarded)
            plan['resource_guard']['scripts'][str(guarded)]={'guarded_script_sha256':row['scripts'][str(i)]['sha256'],'source':source}
        count+=len(selected)
    if not count:raise ValueError('no unfinished self batches need extension')
    plan['extension_excluded_completed']=excluded
    plan_path=output/'self-plan.json';launcher=output/'prepare_q0_evidence.sh'
    launcher.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexport PYTHONDONTWRITEBYTECODE=1\nexec python3 -B -u '
        +shlex.quote(deps['extension_reader']['path'])+' --plan '+shlex.quote(str(plan_path))
        +' --server-dir '+shlex.quote(str(work))+' --threads 32 --minimap2 minimap2\n')
    deps['launcher']=record(launcher);plan['prior_launcher']=record(work/'prepare_q0_evidence.sh')
    verify_transition(plan,parent)
    if parent_path.read_bytes()!=parent_bytes:raise ValueError('parent plan changed during staging')
    plan_path.write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
    receipt={'status':'self_extension_staged_not_installed','plan':record(plan_path),'extension_batches':count,
        'primary_profiles_preserved':True,'excluded_completed_native_batches':len(excluded),'calibration':measurement}
    (output/'staging-receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps(receipt,indent=2),flush=True);return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent-plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--candidate-report',type=Path,required=True)
    args=parser.parse_args();stage(args.parent_plan,args.output,args.candidate_report)
