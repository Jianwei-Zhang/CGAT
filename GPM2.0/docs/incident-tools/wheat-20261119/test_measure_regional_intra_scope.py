import unittest

from measure_regional_intra_scope import scope, summarize


def w(segment, end=10):
    return {'window_id':segment, 'segment_id':segment, 'start':0, 'end':end, 'segment_length':10}


class IntraScopeTests(unittest.TestCase):
    def setUp(self):
        self.lookup = {k:{'dataset':dataset, 'sequence_sha256':k*64, 'length':10}
                       for k,dataset in [('a','one'),('b','one'),('c','two')]}

    def make(self, targets):
        return {'query':w('a'), 'targets':targets,
                'members':[[k,k*64] for k in sorted({'a',*(t['segment_id'] for t in targets)})]}

    def test_mixed_even_if_one_cross_base(self):
        cases = [(self.make([w('b')]),'intra_only'),(self.make([w('c')]),'cross_only'),
                 (self.make([w('b'),w('c',1)]),'mixed')]
        rows = []
        for ctx,want in cases:
            result = scope(ctx,self.lookup)
            self.assertEqual(result['scope'],want)
            rows.append({**result,'native_cpu_s':50,'native_wall_s':45,'raw_receipt':want,'flags':[]})
        summary=summarize(rows)
        self.assertEqual(summary['window_scopes'],{'intra_only':1,'cross_only':1,'mixed':1})
        self.assertEqual(summary['target_bp'],{'intra':20,'cross':11})
        self.assertEqual([r['scope'] for r in summary['slowest_mixed_majority_intra_by_target_bp']],['mixed'])

    def test_incomplete_members_or_same_contig_are_not_scientific_proof(self):
        cases=[self.make([w('a')]),self.make([w('b'),w('b')]),{**self.make([w('c')]),'members':[]}]
        for case in cases:
            with self.assertRaises(ValueError):
                scope(case,self.lookup)


if __name__ == '__main__':
    unittest.main()
