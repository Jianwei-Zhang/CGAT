import random
import unittest
from unittest.mock import patch

from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_sources import SourceKey, split_source
from bench_q0_source_screen_pool import adm, measure, source_packets


class ReferenceLanesTests(unittest.TestCase):
    def fixture(self):
        seqs, parts, refs = {}, {}, {}
        for i in (3, 0, 1, 2):
            key = SourceKey('set', str(i)); dna = ''.join(random.Random(i).choices('ACGT', k=600))
            seqs[key] = dna if i != 2 else dna[:200]+'N'*200+dna[400:]
            for part in split_source(key, seqs[key]).segments:
                parts[part.segment_id] = part
            strand = '+' if i % 2 == 0 else '-'
            for j in range(2 if i == 2 else 0 if i == 3 else 1):
                raw = '\t'.join(map(str, [str(i),600,0,600,strand,'chr'+str(j),6000,1000*i,1000*i+600,600,600,60,'cg:Z:600M']))
                refs.setdefault(key, []).append(parse_paf_line(raw,artifact='ref.paf',line_number=1+2*i+j))
        return adm.EvidenceInput(seqs,parts,{'chr0':6000,'chr1':6000},refs,(),(),{},'fixture')

    def test_remote_worker_and_owner_preserve_serial_decision_and_request(self):
        data = self.fixture()
        baseline, _ = measure(data, [], 1)
        other, info = measure(data, [], 2)
        self.assertGreater(info['offloaded_sources'], 0)
        self.assertEqual(other, baseline)
        self.assertEqual(sum(len(p[3]) for p in source_packets(data)), len(data.parts))

    def test_incomplete_screen_is_not_a_success(self):
        from bench_q0_source_screen_pool import parallel_selection
        data = self.fixture()
        with patch('bench_q0_source_screen_pool.source_packets', return_value=[]), self.assertRaisesRegex(ValueError, 'incomplete'):
            parallel_selection(data, 2)
