import unittest
from measure_replayed_wheat_demand import account

class DemandAccountingTests(unittest.TestCase):
    def test_unseen_target_on_query_miss_stays_unknown(self):
        v=account('localized',10,3,5,{'both':1,'query_only':1,'target_only':1,'omitted':2}); self.assertEqual((v['known_either_axis'],v['known_neither_axis'],v['without_target_inventory_query_intersects'],v['without_target_inventory_needs_target_check']),(3,2,1,4))
        with self.assertRaises(ValueError):account('localized',8,7,5,{'both':1,'omitted':4})
    def test_no_path_and_fallback_are_not_successful_zero_mapping(self):
        for m,tag in [('full_fallback','full_fallback'),('no_supported_backbone','omitted'),('base_only','omitted')]:
            self.assertEqual(account(m,10,0,4,{tag:4})['base_only_first_request'],m=='base_only')

    def test_join_checks_real_query_ids_and_distinguishes_touching_ends(self):
        from contextlib import ExitStack
        import gzip, hashlib, json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        import measure_replayed_wheat_demand as m
        from lgz_core.q0_sources import SourceKey
        def put(path,data):
            path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data);return hashlib.sha256(data).hexdigest()
        def doc(path,data):return put(path,json.dumps(data).encode())
        with TemporaryDirectory() as td:
            b=Path(td);plan=b/'q0-fork-partial-queries-20261123-1556/plan';control=b/'q0-latest-fork-20261123-1435/control'; d=SourceKey('D','one'); part='part'; lens={d:100}; key=lambda a,z:m.stable_id('q0-query-window',dict(segment_id=part,segment_length=100,start=a,end=z))
            text=''.join(f'{key(a,z)}\t0\t{a}\t{z}\n' for a,z in [(0,20),(20,40),(50,90)]).encode(); qp=put(plan/'queries.tsv.gz',gzip.compress(text))
            replay={'snapshot':m.SNAP,'count_matches':True,'logged_plan_count':3,'replayed_query_count':3,'membership_in_frozen_census':{'contexts':1,'matching_contexts':1,'planned_queries_with_observed_target_sets':1,'distinct_other_queries':0},'queries_uncompressed_sha256':hashlib.sha256(text).hexdigest()}; rp=doc(plan/'replay.json',replay)
            first={'schema':'wheat_threshold_global_first_request_v1','threshold_contract':m.supplement_policy('positive_threshold')['decision_frontier'],'snapshot_sha256':m.SNAP,'revision':'rev','has_path':True,'published_q0':False,'mapper_calls':0,'request':[[{'dataset':'D','contig':'one'},[[20,35]]]]}; snapshot=doc(control/'global-first-request.json',first)
            census={'schema':'existing_wheat_context_first_request_count_v1','snapshot':m.SNAP,'mode':'localized','has_path':True,'request_sha256':snapshot,'inventory_sha256':m.AXES,'counts':{'contexts':1,'distinct_query_windows':1,'axes_breakdown':{'target_only':1}}};doc(b/'q0-fork-window-census-20261123-1505/census/first-request-count.json',census)
            with ExitStack() as ctx:
                for k,v in [('REPLAY',rp),('QUERIES',qp)]:ctx.enter_context(patch.object(m,k,v))
                ctx.enter_context(patch.object(m,'bind',return_value=({'revision':'rev'},b/'src',{part:(0,100,'s')},[d],lens)))
                with patch('builtins.print'):m.main(b,b/'result.json')
                out=json.loads((b/'result.json').read_text())['accounting']; self.assertEqual((out['all_queries_directly_intersecting'],out['known_either_axis'],out['without_target_inventory_needs_target_check']),(1,1,1))
                first['request']=[]; doc(control/'global-first-request.json',first)
                with self.assertRaisesRegex(ValueError,'two-axis result differs'):m.main(b,b/'stale.json')
                self.assertFalse((b/'stale.json').exists())
