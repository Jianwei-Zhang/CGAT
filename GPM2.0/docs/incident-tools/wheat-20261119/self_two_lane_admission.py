"""Experimental two-lane f0.005 self admission for an explicitly guarded plan.

Not wired into the running single-lane job. Only bounded, whole-record f0.005
queries with staged 64-GiB per-process-AS wrappers may overlap. Fast/native
pools are not mixed; cross, unknown, f0.001 and oversized work stay exclusive.
The 128-GiB lane reservations include helper overhead but are not a cgroup limit.
"""
from pathlib import Path
from alignment_tasks import AdaptiveDispatcher

POLICY={'scheduler_memory_mib':327680,'reservation_pool_gib':288,
    'fast_reservation_gib':128,'native_reservation_gib':128,
    'maximum_processes':2,'maximum_fast_processes':2,'maximum_native_processes':2,
    'maximum_query_bases':300_000_000,'maximum_target_bases':800_000_000,
    'maximum_native_target_bases':1_000_000_000,
    'fast_process_address_space_bytes':64*1024**3,'mixed_fast_native':False}


class SelfDispatcher(AdaptiveDispatcher):
    def __init__(self,bindings,native_exclusive,*,max_fast):
        super().__init__()
        if type(max_fast) is not int or max_fast!=2:
            raise ValueError('this guarded plan permits exactly two fast lanes')
        plan=bindings.plan
        guard=plan.get('resource_guard',{})
        if (guard.get('scope')!='per_process_virtual_address_space'
                or guard.get('limit_bytes')!=POLICY['fast_process_address_space_bytes']
                or set(guard.get('scripts',{}))!={s['path'] for row in bindings.rows.values() for s in row['scripts'].values()}):
            raise ValueError('every selected script must have a bound address-space guard')
        self.fast=set();self.exclusive=set();self.native_exclusive=native_exclusive
        for rel,profile in bindings.profiles.items():
            total=sum(profile.native['target_lengths'].values())
            if total>POLICY['maximum_native_target_bases']:
                self.exclusive.update(Path(b['directory'])/'command.sh' for b in profile.native['batches'])
            for i in profile.selected:
                row=bindings.rows[rel]['scripts'][str(i)];path=Path(row['path'])
                if guard['scripts'][str(path)].get('guarded_script_sha256')!=row['sha256']:
                    raise ValueError('guard inventory differs from execution script')
                entries=profile.native['batches'][i]['entries']
                if (profile.policy['seed_fraction']=='0.005' and len(entries)==1
                        and entries[0]['length']<=POLICY['maximum_query_bases']
                        and total<=POLICY['maximum_target_bases']):self.fast.add(path)
                else:self.exclusive.add(path)

    def kind(self,task):
        if task.command in self.fast:return 'fast'
        if task.command in self.exclusive:return 'exclusive'
        if '_vs_' in task.command.parent.name and not task.command.parent.name.endswith('_vs_self'):return 'exclusive'
        return 'exclusive' if self.native_exclusive(task) else 'native'

    def __call__(self,pending,available,budget,active,slots):
        slots=min(slots,POLICY['maximum_processes']-len(active))
        if slots<=0 or available<=0:return []
        kinds={self.kind(item['task']) for item in active}
        if 'exclusive' in kinds or len(kinds)>1:return []
        first=super().__call__(pending,available,budget,active,1)
        if not first:return []
        wanted=self.kind(first[0][0])
        if wanted=='exclusive':return [] if active else first
        if kinds and wanted not in kinds:return []
        pool=next(iter(kinds)) if kinds else wanted
        allowed=[task for task in pending if self.kind(task)==pool]
        # The two lanes each reserve 128 GiB; keep 32 GiB outside the 288-GiB pool.
        slots=min(slots,POLICY['reservation_pool_gib']//128-len(active))
        return super().__call__(allowed,available,budget,active,slots)
