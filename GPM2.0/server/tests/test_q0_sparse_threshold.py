"""Localized readless demand may choose windows below the whole-reference size gate."""
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server.tests.test_q0_admission import bridge_fixture, dna
from server.tools.lgz_core import q0_admission as admission, q0_preparation as prep, q0_threshold_prepare as threshold
from server.tools.lgz_core.q0_frontier_scope import UnsearchedQ0Context
from server.tools.lgz_core.q0_sources import Interval, SourceKey, Q0EvidenceError
from server.tools.lgz_core.q0_threshold_acceptance import validate_catalog


class SparseThresholdTests(unittest.TestCase):
    def test_costs_include_context_clipped_to_source_and_union_overlaps(self):
        a,b=(SourceKey("ds",s) for s in ("left","right")); sizes={a:5_000_000,b:45_000_000}
        hint=threshold.sparse_routing({a:(Interval(20,200),Interval(1000,1200))},sizes)
        self.assertEqual(hint["request_bp"],380);self.assertEqual(hint["padded_request_bp"],1_021_200)
        self.assertIsNone(threshold.sparse_routing({a:(Interval(0,sizes[a]),)},sizes))
        self.assertIsNone(threshold.sparse_routing({a:(Interval(10,100),)},{a:2000}))
        self.assertIsNone(threshold.sparse_routing({},sizes));self.assertIsNone(threshold.sparse_routing(None,sizes))

    def test_medium_mixed_workspace_uses_regional_only_for_bounded_request_and_full_repair_is_native(self):
        f,_=bridge_fixture();f.links.clear();f.raw={p:v for p,v in f.raw.items() if "_vs_ref/" in p}
        a,b=(next(s for s in f.sources if s.contig==k) for k in "ab");f.pair(b,a,(0,100),(0,100))
        bulk=3_200_000;f.reference_lengths["other"]=bulk;s=f.source("independent",dna(bulk,222));f.ref(s,(0,bulk),(0,bulk),chromosome="other")
        with tempfile.TemporaryDirectory() as t:
            root=f.workspace(t);(root/"metadata/package.tsv").write_text("reads_qc_enabled\nfalse\n"); fake=Path(t)/"q0-fixture-bin"; opts=dict(minimap2=str(fake/"minimap2"),supplement_scope=threshold.SCOPE)
            with patch.dict(os.environ,{"PATH":str(fake)+os.pathsep+os.environ["PATH"]}):
                # Different executable identity than the fixture used to seed its full generation:
                # do not accidentally test only the warm native-matrix shortcut.
                alternative=fake/"cold-mapper"; shutil.copy2(shutil.which("minimap2",path=os.defpath) or fake/"minimap2", alternative)
                opts["minimap2"]=str(alternative)
                with patch.object(prep,"LocalReferenceCache",wraps=prep.LocalReferenceCache) as indexed:
                    m=prep.prepare_evidence(root,**opts);self.assertEqual(indexed.call_count,1)
                cat=prep.json_file(root/m["catalog"]); self.assertEqual(cat["supplement_scope"]["routing"]["planner"],"sparse_source_windows_v1")
                self.assertIn("regional_candidate_discovery",cat)
                scope=cat["supplement_scope"]; changed={**scope,"routing":{**scope["routing"],"request_bp":0}}
                with self.assertRaisesRegex(Q0EvidenceError,"sparse threshold routing geometry"):
                    validate_catalog(root,m,{**cat,"supplement_scope":changed})
                self.assertEqual(prep.load_verified_evidence(root),m); out=admission.build_q0(root)
                self.assertFalse(out.decisions["supplement_acceptance"]["alternatives_exhaustive"])
                # The independent audit, not the cost heuristic, decides if the reduction can stand.
                (root/prep.MANIFEST).unlink();real=threshold.audit; attempts=[]
                def demand_full(data,selection):
                    attempts.append(data.catalog["supplement_scope"]["effective"])
                    if len(attempts)==1: raise UnsearchedQ0Context("controlled refusal by selector")
                    return real(data,selection)
                with patch.object(threshold,"audit",side_effect=demand_full),patch.object(prep,"LocalReferenceCache",wraps=prep.LocalReferenceCache) as indexed:
                    fixed=prep.prepare_evidence(root,**opts);self.assertEqual(indexed.call_count,1)
                report=prep.json_file(root/fixed["catalog"])["supplement_scope"]
                self.assertEqual(attempts,["decision_frontier","full"]);self.assertNotIn("routing",report);self.assertEqual(report["unsearched_part_intervals"],[])
                with patch.object(prep,"LocalReferenceCache",side_effect=AssertionError("exhaustive mode routed through sparse profile")):
                    full=prep.prepare_evidence(root,minimap2=opts["minimap2"])
                self.assertNotIn("supplement_scope",prep.json_file(root/full["catalog"]))

    @unittest.skipUnless(shutil.which("minimap2"), "needs a real mapper")
    def test_sparse_discovery_resolves_a_bridge_before_competing_candidate_maps(self):
        f,truth=bridge_fixture(reverse=True); c=next(k for k in f.sources if k.contig=="c")
        del f.refs[c]; f.links.clear();f.raw={p:v for p,v in f.raw.items() if "_vs_ref/" in p and p!="runs/c_vs_ref/result.paf"}
        bulk=3_200_000; f.reference_lengths["bulk"]=bulk; d=f.source("bulk",dna(bulk,333)); f.ref(d,(0,bulk),(0,bulk),chromosome="bulk")
        mapper=shutil.which("minimap2")
        with tempfile.TemporaryDirectory() as t:
            root=f.workspace(t);(root/"metadata/package.tsv").write_text("reads_qc_enabled\nfalse\n"); fake=Path(t)/"q0-fixture-bin"
            with patch.dict(os.environ,{"PATH":str(fake)+os.pathsep+os.environ["PATH"]}):
                m=prep.prepare_evidence(root,minimap2=mapper,supplement_scope=threshold.SCOPE)
                cat=prep.json_file(root/m["catalog"]); scope=cat["supplement_scope"]
                self.assertEqual(scope["candidate_threshold_request"],[]);self.assertNotIn("regional_candidate_discovery",cat)
                self.assertTrue(any(t["kind"]=="unplaced_discovery" for t in cat["supplementary_alignments"]))
                self.assertEqual(admission.build_q0(root).records["chr1"],truth)
