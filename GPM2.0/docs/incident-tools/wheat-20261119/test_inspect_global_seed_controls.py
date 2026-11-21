import contextlib
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import inspect_global_seed_controls as probe


class InspectionTests(unittest.TestCase):
    def test_actual_paf_reader_requires_and_receives_explicit_lengths(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);work=root/'work';work.mkdir();control=root/'control';control.mkdir();lookup=root/'lookup';lookup.mkdir()
            baseline=work/'native/result.paf';baseline.parent.mkdir()
            paf='q\t10000\t0\t10000\t+\tt\t10000\t0\t10000\t10000\t10000\t60\tcg:Z:10000M\n'
            baseline.write_text(paf);candidate=control/'result.paf';candidate.write_text(paf)
            write=lambda p,v:p.write_text(json.dumps(v))
            write(baseline.parent/'success.json',{'spec':{'target_ids':['t']}})
            write(control/'summary.json',{'status':'global_seed_controls_complete','result_sha256':probe.sha(candidate),
                                         'all_long_control_coordinates_retained':False})
            write(control/'baseline-query-index.json',{'baseline_identity':{'path':'native/result.paf','sha256':probe.sha(baseline)},
                  'controls':['q'],'ranges':{'q':[[0,len(paf.encode()),1,1]]}})
            write(lookup/'source-part-lookup.json',{'q':{'dataset':'query','length':10000},'t':{'dataset':'target','length':10000}})
            write(lookup/'receipt.json',{'lookup_sha256':probe.sha(lookup/'source-part-lookup.json')})
            cwd=Path.cwd();path=list(sys.path)
            try:
                os.chdir(root)
                with patch.object(sys,'argv',['probe','--control-dir',str(control),'--workspace',str(work),'--lookup-dir',str(lookup)]),contextlib.redirect_stdout(io.StringIO()):probe.main()
            finally:os.chdir(cwd);sys.path[:]=path
            report=json.loads((root/'diagnostics.json').read_text())
            self.assertFalse(report['acceptance_changed'])
            self.assertFalse(report['original_exact_coordinate_gate_passed'])
            self.assertEqual(report['controls'][0]['query_marginal_by_target']['retention'],1)
            self.assertEqual(report['controls'][0]['target_marginal_by_target']['retention'],1)


if __name__=='__main__':unittest.main()
