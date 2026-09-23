from __future__ import annotations

import gzip
import json
from pathlib import Path
import shlex
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
TOOLS = PROJECT / 'server/tools'
sys.path.insert(0, str(TOOLS))
from delivery_archive import archive_options, create_archive, delivery_path, validate_tar_archive
from server_report import embed_report_in_delivery_archives
import test_run_all_runner as runner_fixture


class DeliveryArchiveTests(unittest.TestCase):
    def test_legacy_format_and_allocated_thread_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'gpm_server'
            (root / 'metadata').mkdir(parents=True)
            self.assertEqual(archive_options(root), ('zip', 1))
            options = root / 'metadata/prepare_options.tsv'
            for requested, available, expected in [(32, 32, 32), (32, 4, 4), (4, 32, 4)]:
                options.write_text(f'key\tvalue\narchive_format\ttar.gz\nthreads\t{requested}\n')
                with patch('delivery_archive.os.sched_getaffinity', return_value=set(range(available)), create=True):
                    self.assertEqual(archive_options(root), ('tar.gz', expected))
            self.assertEqual(delivery_path(root, 'light').name, 'gpm_server.light.tar.gz')

    def test_missing_compressor_and_corrupt_gzip_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / 'gpm_server'
            staging.mkdir()
            (staging / 'payload').write_bytes(b'genome' * 10000)
            output = root / 'delivery.tar.gz'
            with patch('delivery_archive.shutil.which', return_value=None):
                with self.assertRaisesRegex(RuntimeError, 'server/install.sh'):
                    create_archive(staging, output, 'tar.gz', 2)
            create_archive(staging, output, 'tar.gz', 2)
            validate_tar_archive(output, {'gpm_server/payload'})
            data = bytearray(output.read_bytes())
            data[-8] ^= 1  # gzip CRC, after the tar EOF
            output.write_bytes(data)
            with self.assertRaises(gzip.BadGzipFile):
                validate_tar_archive(output, {'gpm_server/payload'})

    def test_tar_pipeline_embeds_final_report_and_rebuilds_without_duplicates(self):
        helper = runner_fixture.RunAllRunnerTests()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = helper.make_workspace(root, [('package_full', 'true'), ('package_light', 'true')])
            shutil.copytree(PROJECT / 'tests/fixtures/grt_contract_v2/valid/gpm_server', server, dirs_exist_ok=True)
            shutil.copytree(TOOLS, server / '.prepare_lib/tools', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(PROJECT / 'server/contracts', server / '.prepare_lib/contracts')
            (server / 'metadata/prepare_options.tsv').write_text('key\tvalue\narchive_format\ttar.gz\nthreads\t4\n')
            for unit, name in [('package_full', 'package_full_zip.sh'), ('package_light', 'package_light_zip.sh')]:
                shutil.copyfile(PROJECT / 'server/templates' / name, server / name)
                (server / 'commands' / (unit + '.sh')).write_text('#!/bin/bash\nexec bash ' + shlex.quote(str(server / name)) + '\n')
            for attempt in range(2):
                result = helper.run_runner(server)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('gpm_server.light.tar.gz', result.stdout)
                for kind in ['full', 'light']:
                    path = delivery_path(server, kind)
                    required = {'gpm_server/report/' + name for name in ['manifest.json', 'report.html', 'render_report.py']}
                    validate_tar_archive(path, required)
                    with tarfile.open(path) as archive:
                        self.assertEqual(archive.getnames().count('gpm_server/report/manifest.json'), 1)
                        manifest = json.load(archive.extractfile('gpm_server/report/manifest.json'))
                        self.assertEqual(manifest['status'], 'success')
                        self.assertEqual(any(name.endswith('.fa') for name in archive.getnames()), kind == 'full')
                        self.assertFalse(any('.fastq' in name for name in archive.getnames()))
            # An embedding error must leave both prior deliveries intact.
            paths = [delivery_path(server, kind) for kind in ['full', 'light']]
            original = [path.read_bytes() for path in paths]
            with self.assertRaisesRegex(ValueError, 'already contains a report'):
                embed_report_in_delivery_archives(server, paths)
            self.assertEqual([path.read_bytes() for path in paths], original)
            self.assertFalse(list(root.glob('.*.tmp')))
