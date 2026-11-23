import gzip
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.tools.lgz_core import q0_retained_hits as packed
from server.tools.lgz_core.q0_alignments import read_paf
from server.tools.lgz_core.q0_sources import Q0EvidenceError


class RetainedReaderTests(unittest.TestCase):
    artifact = '路径/"\\pair.paf'

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.file = Path(tmp.name)/'records.paf'; self.cache = packed.retained_geometry_cache()
        self.lengths = {'q': 2**42, 't': 2**42, 'unused invalid': 7}

    def load(self, new):
        if new:
            names = packed.retained_names(self.lengths)
            return list(packed.read_retained_paf(self.file, artifact=self.artifact, query_names=names,
                                                 target_names=names, short_geometry=self.cache))
        return [packed.RetainedHit.from_validated(h, h.query_name, h.target_name) for h in
                read_paf(self.file, artifact=self.artifact, query_lengths=self.lengths, target_lengths=self.lengths)]

    def record(self, ops, strand='+'):
        q = sum(n for n, op in ops if op in 'MI=X'); t = sum(n for n, op in ops if op in 'MDN=X')
        cg = ''.join(str(n)+op for n,op in ops)
        return f'q\t{2**42}\t3\t{3+q}\t{strand}\tt\t{2**42}\t4\t{4+t}\t1\t{max(q,t)}\t255\txy:Z:α\tcg:Z:{cg}\tzz:i:02'

    def test_file_order_ids_tags_newlines_and_long_cigar_match_original(self):
        rng = random.Random(17); groups = [[(4,'M')],[(4,'M')],[(3,'M'),(2**38,'D'),(2,'X')],[(2,'I'),(3,'N'),(5,'=')]]
        groups.extend([[(1,'=')]+[(rng.randrange(1,130), rng.choice('MIDN=X')) for _ in range(n)] for n in (1,4,40,1500)])
        text = '\r\n#comment\r\n'+'\r'.join(self.record(g,s) for s in '+-' for g in groups)
        self.file.write_bytes(text.encode()); expected = self.load(False)
        with patch.object(packed,'parse_paf_line',side_effect=AssertionError('valid rows should be decoded once')):
            actual = self.load(True)
        self.assertEqual(actual,expected);self.assertEqual(actual[0].line_number,3)
        self.assertGreater(self.cache.cache_info().hits,0)
        for a,b in zip(actual,expected):
            self.assertEqual(a.cigar,b.cigar);self.assertEqual(list(a.aligned_blocks()),list(b.aligned_blocks()))

    def test_each_damaged_row_is_rejected_including_after_a_short_cache_hit(self):
        good=self.record([(4,'M')]); broken=[good.replace('cg:Z:4M','cg:Z:'+cg) for cg in ('','0M','04M','3M','2M!2M','４M','4S')]
        broken += [good+'\tcg:Z:4M',good.replace('q\t','unknown\t',1),good.replace('q\t','unused invalid\t',1),
                   good.replace('255\t','256\t'),good.replace('\t+\t','\t*\t'),good.replace('\t3\t7\t','\t3\t6\t'),
                   good.replace(str(2**42),str(2**42-1),1),good.replace('xy:Z:α\tcg:Z:4M','xy:Z:α')]
        for damaged in broken:
            self.file.write_bytes((good+'\n'+damaged+'\n').encode())
            with self.subTest(damaged=damaged):
                with self.assertRaises(Q0EvidenceError) as old:self.load(False)
                with self.assertRaises(Q0EvidenceError) as new:self.load(True)
                self.assertEqual(str(old.exception),str(new.exception))

    def test_native_stream_contract_for_empty_non_utf8_and_compressed_input(self):
        self.file.write_bytes(b'# no rows\n\n'); self.assertEqual(self.load(False),self.load(True))
        for raw in (b'\xff\xfe',gzip.compress(self.record([(1,'M')]).encode())):
            self.file.write_bytes(raw)
            for mode in (False,True):
                with self.assertRaises(Q0EvidenceError):self.load(mode)
