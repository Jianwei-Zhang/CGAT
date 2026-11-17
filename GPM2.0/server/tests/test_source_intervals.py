from __future__ import annotations

import copy
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError, SourceKey
from server.tools.lgz_core.source_intervals import SourceAuthorization, attach_authorizations, source_spans
from server.tools.lgz_core.repair_common import arbitrate
from server.tools.lgz_telomere_finalize import arbitrate_terminal_candidates

A, B = SourceKey("a", "same_name"), SourceKey("b", "same_name")


def segment(source=A, start=0, end=100, orientation="+"):
    return {"segment_kind": "source", "length": end - start, "dataset_name": source.dataset,
            "contig_name": source.contig, "source_start": start + 1, "source_end": end,
            "orientation": orientation, "evidence_ids": []}


def gap(length=100):
    return {"segment_kind": "gap", "length": length}


def authorization(*, informative=None, chromosomes=None):
    members = {(kind, key.dataset): (key, Interval(0, 1000))
               for kind in ("D0", "Dtel") for key in (A, B)}
    return SourceAuthorization({A: 1000, B: 1000}, members,
                               informative or {A: (Interval(0, 1000),), B: (Interval(0, 1000),)},
                               fingerprint="controlled", chromosomes=chromosomes)


def candidate(source=A, start=0, end=100, target=(100, 200), chromosome="chr1", name="candidate", **fields):
    result = {"candidate_id": name, "object_id": name, "member_id": source.dataset,
              "chr": chromosome, "source_dataset": source.dataset, "source_contig": source.contig,
              "source_start": start + 1, "source_end": end, "orientation": "+",
              "input_start": target[0] + 1, "input_end": target[1],
              "target_start": target[0] + 1, "target_end": target[1],
              "identity": 1.0, "aligned_length": 100, "outcome": "candidate"}
    result.update(fields)
    return result


class SourceIntervalTests(unittest.TestCase):
    def setUp(self):
        self.auth = authorization()
        self.paths = {"chr1": [segment(), gap(), segment(B)]}

    def frame(self, paths=None, donor="D0"):
        return self.auth.frame(self.paths if paths is None else paths, donor, "test-q")

    def test_live_source_blocks_reuse_including_reverse_and_other_chromosome(self):
        for orientation in ("+", "-"):
            for chromosome in ("chr1", "chr2"):
                with self.subTest(orientation=orientation, chromosome=chromosome):
                    paths = {**self.paths, "chr2": [gap(300)]}
                    row = candidate(chromosome=chromosome, orientation=orientation)
                    self.assertEqual(self.frame(paths).try_accept(row), "donor_interval_still_present_in_live_path")

    def test_unused_portion_and_distinct_dataset_same_name_are_independent(self):
        self.assertIsNone(self.frame().try_accept(candidate(start=100, end=200)))
        self.assertIsNone(self.frame({"chr1": [segment(), gap()]}).try_accept(candidate(source=B)))

    def test_replacement_reuses_only_its_actual_removed_source(self):
        frame = self.frame()
        row = candidate(start=50, end=150, target=(50, 200))
        self.assertIsNone(frame.try_accept(row))
        self.assertEqual(row["source_interval_authorization"]["reused_within_replacement"], [{"start": 50, "end": 100}])
        blocked = candidate(start=40, end=150, target=(50, 200))
        self.assertEqual(self.frame().try_accept(blocked), "donor_interval_still_present_in_live_path")

    def test_reverse_projection_releases_original_right_end(self):
        paths = {"chr1": [segment(A, 100, 200, "-"), gap()]}
        deletion = candidate(target=(0, 30), interval_edit_kind="remove", source_consumable=False)
        frame = self.frame(paths)
        self.assertIsNone(frame.try_accept(deletion))
        self.assertIsNone(frame.try_accept(candidate(start=170, end=200)))
        blocked = candidate(start=160, end=170, target=(100, 200))
        self.assertEqual(self.frame(paths).try_accept(blocked), "donor_interval_still_present_in_live_path")
        self.assertEqual(deletion["source_interval_authorization"]["released_source_intervals"][0]["intervals"],
                         [{"start": 170, "end": 200}])

    def test_deletion_releases_for_later_edit_and_new_round(self):
        frame = self.frame()
        deletion = candidate(target=(0, 100), interval_edit_kind="remove", source_consumable=False)
        self.assertIsNone(frame.try_accept(deletion))
        self.assertIsNone(frame.try_accept(candidate()))
        resulting_paths = {"chr1": [gap(), segment(B)]}
        next_round = self.frame(resulting_paths)
        self.assertIsNone(next_round.try_accept(candidate(target=(0, 100))))

    def test_rejected_replacement_does_not_release_source(self):
        frame = self.frame()
        # Attempt to replace A with still-live B; this must release neither.
        self.assertEqual(frame.try_accept(candidate(source=B, target=(0, 100))), "donor_interval_still_present_in_live_path")
        self.assertEqual(frame.try_accept(candidate()), "donor_interval_still_present_in_live_path")
        self.assertEqual(frame.removals["chr1"], [])

    def test_new_additions_cannot_duplicate_each_other(self):
        frame = self.frame({"chr1": [gap(200)], "chr2": [gap(200)]})
        self.assertIsNone(frame.try_accept(candidate()))
        self.assertEqual(frame.try_accept(candidate(chromosome="chr2")), "donor_interval_still_present_in_live_path")

    def test_target_overlap_and_zero_length_insertions(self):
        frame = self.frame({"chr1": [gap(200)]})
        self.assertIsNone(frame.try_accept(candidate(target=(50, 150))))
        self.assertEqual(frame.try_accept(candidate(source=B, target=(100, 100))), "source_guard_target_overlap")
        self.assertIsNone(frame.try_accept(candidate(source=B, target=(150, 150))))
        self.assertEqual(frame.try_accept(candidate(source=B, target=(150, 150))), "source_guard_target_overlap")

    def test_frozen_member_and_informative_domains_are_required_for_new_dna(self):
        auth = authorization(informative={A: (Interval(0, 100), Interval(200, 1000)), B: (Interval(0, 1000),)})
        for start, end in ((100, 200), (90, 210)):
            self.assertEqual(auth.frame({"chr1": [gap()]}, "D0", "q").try_accept(candidate(start=start, end=end, target=(0, 100))),
                             "donor_interval_outside_frozen_informative_context")
        self.assertEqual(self.frame().try_accept(candidate(member_id="absent")), "donor_member_not_in_frozen_context")
        self.assertEqual(self.frame().try_accept(candidate(member_id="b")), "donor_member_not_in_frozen_context")
        self.auth.members[("D0", "a")] = (A, Interval(200, 500))
        self.assertEqual(self.frame().try_accept(candidate(start=100, end=300)), "donor_interval_outside_frozen_informative_context")

    def test_reference_guided_removal_does_not_authorize_reference_dna(self):
        guide = SourceKey("reference", "chr1")
        row = candidate(source=guide, target=(0, 100), interval_edit_kind="remove", source_consumable=False)
        self.assertIsNone(self.frame().try_accept(row))
        self.assertIsNone(row["source_interval_authorization"]["added_source_interval"])
        self.assertEqual(self.frame().try_accept(candidate(source=guide)), "donor_member_not_in_frozen_context")
        with self.assertRaisesRegex(Q0EvidenceError, "removal semantics"):
            self.frame().try_accept(candidate(source_consumable=False))

    def test_terminal_coordinates_cover_replaced_terminal_not_only_extension(self):
        for terminal, cut, allowed in (("5prime", 100, True), ("3prime", 200, False)):
            row = candidate(terminal=terminal, target_end=cut)
            row["used_source_start"], row["used_source_end"] = 1, 100
            del row["source_start"], row["source_end"]
            result = self.frame(donor="Dtel").try_accept(row)
            self.assertEqual(result, None if allowed else "donor_interval_still_present_in_live_path")

    def test_path_validation_requires_global_unique_original_source_coordinates(self):
        with self.assertRaisesRegex(Q0EvidenceError, "all live chromosome"):
            authorization(chromosomes={"chr1", "chr2"}).validate_paths(self.paths)
        with self.assertRaisesRegex(Q0EvidenceError, "repeats source"):
            self.auth.validate_paths({**self.paths, "chr2": [segment(orientation="-")]})
        with self.assertRaisesRegex(Q0EvidenceError, "exceeds original"):
            self.auth.validate_paths({"chr1": [segment(end=1001)]})
        with self.assertRaisesRegex(Q0EvidenceError, "length/orientation"):
            self.auth.validate_paths({"chr1": [{**segment(), "length": 99}]})
        with self.assertRaisesRegex(Q0EvidenceError, "absent"):
            self.frame().try_accept(candidate(chromosome="unknown"))
        with self.assertRaisesRegex(Q0EvidenceError, "exceeds its live"):
            self.frame().try_accept(candidate(target=(0, 301)))

    def test_guarded_arbitration_ignores_history_but_blocks_current_reuse(self):
        unused = candidate(start=100, end=200)
        history = [{**unused, "orientation": "-"}]
        result = arbitrate([unused], history, source_guard=self.frame())
        self.assertEqual(result[0]["outcome"], "accepted")
        self.assertNotIn("donor_reuse", result[0])
        live = candidate()
        self.assertEqual(arbitrate([live], [], source_guard=self.frame())[0]["outcome"], "conflicted")

    def test_terminal_arbitration_tries_next_candidate_without_leaking_reservations(self):
        rows = [candidate(terminal="5prime", target_end=0, extract_source_start=1,
                          used_source_start=start + 1, used_source_end=start + 100,
                          telomere_bp=rank, name=name)
                for start, rank, name in ((0, 100, "blocked"), (100, 50, "accepted"))]
        result = arbitrate_terminal_candidates(["chr1"], rows, source_guard=self.frame(donor="Dtel"))
        self.assertEqual([r["outcome"] for r in result], ["conflicted", "accepted"])

    def test_authorization_attaches_to_ordinary_and_terminal_evidence(self):
        row = candidate(start=100, end=200, evidence_ids=["ordinary"], mummer_evidence_id="mummer", minimap_evidence_id="minimap")
        self.assertIsNone(self.frame().try_accept(row))
        evidence = [{"evidence_id": name, "parameters_json": '{"existing": true}'} for name in ("ordinary", "mummer", "minimap", "other")]
        attach_authorizations(evidence, [row])
        for evidence_row in evidence[:3]:
            parameters = json.loads(evidence_row["parameters_json"])
            self.assertTrue(parameters["existing"])
            self.assertEqual(parameters["source_interval_authorization"]["status"], "accepted")
        self.assertNotIn("source_interval_authorization", json.loads(evidence[-1]["parameters_json"]))

    def test_small_random_edits_match_per_base_live_occupancy_oracle(self):
        rng = random.Random(32)
        for _ in range(40):
            orientation = rng.choice(("+", "-"))
            paths = {"chr1": [segment(A, 0, 20, orientation), gap(20)], "chr2": [segment(B, 0, 20)]}
            original = {"chr1": [(A, i) for i in (range(20) if orientation == "+" else reversed(range(20)))] + [None] * 20,
                        "chr2": [(B, i) for i in range(20)]}
            remaining = {chr_name: list(values) for chr_name, values in original.items()}
            frame, additions = self.frame(paths), set()
            # Disjoint original target windows; accepted replacements all remain
            # live. The oracle deliberately uses no interval projection helpers.
            for chromosome, left, right in (("chr1", 0, 10), ("chr1", 10, 20), ("chr1", 20, 30), ("chr2", 0, 10)):
                source, start = rng.choice((A, B)), rng.randrange(35)
                row = candidate(source, start, start + 5, (left, right), chromosome)
                removing = rng.random() < .25
                if removing:
                    row.update(interval_edit_kind="remove", source_consumable=False)
                trial = copy.deepcopy(remaining)
                trial[chromosome][left:right] = [None] * (right - left)
                survivors = {base for values in trial.values() for base in values if base is not None} | additions
                added = set() if removing else {(source, i) for i in range(start, start + 5)}
                expected = not bool(survivors & added)
                accepted = frame.try_accept(row) is None
                self.assertEqual(accepted, expected)
                if accepted:
                    remaining = trial
                    additions |= added


class FrozenSourceIntegrationTests(unittest.TestCase):
    def test_fully_occupied_context_remains_frozen_and_can_be_reused_only_after_removal(self):
        from server.tests.test_q0_admission import EvidenceFixture, dna
        from server.tests.test_q0_publication import complete_workspace, run_prepare
        from server.tools.lgz_core.common import read_tsv
        from server.tools.lgz_core.q0_publication import validate_prepared_q0
        from server.tools.lgz_core.stage_io import load_q_paths, source_catalog
        with tempfile.TemporaryDirectory() as directory:
            fixture = EvidenceFixture()
            sequence = dna(1200) + "N" * 137 + dna(1500, 71)
            source = fixture.source("assembly", sequence)
            fixture.ref(source, (0, 1200), (0, 1200))
            root = complete_workspace(fixture, Path(directory))
            prepared = run_prepare(root)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            frozen = validate_prepared_q0(root)
            self.assertEqual(frozen["sources"][0]["available"], [])
            self.assertEqual(frozen["sources"][0]["informative_intervals"], [{"start": 0, "end": 1200}, {"start": 1337, "end": 2837}])
            ordinary = next(row for row in read_tsv(root / "metadata/grt_donor_sets.tsv") if row["donor_kind"] == "ordinary")
            member = next(row for row in read_tsv(root / "metadata/grt_donor_members.tsv") if row["donor_set_id"] == ordinary["donor_set_id"])
            sources = source_catalog(root)
            auth = SourceAuthorization.load(root, sources, frozen=frozen)
            _, paths, _ = load_q_paths(root, "q0", read_tsv(root / "metadata/grt_q_segments.tsv"), sources)
            frame = auth.frame(paths, ordinary["donor_set_id"], "q0")
            row = candidate(source, target=(1200, 1337), member_id=member["member_id"])
            self.assertEqual(frame.try_accept(row), "donor_interval_still_present_in_live_path")
            deletion = candidate(source, target=(0, 100), member_id=member["member_id"], interval_edit_kind="remove", source_consumable=False)
            self.assertIsNone(frame.try_accept(deletion))
            self.assertIsNone(frame.try_accept(row))
            with self.assertRaisesRegex(Q0EvidenceError, "repeats source"):
                auth.validate_paths({"chr1": [*paths["chr1"], segment(source)]})


@unittest.skipUnless(all(shutil.which(name) for name in ("minimap2", "nucmer", "delta-filter", "show-coords")),
                     "stage CLI tools are not installed")
class SourceAuthorizationStageTests(unittest.TestCase):
    def test_real_refill_cannot_insert_the_same_donor_interval_on_two_chromosomes(self):
        # MUMmer deliberately supplies a completed zero-hit task so this test
        # isolates refill arbitration. Minimap2 and every stage entrypoint run
        # for real; this is not acceptance of the MUMmer structural classifier.
        from server.tests.test_q0_admission import EvidenceFixture, dna
        from server.tests.test_q0_publication import complete_workspace, run_prepare, PROJECT
        from server.tools.lgz_core.common import read_fasta, read_tsv
        from server.tools.lgz_core.stage_io import source_catalog, load_q_paths
        with tempfile.TemporaryDirectory() as directory:
            fixture = EvidenceFixture({"chr1": 60000, "chr2": 60000})
            left, right, fill = dna(22000, 901), dna(23000, 902), dna(500, 903)
            left2, right2 = dna(20000, 904) + left[-2000:], right[:2000] + dna(21000, 905)
            for chromosome, first, last, label in (("chr1", left, right, "one"), ("chr2", left2, right2, "two")):
                a = fixture.source(label + "L", first)
                b = fixture.source(label + "R", last)
                fixture.ref(a, (0, len(first)), (0, len(first)), chromosome=chromosome)
                fixture.ref(b, (0, len(last)), (22100, 22100 + len(last)), chromosome=chromosome)
            # The controlled pre-q0 evidence intentionally leaves this source
            # unlocalized. It becomes a donor candidate only in real refill.
            fixture.source("bridge", left[-2000:] + fill + right[:2000])
            root = complete_workspace(fixture, Path(directory))
            prepared = run_prepare(root)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(dict(read_fasta(root / "grt/q/q0.fa")),
                             {"chr1": left + "N" * 100 + right, "chr2": left2 + "N" * 100 + right2})
            nucmer = Path(directory) / "controlled-no-hit-nucmer"
            nucmer.write_text("#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n"
                              "if '--version' in sys.argv:\n print('controlled completed zero-hit nucmer'); raise SystemExit(0)\n"
                              "prefix = sys.argv[sys.argv.index('-p')+1]\n"
                              "Path(prefix+'.delta').write_text('reference query\\nNUCMER\\n')\n")
            nucmer.chmod(0o755)
            for script in ("lgz_step1.py", "lgz_step2.py", "lgz_step3.py", "lgz_telomere_finalize.py"):
                command = [sys.executable, str(PROJECT / "server/tools" / script), "--server-dir", str(root), "--threads", "1"]
                if script != "lgz_step1.py":
                    command += ["--nucmer", str(nucmer)]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, f"{script}: {result.stdout}\n{result.stderr}")
            records = dict(read_fasta(root / "grt/q/q4.fa"))
            self.assertEqual(records, {"chr1": left + fill + right, "chr2": left2 + "N" * 100 + right2})
            sources = source_catalog(root)
            auth = SourceAuthorization.load(root, sources)
            _, paths, _ = load_q_paths(root, "q4", read_tsv(root / "metadata/grt_q_segments.tsv"), sources)
            auth.validate_paths(paths)
            authorizations = [json.loads(row["parameters_json"]).get("source_interval_authorization")
                              for row in read_tsv(root / "metadata/grt_evidence_registry.tsv")]
            decisions = [decision for decision in authorizations if decision]
            self.assertTrue(any(row["status"] == "accepted" and row["target_chr"] == "chr1" for row in decisions))
            self.assertTrue(any(row.get("reason") == "donor_interval_still_present_in_live_path" and row["target_chr"] == "chr2" for row in decisions))

    def test_schema3_no_edit_path_reaches_q4_and_corrupt_freeze_fails_before_mutation(self):
        from server.tests.test_q0_admission import bridge_fixture
        from server.tests.test_q0_publication import complete_workspace, run_prepare, PROJECT
        from server.tools.lgz_core.common import read_fasta, read_tsv
        from server.tools.lgz_core.q0_publication import FREEZE
        with tempfile.TemporaryDirectory() as directory:
            fixture, truth = bridge_fixture()
            root = complete_workspace(fixture, Path(directory))
            prepared = run_prepare(root)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            commands = ("lgz_step1.py", "lgz_step2.py", "lgz_step3.py", "lgz_telomere_finalize.py")
            def run(script):
                return subprocess.run([sys.executable, str(PROJECT / "server/tools" / script),
                                       "--server-dir", str(root), "--threads", "1"], capture_output=True, text=True)
            for script in commands:
                result = run(script)
                self.assertEqual(result.returncode, 0, f"{script}: {result.stdout}\n{result.stderr}")
            for version in ("q0", "q1", "q2", "q3", "q4"):
                self.assertEqual(dict(read_fasta(root / f"grt/q/{version}.fa")), {"chr1": truth})
            evidence = read_tsv(root / "metadata/grt_evidence_registry.tsv")
            self.assertTrue(any(row["stage"] == "q0_construction" for row in evidence))
            snapshots = {str(path.relative_to(root)): path.read_bytes() for pattern in ("grt/q/*.fa", "grt/checkpoints/*.json")
                         for path in root.glob(pattern)}
            frozen = json.loads((root / FREEZE).read_text())
            frozen["sources"][0]["informative_intervals"] = []
            (root / FREEZE).write_text(json.dumps(frozen))
            result = run("lgz_step2.py")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("informative source intervals differ", result.stderr)
            self.assertEqual({relative: (root / relative).read_bytes() for relative in snapshots}, snapshots)


if __name__ == "__main__":
    unittest.main()
