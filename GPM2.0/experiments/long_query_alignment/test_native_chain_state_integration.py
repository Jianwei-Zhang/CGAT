"""Deferred real-library/tool comparison; NEVER run in implementation phase.

Requires maintainer-built CGAT_NATIVE_CHAIN_STATE_BUNDLE and the unchanged
CGAT_MINIMAP2_BINARY. No compile or download inside this test; missing artifacts
are an explicit skip, not native equivalence evidence. Final closure requires
actually enabling this gate plus large/customer/downstream acceptance.
"""
from __future__ import annotations

import os
import argparse
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


    def test_native_bridge_matches_whole_query_DP_controls_not_only_exit_success(self):
        import audit_post_dp as audit
        import guided_alignment as ga
        fixtures = audit.fixtures()
        rng = random.Random(2311303)
        dna = bytes(rng.choices(b"ACGT",k=200000))
        decoy = bytearray(dna)
        decoy[60000:61000] = bytes(rng.choices(b"ACGT",k=1000))
        decoy[130000:131000] = bytes(rng.choices(b"ACGT",k=1000))
        cancelled = dna[:60000]+bytes(rng.choices(b"ACGT",k=2000))+dna[60000:130000]+dna[132000:]
        fixtures += [("cancelled_indels",{"target":cancelled},dna),
                     ("cancelled_indels_reverse",{"target":cancelled},dna.translate(wa.RC)[::-1]),
                     ("three_split_decoy",{"exact":dna,"decoy":bytes(decoy)},dna),
                     ("three_split_reverse",{"exact":dna,"decoy":bytes(decoy)},dna.translate(wa.RC)[::-1]),
                     ("three_split_without_exact_parent",{"decoy":bytes(decoy)},dna)]
        def signature(path):
            result = []
            for line in path.read_text().splitlines():
                fields = line.split("\t")
                tags = {t.split(":",1)[0]:t for t in fields[12:]}
                known = tuple(tags.get(k) for k in ("cg","NM","nn","ms","cm","s1","s2","tp","rl","zd"))
                result.append((tuple(fields[:12]),known))
            return result
        with tempfile.TemporaryDirectory(prefix="cgat-native-bridge-controls-") as tmp:
            for name,targets,query_bases in fixtures:
                with self.subTest(case=name):
                    root = Path(tmp)/name
                    root.mkdir()
                    target,query,index,baseline = root/"ref.fa",root/"query.fa",root/"original.mmi",root/"baseline.paf"
                    target.write_bytes(b"".join(b">"+key.encode()+b"\n"+sequence+b"\n" for key,sequence in targets.items()))
                    query.write_bytes(b">query\n"+query_bases+b"\n")
                    wa.run_command([self.mm,"-x","asm10","-t","1","-d",str(index),str(target)],root,"index",120,0)
                    wa.run_command([self.mm,"-c","--eqx","-x","asm10","-t","1","-o",str(baseline),str(index),str(query)],root,"baseline",120,0)
                    context = {"part_index":0,"path":str(index),"sha256":wa.sha256(index),"preset":"asm10",
                        "tool_sha256":wa.sha256(Path(self.mm)),"reference_sha256":wa.sha256(target),
                        "mid_occ":sr.read_shared_mid_occ(root/"baseline.stderr",1),
                        "records":[{"name":key,"length":len(sequence)} for key,sequence in targets.items()]}
                    args = argparse.Namespace(target=target,query=query,out=root/"recovery",minimap2=self.mm,preset="asm10",
                        core_bases=50000,context_bases=4000,guide_slack=1000,threads=2,timeout=120,memory_gib=0,
                        require_full_query_coverage=False,index_context=context,allow_empty_index_part=False,
                        window_candidate_policy="all_chains_pool",recover_path_scores=True,native_state_bundle=Path(self.bundle))
                    report = ga.experiment(args)
                    evaluated = Path(report["native_recovery"]["native_evaluated_paf"])
                    self.assertEqual(signature(evaluated),signature(baseline))
                    self.assertTrue(report["native_recovery"]["selection"]["native_decisions_applied"])
                    public = root/"recovery"/"guided.experimental.paf"
                    self.assertTrue(all(row.split("\t")[11]=="255" for row in public.read_text().splitlines()))
                    self.assertFalse(report["production_ready"])


if __name__ == "__main__":
    unittest.main()
