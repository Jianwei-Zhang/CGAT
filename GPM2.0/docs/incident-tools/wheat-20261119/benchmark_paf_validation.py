"""Controlled validator microbenchmark; no customer input or remote runtime edits."""
import argparse
import ast
import hashlib
import json
import platform
from pathlib import Path
import random
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import tracemalloc


def previous_function(repo, revision, relative, name, current, previous_directory=None):
    data = ((previous_directory / relative).read_bytes() if previous_directory is not None else
            subprocess.check_output(['git', '-C', str(repo), 'show', revision + ':' + relative]))
    tree = ast.parse(data.decode())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = dict(vars(current))
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'git:' + revision + ':' + relative, 'exec'), namespace)
    return namespace[name], hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository',type=Path,required=True)
    parser.add_argument('--previous-revision',required=True)
    parser.add_argument('--previous-source-directory',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();repo=args.repository.resolve(strict=True)
    sys.path.insert(0,str(repo/'GPM2.0'))
    from server.tools import run_orchestration as native
    from server.tools.lgz_core import q0_alignments as q0
    modules=[('native',native,'validate_paf','GPM2.0/server/tools/run_orchestration.py'),
             ('q0',q0,'parse_paf_line','GPM2.0/server/tools/lgz_core/q0_alignments.py')]
    revision=(args.previous_revision if args.previous_source_directory else
              subprocess.check_output(['git','-C',str(repo),'rev-parse',args.previous_revision],text=True).strip())
    functions={};sources={}
    for kind,module,name,relative in modules:
        old,old_sha=previous_function(repo,revision,relative,name,module,args.previous_source_directory)
        functions[kind]=(old,getattr(module,name))
        sources[kind]={'path':relative,'old_sha256':old_sha,'new_sha256':hashlib.sha256((repo/relative).read_bytes()).hexdigest()}
    rng=random.Random(512);reports=[]
    with TemporaryDirectory() as temporary:
        root=Path(temporary)
        for label,count,records in [('ordinary',20,6000),('long_cigar',72000,25)]:
            tokens=[(rng.randrange(1,10000),rng.choice('MIDN=X')) for _ in range(count)]
            cigar='100M'+''.join(str(length)+op for length,op in tokens)
            query=100+sum(n for n,op in tokens if op in 'MI=X')
            target=100+sum(n for n,op in tokens if op in 'MDN=X')
            line=f'q\t{query+10}\t5\t{query+5}\t-\tt\t{target+20}\t7\t{target+7}\t100\t{query+target}\t255\tcg:Z:{cigar}'
            path=root/(label+'.paf');path.write_text((line+'\n')*records)
            for kind in functions:
                methods=functions[kind]
                def run(method):
                    if kind=='native':return method(path,require_cigar=True)
                    result=None
                    for number in range(1,records+1):result=method(line,artifact='controlled.paf',line_number=number)
                    return result
                assert run(methods[0])==run(methods[1]),'result/geometry/provenance differs'
                samples=[[],[]]
                for round_number in range(5):
                    for version in ((0,1) if round_number%2==0 else (1,0)):
                        started=time.perf_counter();run(methods[version]);samples[version].append(time.perf_counter()-started)
                medians=[statistics.median(values) for values in samples]
                row={'kind':kind,'case':label,'cigar_operations':count+1,'paf_records':records,
                     'input_bytes':path.stat().st_size,'median_seconds':dict(zip(('previous','candidate'),medians)),
                     'speedup':medians[0]/medians[1],'full_result_equal':True}
                if label=='long_cigar':
                    peaks=[]
                    for method in methods:
                        tracemalloc.start();run(method);peaks.append(tracemalloc.get_traced_memory()[1]);tracemalloc.stop()
                    row['python_allocation_peak_bytes']=dict(zip(('previous','candidate'),peaks))
                reports.append(row)
    report={'schema':'controlled_paf_validator_benchmark_v1','python':sys.version,'platform':platform.platform(),
            'previous_revision':revision,'sources':sources,'cases':reports,
            'synthetic_only':True,'customer_data_used':False,'remote_runtime_modified':False,'whole_wheat_speedup_proven':False}
    for row in sources.values():
        if hashlib.sha256((repo/row['path']).read_bytes()).hexdigest()!=row['new_sha256']:
            raise ValueError('candidate validator source changed during benchmark')
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
