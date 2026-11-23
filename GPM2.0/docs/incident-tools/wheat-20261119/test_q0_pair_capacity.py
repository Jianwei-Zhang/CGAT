from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('c++'), 'C++ compiler required for diagnostic screen')
class PairCapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(temp.cleanup)
        cls.binary = Path(temp.name)/'screen'
        subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror',str(Path(__file__).with_name('q0_pair_capacity.cpp')),'-o',str(cls.binary)],check=True)

    def call(self, cases):
        text=''.join('Q\t'+q+'\n'+''.join('T\t'+t+'\n' for t in ts) for q,ts in cases)
        return subprocess.run([self.binary],input=text,text=True,capture_output=True,check=True).stdout.splitlines()

    def test_excludes_only_incapable_and_abstains_on_ambiguous_or_repetitive(self):
        self.assertEqual(self.call([('A'*300,['A'*99,'C'*240,'C'*120+'N'+'C'*110,'A'*240,'T'*240]),
                                    ('A'*99,['A'*900]),('A'*180+'N',['C'*150])]),
                         ['short','excluded','uncertain','possible','possible','short','uncertain'])

    def test_near_threshold_substitutions_indels_and_tile_boundaries_on_both_strands(self):
        r=random.Random(802); dna=lambda n: ''.join(r.choices('ACGT',k=n))
        complement=str.maketrans('ACGT','TGCA'); cases=[]
        for n in (100,101,119,120,198,199,200,201,398,399,400,601):
            for kind in ('mismatch','mixed'):
                for repeat in range(6):
                    text=dna(n); errors=set(r.sample(range(n),n//20)); left=[]; right=[]
                    for i,a in enumerate(text):
                        if i not in errors: left.append(a);right.append(a);continue
                        e=i%3 if kind=='mixed' else 0
                        if e!=2: left.append(a)
                        if e!=1: right.append('ACGT'[('ACGT'.index(a)+1)%4])
                    # The contract is 100 paired columns, not merely 100 columns including gaps.
                    paired=n-sum(1 for i in errors if kind=='mixed' and i%3!=0)
                    extra=dna(max(0,100-paired)); left.append(extra); right.append(extra)
                    query=dna(195+repeat)+''.join(left)+dna(200); target=dna(198+repeat)+''.join(right)+dna(250)
                    cases.append((query,[target,target.translate(complement)[::-1]]))
        self.assertEqual(self.call(cases),['possible']*(2*len(cases)))

    def test_many_shared_short_motifs_do_not_imply_a_local_full_length_match(self):
        # 16 bp of real agreement in each separate island is insufficient to pass the 8-mer bound.
        r=random.Random(94); seeds=[''.join(r.choices('ACGT',k=19)) for _ in range(4)]
        q=('C'*800).join(seeds); t=('A'*900).join(seeds)
        self.assertEqual(self.call([(q,[t])]),['excluded'])

    def test_pigeonhole_constants_for_every_relevant_chunk_size(self):
        for k, floor in [(8,53),(16,5)]:
            self.assertEqual(min(n-k*(n//20)-(k-1) for n in range(100,200)),floor)
