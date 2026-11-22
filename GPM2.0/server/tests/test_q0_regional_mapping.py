import importlib
import json
import os
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

    def test_verified_loader_applies_only_to_new_children_and_preserves_raw_reuse(self):
        from server.tools.lgz_core import q0_regional_mapping as regional
        from server.tools.lgz_core.common import sha256_bytes

        with tempfile.TemporaryDirectory() as baseline:
            original_root = self.root
            self.root = Path(baseline)
            try:
                original = self.run_mapping(policy=CigarWorkPolicy(minimum_query_bases=1))
                baseline_paf = (self.root / original["paf"]).read_bytes()
            finally:
                self.root = original_root
        loader = regional._MapperLoader(self.tool["resolved"], self.tool["sha256"],
                                        sha256_bytes(os.fsencode(str(self.root))), "a" * 64)
        with (mock.patch.object(regional, "_probe_mapper_loader", return_value=loader),
              mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": str(self.root), "CGAT_CHILD_TEST": "keep"}, clear=True),
              mock.patch.object(regional.subprocess, "Popen", wraps=regional.subprocess.Popen) as launch,
              regional.verified_mapper_loader(self.tool["resolved"]) as active):
            self.assertTrue(active)
            result = self.run_mapping(policy=CigarWorkPolicy(minimum_query_bases=1))
            self.assertEqual(launch.call_count, 2)
            for call in launch.call_args_list:
                self.assertEqual(call.kwargs["env"], {"CGAT_CHILD_TEST": "keep"})
            self.assertEqual(os.environ["LD_LIBRARY_PATH"], str(self.root))
        self.assertEqual((self.root / result["paf"]).read_bytes(), baseline_paf)
        checked = verify_regional_task(self.root, result, members=self.catalog.parts)
        raw = self.root / checked["spec"]["raw_receipt"]["path"]
        command = json.loads(raw.with_name("command.json").read_text())
        self.assertEqual(command["mapper_loader"]["tool_sha256"], self.tool["sha256"])
        self.assertEqual(command["address_space_bytes"], 4 * 1024**3)
        with mock.patch("subprocess.Popen", side_effect=AssertionError("loader switch must not rerun valid work")):
            self.assertEqual(result, self.run_mapping(policy=CigarWorkPolicy(minimum_query_bases=1)))

    def test_loader_scope_falls_back_if_unverified_tool_or_environment_changes(self):
        from server.tools.lgz_core import q0_regional_mapping as regional
        from server.tools.lgz_core.common import sha256_bytes

        loader = regional._MapperLoader(self.tool["resolved"], self.tool["sha256"], sha256_bytes(b"/same"), "b" * 64)
        for env in ({"LD_LIBRARY_PATH": "/different"}, {"LD_LIBRARY_PATH": "/same", "LD_AUDIT": "/audit.so"},
                    {"LD_LIBRARY_PATH": "relative"}, {"LD_LIBRARY_PATH": "/same:"},
                    {"LD_LIBRARY_PATH": "/same", "PYTHONHOME": "/other"}):
            with self.subTest(env=env), mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(loader.child(self.tool), (None, None))
        with mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": "/same"}, clear=True):
            self.assertEqual(loader.child({**self.tool, "sha256": "c" * 64}), (None, None))
        with self.assertRaisesRegex(Q0EvidenceError, "loader record"):
            regional._verify_mapper_loader_record({"policy": "clear_same_dependencies_v1"}, self.tool)
        with mock.patch.object(regional, "_probe_mapper_loader", return_value=None), regional.verified_mapper_loader("unknown") as active:
            self.assertFalse(active)
            with self.assertRaisesRegex(Q0EvidenceError, "scope in use"):
                with regional.verified_mapper_loader("unknown"):
                    self.fail("nested loader scope was entered")

    def test_dependency_resolution_difference_cannot_enable_loader(self):
        from server.tools.lgz_core import q0_regional_mapping as regional
        with (mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": "/opt/module"}, clear=True),
              mock.patch.object(regional.shutil, "which", return_value=self.tool["resolved"]),
              mock.patch.object(regional, "_dynamic_paths", side_effect=lambda binary, env:
                                {"lib": str(binary if "LD_LIBRARY_PATH" in env else self.root)})):
            self.assertIsNone(regional._probe_mapper_loader(self.tool["resolved"]))

    def test_shared_runtime_digest_uses_one_cold_mapper_read_and_rejects_drift(self):
        from server.tools.lgz_core import q0_regional_mapping as regional

        mapper = self.root / "fixture-minimap2"
        shutil.copy2(self.tool["resolved"], mapper)
        self.tool = executable_identity(str(mapper))
        signatures = importlib.import_module(regional._stable_runtime_sha256.__module__)
        policy = CigarWorkPolicy(minimum_query_bases=1)
        with mock.patch.object(signatures, "_sha256_read", wraps=signatures._sha256_read) as read:
            self.run_mapping(policy=policy)
        cold = [call.args[0][0] for call in read.call_args_list]
        self.assertEqual(cold.count(str(mapper)), 1)  # two launches, before/after each

        def tamper_during_mapper(*args, **kwargs):
            prior = mapper.stat()
            with mapper.open("r+b") as stream:
                first = stream.read(1)
                stream.seek(0)
                stream.write(bytes([first[0] ^ 1]))
            os.utime(mapper, ns=(prior.st_atime_ns, prior.st_mtime_ns))
            return mock.Mock(wait=mock.Mock(return_value=0))

        # Shift the actual input span (not just the projection cores) so this
        # run cannot reuse the completed raw result from the verified tool.
        changed = QueryWindow(self.query.segment_id, 30000, 8499, 12500, ((9000, 12000),))
        before = set(self.root.rglob("success.json"))
        with mock.patch.object(regional.subprocess, "Popen", side_effect=tamper_during_mapper):
            with self.assertRaisesRegex(Q0EvidenceError, "mapper changed during execution"):
                self.run_mapping(changed, policy=policy)
        self.assertEqual(set(self.root.rglob("success.json")), before)

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

    def test_complete_receipts_do_not_require_a_duplicate_standalone_scan(self):
        from server.tools.lgz_core import q0_regional_mapping as regional

        policy = CigarWorkPolicy(minimum_query_bases=1)
        with (mock.patch.object(regional, "read_paf", wraps=regional.read_paf) as exact_scan,
              mock.patch.object(regional, "chain_work", wraps=regional.chain_work) as coarse_scan):
            first = self.run_mapping(policy=policy)
            self.assertEqual(exact_scan.call_count, 1)  # pre-publication raw validation
            self.assertEqual(coarse_scan.call_count, 2)  # pre-publication and final replay
        paf = (self.root / first["paf"]).read_bytes()
        with (mock.patch.object(regional, "read_paf", side_effect=AssertionError("duplicate geometry scan")),
              mock.patch("subprocess.Popen", side_effect=AssertionError("must reuse both complete mappers"))):
            second = self.run_mapping(policy=policy)
        self.assertEqual(first, second)
        self.assertEqual(paf, (self.root / second["paf"]).read_bytes())
        verify_regional_task(self.root, second, members=self.catalog.parts)

    def test_independent_verifier_hashes_each_paf_once_and_detects_content_drift(self):
        from server.tools.lgz_core import q0_preparation as prep

        task=self.run_mapping(policy=CigarWorkPolicy(minimum_query_bases=1))
        with mock.patch.object(prep,"identity",wraps=prep.identity) as identity:
            receipt=verify_regional_task(self.root,task,members=self.catalog.parts)
        paths=[r["path"] for r in receipt["outputs"] if r["path"].endswith("/result.paf")]
        self.assertEqual(len(paths),3)  # complete chaining, raw exact, projection
        actual=[call.args[1] for call in identity.call_args_list if call.args[1].endswith("/result.paf")]
        self.assertCountEqual(actual,paths)
        coarse=next(p for p in paths if "/chaining/" in p)
        with (self.root/coarse).open("ab") as f:f.write(b"# ignored by the coarse parser\n")
        with self.assertRaisesRegex(Q0EvidenceError,"regional output content changed"):
            verify_regional_task(self.root,task,members=self.catalog.parts)

    def test_leaf_hash_cannot_disagree_with_verified_projection_closure(self):
        from server.tools.lgz_core import q0_preparation as prep

        task=self.run_mapping(); receipt=verify_regional_task(self.root,task)
        raw_path=receipt["spec"]["raw_receipt"]["path"]
        raw=prep.json_file(self.root/raw_path)
        next(r for r in raw["outputs"] if r["path"].endswith("/result.paf"))["sha256"]="0"*64
        prep.atomic_write_json(self.root/raw_path,raw)
        receipt["spec"]["raw_receipt"]=prep.identity(self.root,raw_path)
        tid=stable_id("q0-regional-project",receipt["spec"])
        relative=f"grt/evidence/q0_prepare/regional/projects/{tid}"
        rebound={**task,"task_id":tid,"receipt":relative+"/success.json","paf":relative+"/result.paf"}
        (self.root/relative).mkdir();shutil.copyfile(self.root/task["paf"],self.root/rebound["paf"])
        paths=[rebound["paf"] if r["path"]==task["paf"] else r["path"] for r in receipt["outputs"]]
        receipt["outputs"]=[prep.identity(self.root,p) for p in sorted(paths)]
        prep.atomic_write_json(self.root/rebound["receipt"],receipt)
        with self.assertRaisesRegex(Q0EvidenceError,"leaf outputs differ"):
            verify_regional_task(self.root,rebound,members=self.catalog.parts)


        from server.tools.lgz_core import q0_preparation as prep

        task = self.run_mapping()
        projection = json.loads((self.root / task["receipt"]).read_text())
        raw_path = projection["spec"]["raw_receipt"]["path"]
        raw = json.loads((self.root / raw_path).read_text())
        result = next(row["path"] for row in raw["outputs"] if row["path"].endswith("/result.paf"))
        old = (self.root / result).read_text()
        fields = old.split("\t", 2)
        self.assertEqual(len(fields), 3)
        bad_rows = [
            ("\t".join([fields[0], str(int(fields[1]) + 1), fields[2]]).encode(),
             "regional PAF input identity or length"),
            (b"\xff\n", "cannot project q0 regional evidence"),
        ]
        projects = (self.root / task["receipt"]).parent.parent
        before = set(projects.glob("*/success.json"))
        for bad, error in bad_rows:
            with self.subTest(error=error):
                (self.root / result).write_bytes(bad)
                # Matching content hashes do not override window or encoding
                # validation, even when a mapper does not need rerunning.
                raw["outputs"] = [prep.identity(self.root, row["path"]) for row in raw["outputs"]]
                prep.atomic_write_json(self.root / raw_path, raw)
                with mock.patch("subprocess.Popen", side_effect=AssertionError("must check raw geometry")):
                    with self.assertRaisesRegex(Q0EvidenceError, error):
                        self.run_mapping()
                self.assertEqual(set(projects.glob("*/success.json")), before)

    def test_member_validation_rejects_changed_length_and_hash(self):
        task=self.run_mapping()
        members={key:(part.interval.length,part.sequence_sha256) for key,part in self.catalog.parts.items()}
        verify_regional_task(self.root,task,members=members)
        key=self.target.segment_id;length,sha=members[key]
        for changed in ((length+1,sha),(length,"0"*64)):
            with self.assertRaises(Q0EvidenceError):
                verify_regional_task(self.root,task,members={**members,key:changed})

    def test_valid_cached_projection_verified_once_without_preflight_hashes(self):
        from server.tools.lgz_core import q0_preparation as prep

        task=self.run_mapping(policy=CigarWorkPolicy(minimum_query_bases=1))
        identity=prep.identity
        with (mock.patch.object(prep,"identity",wraps=identity) as check,
              mock.patch("subprocess.Popen",side_effect=AssertionError("complete cache must not map"))):
            resumed=self.run_mapping(policy=CigarWorkPolicy(minimum_query_bases=1))
        self.assertEqual(resumed,task)
        paths=[call.args[1] for call in check.call_args_list]
        self.assertEqual(paths.count(task["paf"]),1)
        raw_leaf=[p for p in paths if "/q0-regional-raw-" in p and p.endswith("/result.paf")]
        coarse_leaf=[p for p in paths if "/chaining/" in p and p.endswith("/result.paf")]
        self.assertEqual((len(raw_leaf),len(coarse_leaf)),(2,2))  # leaf acceptance and complete replay

    def test_cached_projection_with_matching_hash_but_wrong_geometry_fails_closed(self):
        from server.tools.lgz_core import q0_preparation as prep

        task=self.run_mapping(); receipt=prep.json_file(self.root/task["receipt"])
        paf=self.root/task["paf"]
        # A syntactically valid duplicate is still not the bound projection of
        # the raw output, even when the projection receipt has its real SHA.
        original=paf.read_bytes();self.assertTrue(original)
        paf.write_bytes(original+original)
        receipt["outputs"]=[prep.identity(self.root,path["path"]) for path in receipt["outputs"]]
        prep.atomic_write_json(self.root/task["receipt"],receipt)
        projects=paf.parent.parent; before={d.name for d in projects.iterdir()}
        with mock.patch("subprocess.Popen",side_effect=AssertionError("geometry error must not map")):
            with self.assertRaisesRegex(Q0EvidenceError,"extra records"):
                self.run_mapping()
        self.assertEqual({d.name for d in projects.iterdir()},before)
        self.assertEqual(paf.read_bytes(),original+original)

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
