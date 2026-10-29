"""Deferred real-library/tool comparison; NEVER run in implementation phase.

Requires maintainer-built CGAT_NATIVE_CHAIN_STATE_BUNDLE and the unchanged
CGAT_MINIMAP2_BINARY. No compile or download inside this test; missing artifacts
are an explicit skip, not native equivalence evidence. Final closure requires
actually enabling this gate plus large/customer/downstream acceptance.
"""
from __future__ import annotations

import os
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

import native_chain_state as nst
import selective_reference_alignment as sr
import windowed_alignment as wa


class NativeChainStateIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = os.environ.get("CGAT_NATIVE_CHAIN_STATE_BUNDLE")
        cls.mm = os.environ.get("CGAT_MINIMAP2_BINARY")
        if not cls.bundle or not cls.mm:
            raise unittest.SkipTest("deferred native-state gate: explicit maintainer-built helper and pinned tool required")
        cls.mm = str(Path(cls.mm).resolve())
        cls.verified = nst.validate_bundle(cls.bundle)
        version = subprocess.check_output([cls.mm,"--version"],text=True,timeout=10).strip()
        if version != "2.31-r1302":
            raise AssertionError("native-state integration oracle must use the pinned minimap2")

    def test_native_fields_equal_independent_whole_query_chain_pass_both_strands(self):
        with tempfile.TemporaryDirectory(prefix="cgat-chain-state-integration-") as tmp:
            root = Path(tmp)
            rng = random.Random(2311302)
            sequence = bytes(rng.choices(b"ACGT",k=20000))
            target,query = root/"ref.fa",root/"query.fa"
            target.write_bytes(b">exact\n"+sequence+b"\n>duplicate\n"+sequence+b"\n")
            query.write_bytes(b">forward\n"+sequence+b"\n>reverse\n"+sequence.translate(wa.RC)[::-1]+b"\n")
            index,paf = root/"original.mmi",root/"original.chains.paf"
            wa.run_command([self.mm,"-x","asm10","-t","1","-d",str(index),str(target)],root,"index",120,0)
            wa.run_command([self.mm,"-x","asm10","-t","1","-o",str(paf),str(index),str(query)],root,"chains",120,0)
            mid_occ = sr.read_shared_mid_occ(root/"chains.stderr",1)
            target_store = wa.FastaStore(target,root/"ref.bases")
            query_store = wa.FastaStore(query,root/"query.bases")
            self.addCleanup(target_store.close)
            self.addCleanup(query_store.close)
            context = {"part_index":0,"path":str(index),"sha256":wa.sha256(index),
                       "reference_sha256":wa.sha256(target),"tool_sha256":wa.sha256(Path(self.mm)),
                       "preset":"asm10","mid_occ":mid_occ,
                       "records":[{"name":name,"length":record["length"]} for name,record in target_store.records.items()]}
            before_tool = wa.sha256(Path(self.mm))
            report = nst.collect(query_store,target_store,context,before_tool,self.bundle,paf,root/"states",timeout=120,memory_gib=0)
            self.assertTrue(report["external_chain_paf_equal"])
            self.assertEqual([r["query"] for r in report["queries"]],["forward","reverse"])
            self.assertTrue(all(r["records"] >= 2 for r in report["queries"]))
            self.assertEqual(wa.sha256(Path(self.mm)),before_tool)
            self.assertFalse(report["mapq_reconstructed"])
            self.assertFalse(report["production_ready"])
            bad = root/"tampered.chains.paf"
            rows = paf.read_bytes().splitlines(keepends=True)
            fields = rows[0].decode().rstrip("\n").split("\t")
            fields = [f"s1:i:{int(f[5:])+1}" if f.startswith("s1:i:") else f for f in fields]
            rows[0] = ("\t".join(fields)+"\n").encode()
            bad.write_bytes(b"".join(rows))
            with self.assertRaisesRegex(wa.ExperimentError,"differs from"):
                nst.collect(query_store,target_store,context,before_tool,self.bundle,bad,root/"refused",timeout=120,memory_gib=0)
            self.assertFalse((root/"refused"/"original-chain-state.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
