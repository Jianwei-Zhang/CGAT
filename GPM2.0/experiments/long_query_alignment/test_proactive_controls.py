"""Entry contracts; scientific controls explicitly require a frozen engine."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compare_proactive_mixed as control
import proactive_reference_plan as planner


class ProactiveControlEntryTests(unittest.TestCase):
    def test_default_does_not_import_engine_or_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"out"
            with patch.object(control,"experiment",side_effect=AssertionError("not authorized to execute")),redirect_stdout(io.StringIO()) as text:
                code=control.main(["--engine-root","/no-engine","--out",str(out)])
            self.assertEqual(code,0)
            self.assertEqual(json.loads(text.getvalue())["status"],"plan_only")
            self.assertFalse(out.exists())

    def test_planner_execute_marks_inputs_only_not_analysis_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/"input.fa";source.write_bytes(b">q1\nACGT\n>q2\nNNNN\n")
            with redirect_stdout(io.StringIO()) as text:
                code=planner.main(["--query",str(source),"--out",str(root/"out"),"--execute"])
            self.assertEqual(code,0)
            result=json.loads(text.getvalue())
            self.assertEqual(result["ordinary_queries"],2)
            self.assertFalse(result["analysis_started"])
            self.assertFalse(result["result_published"])
            self.assertEqual(set(p.name for p in (root/"out").iterdir()),{"groups.json","plan.json"})

    def test_invalid_input_has_no_success_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/"input.fa";source.write_bytes(b"not FASTA\n")
            with redirect_stdout(io.StringIO()) as text:
                code=planner.main(["--query",str(source),"--out",str(root/"out"),"--execute"])
            self.assertEqual(code,2)
            self.assertEqual(json.loads(text.getvalue())["status"],"refused_or_failed")
            self.assertFalse((root/"out").exists())


if __name__=="__main__":unittest.main()
