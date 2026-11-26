"""Read partition timing from a *completed* minimap2 2.31 wheat A/B run. Never use partial PAFs."""
from hashlib import sha256
import json
from pathlib import Path
import re,sys

from plan_wheat_panel_neighborhoods import pinned_panel
from wheat_selection_checkpoint import need

STAMP = r'\[M::%s::([\d.]+)\*[\d.]+\] '

def phases(raw, nq, nt, nbp):
    phase='index'; parts=[]; last=0.; ready=None; real=None
    for text in raw.decode().splitlines():
        if m:=re.match((STAMP%'main')+r'loaded/built the index for (\d+) target sequence\(s\)',text):
            need(phase=='index' and real is None,'unexpected index boundary');loaded,count=float(m[1]),int(m[2]);phase='stats'
        elif m:=re.match((STAMP%'mm_idx_stat')+r'distinct minimizers: .*; total length: (\d+)$',text):
            need(phase=='stats','unbound index statistics');ready,bases=float(m[1]),int(m[2]);need(last<=loaded<=ready and bases>0 and count>0,'invalid index statistics');phase='query'
        elif m:=re.match((STAMP%'worker_pipeline')+r'mapped (\d+) sequences$',text):
            t=float(m[1]);need(phase=='query' and int(m[2])==nq and t>=ready,'unfinished or multi-batch query cohort');parts.append(dict(targets=count,bases=bases,pre_query_s=round(ready-last,3),query_s=round(t-ready,3)));last=t;phase='index'
        elif m:=re.match(r'\[M::main\] Real time: ([\d.]+) sec; CPU: ([\d.]+) sec; Peak RSS: ([\d.]+) GB$',text):
            need(real is None and phase=='index' and parts and float(m[1])>=last,'invalid final timer');real,cpu,rss=map(float,m.groups())
    need(real is not None and phase=='index' and sum(p['bases'] for p in parts)==nbp and sum(p['targets'] for p in parts)==nt,'incomplete library or partial native stderr')
    return dict(parts=parts,pre_query_s=round(sum(p['pre_query_s'] for p in parts),3),query_s=round(sum(p['query_s'] for p in parts),3),tail_s=round(real-last,3),native_real_s=real,native_cpu_s=cpu,peak_rss_gb=rss)


def report(mapped,panel_path,logs):
    panel,pin=pinned_panel(panel_path);raw=mapped.read_bytes();m=json.loads(raw);need(m['panel']==pin and (m['original_bp'],m['shortlist_bp'])==(31706122489,2302475263),'foreign mapping')
    res={}; hashes={}
    for arm,n,b in [('full',38267,m['original_bp']),('reduced',len(panel['retained']),m['shortlist_bp'])]:
        log=(logs/(arm+'.stderr')).read_bytes();hashes[arm]=sha256(log).hexdigest();res[arm]=phases(log,len(panel['queries']),n,b)
        need(0<=m['mapper'][arm]['seconds']-res[arm]['native_real_s']<=max(15,0.02*m['mapper'][arm]['seconds']),'native log does not agree with measured subprocess wall time')
    return dict(panel=pin,mapping=sha256(raw).hexdigest(),stderr=hashes,arms=res,scope='Single cold build per arm; pre-query includes reading/building the index plus setup/statistics for each partition. Query time includes mapping/output through the mapped marker. These are observed phases, not a warm index benchmark.')

if __name__=='__main__':print(json.dumps(report(*map(Path,sys.argv[1:4])),sort_keys=True,indent=2))
