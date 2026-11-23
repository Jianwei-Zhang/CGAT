"""Measure child-only LD_LIBRARY_PATH cleanup with unchanged mapper artifacts.

Isolated test of three already-completed windows. Admit only a candidate whose
loader dependency paths resolve to the same files. Every old and new stdout
must be byte-identical to the archived original. No workflow modifications.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import resource
import shutil
import socket
import subprocess
import sys
import time

from benchmark_regional_mapper_dispatch import digest, read_json, within
from probe_regional_guard_startup import CHILD, LIMIT, validate_child

CASES = (3, 25, 63)
MAX_FASTA_BYTES = 50 * 1024**2
MUMMER_PATH = '/share/home/xbzhang26/cgat-reads-debug/gpm2665-20261015/tooling/mummer/lib'


def loader_dependencies(output):
    """Compare canonical paths, not randomized addresses or displayed aliases."""
    paths = {}
    for line in output.splitlines():
        row = re.sub(r'\s+\(0x[0-9a-f]+\)$', '', line.strip())
        if not row or row.startswith('linux-vdso.so.'): continue
        name, sep, path = row.partition(' => ')
        if not sep: path, name = row, Path(row).name
        if name in paths or not path.startswith('/'):
            raise ValueError(f'unrecognized, duplicate or unresolved loader entry: {line}')
        paths[name] = str(Path(path).resolve(strict=True))
    if not paths: raise ValueError('no dynamic dependency inventory')
    return paths


def candidate_envs(environ):
    inherited = dict(environ)
    entries = inherited.get('LD_LIBRARY_PATH', '').split(':')
    if 'LD_LIBRARY_PATH' not in inherited or not any(entries): return []
    cleared = dict(inherited); cleared.pop('LD_LIBRARY_PATH')
    alternatives = [('clear_for_mapper_child', cleared)]
    if MUMMER_PATH in entries:
        pruned = dict(inherited); pruned['LD_LIBRARY_PATH'] = ':'.join(x for x in entries if x != MUMMER_PATH)
        alternatives.append(('omit_mummer_only_for_mapper_child', pruned))
    return alternatives


def run_one(dest, guard, argv, env, expected=None):
    t=time.monotonic();dest.mkdir();shutil.copyfile(guard,dest/'guard.py')
    cmd=[sys.executable,str(dest/'guard.py'),'--address-space-bytes',str(LIMIT),'--',*argv]
    (dest/'command.json').write_text(json.dumps({'executed_argv':cmd,'mapper_argv':argv,'address_space_bytes':LIMIT},indent=2)+'\n')
    recorded=time.monotonic()
    with (dest/'stdout').open('wb') as out, (dest/'stderr').open('wb') as err:
        opened=time.monotonic();child=subprocess.Popen(cmd,env=env,stdout=out,stderr=err,cwd=dest)
        spawned=time.monotonic()
        try: exit_code=child.wait(timeout=180)
        except subprocess.TimeoutExpired:
            child.kill();child.wait();raise
        exited=time.monotonic()
    if exit_code:raise RuntimeError(f'Child failed ({exit_code}): {dest}/stderr')
    if expected is None:
        validate_child((dest/'stdout').read_text(),child.pid,os.getpgrp());sha=None
    else:
        sha=digest(dest/'stdout')
        if sha!=expected:raise ValueError(f'Historical output SHA mismatch: {dest}')
    return {'open_seconds':opened-recorded,'popen_seconds':spawned-opened,
            'child_seconds':exited-spawned,'seconds':time.monotonic()-t,'stdout_sha256':sha}


def original_operations(work, inputs, anchor, expected_tool):
    tasks=[]; inventory={};total=0
    for ordinal in CASES:
        row=anchor['cases'][ordinal];marker=within(work,row['raw_receipt'])
        if digest(marker)!=row['receipt_sha256']:raise ValueError('raw receipt SHA mismatch')
        raw=read_json(marker);binding=raw['spec']['context'];context_file=within(work,binding['path'])
        if raw['status']!='success' or digest(context_file)!=binding['sha256']:raise ValueError('unpinned raw context')
        context=read_json(context_file);tool=context['spec']['tool']
        if Path(tool['resolved']).resolve()!=expected_tool or digest(expected_tool)!=tool['sha256']:
            raise ValueError('different mapper binary')
        input_paths={}
        for item in context['inputs']:
            path=within(inputs,item['path']);total+=item['size']
            if total>MAX_FASTA_BYTES or path.stat().st_size!=item['size'] or digest(path)!=item['sha256']:
                raise ValueError('unbound or oversized input FASTAs')
            inventory[path]=item['sha256'];input_paths[path.name]=str(path)
        if set(input_paths)!={'query.fa','target.fa'}:raise ValueError('unexpected FASTA inventory')
        pre=context_file.parent/'chaining/success.json';stages=[('exact',raw,marker)]
        if pre.is_file():
            coarse=read_json(pre)
            if coarse['status']!='success' or coarse['spec']['context']!=binding:raise ValueError('coarse context differs')
            stages.insert(0,('coarse',coarse,pre))
        commands=[]
        for name,record,receipt in stages:
            files={Path(x['path']).name:x for x in record['outputs']}
            cmd=within(work,files['command.json']['path'])
            if cmd.parent!=receipt.parent or digest(cmd)!=files['command.json']['sha256']:raise ValueError('unbound command')
            meta=read_json(cmd);argv=meta['argv']
            if (Path(argv[0]).resolve()!=expected_tool or meta['address_space_bytes']!=LIMIT or '-t' not in argv
                    or argv[argv.index('-t')+1]!='2' or ('-c' in argv)!=(name=='exact')):
                raise ValueError('mapper/resource profile differs')
            sha=files['result.paf']['sha256']
            if name=='exact' and sha!=row['paf_sha256']:raise ValueError('unpinned historical exact output')
            result=within(work,files['result.paf']['path'])
            if result.parent!=receipt.parent or digest(result)!=sha:raise ValueError('historical PAF changed')
            commands.append((name,[*argv[:-2],input_paths['target.fa'],input_paths['query.fa']],sha))
        tasks.append((ordinal,commands))
    return tasks,inventory,total


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('workspace','control-artifacts','anchor-report','guard','tool','output'):
        p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();work=a.workspace.resolve(strict=True);inputs=a.control_artifacts.resolve(strict=True);out=a.output.resolve()
    if any(x.is_relative_to(y) or y.is_relative_to(x) for x,y in [(out,work),(out,inputs),(inputs,work)]):
        raise ValueError('diagnostic output/input overlaps main')
    out.mkdir(exist_ok=False);tool=a.tool.resolve(strict=True);guard=a.guard.resolve(strict=True)
    if digest(a.anchor_report)!='8d774d0fd5ac8652f503375a75c997c8182852041d5fe052e3c6a88c66047901':
        raise ValueError('wrong control manifest')
    if any(os.environ.get(k) for k in ('LD_PRELOAD','LD_AUDIT')):raise ValueError('custom loader instrumentation is not comparable')
    inherited=dict(os.environ)
    binaries=[Path(sys.executable),Path(resource.__file__),tool,Path('/bin/bash')]
    def fingerprint(env):
        return {str(x):loader_dependencies(subprocess.check_output(['/usr/bin/ldd',str(x)],env=env,text=True,timeout=75)) for x in binaries}
    baseline=fingerprint(inherited);attempts=[];chosen=None;candidate=None
    for label,env in candidate_envs(inherited):
        try: matches=fingerprint(env)==baseline
        except (ValueError,subprocess.CalledProcessError): matches=False
        attempts.append({'mode':label,'same_loader_dependency_paths':matches})
        if matches:chosen,candidate=label,env;break
    report={'status':'diagnostic_no_compatible_loader_cleanup','host':socket.gethostname(),'attempts':attempts,
            'loader_dependency_paths':baseline,'guard_sha256':digest(guard),'tool_sha256':digest(tool),
            'main_workspace_modified':False,'production_strategy_enabled':False,'phases':[]}
    print(json.dumps({'loader_attempts':attempts}),flush=True)
    if candidate is not None:
        library_paths=sorted(set(v for table in baseline.values() for v in table.values()))
        report['dependency_sha256']={path:digest(path) for path in library_paths}
        for label,env in [('inherited',inherited),(chosen,candidate)]:
            report.setdefault('limit_probes',{})[label]=run_one(out/('limit-'+label),guard,CHILD,env)
        tasks,inventory,total=original_operations(work,inputs,read_json(a.anchor_report),tool)
        report['verified_input_bytes']=total
        for phase,label in enumerate(('inherited',chosen,chosen,'inherited')):
            d=out/f'{phase}-{label}';d.mkdir();begin=time.monotonic();env=inherited if label=='inherited' else candidate
            def run(task):
                ordinal,ops=task;case=d/str(ordinal);case.mkdir()
                return {'ordinal':ordinal,'runs':{name:run_one(case/name,guard,argv,env,sha) for name,argv,sha in ops}}
            with ThreadPoolExecutor(max_workers=3) as pool: rows=list(pool.map(run,tasks))
            value={'phase':phase,'mode':label,'seconds':time.monotonic()-begin,'cases':rows}
            report['phases'].append(value);print(json.dumps(value),flush=True)
        protected={**inventory,**report['dependency_sha256'],tool:report['tool_sha256'],guard:report['guard_sha256']}
        if dict(os.environ)!=inherited or any(digest(p)!=sha for p,sha in protected.items()):
            raise ValueError('child env escaped scope or immutable input changed')
        report['status']='diagnostic_loader_cleanup_ABBA_historical_stdout_identical_NOT_deployed'
    (out/'summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')


if __name__=='__main__':main()
