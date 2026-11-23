from dataclasses import replace
from types import SimpleNamespace as Row
import unittest

from audit_q0_window_use import ablate, classify
from lgz_core import q0_admission
from server.tests.test_q0_admission import bridge_fixture


class WindowUseTests(unittest.TestCase):
    def test_task_priority_not_record_counts_or_base_evidence(self):
        parts = [Row(placement_id=s, evidence_ids=[s]) for s in ('placed', 'backup')]
        def path(key, eid):
            return Row(slices=[Row(placement_id=key)], joins=[Row(evidence_ids=[eid])])
        s = path('placed', 'edge'); alt = path('backup', 'side')
        data = Row(admission=Row(placements=parts), paths={'A': Row(path=s, alternatives=[s, alt])},
                   decisions={'evidence': {k: {} for k in ('placed', 'edge', 'backup', 'side', 'other')}})
        links = [Row(hit=Row(artifact=task, evidence_id=eid)) for task, eid in (
            ('A', 'placed'), ('A', 'backup'), ('A', 'edge'), ('A', 'edge'), ('B', 'side'),
            ('C', 'other'), ('D', 'uncited'), ('base', 'edge'))]
        selected, counts, joins = classify(data, links, set('ABCDE'))
        self.assertEqual(selected, {'A'})
        self.assertEqual(joins, 1)
        self.assertEqual(counts, dict.fromkeys(('selected_placement_or_join', 'alternative_placement_or_join_only',
            'other_decision_record_only', 'projected_hits_not_cited', 'no_projected_hits'), 1))

    def test_keep_native_when_testing_absence_of_regions(self):
        fixture, truth = bridge_fixture(reverse=True)
        data = fixture.data()
        full = q0_admission.construct_q0(data)
        artifacts = {link.hit.artifact for link in data.pair_links}
        self.assertTrue(artifacts)
        tagged = replace(data, catalog={'base_alignments': [], 'supplementary_alignments': [{'paf': k} for k in artifacts]})
        row = ablate(tagged, full, set(), {}, artifacts)
        self.assertEqual(row['guard'], 'passed')
        self.assertTrue(row['comparison']['chr1']['same_sequence'])
        self.assertEqual(full.records['chr1'], truth)


if __name__ == '__main__':
    unittest.main()
