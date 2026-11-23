from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bench_q0_indexed_screen_batch import checked_path, choose, fetch_dna


class IndexedBatchTests(unittest.TestCase):
    def test_source_selection_does_not_use_hits_or_input_order(self):
        rows={f'ctg{i:03d}':(1_000_000+i,) for i in reversed(range(48))}
        rows.update(low=(999999,), high=(2_400_001,))
        self.assertEqual(choose(rows), [f'ctg{i:03d}' for i in range(1,48,3)])
        with self.assertRaisesRegex(ValueError,'insufficient'): choose({'only':(1_000_000,)})

    def test_read_only_indexed_extent_preserves_case_and_line_break_handling(self):
        self.assertEqual(fetch_dna(BytesIO(b'>r\r\nAcG\r\nTac\r\n'), (5,4,3,5)),('AcGTa',7))
        for row in ((6,4,3,6),(6,-1,3,4),(7,4,3,4)):
            with self.subTest(row=row), self.assertRaises(ValueError): fetch_dna(BytesIO(b'>r\nA'),row)

    def test_source_reader_does_not_follow_aliases(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'raw').write_bytes(b''); (root/'other').symlink_to(root/'raw')
            for name in ('other', '../raw', '/raw'):
                with self.assertRaises(ValueError): checked_path(root,name)
