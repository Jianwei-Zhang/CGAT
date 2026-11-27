"""Bind the qualified engineering packet to the installed continuity engine."""
import json
from pathlib import Path
import prepare_q0_runtime_transition as p
root=Path(__file__).resolve().parent
base=root.parent; work=base/'gpm_server'
authorization=json.loads((root/'engineering-authorization.json').read_text())
owner_pair=authorization.get('schema')=='q0_exact_owner_pair_v1'
parent, pin, job = (
    ('q0-pair-transition-20261127.WY7Rw2ll','a0ac52d9e238e8d7bf339610c6fa140082fd8f3b42d25e9dc08e1e7edb7d715d',43138304)
    if owner_pair else ('q0-continuity-transition-20261127.bs5d44Do','248ee1e7a93edc6e5c1e14199d1e8c7f0b7e4fed04f2d1d5e3518da4fb631941',43137228))
previous=base/parent/'transition.json'
if p.digest(previous)!=pin:
    raise ValueError('retired transition changed; inspect instead of restaging')
journal_path=previous.parent/'installation/receipt.json'
if owner_pair and p.digest(journal_path)!='3b42d2c97f44843582d07478d4b6bf2cac1dc15d67d83fba6a3074fd549a89b3':
    raise ValueError('previous installation journal changed')
journal=json.loads(journal_path.read_text())
installed={r['relative']:r['sha256'] for r in journal['installed']}
names=p.threshold_runtime_names(root/'runtime'); prefix='.prepare_lib/tools/lgz_core/'
prior={prefix+n:p.digest(work/prefix/n) for n in names if prefix+n not in installed and (work/prefix/n).is_file()}
changes={}
for name in sorted(p.THRESHOLD_POLICY_CHANGES):
    symbol=p.POLICIES.get(name) or p.SELECTOR_POLICIES[name]
    get=p.policy_ast if name in p.POLICIES else p.selector_policy_ast
    old=get(work/prefix/name,symbol);new=get(root/'runtime'/name,symbol)
    if old!=new:changes[name]=p.policy_change(old,new)
manifest={'schema':p.SOURCE_SCHEMA,'workspace':str(work),'git_revision':(root/'source-revision.txt').read_text().strip(),
          'previous_transition':p.record(previous),'previous_job':job,'protected_baseline':43061436,
          'continuous_q0_policy_change':dict(p.CONTINUITY_CHANGE),
          'exact_engineering_change':authorization,
          'q0_supplement_scope':'positive_threshold','proof_repair_package':p.record(work/'metadata/package.tsv'),
          'prior_selector_files':prior,'positive_threshold_policy_changes':changes,
          'regional_mapper_loader_policy':'clear_same_dependencies_v1',
          'files':json.loads((root/'source-files.json').read_text())}
if manifest['git_revision'] != manifest['exact_engineering_change']['runtime_revision']:
    raise ValueError('wrong qualified engineering revision')
if changes:
    raise ValueError('engineering successor cannot change any scientific policy')
p.write_new(root/'candidate-source.json',manifest)
print(json.dumps(p.prepare(root)),flush=True)
