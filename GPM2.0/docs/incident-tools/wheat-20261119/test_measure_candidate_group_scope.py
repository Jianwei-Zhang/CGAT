from pathlib import Path
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import measure_candidate_group_scope as scope


class CandidateScopeTests(unittest.TestCase):
    def test_weak_alternatives_are_not_qualified_but_original_groups_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=root/'work';lookup=root/'lookup';lookup.mkdir()
            parts={'one':{'dataset':'ds','contig':'q1','length':1000,'original_assigned_chromosomes':['c1']},
                   'two':{'dataset':'ds','contig':'q2','length':1000,'original_assigned_chromosomes':['c2']}}
            data=json.dumps(parts).encode();(lookup/'source-part-lookup.json').write_bytes(data)
            (lookup/'receipt.json').write_text(json.dumps({'lookup_sha256':hashlib.sha256(data).hexdigest()}))
            path=work/'runs/ds_vs_ref/result.paf';path.parent.mkdir(parents=True)
            lines=[]
            for q,t,mq in [('q1','c1',255),('q1','c2',0),('q2','c1',60),('q2','c2',60)]:
                lines.append(f'{q}\t1000\t0\t1000\t+\t{t}\t2000\t0\t1000\t990\t1000\t{mq}\tcg:Z:1000M\n')
            path.write_text(''.join(lines));summary=root/'reference-summary.json'
            summary.write_text(json.dumps({'datasets':[{'dataset':'ds','reference_paf_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]}))
            before=Path.cwd()
            try:
                os.chdir(root)
                with mock.patch.object(sys,'argv',['scope','--workspace',str(work),'--lookup-dir',str(lookup),'--reference-summary',str(summary)]),contextlib.redirect_stdout(io.StringIO()):
                    scope.main()
            finally:os.chdir(before)
            report=json.loads((root/'summary.json').read_text());rows={r['chromosome']:r for r in report['chromosomes']}
            self.assertEqual(rows['c1']['original_plus_qualifying_count'],2)
            self.assertEqual(rows['c2']['all_reference_candidates_count'],2)
            self.assertEqual(rows['c2']['original_plus_qualifying_count'],1)
            self.assertFalse(report['scientific_acceptance']);self.assertFalse(report['production_policy_changed'])


if __name__=='__main__':unittest.main()
