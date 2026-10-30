"""Maintainer artifact portability checks; no customer compiler/configuration."""
from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_native_chain_state as build
import windowed_alignment as wa


class CompanionPortabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def files(self,root,names):
        for name in names:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"fixture only")

    def test_default_build_retains_dynamic_zlib_without_touching_a_sysroot(self):
        flags,cppflags,libraries,dependencies=build.portable_options(argparse.Namespace())
        self.assertIn("-std=gnu17",flags)
        self.assertEqual(cppflags,["-DHAVE_KALLOC"])
        self.assertEqual(libraries,["-lz"])
        self.assertEqual(dependencies,{})

    def test_explicit_old_sysroot_and_static_zlib_are_hash_bound(self):
        sysroot,zlib=self.root/"old sysroot",self.root/"static zlib"
        self.files(sysroot,["usr/include/features.h","usr/lib64/Scrt1.o","lib64/libc.so.6"])
        self.files(zlib,["include/zlib.h","include/zconf.h","lib/libz.a"])
        args=argparse.Namespace(sysroot=sysroot,zlib_prefix=zlib)
        flags,cppflags,libraries,dependencies=build.portable_options(args)
        self.assertIn("--sysroot="+str(sysroot),flags)
        self.assertIn("-B"+str(sysroot/"usr/lib64")+"/",flags)
        self.assertIn("-I"+str(zlib/"include"),cppflags)
        self.assertEqual(libraries,[str(zlib/"lib/libz.a")])
        self.assertEqual(dependencies["sysroot_features_sha256"],wa.sha256(sysroot/"usr/include/features.h"))
        self.assertEqual(set(dependencies["static_zlib_files_sha256"]),{"include/zlib.h","include/zconf.h","lib/libz.a"})

    def test_incomplete_sysroot_or_zlib_is_refused_before_build(self):
        for args in (argparse.Namespace(sysroot=self.root/"missing"),argparse.Namespace(zlib_prefix=self.root/"missing")):
            with self.subTest(args=args),self.assertRaises(wa.ExperimentError):
                build.portable_options(args)

    def inspect(self,symbols,dynamic,*,legacy=True):
        with patch.object(build.shutil,"which",return_value="mock-readelf"), \
             patch.object(build.subprocess,"check_output",side_effect=[symbols,dynamic]):
            return build.inspect_elf(self.root/"mock-binary",legacy=legacy)

    def test_old_abi_is_measured_from_binary_not_host_distribution(self):
        dynamic=" 0x1 (NEEDED) Shared library: [libm.so.6]\n 0x1 (NEEDED) Shared library: [libc.so.6]\n"
        report=self.inspect("foo@GLIBC_2.2.5 bar@GLIBC_2.14",dynamic)
        self.assertEqual(report["maximum_glibc"],"2.14")
        self.assertEqual(report["needed_libraries"],["libm.so.6","libc.so.6"])
        self.assertTrue(report["legacy_2_17_checked"])
        self.assertEqual(report["runtime_paths"],[])

    def test_new_abi_no_symbol_receipt_or_embedded_build_path_cannot_claim_legacy(self):
        cases=[("foo@GLIBC_2.34",""),("no version information",""),
               ("foo@GLIBC_2.14 bar@GLIBC_ABI_DT_RELR",""),
               ("foo@GLIBC_2.14"," 0x1 (NEEDED) Shared library: [libunbundled.so.1]"),
               ("foo@GLIBC_2.14"," 0x1 (RPATH) Library rpath: [/developer/build/lib]"),
               ("foo@GLIBC_2.14"," 0x1 (RUNPATH) Library runpath: [/developer/build/lib]")]
        for symbols,dynamic in cases:
            with self.subTest(symbols=symbols,dynamic=dynamic),self.assertRaisesRegex(wa.ExperimentError,"glibc 2.17"):
                self.inspect(symbols,dynamic)

    def test_missing_maintainer_inspector_does_not_relax_portability_check(self):
        with patch.object(build.shutil,"which",return_value=None),self.assertRaisesRegex(wa.ExperimentError,"inspector"):
            build.inspect_elf(self.root/"mock")


if __name__=="__main__":
    unittest.main()
