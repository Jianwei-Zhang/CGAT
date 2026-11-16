"""Cross-check audit projections against the actual Server assignment loops.

The Server script has top-level command execution, so execute only its two pure
PAF-to-assignment loops and interval/median helpers with controlled tiny fixtures.
No script CLI, chromosome FASTA generation, or external tools are invoked.
"""
import ast
from pathlib import Path
import tempfile
import unittest

import adaptive_screening as policy


def paf(qlen=1000, start=0, end=800, target="a", strand="+", target_start=100):
    block=end-start
    return f"q\t{qlen}\t{start}\t{end}\t{strand}\t{target}\t20000\t{target_start}\t{target_start+block}\t{block}\t{block}\t60\tcg:Z:{block}M\n"


class AssignmentProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=Path(__file__).resolve().parents[2]/"server/tools/assign_chr_groups.py"
        tree=ast.parse(source.read_text())
        helpers=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ("merged_interval_coverage","weighted_median_of_positions")]
        loops=[n for n in tree.body if isinstance(n,ast.For) and isinstance(n.target,ast.Name)
               and n.target.id=="dataset_name" and isinstance(n.iter,ast.Name) and n.iter.id=="dataset_order"]
        if len(helpers)!=2 or len(loops)<2:raise AssertionError("Server assignment structure changed; review projection")
        cls.code=compile(ast.Module(body=helpers+loops[:2],type_ignores=[]),str(source),"exec")

    def compare(self, text, qlen=1000):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=root/"d_vs_ref";run.mkdir();path=run/"result.paf";path.write_text(text)
            records=[("q","A"*qlen)]
            env={"runs_dir":root,"dataset_order":["d"],"reference_chr_names":["a","b"],"threshold":60.0,
                 "dataset_infos":{"d":{"records_by_name":dict(records),"ordered_records":records}},
                 "candidate_map":{},"assignment_rows":[],"selected_by_chr_dataset":{"a":{},"b":{}},
                 "fail":lambda message: self.fail(message)}
            exec(self.code,env)
            actual={r["assigned_chr_name"]:{"orientation":r["source_orientation"],"covered":r["support_bp"],
                                          "anchor_start":r["anchor_start"]} for r in env["assignment_rows"]}
            profile=policy.coverage_profile(path,[{"name":"q","length":qlen}])["q"]
            self.assertEqual(policy.consumer_assignments(profile,policy.Limits()),actual)
            return profile, actual

    def test_all_qualifying_chromosomes_not_just_winner(self):
        _,actual=self.compare(paf()+paf(end=650,target="b",strand="-"))
        self.assertEqual(set(actual),{"a","b"})

    def test_short_hits_do_not_create_assignment_by_accumulation(self):
        _,actual=self.compare("".join(paf(qlen=10000,start=i,end=i+500) for i in range(0,10000,500)),qlen=10000)
        self.assertEqual(actual,{})

    def test_coverage_threshold_boundary(self):
        for length in (599,600):
            _,actual=self.compare(paf(end=length))
            self.assertEqual(bool(actual),length==600)

    def test_weighted_orientation_can_flip_while_union_coverage_stays_equal(self):
        positive=paf(end=800)
        negative=paf(end=600,strand="-",target_start=200)
        before,old=self.compare(positive+negative+negative)
        after,new=self.compare(positive+negative)
        self.assertEqual(old["a"]["orientation"],"-")
        self.assertEqual(new["a"]["orientation"],"+")
        self.assertEqual(before["target_strands"],after["target_strands"])
        loss=policy.assess_loss({"q":before},{"q":after})
        self.assertIn("downstream_orientation_changed",loss["reasons"])

    def test_orientation_tie_and_reverse_anchor_match_consumer(self):
        _,actual=self.compare(paf(end=600)+paf(end=600,strand="-"))
        self.assertEqual(actual["a"]["orientation"],"+")
        _,actual=self.compare(paf(start=100,end=800,strand="-",target_start=500))
        self.assertEqual(actual["a"]["anchor_start"],301)


if __name__=="__main__":unittest.main()
