"""Same strict reader under both modern and frozen legacy outer runtimes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import sys

from server.tools.lgz_core.q0_paf_io import open_paf_text, install_legacy_paf_reader
from server.tools.run_orchestration import open_paf_text as outer_reader


class Q0PafIOTests(unittest.TestCase):
    def test_byte_decoder_and_newline_semantics_match_outer_reader(self):
        with TemporaryDirectory() as d:
            path=Path(d)/"rows.paf"
            for payload in (b"", b"a\r\nb\rc\n", "查询\t目标\r\n".encode(),
                            b"x"*(1024*1024+3)+b"\nlast"):
                path.write_bytes(payload)
                for newline in (None, "", "\n"):
                    with open_paf_text(path,newline=newline) as a, outer_reader(path,newline=newline) as b:
                        self.assertEqual(list(a),list(b))
                    self.assertTrue(a.closed)

    def test_compatibility_adds_only_absent_api_to_authentic_module(self):
        outer=SimpleNamespace(__file__='/frozen/run_orchestration.py', validate_paf=object())
        original=dict(vars(outer))
        with patch.dict(sys.modules, {'run_orchestration':outer}):
            install_legacy_paf_reader()
            self.assertEqual({k:v for k,v in vars(outer).items() if k!='open_paf_text'},original)
            self.assertIs(outer.open_paf_text,open_paf_text)
            present=object();outer.open_paf_text=present
            install_legacy_paf_reader()
            self.assertIs(outer.open_paf_text,present)

    def test_invalid_utf8_fails_not_replaced(self):
        with TemporaryDirectory() as d:
            path=Path(d)/"rows.paf";path.write_bytes(b"valid\n\xff")
            for reader in (open_paf_text,outer_reader):
                with self.assertRaises(UnicodeDecodeError):
                    with reader(path) as stream:list(stream)


if __name__ == '__main__':unittest.main()
