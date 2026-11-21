import os
from pathlib import Path
import random
import tempfile
import unittest

from server.tools.lgz_core.q0_alignments import read_paf, parse_paf_line
from server.tools.lgz_core.q0_catalog import build_catalog
from server.tools.lgz_core.q0_reference_index import ReferenceIndex, _project
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError, SourceKey, split_source


class RecordOffsetTests(unittest.TestCase):
    def test_offsets_preserve_utf8_comments_blank_lines_and_all_newlines(self):
        for newline in ("\n","\r\n","\r"):
            with self.subTest(newline=repr(newline)), tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/"ref.paf";line="小麦\t100\t0\t100\t+\tchr\t1000\t200\t300\t100\t100\t60\tcg:Z:100M"
                raw=("# 注释"+newline+newline+line+newline+line).encode()
                path.write_bytes(raw);seen=[]
                ordinary=list(read_paf(path,query_lengths={"小麦":100},target_lengths={"chr":1000}))
                indexed=list(read_paf(path,query_lengths={"小麦":100},target_lengths={"chr":1000},record_observer=lambda hit,off,size:seen.append((hit,off,size))))
                self.assertEqual(ordinary,indexed);self.assertEqual(len(seen),2)
                for hit,off,size in seen:
                    self.assertEqual(parse_paf_line(raw[off:off+size].decode(),artifact=str(path),line_number=hit.line_number),hit)


class ReferenceIndexTests(unittest.TestCase):
    def fixture(self,root):
        sources={SourceKey("ds",n):"A"*1000 for n in ("a","b","c")}
        parts={p.segment_id:p for key,seq in sources.items() for p in split_source(key,seq).segments}
        ids={p.source.contig:key for key,p in parts.items()}
        refs={"chr":10000};path=root/"runs/ds_vs_ref/result.paf";path.parent.mkdir(parents=True)
        rows=[("a",100,200,"+",9000,9100), # distant query flank must not win
              ("a",300,400,"+",1000,1100),
              ("a",700,800,"+",1400,1500),
              ("b",400,500,"-",1100,1200),
              ("c",100,200,"+",5000,5100)]
        path.write_text("".join(f"{q}\t1000\t{qs}\t{qe}\t{s}\tchr\t10000\t{ts}\t{te}\t100\t100\t255\tcg:Z:100M\n" for q,qs,qe,s,ts,te in rows))
        return sources,parts,ids,refs,path

    def build(self,root,parts,refs,path):
        index=ReferenceIndex.create(root/"index.sqlite",root,parts,refs)
        rel=path.relative_to(root).as_posix();index.register_artifact(rel)
        list(read_paf(path,query_lengths={p.source.contig:1000 for p in parts.values()},target_lengths=refs,artifact=rel,
                      record_observer=lambda hit,offset,size:index.observe_record("ds",hit,offset,size)))
        index.seal();index.close()
        return ReferenceIndex.open(root/"index.sqlite",root,parts,refs)

    def test_exact_nearest_regions_and_exact_target_coordinates_not_grid_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,parts,ids,refs,path=self.fixture(root);index=self.build(root,parts,refs,path)
            regions=index.regions(ids["a"],Interval(500,600),anchor_context=1000,reference_context=10)
            self.assertEqual(regions,{"chr":(Interval(1080,1420),)})
            self.assertEqual(index.targets({"chr":[Interval(1120,1140)]},context=5,exclude=[ids["a"]]),{ids["b"]:(Interval(455,485),)})
            self.assertEqual(index.build_report()["records"],5)
            index.close()

    def test_catalog_callback_is_one_pass_and_payload_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sources,parts,ids,refs,path=self.fixture(root)
            expected=build_catalog(root,sources,refs,[])
            actual=build_catalog(root,sources,refs,[],regional_factory=lambda parts,refs:ReferenceIndex.create(root/"index.sqlite",root,parts,refs))
            self.assertEqual(actual.payload,expected.payload)
            self.assertEqual(actual.regional_index_report["records"],5)
            reused=build_catalog(root,sources,refs,[],regional_factory=lambda parts,refs:ReferenceIndex.open(root/"index.sqlite",root,parts,refs))
            self.assertEqual(reused.payload,expected.payload)

    def test_content_drift_rejected_but_timestamp_only_change_can_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,parts,ids,refs,path=self.fixture(root);index=self.build(root,parts,refs,path)
            index.targets({"chr":[Interval(1120,1140)]}) # populate cache
            original=path.read_text();path.write_text(original)
            with self.assertRaises(Q0EvidenceError):index.targets({"chr":[Interval(1120,1140)]})
            index.close()
            index=ReferenceIndex.open(root/"index.sqlite",root,parts,refs);index.close()
            path.write_text(original.replace("255","254"))
            with self.assertRaises(Q0EvidenceError):ReferenceIndex.open(root/"index.sqlite",root,parts,refs)

    def test_local_paf_mirror_preserves_original_identity_and_fences_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,parts,ids,refs,path=self.fixture(root);index=self.build(root,parts,refs,path)
            regions={"chr":[Interval(1120,1140)]};expected=index.targets(regions,context=5);index.close()
            mirrors=root/"local-pafs";mirrors.mkdir()
            index=ReferenceIndex.open(root/"index.sqlite",root,parts,refs,local_paf_directory=mirrors)
            self.assertEqual(index.targets(regions,context=5),expected)
            self.assertTrue(all(Path(f.name).parent==mirrors for f in index.handles.values()))
            original=path.read_bytes();path.write_bytes(original)
            with self.assertRaisesRegex(Q0EvidenceError,"reference input changed"):
                index.targets(regions)
            index.close()
            index=ReferenceIndex.open(root/"index.sqlite",root,parts,refs,local_paf_directory=mirrors)
            mirror=next(mirrors.glob("*.paf"));mirror.write_bytes(mirror.read_bytes()+b"\n")
            with self.assertRaisesRegex(Q0EvidenceError,"mirror changed"):
                index.targets(regions)
            index.close()
            with self.assertRaisesRegex(Q0EvidenceError,"local reference PAF bytes differ"):
                ReferenceIndex.open(root/"index.sqlite",root,parts,refs,local_paf_directory=mirrors)

    def test_unsealed_and_changed_bindings_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,parts,ids,refs,path=self.fixture(root)
            index=ReferenceIndex.create(root/"unfinished.sqlite",root,parts,refs);index.close()
            with self.assertRaises(Q0EvidenceError):ReferenceIndex.open(root/"unfinished.sqlite",root,parts,refs)
            index=self.build(root,parts,refs,path);index.close()
            with self.assertRaises(Q0EvidenceError):ReferenceIndex.open(root/"index.sqlite",root,parts,{"chr":10001})
            with self.assertRaises(FileExistsError):ReferenceIndex.create(root/"index.sqlite",root,parts,refs)

    def test_split_source_offset_and_large_reference_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=SourceKey("ds","q");sources={source:"A"*100+"N"*100+"C"*100}
            refs={"chr":5_000_000_000};path=root/"runs/ds_vs_ref/result.paf";path.parent.mkdir(parents=True)
            path.write_text("q\t300\t200\t300\t-\tchr\t5000000000\t4000000000\t4000000100\t100\t100\t255\tcg:Z:100M\n")
            catalog=build_catalog(root,sources,refs,[],regional_factory=lambda parts,refs:ReferenceIndex.create(root/"index.sqlite",root,parts,refs))
            index=ReferenceIndex.open(root/"index.sqlite",root,catalog.parts,refs)
            part=next(p for p in catalog.parts.values() if p.interval.start==200)
            self.assertEqual(index.regions(part.segment_id,Interval(20,30),anchor_context=0,reference_context=0),{"chr":(Interval(4000000070,4000000080),)})
            self.assertEqual(index.targets({"chr":[Interval(4000000070,4000000080)]},context=0),{part.segment_id:(Interval(20,30),)})
            index.close()

    def test_projection_roundtrip_and_true_indel_holes(self):
        rng=random.Random(91)
        for strand in ("+","-"):
            for _ in range(100):
                a,b,n=rng.randrange(100),rng.randrange(100),rng.randrange(1,100)
                q,t=Interval(a,a+n),Interval(b,b+n);start=rng.randrange(a,a+n);sub=Interval(start,a+n)
                ref=_project(q,t,strand,sub,from_query=True)
                self.assertEqual(_project(q,t,strand,ref,from_query=False),sub)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sources={SourceKey("ds","q"):"A"*300};refs={"chr":300}
            path=root/"runs/ds_vs_ref/result.paf";path.parent.mkdir(parents=True)
            path.write_text("q\t300\t0\t300\t+\tchr\t300\t0\t300\t290\t310\t60\tcg:Z:100M10I10D190M\n")
            catalog=build_catalog(root,sources,refs,[],regional_factory=lambda parts,refs:ReferenceIndex.create(root/"index.sqlite",root,parts,refs))
            index=ReferenceIndex.open(root/"index.sqlite",root,catalog.parts,refs)
            self.assertEqual(index.targets({"chr":[Interval(100,110)]},context=0),{})
            index.close()


if __name__=="__main__":unittest.main()
