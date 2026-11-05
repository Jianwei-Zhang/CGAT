"""-f changes are experimental scientific changes, not approved by coverage alone."""
import contextlib
from collections import Counter
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import benchmark_ordinary_filtering as filtering


class FilteringTests(unittest.TestCase):
    def row(self,q='q',start=0,end=10,strand='+',target='t',mapq=60):
        return f'{q}\t100\t{start}\t{end}\t{strand}\t{target}\t100\t0\t{end-start}\t{end-start}\t{end-start}\t{mapq}\tcg:Z:{end-start}M\n'

    def test_coverage_is_union_not_sum_of_secondary_hits(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a';p.write_text(self.row()+self.row(start=5,end=15)+self.row())
            r=filtering.profile(p)
            self.assertEqual(r['coverage'],{'q':15})
            self.assertEqual(sum(r['signatures'].values()),3)

    def test_candidate_losses_and_new_hits_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a',Path(d)/'b'
            a.write_text(self.row()+self.row(q='lost'))
            b.write_text(self.row(end=5)+self.row(q='new',strand='-'))
            diff=filtering.differences(filtering.profile(a),filtering.profile(b))
            self.assertEqual(diff['previously_mapped_queries_now_unmapped'],['lost'])
            self.assertEqual(diff['newly_mapped_queries'],['new'])
            self.assertEqual(diff['queries_with_reduced_union_coverage'],2)
            self.assertEqual(diff['removed_full_PAF_rows'],2)
            self.assertFalse(diff['downstream_scientific_acceptance'])

    def test_score_change_detected_even_when_coordinates_and_coverage_match(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a',Path(d)/'b'
            a.write_text(self.row());b.write_text(self.row(mapq=20))
            diff=filtering.differences(filtering.profile(a),filtering.profile(b))
            self.assertEqual(diff['queries_with_reduced_union_coverage'],0)
            self.assertEqual(diff['removed_full_PAF_rows'],1)
            self.assertEqual(diff['added_full_PAF_rows'],1)
            self.assertEqual(diff['unchanged_geometry_CIGAR_records_with_MAPQ_change'],1)
            self.assertFalse(diff['downstream_scientific_acceptance'])

    def test_lost_alternative_target_detected_without_any_coverage_loss(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a',Path(d)/'b'
            a.write_text(self.row(target='first')+self.row(target='alternative'))
            b.write_text(self.row(target='first'))
            diff=filtering.differences(filtering.profile(a),filtering.profile(b))
            self.assertEqual(diff['queries_with_reduced_union_coverage'],0)
            self.assertEqual(diff['baseline_query_union_coverage_bases'],diff['candidate_query_union_coverage_bases'])
            self.assertEqual(diff['removed_query_target_strand_pairs'],1)
            self.assertEqual(diff['removed_full_PAF_rows'],1)
            self.assertFalse(diff['downstream_scientific_acceptance'])

    def test_primary_coordinate_change_not_hidden_by_total_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a',Path(d)/'b'
            a.write_text(self.row().rstrip('\n')+'\ttp:A:P\n')
            b.write_text(self.row(start=10,end=20).rstrip('\n')+'\ttp:A:P\n')
            diff=filtering.differences(filtering.profile(a),filtering.profile(b))
            self.assertEqual(diff['queries_with_reduced_union_coverage'],0)
            self.assertEqual(diff['queries_with_changed_primary_geometry_or_CIGAR'],1)
            self.assertEqual(diff['removed_geometry_rows'],1)

    def test_cigar_change_at_same_coordinates_is_distinguished(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a',Path(d)/'b'
            first=self.row().rstrip('\n')+'\ttp:A:P\n'
            a.write_text(first);b.write_text(first.replace('cg:Z:10M','cg:Z:4M1I1D5M'))
            diff=filtering.differences(filtering.profile(a),filtering.profile(b))
            self.assertEqual(diff['removed_geometry_rows'],0)
            self.assertEqual(diff['removed_geometry_and_CIGAR_rows'],1)
            self.assertEqual(diff['queries_with_changed_primary_geometry_or_CIGAR'],1)

    def test_even_identical_profile_does_not_claim_downstream_acceptance(self):
        x={'signatures':Counter(),'pairs':set(),'coverage':{}}
        self.assertFalse(filtering.differences(x,x)['downstream_scientific_acceptance'])

    def test_plan_only_does_not_run_or_create_files(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(filtering,'execute') as execute,contextlib.redirect_stdout(io.StringIO()):
                filtering.main(['--target','/missing','--query','/absent','--out',d+'/out'])
            execute.assert_not_called();self.assertEqual(list(Path(d).iterdir()),[])

    def test_invalid_fractions_and_resources_never_execute(self):
        with patch.object(filtering,'execute') as execute,contextlib.redirect_stderr(io.StringIO()):
            for flags in [['--fractions','0.5'],['--fractions','0.01','0.01'],['--threads','65'],['--expected-baseline-paf-sha256','bad']]:
                with self.assertRaises(SystemExit):filtering.main(['--target','/a','--query','/b','--out','/o','--execute',*flags])
            execute.assert_not_called()


if __name__=='__main__':unittest.main()
