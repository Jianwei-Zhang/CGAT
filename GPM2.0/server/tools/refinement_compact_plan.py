"""Read-only planner for explicit compaction of completed, published native attempts."""
from __future__ import annotations

import csv
import hashlib
import os
from pathlib import Path
from itertools import chain
import re
import stat

from delivery_archive import archive_options
from job_final_catalog import _encode, _read_catalog, validate_catalog
from project_delivery_publish import HOME, _checked_receipt, _names
from refinement_bundle import MANIFEST as TOOL_MANIFEST
from refinement_commit import (PublicationError, committed_area_history, current_publication,
                               layout_and_lock, read_json, targets)
from refinement_native_checkpoint import NAME, SCHEMA as NATIVE_SCHEMA
from refinement_scratch import MAX_FILES, POLICY, identity, role
from refinement_source_evidence import measurement_input
from refinement_tools import fingerprint
from run_orchestration import sha256_file
from workspace_layout import TOOL_DIRECTORIES, relative_path

HEX = re.compile('[a-f0-9]{64}')
WARNING = ('Only the listed generated read copies/indices can be unlinked. Raw-stage inspection or '
           'rerunning the native tool by hand may require preprocessing again. Published genomes, '
           'accepted sources, evidence, receipts, failed attempts and .runtime are not cleanup targets. '
           'COW sharing keeps both files; unsupported filesystems skip it without a destructive fallback.')


def regular(layout, path):
    p=layout.path(Path(path).relative_to(layout.root).as_posix())
    if p.is_symlink() or not p.is_file(): raise PublicationError(f'missing/linked compaction dependency: {p}')
    return p


def bound(layout,path,sha):
    p=regular(layout,path)
    if not isinstance(sha,str) or not HEX.fullmatch(sha) or sha256_file(p)!=sha:
        raise PublicationError(f'changed compaction dependency: {p}')
    return p


def collect_refs(layout,value,paths,hashes):
    """Protect explicit paths as well as content identities in publication/source evidence."""
    pending=[value]
    while pending:
        item=pending.pop()
        if isinstance(item,dict): pending.extend(item.keys()); pending.extend(item.values())
        elif isinstance(item,list): pending.extend(item)
        elif isinstance(item,str):
            if HEX.fullmatch(item): hashes.add(item)
            elif item.startswith('/') or item.startswith(('04_refinement/','05_final/','.runtime/','01_inputs/')):
                # Exact resolved names also protect a source reached through a locator alias.
                path=Path(item) if item.startswith('/') else layout.root/item
                paths.add(path.resolve())


def project_state(layout):
    home=layout.path(HOME); pending=home/'publishing.json'
    if pending.exists() or pending.is_symlink(): raise PublicationError('finish project archive recovery before compaction')
    pointer=regular(layout,home/'committed.json'); proof=read_json(pointer)
    names=_names(layout,archive_options(layout.root)[0]); hashes=_checked_receipt(proof,names)
    if not hashes:
        raise PublicationError('project Full/Light pair must be committed first')
    tools = proof.get('tools')
    if not isinstance(tools, dict) or set(tools) - TOOL_DIRECTORIES.keys() or bool(tools) != ('auto' in hashes):
        raise PublicationError('inconsistent automatic tool set in project delivery receipt')
    for kind,sha in hashes.items(): bound(layout,layout.path('07_delivery/'+names[kind]),sha)
    rows,_=_read_catalog(layout)
    validate_catalog(layout,hashlib.sha256(_encode(rows)).hexdigest())
    return proof,{'pair_sha256':sha256_file(pointer),'catalog_sha256':sha256_file(layout.path('05_final/results.tsv'))}


def protected_assets(layout):
    paths,hashes,versions,receipts=set(),set(),{},{}
    for tool in TOOL_DIRECTORIES:
        journal=current_publication(layout.root,tool)
        if not journal: continue
        live=targets(layout,tool); versions[tool]=journal
        receipts[tool]=fingerprint(journal)
        for area in ('final','report'):
            current=(live[area],journal['areas'][area]['new']['files'])
            for directory,files in chain([current],committed_area_history(layout,tool,area)):
                if area=='final':
                    prov=read_json(bound(layout,directory/'provenance.json',files['provenance.json']))
                    collect_refs(layout,prov,paths,hashes)
                    origin=prov['execution'].get('native_origin')
                    if origin:
                        native=read_json(bound(layout,layout.path(origin['receipt']),origin['receipt_sha256']))
                        collect_refs(layout,native['input_dependencies'],paths,hashes)
                        collect_refs(layout,native['result']['artifacts'],paths,hashes)
                    with bound(layout,directory/'sources.tsv',files['sources.tsv']).open(newline='',encoding='utf-8') as stream:
                        for row in csv.DictReader(stream,delimiter='\t'):
                            name=row['fasta_path']
                            if row['path_scope']=='workspace': src=layout.path(name)
                            elif row['path_scope']=='external' and Path(name).is_absolute(): src=Path(name)
                            else: raise PublicationError('invalid retained source locator')
                            resolved=src.resolve(strict=True)
                            if sha256_file(resolved)!=row['fasta_sha256']: raise PublicationError(f'retained source changed: {src}')
                            paths.add(resolved); hashes.add(row['fasta_sha256'])
                else:
                    report=read_json(bound(layout,directory/'manifest.json',files['manifest.json']))
                    binding=report['binding']; collect_refs(layout,binding,paths,hashes)
                    # Source-comparison measurements may consume native references not used by the final path.
                    receipt=binding.get('source_evidence_receipt_sha256')
                    if receipt:
                        matches=[a for a in binding['assets'] if a['sha256']==receipt and a['workspace_path'].endswith('/receipt.json')]
                        if len(matches)!=1: raise PublicationError('source evidence is missing its retained receipt')
                        src=bound(layout,layout.path(matches[0]['workspace_path']),receipt)
                        measurement=read_json(src);collect_refs(layout,measurement,paths,hashes)
                        for row in measurement['recipe']['inputs']:
                            paths.add(measurement_input(row,measurement['recipe'],layout))
    return paths,hashes,versions,receipts


def registered_refs(layout,paths,hashes):
    # A manual job may explicitly have used an automatic intermediate as reads. Non-published
    # jobs/diagnostic records are not targets, but their input and evidence references still count.
    for tool in TOOL_DIRECTORIES:
        base=layout.tool_relative('04_refinement',tool)
        patterns=(('02_jobs','*/invocation.json'),('02_jobs','*/'+NAME),('05_report','*/*/summary.json'))
        for parent,pattern in patterns:
            for file in layout.path(base+'/'+parent).glob(pattern):
                info=read_json(regular(layout,file))
                if file.name==NAME: info={k:info[k] for k in ('input_dependencies','result')}
                collect_refs(layout,info,paths,hashes)
    manual=layout.path('04_refinement/manual')
    # Reads passed on the command line need not appear in the exported task manifest.
    # Include every attempt, even one that failed before writing a completion record.
    for pattern in (
        '*/01_inputs/refinement_tasks.json', '*/01_inputs/*/prepared.json',
        '*/02_jobs/*/*/*/invocation.json', '*/02_jobs/*/*/*/completion.json',
        '*/manual-delivery.json', '*/03_report/summary.json',
    ):
        for file in manual.glob(pattern):
            collect_refs(layout, read_json(regular(layout, file)), paths, hashes)


def alias_targets(root,candidates):
    """A read-only symlink elsewhere in the job may point into an otherwise disposable copy."""
    if not candidates:return set()
    dirs={d for p in candidates for d in p.parents if d.is_relative_to(root)}
    hits=set()
    def problem(exc): raise exc
    for directory,children,names in os.walk(root,followlinks=False,onerror=problem):
        for name in children+names:
            p=Path(directory)/name
            if not p.is_symlink(): continue
            target=p.resolve()
            if target in candidates: hits.add(target)
            if target in dirs: hits.update(c for c in candidates if c.is_relative_to(target))
    return hits


def inspect_tool(layout,tool,journal,delivered,protected,hashes):
    if not journal: return [],'no committed tool publication'
    # A repeated run id alone does not identify the published tool projection.
    manifest_sha = journal['areas']['delivery']['new']['files'].get('light/' + TOOL_MANIFEST)
    if (not isinstance(manifest_sha, str) or not HEX.fullmatch(manifest_sha)
            or delivered != {'run_id': journal['run_id'], 'light_manifest': manifest_sha}):
        raise PublicationError(f'{tool} is not the generation in the committed Full/Light pair')
    path=targets(layout,tool)['final']/'provenance.json'
    prov=read_json(bound(layout,path,journal['areas']['final']['new']['files']['provenance.json']))
    origin=prov['execution'].get('native_origin')
    if not origin: return [],'no completed native producer'
    run=origin['run_id']
    if not re.fullmatch('[a-f0-9]{32}',run): raise PublicationError('invalid native run id')
    base=layout.tool_relative('04_refinement',tool); native=f'{base}/03_native/{run}'; jobs=f'{base}/02_jobs/{run}'
    marker=jobs+'/'+NAME
    if origin['native_root']!=native or origin['receipt']!=marker: raise PublicationError('foreign native origin')
    proof=read_json(bound(layout,layout.path(marker),origin['receipt_sha256'])); checksum=proof.pop('payload_sha256')
    if (checksum!=fingerprint(proof) or proof.get('schema')!=NATIVE_SCHEMA or proof.get('schema_version')!=1
        or proof.get('status')!='completed' or proof['tool']!=tool or proof['run_id']!=run or proof['native_root']!=native
        or proof['attempt_paths']['03_native']!=str(layout.path(native)) or proof['attempt_paths']['02_jobs']!=str(layout.path(jobs))):
        raise PublicationError('invalid native scratch owner')
    artifacts=proof['result']['artifacts'];collect_refs(layout,proof['input_dependencies'],protected,hashes)
    copies={};known={}
    for name,sha in artifacts.items():
        if not (name.startswith(jobs+'/') or name.startswith(native+'/')): raise PublicationError('foreign native artifact')
        p=bound(layout,layout.path(name),sha); protected.add(p); hashes.add(sha)
        if name.startswith(jobs+'/native_units/') and p.stat().st_nlink==1: copies.setdefault(sha,name)
        if name.startswith(native+'/'): known[name[len(native)+1:]]=sha
    recorded=proof.get('scratch_inventory',{})
    if recorded and (recorded.get('policy')!=POLICY or not isinstance(recorded.get('files'),dict) or len(recorded['files'])>MAX_FILES):
        raise PublicationError('unsupported native scratch inventory')
    files=recorded.get('files',{});actions=[]
    # DEGAP top-level read copies can also serve unsuccessful child diagnostics.
    children=(proof['result'].get('native_jobs') or {}).get('jobs',[]) if tool=='degap' else []
    complete = tool != 'degap' or (bool(children) and all(child.get('status') == 'success' for child in children))
    for name in sorted(set(files)|set(known)):
        policy=role(tool,relative_path(name)); fact=files.get(name); full=native+'/'+name
        if not policy: continue
        p=layout.path(full)
        try: st=p.lstat()
        except FileNotFoundError: continue # an earlier confirmed cleanup may have removed a rebuildable file
        if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or not st.st_size: continue
        stamp=identity(st)
        if fact and fact.get('identity')!=stamp and name not in known: continue
        sha=sha256_file(p)
        if identity(p.lstat())!=stamp or (name in known and sha!=known[name]): raise PublicationError('unstable native scratch member')
        op='unlink' if complete and fact and fact.get('kind')==policy=='rebuild' and p not in protected and sha not in hashes else 'share'
        entry={'tool':tool,'run':run,'path':full,'op':op,'sha256':sha,'identity':stamp,'size_bytes':st.st_size,'allocated_bytes':st.st_blocks*512}
        if op=='share':
            if sha not in copies: continue
            src=layout.path(copies[sha]); other=src.lstat()
            if st.st_dev!=other.st_dev or st.st_ino==other.st_ino:continue
            entry.update(copy=copies[sha],copy_identity=identity(other))
        actions.append(entry)
    return actions,('no producer inventory; no unlink allowed' if not recorded else 'recorded native intermediates')


def build_plan(root,lock,tools,*,quarantined=()):
    layout=layout_and_lock(root,lock)
    if not layout.project_delivery: raise PublicationError('compaction is only supported for new project-delivery workspaces')
    project,seal=project_state(layout)
    protected,hashes,versions,journals=protected_assets(layout)
    seal['tool_publications']=journals
    registered_refs(layout,protected,hashes)
    files=[];notes={}
    for tool in sorted(tools):
        rows,notes[tool]=inspect_tool(layout,tool,versions.get(tool),project.get('tools',{}).get(tool),protected,hashes)
        files.extend(rows)
    # Include references to scratch in other selected origins before admitting any unlink.
    targets_to_check={layout.path(f['path']) for f in chain(files,quarantined) if f['op']=='unlink'}
    unsafe=alias_targets(root,targets_to_check)|protected
    if any(layout.path(f['path']) in unsafe or f['sha256'] in hashes for f in quarantined if f['op']=='unlink'):
        raise PublicationError('a retained source now references a quarantined file')
    files=[f for f in files if f['op']!='unlink' or (layout.path(f['path']) not in unsafe and f['sha256'] not in hashes)]
    plan={'schema':'cgat.native-compaction-plan.v1','root':str(root),'tools':sorted(tools),'publication':seal,'files':files}
    return {'plan_sha256':fingerprint(plan),'impact':WARNING,'notes':notes,
            'unlink_allocated_bytes':sum(f['allocated_bytes'] for f in files if f['op']=='unlink'),
            'share_candidate_bytes':sum(f['identity'][2] for f in files if f['op']=='share'),**plan}
