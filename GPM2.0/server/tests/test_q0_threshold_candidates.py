"""Whole-map stops are per decision, not per chromosome, mapper hit, or batch."""
from dataclasses import replace
import os
import shutil
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server.tests.test_q0_admission import bridge_fixture, dna
from server.tools.lgz_core import q0_admission as adm, q0_preparation as prep
from server.tools.lgz_core import q0_threshold_candidates as native
from server.tools.lgz_core.q0_sources import Q0EvidenceError
from server.tools.lgz_core.q0_threshold_questions import questions


def candidate(chromosome, q, t):
    return dict(kind="candidate_chr", chromosome=chromosome, query_ids=sorted(q), target_ids=sorted(t))


class NativeThresholdTests(unittest.TestCase):
    def test_actual_paired_evidence_stops_a_pending_rival_only_after_both_joins_are_supported(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse), tempfile.TemporaryDirectory() as tmp:
                f, _ = bridge_fixture(reverse); data = replace(f.data(), pair_links=())
                parts = {p.source.contig: p.segment_id for p in data.parts.values()}
                ids = list(parts.values()); a,b,c = (parts[k] for k in "abc")
                need, _ = questions(data, adm.select_q0_paths(data), [])
                self.assertTrue(need)
                state = native.DecisionState(data, need, [])
                requests = [candidate("a", [c], [a,c]), candidate("alias", [c], [a,c]),
                            candidate("b", [c], [b,c]), candidate("rival", [a,b], ids)]
                launched = []
                def run(wave):
                    self.assertEqual(len(wave), 1)
                    r = wave[0]; name = r["chromosome"]; launched.append(name)
                    hit = f.links[len(launched)-1].hit
                    cols = f.raw[hit.artifact][0].split("\t")
                    cols[0], cols[5] = parts[cols[0]], parts[cols[5]]
                    paf = name+".paf"; (Path(tmp)/paf).write_text("\t".join(cols)+"\n")
                    return [{**r, "paf": paf, "task_id":name}]
                kept, skipped = native.dispatch(Path(tmp), data, requests, [], state, run)
                self.assertEqual(launched, ["a","b"])
                self.assertEqual([r["request"] for r in kept], requests[:3]); self.assertEqual(skipped,requests[3:])
                self.assertEqual(len(state.data.pair_links),2); self.assertEqual(state.need,{})

    def test_target_only_need_preserves_full_map_and_disjoint_work_shares_wave(self):
        f,_=bridge_fixture(); data=f.data(); a,b,c = sorted(data.parts.values(),key=lambda p:p.source.contig)
        need={b.source:(b.interval,),c.source:(c.interval,)}
        req=[candidate("target",[a.segment_id],[a.segment_id,b.segment_id]),candidate("other",[c.segment_id],[c.segment_id])]
        for frontier in (need,None):
            state=SimpleNamespace(need=frontier, observe=lambda *_:None); waves=[]
            def run(batch):
                waves.append(batch); return batch
            kept,skipped=native.dispatch(None,data,req,[],state,run)
            self.assertEqual(waves,[req]);self.assertFalse(skipped);self.assertEqual([r["request"] for r in kept],req)

    @unittest.skipUnless(shutil.which("minimap2"), "needs a real mapper")
    def test_real_native_discovery_can_finish_the_backbone_before_candidate_dispatch(self):
        f,truth=bridge_fixture(); c=next(k for k in f.sources if k.contig=="c")
        del f.refs[c]; f.raw={p:v for p,v in f.raw.items() if "_vs_ref/" in p and p!="runs/c_vs_ref/result.paf"};f.links.clear()
        mapper=shutil.which("minimap2")
        with tempfile.TemporaryDirectory() as td:
            root=f.workspace(td); (root/"metadata/package.tsv").write_text("reads_qc_enabled\nfalse\n")
            # The fixture signed initial checkpoint scripts against its controlled PATH.
            with patch.dict(os.environ,{"PATH":str(Path(td)/"q0-fixture-bin")+os.pathsep+os.environ["PATH"]}):
                receipt=prep.prepare_evidence(root,minimap2=mapper,supplement_scope="positive_threshold")
                cat=prep.json_file(root/receipt["catalog"])
                self.assertEqual(cat["supplement_scope"]["effective"], "supported_after_discovery")
                self.assertEqual([t["kind"] for t in cat["supplementary_alignments"]], ["unplaced_discovery"])
                self.assertEqual(adm.build_q0(root).records["chr1"],truth)

    def test_mixed_workspace_skips_only_supported_chromosome_and_reloads_bound_receipt(self):
        f,_=bridge_fixture(); f.raw={p:v for p,v in f.raw.items() if "_vs_ref/" in p}; f.links.clear()
        f.reference_lengths["supported"]=5000
        for name, length in (("d",5000),("e",1200)):
            source=f.source(name,dna(length));f.ref(source,(0,length),(0,length),chromosome="supported")
        with tempfile.TemporaryDirectory() as td:
            root=f.workspace(td); (root/"metadata/package.tsv").write_text("reads_qc_enabled\nfalse\n")
            bin_=Path(td)/"q0-fixture-bin"; mapper=str(bin_/"minimap2")
            with patch.dict(os.environ,{"PATH":str(bin_)+os.pathsep+os.environ["PATH"]}):
                receipt=prep.prepare_evidence(root,minimap2=mapper,supplement_scope="positive_threshold")
                cat=prep.json_file(root/receipt["catalog"]); report=cat["supplement_scope"]
                self.assertEqual(report["effective"],"decision_frontier")
                self.assertEqual([r["chromosome"] for r in report["native_candidate_stops"]],["supported"])
                self.assertEqual([t["request"]["chromosome"] for t in cat["supplementary_alignments"] if t["kind"]=="candidate_chr"],["chr1"])
                self.assertEqual(prep.load_verified_evidence(root),receipt)
                selection=adm.build_q0(root); self.assertFalse(selection.decisions["supplement_acceptance"]["alternatives_exhaustive"])
                self.assertTrue(selection.decisions["supplement_acceptance"]["decision_counts"]["unproven_join"])
                with self.assertRaisesRegex(Q0EvidenceError,"axes"):
                    native.verify_stops(cat,{**report,"unsearched_part_intervals":[]})
                self.assertEqual(prep.prepare_evidence(root,minimap2=mapper,supplement_scope="positive_threshold"),receipt)
                # Simulate a superseded/intermediate planning selection. The independent final
                # selector must detect the omitted weak join and repair with complete maps.
                (root/prep.MANIFEST).unlink()
                with patch.object(native.DecisionState,"observe",lambda self,*_: setattr(self,"need",{})):
                    repaired=prep.prepare_evidence(root,minimap2=mapper,supplement_scope="positive_threshold")
                fixed=prep.json_file(root/repaired["catalog"])
                self.assertEqual(fixed["supplement_scope"]["effective"],"full")
                self.assertEqual(len(fixed["supplementary_alignments"]),2)
                self.assertFalse(fixed["supplement_scope"]["unsearched_part_intervals"])
                full=prep.prepare_evidence(root,minimap2=mapper);fullcat=prep.json_file(root/full["catalog"])
                self.assertEqual([t["request"]["chromosome"] for t in fullcat["supplementary_alignments"] if t["kind"]=="candidate_chr"],["chr1","supported"])
