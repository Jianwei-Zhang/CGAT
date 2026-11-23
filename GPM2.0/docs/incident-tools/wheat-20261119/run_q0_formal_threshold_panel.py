"""Two cold Server scopes, including canonical ready, normal build_q0, and publication rows.

Only initial outer-checkpoint loading and the frozen reference lengths are adapted. No override
of admission, guards, regional plans, verification, or publication. Never write to the panel.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
from threading import Lock
from time import monotonic
from unittest.mock import patch

from lgz_core import q0_admission as admission, q0_preparation as prep, q0_regional_mapping as mapping
from lgz_core.common import read_fasta, write_fasta
from lgz_core.q0_catalog import ObservedSourcePairs
from lgz_core.q0_publication import stage_selection
from audit_q0_draft_consumers import differences, footprint, source, digest as field_digest
from run_wheat_frontier_panel import base_input, digest, within, restore_committed_tasks


def run(panel, sha, scratch, mapper, tool_sha, threads, archive=None, restore=None):
    if (not scratch.is_relative_to('/tmp') or scratch.exists() or scratch.is_relative_to(panel) or panel.is_relative_to(scratch)
            or digest(mapper)!=tool_sha or digest(panel/'panel.json')!=sha):
        raise ValueError('non-isolated scratch or incorrect frozen identity')
    manifest=json.loads((panel/'panel.json').read_text()); artifacts=manifest['artifacts']
    if manifest['panel']!=panel.name or any(digest(within(panel,p))!=h for p,h in artifacts.items()):
        raise ValueError('panel input drift')
    data,assignments,desc=base_input(panel,manifest); scratch.mkdir(mode=0o700)
    seqs={source(s):v for s,v in data.sources.items()}; geometry={}; results={}
    for scope in (('positive_threshold',) if archive else ('positive_threshold','full')):
        root=scratch/scope
        for p,h in artifacts.items():
            dest=root/p; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(within(panel,p),dest)
            if digest(dest)!=h: raise ValueError('cold copy changed')
        restored = None
        if restore:
            previous, expected = restore
            if scope!='positive_threshold' or not archive or not previous.is_relative_to('/tmp') or digest(previous/prep.MANIFEST)!=expected:
                raise ValueError('not the terminal bound threshold replay')
            restored = restore_committed_tasks(previous,root,data.parts)
            if digest(previous/prep.MANIFEST)!=expected: raise ValueError('terminal source changed')
        (root/'metadata/package.tsv').write_text('reads_qc_enabled\nfalse\n'); counts=Counter(); lock=Lock()
        execute,call=mapping._execute,prep.subprocess.run
        def initial(path):
            if path!=root: raise ValueError('wrong frozen root')
            known=ObservedSourcePairs({s:len(v) for s,v in data.sources.items()})
            for link in data.pair_links: known.observe_alignment(link.hit,link.query_source,link.target_source)
            return data.sources,data.reference_lengths,assignments,{'minimap_preset':'asm10'},sorted(artifacts),desc,known
        def fasta(p):
            return [(c,range(n)) for c,n in data.reference_lengths.items()] if p==root/'reference-lengths.json' else read_fasta(p)
        def counter(path,directory,*a,**kw):
            v=execute(path,directory,*a,**kw)
            with lock: counts['coarse' if directory.name=='chaining' else 'regional_exact']+=1
            return v
        def native(args,*a,**kw):
            v=call(args,*a,**kw)
            if isinstance(args,list) and args[0]==str(mapper) and '-o' in args and kw.get('cwd') and v.returncode==0:
                counts['native']+=1
            return v
        start=monotonic()
        with (patch.object(prep,'_initial_inputs',initial), patch.object(admission,'read_fasta',fasta),
              patch.object(mapping,'_execute',counter),patch.object(prep.subprocess,'run',native)):
            receipt=prep.prepare_evidence(root,threads=threads,minimap2=str(mapper),supplement_scope=scope)
            prepared=monotonic(); built=admission.build_q0(root)
            if receipt!=prep.load_verified_evidence(root): raise ValueError('ordinary consumer did not verify canonical generation')
            stage=root/'stage'; write_fasta(stage/'grt/q/q0.fa',built.records.items())
            datasets=prep.table(root,'metadata/datasets.tsv',('dataset_name','fasta_relpath'))
            rows,evidence=stage_selection(root,stage,built,datasets,assignments)
        end=monotonic(); geometry[scope]=footprint(built,seqs)
        catalog=prep.json_file(root/receipt['catalog']); report=catalog.get('supplement_scope',{})
        results[scope]={'actual_mapper_calls':dict(counts),'wall_s':end-start,'to_ready_s':prepared-start,
            'fasta_sha256':digest(stage/'grt/q/q0.fa'),'records':len(built.records),'staged_path_rows':len(rows),
            'staged_evidence_rows':len(evidence),'mode':report.get('effective','full'),'contract':built.decisions.get('supplement_acceptance'),
            'restored':restored,'regional_tasks':sum(t['kind']=='regional_discovery' for t in catalog['supplementary_alignments']),
            'manifest_sha256':digest(root/prep.MANIFEST),'catalog_sha256':digest(root/receipt['catalog'])}
        print('FORMAL_ARM',scope,json.dumps(results[scope],sort_keys=True),flush=True)
    output={'schema':'q0_formal_threshold_cold_panel_v1','panel_sha256':sha,'mapper_sha256':tool_sha,'panel':panel.name,
            'threads':threads,'arms':results}
    if archive:
        # Only after sealing the threshold result look at the old full comparator.
        path, expected_sha, expected_ready=archive
        if digest(path)!=expected_sha: raise ValueError('archived full comparison changed')
        prior=json.loads(path.read_text()); fields=prior['base_only']['fields']
        if (prior['panel']!=panel.name or prior['ready']!=expected_ready
                or fields.keys()!=geometry['positive_threshold'].keys()): raise ValueError('wrong archived full panel')
        output['archived_full']={'sha256':expected_sha,'ready':expected_ready,'sequences':prior['full_sequences'],
                                 'regional_tasks':prior['regional_windows'],'native_tasks':prior['native_tasks']}
        output['comparison']={k:{'draft_sha256':field_digest(v),'full_sha256':fields[k]['full_sha256']}
                              for k,v in geometry['positive_threshold'].items()}
    else:
        output['comparison']=differences(geometry['positive_threshold'],geometry['full'])
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('panel','scratch','mapper','output'):p.add_argument(k,type=Path)
    p.add_argument('--panel-sha',required=True);p.add_argument('--mapper-sha',required=True);p.add_argument('--threads',type=int,choices=(2,4,6),required=True)
    p.add_argument('--archived-full',type=Path); p.add_argument('--archive-sha'); p.add_argument('--archive-ready')
    p.add_argument('--restore-terminal',type=Path);p.add_argument('--restore-manifest-sha')
    a=p.parse_args(); panel=a.panel.resolve(strict=True); scratch=a.scratch.resolve();out=a.output.resolve()
    if out.exists() or out.is_relative_to(panel) or out.is_relative_to(scratch): raise ValueError('invalid output')
    args=(a.archived_full,a.archive_sha,a.archive_ready)
    if any(args) and not all(args): raise ValueError('incomplete archived comparator binding')
    if bool(a.restore_terminal)!=bool(a.restore_manifest_sha): raise ValueError('incomplete restore binding')
    restore=(a.restore_terminal.resolve(strict=True),a.restore_manifest_sha) if a.restore_terminal else None
    doc=run(panel,a.panel_sha,scratch,a.mapper.resolve(strict=True),a.mapper_sha,a.threads,args if all(args) else None,restore)
    with out.open('x') as f:json.dump(doc,f,sort_keys=True,indent=2);f.write('\n')
