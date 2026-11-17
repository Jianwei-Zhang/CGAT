"""Unbounded-by-file-size metadata, bounded reader buffers and exact validation."""
import hashlib
import json
import os
from pathlib import Path
import random
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

import metadata_json as mj
import proactive_resume as pr
import recovery_publication as rp
import windowed_alignment as wa


class MetadataJsonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "state.json"

    def write(self, value):
        self.path.write_text(json.dumps(value, ensure_ascii=True))

    def test_stdlib_parity_at_every_small_chunk_boundary(self):
        value = {"keys": [None, True, False, 0, -12, .002, 3e25, {}, [], {"unicode": "小麦😀"}],
                 "escapes": ['a"b', "a\\b", "a\nb", "", "\t\r\b\f"], "arr": list(range(30))}
        self.write(value)
        for size in range(1, 37):
            with self.subTest(size=size), patch.object(mj, "CHUNK", size):
                self.assertEqual(mj.load(self.path), value)
                mj.compare(self.path, value)

    def test_random_nested_json_matches_stdlib(self):
        rng = random.Random(19)
        def generate(depth):
            if depth > 3 or rng.random() < .4:
                return rng.choice([None, True, False, rng.randint(-100000, 100000), rng.random(), 'x\\"小麦' * rng.randrange(10)])
            if rng.random() < .5:return [generate(depth + 1) for _ in range(rng.randrange(6))]
            return {str(i): generate(depth + 1) for i in range(rng.randrange(6))}
        with patch.object(mj, "CHUNK", 31):
            for _ in range(100):
                value = {"state": generate(0)}; self.write(value)
                self.assertEqual(mj.load(self.path), value); mj.compare(self.path, value)

    def test_growth_past_both_old_limits_is_not_a_resume_or_publication_veto(self):
        # 65 MiB of valid whitespace is consumed in chunks, not retained as raw bytes.
        with self.path.open("w") as stream:
            stream.write('{"identity":{"input":"verified"},"records":[1,2]')
            for _ in range(65):stream.write(" " * 1024**2)
            stream.write("}")
        expected = {"identity": {"input": "verified"}, "records": [1, 2]}
        tracemalloc.start()
        try:
            self.assertEqual(rp.read_json(self.path, self.root), expected)
            self.assertEqual(pr.read_json(self.path), expected)
            rp.compare_json(self.path, self.root, expected)
            _, peak = tracemalloc.get_traced_memory()
        finally:tracemalloc.stop()
        self.assertLess(peak, 2 * 1024**2)

    def test_dense_array_comparison_and_selected_fields_do_not_build_second_tree(self):
        with self.path.open("w") as stream:
            stream.write('{"identity":{"input":"same"},"records":[')
            stream.write(','.join(['123'] * 100000)); stream.write(']}')
        expected = {"identity": {"input": "same"}, "records": [123] * 100000}
        tracemalloc.start()
        try:
            mj.compare(self.path, expected)
            self.assertEqual(pr.read_json(self.path, fields={"identity"}), {"identity": {"input": "same"}})
            _, peak = tracemalloc.get_traced_memory()
        finally:tracemalloc.stop()
        self.assertLess(peak, 2 * 1024**2)

    def test_large_record_list_not_only_whitespace_is_admitted(self):
        value = {"records": [{"name": "contig" + str(i), "length": i + 1} for i in range(30000)]}
        self.write(value)
        self.assertGreater(self.path.stat().st_size, 1024**2)
        self.assertEqual(rp.read_json(self.path, self.root), value)
        mj.compare(self.path, value)

    def test_syntax_truncation_extra_data_duplicate_keys_and_nonfinite_rejected(self):
        for raw in ['{"a":1', '{"a":1} {}', '{"a":1,"a":2}', '{"a":[1,]}', '{"a":}',
                    '{"a":01}', '{"a":1e}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}',
                    '{"a":"bad\n"}', '{"a":"bad\\q"}', '{"a":trueX}', '{"a":1,}', '']:
            with self.subTest(raw=raw):
                self.path.write_text(raw)
                with self.assertRaises(ValueError):mj.load(self.path)
                with self.assertRaises(ValueError):mj.load(self.path, fields=set())

    def test_comparison_rejects_missing_extra_changed_and_reordered_values(self):
        value = {"a": [1, 2], "b": {"ok": True}}; self.write(value)
        for other in ({"a": [2, 1], "b": {"ok": True}}, {"a": [1], "b": {"ok": True}},
                      {"a": [1, 2, 3], "b": {"ok": True}}, {"a": [1, 2]},
                      {**value, "c": 0}, {"a": [1, 2], "b": {"ok": 1}}):
            with self.subTest(other=other), self.assertRaises(mj.MetadataError):mj.compare(self.path, other)

    def test_long_unicode_strings_and_scalar_chunk_boundaries(self):
        value = {"name": '小麦\\"' * 50000, "values": [1e-29, -22, None]}; self.write(value)
        with patch.object(mj, "CHUNK", 97):
            self.assertEqual(mj.load(self.path), value); mj.compare(self.path, value)

    def test_wrong_container_invalid_utf8_and_deep_nesting(self):
        self.path.write_text('[]')
        with self.assertRaises(mj.MetadataError):mj.load(self.path)
        self.assertEqual(mj.load(self.path, expected_type=list), [])
        self.path.write_bytes(b'{"x":"\xff"}')
        with self.assertRaises(UnicodeError):mj.load(self.path)
        self.path.write_text('{"x":' + '[' * 140 + '0' + ']' * 140 + '}')
        with self.assertRaises(mj.MetadataError):mj.load(self.path)

    def test_private_file_checks_and_explicit_fixed_schema_budget(self):
        self.write({"a": 1})
        link = self.root / "link.json"; link.symlink_to(self.path)
        for path in (link, self.root):
            with self.assertRaises((mj.MetadataError, wa.ExperimentError)):
                pr.read_json(path)
        with self.assertRaises(wa.ExperimentError):rp.read_json(self.path, self.root, max_bytes=2)
        outside = self.root.parent / (self.root.name + ".json")
        outside.write_text('{}'); self.addCleanup(outside.unlink)
        with self.assertRaises(wa.ExperimentError):rp.read_json(outside, self.root)

    def test_source_digest_is_bound_to_selected_fields(self):
        self.write({"execution": {"command": ["minimap2"]}, "unselected": [1, 2]})
        digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertEqual(mj.load(self.path, fields={"execution"}, expected_sha256=digest),
                         {"execution": {"command": ["minimap2"]}})
        self.write({"execution": {"command": ["minimap2"]}, "unselected": [1, 3]})
        with self.assertRaisesRegex(mj.MetadataError, "digest differs"):
            mj.load(self.path, fields={"execution"}, expected_sha256=digest)

    def test_file_replacement_during_parse_is_rejected(self):
        self.write({"a": 1})
        finish = mj._Reader.finish
        def replace(reader):
            finish(reader)
            replacement = self.root / "replacement"; replacement.write_text('{"a":2}')
            replacement.replace(self.path)
        with patch.object(mj._Reader, "finish", replace), self.assertRaisesRegex(mj.MetadataError, "changed during"):
            mj.load(self.path)


if __name__ == "__main__":unittest.main()
