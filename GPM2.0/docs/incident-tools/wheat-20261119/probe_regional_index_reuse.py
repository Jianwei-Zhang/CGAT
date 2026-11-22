"""ABBA: build the original target index during chaining, reuse it for CIGAR.

No union/subset of targets, profile changes, or adoption of generated evidence.
Both stages must reproduce their original PAF bytes. Include scratch index
writing and loading in measured time, not just the reported alignment time.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import tempfile
import time

from benchmark_regional_mapper_dispatch import digest, read_json
from probe_regional_loader_path import original_operations, run_one


CONTROL_SHA = '8d774d0fd5ac8652f503375a75c997c8182852041d5fe052e3c6a88c66047901'


def reuse_commands(operations, index):
    if tuple(name for name, _, _ in operations) != ('coarse', 'exact'):
        raise ValueError('index reuse diagnostic requires paired original stages')
    (_, coarse, cp), (_, exact, ep) = operations
    if coarse[0] != exact[0] or coarse[-2:] != exact[-2:]:
        raise ValueError('chaining and CIGAR do not share exact input files')
    expected = ['-x', 'asm10', '-D', '-P', '--dual=yes', '--no-long-join']
    if coarse[1:-2] != [*expected, '-t', '2'] or exact[1:-2] not in (
            ['-c', *expected, '-t', '2'], ['-c', *expected, '-m', '2000', '-t', '2']):
        raise ValueError('unexpected archived mapper options')
    return [('coarse', [*coarse[:-2], '-d', str(index), *coarse[-2:]], cp),
            ('exact', [*exact[:-2], str(index), exact[-1]], ep)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'control-artifacts', 'anchor-report', 'guard', 'tool', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a=p.parse_args(); work=a.workspace.resolve(strict=True); inputs=a.control_artifacts.resolve(strict=True)
    out=a.output.resolve(); tool=a.tool.resolve(strict=True); guard=a.guard.resolve(strict=True)
    if any(x.is_relative_to(y) or y.is_relative_to(x) for x,y in [(out,work),(out,inputs),(inputs,work)]):
        raise ValueError('diagnostic output/input overlaps main')
    if digest(a.anchor_report)!=CONTROL_SHA:
        raise ValueError('wrong archived original inventory')
    out.mkdir(exist_ok=False)
    tasks,inventory,total=original_operations(work,inputs,read_json(a.anchor_report),tool)
    protected={**inventory,tool:digest(tool),guard:digest(guard)}
    if len(tasks)!=3:
        raise ValueError('expected three bounded archived cases')
    phases=[]
    env=dict(os.environ)
    for number, reuse in enumerate((False,True,True,False)):
        path=out/f'{number}-{"reuse" if reuse else "baseline"}'; path.mkdir()
        start=time.monotonic()
        def run(task):
            ordinal,ops=task; dest=path/str(ordinal); dest.mkdir()
            # Private node-local scratch; never read an index from production.
            with tempfile.TemporaryDirectory(dir='/tmp',prefix='cgat-regional-index-') as scratch:
                index=Path(scratch)/'target.mmi'; results={}
                for name,argv,sha in (reuse_commands(ops,index) if reuse else ops):
                    result=run_one(dest/name,guard,argv,env,sha)
                    stderr=(dest/name/'stderr').read_text()
                    if stderr.count('loaded/built the index for ')!=1:
                        raise ValueError('expected one complete target index part per original stage')
                    if reuse and (not index.is_file() or not index.stat().st_size):
                        raise ValueError('missing candidate scratch index')
                    results[name]=result
                return {'ordinal':ordinal,'index_bytes':index.stat().st_size if reuse else 0,'stages':results}
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows=list(pool.map(run,tasks))
        phase={'replicate':number,'reuse':reuse,'seconds':time.monotonic()-start,'cases':rows}
        phases.append(phase); print(json.dumps(phase),flush=True)
    if any(digest(path)!=sha for path,sha in protected.items()):
        raise ValueError('immutable diagnostic input drift')
    (out/'summary.json').write_text(json.dumps({'status':'archived_output_exact_ABBA_not_deployed',
        'host':socket.gethostname(),'input_bytes':total,'guard_sha256':protected[guard],'tool_sha256':protected[tool],
        'phases':phases,'production_modified':False,'same_as_historical':True},indent=2,sort_keys=True)+'\n')


if __name__=='__main__':
    main()
