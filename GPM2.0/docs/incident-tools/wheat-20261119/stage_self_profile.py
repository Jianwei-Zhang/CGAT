"""Stage an isolated initial self plan; never submit, stop, or edit a workspace.

Preview plans cannot execute. Final plans require the successful complete
moderate candidate; adoption itself still verifies all source/output bytes on
the owning compute job. Existing native markers are only inspected here and
must pass full content verification by the controller before reuse.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import sys

import full_self_seed_pilot as pilot
from self_seed_profile import POLICY, SCHEMA
from self_profile_bindings import SCHEMA as DISPATCH_SCHEMA

HERE = Path(__file__).resolve().parent
MODULES = {'stager': 'stage_self_profile.py', 'entry': 'resume_with_self_profile.py',
           'reader': 'self_profile_evidence_reader.py', 'context': 'self_profile_context.py',
           'support': 'self_profile_bindings.py', 'runtime': 'self_seed_profile.py',
           'pilot': 'full_self_seed_pilot.py', 'admission': 'self_profile_admission.py',
           'audit_exporter': 'self_profile_audit.py', 'cross_audit': 'export_routing_provenance.py'}


def record(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': pilot.digest(path)}


def calibration(candidate, fraction="0.001", audit=None):
    candidate = Path(candidate).resolve(strict=True)
    data = json.loads(candidate.read_text())
    if fraction not in ("0.001", "0.005"):
        raise ValueError('unsupported execution profile fraction')
    common = (data.get('analysis_workspace_modified') is False and data.get('candidate_adopted') is False
              and data.get('mapping', {}).get('returncode') == 0)
    if fraction == "0.001":
        valid = (data.get('scope') == 'one_complete_self_query_moderate_candidate_only'
            and data.get('status') == 'moderate_candidate_complete_not_adopted'
            and data.get('seed_fraction') == fraction and data.get('restoration', {}).get('returncode') == 0
            and data.get('whole_records_preserved') is True)
    else:
        command, native = data.get('command', []), data.get('native_command', [])
        valid = (data.get('scope') == 'one_complete_self_query_candidate_only'
            and data.get('status') == 'candidate_complete_not_compared_not_adopted'
            and len(native) >= 4 and command == native[:-2] + ['-f', fraction] + native[-2:]
            and data.get('driver_sha256') == pilot.digest(Path(pilot.__file__)))
        if audit is None:
            raise ValueError('aggressive profile requires its complete evidence-loss audit')
        proof = json.loads(Path(audit).read_text())
        if (proof.get('status') != 'full_self_identity_strata_compared_not_adopted'
                or proof.get('candidate_adopted') is not False
                or proof.get('analysis_workspace_modified') is not False
                or not data.get('outputs')
                or any(proof.get('checked_source_files', {}).get(path) != value
                       for path, value in data['outputs'].items())):
            raise ValueError('aggressive calibration audit does not bind this candidate')
    if not common or not valid:
        raise ValueError('a completed whole candidate matching the profile is required, not partial mapping output')
    stderr = candidate.parent / 'stderr.log'
    proof = data['outputs'].get(str(stderr))
    if not proof or pilot.identities([stderr])[str(stderr)] != proof:
        raise ValueError('candidate resource evidence differs')
    pilot.verify_completion(stderr, 1)
    peaks = re.findall(r'Peak RSS: ([0-9.]+) GB', stderr.read_text())
    if len(peaks) != 1 or not 0 < float(peaks[0]) < 10000:
        raise ValueError('candidate peak RSS is missing or invalid')
    measured = {'report': record(candidate), 'observed_peak_rss_gb': float(peaks[0]), 'max_fast': 1,
        'interpretation': 'observed peak only; long queries remain exclusive, not a memory guarantee'}
    if audit is not None:
        measured['evidence_loss_audit'] = record(audit)
    return data, measured


def stage(work, cross_plan, reader_helper, output, *, preview, candidate=None, fraction="0.001", audit=None):
    work, cross_plan = work.resolve(strict=True), cross_plan.resolve(strict=True)
    output = output.resolve()
    if output.exists() or output == work or output.is_relative_to(work) or work.is_relative_to(output):
        raise ValueError('use a new isolated staging directory outside the workspace')
    sys.path.insert(0, str(work / '.prepare_lib/tools'))
    import run_orchestration as contract
    from self_profile_admission import POLICY as RESERVATIONS
    cross = json.loads(cross_plan.read_text())
    if cross.get('workspace') != str(work) or cross.get('schema') != 'incident_q0_routing_v1':
        raise ValueError('cross plan belongs to another workflow')
    source, measured = (None, {'max_fast': 1, 'interpretation': 'preview has no completed full candidate'})
    if candidate is not None:
        source, measured = calibration(candidate, fraction, audit)
    elif not preview:
        raise ValueError('final staging requires completed full candidate calibration')
    if fraction not in ("0.001", "0.005"):
        raise ValueError("unsupported execution profile fraction")
    policy = {**POLICY, "seed_fraction": fraction}
    dependencies = {name: record(HERE / filename) for name, filename in MODULES.items()}
    dependencies.update(cross_plan=record(cross_plan), reader_helper=record(reader_helper))
    if audit is not None:
        dependencies['calibration_audit'] = record(audit)
    output.mkdir(); (output / 'profiles').mkdir(); (output / 'commands').mkdir()
    plan_path = output / 'self-plan.json'
    launcher = output / 'prepare_q0_evidence.sh'
    launcher.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexport PYTHONDONTWRITEBYTECODE=1\n'
        + '(cd ' + shlex.quote(str(HERE)) + ' && sha256sum -c code.sha256)\n'
        + 'exec python3 -B -u ' + shlex.quote(dependencies['reader']['path'])
        + ' --plan ' + shlex.quote(str(plan_path)) + ' --server-dir ' + shlex.quote(str(work))
        + ' --threads 32 --minimap2 minimap2\n')
    dependencies['launcher'] = record(launcher)
    operations, adoption_count = [], 0
    for tasks_path in sorted((work / 'runs').glob('chr_*/q0_alignment_tasks.json')):
        commands = [work / row['command'] for row in json.loads(tasks_path.read_text())['tasks']]
        manifests = sorted({command.parents[2] / 'self_batch_manifest.json' for command in commands
                            if command.parent.parent.name == 'batches'})
        for manifest_path in manifests:
            native = json.loads(manifest_path.read_text())
            rel = manifest_path.parent.relative_to(work).as_posix()
            selected, adoptions, native_commands = [], {}, {}
            for i, batch in enumerate(native['batches']):
                command = Path(batch['directory']) / 'command.sh'
                if command not in commands:
                    raise ValueError('self batch is not in its q0 task plan')
                native_commands[str(i)] = contract.file_identity(command, relative_to=work)
                marker = Path(batch['directory']) / 'complete.json'
                if marker.exists():
                    if json.loads(marker.read_text()).get('key') != batch['key']:
                        raise ValueError('non-native marker exists; reuse its original frozen self plan instead')
                    continue
                if len(batch['entries']) == 1 and batch['entries'][0]['length'] >= POLICY['minimum_query_bases']:
                    selected.append(i)
                    if (fraction == "0.001" and source is not None and source.get('native_batch_key') == batch['key']
                            and source.get('native_command', [None])[-1] == batch['query']):
                        adoptions[str(i)] = measured['report']; adoption_count += 1
            label = rel.replace('/', '__')
            profile_path = output / 'profiles' / (label + '.json')
            profile = {'schema': SCHEMA, 'workspace': str(work), 'policy': policy,
                'native_manifest': record(manifest_path), 'selected_batches': selected, 'adoptions': adoptions,
                'dependencies': {'runtime': dependencies['runtime'], 'pilot': dependencies['pilot'],
                    'helper': record(work / '.prepare_lib/tools/self_alignment_batches.py'),
                    'contract': record(work / '.prepare_lib/tools/run_orchestration.py')}}
            profile_path.write_text(json.dumps(profile, indent=2, sort_keys=True) + '\n')
            scripts = {}
            for i in selected:
                path = output / 'commands' / (label + '__%05d.sh' % i)
                path.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexec python3 -B -u '
                    + shlex.quote(dependencies['runtime']['path']) + ' --profile ' + shlex.quote(str(profile_path))
                    + ' --batch-index ' + str(i) + '\n')
                path.chmod(0o755); scripts[str(i)] = contract.file_identity(path)
            operations.append({'operation': rel, 'unit_id': 'q0_chr:' + tasks_path.parent.name[4:],
                'profile': record(profile_path), 'scripts': scripts, 'native_commands': native_commands,
                'task_manifest': record(tasks_path)})
    if not operations or adoption_count > 1:
        raise ValueError('unexpected self operation/adoption inventory')
    plan = {'schema': DISPATCH_SCHEMA, 'workspace': str(work), 'preview_only': preview,
        'dependencies': dependencies, 'operations': operations,
        'resource_policy': {'reservation_policy': RESERVATIONS, 'max_fast': measured['max_fast'], 'calibration': measured},
        'prior_launcher': record(work / 'prepare_q0_evidence.sh'),
        'staging_scope': 'metadata_only_native_markers_not_content_accepted'}
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + '\n')
    from self_profile_bindings import SelfBindings
    bindings = SelfBindings(work, plan_path, contract)
    proof = {'status': 'isolated_self_plan_staged_not_installed', 'preview_only': preview,
        'plan': record(plan_path), 'self_operations': len(operations),
        'approximate_batches': sum(len(p.selected) for p in bindings.profiles.values()), 'candidate_adoptions': adoption_count}
    (output / 'staging-receipt.json').write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')
    print(json.dumps(proof, indent=2), flush=True)
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('work', 'cross-plan', 'reader-helper', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--fraction', choices=('0.001', '0.005'), default='0.001')
    parser.add_argument('--audit', type=Path)
    args = parser.parse_args()
    stage(args.work, args.cross_plan, args.reader_helper, args.output, preview=args.preview, candidate=args.candidate, fraction=args.fraction, audit=args.audit)


if __name__ == '__main__':
    main()
