"""Exercise the same fresh, metadata-only worker used by the whole-wheat accounting job."""
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lgz_core.q0_alignments import read_paf
from lgz_core.q0_reference_index import ReferenceIndex
from lgz_core.q0_sources import Interval,SourceKey,split_source
from check_wheat_inverse_targets import init_worker,inverse_group
from inverse_wheat_target_evidence import invert


class InverseWorkerTests(unittest.TestCase):
    def test_spawn_reads_bound_index_and_excludes_own_source(self):
        src=SourceKey('x','a'); other=SourceKey('x','b'); seq='ACGT'*250
        parts={p.segment_id:p for source in (src,other) for p in split_source(source,seq).segments}
        ids={p.source:p.segment_id for p in parts.values()}; refs={'chr':10000}
        with TemporaryDirectory() as td:
            root=Path(td); path=root/'r.paf'; path.write_text(''.join(f'{s.contig}\t1000\t0\t1000\t+\tchr\t10000\t17\t1017\t1000\t1000\t60\tcg:Z:1000M\n' for s in (src,other)))
            index=ReferenceIndex.create(root/'db',root,parts,refs)
            try:
                list(read_paf(path,artifact='r.paf',query_lengths={'a':1000,'b':1000},target_lengths=refs,record_observer=lambda h,a,n:index.observe_record('x',h,a,n)));index.seal(); mask=invert(index,{src:(Interval(100,200),)})
                with ProcessPoolExecutor(1,mp_context=get_context('spawn'),initializer=init_worker,initargs=(index.reader_snapshot(),mask)) as pool:
                    out=pool.submit(inverse_group,[(b'A',ids[src],30,200),(b'B',ids[other],30,200)]).result(timeout=40)
                self.assertEqual(out,[(b'A',False),(b'B',True)])
            finally:index.close()
