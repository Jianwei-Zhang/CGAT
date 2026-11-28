import json
import shlex
from pathlib import Path
import tempfile
import unittest

import prepare_q0_runtime_transition as prep


class CandidatePreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.work=self.root/'work';self.work.mkdir()
        self.bundle=self.root/'candidate';(self.bundle/'runtime').mkdir(parents=True)
        old=self.root/'old';(old/'runtime').mkdir(parents=True);(old/'installation').mkdir()
        (self.work/'.prepare_lib/tools/lgz_core').mkdir(parents=True);(self.work/'metadata').mkdir()
        before="POLICY={'version':5}\ndef builder_identity():\n return ('q0_preparation.py','common.py')\n"
        after=before.replace("'common.py')", "'common.py','q0_regional_execution.py')")
        old_rows=[]
        for name,content in [('q0_preparation.py',before),('common.py','COMMON=1\n')]:
            source=old/'runtime'/name;source.write_text(content)
            target=self.work/'.prepare_lib/tools/lgz_core'/name;target.write_text(content)
            old_rows.append({'relative':str(target.relative_to(self.work)), 'source':prep.record(source),
                             'new_sha256':prep.digest(source)})
        launcher=old/prep.LAUNCHER;launcher.write_text('# old launcher\n')
        (self.work/prep.LAUNCHER).write_text(launcher.read_text())
        dependencies={}
        for role,name in prep.HELPERS.items():
            p=old/name;p.write_text('# old '+role+'\n');dependencies[role]=prep.record(p)
        native=old/'native.json';native.write_text('{}')
        previous={'schema':'incident_q0_science_transition_v1','phase':'prepared','workspace':str(self.work),
                  'scientific_builder_modified':True,'runtime':old_rows,'launcher':prep.record(launcher),
                  'dependencies':dependencies,'native_origin':prep.record(native)}
        self.previous=old/'transition.json';self.previous.write_text(json.dumps(previous))
        declaration={'transition_sha256':prep.digest(self.previous),'reader_sha256':dependencies['reader']['sha256'],
                     'scientific_builder_modified':True}
        (self.work/prep.DECLARATION).write_text(json.dumps(declaration))
        installed=[{'relative':str(p.relative_to(self.work)),'sha256':prep.digest(p)} for p in self.work.rglob('*') if p.is_file()]
        self.journal=old/'installation/receipt.json'
        self.journal.write_text(json.dumps({'status':'installed','transition_sha256':prep.digest(self.previous),
                                            'installed':installed}))
        for name,content in [('q0_preparation.py',after),('common.py','COMMON=1\n'),('q0_regional_execution.py','ENABLED=True\n')]:
            (self.bundle/'runtime'/name).write_text(content)
        for name in set(prep.HELPERS.values())|{'q0_science_handoff_gate.py','prepare_q0_runtime_transition.py'}:
            (self.bundle/name).write_text('# new '+name+'\n')
        self.manifest={'schema':prep.SOURCE_SCHEMA,'git_revision':'a'*40,'workspace':str(self.work),
                       'previous_transition':prep.record(self.previous),'previous_job':1,'protected_baseline':2}
        self.save_manifest()
        self.before=self.snapshot()

    def snapshot(self):
        return {str(p.relative_to(self.work)):p.read_bytes() for p in self.work.rglob('*') if p.is_file()}

    def save_manifest(self):
        self.manifest['files']=[{'relative':str(p.relative_to(self.bundle)),'sha256':prep.digest(p)}
                                for p in self.bundle.rglob('*.py')]
        (self.bundle/'candidate-source.json').write_text(json.dumps(self.manifest))

    def test_prepares_exact_slice_with_new_module_but_no_workspace_write_or_cache_move(self):
        result=prep.prepare(self.bundle)
        self.assertEqual(result['status'],'q0_candidate_prepared_not_installed')
        self.assertEqual(result['runtime_files'],3)
        self.assertEqual(result['new_runtime_files'],['.prepare_lib/tools/lgz_core/q0_regional_execution.py'])
        self.assertEqual(result['unchanged_runtime_files'],['.prepare_lib/tools/lgz_core/common.py'])
        self.assertEqual(self.snapshot(),self.before)
        self.assertFalse(result['existing_cache_adoption_repeated'])
        transition=json.loads((self.bundle/'transition.json').read_text())
        self.assertNotIn('mapping_adoptions',transition)
        self.assertNotIn('reference_index_adoption',transition)
        row=next(r for r in transition['runtime'] if r['relative'].endswith('q0_regional_execution.py'))
        self.assertIsNone(row['prior_sha256'])
        self.assertEqual(transition['native_origin'],json.loads(self.previous.read_text())['native_origin'])
        self.assertTrue(all(r['ast_equal'] for r in result['scientific_policy_ast_checks']))
        with self.assertRaisesRegex(ValueError,'already exists'):prep.prepare(self.bundle)
        self.assertEqual(self.snapshot(),self.before)

    def test_launcher_quotes_paths_without_an_incidental_space_veto(self):
        destination=self.bundle.with_name('candidate with spaces');self.bundle.rename(destination);self.bundle=destination
        prep.prepare(self.bundle)
        argv=shlex.split((self.bundle/prep.LAUNCHER).read_text().splitlines()[-1])
        self.assertEqual(argv[0:4],['exec','python3','-B','-u'])
        self.assertEqual(argv[argv.index('--transition')+1],str(self.bundle/'transition.json'))
        self.assertEqual(argv[argv.index('--server-dir')+1],str(self.work))

    def test_loader_policy_is_explicit_and_does_not_mutate_live_workspace(self):
        self.manifest['regional_mapper_loader_policy'] = 'unsupported_policy'
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'loader candidate policy'):
            prep.prepare(self.bundle)
        self.assertFalse((self.bundle/prep.LAUNCHER).exists())
        self.manifest['regional_mapper_loader_policy'] = 'clear_same_dependencies_v1'
        self.save_manifest()
        prep.prepare(self.bundle)
        transition = json.loads((self.bundle/'transition.json').read_text())
        self.assertEqual(transition['regional_mapper_loader_policy'], 'clear_same_dependencies_v1')
        self.assertEqual(self.snapshot(), self.before)

    def bind_repair_candidate(self):
        package = self.work/'metadata/package.tsv'
        package.write_text('reads_qc_enabled\nfalse\n')
        initial = {
            'q0_admission.py': "class AdmissionPolicy:\n    minimum_bp=100\ndef selector_identity():\n    return ('q0_admission.py','q0_paths.py','q0_coverage.py','common.py')\n",
            'q0_paths.py': 'class PathPolicy:\n    maximum_evaluations=20000\n',
            'q0_coverage.py': 'VALUE=1\n',
        }
        prior = {}
        for name, content in initial.items():
            relative = '.prepare_lib/tools/lgz_core/'+name
            source = self.work/relative
            source.write_text(content)
            prior[relative] = prep.digest(source)
            (self.bundle/'runtime'/name).write_text(content+'\nVALUE=2\n')
        self.manifest.update(q0_supplement_scope=prep.REPAIR_PROFILE, proof_repair_package=prep.record(package),
                             prior_selector_files=prior)
        self.save_manifest()
        self.before = self.snapshot()

    def test_explicit_proof_repair_binds_new_selector_and_real_prior_without_writing_workspace(self):
        self.bind_repair_candidate()
        result = prep.prepare(self.bundle)
        self.assertEqual(result['q0_supplement_scope'], prep.REPAIR_PROFILE)
        transition = json.loads((self.bundle/'transition.json').read_text())
        self.assertEqual(transition['proof_repair_package'], prep.record(self.work/'metadata/package.tsv'))
        installed_prior = self.manifest['prior_selector_files']
        for row in transition['runtime']:
            if row['relative'] in installed_prior:
                self.assertEqual(row['prior_sha256'], installed_prior[row['relative']])
        self.assertEqual(result['runtime_files'], 6)
        self.assertEqual({r['symbol'] for r in result['scientific_policy_ast_checks']},
                         {'POLICY', 'AdmissionPolicy', 'PathPolicy'})
        self.assertEqual(self.snapshot(), self.before)

    def test_repair_fails_closed_on_unknown_prior_or_changed_selector_policy(self):
        self.bind_repair_candidate()
        rel = '.prepare_lib/tools/lgz_core/q0_coverage.py'
        previous = self.manifest['prior_selector_files'].pop(rel)
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'prior selector identity inventory'):
            prep.prepare(self.bundle)
        self.manifest['prior_selector_files'][rel] = previous
        p = self.bundle/'runtime/q0_paths.py'
        p.write_text(p.read_text().replace('20000','10000'))
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'changes a selector policy'):
            prep.prepare(self.bundle)
        self.assertFalse((self.bundle/prep.LAUNCHER).exists())
        self.assertEqual(self.snapshot(), self.before)

    def test_reads_qc_blocks_candidate_even_if_its_new_package_bytes_are_bound(self):
        self.bind_repair_candidate()
        package = self.work/'metadata/package.tsv'
        package.write_text('reads_qc_enabled\ntrue\n')
        self.manifest['proof_repair_package'] = prep.record(package)
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'no-reads-QC workspace'):
            prep.prepare(self.bundle)
        self.assertFalse((self.bundle/'transition.json').exists())

    def bind_threshold_candidate(self):
        self.bind_repair_candidate()
        self.manifest['q0_supplement_scope'] = prep.THRESHOLD_PROFILE
        (self.bundle/'runtime/__init__.py').write_text('# Q0 compatibility bootstrap\n')
        (self.bundle/'support').mkdir()
        (self.bundle/'support/workspace_layout.py').write_text('# legacy support\n')
        # Include transitive and identity-only dependencies in addition to the
        # old builder/selector lists. They must be bound, never found by accident.
        (self.bundle/'runtime/q0_threshold_acceptance.py').write_text(
            "from .q0_sources import SourceKey\nRULE='q0_threshold_questions.py'\n")
        (self.bundle/'runtime/q0_sources.py').write_text('class SourceKey: pass\n')
        (self.bundle/'runtime/q0_threshold_questions.py').write_text('VALUE=1\n')
        (self.bundle/'runtime/q0_threshold_prepare.py').write_text('from . import q0_preparation\n')
        path=self.bundle/'runtime/q0_paths.py'
        before=prep.selector_policy_ast(path, 'PathPolicy')
        path.write_text(path.read_text().replace('20000', 'None'))
        self.manifest['positive_threshold_policy_changes'] = {
            'q0_paths.py':prep.policy_change(before,prep.selector_policy_ast(path,'PathPolicy'))}
        self.save_manifest()
        self.before=self.snapshot()

    def test_threshold_explicitly_binds_policy_delta_closure_and_legacy_support(self):
        self.bind_threshold_candidate()
        report=prep.prepare(self.bundle)
        self.assertEqual(report['q0_supplement_scope'],'positive_threshold')
        transition=json.loads((self.bundle/'transition.json').read_text())
        names={r['relative'] for r in transition['runtime']}
        self.assertIn('.prepare_lib/tools/workspace_layout.py',names)
        self.assertIn('.prepare_lib/tools/lgz_core/q0_threshold_questions.py',names)
        self.assertEqual(transition['positive_threshold_policy_changes'],self.manifest['positive_threshold_policy_changes'])
        self.assertEqual(self.snapshot(),self.before)

    def test_admission_change_is_not_a_generic_budget_permission(self):
        self.bind_threshold_candidate()
        path = self.bundle/'runtime/q0_admission.py'
        before = prep.selector_policy_ast(path, 'AdmissionPolicy')
        path.write_text(path.read_text().replace('minimum_bp=100', 'minimum_bp=200'))
        self.manifest['positive_threshold_policy_changes']['q0_admission.py'] = prep.policy_change(
            before, prep.selector_policy_ast(path, 'AdmissionPolicy'))
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'requires explicit continuous'):
            prep.prepare(self.bundle)
        self.assertEqual(self.snapshot(), self.before)

    def test_reviewed_continuity_files_and_declaration_are_exact(self):
        import shutil
        core = Path(__file__).resolve().parents[3]/'server/tools/lgz_core'
        for name in prep.CONTINUITY_FILES:
            shutil.copyfile(core/name, self.bundle/'runtime'/name)
        manifest = {'git_revision': prep.CONTINUITY_CHANGE['engine_revision'],
                    'q0_supplement_scope': prep.THRESHOLD_PROFILE,
                    'continuous_q0_policy_change': dict(prep.CONTINUITY_CHANGE)}
        # The working tree is now an engineering successor, not the byte-pinned
        # original. It MUST NOT pass using the old scientific declaration alone.
        with self.assertRaisesRegex(ValueError, 'differs from reviewed'):
            prep.validate_continuity_change(self.bundle, manifest)
        for name, expected in prep.CONTINUITY_FILES.items():
            if name in ('q0_admission.py', 'q0_collinear.py', 'q0_reference_locus.py'):
                self.assertNotEqual(prep.digest(core/name), expected)  # not authorized by this historical packet
            else:
                self.assertEqual(prep.digest(core/name), expected)
        manifest['continuous_q0_policy_change']['reference_locus_padding_bp'] = 1000000
        with self.assertRaisesRegex(ValueError, 'authorization'):
            prep.validate_continuity_change(self.bundle, manifest)
        manifest['continuous_q0_policy_change'] = dict(prep.CONTINUITY_CHANGE)
        path = self.bundle/'runtime/q0_collinear.py'
        path.write_text(path.read_text() + '\n# changed nested policy source\n')
        with self.assertRaisesRegex(ValueError, 'differs from reviewed'):
            prep.validate_continuity_change(self.bundle, manifest)

    def test_explicit_continuity_declaration_survives_preparation(self):
        from unittest.mock import patch
        self.bind_threshold_candidate()
        self.manifest['git_revision'] = prep.CONTINUITY_CHANGE['engine_revision']
        self.manifest['continuous_q0_policy_change'] = dict(prep.CONTINUITY_CHANGE)
        path = self.bundle/'runtime/q0_admission.py'
        before = prep.selector_policy_ast(path, 'AdmissionPolicy')
        path.write_text(path.read_text().replace('minimum_bp=100', 'minimum_bp=200'))
        self.manifest['positive_threshold_policy_changes']['q0_admission.py'] = prep.policy_change(
            before, prep.selector_policy_ast(path, 'AdmissionPolicy'))
        self.save_manifest()
        # Synthetic fixture pins exercise full preparation; the separate test
        # above checks every real 2064cb4c byte pin and rejects even rehashed drift.
        pins = {p.name: prep.digest(p) for p in (self.bundle/'runtime').glob('*.py')}
        with patch.object(prep, 'CONTINUITY_FILES', pins):
            report = prep.prepare(self.bundle)
        transition = json.loads((self.bundle/'transition.json').read_text())
        self.assertEqual(report['continuous_q0_policy_change'], prep.CONTINUITY_CHANGE)
        self.assertEqual(transition['continuous_q0_policy_change'], prep.CONTINUITY_CHANGE)
        self.assertEqual(self.snapshot(), self.before)

    def test_threshold_reuses_only_journal_bound_identical_legacy_support(self):
        self.bind_threshold_candidate()
        relative = '.prepare_lib/tools/workspace_layout.py'
        target = self.work/relative
        target.write_bytes((self.bundle/'support/workspace_layout.py').read_bytes())
        journal = json.loads(self.journal.read_text())
        journal['installed'].append({'relative':relative, 'sha256':prep.digest(target)})
        self.journal.write_text(json.dumps(journal))
        before = self.snapshot()
        report = prep.prepare(self.bundle)
        self.assertIn(relative, report['unchanged_runtime_files'])
        self.assertEqual(self.snapshot(), before)

    def test_threshold_rejects_changed_support_even_if_previous_bytes_are_owned(self):
        self.bind_threshold_candidate()
        relative = '.prepare_lib/tools/workspace_layout.py'
        target = self.work/relative
        target.write_text('# previously installed different support\n')
        journal = json.loads(self.journal.read_text())
        journal['installed'].append({'relative':relative, 'sha256':prep.digest(target)})
        self.journal.write_text(json.dumps(journal))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'existing workspace layout'):
            prep.prepare(self.bundle)
        self.assertEqual(self.snapshot(), before)

    def test_threshold_rejects_undeclared_or_changed_policy_delta(self):
        self.bind_threshold_candidate()
        self.manifest['positive_threshold_policy_changes']={}
        self.save_manifest()
        with self.assertRaisesRegex(ValueError,'changes a selector policy'):
            prep.prepare(self.bundle)
        self.assertFalse((self.bundle/prep.LAUNCHER).exists())

    def test_threshold_still_rejects_alignment_policy_change_and_existing_support(self):
        self.bind_threshold_candidate()
        p=self.bundle/'runtime/q0_preparation.py';before=p.read_text()
        p.write_text(before.replace("'version':5", "'version':6"));self.save_manifest()
        with self.assertRaisesRegex(ValueError,'changes a scientific policy'):
            prep.prepare(self.bundle)
        p.write_text(before);self.save_manifest()
        (self.work/'.prepare_lib/tools/workspace_layout.py').write_text('# unexpected existing support')
        with self.assertRaisesRegex(ValueError,'existing workspace layout'):
            prep.prepare(self.bundle)

    def test_threshold_missing_transitive_dependency_is_not_silently_omitted(self):
        self.bind_threshold_candidate()
        (self.bundle/'runtime/q0_threshold_questions.py').unlink();self.save_manifest()
        with self.assertRaises(FileNotFoundError):
            prep.prepare(self.bundle)
        self.assertEqual(self.snapshot(),self.before)

    def test_existing_unowned_new_module_is_never_assumed_to_be_a_valid_prior(self):
        p=self.work/'.prepare_lib/tools/lgz_core/q0_regional_execution.py';p.write_text('unrelated file')
        with self.assertRaisesRegex(ValueError,'unexpected existing'):prep.prepare(self.bundle)
        self.assertEqual(p.read_text(),'unrelated file');self.assertFalse((self.bundle/'transition.json').exists())

    def test_prior_source_or_declaration_drift_is_rejected(self):
        for relative in ('.prepare_lib/tools/lgz_core/common.py',prep.DECLARATION):
            p=self.work/relative;old=p.read_bytes();p.write_bytes(old+b'\n')
            with self.subTest(relative=relative),self.assertRaisesRegex(ValueError,'drifted'):prep.prepare(self.bundle)
            p.write_bytes(old)
        self.assertFalse((self.bundle/'transition.json').exists())

    def test_rehashed_candidate_scientific_policy_change_is_rejected(self):
        p=self.bundle/'runtime/q0_preparation.py';p.write_text(p.read_text().replace("'version':5","'version':6"))
        self.save_manifest()
        with self.assertRaisesRegex(ValueError,'scientific policy'):prep.prepare(self.bundle)
        self.assertEqual(self.snapshot(),self.before)

    def test_unbound_source_and_incomplete_packet_fail_before_output(self):
        p=self.bundle/'runtime/common.py';original=p.read_bytes();p.write_bytes(original+b'\n')
        with self.assertRaisesRegex(ValueError,'source changed'):prep.prepare(self.bundle)
        p.write_bytes(original)
        self.manifest['files']=[r for r in self.manifest['files'] if r['relative']!='stage_q0_science.py']
        (self.bundle/'candidate-source.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError,'closure'):prep.prepare(self.bundle)
        self.assertFalse((self.bundle/'transition.json').exists())

    def test_published_q0_and_unsuccessful_previous_installation_are_preserved(self):
        p=self.work/'metadata/grt_q0_evidence.json';p.write_text('completed output')
        with self.assertRaisesRegex(ValueError,'already published'):prep.prepare(self.bundle)
        self.assertEqual(p.read_text(),'completed output');p.unlink()
        journal=json.loads(self.journal.read_text());journal['status']='rolled_back';self.journal.write_text(json.dumps(journal))
        with self.assertRaisesRegex(ValueError,'successful journal'):prep.prepare(self.bundle)
        self.assertEqual(self.snapshot(),self.before)

    def test_new_source_cannot_link_to_or_stage_inside_the_work(self):
        p=self.bundle/'runtime/common.py';p.unlink();p.symlink_to(self.work/'.prepare_lib/tools/lgz_core/common.py')
        with self.assertRaisesRegex(ValueError,'linked'):prep.prepare(self.bundle)
        self.assertFalse((self.bundle/'transition.json').exists())


if __name__=='__main__':unittest.main()
