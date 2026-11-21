"""Native-coordinate/anchor fixtures for the final consolidated validation gate."""
import unittest
from server.tools.refinement_admission import degap_proposal, exclude_conflicts
from server.tools.refinement_path import Gap


class Genome:
    def __init__(self, name, sequence):
        self.records = {name: (len(sequence),)}
        self.name, self.sequence = name, sequence.encode()

    def fetch(self, name, start, end):
        assert name == self.name
        return self.sequence[start:end]


def proposal(sequence, candidate, gaps, start, end, left, right):
    row = dict(chromosome="chr1", gap_start=start, gap_end=end - 1, gap_len=end - start,
               left_flank_len=left, right_flank_len=right, replace_start=start - left,
               replace_end=end + right - 1, replace_len=left + end - start + right,
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

    def test_all_overlapping_proposals_are_rejected(self):
        edit, _ = proposal("AANNGG", "AATTTGG", [Gap("g", "chr1", 2, 4)], 2, 4, 2, 2)
        accepted, rejected = exclude_conflicts([edit, edit])
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 2)


if __name__ == "__main__":
    unittest.main()
