"""ABBA on three frozen operations' real native wrapper/spec inventories.

This checks the original and reduced-I/O metadata verifier on the same files.
It never instantiates an owner, executes a wrapper, or touches a checkpoint.
Fixture objects feed the real verifier; this is not full resume validation.
"""
import argparse
import hashlib
import importlib.util
import json
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace

TRANSITION = '95c2b13113ee94f7f4fb6fe17d484c5797163a0115a72a862a38e6ca7e2fe497'
ORIGINAL = 'f30a10d7c2e470bcb3e7bf73303c274ebe05eebf38b1f4cc3617a1b780bbfa1e'
CONTRACT = '899b629ca3d2d2fb2d7e768f3368bd1e94a049d345a571928c09442090ba4ffb'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(rec, limit=32*1024**2):
    path = Path(rec['path'])
    if (not path.is_absolute() or path.is_symlink() or path.stat().st_size > limit or sha(path) != rec['sha256']):
        raise ValueError('archived binding identity differs: '+str(path))
    return path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def stage_profiles(plan, work):
    rows = dict((row['operation'], row) for row in plan['operations'])
    if len(rows) != 44 or sum(len(row['native_scripts']) for row in rows.values()) != 876:
        raise ValueError('wrong frozen wheat operation inventory')
    names = sorted(rows, key=lambda name: (len(rows[name]['native_scripts']), name))
    selected_rows = {name: rows[name] for name in (names[0], names[len(names)//2], names[-1])}
    profiles = {}
    for name, row in selected_rows.items():
        profile = json.loads(checked(row['profile']).read_text())
        manifest = profile['native_manifest']
        source = checked(manifest)
        if source.parent != work/name or source.name != 'self_batch_manifest.json':
            raise ValueError('native operation belongs to a different project')
        if 'selected_batches' in profile:
            picks = profile['selected_batches']
        else:
            picks = []
            for label in ('primary_profile','extension_profile'):
                leaf = json.loads(checked(profile[label]).read_text())
                if leaf['native_manifest'] != manifest:
                    raise ValueError('composite profile manifest differs')
                picks.extend(leaf['selected_batches'])
        if len(picks) != len(set(picks)):
            raise ValueError('overlapping profile selections')
        profiles[name] = SimpleNamespace(source=source,native=json.loads(source.read_text()),selected=set(picks))
    return selected_rows, profiles


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('transition','candidate','output'):
        p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--candidate-sha256',required=True)
    a = p.parse_args()
    transition_path = checked({'path':str(a.transition),'sha256':TRANSITION})
    transition = json.loads(transition_path.read_text())
    work = Path(transition['workspace']).resolve(strict=True)
    out = a.output.resolve()
    if out.is_relative_to(work) or work.is_relative_to(out):
        raise ValueError('diagnostic result must remain isolated')
    plan_path = checked(transition['native_origin'])
    plan = json.loads(plan_path.read_text())
    original = plan['dependencies']['native_support']
    if original['sha256'] != ORIGINAL or plan['workspace'] != str(work):
        raise ValueError('original native support scope differs')
    candidate = {'path':str(a.candidate),'sha256':a.candidate_sha256}
    modules = {'original': checked(original), 'candidate': checked(candidate)}
    guard = checked(plan['dependencies']['native_guard'])
    contract_path = checked({'path':str(work/'.prepare_lib/tools/run_orchestration.py'),'sha256':CONTRACT})
    load_module('native_batch_guard',guard)
    contract = load_module('diagnostic_wheat_binding_contract',contract_path)
    rows, profiles = stage_profiles(plan,work)
    results = []
    print(json.dumps({'phase':'verified_input_inventory','operations':{n:len(r['native_scripts']) for n,r in rows.items()}}),flush=True)
    for label in ('original','candidate','candidate','original'):
        module = load_module('diagnostic_binding_'+label,modules[label])
        scoped = {**plan,'dependencies':{**plan['dependencies'],'native_support':original if label=='original' else candidate}}
        # Simulate the pre-lock verifier's empty process-local digest/JSON caches;
        # do not manipulate kernel or shared storage caches. The candidate's
        # identity is declared truthfully; guard/spec identities remain original.
        contract._SHA256_CACHE.clear()
        binding = object.__new__(module.NativeBindings)
        binding.original = SimpleNamespace(work=work,contract=contract,plan=scoped,rows=rows,profiles=profiles)
        binding._specs = {}
        count = [0]
        record = binding.record
        def counted(path):
            count[0] += 1
            return record(path)
        binding.record = counted
        start = time.monotonic();cpu = time.process_time()
        binding.verify_native_resources()
        elapsed = time.monotonic()-start
        n = sum(len(row['native_scripts']) for row in rows.values())
        if len(binding._specs) != n or sha(modules[label]) != scoped['dependencies']['native_support']['sha256']:
            raise ValueError('not all original spec identities verified')
        r = {'mode':label,'seconds':elapsed,'cpu_seconds':time.process_time()-cpu,
             'verified_specs':n,'operation_file_identity_calls':count[0]}
        results.append(r); print(json.dumps(r),flush=True)
    with out.open('x') as f:
        json.dump({'status':'native_binding_metadata_only_no_handoff_authority','node':socket.gethostname(),
                   'workspace_modified':False,'wrapper_executed':False,'arms':results},f,indent=2,sort_keys=True);f.write('\n')


if __name__ == '__main__':
    main()
