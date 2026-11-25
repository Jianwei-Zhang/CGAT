from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from server.tests import test_q0_regional_mapping as support
from lgz_core.q0_query_windows import QueryWindow
from lgz_core import q0_regional_mapping as m
from lgz_core.common import sha256_file
from census_wheat_q0_fork import pack_context
import refresh_whole_wheat_cached_demand as whole


class WholeDraftStageTests(unittest.TestCase):
    def test_hit_and_original_core_projection_match_the_stock_paf_without_a_new_mapper(self):
        f=support.RegionalMappingTests();f.setUp();self.addCleanup(f.doCleanups)
        task=f.run_mapping();verified=m.verify_regional_task(f.root,task,members=f.catalog.parts);sp=verified['spec'];ctx=sp['context'];context=m._ops().json_file(f.root/ctx['path']);cid=ctx['path'].split('/')[-2];raw=sp['raw_receipt'];leaf=m._ops().json_file(f.root/raw['path']);paf,=[row for row in leaf['outputs'] if row['path'].endswith('/result.paf')]
        parts={k:(i,p.interval.length,p.sequence_sha256) for i,(k,p) in enumerate(sorted(f.catalog.parts.items()))}; stamp=sha256(pack_context(cid,context['spec'],parts)).hexdigest()
        entry=dict(context=cid,context_file=ctx,decision_file=sp['decision'],chaining_receipt=None,raw_paf=paf,raw_receipt=raw,flags=leaf['spec']['flags']);changed=QueryWindow(f.query.segment_id,f.query.segment_length,f.query.start,f.query.end,((10000,11000),))
        with TemporaryDirectory() as d, patch.multiple(whole,create=True,ROOT=f.root,STAGE=Path(d),PARTS=parts,TOOL=f.tool,MEMBERS={k:v[1:] for k,v in parts.items()},PROJECTOR=sp['projector_sha256'],VALIDATOR=sp['validator_sha256']):
            for query,mode in ((f.query,'projected_hit'),(changed,'projection_only')):
                with patch.object(whole,'WINDOWS',{query.window_id:query},create=True),patch.object(m.subprocess,'Popen',side_effect=AssertionError('no mapper')):
                    _,ident,_,_,digest,actual=whole.project_one(query.window_id,stamp,entry);expected=f.run_mapping(query)
                self.assertEqual((actual,ident,digest),(mode,expected['task_id'],sha256_file(f.root/expected['paf'])))
                self.assertEqual((Path(d)/expected['paf']).read_bytes(),(f.root/expected['paf']).read_bytes())

    def test_mismatched_raw_bytes_never_make_a_completed_stream(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'x';p.write_bytes(b'x\n');self.assertEqual(list(whole.raw_lines(p,dict(size=2,sha256=sha256_file(p)))),['x\n'])
            with self.assertRaisesRegex(ValueError,'unbound raw stream'):list(whole.raw_lines(p,dict(size=2,sha256='f'*64)))


if __name__=='__main__': unittest.main()
