"""Deferred control-flow checks for original MMI-part guidance; no real tool."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import guided_alignment as ga
import windowed_alignment as wa
from test_minimap_index_context import index_part


class OriginalIndexPartGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target,self.query = self.root/"ref.fa",self.root/"query.fa"
        self.target.write_bytes(b">chr1\nACGTACGT\n>chr2\nACGTACGT\n")
        self.query.write_bytes(b">q\nACGTACGT\n")
        self.tool,self.index = self.root/"minimap2",self.root/"original-part.mmi"
        self.tool.write_bytes(b"not executed by these mock-only checks")
        self.index.write_bytes(index_part([("chr2",8)]))
        self.context = {"part_index":1,"path":str(self.index),"sha256":wa.sha256(self.index),
                        "reference_sha256":wa.sha256(self.target),"tool_sha256":wa.sha256(self.tool),
                        "preset":"asm10","mid_occ":500,"records":[{"name":"chr2","length":8}]}

    def options(self,**updates):
        args = dict(target=self.target,query=self.query,out=self.root/"guidance",minimap2=str(self.tool),
                    preset="asm10",core_bases=4,context_bases=1,guide_slack=0,threads=1,
                    timeout=30,memory_gib=0,require_full_query_coverage=False,
                    index_context=self.context,allow_empty_index_part=True)
        args.update(updates)
        return argparse.Namespace(**args)

    def run_guidance(self, *, window_rows=b"", chain_rows=b""):
        observed = []
        def command(argv,directory,name,*limits):
            observed.append((name,argv))
            if name not in ("map","whole-query"):
                raise AssertionError("original part must not be re-indexed")
            Path(argv[argv.index("-o")+1]).write_bytes(window_rows if name == "map" else chain_rows)
            return {"returncode":0}
        with patch.object(ga.shutil,"which",return_value=str(self.tool)), \
             patch.object(ga.subprocess,"check_output",return_value="2.31-r1302\n"), \
             patch.object(wa,"run_command",side_effect=command):
            report = ga.experiment(self.options())
        return report,observed

    def test_no_hit_part_is_explicit_and_both_passes_reuse_identical_index(self):
        report,observed = self.run_guidance()
        self.assertEqual(report["status"],"no_candidates_in_original_part")
        self.assertEqual([name for name,_ in observed],["map","whole-query"])
        self.assertTrue(all(argv[-2] == str(self.index) for _,argv in observed))
        self.assertTrue(all("-I" not in argv for _,argv in observed))
        self.assertTrue(all(argv[argv.index("-f")+1] == "500" for _,argv in observed))
        self.assertEqual((self.options().out/"guided.experimental.paf").read_bytes(),b"")
        self.assertFalse(report["production_ready"])

    def test_window_chain_disagreement_is_not_accepted_as_no_hit(self):
        raw = b"gpm_window_00000000\t5\t0\t5\t+\tchr2\t8\t0\t5\t5\t5\t60\tcg:Z:5=\n"
        with self.assertRaisesRegex(wa.ExperimentError,"no whole-query candidates"):
            self.run_guidance(window_rows=raw)
        self.assertFalse((self.options().out/"guided.experimental.paf").exists())

    def test_ordinary_standalone_empty_mapping_remains_refused(self):
        with self.assertRaisesRegex(wa.ExperimentError,"no owned alignments"):
            with patch.object(ga.shutil,"which",return_value=str(self.tool)), \
                 patch.object(ga.subprocess,"check_output",return_value="2.31-r1302\n"), \
                 patch.object(wa,"run_command",side_effect=lambda argv,*args:Path(argv[argv.index("-o")+1]).write_bytes(b"")):
                wa.experiment(self.options(out=self.root/"legacy",allow_empty_index_part=False))


if __name__ == "__main__":
    unittest.main()
