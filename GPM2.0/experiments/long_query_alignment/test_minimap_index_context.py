"""Deferred MMI2 format/partition checks; never run during implementation."""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

import minimap_index_context as mic


def index_part(records, *, flags=0, bucket_bits=0, payload=True):
    raw = bytearray(mic.MAGIC+struct.pack("<IIIII",19,19,bucket_bits,len(records),flags))
    for name,length in records:
        value = name.encode("ascii")
        raw += bytes([len(value)])+value+struct.pack("<I",length)
    for _ in range(1<<bucket_bits):
        # One position and one hash entry exercise both payload skip lengths.
        raw += struct.pack("<I",1)+b"p"*8+struct.pack("<I",1)+b"h"*16
    if payload:
        raw += b"s"*(4*((sum(length for _,length in records)+7)//8))
    return bytes(raw)


class MinimapIndexContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root/"reference.mmi"
        self.first = index_part([("chr1",8),("chr2",9)])
        self.second = index_part([("chr3",12)])
        self.path.write_bytes(self.first+self.second)
        self.records = {"chr1":{"length":8},"chr2":{"length":9},"chr3":{"length":12}}

    def test_reads_original_extents_order_and_membership_without_payload_decoding(self):
        result = mic.read_catalog(self.path,self.records)
        self.assertEqual(len(result["parts"]),2)
        self.assertEqual([(p["start"],p["end"]) for p in result["parts"]],
                         [(0,len(self.first)),(len(self.first),len(self.first)+len(self.second))])
        self.assertEqual([p["records"] for p in result["parts"]],
                         [[{"name":"chr1","length":8},{"name":"chr2","length":9}],
                          [{"name":"chr3","length":12}]])
        self.assertFalse(result["partition_boundaries_guessed"])

    def test_copies_original_serialized_parts_exactly_and_hashes_complete_source(self):
        output = self.root/"parts"
        result = mic.copy_parts(self.path,output,self.records)
        self.assertEqual(Path(result["parts"][0]["path"]).read_bytes(),self.first)
        self.assertEqual(Path(result["parts"][1]["path"]).read_bytes(),self.second)
        self.assertEqual(result["sha256"],hashlib.sha256(self.first+self.second).hexdigest())
        self.assertFalse(result["global_mapq_restored"])
        with self.assertRaises(FileExistsError):
            mic.copy_parts(self.path,output,self.records)

    def test_single_part_reuses_original_file_without_copy(self):
        self.path.write_bytes(self.first)
        records = {r["name"]: {"length": r["length"]}
                   for r in mic.read_catalog(self.path)["parts"][0]["records"]}
        output = self.root / "no-copy"
        result = mic.copy_parts(self.path, output, records, reuse_single_part=True)
        self.assertTrue(result["single_part_file_reused"])
        self.assertFalse(output.exists())
        self.assertEqual(result["parts"][0]["path"], str(self.path.resolve()))
        self.assertEqual(result["sha256"], hashlib.sha256(self.first).hexdigest())

    def test_multi_part_opt_in_still_preserves_each_exact_part(self):
        result = mic.copy_parts(self.path, self.root / "split", self.records, reuse_single_part=True)
        self.assertEqual(Path(result["parts"][0]["path"]).read_bytes(), self.first)
        self.assertEqual(Path(result["parts"][1]["path"]).read_bytes(), self.second)
        self.assertNotIn("single_part_file_reused", result)

    def test_truncation_unknown_flags_magic_and_duplicate_names_fail_closed(self):
        for raw in (self.first[:-1],self.first+self.second[:-2],b"other",self.first+b"junk",
                    index_part([("chr1",8)],flags=2,payload=False),
                    self.first+index_part([("chr1",4)])):
            with self.subTest(size=len(raw)),self.assertRaises(mic.IndexContextError):
                self.path.write_bytes(raw)
                mic.read_catalog(self.path)

    def test_reference_order_names_lengths_and_header_limits_are_checked(self):
        for records in ({"chr2":{"length":9},"chr1":{"length":8},"chr3":{"length":12}},
                        {"chr1":{"length":8},"chr2":{"length":10},"chr3":{"length":12}}):
            with self.assertRaisesRegex(mic.IndexContextError,"order differ"):
                mic.read_catalog(self.path,records)
        self.path.write_bytes(mic.MAGIC+struct.pack("<IIIII",19,19,31,1,0))
        with self.assertRaisesRegex(mic.IndexContextError,"header"):
            mic.read_catalog(self.path)

    def test_context_requires_one_part_and_exact_reference_tool_preset_and_hash(self):
        result = mic.copy_parts(self.path,self.root/"parts",self.records)
        context = {**result["parts"][0],"reference_sha256":"a"*64,"tool_sha256":"b"*64,"preset":"asm10","mid_occ":500}
        kwargs = dict(reference_sha256="a"*64,tool_sha256="b"*64,preset="asm10",target_records=self.records)
        self.assertEqual(mic.validate_part_context(context,**kwargs),Path(context["path"]))
        for changed in ({**context,"sha256":"0"*64},{**context,"preset":"asm5"},
                        {**context,"path":str(self.path)}):
            with self.subTest(changed=changed),self.assertRaises(mic.IndexContextError):
                mic.validate_part_context(changed,**kwargs)


if __name__ == "__main__":
    unittest.main()
