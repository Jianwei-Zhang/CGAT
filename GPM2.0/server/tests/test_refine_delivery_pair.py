"""Check the numbered Server's adjacent full/light jobs, not just the projector."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile

from refinement_bundle_fixture import FIXTURE
from workspace_layout import initialize_workspace, render_workspace_shell
from delivery_archive import delivery_path, delivery_staging_path, publish_delivery_staging
import lgz_app_package as package
from refinement_config import save_request
from run_all_runner import PlanUnit, Runner, WorkspaceLock


class RefineDeliveryPairTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / 'col0'
        self.channel = self.tmp / 'pair.json'
        self.layout = initialize_workspace(self.root)
        for name, contents in json.loads(FIXTURE.read_text())['files'].items():
            path = self.layout.path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
        self.layout.path('metadata/prepare_options.tsv').write_text('key\tvalue\nthreads\t1\narchive_format\tzip\n')
        # An optional final-Q index is present only in full; keep source FAIs in light.
        self.layout.path('grt/q/q4.fa.fai').write_text('chr1\t10\t6\t10\t11\n')
        self.run_id = 'current-run'
        self.lock = WorkspaceLock(self.root, self.run_id)
        self.lock.acquire()
        self.addCleanup(self.lock.release)

    def test_real_runner_templates_produce_exact_standalone_light_and_distinct_full(self):
        project = Path(__file__).resolve().parents[1]
        runtime = self.layout.path('.prepare_lib')
        shutil.copytree(project / 'tools', runtime / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(project / 'contracts', runtime / 'contracts')
        units = []
        for unit in ('package_full', 'package_light'):
            script = unit + '_zip.sh'
            target = self.layout.path(script)
            target.parent.mkdir(exist_ok=True, parents=True)
            target.write_text(render_workspace_shell((project / 'templates' / script).read_text(), self.layout, script))
            units.append(PlanUnit(unit, str(target.relative_to(self.root)), '.runtime/logs/run_all.log'))
        save_request(self.root, {}, self.run_id)
        runner = Runner(self.root, units, self.run_id, color='never')
        runner.contract_channel = self.tmp / 'private-run-handoff'
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(runner.run(), 0)
        self.assertIn("Light App payload derived from this run's full projection", self.layout.path('logs/run_all.log').read_text())
        for kind in ('full', 'light'):
            with self.subTest(kind=kind):
                separate = self.tmp / ('independent-' + kind)
                package.build_delivery(self.root, separate, kind == 'full')
                wanted = {str(p.relative_to(separate)): p.read_bytes() for p in separate.rglob('*') if p.is_file()}
                with zipfile.ZipFile(delivery_path(self.root, kind)) as arc:
                    got = {s.filename.partition('/')[2]: arc.read(s) for s in arc.infolist()
                           if not s.is_dir() and not s.filename.startswith(self.root.name + '/report/')}
                self.assertEqual(got.keys(), wanted.keys())
                for name in wanted:
                    self.assertEqual(got[name], wanted[name], name)
                self.assertEqual('grt/q/q4.fa.fai' in got, kind == 'full')
                self.assertTrue(any(k.startswith('data/') and k.endswith('.fai') for k in got))

    def test_changed_full_cannot_seed_light_and_standalone_does_not_trust_old_staging(self):
        env = {'GPM_REPORT_RUN_ID': self.run_id, 'GPM_APP_PROJECTION_PAIR': str(self.channel)}
        prepared = self.tmp / 'staged' / self.root.name
        with mock.patch.dict(os.environ, {**env, 'GPM_REPORT_UNIT_ID': 'package_full'}):
            package.build_delivery(self.root, prepared, True)
        publish_delivery_staging(self.root, 'full', prepared)
        full = delivery_staging_path(self.root, 'full')
        f = full / 'metadata/grt_final_path.json'
        st = f.stat()
        tmp = f.with_suffix('.new')
        tmp.write_bytes(f.read_bytes())
        os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
        os.replace(tmp, f)
        light = self.tmp / 'light'
        with mock.patch.dict(os.environ, {**env, 'GPM_REPORT_UNIT_ID': 'package_light'}):
            with self.assertRaisesRegex(ValueError, 'full App staging changed'):
                package.build_delivery(self.root, light, False)
            self.assertFalse(light.exists())
            # A fresh or standalone run does not trust that unrelated full tree.
            with mock.patch.dict(os.environ, {'GPM_REPORT_RUN_ID': 'different'}), mock.patch.object(
                    package, 'build', wraps=package.build) as independent:
                package.build_delivery(self.root, light, False)
                independent.assert_called_once()
        self.assertTrue((light / 'metadata/grt_app_manifest.json').is_file())
