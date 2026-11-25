"""Read-only, complete Final Path preview from the current publication, never an N-count delta."""
import csv
from pathlib import PurePosixPath

from report_gap_story import checked_json, source
from report_inventory import SHA, obj, physical
from report_q0_tracks import label
from run_orchestration import file_signature, sha256_file
from workspace_layout import TOOL_DIRECTORIES


def source_lengths(layout, folder, files):
    if 'sources.tsv' not in files:
        return {}
    p = physical(layout.root, folder + '/sources.tsv'); sig = file_signature(p)
    if sha256_file(p) != files['sources.tsv']:
        raise ValueError('committed source catalog changed')
    sizes = {}
    with p.open(encoding='utf-8', newline='') as h:
        for row in csv.DictReader(h, delimiter='\t'):
            key = label(row['dataset']), label(row['contig']); n = int(row['length'])
            if n <= 0 or key in sizes: raise ValueError('invalid committed source catalog')
            sizes[key] = n  # Never export path, sequence, or private catalog columns.
    if file_signature(p) != sig: raise ValueError('source catalog changed while reading')
    return sizes


def project_path(final, sizes, *, refined):
    rows = []; seen = set(); sids = set()
    edits = {e['edit_id']: e for e in final.get('edits', [])}
    for c in final['chromosomes']:
        chrom = label(c['chr']); n = c['length' if refined else 'q4_length']; sha = c['sha256' if refined else 'q4_sha256']
        if chrom in seen or type(n) is not int or n <= 0 or not SHA.fullmatch(sha):
            raise ValueError('invalid final chromosome')
        seen.add(chrom); pos = 0; parts = []
        for s in c['segments']:
            sid = label(s['segment_id']); size = s['length']; kind = label(s['kind'])
            if sid in sids or type(size) is not int or size <= 0: raise ValueError('invalid final segment')
            sids.add(sid); end = pos + size
            if refined and (s['output_start'], s['output_end']) != (pos, end):
                raise ValueError('discontinuous committed output track')
            src = source(s.get('source') if kind != 'gap' else s.get('refinement_source'))
            if not src and kind != 'gap': raise ValueError('source-backed segment lacks coordinates')
            if src:
                x,y = src['span']; full = sizes.get((src['dataset'],src['name']))
                if y-x != size or full is not None and y>full or s.get('orientation',src['strand'])!=src['strand']:
                    raise ValueError('invalid adopted source slice')
                src['length'] = full
            eid = s.get('refinement_edit_id'); gids = []
            if eid:
                e=edits[eid]; gids = [label(v) for v in e['gap_ids']]
                if (sid not in e['replacement_segment_ids'] or e['chromosome']!=chrom or not e['output_start']<=pos<end<=e['output_end']
                        or set(gids)!=set(s['original_gap_ids'])): raise ValueError('unbound refinement segment')
            parts.append(dict(start=pos,end=end,kind=kind,source=src,edit=label(eid) if eid else None,gaps=gids));pos=end
        if pos!=n: raise ValueError('final segment length differs from chromosome')
        rows.append(dict(chr=chrom,length=n,sha256=sha,parts=parts))
    if not rows: raise ValueError('missing complete chromosome paths')
    return rows


def recorded_output(server_directory, relative):
    # Only the publication-time output directory may locate a file on the server.
    if not isinstance(server_directory,str) or not relative.startswith('05_final/'):
        return relative, False
    home = PurePosixPath(server_directory)
    if not home.is_absolute() or home.name!='05_final' or '..' in home.parts or any(ord(c)<32 for c in server_directory):
        return relative, False
    return str(home / relative.removeprefix('05_final/')), True


def supplied_version(layout, tool, receipt, files, final, *, quick, transaction, edits):
    code = '00_lgz' if tool=='lgz' else TOOL_DIRECTORIES[tool]; folder=layout.relative('05_final/'+code)
    expected = files.get('assembly.fa'); detail = folder+'/assembly.fa'
    if not SHA.fullmatch(expected or '') or sha256_file(physical(layout.root,detail)) != expected:
        raise ValueError('published FASTA differs from receipt')
    relative = detail
    if layout.result_prefix:
        public=f'05_final/{layout.result_prefix}.{tool}.fa'
        # The overview can be generated before the direct-name catalog transaction.
        # Its committed details FASTA is still valid. Never borrow a previous public version.
        if quick.get(tool,{}).get('publication_verified') and quick[tool]['relpath']==public and quick[tool]['sha256']==expected:
            from job_final_catalog import _read_catalog
            auto,_ = _read_catalog(layout)
            if any(r[0]==tool and r[7]==transaction and r[6]==expected for r in auto):
                p=physical(layout.root,public)
                if not p.samefile(physical(layout.root,detail)) and sha256_file(p)!=expected: raise ValueError('public FASTA changed')
                relative=public
    path, absolute = recorded_output(receipt.get('server_final_directory'), relative)
    try:
        tracks=project_path(final,source_lengths(layout,folder,files),refined=tool!='lgz')
    except (KeyError,TypeError,ValueError):
        tracks=None  # Old jobs can have a committed FASTA but no complete track geometry.
    return dict(tool=tool, fasta=path, absolute=absolute, sha256=expected, edits=edits, tracks=tracks)


def final_versions(layout, lgz, ref, batch, pickup, mode):
    if mode in ('lgz_failed','manual_only') or (batch or {}).get('status')=='invalidated': return []
    quick={r['label_key']:r for r in pickup if r['category']=='fasta'}
    if ref['tools']:
        from refinement_commit import current_publication
        versions=[]
        for t in ref['tools']:
            if not t['publication_verified']: continue
            tool=t['tool'];j=current_publication(layout.root,tool,verify=False); rec=batch['tools'][tool]
            if not j or (j['transaction'],j['run_id'])!=(rec['publication_transaction'],t['run_id']): continue
            f=j['areas']['final']['new']['files'];folder=layout.relative('05_final/'+TOOL_DIRECTORIES[tool]);final=checked_json(layout,folder,'final_path.json',f)
            versions.append(supplied_version(layout,tool,j,f,final,quick=quick,transaction=j['transaction'],edits=t.get('accepted_edit_count')))
        return versions
    if layout.version==2:
        pointer=layout.relative('.runtime/refinement/lgz_baseline.json')
        if not physical(layout.root,pointer).is_file(): return []
        r=obj(layout.root,pointer)
        if r.get('schema')!='cgat.lgz-baseline-publication' or r.get('state')!='committed': return []
        f=r['files']['files'];binding=r['binding'];folder=layout.relative('05_final/00_lgz')
        if (binding.get('assembly_sha256'),binding.get('final_path_sha256'))!=(f.get('assembly.fa'),f.get('final_path.json')): return []
        # Bind this baseline to the report's run or invocation instead of accepting a stale directory.
        seal=(batch or {}).get('baseline_inputs') or {}; original=str(layout.path('metadata/grt_final_path.json'))
        if (original in seal and seal[original]!=f['final_path.json'] or lgz.get('final_fasta_sha256') not in (None,f['assembly.fa'])
                or not (seal.get(original)==f['final_path.json'] or lgz.get('final_fasta_sha256')==f['assembly.fa'])): return []
        final=checked_json(layout,folder,'final_path.json',f)
        return [supplied_version(layout,'lgz',r,f,final,quick=quick,transaction=f['final_path.json'],edits=None)]
    ck='grt/checkpoints/finalize.json'
    if not physical(layout.root,ck).is_file():return []
    r=obj(layout.root,ck);f=r.get('output_hashes',{});raw='metadata/grt_final_path.json'
    if r.get('status')!='success' or r.get('stage')!='finalize' or raw not in f:return []
    final=checked_json(layout,'metadata','grt_final_path.json',{'grt_final_path.json':f[raw]});rel=final['q4_relpath']
    if rel not in ('grt/q/q3.fa','grt/q/q4.fa') or not f.get(rel) or lgz.get('final_fasta_sha256')!=f[rel] or sha256_file(physical(layout.root,rel))!=f[rel]:return []
    return [dict(tool='lgz',fasta=rel,absolute=False,sha256=f[rel],edits=None,tracks=project_path(final,{},refined=False))]
