"""Candidate discovery and required-evidence publication, not path quality claims."""
import contextlib
import hashlib
import io
import json
import os
import random
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from server.tests import test_grt_prepare_inputs as fixture
from server.tests.q0_test_support import seed_q0_evidence
from server.tools.lgz_core.common import read_fasta, write_fasta
from server.tools.lgz_core.q0_sources import SourceKey, Q0EvidenceError
from server.tools.lgz_core.q0_catalog import build_catalog, supplemental_groups
from server.tools import run_orchestration
from server.tools.lgz_core.q0_preparation import MANIFEST, prepare_evidence, load_verified_evidence, artifact_path, identity


class Q0ArtifactIdentityTests(unittest.TestCase):
    def test_receipt_label_and_byte_identity_with_one_signature_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "parts").mkdir()
            content = b"exact receipt bytes\r\n"
            (root / "parts" / "result.paf").write_bytes(content)
            label = "parts//result.paf"
            expected = {"path": label, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            with (mock.patch.object(run_orchestration, "file_signature", wraps=run_orchestration.file_signature) as stat,
                  mock.patch.object(run_orchestration, "_sha256_read", wraps=run_orchestration._sha256_read) as read):
                self.assertEqual(identity(root, label), expected)
                self.assertEqual(identity(root, label), expected)
            self.assertEqual(stat.call_count, 4)
            self.assertEqual(read.call_count, 1)

    def test_outside_symlink_rejected_before_reading_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "workspace"
            root.mkdir()
            outside = parent / "outside"
            outside.write_bytes(b"not a workspace artifact")
            alias = root / "alias"
            try:
                alias.symlink_to(outside)
            except OSError:
                self.skipTest("symlink support required")
            with mock.patch.object(run_orchestration, "_sha256_read", side_effect=AssertionError("outside file read")):
                with self.assertRaisesRegex(Q0EvidenceError, "escapes workspace"):
                    identity(root, "alias")

    def test_warm_artifact_identity_rejects_alias_retargeted_after_initial_stat(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old, new, alias = (root / name for name in ("old", "new", "alias"))
            old.write_bytes(b"before")
            new.write_bytes(b"after ")
            try:
                alias.symlink_to(old)
            except OSError:
                self.skipTest("symlink support required")
            self.assertEqual(identity(root, "alias")["path"], "alias")
            signature = run_orchestration.file_signature

            def retarget(path):
                original = signature(path)
                if alias.readlink() == old:
                    alias.unlink()
                    alias.symlink_to(new)
                return original

            with mock.patch.object(run_orchestration, "file_signature", side_effect=retarget):
                with self.assertRaisesRegex(Q0EvidenceError, "changed during hash reuse"):
                    identity(root, "alias")
            self.assertEqual(identity(root, "alias")["sha256"], hashlib.sha256(b"after ").hexdigest())


class CandidateDiscoveryTests(unittest.TestCase):
    def test_split_sources_keep_original_links_and_all_chr_alternatives(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paf = root / "runs/ds_vs_ref/result.paf"
            paf.parent.mkdir(parents=True)
            paf.write_text("c\t300\t0\t100\t+\tChrA\t1000\t50\t150\t100\t100\t60\tcg:Z:100M\n"
                           "c\t300\t200\t300\t-\tChrB\t1000\t20\t120\t100\t100\t30\tcg:Z:100M\n")
            sources = {SourceKey("ds", "c"): "A" * 100 + "N" * 100 + "G" * 100}
            catalog = build_catalog(root, sources, {"ChrA": 1000, "ChrB": 1000}, [])
            self.assertEqual(len(catalog.payload["segments"]), 2)
            self.assertEqual(len(catalog.payload["original_connections"]), 1)
            self.assertEqual({row["chromosome"] for row in catalog.payload["candidates"]}, {"ChrA", "ChrB"})
            by_chr = {row["chromosome"]: row for row in catalog.payload["candidates"]}
            self.assertEqual(by_chr["ChrB"]["query_intervals"], [[200, 300]])
            self.assertEqual(by_chr["ChrB"]["orientation"], "-")
            self.assertEqual(by_chr["ChrB"]["origin_group"], "expanded")
            self.assertTrue(all(not value["artifact"].startswith(str(root)) for value in catalog.payload["evidence"].values()))

    def test_internal_gap_is_not_counted_as_reference_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paf = root / "runs/ds_vs_ref/result.paf"
            paf.parent.mkdir(parents=True)
            paf.write_text("c\t120\t0\t120\t+\tChrA\t1000\t0\t220\t120\t220\t255\tcg:Z:60M100D60M\n")
            catalog = build_catalog(root, {SourceKey("ds", "c"): "A" * 120}, {"ChrA": 1000}, [])
            row = catalog.payload["candidates"][0]
            self.assertEqual(row["reference_intervals"], [[0, 60], [160, 220]])
            self.assertIsNone(row["maximum_available_mapq"])

    def test_reference_single_part_shortcut_matches_full_clipping_on_both_strands(self):
        from server.tools.lgz_core import q0_catalog as catalog_module
        from server.tools.lgz_core.q0_reference_index import ReferenceIndex
        from server.tools.lgz_core.q0_sources import Interval

        def full_clipping(hit, parts, ends):
            for block in hit.aligned_blocks():
                for part in parts:
                    overlap = part.interval.intersection(block.query)
                    if overlap is None:
                        continue
                    a = (overlap.start - block.query.start if hit.strand == "+"
                         else block.query.end - overlap.end)
                    start = block.target.start + a
                    yield part, overlap, Interval(start, start + overlap.length), block.operation

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paf = root / "runs/ds_vs_ref/result.paf"
            paf.parent.mkdir(parents=True)
            lines = []
            for start in (54, 120, 200):  # hits entirely inside and spanning split parts
                for strand in ("+", "-"):
                    for mapq in (6, 44, 255):
                        lines.append(f"c\t360\t{start}\t{start+101}\t{strand}\tChrA\t1000\t20\t120"
                                     f"\t97\t103\t{mapq}\tcg:Z:35M3I15M2D45=1X2M\n")
            for strand in ("+", "-"):
                lines.append(f"c\t360\t55\t305\t{strand}\tChrA\t1000\t20\t270\t250\t250\t6\tcg:Z:250M\n")
            lines.append("c\t360\t235\t265\t+\tChrA\t1000\t10\t40\t0\t60\t60\tcg:Z:30I30D\n")
            paf.write_text("".join(lines))
            sources = {SourceKey("ds", "c"): "A" * 80 + "N" * 100 + "G" * 180}
            refs = {"ChrA": 1000}
            db = root / "routing.sqlite"
            with mock.patch.object(catalog_module, "_reference_blocks", side_effect=full_clipping):
                original = build_catalog(root, sources, refs, [],
                        regional_factory=lambda parts, lengths: ReferenceIndex.create(db, root, parts, lengths))
            fast = build_catalog(root, sources, refs, [],
                        regional_factory=lambda parts, lengths: ReferenceIndex.open(db, root, parts, lengths))
            self.assertEqual(fast.payload, original.payload)
            self.assertEqual(fast.reference_routable_parts, original.reference_routable_parts)
            self.assertEqual(fast.reference_routable_footprints, original.reference_routable_footprints)
            self.assertEqual(fast.regional_index_report, original.regional_index_report)
            self.assertEqual(len(fast.payload["evidence"]), 20)  # the gap-only hit is not evidence
            self.assertTrue(all(row["maximum_available_mapq"] == 44 for row in fast.payload["candidates"]))

    def test_candidate_catalog_is_independent_of_dataset_input_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = {SourceKey("b", "same"): "A" * 10, SourceKey("a", "same"): "A" * 10}
            for key in sources:
                path = root / f"runs/{key.dataset}_vs_ref/result.paf"
                path.parent.mkdir(parents=True)
                path.write_text("same\t10\t0\t10\t+\tChr\t20\t0\t10\t10\t10\t60\tcg:Z:10M\n")
            first = build_catalog(root, sources, {"Chr": 20}, []).finish()
            second = build_catalog(root, dict(reversed(list(sources.items()))), {"Chr": 20}, []).finish()
            self.assertEqual(first, second)
            self.assertNotEqual(first["segments"][0]["segment_id"], first["segments"][1]["segment_id"])

    def test_main_unsplit_pairs_do_not_get_recomputed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "runs/ds_vs_ref/result.paf"
            path.parent.mkdir(parents=True)
            path.write_text("a\t10\t0\t10\t+\tChr\t20\t0\t10\t10\t10\t60\tcg:Z:10M\n"
                            "b\t10\t0\t10\t+\tChr\t20\t5\t15\t10\t10\t60\tcg:Z:10M\n")
            sources = {SourceKey("ds", name): "A" * 10 for name in ("a", "b")}
            assignments = [{"dataset_name": "ds", "seq_name": name, "assigned_chr_name": "Chr"} for name in ("a", "b")]
            catalog = build_catalog(root, sources, {"Chr": 20}, assignments)
            known_pairs = {tuple(sorted(sources))}
            self.assertEqual(supplemental_groups(catalog, assignments, known_pairs), [])
            # The high-threshold base run can succeed without finding a real
            # short overlap. Such a missing neighbor relation gets a new task.
            self.assertEqual(len(supplemental_groups(catalog, assignments, set())), 1)
            expanded = supplemental_groups(catalog, assignments[:1], known_pairs)
            self.assertEqual(len(expanded), 1)
            self.assertEqual(len(expanded[0]["query_ids"]), 1)
            self.assertEqual(len(expanded[0]["target_ids"]), 2)

    def test_observed_partial_pair_is_not_remapped_as_a_missing_neighbor(self):
        from server.tools.lgz_core.q0_catalog import add_pairwise_candidates
        from server.tools.lgz_core.q0_alignments import parse_paf_line
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "runs/ds_vs_ref/result.paf"
            path.parent.mkdir(parents=True)
            path.write_text("a\t100\t0\t100\t+\tChr\t200\t0\t100\t100\t100\t60\tcg:Z:100M\n"
                            "b\t100\t0\t100\t+\tChr\t200\t50\t150\t100\t100\t60\tcg:Z:100M\n")
            sources = {SourceKey("ds", name): "A" * 100 for name in ("a", "b")}
            assignments = [{"dataset_name": "ds", "seq_name": name, "assigned_chr_name": "Chr"}
                           for name in ("a", "b")]
            catalog = build_catalog(root, sources, {"Chr": 200}, assignments)
            ids = {p.source.contig: p.segment_id for p in catalog.parts.values()}
            known = set()
            self.assertTrue(supplemental_groups(catalog, assignments, known))
            def hit(cigar, matches, span):
                return parse_paf_line(f"{ids['a']}\t100\t0\t100\t+\t{ids['b']}\t100\t0\t100"
                                      f"\t{matches}\t{span}\t60\tcg:Z:{cigar}", artifact="supplement.paf", line_number=1)
            # A gap-only record does not prove an observed paired-base relation.
            add_pairwise_candidates(catalog, [hit("100I100D", 0, 200)], {ids["a"]}, {ids["b"]},
                                    include_placed=True, known_pairs=known)
            self.assertEqual(known, set())
            add_pairwise_candidates(catalog, [hit("100M", 100, 100)], {ids["a"]}, {ids["b"]},
                                    include_placed=True, known_pairs=known)
            self.assertEqual(known, {tuple(sorted(sources))})
            self.assertEqual(supplemental_groups(catalog, assignments, known), [])
            # Explicit out-of-group work is not waived by one known source pair.
            self.assertTrue(supplemental_groups(catalog, assignments[:1], known))

    def test_split_same_record_relationships_get_explicit_supplements(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "runs/ds_vs_ref/result.paf"
            path.parent.mkdir(parents=True)
            path.write_text("c\t300\t0\t300\t+\tChr\t1000\t0\t300\t200\t300\t60\tcg:Z:300M\n")
            assignments = [{"dataset_name": "ds", "seq_name": "c", "assigned_chr_name": "Chr"}]
            catalog = build_catalog(root, {SourceKey("ds", "c"): "A" * 100 + "N" * 100 + "G" * 100}, {"Chr": 1000}, assignments)
            tasks = supplemental_groups(catalog, assignments)
            self.assertEqual(len(tasks), 1)
            self.assertEqual(len(tasks[0]["query_ids"]), 2)
            self.assertEqual(len(tasks[0]["target_ids"]), 2)

    def test_invalid_policy_is_not_recast_as_invalid_sources(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(Q0EvidenceError):
            build_catalog(Path(directory), {}, {}, [], min_gap=0)


class EvidencePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.helper = fixture.GrtPrepareInputsTests()
        self.server = self.helper.make_server(self.root)
        seed_q0_evidence(self.server)
        self.environment = mock.patch.dict(os.environ, {"PATH": str(self.root / "q0-fixture-bin") + os.pathsep + os.environ.get("PATH", "")})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.minimap = self.root / "q0-fixture-bin/minimap2"

    def seed_assigned_support(self):
        import csv
        assignment = self.server / "metadata/chr_assignments.tsv"
        with assignment.open(newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            fields, rows = reader.fieldnames, list(reader)
        rows.append({**rows[0], "dataset_name": "support", "seq_name": "s_assigned",
                     "seq_length_bp": "1500", "assigned_chr_name": "Chr01",
                     "support_bp": "1500", "support_percent": "100.000", "anchor_start": "3001"})
        with assignment.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        seed_q0_evidence(self.server)

    def test_large_route_reaches_real_regional_receipts_and_ready_manifest(self):
        from server.tools.lgz_core import q0_preparation as prep
        mapper, _ = self.mapper()  # different identity from the seeded native mapper
        with mock.patch.object(prep, "regional_enabled", return_value=True), \
             mock.patch.object(prep, "prepare_partial", wraps=prep.prepare_partial) as regional:
            manifest = self.run_prepare(mapper)
        regional.assert_called_once()
        self.assertEqual(load_verified_evidence(self.server), manifest)
        catalog = self.catalog()
        self.assertIn("regional_partial_discovery", catalog)
        self.assertTrue(any(t["kind"] == "regional_discovery" for t in catalog["supplementary_alignments"]))
        self.assertTrue(list((self.server/"grt/evidence/q0_prepare/indexes").glob("*/success.json")))

    def test_large_route_prefers_completed_native_partial_result(self):
        from server.tools.lgz_core import q0_preparation as prep
        (self.server/MANIFEST).unlink()  # only the disposable synthetic ready manifest
        with mock.patch.object(prep, "regional_enabled", return_value=True), \
             mock.patch.object(prep, "prepare_partial", side_effect=AssertionError("must reuse completed native mapping")):
            manifest = self.run_prepare()
        self.assertEqual(load_verified_evidence(self.server), manifest)
        self.assertNotIn("regional_partial_discovery", self.catalog())

    def test_partition_parsing_is_reused_across_roles_but_not_invocations(self):
        self.seed_assigned_support()
        from collections import Counter
        from server.tools.lgz_core import q0_preparation
        expected = set()
        occurrences = 0
        for descriptor in (self.server / "runs").glob("chr_*/q0_alignment_inputs.json"):
            for row in json.loads(descriptor.read_text())["alignments"]:
                for field in ("query_fasta", "target_fasta"):
                    expected.add((self.server / row[field]).resolve())
                    occurrences += 1
        self.assertGreater(occurrences, len(expected))
        with mock.patch.object(q0_preparation, "read_fasta", wraps=read_fasta) as reads:
            first = q0_preparation._initial_inputs(self.server)
            counts = Counter(Path(call.args[0]).resolve() for call in reads.call_args_list)
            self.assertTrue(all(counts[path] == 1 for path in expected))
            second = q0_preparation._initial_inputs(self.server)
            counts = Counter(Path(call.args[0]).resolve() for call in reads.call_args_list)
            self.assertTrue(all(counts[path] == 2 for path in expected))
        self.assertEqual(first, second)
        self.assertTrue({path.relative_to(self.server).as_posix() for path in expected} <= set(first[4]))

    def test_same_size_partition_change_with_restored_mtime_is_not_reused(self):
        from server.tools.lgz_core import q0_preparation
        target = (self.server / "runs/chr_Chr01/datasets/primary.fa").resolve()
        original_hash = q0_preparation._partition_sha256
        calls = 0
        def digest(path):
            nonlocal calls
            if path == target:
                calls += 1
                if calls == 3:  # first validation has completed; the next role must recheck bytes
                    stat = target.stat()
                    before = target.read_text()
                    after = before.replace("\nA", "\nT", 1)
                    self.assertNotEqual(before, after)
                    self.assertEqual(len(before), len(after))
                    target.write_text(after)
                    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            return original_hash(path)
        with mock.patch.object(q0_preparation, "_partition_sha256", side_effect=digest), \
             mock.patch.object(q0_preparation, "read_fasta", wraps=read_fasta) as reads:
            with self.assertRaisesRegex(Q0EvidenceError, "differs from original sources"):
                q0_preparation._initial_inputs(self.server)
        self.assertEqual(sum(Path(call.args[0]).resolve() == target for call in reads.call_args_list), 2)

    def test_partition_change_during_parsing_cannot_populate_validation_cache(self):
        from server.tools.lgz_core import q0_preparation
        target = (self.server / "runs/chr_Chr01/datasets/primary.fa").resolve()
        def changing_read(path):
            yield from read_fasta(path)
            if Path(path).resolve() == target:
                target.write_text(target.read_text().replace("\nA", "\nT", 1))
        with mock.patch.object(q0_preparation, "read_fasta", side_effect=changing_read):
            with self.assertRaisesRegex(Q0EvidenceError, "changed during validation"):
                q0_preparation._initial_inputs(self.server)

    def test_byte_identical_partition_replacement_can_reuse_validation(self):
        from server.tools.lgz_core import q0_preparation
        target = (self.server / "runs/chr_Chr01/datasets/primary.fa").resolve()
        original_hash = q0_preparation._partition_sha256
        calls = 0
        def digest(path):
            nonlocal calls
            if path == target:
                calls += 1
                if calls == 3:
                    replacement = target.with_suffix(".replacement.fa")
                    replacement.write_bytes(target.read_bytes())
                    os.replace(replacement, target)
            return original_hash(path)
        with mock.patch.object(q0_preparation, "_partition_sha256", side_effect=digest), \
             mock.patch.object(q0_preparation, "read_fasta", wraps=read_fasta) as reads:
            q0_preparation._initial_inputs(self.server)
        self.assertGreaterEqual(calls, 3)
        self.assertEqual(sum(Path(call.args[0]).resolve() == target for call in reads.call_args_list), 1)

    def test_partition_validation_cache_does_not_cross_dataset_roles(self):
        self.seed_assigned_support()
        from server.tools.lgz_core import q0_preparation
        from server.tools.run_outer_checkpoints import OuterCheckpointManager
        descriptor = self.server / "runs/chr_Chr01/q0_alignment_inputs.json"
        value = json.loads(descriptor.read_text())
        cross = next(row for row in value["alignments"] if row["kind"] == "cross")
        cross["query_fasta"] = cross["target_fasta"]
        descriptor.write_text(json.dumps(value))
        manager = OuterCheckpointManager(self.server)
        prepared = manager.prepare("q0_chr:Chr01", "runs/chr_Chr01/q0_command.sh")
        manager.commit(prepared)
        with self.assertRaisesRegex(Q0EvidenceError, "differs from original sources"):
            q0_preparation._initial_inputs(self.server)

    def catalog(self):
        manifest = load_verified_evidence(self.server)
        return json.loads((self.server / manifest["catalog"]).read_text())

    def run_prepare(self, minimap=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return prepare_evidence(self.server, minimap2=str(minimap or self.minimap))

    def mapper(self, pairs=(), *, failure=False, malformed=False, mutate=None):
        script = self.root / "supplement_mapper.py"
        log = self.root / "supplement_calls.log"
        script.write_text(f"#!{sys.executable}\n" + """import sys
from pathlib import Path
if '--version' in sys.argv:
    print('q0-test-supplement-mapper')
    raise SystemExit(0)
def fasta(path):
    result = {}; name = None
    for line in Path(path).read_text().splitlines():
        if line.startswith('>'): name = line[1:]; result[name] = ''
        else: result[name] += line
    return result
""" + f"with Path({str(log)!r}).open('a') as out: out.write('run\\n')\n"
            + ("raise SystemExit(19)\n" if failure else "")
            + f"queries, targets = fasta(sys.argv[-1]), fasta(sys.argv[-2])\npairs = {list(pairs)!r}\n"
            + "rows = []\nfor q, t in pairs:\n    if q in queries and t in targets:\n        n = min(len(queries[q]),len(targets[t]))\n        rows.append(f'{q}\t{len(queries[q])}\t0\t{n}\t+\t{t}\t{len(targets[t])}\t0\t{n}\t{n}\t{n}\t60\tcg:Z:{n}M')\n"
            + ("rows = ['malformed']\n" if malformed else "")
            + "result = chr(10).join(rows) + (chr(10) if rows else '')\n"
            + "if '-o' in sys.argv: Path(sys.argv[sys.argv.index('-o')+1]).write_text(result)\n"
            + "else: sys.stdout.write(result)\n"
            + (f"with Path({str(mutate)!r}).open('a') as out: out.write(chr(10))\n" if mutate else ""))
        script.chmod(0o755)
        return script, log

    def test_success_manifest_and_empty_results_are_verifiable(self):
        manifest = load_verified_evidence(self.server)
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(self.run_prepare(), manifest)
        self.assertTrue(self.catalog()["unplaced_segment_ids"])
        self.assertTrue(any(row["origin_group"] == "expanded" for row in self.catalog()["candidates"]))

    def test_discovery_reaches_new_anchors_without_inventing_reference_hits(self):
        parts = {row["source"]["contig"]: row["segment_id"] for row in self.catalog()["segments"]}
        mapper, log = self.mapper([(parts["s_unplaced"], parts["p_cover"]),
                                   (parts["s_tel_short"], parts["s_unplaced"])])
        manifest = self.run_prepare(mapper)
        catalog = self.catalog()
        self.assertEqual(catalog["unplaced_segment_ids"], [])
        self.assertEqual(len(catalog["discovery_rounds"]), 2)
        derived = [row for row in catalog["candidates"] if row["placement_kind"] == "pairwise"]
        self.assertEqual(len(derived), 2)
        self.assertTrue(all(row["reference_intervals"] == [] and row["reference_evidence_ids"] == [] for row in derived))
        self.assertTrue(all(row["anchor_candidate_ids"] and row["pairwise_evidence_ids"] for row in derived))
        before = log.read_text()
        self.assertEqual(self.run_prepare(mapper), manifest)
        self.assertEqual(log.read_text(), before)

    def test_completed_discovery_pairs_reach_later_neighbor_planning(self):
        from server.tools.lgz_core import q0_preparation
        parts = {row["source"]["contig"]: row["segment_id"] for row in self.catalog()["segments"]}
        sources = {row["segment_id"]: SourceKey(**row["source"]) for row in self.catalog()["segments"]}
        pair = (parts["s_unplaced"], parts["p_cover"])
        mapper, _ = self.mapper([pair])
        observed = []
        original = q0_preparation.supplemental_groups
        def groups(catalog, assignments, known_pairs):
            observed.append(set(known_pairs))
            return original(catalog, assignments, known_pairs)
        with mock.patch.object(q0_preparation, "supplemental_groups", side_effect=groups):
            manifest = self.run_prepare(mapper)
        self.assertEqual(len(observed), 1)
        self.assertIn(tuple(sorted(sources[key] for key in pair)), observed[0])
        self.assertEqual(load_verified_evidence(self.server), manifest)

    def test_discovery_retains_competing_chromosome_candidates(self):
        parts = {row["source"]["contig"]: row["segment_id"] for row in self.catalog()["segments"]}
        mapper, _ = self.mapper([(parts["s_unplaced"], parts["p_cover"]),
                                 (parts["s_unplaced"], parts["p_reverse"])])
        self.run_prepare(mapper)
        rows = [row for row in self.catalog()["candidates"] if row["segment_id"] == parts["s_unplaced"]]
        self.assertEqual({row["chromosome"] for row in rows}, {"Chr01", "Chr02"})
        self.assertEqual({row["orientation"] for row in rows}, {"+", "-"})

    def test_candidate_builder_change_reuses_content_bound_raw_mappings(self):
        from server.tools.lgz_core import q0_preparation
        mapper, log = self.mapper()
        old = self.run_prepare(mapper)
        before = log.read_text()
        with mock.patch.object(q0_preparation, "builder_identity", return_value="new-candidate-builder"):
            new = self.run_prepare(mapper)
            self.assertNotEqual(old["input_fingerprint"], new["input_fingerprint"])
            self.assertEqual(log.read_text(), before)
            self.assertEqual(new, load_verified_evidence(self.server))

    def test_incomplete_task_receipt_is_not_a_cache_hit(self):
        mapper, log = self.mapper()
        self.run_prepare(mapper)
        task = self.catalog()["supplementary_alignments"][0]
        receipt = self.server / task["receipt"]
        value = json.loads(receipt.read_text()); value["outputs"] = []
        receipt.write_text(json.dumps(value))
        before = log.read_text().count("run")
        self.run_prepare(mapper)
        self.assertEqual(log.read_text().count("run"), before + 1)
        self.assertTrue(load_verified_evidence(self.server))

    def test_failed_or_malformed_supplement_never_replaces_ready_manifest(self):
        for kwargs in ({"failure": True}, {"malformed": True}):
            with self.subTest(kwargs=kwargs):
                before = (self.server / MANIFEST).read_bytes()
                mapper, _ = self.mapper(**kwargs)
                with self.assertRaises(Q0EvidenceError):
                    self.run_prepare(mapper)
                self.assertEqual((self.server / MANIFEST).read_bytes(), before)
                self.assertTrue(list((self.server / "grt/evidence/q0_prepare/tasks").glob("*/stderr.log")))

    def test_reused_output_changed_in_a_later_phase_cannot_publish_success(self):
        from server.tools.lgz_core import q0_preparation as prep
        before=(self.server/MANIFEST).read_bytes();mapper,_=self.mapper();original=prep._supplement
        first=[]
        def supplement(*args,**kwargs):
            task=original(*args,**kwargs)
            if task is not None:
                if first and task["task_id"] != first[0]["task_id"]:
                    path=self.server/first[0]["paf"];path.write_bytes(path.read_bytes()+b"\n")
                elif not first:first.append(task)
            return task
        with mock.patch.object(prep,"_supplement",side_effect=supplement):
            with self.assertRaisesRegex(Q0EvidenceError,"output changed before publication"):
                self.run_prepare(mapper)
        self.assertEqual((self.server/MANIFEST).read_bytes(),before)

    def test_missing_success_receipt_cannot_be_replaced_by_an_existing_paf(self):
        receipt = next((self.server / ".run_all/checkpoints").glob("*.json"))
        receipt.unlink()
        with self.assertRaisesRegex(Q0EvidenceError, "not complete"):
            self.run_prepare()

    def numbered_copy(self):
        from server.tools.run_outer_checkpoints import OuterCheckpointManager
        from server.tools.workspace_layout import initialize_workspace

        layout = initialize_workspace(self.root / "numbered")
        for source in self.server.rglob("*"):
            if source.is_file():
                target = layout.path(source.relative_to(self.server).as_posix())
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        manager = OuterCheckpointManager(layout.root)
        for script in layout.path("runs").glob("chr_*/q0_command.sh"):
            chromosome = script.parent.name.removeprefix("chr_")
            manager.commit(manager.prepare(f"q0_chr:{chromosome}", script.relative_to(layout.root).as_posix()))
        return layout, manager

    def test_numbered_regional_route_keeps_paths_and_reuses_ready_evidence(self):
        from server.tools.lgz_core import q0_preparation as prep

        layout, _ = self.numbered_copy()
        mapper, _ = self.mapper()
        with mock.patch.object(prep, "regional_enabled", return_value=True):
            manifest = prepare_evidence(layout.root, minimap2=str(mapper))
            self.assertEqual(load_verified_evidence(layout.root), manifest)
            with mock.patch.object(prep, "build_catalog", side_effect=AssertionError("ready evidence should be reused")):
                self.assertEqual(prepare_evidence(layout.root, minimap2=str(mapper)), manifest)
        catalog = json.loads(layout.path(manifest["catalog"]).read_text())
        regional = [task for task in catalog["supplementary_alignments"] if task["kind"] == "regional_discovery"]
        self.assertTrue(regional)
        for task in regional:
            self.assertTrue(layout.path(task["receipt"]).is_file())
            self.assertTrue(layout.path(task["paf"]).is_file())
        self.assertTrue(list(layout.path("grt/evidence/q0_prepare/indexes").glob("*/success.json")))
        self.assertFalse(any((layout.root / label).exists() for label in ("grt", "metadata", "runs")))

    def test_numbered_q0_accepts_both_forms_of_the_same_pair_but_rejects_wrong_direction(self):
        from server.tools.lgz_core.q0_preparation import _initial_inputs

        self.seed_assigned_support()
        layout, manager = self.numbered_copy()
        descriptor = layout.path("runs/chr_Chr01/q0_alignment_inputs.json")
        values = json.loads(descriptor.read_text())
        cross = next(row for row in values["alignments"] if row["kind"] == "cross")
        logical = cross["paf"]
        self.assertTrue(logical.startswith("runs/"))
        for supplied in (logical, layout.relative(logical)):
            with self.subTest(paf=supplied):
                cross["paf"] = supplied
                descriptor.write_text(json.dumps(values))
                manager.commit(manager.prepare("q0_chr:Chr01", "runs/chr_Chr01/q0_command.sh"))
                self.assertIn(supplied, {row["paf"] for row in _initial_inputs(layout.root)[5]})
        cross["paf"] = layout.relative(logical).replace("_vs_support/", "_vs_self/")
        self.assertNotEqual(cross["paf"], layout.relative(logical))
        descriptor.write_text(json.dumps(values))
        manager.commit(manager.prepare("q0_chr:Chr01", "runs/chr_Chr01/q0_command.sh"))
        with self.assertRaisesRegex(Q0EvidenceError, "does not match its declared direction"):
            _initial_inputs(layout.root)

    def test_missing_mandatory_pair_is_rejected_even_with_a_fresh_receipt(self):
        from server.tools.run_outer_checkpoints import OuterCheckpointManager
        descriptor = self.server / "runs/chr_Chr01/q0_alignment_inputs.json"
        value = json.loads(descriptor.read_text()); value["alignments"] = []
        descriptor.write_text(json.dumps(value))
        manager = OuterCheckpointManager(self.server)
        prepared = manager.prepare("q0_chr:Chr01", "runs/chr_Chr01/q0_command.sh")
        manager.commit(prepared)
        with self.assertRaisesRegex(Q0EvidenceError, "missing required q0 pairs"):
            self.run_prepare()

    def test_changed_source_or_output_invalidates_the_manifest(self):
        manifest = load_verified_evidence(self.server)
        output = self.server / manifest["catalog"]
        original = output.read_bytes()
        output.write_bytes(original + b" ")
        with self.assertRaisesRegex(Q0EvidenceError, "changed"):
            load_verified_evidence(self.server)
        output.write_bytes(original)
        source = self.server / "data/datasets/primary.fa"
        source.write_text(source.read_text() + "\n")
        with self.assertRaisesRegex(Q0EvidenceError, "changed"):
            load_verified_evidence(self.server)

    def test_manifest_cannot_hide_input_or_supplementary_artifact_entries(self):
        manifest_path = self.server / MANIFEST
        original = manifest_path.read_text()
        manifest = json.loads(original)
        manifest["inputs"].pop()
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(Q0EvidenceError, "fingerprint is inconsistent"):
            load_verified_evidence(self.server)
        manifest_path.write_text(original)
        task = self.catalog()["supplementary_alignments"][0]
        manifest = json.loads(original)
        manifest["outputs"] = [row for row in manifest["outputs"] if row["path"] != task["paf"]]
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(Q0EvidenceError, "not fully bound"):
            load_verified_evidence(self.server)

    def test_candidate_artifact_lookup_accepts_both_inventories_and_rejects_unbound_path(self):
        from server.tools.lgz_core import q0_preparation as prep

        manifest = load_verified_evidence(self.server)
        catalog_path = self.server / manifest["catalog"]
        catalog = prep.json_file(catalog_path)
        # This is the dependency check only; admission separately compares
        # each evidence record to the corresponding bound PAF row.
        in_path = next(row["path"] for row in manifest["inputs"] if row["path"].endswith("/result.paf"))
        out_path = catalog["supplementary_alignments"][0]["paf"]
        catalog["evidence"].update({"input-test":{"artifact":in_path},"output-test":{"artifact":out_path}})
        def rebind_catalog():
            prep.atomic_write_json(catalog_path, catalog)
            manifest["outputs"] = [prep.identity(self.server,r["path"]) if r["path"]==manifest["catalog"] else r
                                   for r in manifest["outputs"]]
            prep.atomic_write_json(self.server / MANIFEST, manifest)
        rebind_catalog()
        self.assertEqual(load_verified_evidence(self.server), manifest)
        catalog["evidence"]["output-test"]["artifact"] = "not-in-the-ready-manifest.paf"
        rebind_catalog()
        with self.assertRaisesRegex(Q0EvidenceError, "unbound alignment artifact"):
            load_verified_evidence(self.server)

    def test_builder_changes_during_preparation_do_not_publish_success(self):
        from server.tools.lgz_core import q0_preparation
        original_manifest = (self.server / MANIFEST).read_bytes()
        mapper, _ = self.mapper()
        value = ["builder-before"]
        real_supplement = q0_preparation._supplement
        def changed(*args, **kwargs):
            result = real_supplement(*args, **kwargs)
            value[0] = "builder-after"
            return result
        with mock.patch.object(q0_preparation, "builder_identity", side_effect=lambda: value[0]), \
             mock.patch.object(q0_preparation, "_supplement", side_effect=changed):
            with self.assertRaisesRegex(Q0EvidenceError, "builder changed"):
                self.run_prepare(mapper)
        self.assertEqual((self.server / MANIFEST).read_bytes(), original_manifest)

    def test_input_change_during_supplement_does_not_publish(self):
        source = self.server / "data/datasets/primary.fa"
        before = (self.server / MANIFEST).read_bytes()
        mapper, _ = self.mapper(mutate=source)
        with self.assertRaisesRegex(Q0EvidenceError, "inputs changed"):
            self.run_prepare(mapper)
        self.assertEqual((self.server / MANIFEST).read_bytes(), before)

    def test_q0_entry_rejects_absent_evidence_instead_of_old_strategy_fallback(self):
        from server.tests.test_q0_admission import bridge_fixture
        from server.tests.test_q0_publication import complete_workspace
        evidence_fixture, _ = bridge_fixture()
        server = complete_workspace(evidence_fixture, self.root / "schema3")
        (server / MANIFEST).unlink()
        completed = subprocess.run([sys.executable, str(fixture.TOOL), "--server-dir", str(server)],
                                   text=True, capture_output=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("q0 evidence is not ready", completed.stderr)
        self.assertFalse((server / "grt/q/q0.fa").exists())

    def test_q0_transaction_preserves_the_prepared_evidence(self):
        from server.tests.test_q0_admission import bridge_fixture
        from server.tests.test_q0_publication import complete_workspace
        evidence_fixture, _ = bridge_fixture()
        server = complete_workspace(evidence_fixture, self.root / "schema3")
        before = load_verified_evidence(server)
        completed = subprocess.run([sys.executable, str(fixture.TOOL), "--server-dir", str(server)],
                                   text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(load_verified_evidence(server), before)

    def test_skip_self_is_not_ignored_by_supplementary_comparisons(self):
        from server.tools.lgz_core.q0_catalog import CandidateCatalog
        from server.tools.lgz_core.q0_preparation import _supplement
        from server.tools.lgz_core.q0_sources import split_source
        from server.tools.lgz_core.common import executable_identity
        sources = {SourceKey("same", "one"): "A" * 100,
                   SourceKey("same", "two"): "C" * 100,
                   SourceKey("other", "three"): "G" * 100}
        parts = {part.segment_id: part for key, seq in sources.items() for part in split_source(key, seq).segments}
        ids = {part.source.contig: part.segment_id for part in parts.values()}
        catalog = CandidateCatalog({"candidates": []}, sources, parts)
        request = {"kind": "skip_self_control", "query_ids": [ids["one"]], "target_ids": [ids["two"]]}
        tool = executable_identity(str(self.minimap))
        with self.assertRaisesRegex(Q0EvidenceError, "--skip-self conflicts"):
            _supplement(self.server, catalog, request, tool, "asm10", 1, skip_self=True)
        request["target_ids"] = [ids["one"], ids["three"]]
        task = _supplement(self.server, catalog, request, tool, "asm10", 1, skip_self=True)
        self.assertTrue((self.server / task["paf"]).is_file())

    def test_artifact_paths_cannot_escape_workspace(self):
        for relative in ("../outside", "/tmp/outside", "x\\y"):
            with self.subTest(relative=relative), self.assertRaises(Q0EvidenceError):
                artifact_path(self.server, relative)


class RealSupplementMappingTests(unittest.TestCase):
    def test_partial_overlap_survives_self_target_and_query_name_order(self):
        from server.tools.lgz_core.q0_preparation import _supplement
        from server.tools.lgz_core.q0_catalog import CandidateCatalog
        from server.tools.lgz_core.q0_sources import split_source
        from server.tools.lgz_core.q0_alignments import read_paf
        from server.tools.lgz_core.common import executable_identity
        minimap = shutil.which("minimap2")
        if not minimap:
            self.skipTest("requires minimap2 for controlled overlap evidence")
        rng = random.Random(20261118)
        sequence = "".join(rng.choices("ACGT", k=8000))
        sources = {SourceKey("ds", "a"): sequence[:5000], SourceKey("ds", "b"): sequence[3000:]}
        parts = {part.segment_id: part for key, seq in sources.items() for part in split_source(key, seq).segments}
        catalog = CandidateCatalog({"candidates": []}, sources, parts)
        ids = sorted(parts)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for query in ids:
                other = next(key for key in ids if key != query)
                task = _supplement(root, catalog, {"kind": "controlled_overlap", "query_ids": [query],
                                                   "target_ids": ids}, executable_identity(minimap), "asm5", 1)
                hits = list(read_paf(root / task["paf"], query_lengths={query: 5000},
                                     target_lengths={key: 5000 for key in ids}))
                paired = [hit for hit in hits if hit.query_name == query and hit.target_name == other]
                self.assertTrue(paired, "self identity or lexical name order suppressed the partial overlap")
                self.assertGreater(max(sum(block.query.length for block in hit.aligned_blocks()) for hit in paired), 1800)


if __name__ == "__main__":
    unittest.main()
