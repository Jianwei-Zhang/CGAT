"""Bind the reviewed packet to the observed retired legacy installation."""
import json
from pathlib import Path
import prepare_q0_runtime_transition as p
root=Path(__file__).resolve().parent
base=root.parent; work=base/'gpm_server'
previous=base/'q0-selection-reuse-20261126.DjPxKFgH/transition.json'
if p.digest(previous)!='5b7408fc2337cf00b92cec23fe0b322c349b6312f50440246c99ec506ae6aec0':
    raise ValueError('retired transition changed; inspect instead of restaging')
journal=json.loads((previous.parent/'installation/receipt.json').read_text())
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
          'previous_transition':p.record(previous),'previous_job':43098569,'protected_baseline':43061436,
          'continuous_q0_policy_change':dict(p.CONTINUITY_CHANGE),
          'q0_supplement_scope':'positive_threshold','proof_repair_package':p.record(work/'metadata/package.tsv'),
          'prior_selector_files':prior,'positive_threshold_policy_changes':changes,
          'regional_mapper_loader_policy':'clear_same_dependencies_v1',
          'files':json.loads((root/'source-files.json').read_text())}
if manifest['git_revision'] != p.CONTINUITY_CHANGE['engine_revision']:
    raise ValueError('wrong reviewed production engine revision')
p.write_new(root/'candidate-source.json',manifest)
print(json.dumps(p.prepare(root)),flush=True)
