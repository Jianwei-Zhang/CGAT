import random,unittest
from wheat_split_first_indexed_readonly import OverlapIndex,indexed_barriers,original
from test_wheat_continuous_dominant_admission import anchor,Interval

class IndexedOverlapTests(unittest.TestCase):
    def test_random_union_overlap_exact(self):
        rng=random.Random(1307)
        for _ in range(400):
            rows=[Interval((a:=rng.randrange(1000)),a+rng.randrange(1,250)) for _ in range(rng.randrange(30))]
            queries=[Interval((a:=rng.randrange(1100)),a+rng.randrange(1,200)) for _ in range(rng.randrange(20))]
            self.assertEqual(OverlapIndex(rows).overlap(queries),original.legacy.overlap_bp(rows,queries))
    def test_all_barrier_audit_fields_equal(self):
        rng=random.Random(32);fast,_=indexed_barriers()
        for _ in range(40):
            groups={('1A','+'):[],('1B','+'):[],('1D','-'):[]}
            for i in range(40):
                key=rng.choice(list(groups));lo=i*50000;hi=lo+rng.randrange(100,49000)
                groups[key].append(anchor(lo,hi,lo if key[1]=='+' else 3000000-hi))
            high={k:tuple(a.source for a in rows if rng.random()>.2) for k,rows in groups.items()}
            main=original.chain(groups['1A','+'],'+')
            self.assertEqual(fast(groups,high,('1A','+'),main,2000000),original.foreign_barriers(groups,high,('1A','+'),main,2000000))

if __name__=='__main__':unittest.main()
