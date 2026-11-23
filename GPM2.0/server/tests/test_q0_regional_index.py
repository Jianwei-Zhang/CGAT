from pathlib import Path
import random
import tempfile
import unittest
from server.tools.lgz_core.q0_regional_index import RegionalIndex, paired_cells, search_regions
from server.tools.lgz_core.q0_catalog import build_catalog
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError, SourceKey, split_source


class RegionalIndexTests(unittest.TestCase):
    def parts(self):
        return {p.segment_id:p for name in ("a","b","c")
                for p in split_source(SourceKey("ds",name),"A"*1000).segments}

    def test_paired_grid_matches_actual_bases_not_cartesian_hull(self):
        rng=random.Random(20261121)
        for strand in ("+","-"):
            for _ in range(1000):
                qs,ts,n,cell=rng.randrange(100),rng.randrange(100),rng.randrange(1,100),rng.randrange(1,25)
                actual=set(paired_cells(Interval(qs,qs+n),Interval(ts,ts+n),strand,cell))
                expected={((qs+i if strand=="+" else qs+n-1-i)//cell,(ts+i)//cell) for i in range(n)}
                self.assertEqual(actual,expected)
        with self.assertRaises(Q0EvidenceError):list(paired_cells(Interval(0,2),Interval(0,3),"+",10))

    def test_seal_exact_bindings_reopen_and_search_only_overcoverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"index.sqlite";parts=self.parts();ids={p.source.contig:k for k,p in parts.items()}
            refs={"chr":2000};index=RegionalIndex.create(path,parts,refs,cell_bases=100)
            index.observe(ids["a"],"chr",Interval(120,180),Interval(1020,1080),"+")
            index.observe(ids["b"],"chr",Interval(310,370),Interval(1020,1080),"-")
            index.observe(ids["c"],"chr",Interval(700,710),Interval(1700,1710),"+")
            with self.assertRaises(Q0EvidenceError):index.regions(ids["a"],Interval(120,130),anchor_context=0,reference_context=0,bridge_bases=0)
            report=index.seal();self.assertEqual(report["stored_links"],3)
            regions=index.regions(ids["a"],Interval(130,150),anchor_context=0,reference_context=0,bridge_bases=0)
            self.assertEqual(regions,{"chr":(Interval(1000,1100),)})
            self.assertEqual(index.targets(regions,context=10,exclude=[ids["a"]]),{ids["b"]:(Interval(290,410),)})
            with self.assertRaises(Q0EvidenceError):index.observe(ids["a"],"chr",Interval(0,1),Interval(0,1),"+")
            index.close();index=RegionalIndex.open(path,parts,refs,cell_bases=100)
            self.assertEqual(index.targets(regions,context=0,exclude=[ids["a"]]),{ids["b"]:(Interval(300,400),)})
            index.close()
            with self.assertRaises(Q0EvidenceError):RegionalIndex.open(path,parts,{"chr":2001},cell_bases=100)
            with self.assertRaises(FileExistsError):RegionalIndex.create(path,parts,refs,cell_bases=100)

    def test_unsealed_is_never_accepted_and_gaps_are_search_scope_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"index.sqlite";parts=self.parts();index=RegionalIndex.create(path,parts,{"chr":2000})
            index.close()
            with self.assertRaises(Q0EvidenceError):RegionalIndex.open(path,parts,{"chr":2000})
        intervals=[Interval(10,20),Interval(30,40),Interval(100,110)]
        self.assertEqual(search_regions(intervals,bridge_bases=10),(Interval(10,40),Interval(100,110)))
        self.assertEqual(search_regions(intervals),tuple(intervals))

    def test_context_bounds_unknown_names_and_duplicate_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            parts=self.parts();pid=next(iter(parts));index=RegionalIndex.create(Path(tmp)/"index.sqlite",parts,{"chr":2000},cell_bases=100)
            for _ in range(3):index.observe(pid,"chr",Interval(0,1000),Interval(1000,2000),"+")
            self.assertEqual(index.seal()["stored_links"],10)
            self.assertEqual(index.regions(pid,Interval(0,1),anchor_context=10000,reference_context=10000,bridge_bases=0),{"chr":(Interval(0,2000),)})
            with self.assertRaises(Q0EvidenceError):index.targets({"bad":[Interval(0,1)]})
            with self.assertRaises(Q0EvidenceError):index.targets({"chr":[Interval(1900,2100)]})
            with self.assertRaises(Q0EvidenceError):index.targets({},exclude=["bad"])
            with self.assertRaises(Q0EvidenceError):index.regions(pid,Interval(0,1001),anchor_context=0,reference_context=0,bridge_bases=0)
            index.close()

    def test_nearest_flanks_do_not_pull_in_every_distant_local_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            parts=self.parts();pid=next(iter(parts))
            index=RegionalIndex.create(Path(tmp)/"index.sqlite",parts,{"chr":10000},cell_bases=100)
            index.observe(pid,"chr",Interval(100,200),Interval(9000,9100),"+")
            index.observe(pid,"chr",Interval(300,400),Interval(1000,1100),"+")
            index.observe(pid,"chr",Interval(700,800),Interval(1400,1500),"+")
            index.seal()
            regions=index.regions(pid,Interval(500,600),anchor_context=1000,reference_context=0,bridge_bases=0)
            self.assertEqual(regions,{"chr":(Interval(1000,1500),)})
            index.close()

    def test_catalog_one_pass_index_does_not_change_evidence_and_handles_split_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);paf=root/"runs/ds_vs_ref/result.paf";paf.parent.mkdir(parents=True)
            paf.write_text("q\t120\t0\t10\t+\tchr\t1000\t100\t110\t10\t10\t255\tcg:Z:10M\n"
                           "q\t120\t110\t120\t-\tchr\t1000\t200\t210\t10\t10\t255\tcg:Z:10M\n")
            sources={SourceKey("ds","q"):"A"*10+"N"*100+"C"*10};refs={"chr":1000}
            plain=build_catalog(root,sources,refs,[])
            indexed=build_catalog(root,sources,refs,[],regional_factory=lambda parts,lengths:RegionalIndex.create(root/"index.sqlite",parts,lengths,cell_bases=10))
            self.assertEqual(plain.payload,indexed.payload)
            self.assertEqual(indexed.regional_index_report["observed_paired_blocks"],2)
            index=RegionalIndex.open(root/"index.sqlite",indexed.parts,refs,cell_bases=10)
            part=next(p for p in indexed.parts.values() if p.interval.start==110)
            self.assertEqual(index.regions(part.segment_id,Interval(0,10),anchor_context=0,reference_context=0,bridge_bases=0),{"chr":(Interval(200,210),)})
            index.close()
            reused=build_catalog(root,sources,refs,[],regional_factory=lambda parts,lengths:RegionalIndex.open(root/"index.sqlite",parts,lengths,cell_bases=10))
            self.assertEqual(reused.payload,plain.payload)
            self.assertEqual(reused.regional_index_report,indexed.regional_index_report)


if __name__=="__main__":unittest.main()
