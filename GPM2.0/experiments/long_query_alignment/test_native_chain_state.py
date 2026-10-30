"""Deferred protocol/build-receipt checks; NOT run during implementation."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch

import build_native_chain_state as build
import native_chain_state as nst
import post_dp_selection as ps
import windowed_alignment as wa


def fixture():
    context = {"mid_occ":50,"part_index":0,"records":[{"name":"t","length":8}]}
    values = [0,0,0,17,3,8,8,0,8,0,0,8,0,4294967294,5,7,8,8,13,0,0,0,0,0,0,0,0,"-0x1p+0"]
    paf = b"q\t8\t0\t8\t+\tt\t8\t0\t8\t8\t8\t13\ttp:A:P\tcm:i:3\ts1:i:8\ts2:i:5\trl:i:0\n"
    text = ("H\tcgat-chain-state\t1\t2.31-r1302\tasm10\t50\t0\t19\t19\n"
            "T\t0\tt\t8\nQ\tq\t8\t0\t10000\t1\nR\t"+
            "\t".join(map(str,values))+"\nP\t"+paf.decode()+"END\t1\n")
    return context,values,paf,text


class NativeChainStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.protocol = self.root/"native.stdout"

    def parse(self,text,**updates):
        context,_,paf,_ = fixture()
        self.protocol.write_text(text)
        args = dict(query_name="q",query_length=8,context=context,expected_paf=[paf])
        args.update(updates)
        return nst.parse_state(self.protocol,**args)

    def test_required_native_hash_score_and_prior_competition_are_preserved(self):
        _,_,_,text = fixture()
        report = self.parse(text)
        row = report["records"][0]
        self.assertEqual(row["native_hash"],4294967294)
        self.assertEqual((row["subscore"],row["subcount"],row["anchor_offset"]),(5,7,17))
        self.assertEqual((row["chain_score"],row["original_chain_score"]),(8,8))
        self.assertTrue(report["external_chain_paf_equal"])
        self.assertFalse(report["post_dp_state_certified"])
        self.assertFalse(report["mapq_reconstructed"])

    def test_missing_fields_corruption_foreign_query_and_mismatching_PAF_refuse(self):
        context,values,paf,text = fixture()
        record = "R\t"+"\t".join(map(str,values))+"\n"
        cases = [text.replace(record,"R\t"+"\t".join(map(str,values[:-1]))+"\n"),
                 text.replace("4294967294","4294967296"),text.replace("-0x1p+0","nan"),
                 text.replace("T\t0\tt\t8","T\t0\tother\t8"),text.replace("Q\tq","Q\tother"),
                 text.replace("END\t1\n",""),text+"garbage\n"]
        for bad in cases:
            with self.subTest(bad=bad[-50:]),self.assertRaises(wa.ExperimentError):
                self.parse(bad)
        with self.assertRaisesRegex(wa.ExperimentError,"differs from"):
            self.parse(text,expected_paf=[paf.replace(b"s1:i:8",b"s1:i:9")])
        with self.assertRaisesRegex(wa.ExperimentError,"count differs"):
            self.parse(text,expected_paf=[])

    def test_empty_query_state_is_explicit_not_fictitious_alignment(self):
        context,_,_,_ = fixture()
        text = "H\tcgat-chain-state\t1\t2.31-r1302\tasm10\t50\t0\t19\t19\nT\t0\tt\t8\nQ\tq\t8\t3\t10000\t0\nEND\t0\n"
        report = self.parse(text,expected_paf=[])
        self.assertEqual(report["records"],[])
        self.assertEqual(report["repetitive_length"],3)
        self.assertFalse(report["production_ready"])

    def test_trace_requires_matching_complete_scope_and_does_not_claim_ownership(self):
        trace = self.root/"trace.stderr"
        good = b"QR\tq\t0\t8\nCN\t0\tt\t2\t+\t2\t2\t0\nQT\tq\t0\t0.1\n"
        trace.write_bytes(good)
        report = nst.trace_receipt(trace,"q",8)
        self.assertTrue(report["query_end_observed"])
        self.assertFalse(report["anchor_ownership_validated"])
        for bad in (good.replace(b"QT\tq",b"QT\tother"),good.split(b"QT")[0],
                    good+b"CN\t0\tt\t2\t+\t2\t2\t0\n"):
            trace.write_bytes(bad)
            with self.assertRaises(wa.ExperimentError):
                nst.trace_receipt(trace,"q",8)

    def bundle(self):
        bundle = self.root/"bundle"
        bundle.mkdir()
        binary = bundle/build.BINARY
        binary.write_bytes(b"mock executable identity ONLY; never run")
        binary.chmod(0o755)
        manifest = {"schema":1,"status":"built_unvalidated","protocol":1,"version":build.VERSION,
            "preset":"asm10","upstream_commit":build.UPSTREAM_COMMIT,"binary":build.BINARY,
            "platform":"fixture-platform","binary_sha256":wa.sha256(binary),
            "helper_source_sha256":wa.sha256(Path(nst.__file__).with_suffix(".c")),
            "source_files_sha256":{k.removesuffix("_sha256"):v for k,v in ps.UPSTREAM.items() if k != "version"}}
        (bundle/build.MANIFEST).write_text(json.dumps(manifest))
        return bundle,binary,manifest

    def test_bundle_binding_is_automatic_and_no_compiler_or_helper_is_started(self):
        bundle,binary,manifest = self.bundle()
        with patch.object(build,"host_platform",return_value="fixture-platform"), \
             patch.object(build,"default_bundle",return_value=bundle), \
             patch.object(build.subprocess,"run",side_effect=AssertionError("no execution during validation")):
            report = nst.validate_bundle()
            self.assertEqual(report["sha256"],manifest["binary_sha256"])
            binary.write_bytes(b"changed")
            with self.assertRaises(wa.ExperimentError):
                nst.validate_bundle()
        with self.assertRaisesRegex(wa.ExperimentError,"maintainer"):
            nst.validate_bundle(self.root/"missing")

    def test_bundled_static_zlib_license_is_bound_and_cannot_be_omitted(self):
        bundle,binary,manifest = self.bundle()
        license_path = bundle/"ZLIB_LICENSE_AND_HEADER.txt"
        license_path.write_text("fixture license only\n")
        manifest["third_party_licenses_sha256"] = {license_path.name:wa.sha256(license_path)}
        wa.write_json(bundle/build.MANIFEST,manifest)
        with patch.object(build,"host_platform",return_value="fixture-platform"):
            report = nst.validate_bundle(bundle)
            self.assertEqual(report["third_party_licenses_sha256"],manifest["third_party_licenses_sha256"])
            license_path.write_text("changed license\n")
            with self.assertRaisesRegex(wa.ExperimentError,"license"):
                nst.validate_bundle(bundle)

    def test_foreign_license_path_is_rejected_not_followed(self):
        bundle,binary,manifest = self.bundle()
        manifest["third_party_licenses_sha256"] = {"../foreign.txt":"0"*64}
        wa.write_json(bundle/build.MANIFEST,manifest)
        with patch.object(build,"host_platform",return_value="fixture-platform"),self.assertRaisesRegex(wa.ExperimentError,"license"):
            nst.validate_bundle(bundle)

    def test_builder_default_is_plan_only_even_without_source_checkout(self):
        output = self.root/"not-created"
        with patch("sys.argv",["build","--source",str(self.root/"absent"),"--out",str(output)]), \
             patch.object(build,"build",side_effect=AssertionError("no build")), \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(build.main(),0)
        self.assertEqual(json.loads(stdout.getvalue())["status"],"plan_only")
        self.assertFalse(output.exists())

    def test_child_file_limit_keeps_inherited_soft_and_hard_bounds(self):
        process = MagicMock()
        process.wait.return_value = 0
        observed = []
        def spawn(argv,**kwargs):
            kwargs["preexec_fn"]()  # Resource calls below are MOCKED, never applied.
            return process
        with patch.object(wa.subprocess,"Popen",side_effect=spawn), \
             patch.object(wa.resource,"getrlimit",return_value=(100,200)), \
             patch.object(wa.resource,"setrlimit",side_effect=lambda kind,value:observed.append((kind,value))):
            wa.run_command(["not-executed"],self.root,"limit",30,0,max_file_bytes=1000)
        self.assertIn((wa.resource.RLIMIT_FSIZE,(100,200)),observed)


if __name__ == "__main__":
    unittest.main()
