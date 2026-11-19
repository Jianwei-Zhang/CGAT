"""Compute-node synthetic validation of two guarded minimap2 processes.

No customer mapping is rerun. Require nonempty byte-identical success outputs
and an explicit nonzero allocator failure in a separate deliberately tiny limit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shlex
import subprocess
import sys

import self_memory_guard as guard


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def execute(tool,output):
    tool=tool.resolve(strict=True);output=output.resolve();output.mkdir(exist_ok=False)
    rng=random.Random(20261119)
    sequence=''.join(rng.choice('ACGT') for _ in range(200000))
    target=output/'target.fa';target.write_text('>q2a\n'+sequence+'\n')
    query=output/'query.fa';query.write_text('>q1b\n'+sequence[50000:150000]+'\n')
    index=output/'target.mmi'
    subprocess.run([str(tool),'-x','asm10','-d',str(index),str(target)],check=True,capture_output=True,timeout=120)
    command=[str(tool),'-c','-x','asm10','-X','--no-hash-name','-m','200','-n','100','-t','1','-f','0.005',str(index),str(query)]
    native=subprocess.run(command,check=True,capture_output=True,timeout=120)
    if not native.stdout or b'cg:Z:' not in native.stdout:raise ValueError('nonempty synthetic baseline required')
    (output/'baseline.paf').write_bytes(native.stdout);(output/'baseline.stderr').write_bytes(native.stderr)
    def launch(name,limit):
        script=output/(name+'.sh');paf=output/(name+'.paf');stderr=output/(name+'.stderr')
        script.write_text('#!/bin/bash\nset -eu\necho SYNTHETIC_MAPPER_START\nexec '+shlex.join(command)
                          +' > '+shlex.quote(str(paf))+' 2> '+shlex.quote(str(stderr))+'\n')
        args=[sys.executable,str(Path(guard.__file__).resolve()),'--script',str(script),'--sha256',sha(script),'--limit-bytes',str(limit)]
        return subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE),paf,stderr
    children=[launch('guarded-'+str(i),guard.MAX_LIMIT_BYTES) for i in range(2)]
    successes=[]
    try:
        for child,paf,stderr in children:
            out,err=child.communicate(timeout=120)
            if child.returncode or paf.read_bytes()!=native.stdout:
                raise ValueError('guarded fixture differs or failed: '+err.decode(errors='replace'))
            successes.append({'returncode':child.returncode,'paf_sha256':sha(paf),'guard_stdout':out.decode()})
    finally:
        for child,_paf,_stderr in children:
            if child.poll() is None:child.kill();child.wait()
    child,paf,stderr=launch('forced-small-limit',16*1024**2)
    try:out,err=child.communicate(timeout=120)
    finally:
        if child.poll() is None:child.kill();child.wait()
    mapper_error=stderr.read_text(errors='replace') if stderr.exists() else ''
    explicit_oom='insufficient memory' in mapper_error.lower() or 'failed to allocate' in mapper_error.lower()
    if child.returncode==0 or b'SYNTHETIC_MAPPER_START' not in out or not explicit_oom:
        raise ValueError('small-limit test did not demonstrate an explicit mapper allocator failure: '+mapper_error+err.decode(errors='replace'))
    report={'status':'synthetic_two_guarded_mappers_and_allocator_failure_verified','customer_workspace_modified':False,
        'customer_mapping_rerun':False,'tool_sha256':sha(tool),'guard_sha256':sha(guard.__file__),
        'baseline_paf_sha256':sha(output/'baseline.paf'),'two_process_successes':successes,
        'forced_small_limit':{'limit_bytes':16*1024**2,'returncode':child.returncode,'mapper_stderr':mapper_error},
        'scope':'synthetic fixture; per-process AS limit, not a cgroup RSS guarantee or full wheat benchmark'}
    (output/'probe.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--tool',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();execute(args.tool,args.output)
