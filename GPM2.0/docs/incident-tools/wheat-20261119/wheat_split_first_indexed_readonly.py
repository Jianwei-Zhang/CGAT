"""Exact overlap indexing for the cached split-first audit, no policy change."""
import argparse,inspect,json,subprocess,textwrap
from bisect import bisect_left,bisect_right
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from lgz_core.q0_sources import merged_intervals
import wheat_continuity_gap_rescue_readonly as rescue
import wheat_continuous_dominant_admission_readonly as original
from wheat_reference_funnel_readonly import write,digest


class OverlapIndex:
    def __init__(self, intervals):
        self.rows=merged_intervals(intervals)
        self.starts=tuple(i.start for i in self.rows);self.ends=tuple(i.end for i in self.rows)
        self.sums=[0]
        for i in self.rows:self.sums.append(self.sums[-1]+i.length)
    def overlap(self,intervals):
        total=0
        for iv in merged_intervals(intervals):
            lo=bisect_right(self.ends,iv.start);hi=bisect_left(self.starts,iv.end)
            if lo<hi:
                total+=self.sums[hi]-self.sums[lo]-max(0,iv.start-self.starts[lo])-max(0,self.ends[hi-1]-iv.end)
        return total


def indexed_barriers():
    source=textwrap.dedent(inspect.getsource(original.foreign_barriers))
    changes={
        '    main_hull = adm._hull(a.source for a in main_chain)':
        '    main_index = OverlapIndex(a.source for a in main_chain)\n    high_indexes = {key: OverlapIndex(high.get(key, ())) for key in groups}\n    main_hull = adm._hull(a.source for a in main_chain)',
        'legacy.overlap_bp((a.source for a in main_chain), (hull,))':'main_index.overlap((hull,))',
        'legacy.overlap_bp((a.source for a in selected), high.get(key, ()))':'high_indexes[key].overlap(a.source for a in selected)',
    }
    for old,new in changes.items():
        rescue.need(source.count(old)==1,'foreign overlap implementation changed')
        source=source.replace(old,new)
    scope=dict(vars(original));scope['OverlapIndex']=OverlapIndex
    exec(compile(source,'<indexed-foreign-barriers>','exec'),scope)
    return scope['foreign_barriers'],sha256(source.encode()).hexdigest()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('admission',type=Path);p.add_argument('owner',type=Path);a=p.parse_args()
    rescue.need(a.owner.resolve().parent==a.admission.resolve().parent and a.owner.stat().st_mode&0o077==0,'private sibling owner required')
    fast,pin=indexed_barriers()
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external program forbidden')),patch.object(rescue,'foreign_barriers',fast):
        rescue.admission_audit(a.admission,a.owner)
    write(a.owner/'indexed-admission-receipt.json',{'schema':'wheat_cached_admission_indexed_receipt_v1','indexed_function_sha256':pin,'policy_changed_by_index':False,'report_sha256':digest(a.owner/'split-first-admission-audit.json')})
