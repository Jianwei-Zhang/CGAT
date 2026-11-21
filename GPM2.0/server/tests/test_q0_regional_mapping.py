import json
from dataclasses import asdict
from pathlib import Path
import random
import shutil
import tempfile
import unittest
from unittest import mock

from server.tools.lgz_core.common import executable_identity, write_fasta, stable_id
from server.tools.lgz_core.q0_catalog import CandidateCatalog
from server.tools.lgz_core.q0_query_windows import QueryWindow,TargetWindow
from server.tools.lgz_core.q0_sources import SourceKey,split_source,Q0EvidenceError
from server.tools.lgz_core.q0_regional_mapping import prepare_regional_mapping,verify_regional_task,RegionalFallbackRequired,chain_work
from server.tools.lgz_core.q0_cigar_policy import CigarWorkPolicy


class RegionalMappingTests(unittest.TestCase):
    def setUp(self):
        mapper=shutil.which("minimap2")
        if mapper is None:self.skipTest("requires minimap2")
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        rng=random.Random(812);sequence="".join(rng.choices("ACGT",k=30000))
        sources={SourceKey("a","q"):sequence,SourceKey("b","t"):"A"*500+sequence[8500:12500]+"C"*500}
        parts={p.segment_id:p for key,seq in sources.items() for p in split_source(key,seq).segments}
        self.catalog=CandidateCatalog({"candidates":[]},sources,parts);ids={p.source.contig:key for key,p in parts.items()}
        self.query=QueryWindow(ids["q"],30000,8500,12500,((9000,12000),));self.target=TargetWindow(ids["t"],5000,400,4600)
        self.tool=executable_identity(mapper)

    def run_mapping(self,query=None,**kwargs):
        return prepare_regional_mapping(self.root,self.catalog,query or self.query,[self.target],self.tool,
                                        reference_bases=5_000_000_000,threads=1,**kwargs)

    def test_complete_raw_reused_when_cores_change_and_temporary_inputs_are_gone(self):
        first=self.run_mapping();old=verify_regional_task(self.root,first,members=self.catalog.parts)
        self.assertGreater((self.root/first["paf"]).stat().st_size,0)
        self.assertEqual(list((self.root/"grt").rglob("query.fa")),[])
        changed=QueryWindow(self.query.segment_id,30000,8500,12500,((10000,11000),))
        with mock.patch("subprocess.Popen",side_effect=AssertionError("must reuse complete mapper output")):
            second=self.run_mapping(changed)
        new=verify_regional_task(self.root,second,members=self.catalog.parts)
        self.assertNotEqual(first["task_id"],second["task_id"])
        self.assertEqual(old["spec"]["raw_receipt"],new["spec"]["raw_receipt"])

    def test_member_validation_rejects_changed_length_and_hash(self):
        task=self.run_mapping()
        members={key:(part.interval.length,part.sequence_sha256) for key,part in self.catalog.parts.items()}
        verify_regional_task(self.root,task,members=members)
        key=self.target.segment_id;length,sha=members[key]
        for changed in ((length+1,sha),(length,"0"*64)):
            with self.assertRaises(Q0EvidenceError):
                verify_regional_task(self.root,task,members={**members,key:changed})

    def test_projection_damage_is_repaired_without_rerunning_raw_mapping(self):
        task=self.run_mapping();(self.root/task["paf"]).write_text("damaged\n")
        with self.assertRaises(Q0EvidenceError):verify_regional_task(self.root,task)
        with mock.patch("subprocess.Popen",side_effect=AssertionError("raw must survive projection repair")):
            repaired=self.run_mapping()
        verify_regional_task(self.root,repaired)
        self.assertTrue(list((self.root/task["paf"]).parent.parent.glob("*.invalid-*")))

    def test_source_change_and_unknown_window_bounds_fail_before_cached_acceptance(self):
        self.run_mapping();key=next(k for k in self.catalog.sequences if k.dataset=="a")
        self.catalog.sequences[key]="C"*30000
        with self.assertRaises(Q0EvidenceError):self.run_mapping()
        with self.assertRaises(RegionalFallbackRequired):prepare_regional_mapping(self.root,self.catalog,self.query,[],self.tool,reference_bases=5_000_000_000)

    def test_complete_chaining_selects_profile_and_is_not_adopted_as_scientific_paf(self):
        # Exercise the small fixture through the same complete-chaining branch.
        policy=CigarWorkPolicy(minimum_query_bases=1)
        task=self.run_mapping(policy=policy);receipt=verify_regional_task(self.root,task,members=self.catalog.parts)
        decision=json.loads((self.root/receipt["spec"]["decision"]["path"]).read_text())
        self.assertIn("chaining_receipt",decision)
        self.assertFalse(decision["approximate_chaining_is_evidence"])
        with mock.patch("subprocess.Popen",side_effect=AssertionError("chaining and exact mapping must both reuse")):
            self.run_mapping(policy=policy)
        self.assertNotEqual(task["paf"],decision["chaining_receipt"]["path"])

    def test_incomplete_or_wrong_approximate_inputs_are_rejected(self):
        path=self.root/"bad.paf"
        path.write_text(f"{self.query.window_id}\t4000\t0\t100\t+\t{self.target.window_id}\t4200\t0\t100\t100\t100\t0\tcg:Z:100M\ts1:i:100\n")
        with self.assertRaises(Q0EvidenceError):chain_work(path,self.query,{self.target.window_id:self.target.length},CigarWorkPolicy())

    def test_ready_manifest_and_unchanged_admission_accept_only_projected_cigar(self):
        from server.tools.lgz_core import q0_preparation as prep
        from server.tools.lgz_core.q0_admission import load_evidence_input
        from server.tools.lgz_core.q0_catalog import CATALOG_SCHEMA
        task=self.run_mapping(policy=CigarWorkPolicy(minimum_query_bases=1))
        (self.root/"metadata").mkdir();(self.root/"data").mkdir();paths=[];datasets=[]
        for key,sequence in self.catalog.sequences.items():
            rel=f"data/{key.dataset}.fa";write_fasta(self.root/rel,[(key.contig,sequence)]);paths.append(rel)
            datasets.append(f"{key.dataset}\t{rel}\n")
            paf=f"runs/{key.dataset}_vs_ref/result.paf";(self.root/paf).parent.mkdir(parents=True);(self.root/paf).write_text("");paths.append(paf)
        write_fasta(self.root/"data/ref.fa",[("chr","ACGT"*1000)]);paths.append("data/ref.fa")
        (self.root/"metadata/datasets.tsv").write_text("dataset_name\tfasta_relpath\n"+"".join(datasets))
        (self.root/"metadata/reference.tsv").write_text("fasta_relpath\ndata/ref.fa\n")
        paths.extend(["metadata/datasets.tsv","metadata/reference.tsv"])
        catalog={"schema":CATALOG_SCHEMA,"min_gap":100,"segments":[asdict(p) for p in self.catalog.parts.values()],
                 "original_connections":[],"base_alignments":[],"supplementary_alignments":[task],"evidence":{}}
        relative="grt/evidence/regional-test-catalog.json";prep.atomic_write_json(self.root/relative,catalog)
        receipt=verify_regional_task(self.root,task,members=self.catalog.parts)
        outputs={relative,task["receipt"]}|{r["path"] for r in receipt["outputs"]}
        inputs=[prep.identity(self.root,rel) for rel in sorted(paths)];builder=prep.builder_identity()
        manifest={"schema":prep.SCHEMA,"status":"success","policy":prep.POLICY,"builder":builder,"tool":self.tool,
                  "inputs":inputs,"outputs":[prep.identity(self.root,rel) for rel in sorted(outputs)],"catalog":relative}
        manifest["input_fingerprint"]=stable_id("q0-evidence-input",{"inputs":inputs,"tool":self.tool,"policy":prep.POLICY,"builder":builder})
        prep.atomic_write_json(self.root/prep.MANIFEST,manifest)
        self.assertEqual(prep.load_verified_evidence(self.root),manifest)
        data=load_evidence_input(self.root)
        self.assertTrue(data.pair_links)
        self.assertTrue(all(link.hit.artifact==task["paf"] for link in data.pair_links))
        self.assertTrue(all(link.hit.mapq==255 for link in data.pair_links))
        # Removing any raw/chaining dependency is not a valid ready manifest.
        manifest["outputs"]=[row for row in manifest["outputs"] if not row["path"].endswith("/chaining/result.paf")]
        prep.atomic_write_json(self.root/prep.MANIFEST,manifest)
        with self.assertRaises(Q0EvidenceError):prep.load_verified_evidence(self.root)


if __name__=="__main__":unittest.main()
