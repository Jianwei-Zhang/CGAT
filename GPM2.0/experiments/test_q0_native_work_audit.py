import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from q0_native_work_audit import summarize
from server.tests.test_q0_admission import bridge_fixture
from server.tests.test_q0_publication import complete_workspace, run_prepare
from server.tools.lgz_core import q0_preparation as prep


class WorkAuditTests(unittest.TestCase):
    def test_distinguishes_query_contexts_aliases_and_evidence_roles_without_inventing_skips(self):
        tasks = [dict(kind="candidate_chr", task_id=k, paf=k, query_ids=q, target_ids=t, request={"chromosome":c})
                 for k,c,q,t in [("x","A",["a"],["a","b"]),("x","B",["a"],["a","b"]),
                                 ("y","C",["a","b"],["a","b"]),("z","D",["a"],["a","z"])]]
        def path(p,j):return {"slices":[{"placement_id":p}],"joins":[{"evidence_ids":[j]}]}
        con={"placements":[{"placement_id":k,"evidence_ids":[k]} for k in "pq"],
             "searches":{"C":{"path":path("p","j"),"alternatives":[path("q","j")]}},
             "evidence":{k:{"artifact":v} for k,v in zip("pqjr",("x","y","x","y"))}}
        out=summarize({"supplementary_alignments":tasks},con,{k:{"sha256":k,"size":50} for k in "xyz"})
        self.assertEqual((out["completed_native_requests"],out["distinct_completed_native_maps"]),(4,3))
        self.assertEqual(out["ordinary_whole_queries_repeated_with_identical_targets"],1)
        self.assertEqual(out["ordinary_whole_queries_used_with_different_targets"],1)
        self.assertEqual([out["completed_maps"][k]["cited_rows"] for k in "xyz"],
                         [{"selected":2},{"other_decision":1,"alternative_only":1},{}]);self.assertEqual(out["skipped_native_candidate_requests"],[])

    def test_cli_verifies_published_readless_generation(self):
        with tempfile.TemporaryDirectory() as td:
            f,_=bridge_fixture();root=complete_workspace(f,Path(td));bin_=Path(td)/"q0-fixture-bin"
            with patch.dict(os.environ,{"PATH":str(bin_)+os.pathsep+os.environ["PATH"]}):
                receipt=prep.prepare_evidence(root,minimap2=str(bin_/"minimap2"),supplement_scope="positive_threshold")
                proc=run_prepare(root);self.assertEqual(proc.returncode,0,proc.stderr)
                exe=[sys.executable,"-B",str(Path(__file__).with_name("q0_native_work_audit.py")),str(root)]
                out=json.loads(subprocess.check_output(exe));self.assertEqual(out["input_fingerprint"],receipt["input_fingerprint"])
                self.assertEqual((out["scope"],out["completed_native_requests"]),("base_only",0))
                (root/"metadata/grt_q0_selection.json").write_text("{}")
                self.assertNotEqual(subprocess.run(exe,capture_output=True).returncode,0)
