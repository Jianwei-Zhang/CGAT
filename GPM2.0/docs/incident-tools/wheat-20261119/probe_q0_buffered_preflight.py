"""Independently validate all 25 original wheat checkpoints with buffered PAF I/O.

This narrowly replaces outer PAF output verification in an isolated reader.
The authentic initial input and native/cross/self runtime verifiers remain in
force. It cannot write a workspace, satisfy the existing loader's validation
file, submit a job, or publish any alignment checkpoint.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

from q0_science_context import checked, digest, opened_transition

BASE_SHA = 'e066d7950f99b35822512c3840ae2a9e0683eede275f30f29747879b32be0035'
CONTRACT_SHA = '899b629ca3d2d2fb2d7e768f3368bd1e94a049d345a571928c09442090ba4ffb'


def reader(path):
    name = 'isolated_buffered_checkpoint_paf_identity'
    if name in sys.modules:
        raise ValueError('unexpected pre-existing buffered reader')
    spec = importlib.util.spec_from_file_location(name, path)
    lib = importlib.util.module_from_spec(spec)
    sys.modules[name] = lib
    try:
        spec.loader.exec_module(lib)
    except BaseException:
        sys.modules.pop(name)
        raise
    return lib


def verifier(base, lib, errors):
    """Run the frozen path discovery and identity helpers for every non-PAF.

    This mirrors only _output_identities from the SHA-pinned old base. The
    earlier prepare() and validate() and all attached cross/self receipts
    remain the actual frozen methods, not a replacement metadata checker.
    """
    class Buffered(base):
        def _output_identities(self, prepared):
            if prepared.kind == 'reference_alignment':
                dataset = prepared.unit_id.removeprefix('ref:')
                run = self.server_dir/f'runs/{dataset}_vs_ref'
                paths = [run/'result.paf', run/'tool_version.txt']
            elif prepared.kind == 'assignment':
                paths = self._assignment_output_paths()
            elif prepared.kind == 'q0_chromosome_alignments':
                paths = self._chromosome_output_paths(prepared.unit_id.split(':',1)[1], alignment_only=True)
            else:
                raise errors('outside the audited initial validation scope')
            records = {}
            for path in paths:
                if path.suffix.lower() != '.paf':
                    continue
                try:
                    row = lib.paf_file_identity(path, relative_to=self.server_dir, require_cigar=True)
                except lib.OrchestrationContractError as exc:
                    raise errors(str(exc)) from exc
                key = self.server_dir/row['path']
                if key in records and records[key] != row:
                    raise errors('inconsistent output aliases during validation')
                records[key] = row
            for path in paths:
                resolved = path.resolve(strict=True)
                if path.suffix.lower() == '.paf' and resolved not in records:
                    raise errors('output alias changed after buffered validation')
                if resolved not in records:
                    records[resolved] = self._identities([resolved])[0]
            return [records[p] for p in sorted(records, key=str)]

        def commit(self, prepared):
            raise errors('isolated checkpoint verifier cannot commit')
    return Buffered


def rows_from_previous(path, transition_sha):
    data = json.loads(path.read_text())
    rows = data['initial_checkpoints']
    if (data.get('status') != 'q0_transition_all_initial_checkpoints_verified_only'
            or data.get('transition_sha256') != transition_sha
            or any(data.get(k) is not False for k in ('workspace_modified','q0_runtime_installed','main_task_submitted'))
            or len(rows) != 25 or len({x['unit_id'] for x in rows}) != 25):
        raise ValueError('not the previous complete real checkpoint proof')
    return rows


def validate(ctx, lib, rows):
    import run_outer_checkpoints as outer
    tools = ctx.work/'.prepare_lib/tools'
    for source, filename, sha in ((ctx.contract,'run_orchestration.py',CONTRACT_SHA),
                                   (outer,'run_outer_checkpoints.py',BASE_SHA)):
        if Path(source.__file__).resolve() != (tools/filename).resolve() or digest(source.__file__) != sha:
            raise ValueError('wrong frozen checkpoint implementation: '+ filename)
    owning = ctx.native_bootstrap.module('authentic_initial_alignment_owner', checked(ctx.plan['dependencies']['entry']))
    units = ctx.base.rr.load_plan(ctx.work)
    if len(units) != 55 or any(x.unit_id == 'degap_gapfill' for x in units):
        raise ValueError('comparison workflow changed')
    owning.configure(ctx)
    base = verifier(outer.OuterCheckpointManager, lib, ctx.contract.OrchestrationContractError)
    manager = ctx.native_original_context.compose(ctx, base, readonly=True)(ctx.work)
    report = []
    for unit in units:
        if unit.unit_id == 'q0_evidence':
            break
        started = time.monotonic()
        prepared = manager.prepare(unit.unit_id, unit.command_relpath)
        if prepared is None or len(report) >= len(rows):
            raise ValueError('unexpected initial unit: '+unit.unit_id)
        outcome = {'unit_id':unit.unit_id,'input_fingerprint':prepared.input_fingerprint,
                   'checkpoint_sha256':digest(prepared.path)}
        if outcome != rows[len(report)]:
            raise ValueError('initial identity differs from original true proof: '+unit.unit_id)
        valid, reason = manager.validate(prepared)
        if not valid or digest(prepared.path) != outcome['checkpoint_sha256']:
            raise ValueError('checkpoint did not pass complete validation: '+unit.unit_id+': '+reason)
        report.append(outcome)
        print(json.dumps({'status':'BUFFERED_INITIAL_CHECKPOINT_VALID', 'unit':unit.unit_id,
                          'completed':len(report), 'seconds':time.monotonic()-started}), flush=True)
    if report != rows:
        raise ValueError('not all 25 initial checkpoints')
    ctx.verify()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe_config', type=Path)
    args = parser.parse_args()
    config_path = args.probe_config.resolve(strict=True)
    root = config_path.parent
    config = json.loads(config_path.read_text())
    if Path.cwd().resolve() != root:
        raise ValueError('run only within the isolated diagnostic directory')
    source = checked(config['candidate_reader'])
    if source.parent != root:
        raise ValueError('buffered reader must come from the isolated packet')
    probe = checked(config['origin_probe'])
    stage = checked(config['original_staged_transition'])
    staged_record = json.loads(checked(config['candidate_prepared']).read_text())
    if (staged_record.get('status') != 'q0_candidate_prepared_not_installed'
            or staged_record['transition'] != config['original_staged_transition']
            or staged_record['previous_transition'] != config['previous_transition']):
        raise ValueError('probe proof does not belong to the prepared loader transition')
    frozen = json.loads(stage.read_text())
    origin = json.loads(probe.read_text())
    if origin['native_origin'] != frozen['native_origin'] or origin['workspace'] != frozen['workspace']:
        raise ValueError('isolated probe is not for the staged transition origin')
    prior_transition = checked(config['previous_transition'])
    prior_report = checked(config['previous_report'])
    if prior_report != prior_transition.with_name('validation.json'):
        raise ValueError('previous report does not belong to previous transition')
    rows = rows_from_previous(prior_report, config['previous_transition']['sha256'])
    clock = time.monotonic()
    with opened_transition(probe, role='probe', caller=__file__, require_installed=False) as ctx:
        report = validate(ctx,reader(source),rows)
        for identity in config.values():
            checked(identity)
    # Not a file accepted by the existing waiting allocation/installation gate.
    with (root/'buffered-proof.json').open('x') as stream:
        json.dump({'status':'buffered_preflight_probe_only_no_handoff_authority',
                   'workspace_modified':False,'main_task_submitted':False,'q0_runtime_installed':False,
                   'bindings':config,'initial_checkpoints':report,'seconds':time.monotonic()-clock}, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
