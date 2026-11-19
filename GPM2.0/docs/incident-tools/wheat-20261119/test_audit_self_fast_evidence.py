import tempfile
import unittest
from pathlib import Path

import audit_self_fast_evidence as audit
from test_self_paf_comparison import row


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def evidence(self, name, text):
        path = self.root / name
        path.write_text(text)
        return audit.comparison.read_evidence(path, step=1)

    def test_identity_boundary_retains_secondary_zero_mapq(self):
        source, dest = self.root/'source', self.root/'dest'
        line = row().replace('\t10\t10\t0\t', '\t95\t100\t0\t')
        source.write_text(line + line.replace('\t95\t100\t', '\t94\t100\t'))
        self.assertEqual(audit.filter_identity(source,dest,.95), {'input_rows':2,'retained_rows':1})
        self.assertEqual(dest.read_text(),line)
        self.assertIn('tp:A:S', dest.read_text())

    def test_length_diagnostic_is_not_identity_admission(self):
        source, dest = self.root/'source', self.root/'dest'
        source.write_text(row())
        audit.filter_identity(source,dest,.95,10000)
        self.assertEqual(dest.read_text(),'')

    def test_no_overwrite_or_invalid_identity(self):
        source, dest = self.root/'source', self.root/'dest'
        source.write_text(row()); dest.touch()
        with self.assertRaises(FileExistsError): audit.filter_identity(source,dest,.95)
        with self.assertRaises(ValueError): audit.filter_identity(source,dest,0)
        source.write_text('bad\n')
        with self.assertRaises(ValueError): audit.filter_identity(source,self.root/'new',.95)

    def test_lost_alternative_cannot_be_called_preserved_uniqueness(self):
        a=self.evidence('a',row()+row(ts=50,te=60))
        b=self.evidence('b',row())
        result=audit.uniqueness_transition(a,b)
        self.assertFalse(result['q0_admission_evaluated'])
        self.assertEqual(result['counts']['multiple_to_single_grid_keys'],10)
        self.assertEqual(result['counts']['multiple_to_single_survivor_observed_in_baseline'],10)

    def test_opposite_strand_is_a_competing_map(self):
        a=self.evidence('a',row()+row(strand='-'))
        b=self.evidence('b',row())
        self.assertEqual(audit.uniqueness_transition(a,b)['counts']['multiple_to_single_grid_keys'],10)

    def test_single_map_loss_shift_and_exact_retention(self):
        a=self.evidence('a',row())
        b=self.evidence('b',row(ts=1,te=11))
        c=self.evidence('c',row())
        self.assertEqual(audit.uniqueness_transition(a,b)['counts']['baseline_single_map_missing_or_shifted'],10)
        self.assertEqual(audit.uniqueness_transition(a,c)['counts']['baseline_single_map_retained_exactly'],10)

    def test_distinct_pairs_do_not_compete_and_duplicates_do_not_create_conflicts(self):
        a=self.evidence('a',row()+row()+row(t='different'))
        b=self.evidence('b',row())
        counts=audit.uniqueness_transition(a,b)['counts']
        self.assertEqual(counts['baseline_single_grid_keys'],20)
        self.assertNotIn('baseline_multiple_grid_keys',counts)

if __name__=='__main__': unittest.main()
