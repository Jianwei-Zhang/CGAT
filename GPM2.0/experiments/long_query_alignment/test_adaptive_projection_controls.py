"""Real pinned-mapper controls for an explicitly approximate projection route.

These exercise the complete mapping/base-check/core-ownership/stitching path,
not just a coverage calculation. They never claim native confidence equivalence.
"""
import argparse
import os
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

import adaptive_screening as policy
import benchmark_ordinary_partitions as validation
import minimap_index_context as mic
import ordinary_batch_performance as perf
import windowed_alignment as wa


class ApproximateProjectionControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm = os.environ.get("CGAT_MINIMAP2_BINARY")
        if not cls.mm:
            raise unittest.SkipTest("explicit pinned minimap2 required; skips are not acceptance")
        cls.mm = str(Path(cls.mm).resolve())
        if subprocess.check_output([cls.mm, "--version"], text=True).strip() != "2.31-r1302":
            raise AssertionError("projection controls require minimap2 2.31-r1302")

    def compare_case(self, copies, *, multipart=False, reverse=False, core=20000, fragmented_decoys=False):
        with tempfile.TemporaryDirectory(prefix="cgat-adaptive-projection-control-") as tmp:
            root = Path(tmp)
            rng = random.Random(2311302)
            sequence = bytes(rng.choices(b"ACGT", k=120000))
            query_sequence = sequence[10000:90000]
            ref, query_path = root/"reference.fa", root/"query.fa"
            if fragmented_decoys:
                # One near-perfect whole-query placement competes with many
                # perfect LOCAL pieces. Local ranking may discard the globally
                # supported chromosome even while total union coverage is 100%.
                mutated = bytearray(sequence)
                changes = dict(zip(b"ACGT", b"CGTA"))
                for i in range(0, len(mutated), 97): mutated[i] = changes[mutated[i]]
                targets = [b">global\n" + bytes(mutated) + b"\n"]
                for start in range(0, len(query_sequence), core):
                    piece = query_sequence[max(0,start-1000):min(len(query_sequence),start+core+1000)]
                    targets.extend(f">decoy_{start}_{i}\n".encode()+piece+b"\n" for i in range(copies))
                ref.write_bytes(b"".join(targets))
            else:
                ref.write_bytes(b"".join(f">chr{i}\n".encode()+sequence+b"\n" for i in range(copies)))
            query_path.write_bytes(b">forward\n"+query_sequence+b"\n"+
                (b">reverse\n"+query_sequence.translate(wa.RC)[::-1]+b"\n" if reverse else b""))
            index = root/"original.mmi"
            flags = ["-I", "100K"] if multipart else []  # Fixture-only original layout.
            wa.run_command([self.mm,"-x","asm10",*flags,"-t","1","-d",str(index),str(ref)],root,"index",30,1)
            native = root/"native.paf"
            wa.run_command([self.mm,"-c","-x","asm10","-t","1","-o",str(native),str(index),str(query_path)],root,"native",30,1)
            mids = validation.thresholds(root/"native.stderr")
            self.assertEqual(len(set(mids)), 1)
            target, query = wa.FastaStore(ref,root/"reference.bases"), wa.FastaStore(query_path,root/"query.bases")
            try:
                layout = mic.copy_parts(index,root/"parts",target.records,reuse_single_part=True)
                self.assertEqual(len(layout["parts"]),copies if multipart else 1)
                combined = root/"projected.paf"
                with combined.open("xb") as out:
                    for part in layout["parts"]:
                        context = {**part,"reference_sha256":target.identity["sha256"],
                            "tool_sha256":wa.sha256(Path(self.mm)),"preset":"asm10","mid_occ":mids[0]}
                        args = argparse.Namespace(target=ref,query=query_path,out=root/f"projection-{part['part_index']}",
                            minimap2=self.mm,preset="asm10",core_bases=core,context_bases=1000,threads=1,
                            timeout=30,memory_gib=1,require_full_query_coverage=False,index_context=context,
                            allow_empty_index_part=True,window_candidate_policy="native_window_selection")
                        result = wa.experiment(args,shared_target=target,shared_query=query)
                        self.assertEqual(result["status"],"validated_experimental_candidate")
                        self.assertFalse(result["production_ready"])
                        parsed = perf.parse_log((args.out/"map.stderr").read_text())
                        self.assertEqual(sum(b["records"] for p in parsed["parts"] for b in p["batches"]),
                                         len(wa.make_windows(query.records,core,1000)))
                        out.write((args.out/"stitched.experimental.paf").read_bytes())
                queries = [{"name":name,"length":r["length"]} for name,r in query.records.items()]
                targets = [{"name":name,"length":r["length"]} for name,r in target.records.items()]
                validation.validate_paf(native,queries,targets)
                validation.validate_paf(combined,queries,targets)
                for line in combined.read_text().splitlines():
                    fields = line.split("\t")
                    self.assertEqual(fields[11],"255")
                    self.assertFalse(any(tag.split(":",1)[0] in {"AS","ms","s1","s2","cm","tp"} for tag in fields[12:]))
                before, after = policy.coverage_profile(native,queries), policy.coverage_profile(combined,queries)
                return before, after, policy.assess_loss(before,after)
            finally:
                target.close(); query.close()

    def test_full_forward_reverse_projection_across_original_parts(self):
        before, after, loss = self.compare_case(2,multipart=True,reverse=True)
        self.assertTrue(loss["passed"],loss)
        for name, strand in (("forward","+"),("reverse","-")):
            self.assertEqual(after[name]["covered"],80000)
            assigned = policy.consumer_assignments(after[name],policy.Limits())
            self.assertEqual(set(assigned),{"chr0","chr1"})
            self.assertTrue(all(row["orientation"]==strand and row["anchor_start"]==10001 for row in assigned.values()))

    def test_full_union_coverage_does_not_hide_lost_ambiguous_assignments(self):
        # asm10 uses N=50 (not the generic N=5); exceed that actual preset
        # limit with local perfect competitors to exercise global-support loss.
        before, after, loss = self.compare_case(64,core=5000,fragmented_decoys=True)
        self.assertEqual(before["forward"]["covered"],80000)
        self.assertEqual(after["forward"]["covered"],80000)
        self.assertFalse(loss["passed"],loss)
        screen = policy.screen_candidate_projection(after)
        self.assertIn("covered_but_unassigned",screen["queries"][0]["reasons"])
        self.assertEqual(screen["queries"][0]["action"],"bounded_review")
        self.assertTrue(loss["downstream_assignments_removed"] or loss["downstream_assignments_added"],loss)
        review = policy.plan_completed_record_review(before,after)
        self.assertEqual(review["selection"],"baseline")


if __name__ == "__main__": unittest.main()
