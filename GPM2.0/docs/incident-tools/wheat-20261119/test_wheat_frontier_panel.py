from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from lgz_core.q0_paths import PairLink
from lgz_core.common import stable_id
from lgz_core.q0_preparation import identity, MAPPING_OUTPUT_FILES
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_sources import Interval, SourceKey
from prepare_wheat_frontier_panel import read_bound
from run_wheat_frontier_panel import context_inventory, missing_competitor_contexts, restore_committed_tasks


class WheatFrontierPanelTests(unittest.TestCase):
    def test_original_paf_read_keeps_bytes_and_requires_receipt(self):
        original = b"# comment\na\t1\t2\t3\t4\tb\trest\nc\t1\t2\t3\t4\td\trest\r\n"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"raw.paf"
            p.write_bytes(original)
            collect = []
            receipt = {"size":len(original),"sha256":sha256(original).hexdigest()}
            def keep(_query,target,line):
                if target == b"d":
                    collect.append(line)
            self.assertEqual(read_bound(p,receipt,keep),2)
            self.assertEqual(collect,[original.splitlines(keepends=True)[-1]])
            p.write_bytes(original.replace(b"rest",b"edit"))
            with self.assertRaisesRegex(ValueError,"frozen receipt"):
                read_bound(p,receipt,keep)

    def test_context_filter_retains_target_only_and_all_targets(self):
        q,t,u = (SourceKey("ds",k) for k in ("query","target","other"))
        parts = {k:SimpleNamespace(source=s,interval=Interval(100,400)) for k,s in (("q",q),("t",t),("u",u))}
        def win(k,start,end):
            return SimpleNamespace(window_id=k+str(start),cores=((start,end),),record=lambda:
                                   {"segment_id":k,"segment_length":300,"start":start,"end":end})
        a,b,c,d = win("q",10,40),win("t",30,60),win("u",0,20),win("q",50,90)
        def completed(_runner,_request):
            yield 0,"parent", ([(a,[b,c]),(d,[c])], "native-fallback-mask", "reason")
        dispatch, plans, counts = context_inventory(completed, SimpleNamespace(parts=parts),{t:(Interval(150,180),)})
        self.assertEqual(list(dispatch(None,None)),[(0,"parent", ([(a,[b,c])], "native-fallback-mask", "reason"))])
        self.assertEqual(counts,Counter(scheduled=1,omitted=1))
        self.assertEqual(len(plans),2)

    def test_terminal_native_resume_copies_success_closure_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            previous, new = (Path(temporary)/name for name in ("old", "new"))
            parts = {key:SimpleNamespace(sequence_sha256=key*64) for key in ("a", "b")}
            spec = {"schema":"lgz_q0_mapping_v1", "query_ids":["a"], "target_ids":["b"],
                    "members":[[k,p.sequence_sha256] for k,p in parts.items()]}
            rel = "grt/evidence/q0_prepare/tasks/" + stable_id("q0-map",spec)
            (previous/rel).mkdir(parents=True)
            outputs = []
            for name in MAPPING_OUTPUT_FILES:
                (previous/rel/name).write_text(name)
                outputs.append(identity(previous,f"{rel}/{name}"))
            for name in ("result.paf.tmp", "stderr.log"):
                (previous/rel/name).write_text("uncommitted input")
            (previous/rel/"success.json").write_text(json.dumps({"status":"success","spec":spec,"outputs":outputs}))
            receipt=restore_committed_tasks(previous,new,parts)
            self.assertEqual(receipt,{"native_successes":1,"regional_successes":0,"files":len(outputs)+1})
            self.assertEqual({p.name for p in (new/rel).iterdir()},set(MAPPING_OUTPUT_FILES)|{"success.json"})
            (previous/rel/"result.paf").write_text("corrupted")
            with self.assertRaisesRegex(ValueError,"differs from receipt"):
                restore_committed_tasks(previous,Path(temporary)/"other",parts)

    def test_competitor_outside_join_region_still_triggers_on_either_axis(self):
        q,t,u = (SourceKey("ds",k) for k in ("query","target","other"))
        h=parse_paf_line("query\t400\t90\t190\t+\ttarget\t400\t0\t100\t100\t100\t60\tcg:Z:100M",
                         artifact="original",line_number=1)
        d=SimpleNamespace(pair_links=[PairLink(h,q,t,100,200)])
        j=SimpleNamespace(kind="sequence_overlap", evidence_ids=[h.evidence_id], join_id="cut")
        p=SimpleNamespace(paths={"chr":SimpleNamespace(path=SimpleNamespace(joins=[j]))})
        scopes={
            (("raw1",()),()):(t,Interval(280,320),((q,Interval(10,30)),),False),
            (("raw2",()),()):(q,Interval(250,300),((t,Interval(350,390)),),False),
            (("unrelated",()),()):(q,Interval(250,300),((u,Interval(90,110)),),False),
        }
        self.assertEqual(missing_competitor_contexts(d,p,scopes),
                         {"exact_joins":1,"joins_with_unsearched_same_pair_contexts":1,
                          "additional_projected_plans":2,"potential_additional_raw_contexts":2})


if __name__=="__main__":
    unittest.main()
