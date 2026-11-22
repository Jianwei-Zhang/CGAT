import tempfile
import unittest
from pathlib import Path
from unittest import mock

from server.tools.lgz_core import common


class FastaWriterTests(unittest.TestCase):
    def test_batched_writer_preserves_original_bytes_on_boundaries(self):
        for length in (0, 1, 79, 80, 81, 81919, 81920, 81921, 163881):
            with self.subTest(length=length), tempfile.TemporaryDirectory() as directory:
                source = ('actgNΩ\n' * (length // 7 + 1))[:length]
                records = [('one with spaces', source), ('other', 'G')]
                expected = '\n'.join(line for name, seq in records
                                     for line in ['>' + name, *(seq[i:i+80] for i in range(0,len(seq),80))]) + '\n'
                path = Path(directory)/'nested'/'result.fa'
                common.write_fasta(path, iter(records))
                self.assertEqual(path.read_bytes(), expected.encode('utf-8'))

    def test_output_writes_are_bounded_and_do_not_buffer_the_entire_contig(self):
        writer = mock.mock_open()
        path = Path('mock-location')/'out.fa'
        with mock.patch.object(Path, 'mkdir'), mock.patch.object(Path, 'open', writer):
            common.write_fasta(path, [('ctg', 'N'*250_000)])
        blocks = [call.args[0] for call in writer().write.call_args_list]
        self.assertEqual(blocks[0], '>ctg\n')
        self.assertEqual(len(blocks), 5)  # header + four bounded blocks
        self.assertTrue(all(0 < len(block) <= 81*1024 and block.endswith('\n') for block in blocks[1:]))
        self.assertEqual(sum(block.count('N') for block in blocks[1:]), 250_000)


if __name__ == '__main__':
    unittest.main()
