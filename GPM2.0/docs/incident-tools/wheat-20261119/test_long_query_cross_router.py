import contextlib
import dataclasses
import io
import json
import os
import signal
import time
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from long_query_cross_router import Policy, Router, RoutingError, acceptable
TOOLS = Path(os.environ.get("CGAT_ROUTER_TEST_TOOLS", str(Path(__file__).resolve().parents[3] / "server/tools")))
SMALL = Policy(long_bases=60, minimum_target_bases=1, maximum_target_bases=2000,
               probe_window_bases=10, anchor_step=1, minimum_anchors=20)


class FakeRouter(Router):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []
        self.fail_exact = False
        self.reject_strong = False
        self.low_full_coverage = False
        self.mutate_source = False
        self.abort = False

    def execute(self, command, directory, timeout):
        records = self.catalog_lib.scan_query(command[-1]).records
        fraction = float(command[command.index("-f") + 1]) if "-f" in command else None
        probe = all(r.name.startswith("window_") for r in records)
        self.calls.append((tuple(r.name for r in records), fraction, probe, timeout))
        target_name, target_length = next(iter(self.target_lengths.items()))
        lines = []
        for r in records:
            start = 200 if self.reject_strong and fraction == .005 else 0
            length = r.length // 2 if self.low_full_coverage and fraction is not None and not probe else r.length
            lines.append(f"{r.name}\t{r.length}\t0\t{length}\t+\t{target_name}\t{target_length}\t{start}\t{start + length}\t{length}\t{length}\t60\ttp:A:P\tcg:Z:{length}M\n")
        Path(command[command.index("-o") + 1]).write_text("".join(lines))
        (directory / "stdout.log").write_text("")
        occ = 500 if fraction is None else (66 if fraction == .005 else 250)
        (directory / "stderr.log").write_text(
            f"[M::main::0] loaded/built the index for {len(self.target_lengths)} target sequence(s)\n"
            f"[M::mm_mapopt_update::0] mid_occ = {occ}\n"
            f"[M::worker_pipeline::1] mapped {len(records)} sequences\n")
        if self.mutate_source:
            Path(self.target.source).write_text(">target\n" + "C" * target_length + "\n")
        if self.abort:
            self.cancelled = True
        return 17 if self.fail_exact and fraction is None and not probe else 0


class RouterTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.target, self.query = self.root / "target.fa", self.root / "query.fa"
        self.target.write_text(">target\n" + "A" * 1000 + "\n")
        self.raw = b">short1 comment\r\n" + b"a" * 20 + b"\r\n>long original header\n" + b"A" * 80 + b"\n>short2\n" + b"C" * 30 + b"\n"
        self.query.write_bytes(self.raw)
        self.tool = self.root / "minimap2"; self.tool.write_text("test-only executor identity\n")
        self.output, self.receipt = self.root / "result.paf", self.root / "receipt.json"

    def router(self, **kwargs):
        return FakeRouter(self.target, self.query, self.tool, self.root / "cache", TOOLS,
                          threads=2, policy=SMALL, **kwargs)

    def execute(self, router):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return router.run(self.output, self.receipt)

    def test_routes_only_long_records_and_restores_original_order(self):
        router = self.router(); result = self.execute(router)
        final_calls = [c for c in router.calls if not c[2]]
        self.assertEqual([(c[0], c[1]) for c in final_calls], [(('long',), .005), (('short1', 'short2'), None)])
        self.assertTrue(all(c[3] is None for c in final_calls))
        self.assertEqual([line.split('\t')[0] for line in self.output.read_text().splitlines()], ['short1', 'long', 'short2'])
        self.assertEqual(self.query.read_bytes(), self.raw)
        self.assertTrue(result['whole_records_preserved'])
        self.assertEqual(result['query_count'], 3)
        copied = router.materialize(['short1', 'short2']).read_bytes()
        self.assertEqual(copied, self.raw.split(b'>long')[0] + b'>short2\n' + b'C' * 30 + b'\n')

    def test_quality_rejection_chooses_weaker_filter(self):
        router = self.router(); router.reject_strong = True
        result = self.execute(router)
        decision = next(d for d in result['decisions'] if d['query'] == 'long')
        self.assertEqual(decision['filter'], .001)
        self.assertEqual([c['passed'] for c in decision['cases']], [False, True])

    def test_low_full_coverage_falls_back_without_omitting_the_record(self):
        router = self.router(); router.low_full_coverage = True
        result = self.execute(router)
        decision = next(d for d in result['decisions'] if d['query'] == 'long')
        self.assertIsNone(decision['effective_filter'])
        self.assertEqual(decision['fallback_reason'], 'full_query_coverage_guard')
        lines = self.output.read_text().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(int(lines[1].split('\t')[3]), 80)
        self.assertEqual(router.calls[-1][0], ('short1', 'long', 'short2'))

    def test_failed_mapping_is_not_completed_and_resume_reuses_paid_groups(self):
        router = self.router(); router.fail_exact = True
        with self.assertRaises(RoutingError): self.execute(router)
        self.assertFalse(self.receipt.exists()); self.assertFalse(self.output.exists())
        resumed = self.router(); self.execute(resumed)
        self.assertEqual(resumed.calls, [(('short1', 'short2'), None, False, None)])
        self.assertTrue(list((self.root / 'cache').glob('mappings/*/attempt-*/stderr.log')))

    def test_completed_final_survives_intermediate_cache_removal(self):
        first = self.execute(self.router())
        shutil.rmtree(self.root / 'cache')
        resumed = self.router(); second = self.execute(resumed)
        self.assertEqual(first, second)
        self.assertEqual(resumed.calls, [])

    def test_corrupt_completed_group_does_not_get_silently_recomputed(self):
        router = self.router(); router.fail_exact = True
        with self.assertRaises(RoutingError): self.execute(router)
        for p in (self.root / 'cache').glob('mappings/*/complete.json'):
            row = json.loads(p.read_text())
            if row['identity']['phase'] == 'whole_records':
                (p.parent / row['paf']).write_text('damaged\n')
        with self.assertRaisesRegex(RoutingError, 'output changed'): self.execute(self.router())
        self.assertFalse(self.receipt.exists())

    def test_corrupt_final_output_is_refused(self):
        self.execute(self.router()); self.output.write_text('damaged\n')
        with self.assertRaisesRegex(RoutingError, 'final routing output changed'): self.execute(self.router())

    def test_changed_inputs_do_not_reuse_a_final_receipt(self):
        self.execute(self.router())
        self.query.write_bytes(self.raw.replace(b'a', b'g'))
        with self.assertRaisesRegex(RoutingError, 'another request'): self.execute(self.router())

    def test_changed_preset_cannot_reuse_a_final_receipt(self):
        result = self.execute(self.router())
        self.assertEqual(result['preset'], 'asm10')
        with self.assertRaisesRegex(RoutingError, 'another request'):
            self.execute(self.router(preset='asm20'))

    def test_changed_dependency_before_publication_is_refused(self):
        router = self.router()
        dependency = self.root / 'dependency.py'
        dependency.write_text('initial source')
        router.dependencies['fixture'] = {
            'path': dependency, 'sha256': router.contract.sha256_file(dependency)}
        original = router.execute
        def mutate_after_mapping(command, directory, timeout):
            code = original(command, directory, timeout)
            dependency.write_text('changed source')
            return code
        with patch.object(router, 'execute', side_effect=mutate_after_mapping):
            with self.assertRaisesRegex(RoutingError, 'implementation changed'):
                self.execute(router)
        self.assertFalse(self.receipt.exists())
        self.assertFalse(self.output.exists())

    def test_multipart_calibration_falls_back_to_full_ordinary_mapping(self):
        self.target.write_text('>target\n' + 'A' * 1000 + '\n>second\nAAAA\n')
        router = self.router()
        original = router.execute
        def multipart(command, directory, timeout):
            code = original(command, directory, timeout)
            records = router.catalog_lib.scan_query(command[-1]).records
            (directory / 'stderr.log').write_text(
                (f'loaded/built the index for 1 target sequence(s)\n'
                 f'mid_occ = 500\nmapped {len(records)} sequences\n') * 2)
            return code
        with patch.object(router, 'execute', side_effect=multipart):
            result = self.execute(router)
        self.assertEqual(router.calls[-1], (('short1', 'long', 'short2'), None, False, None))
        self.assertEqual(len(router.calls), 2)
        self.assertEqual(result['group_evidence'][0]['index_parts'], 2)
        self.assertTrue(all(d['filter'] is None for d in result['decisions']))

    def test_source_mutation_or_cancellation_never_publishes_final(self):
        for kind in ('mutate_source', 'abort'):
            with self.subTest(kind=kind):
                router = self.router(); setattr(router, kind, True)
                with self.assertRaises(Exception): self.execute(router)
                self.assertFalse(self.receipt.exists()); self.assertFalse(self.output.exists())
                self.target.write_text('>target\n' + 'A' * 1000 + '\n')

    def test_output_cannot_alias_input(self):
        router = self.router()
        with self.assertRaisesRegex(RoutingError, 'protected input'):
            router.run(self.query, self.receipt)
        self.assertEqual(self.query.read_bytes(), self.raw)

    def test_short_only_input_is_ordinary_without_calibration(self):
        self.query.write_text('>s\n' + 'A' * 20 + '\n')
        router = self.router(); self.execute(router)
        self.assertEqual(router.calls, [(('s',), None, False, None)])

    def test_probe_cannot_be_misrepresented_as_whole_query_evidence(self):
        router = self.router()
        probe, lengths = router.probes(router.records['long'])
        with self.assertRaisesRegex(RoutingError, 'complete original records'):
            router.mapping(probe, lengths, .005, phase='whole_records')
        self.assertEqual(router.calls, [])

    def test_changed_scientific_command_proof_is_refused(self):
        router = self.router(); router.fail_exact = True
        with self.assertRaises(RoutingError): self.execute(router)
        for path in (self.root / 'cache').glob('mappings/*/complete.json'):
            row = json.loads(path.read_text())
            if row['identity']['phase'] == 'whole_records':
                row['command'][row['command'].index('-f') + 1] = '0.001'
                path.write_text(json.dumps(row))
        with self.assertRaisesRegex(RoutingError, 'scientific options changed'):
            self.execute(self.router())

    def test_existing_output_is_archived_only_after_new_result_is_valid(self):
        self.output.write_bytes(b'old result kept as evidence\n')
        self.execute(self.router())
        backups = list(self.root.glob('result.paf.before-route-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'old result kept as evidence\n')

    def test_group_cache_is_reusable_after_resource_change(self):
        router = self.router(); router.fail_exact = True
        with self.assertRaises(RoutingError): self.execute(router)
        resumed = self.router(); resumed.threads = 1
        self.execute(resumed)
        self.assertEqual(resumed.calls, [(('short1', 'short2'), None, False, None)])

    def test_outside_target_domain_keeps_ordinary_path(self):
        router = self.router()
        router.policy = dataclasses.replace(SMALL, maximum_target_bases=500)
        self.execute(router)
        self.assertEqual(router.calls, [(('short1', 'long', 'short2'), None, False, None)])

    def test_output_cannot_overwrite_private_cache_inputs(self):
        router = self.router()
        with self.assertRaises(RoutingError):
            router.run(self.root / 'cache' / 'input.fa', self.receipt)

    def test_calibration_gate_rejects_empty_or_changed_geometry(self):
        b = {'primary_query_covered_bases': 100}
        c = {'baseline_anchor_count': 100, 'baseline_anchors_supported_within_100bp': 100,
             'candidate_anchor_count': 100, 'extra_candidate_anchors': 0,
             'candidate_anchors_with_extra_positions_beyond_100bp': 0}
        self.assertTrue(acceptable(b, b, c, SMALL))
        self.assertFalse(acceptable(b, b, {**c, 'baseline_anchor_count': 0}, SMALL))
        self.assertFalse(acceptable(b, b, {**c, 'baseline_anchors_supported_within_100bp': 50}, SMALL))
        self.assertFalse(acceptable(b, {'primary_query_covered_bases': 50}, c, SMALL))


@unittest.skipUnless(shutil.which('minimap2'), 'native minimap2 required for scoped equivalence fixture')
class NativeRouterTests(unittest.TestCase):
    def test_native_ordinary_records_stay_byte_identical_after_routing(self):
        self.native_case(False)

    def test_native_repeated_target_ties_stay_identical_after_record_regrouping(self):
        self.native_case(True)

    def native_case(self, duplicated):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); rng = random.Random(143)
            target = ''.join(rng.choices('ACGT', k=180_000))
            (root / 'target.fa').write_text('>target\n' + target + '\n' + ('>duplicate\n' + target + '\n' if duplicated else ''))
            records = [('short1', target[1000:9000]), ('long', target[30_000:70_000]), ('short2', target[100_000:110_000])]
            (root / 'query.fa').write_text(''.join('>' + name + ' original-header\n' + seq + '\n' for name, seq in records))
            tool = shutil.which('minimap2')
            command = [tool, '-c', '-x', 'asm10', '-t', '2', '-o', str(root / 'baseline.paf'), str(root / 'target.fa'), str(root / 'query.fa')]
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            policy = Policy(long_bases=30_000, minimum_target_bases=1, probe_window_bases=2000, minimum_anchors=1)
            router = Router(root / 'target.fa', root / 'query.fa', tool, root / 'cache', TOOLS, threads=2, policy=policy)
            def decision(record):
                return {'query': record.name, 'length': record.length, 'filter': .005, 'reason': 'fixture_only_forced_route'}
            with patch.object(router, 'calibrate', side_effect=decision), contextlib.redirect_stdout(io.StringIO()):
                router.run(root / 'routed.paf', root / 'receipt.json')
            def ordinary(path):
                return [line for line in path.read_bytes().splitlines(keepends=True) if line.split(b'\t', 1)[0] != b'long']
            self.assertEqual(ordinary(root / 'baseline.paf'), ordinary(root / 'routed.paf'))
            self.assertEqual(list(dict.fromkeys(line.split('\t')[0] for line in (root / 'routed.paf').read_text().splitlines())), ['short1', 'long', 'short2'])


class CancellationTests(unittest.TestCase):
    def test_cancellation_leaves_no_mapper_or_complete_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('target', 'query'):
                (root / (name + '.fa')).write_text('>q\n' + 'A' * 100 + '\n')
            native = root / 'minimap2'
            native.write_text('#!' + sys.executable + '\nimport os,time\nfrom pathlib import Path\n'
                              'Path(__file__).with_suffix(".pid").write_text(str(os.getpid()))\ntime.sleep(60)\n')
            native.chmod(0o755)
            command = [sys.executable, '-B', str(Path(__file__).with_name('long_query_cross_router.py')),
                       '--target', str(root / 'target.fa'), '--query', str(root / 'query.fa'),
                       '--minimap2', str(native), '--runtime-tools', str(TOOLS), '--threads', '1',
                       '--output', str(root / 'out.paf'), '--receipt', str(root / 'receipt.json'), '--cache', str(root / 'cache')]
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                deadline = time.monotonic() + 30
                while not native.with_suffix('.pid').exists() and proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(native.with_suffix('.pid').exists(), 'test mapper did not start')
                pid = int(native.with_suffix('.pid').read_text())
                os.killpg(proc.pid, signal.SIGTERM)
                proc.communicate(timeout=15)
                self.assertNotEqual(proc.returncode, 0)
                self.assertFalse((root / 'receipt.json').exists())
                self.assertFalse(list((root / 'cache').glob('mappings/*/complete.json')))
                self.assertFalse(Path(f'/proc/{pid}').exists(), 'mapper survived its cancelled outer task')
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.communicate(timeout=10)


if __name__ == '__main__': unittest.main()
