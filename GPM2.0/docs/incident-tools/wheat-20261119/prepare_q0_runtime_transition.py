"""Prepare an isolated NEW-q0 transition, without installing or stopping jobs.

The source packet binds the previous installed transition and the exact new
files. The native origin stays unchanged. Policy changes are rejected except
for explicitly bound positive-threshold routing/budget deltas.
A real read-only 25-checkpoint preflight and allocation-ready gate follow this
metadata-only step. Never rerun it over an existing candidate/journal.
"""
import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path
import re
import shlex

from q0_science_context import checked, digest

SOURCE_SCHEMA = 'incident_q0_candidate_source_v1'
HELPERS = {'context':'q0_science_context.py', 'entry':'resume_q0_science.py',
           'reader':'read_q0_science.py', 'stager':'stage_q0_science.py'}
POLICIES = {'q0_preparation.py':'POLICY', 'q0_regional_discovery.py':'REGIONAL_POLICY',
            'q0_regional_candidates.py':'CANDIDATE_POLICY', 'q0_regional_mapping.py':'BASE_FLAGS'}
LAUNCHER = 'prepare_q0_evidence.sh'
DECLARATION = 'metadata/incident_q0_routing_reader.json'
REPAIR_PROFILE = 'decision_frontier_repair'
THRESHOLD_PROFILE = 'positive_threshold'
# These are the already-approved local-only routing/budget changes, not a
# permission to relax alignment scores or placement acceptance. Exact old/new
# policy AST identities must be declared in the source packet.
THRESHOLD_POLICY_CHANGES = {'q0_regional_discovery.py', 'q0_regional_candidates.py', 'q0_paths.py'}
SELECTOR_POLICIES = {'q0_admission.py': 'AdmissionPolicy', 'q0_paths.py': 'PathPolicy'}


def child(root, relative):
    rel = Path(relative)
    if (not relative or rel.is_absolute() or '..' in rel.parts or '\\' in relative):
        raise ValueError('unsafe candidate source path')
    current = root
    for part in rel.parts:
        current /= part
        if current.is_symlink():
            raise ValueError('linked candidate source/target')
    if not current.resolve().is_relative_to(root):
        raise ValueError('candidate source/target escaped root')
    return current


def record(path):
    return {'path':str(path), 'sha256':digest(path)}


def runtime_names(path, function='builder_identity'):
    tree = ast.parse(path.read_text())
    identity = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function), None)
    if identity is None:
        raise ValueError('candidate lacks a bound identity function: '+function)
    names = sorted({n.value for n in ast.walk(identity)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.endswith('.py')})
    if path.name not in names or any(not re.fullmatch(r'[A-Za-z0-9_]+\.py', n) for n in names):
        raise ValueError('candidate has an unsafe/empty runtime inventory: '+function)
    return names


def threshold_runtime_names(root):
    """Close the Q0-only relative imports and identity-file references."""
    pending = ['q0_preparation.py', 'q0_admission.py', 'q0_threshold_acceptance.py', 'q0_threshold_prepare.py']
    names = set()
    while pending:
        name = pending.pop()
        if name in names:
            continue
        if name != 'common.py' and not re.fullmatch(r'q0_[a-z_]+\.py', name):
            raise ValueError('threshold closure escaped Q0 modules')
        tree = ast.parse(child(root, name).read_text())
        names.add(name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                modules = [node.module.split('.')[0]] if node.module else [n.name for n in node.names]
                pending.extend(mod+'.py' for mod in modules)
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and re.fullmatch(r'(?:q0_[a-z_]+|common)\.py', node.value)):
                pending.append(node.value)
    names.add('__init__.py')
    return names


def policy_change(before, after):
    return {'prior_ast_sha256': hashlib.sha256(before.encode()).hexdigest(),
            'candidate_ast_sha256': hashlib.sha256(after.encode()).hexdigest()}


def selector_policy_ast(path, symbol):
    tree = ast.parse(path.read_text())
    node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == symbol), None)
    if node is None:
        raise ValueError('required selector policy is missing: '+symbol)
    return ast.dump(node, include_attributes=False)


def repair_inputs(work, manifest, selector_only, installed):
    package = child(work, 'metadata/package.tsv')
    bound_package = record(package)
    with package.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    if len(rows) != 1 or rows[0].get('reads_qc_enabled') != 'false':
        raise ValueError('q0 proof repair requires a bound no-reads-QC workspace')
    if manifest.get('proof_repair_package') != bound_package:
        raise ValueError('q0 proof repair package identity differs')
    supplemental = manifest.get('prior_selector_files')
    if not isinstance(supplemental, dict):
        raise ValueError('q0 proof repair lacks prior selector identities')
    prefix = '.prepare_lib/tools/lgz_core/'
    expected = {prefix+name for name in selector_only if prefix+name not in installed
                and child(work, prefix+name).is_file()}
    if set(supplemental) != expected:
        raise ValueError('prior selector identity inventory differs')
    for relative, expected_sha in supplemental.items():
        if digest(child(work, relative)) != expected_sha:
            raise ValueError('prior selector identity differs: '+relative)
    return bound_package, supplemental


def policy_ast(path, symbol):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == symbol for n in node.targets):
            return ast.dump(node.value, include_attributes=False)
    raise ValueError('required scientific policy is missing: '+symbol)


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True); stream.write('\n')


def prepare(bundle):
    bundle = Path(bundle).resolve(strict=True)
    manifest_path = child(bundle, 'candidate-source.json')
    manifest = json.loads(manifest_path.read_text()); manifest_before = record(manifest_path)
    if (manifest.get('schema') != SOURCE_SCHEMA or not re.fullmatch(r'[a-f0-9]{40}', manifest.get('git_revision', ''))
            or type(manifest.get('previous_job')) is not int or manifest['previous_job'] < 1
            or type(manifest.get('protected_baseline')) is not int or manifest['protected_baseline'] < 1
            or manifest['previous_job'] == manifest['protected_baseline']):
        raise ValueError('invalid candidate source/job identity')
    scope = manifest.get('regional_mapper_loader_policy')
    if 'regional_mapper_loader_policy' in manifest and scope != 'clear_same_dependencies_v1':
        raise ValueError('invalid regional mapper loader candidate policy')
    supplement = manifest.get('q0_supplement_scope')
    if ('q0_supplement_scope' in manifest and supplement not in (REPAIR_PROFILE, THRESHOLD_PROFILE)
            or supplement is None and any(key in manifest for key in ('proof_repair_package', 'prior_selector_files'))):
        raise ValueError('invalid candidate q0 supplement scope')
    declared_changes = manifest.get('positive_threshold_policy_changes', {})
    if (not isinstance(declared_changes, dict) or not set(declared_changes) <= THRESHOLD_POLICY_CHANGES
            or supplement != THRESHOLD_PROFILE and 'positive_threshold_policy_changes' in manifest):
        raise ValueError('invalid positive-threshold policy change declaration')
    previous_path = checked(manifest['previous_transition'])
    previous = json.loads(previous_path.read_text())
    work = Path(previous['workspace']).resolve(strict=True)
    if (previous.get('schema') != 'incident_q0_science_transition_v1' or previous.get('phase') != 'prepared'
            or previous.get('scientific_builder_modified') is not True
            or str(work) != manifest.get('workspace') or bundle.is_relative_to(work)
            or previous_path.is_relative_to(work)):
        raise ValueError('candidate and previous explicit transition scopes differ')
    if child(work, 'metadata/grt_q0_evidence.json').exists():
        raise ValueError('q0 evidence already published; do not supersede completed work')
    for row in previous['dependencies'].values():
        checked(row)
    checked(previous['native_origin'])
    journal_path = previous_path.parent/'installation/receipt.json'
    journal_before = record(journal_path); journal = json.loads(journal_path.read_text())
    if journal.get('status') != 'installed' or journal.get('transition_sha256') != manifest['previous_transition']['sha256']:
        raise ValueError('previous installation has no matching successful journal')
    installed = {row['relative']:row['sha256'] for row in journal['installed']}
    if len(installed) != len(journal['installed']):
        raise ValueError('duplicate previous installed file')
    for relative, expected in installed.items():
        if digest(child(work, relative)) != expected:
            raise ValueError('previous installed runtime/declaration drifted: '+relative)
    if (installed.get(LAUNCHER) != previous['launcher']['sha256']
            or any(installed.get(row['relative']) != row['new_sha256'] for row in previous['runtime'])):
        raise ValueError('previous transition and installation inventories differ')
    for row in previous['runtime']:
        checked(row['source'])
        if row['new_sha256'] != row['source']['sha256']:
            raise ValueError('previous runtime source binding differs')
    declaration = json.loads(child(work, DECLARATION).read_text())
    if (declaration.get('transition_sha256') != manifest['previous_transition']['sha256']
            or declaration.get('reader_sha256') != previous['dependencies']['reader']['sha256']
            or declaration.get('scientific_builder_modified') is not True):
        raise ValueError('previous reader declaration is not the installed transition')
    sources = {}
    for row in manifest['files']:
        path = child(bundle, row['relative'])
        if row['relative'] in sources or digest(path) != row['sha256']:
            raise ValueError('candidate source changed or duplicated')
        sources[row['relative']] = record(path)
    names = set(runtime_names(child(bundle, 'runtime/q0_preparation.py')))
    repair_package = None
    if supplement is not None:
        selector = set(runtime_names(child(bundle, 'runtime/q0_admission.py'), 'selector_identity'))
        if not set(SELECTOR_POLICIES) <= selector:
            raise ValueError('candidate omits a required selector policy module')
        if supplement == THRESHOLD_PROFILE:
            selector |= threshold_runtime_names(bundle/'runtime')
        prior_names = selector | names if supplement == THRESHOLD_PROFILE else selector - names
        repair_package, prior_selector = repair_inputs(work, manifest, prior_names, installed)
        installed = {**installed, **prior_selector}
        names |= selector
    required = {'runtime/'+name for name in names} | set(HELPERS.values()) | {'q0_science_handoff_gate.py', 'prepare_q0_runtime_transition.py'}
    if supplement == THRESHOLD_PROFILE:
        required.add('support/workspace_layout.py')
    if set(sources) != required:
        raise ValueError('candidate source closure differs from builder/entry inventory')
    runtime = []; policy_checks = []
    for name in sorted(names):
        relative = '.prepare_lib/tools/lgz_core/'+name
        target = child(work, relative)
        prior = installed.get(relative)
        if prior is None and target.exists():
            raise ValueError('unexpected existing candidate runtime target: '+relative)
        symbol = POLICIES.get(name) or (SELECTOR_POLICIES.get(name) if supplement is not None else None)
        if symbol:
            extract = policy_ast if name in POLICIES else selector_policy_ast
            before = extract(target, symbol) if prior is not None else None
            after = extract(child(bundle, 'runtime/'+name), symbol)
            equal = before == after
            if not equal:
                change = policy_change(before or '', after)
                if (supplement != THRESHOLD_PROFILE or name not in THRESHOLD_POLICY_CHANGES
                        or prior is None or declared_changes.get(name) != change):
                    kind = 'scientific' if name in POLICIES else 'selector'
                    raise ValueError('candidate changes a '+kind+' policy: '+name)
            elif name in declared_changes:
                raise ValueError('declared policy change has no matching difference: '+name)
            policy_checks.append({'file':name, 'symbol':symbol, 'ast_equal':equal,
                                  **({'explicit_change':change} if not equal else {})})
        runtime.append({'relative':relative, 'prior_sha256':prior, 'source':sources['runtime/'+name],
                        'new_sha256':sources['runtime/'+name]['sha256']})
    if set(declared_changes) != {row['file'] for row in policy_checks if not row['ast_equal']}:
        raise ValueError('positive-threshold policy changes are incomplete or unused')
    if supplement == THRESHOLD_PROFILE:
        relative = '.prepare_lib/tools/workspace_layout.py'
        # This support module is new in the legacy runtime. An existing file
        # needs a separate reviewed migration, never an assumed overwrite.
        if child(work, relative).exists():
            raise ValueError('unexpected existing workspace layout support')
        source = sources['support/workspace_layout.py']
        runtime.append({'relative':relative, 'prior_sha256':None, 'source':source,
                        'new_sha256':source['sha256']})
    for name in ('transition.json', LAUNCHER, 'candidate-prepared.json'):
        if child(bundle, name).exists():
            raise ValueError('candidate output already exists; inspect rather than overwrite')
    if child(bundle, 'installation').exists():
        raise ValueError('candidate already has an installation journal')
    transition_path = bundle/'transition.json'
    argv = ['python3','-B','-u',str(bundle/HELPERS['reader']), '--transition',str(transition_path),
            '--server-dir',str(work), '--threads','32', '--minimap2','minimap2']
    launcher = ('#!/usr/bin/env bash\nset -euo pipefail\nexport PYTHONDONTWRITEBYTECODE=1\n'
                'exec '+shlex.join(argv)+'\n')
    with (bundle/LAUNCHER).open('x') as stream:
        stream.write(launcher)
    (bundle/LAUNCHER).chmod(0o755)
    transition = {'schema':'incident_q0_science_transition_v1', 'phase':'prepared', 'workspace':str(work),
        'scientific_builder_modified':True, 'dependencies':{role:sources[name] for role,name in HELPERS.items()},
        'native_origin':previous['native_origin'], 'runtime':runtime, 'launcher':record(bundle/LAUNCHER),
        'prior_launcher_sha256':installed[LAUNCHER], 'prior_declaration_sha256':installed[DECLARATION]}
    if scope is not None:
        transition['regional_mapper_loader_policy'] = scope
    if supplement is not None:
        transition['q0_supplement_scope'] = supplement
        transition['proof_repair_package'] = repair_package
        checked(repair_package)
    if supplement == THRESHOLD_PROFILE:
        transition['positive_threshold_policy_changes'] = declared_changes
    write_new(transition_path, transition)
    checked(manifest_before); checked(journal_before); checked(manifest['previous_transition'])
    for relative, expected in installed.items():
        if digest(child(work, relative)) != expected:
            raise ValueError('previous installation changed during candidate preparation')
    if child(work, 'metadata/grt_q0_evidence.json').exists():
        raise ValueError('q0 completed during staging; preserve it and inspect candidate')
    report = {'status':'q0_candidate_prepared_not_installed', 'git_revision':manifest['git_revision'],
        'transition':record(transition_path), 'previous_transition':manifest['previous_transition'],
        'previous_installation':journal_before, 'previous_job':manifest['previous_job'],
        'protected_baseline':manifest['protected_baseline'], 'runtime_files':len(runtime),
        'new_runtime_files':[r['relative'] for r in runtime if r['prior_sha256'] is None],
        'changed_runtime_files':[r['relative'] for r in runtime if r['prior_sha256'] != r['new_sha256']],
        'unchanged_runtime_files':[r['relative'] for r in runtime if r['prior_sha256'] == r['new_sha256']],
        'scientific_policy_ast_checks':policy_checks, 'workspace_modified':False, 'job_stopped':False,
        'initial_alignment_profiles_modified':False, 'native_checkpoints_rewritten':False,
        'existing_cache_adoption_repeated':False, 'outer_contract_replaced':False}
    if supplement is not None:
        checked(repair_package)
        report['q0_supplement_scope'] = supplement
    write_new(bundle/'candidate-prepared.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args()
    if Path(__file__).resolve() != args.bundle.resolve()/'prepare_q0_runtime_transition.py':
        raise SystemExit('candidate preparer must run from its bound isolated packet')
    print(json.dumps(prepare(args.bundle)), flush=True)
