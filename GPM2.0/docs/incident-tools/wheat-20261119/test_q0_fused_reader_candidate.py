import unittest
from bench_q0_fused_reader import old
from q0_fused_reader_candidate import parsed,names,prefix
from lgz_core.q0_sources import Q0EvidenceError

class A(unittest.TestCase):
    r='哈/"C\\G.paf'; qs=names({'a':16}); ts=names({'b':18})
    def make(self,cg,q=8,t=9,strand='-'):
        return f'a\t16\t0\t{q}\t{strand}\tb\t18\t1\t{1+t}\t1\t12\t255\txx:Z:α\tcg:Z:{cg}\tzz:i:02\r\n'
    def compare(self,line,ok):
        for v in (2,150):
            calls=(lambda:old(line,self.r,v,self.qs,self.ts),lambda:parsed(line,self.r,v,prefix(self.r),self.qs,self.ts))
            if ok:self.assertEqual(calls[0](),calls[1]())
            else:
                for fn in calls:
                    with self.assertRaises(ValueError):fn()
    def test_good(self):
        for strand in ('+','-'):
            for c,q,t in [('4M',4,4),('3=1X',4,4),('2M3I4D1N1=2X',8,10)]:self.compare(self.make(c,q,t,strand),True)
    def test_bad(self):
        for c in ['0M','01M','2M*','M2','5S','２M','8M','4M\tcg:Z:4M','']:
            self.compare(self.make(c,4,4),False)
        self.compare(self.make('4M',4,4).replace('a\t16','a\t99'),False); self.compare(self.make('4M',4,4).replace('a\t16','z\t16'),False)
    def test_short_cache_still_checks_each_span(self):
        self.compare(self.make('4M',4,4),True);self.compare(self.make('4M',3,4),False)
    def test_wide(self):
        n=2**40;r=self.r; line=f'a\t{n}\t0\t{n}\t+\tb\t{n}\t0\t{n}\t1\t{n}\t60\tcg:Z:{n}M'; q,t=names({'a':n}),names({'b':n});self.assertEqual(old(line,r,1,q,t),parsed(line,r,1,prefix(r),q,t))
