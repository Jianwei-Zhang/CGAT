"""Native-coordinate/anchor fixtures for the final consolidated validation gate."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from server.tools.refinement_admission import degap_proposal, degap_family_proposal, exclude_conflicts
from server.tools.refinement_path import Gap


class Genome:
    def __init__(self, name, sequence):
        self.records = {name: (len(sequence),)}
        self.name, self.sequence = name, sequence.encode()

    def fetch(self, name, start, end):
        assert name == self.name
        return self.sequence[start:end]


def proposal(sequence, candidate, gaps, start, end, left, right):
    row = dict(chromosome="chr1", gap_start=start + 1, gap_end=end, gap_len=end - start,
               left_flank_len=left, right_flank_len=right, replace_start=start - left + 1,
               replace_end=end + right, replace_len=left + end - start + right,
               filled=True, gap_id="native-job")
    return degap_proposal(row, Genome("chr1", sequence), Genome("candidate", candidate), gaps,
                          source_dataset="refinement", native_job="native/job-1", artifact_sha256="a" * 64)


class RefinementAdmissionTests(unittest.TestCase):
    def test_overlap_is_normalized_as_gap_and_duplicate_source_deletion(self):
        edit, reason = proposal("AACCGGNNGGTTAA", "AACCGGTTAA", [Gap("g", "chr1", 6, 8)], 6, 8, 6, 6)
        self.assertEqual(reason, "accepted")
        self.assertEqual((edit.start, edit.end, edit.replacement), (6, 10, None))
        self.assertEqual(edit.evidence["method"], "exact_anchors_overlap_closure")

    def test_joint_repair_keeps_all_gap_identities_and_native_coordinates(self):
        edit, reason = proposal("AANNCCNNGG", "AATTTGG", [Gap("g1", "chr1", 2, 4), Gap("g2", "chr1", 6, 8)], 2, 8, 2, 2)
        self.assertEqual(reason, "accepted")
        self.assertEqual(edit.gap_ids, ("g1", "g2"))
        self.assertEqual((edit.replacement["start"], edit.replacement["end"]), (3, 5))
        self.assertEqual(edit.evidence["method"], "exact_anchors_joint_repair")

    def test_unchanged_ambiguous_or_n_only_candidates_are_not_refinement(self):
        gaps = [Gap("g", "chr1", 2, 4)]
        self.assertEqual(proposal("AANNGG", "AANNNGG", gaps, 2, 4, 2, 2)[1], "candidate_has_no_filled_bases")
        self.assertEqual(proposal("AANNGG", "AATTTCC", gaps, 2, 4, 2, 2)[1], "native_anchors_do_not_reconstruct_baseline")

    def test_pinned_report_coordinates_are_one_based_inclusive_without_heuristics(self):
        row = {"chromosome": "chr1", "gap_start": 3, "gap_end": 4, "gap_len": 2,
               "left_flank_len": 2, "right_flank_len": 2, "replace_start": 1,
               "replace_end": 6, "replace_len": 6, "filled": True, "gap_id": 1}
        def admit(value):
            return degap_proposal(value, Genome("chr1", "AANNGG"), Genome("candidate", "AATTTGG"),
                                  [Gap("g", "chr1", 2, 4)], source_dataset="patch",
                                  native_job="pinned-native-report", artifact_sha256="a" * 64)
        edit, reason = admit(row)
        self.assertEqual(reason, "accepted")
        self.assertEqual((edit.start, edit.end), (2, 4))
        self.assertEqual(edit.evidence["native_coordinates"]["gap_start"], 3)
        shifted = {**row, "gap_start": 2, "gap_end": 3, "replace_start": 0, "replace_end": 5}
        self.assertEqual(admit(shifted)[1], "invalid_native_coordinates")

    @unittest.skipUnless(importlib.util.find_spec("Bio"), "pinned native detector requires Biopython")
    def test_actual_pinned_detector_and_analyzer_emit_the_admitted_coordinate_system(self):
        """Real upstream coordinate producers; filled candidate is controlled, not a native fill run."""
        from server.tools.refinement_tools import bundled_receipt, load_lock
        bundled_receipt(load_lock()["tools"]["degap"])
        directory = Path(__file__).parents[1] / "tools/degap_core/bin"
        modules = []
        for name in ("AutoGapfillerPart2", "AutoGapfillerPart3"):
            spec = importlib.util.spec_from_file_location(name, directory / (name + ".py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules.append(module)
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temporary)
            genome = root / "assembly.fa"
            genome.write_text(">chr1\nAANNGG\n")
            config = root / "01.reads_preprocessor/preprocessing_config.json"
            config.parent.mkdir()
            config.write_text(json.dumps({"hifi_stats": {"SeedLength": 2}}))
            detector = modules[0].GapDetector(genome, root)
            info = detector._extract_flanking_sequences("AANNGG", "chr1", 1, 2, 3)
            analyzer = modules[1].GapFillingAnalyzer(root)
            row = analyzer._analyze_single_gap({"chromosome": "chr1", "gap_id": 1,
                                               "gap_info": info, "left": None, "right": None})
            self.assertEqual((row["gap_start"], row["gap_end"], row["replace_start"], row["replace_end"]),
                             (3, 4, 0, 5))
            self.assertEqual(row["filled"], False)
            # Exercise admission with this exact generated geometry and a known
            # controlled bridge; do not claim the no-job analyzer filled a gap.
            edit, reason = degap_proposal({**row, "filled": True, "replace_start": 1, "replace_end": 6}, Genome("chr1", "AANNGG"),
                                          Genome("candidate", "AATTTGG"), [Gap("g", "chr1", 2, 4)],
                                          source_dataset="patch", native_job="controlled-bridge-real-geometry",
                                          artifact_sha256="a" * 64)
            self.assertEqual(reason, "accepted")
            self.assertEqual((edit.start, edit.end), (2, 4))

    def test_bounded_family_edit_needs_full_exterior_and_exact_integration_slice(self):
        row = dict(chromosome="chr1", gap_start=5, gap_end=6, gap_len=2, left_flank_len=4, right_flank_len=4,
                   replace_start=3, replace_end=6, replace_len=4, filled=True, gap_id=1,
                   junction=dict(mode="gap", gap_length=2, overlap_trim=0, left_replace_bases=1,
                                 right_replace_bases=1, flank_length_delta=0, policy={"version": "test"}))
        def admit(value, integration, full):
            return degap_family_proposal(value, Genome("chr1", "AACCNNAAGG"), Genome("slice", integration),
                                         Genome("full", full), [Gap("g", "chr1", 4, 6)], source_dataset="patch",
                                         native_job="sealed", artifact_sha256="a" * 64, junction_policy="test",
                                         max_flank_replacement_bp=2)
        edit, reason = admit(row, "TTTC", "AACTTTCAGG")
        self.assertEqual(reason, "accepted")
        self.assertEqual((edit.start, edit.end, edit.replacement["end"]), (3, 7, 4))
        self.assertEqual(admit(row, "TTTA", "AACTTTCAGG")[1], "native_integration_slice_disagrees_with_full_candidate")
        self.assertEqual(admit(row, "TTTC", "GCCTTTCAGG")[1], "native_junction_exterior_does_not_reconstruct_baseline")
        self.assertEqual(admit({**row, "replace_start": 4}, "TTTC", "AACTTTCAGG")[1], "invalid_native_junction_coordinates")

    def test_family_overlap_creates_deletion_without_fake_patch(self):
        row = dict(chromosome="chr1", gap_start=7, gap_end=8, gap_len=2, left_flank_len=6, right_flank_len=6,
                   replace_start=6, replace_end=9, replace_len=4, filled=True, gap_id=1,
                   junction=dict(mode="overlap", gap_length=-2, overlap_trim=2, left_replace_bases=0,
                                 right_replace_bases=2, flank_length_delta=0, policy={"version": "test"}))
        edit, reason = degap_family_proposal(row, Genome("chr1", "AACCGGNNGGTTAA"), None,
                                             Genome("full", "AACCGGTTAA"), [Gap("g", "chr1", 6, 8)],
                                             source_dataset="patch", native_job="sealed", artifact_sha256="a" * 64,
                                             junction_policy="test", max_flank_replacement_bp=2)
        self.assertEqual(reason, "accepted")
        self.assertEqual((edit.start, edit.end, edit.replacement), (6, 10, None))

    def test_all_overlapping_proposals_are_rejected(self):
        edit, _ = proposal("AANNGG", "AATTTGG", [Gap("g", "chr1", 2, 4)], 2, 4, 2, 2)
        accepted, rejected = exclude_conflicts([edit, edit])
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 2)


if __name__ == "__main__":
    unittest.main()
