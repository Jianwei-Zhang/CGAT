from dataclasses import replace
import unittest

from server.tests.test_q0_admission import EvidenceFixture, bridge_fixture, dna
from audit_q0_draft_consumers import differences, draft_facts, source
from probe_q0_decision_frontier import subset_input


class DraftConsumerTests(unittest.TestCase):
    def test_internal_competitor_changes_placement_inventory_not_donor_availability(self):
        f = EvidenceFixture({'chr': 2000})
        seq = dna(2000); root = f.source('root', seq); alt = f.source('alt', seq[850:1350])
        f.ref(root, (0, 2000), (0, 2000), chromosome='chr')
        hit = f.pair(alt, root, (0, 500), (850, 1350))
        d = replace(f.data(), catalog={'base_alignments': [], 'supplementary_alignments': [{'paf': hit.artifact}]})
        seqs = {source(k): v for k, v in d.sources.items()}
        draft = draft_facts(subset_input(d, set()), seqs); full = draft_facts(d, seqs)
        diff = differences(draft, full)
        for k in ('sequence', 'ordered_path', 'occupied', 'available_donor_intervals', 'reference_gaps'):
            self.assertEqual(diff[k]['draft_sha256'], diff[k]['full_sha256'], k)
        self.assertGreater(diff['known_placement_geometry']['full_only_keys'], 0)
        self.assertEqual(diff['alternative_paths']['changed_common_keys'], 1)
        self.assertEqual(diff['unplaced_parts']['draft_only_keys'], 1)

    def test_positive_reference_placements_do_not_supply_missing_junctions(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                f, _ = bridge_fixture(reverse)
                d = f.data()
                d = replace(d, catalog={'base_alignments': [], 'supplementary_alignments': [
                    {'paf': link.hit.artifact} for link in d.pair_links]})
                seqs = {source(k): v for k, v in d.sources.items()}
                thin = draft_facts(subset_input(d, set()), seqs)
                diff = differences(thin, draft_facts(d, seqs))
                self.assertEqual(diff['known_placement_geometry']['draft_sha256'],
                                 diff['known_placement_geometry']['full_sha256'])
                self.assertEqual(diff['ordered_path']['changed_common_keys'], 1)
                self.assertEqual(diff['sequence']['changed_common_keys'], 1)
                self.assertEqual(diff['available_donor_intervals']['changed_common_keys'], 3)

    def test_same_total_bp_but_different_source_interval_is_not_agreement(self):
        d = differences({'occupied': {'S': [(0, 100)]}}, {'occupied': {'S': [(1, 101)]}})['occupied']
        self.assertEqual(d['changed_common_keys'], 1); self.assertNotEqual(d['full_sha256'], d['draft_sha256'])

    def test_no_trustworthy_path_is_not_a_valid_empty_agreement(self):
        f = EvidenceFixture(); s = f.source('unknown', dna(550)); data = f.data()
        self.assertIsNone(draft_facts(data, {source(s): f.sources[s]}))
