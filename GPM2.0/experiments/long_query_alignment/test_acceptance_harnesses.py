"""Read-only/default-safe maintainer harness entrypoint contracts."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compare_publication_contract as publication
import compare_server_lifecycle as lifecycle


class AcceptanceHarnessTests(unittest.TestCase):
    def test_publication_default_never_opens_fixture_or_launches_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"not-created"
            with patch.object(publication,"experiment",side_effect=AssertionError("must not execute")),redirect_stdout(io.StringIO()) as text:
                code=publication.main(["--result-dir","/nonexistent-fixture","--native-state-bundle","/nonexistent-helper","--out",str(out)])
            self.assertEqual(code,0)
            self.assertEqual(json.loads(text.getvalue())["status"],"plan_only")
            self.assertFalse(out.exists())

    def test_lifecycle_default_never_opens_package_or_launches_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"not-created"
            with patch.object(lifecycle,"experiment",side_effect=AssertionError("must not execute")),redirect_stdout(io.StringIO()) as text:
                code=lifecycle.main(["--package-root","/nonexistent-package","--out",str(out)])
            self.assertEqual(code,0)
            value=json.loads(text.getvalue())
            self.assertTrue(value["no_files_or_commands_started"])
            self.assertFalse(value["real_minimap2_recovery_test"])
            self.assertFalse(out.exists())

    def test_negative_report_variants_are_disjoint_and_do_not_mutate_fixture(self):
        original={"original_native":{"execution":{"returncode":-6}},"partial_PAF_reused":False,
            "query":{"sha256":"a"*64},"index_catalog_sha256":"a"*64,
            "parts":[{"status":"complete","attempts":[{"queries":["long","empty"],"status":"target_assertion"},
                {"queries":["long"],"status":"target_assertion","recovery":{"publication_proof_sha256":"a"*64}}]}],
            "combination":{"rows_by_query":{"long":1,"empty":0}},
            "native_evaluation":{"sha256":"a"*64},
            "native_evaluation_combination":{"native_cells":1,"evaluated_replacements":["long"]}}
        before=deepcopy(original)
        variants=publication.variants(original)
        self.assertEqual(len(variants),14)
        self.assertEqual(len({name for name,_ in variants}),14)
        self.assertTrue(all(value!=original for _,value in variants))
        self.assertEqual(original,before)
        variants[0][1]["parts"].clear()
        self.assertEqual(original,before)
        self.assertTrue(variants[1][1]["parts"])


if __name__=="__main__":unittest.main()
