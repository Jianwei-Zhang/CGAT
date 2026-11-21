"""Controlled exact-payload/RSS benchmark, not a customer speedup estimate."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import resource
import sys
import tempfile
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gpm-root',type=Path,required=True)
    p.add_argument('--catalog-module',type=Path,required=True)
    p.add_argument('--mode',choices=['reference','pairwise'],required=True)
    p.add_argument('--repetitions',type=int,default=500)
    a=p.parse_args();sys.path.insert(0,str(a.gpm_root))
    from server.tools.lgz_core.common import canonical_json
    from server.tools.lgz_core.q0_sources import SourceKey
    from server.tools.lgz_core.q0_alignments import parse_paf_line
    name='server.tools.lgz_core._catalog_union_benchmark'
    spec=importlib.util.spec_from_file_location(name,a.catalog_module)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);paf=root/'runs/ds_vs_ref/result.paf';paf.parent.mkdir(parents=True)
        if a.mode=='reference':
            cigar='20M1D'*1000
            paf.write_text(('q\t20000\t0\t20000\t+\tchr\t21000\t0\t21000\t20000\t21000\t60\tcg:Z:'+cigar+'\n')*a.repetitions)
            sources={SourceKey('ds','q'):'A'*20000};refs={'chr':21000}
        else:
            sources={SourceKey('ds',key):'A'*21000 for key in ['q','t']};refs={f'chr{i}':21000 for i in range(3)}
            paf.write_text(''.join(f't\t21000\t0\t21000\t+\t{chr}\t21000\t0\t21000\t21000\t21000\t60\tcg:Z:21000M\n' for chr in refs))
        started=time.perf_counter();catalog=module.build_catalog(root,sources,refs,[])
        if a.mode=='pairwise':
            ids={part.source.contig:part.segment_id for part in catalog.parts.values()}
            cigar='20M1I1D'*1000
            line=f"{ids['q']}\t21000\t0\t21000\t+\t{ids['t']}\t21000\t0\t21000\t20000\t22000\t60\tcg:Z:{cigar}"
            hits=(parse_paf_line(line,artifact='supplement.paf',line_number=i+1) for i in range(a.repetitions))
            module.add_pairwise_candidates(catalog,hits,{ids['q']},{ids['t']})
        elapsed=time.perf_counter()-started;payload=catalog.finish()
        report={'mode':a.mode,'repetitions':a.repetitions,'seconds':elapsed,
                'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'payload_sha256':hashlib.sha256(canonical_json(payload).encode()).hexdigest(),
                'module_sha256':hashlib.sha256(a.catalog_module.read_bytes()).hexdigest(),
                'candidate_count':len(payload['candidates']),'evidence_count':len(payload['evidence'])}
        print(json.dumps(report))


if __name__=='__main__':main()
