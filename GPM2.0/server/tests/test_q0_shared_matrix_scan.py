"""Single-pass first planning, with original input/checkpoint validation still in the path."""
from collections import Counter
from contextlib import ExitStack, nullcontext
import json
import random
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from server.tests import test_q0_preparation as support
from server.tools.lgz_core import q0_alignments as paf, q0_preparation as prep, q0_retained_hits as packed, q0_threshold_prepare as threshold
from server.tools.lgz_core.q0_sources import Q0EvidenceError, SourceKey
from server.tools.lgz_core.q0_catalog import ObservedSourcePairs


def cover(known):
    return (set(known), {k:tuple(v) for k,v in known.cross_coverage.items()})


class SharedScanTests(unittest.TestCase):
    def test_real_outer_checkpoint_reader_and_cold_ready_reuse(self):
        fixture=support.EvidencePreparationTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.seed_assigned_support(); root=fixture.server; ready=root/prep.MANIFEST; ready.unlink()
        counts=Counter(); original=paf.open_paf_text
        def traced(path,**kw):
            counts[path.relative_to(root).as_posix()]+=1;return original(path,**kw)
        def run(shared):
            counts.clear()
            with ExitStack() as stack:
                stack.enter_context(patch.object(paf,'open_paf_text',traced));stack.enter_context(patch.object(packed,'open_paf_text',traced))
                stack.enter_context(patch.object(prep,'regional_enabled',return_value=True))
                if not shared:stack.enter_context(patch.object(prep,'_initial_inputs',wraps=prep._native_initial_inputs))
                s=threshold._ThresholdInputs(root); values=s.read(); matrices=s.matrices
                self.assertEqual(matrices is not None,shared)
                seqs,lens,assignments,_,_,desc,known,_=values
                out=threshold.initial_questions(root,seqs,lens,assignments,desc,matrices=matrices)
                return dict(counts),out,cover(known),[d['paf'] for d in desc]
        old,a,c,paths=run(False); new,b,d,_=run(True);self.assertTrue(paths);self.assertEqual(a,b);self.assertEqual(c,d)
        for path in paths:self.assertEqual((old[path],new[path]),(2,1))
        ready.write_text('{}')  # even a potentially reusable ready must not allocate a retained matrix heap
        with patch.object(threshold,'_DraftMatrices',side_effect=AssertionError('unexpected shared heap')):
            threshold._ThresholdInputs(root).read()
        ready.unlink()
        with patch.object(prep,'read_paf_observations',wraps=paf.read_paf_observations) as custom, \
             patch.object(threshold,'_DraftMatrices',side_effect=AssertionError('custom reader bypassed')):
            state=threshold._ThresholdInputs(root);state.read()
            self.assertIsNone(state.matrices);self.assertGreater(custom.call_count,0)

    def test_real_published_ready_and_q0_are_identical_with_a_nonempty_cross_matrix(self):
        from server.tools.lgz_core import q0_admission as adm
        from server.tools.lgz_core.common import read_fasta,write_fasta
        fixture=support.EvidencePreparationTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.seed_assigned_support(); root=fixture.server; rng=random.Random(331)
        path=root/'data/datasets/primary.fa'; seqs=dict(read_fasta(path));seq=''.join(rng.choices('ACGT',k=len(seqs['p_cover'])))
        seqs['p_cover']=seq;write_fasta(path,seqs.items())
        path=root/'data/datasets/support.fa'; other=dict(read_fasta(path));other['s_assigned']=seq[:120]+other['s_assigned'][120:];write_fasta(path,other.items())
        desc=json.loads((root/'runs/chr_Chr01/q0_alignment_inputs.json').read_text())['alignments'];cross=next(d for d in desc if d['kind']=='cross')
        names={'primary':('p_cover',len(seq)),'support':('s_assigned',len(other['s_assigned']))};q,qn=names[cross['query_dataset']];t,tn=names[cross['target_dataset']]
        (root/cross['paf']).write_text(f'{q}\t{qn}\t0\t120\t+\t{t}\t{tn}\t0\t120\t120\t120\t60\tcg:Z:120M\n')
        support.seed_q0_evidence(root); results=[]
        for shared in (False,True):
            (root/prep.MANIFEST).unlink()
            with (nullcontext() if shared else patch.object(prep,'_initial_inputs',wraps=prep._native_initial_inputs)):
                ready=prep.prepare_evidence(root,threads=1,minimap2=str(fixture.minimap),supplement_scope='positive_threshold')
                self.assertEqual(ready,prep.load_verified_evidence(root));built=adm.build_q0(root)
                self.assertTrue(built.records);results.append((ready,built.records,built.decisions))
        self.assertEqual(*results)

    def test_canonical_names_do_not_grant_membership_in_another_partition(self):
        canonical={};a=threshold._PartitionNames({'one':10},canonical);self.assertEqual(a['one'],('one',10))
        b=threshold._PartitionNames({'other':10},canonical)
        with self.assertRaises(KeyError):_ = b['one']
        c=threshold._PartitionNames({'one':9},canonical)
        with self.assertRaises(Q0EvidenceError):_ = c['one']

    def test_changed_empty_partial_or_wrong_direction_cannot_be_replayed(self):
        with TemporaryDirectory() as td:
            root=Path(td); path=root/'d.paf'; path.write_text('# no hits\n'); cache=threshold._DraftMatrices(root)
            args={'artifact':'d.paf','query_dataset':'a','target_dataset':'b','query_lengths':{'q':5},'target_lengths':{'t':5}}
            row={'paf':'d.paf','query_dataset':'a','target_dataset':'b'}
            self.assertEqual(list(cache.observe(path,**args)),[]);cache.check_inventory([row]);self.assertEqual(cache.take(row),[])
            list(cache.observe(path,**args));
            with self.assertRaises(Q0EvidenceError):cache.check_inventory([row,row])
            with self.assertRaises(Q0EvidenceError):cache.take({**row,'target_dataset':'a'})
            list(cache.observe(path,**args));path.write_text('# different generation\n')
            with self.assertRaisesRegex(Q0EvidenceError,'generation'):cache.take(row)
            path.write_text('q\t5\t0\t5\t+\tt\t5\t0\t5\t5\t5\t60\tcg:Z:5M\n'); g=cache.observe(path,**args);next(g);g.close()
            with self.assertRaisesRegex(Q0EvidenceError,'incomplete'):cache.check_inventory([row])

    def test_cross_coverage_reiterates_cigar_after_failed_qualifier(self):
        with TemporaryDirectory() as td:
            root=Path(td); path=root/'p'; a,b=SourceKey('a','q'),SourceKey('b','t'); lens={a:200,b:200}; cache=threshold._DraftMatrices(root)
            path.write_text('q\t200\t0\t5\t-\tt\t200\t0\t5\t5\t5\t60\tcg:Z:5M\nq\t200\t5\t105\t+\tt\t200\t8\t108\t100\t100\t60\tcg:Z:100M\n')
            kw=dict(artifact='p',query_lengths={'q':200},target_lengths={'t':200}); outputs=[]
            for stream in (paf.read_paf_observations(path,**kw),cache.observe(path,query_dataset='a',target_dataset='b',**kw)):
                obs=ObservedSourcePairs(lens)
                for i,hit in enumerate(stream):
                    obs.observe_alignment(hit,a,b)
                    if i==0:self.assertIn((a,b),obs);self.assertFalse(obs.cross_coverage)
                outputs.append(cover(obs))
            self.assertEqual(*outputs)
