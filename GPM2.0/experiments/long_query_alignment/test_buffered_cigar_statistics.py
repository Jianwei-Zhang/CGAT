from __future__ import annotations
import random
import unittest
from windowed_alignment import CHUNK, NT, RC, Q_OPS, T_OPS, ExperimentError, Hit, FastaStore
import buffered_cigar_statistics as fast

def scalar_reference(hit: Hit, query: FastaStore, target: FastaStore) -> tuple[int, int, int]:
    """Check =/X against original bases and recompute stats, excluding ambiguity.

    Mapping quality, chaining scores and primary/secondary labels CANNOT be
    inherited after windowing. Those are deliberately absent/unknown in output.
    """
    q, t = 0, hit.ts
    matches = block = ambiguous = 0
    for size, op in hit.ops:
        for offset in range(0, size, CHUNK):
            n = min(CHUNK, size - offset)
            qb = tb = b""
            if op in Q_OPS:
                if hit.strand == "+":
                    qb = query.fetch(hit.query, hit.qs + q + offset, hit.qs + q + offset + n).translate(NT)
                else:
                    qb = query.fetch(hit.query, hit.qe - q - offset - n, hit.qe - q - offset).translate(NT).translate(RC)[::-1]
            if op in T_OPS:
                tb = target.fetch(hit.target, t + offset, t + offset + n).translate(NT)
            if op == "=":
                if qb != tb:
                    raise ExperimentError("= operation disagrees with original input bases")
                amb = qb.count(b"N")
                matches += n - amb
            elif op == "X":
                if any(a == b for a, b in zip(qb, tb)):
                    raise ExperimentError("X operation disagrees with original input bases")
                amb = qb.count(b"N") + tb.count(b"N")  # Both N would violate X.
            else:
                amb = (qb if op == "I" else tb).count(b"N")
            ambiguous += amb
            block += n - amb
        q += size if op in Q_OPS else 0
        t += size if op in T_OPS else 0
    return matches, block, ambiguous

class Store:
    def __init__(self, sequence):
        self.sequence=sequence; self.calls=0; self.maximum=0
    def fetch(self,name,start,end):
        if not 0<=start<=end<=len(self.sequence):raise ExperimentError("invalid sequence interval")
        self.calls+=1;self.maximum=max(self.maximum,end-start)
        return self.sequence[start:end]

class BufferedStatisticsTests(unittest.TestCase):
    def case(self, rng, strand):
        ops=[];q=[];t=[]
        for _ in range(rng.randrange(1,40)):
            op=rng.choice("=XID");size=rng.randrange(1,12);ops.append((size,op))
            for _ in range(size):
                if op=="=":
                    base=rng.choice(b"ACGTNRY");q.append(base);t.append(base)
                elif op=="X":
                    a=rng.choice(b"ACGTNRY");b=rng.choice(b"ACGTNRY")
                    while bytes([a]).translate(NT)==bytes([b]).translate(NT):b=rng.choice(b"ACGTNRY")
                    q.append(a);t.append(b)
                elif op=="I":q.append(rng.choice(b"ACGTNRY"))
                else:t.append(rng.choice(b"ACGTNRY"))
        qseq=bytes(q);tseq=bytes(t)
        if strand=="-":qseq=qseq.translate(RC)[::-1]
        hit=Hit("q",len(qseq)+6,3,len(qseq)+3,strand,"t",len(tseq)+14,7,len(tseq)+7,0,0,60,tuple(ops))
        return hit,Store(b"GGG"+qseq+b"TTT"),Store(b"AAAAAAA"+tseq+b"CCCCCCC")

    def test_random_both_strands_indels_ambiguity_and_buffer_edges_match_scalar(self):
        rng=random.Random(20261116)
        for strand in "+-":
            for _ in range(300):
                hit,q,t=self.case(rng,strand);expected=scalar_reference(hit,q,t)
                for size in (1,2,7,31,CHUNK):
                    q.calls=t.calls=q.maximum=t.maximum=0
                    self.assertEqual(fast.checked_statistics(hit,q,t,buffer_bytes=size),expected)
                    self.assertLessEqual(max(q.maximum,t.maximum),size)

    def test_dense_cigar_does_not_issue_per_operation_source_reads(self):
        q=Store(b"AC"*10000);t=Store(b"AG"*10000)
        hit=Hit("q",20000,0,20000,"+","t",20000,0,20000,0,0,60,((1,"="),(1,"X"))*10000)
        expected=scalar_reference(hit,q,t);self.assertEqual(q.calls,20000)
        q.calls=t.calls=0
        self.assertEqual(fast.checked_statistics(hit,q,t,buffer_bytes=1024),expected)
        self.assertEqual(q.calls,20);self.assertEqual(t.calls,20)

    def test_invalid_equal_and_mismatch_are_not_hidden_at_buffer_edges(self):
        for op,qbytes,tbytes in (("=",b"AAAAAA",b"AAAATA"),("X",b"AAAAAA",b"TTTTAT")):
            hit=Hit("q",6,0,6,"+","t",6,0,6,0,0,60,((6,op),))
            for fn in (scalar_reference,lambda h,q,t:fast.checked_statistics(h,q,t,buffer_bytes=2)):
                with self.assertRaises(ExperimentError):fn(hit,Store(qbytes),Store(tbytes))

    def test_overlong_logical_operation_is_checked_with_bounded_reads(self):
        length = (1 << 28) + 12
        class PatternStore:
            def __init__(self, letter):self.letter=letter;self.maximum=0
            def fetch(self,name,start,end):
                if not 0<=start<=end<=length:raise ExperimentError("invalid sequence interval")
                self.maximum=max(self.maximum,end-start)
                return self.letter*(end-start)
        for strand in "+-":
            q=PatternStore(b"A" if strand=="+" else b"T");t=PatternStore(b"A")
            hit=Hit("q",length,0,length,strand,"t",length,0,length,0,0,255,(((1<<28)-1,"="),(13,"=")))
            self.assertEqual(fast.checked_statistics(hit,q,t),(length,length,0))
            self.assertLessEqual(max(q.maximum,t.maximum),fast.MAX_BUFFER_BYTES)

    def test_invalid_buffer_and_short_source_are_rejected(self):
        hit=Hit("q",2,0,2,"+","t",2,0,2,0,0,60,((2,"="),))
        for size in (0,-1,True,CHUNK+1):
            with self.assertRaises(ExperimentError):fast.checked_statistics(hit,Store(b"AA"),Store(b"AA"),buffer_bytes=size)
        class Short(Store):
            def fetch(self,*args):return b""
        with self.assertRaises(ExperimentError):fast.checked_statistics(hit,Short(b"AA"),Store(b"AA"))

if __name__=="__main__":unittest.main()
