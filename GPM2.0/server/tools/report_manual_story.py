"""Reconstruct display coordinates, not bases, from the submitted App snapshot and sealed choices."""
from collections import defaultdict
import json
import hashlib
from zipfile import BadZipFile, ZipFile

from manual_genome import names, winners
from manual_snapshot import FILE, LIMIT, load_snapshot
from refine import MANIFEST, MAX_MANIFEST, check_manifest
from refinement_tools import fingerprint
from report_gap_story import PRIORITY, checked_json
from report_final_story import check_fasta
from report_inventory import SHA, physical
from report_q0_tracks import label
from run_orchestration import sha256_file


REASONS={
    'original_gap_unchanged':('候选与原 gap 相同。','The candidate left the gap unchanged.'),
    'native_candidate_contains_only_ns':('候选仍全为 N。','The candidate contains only Ns.'),
    'incomplete_gap_kept_original':('候选含残留 N，整个原 gap 保留。','The candidate still contained Ns; the entire original gap was kept.'),
    'native_candidate_requires_flank_change':('候选改变了侧翼，未采用。','The candidate changed a flank and was not admitted.'),
    'no_positive_terminal_extension':('没有产生正长度的延伸。','There was no positive terminal extension.'),
    'native_candidate_changes_original_endpoint':('候选改变了原始末端。','The candidate changed the original endpoint.'),
    'terminal_extension_contains_ns':('延伸片段中仍有 N。','The extension still contained Ns.'),
    'native_patch_exceeds_size_limit':('候选超过接纳长度上限。','The candidate exceeded the admission size limit.'),
    'native_execution_or_evidence_failed':('工具执行或证据检查失败。','Tool execution or evidence validation failed.'),
    'runtime_or_input_check_failed':('运行环境或输入检查失败。','The runtime or input check failed.'),
}


def attempt_row(row):
    status=label(row['status']);tool=label(row['tool']);patch=row.get('patch');item=dict(tool=tool,status=status,reason=row.get('reason') if row.get('reason') in REASONS else None,patch=None)
    if patch and 'length' in patch:
        if (patch['operation'] not in ('replace_gap','prepend_tel','append_tel') or type(patch['length']) is not int
            or patch['length']<0 or not SHA.fullmatch(patch['sha256']) or type(patch['original_length']) is not int or patch['original_length']<=0):
            raise ValueError('invalid manual patch metadata')
        item['patch']={k:patch[k] for k in ('length','sha256','operation','original_length')}
    return item


def project_snapshot(snapshot, manifest, selection, rows):
    chosen=winners(manifest,rows); selected={k:r['tool'] if r else None for k,r in chosen.items()}
    if selected!=selection['selected']:raise ValueError('selection differs from admitted task results')
    by_target=defaultdict(dict); by_locus=defaultdict(list); scenes={};tracks=[]
    for r in rows:by_locus[r['locus_id']].append(attempt_row(r))
    for l in manifest['loci']:
        lid=l['id'];by_target[l['chr'],l['target']][l['kind']]=lid
        scenes[lid]=dict(id=lid,chr=label(l['chr']),target=label(l['target']),kind=l['kind'],selected=selected[lid],
                         attempts=sorted(by_locus[lid],key=lambda r:(r['status'] not in ('closed','extended'),PRIORITY.index(r['tool']))))
    for c in snapshot['chromosomes']:
        chrom=label(c['chr']);old=new=0;original=[];after=[];loci=[];changed=0
        for part in c['segments']:
            w=part['witness'];sid=label(w['segment_id']); plan=part['plan'];kind=w['kind'];target=by_target.pop((chrom,sid),{})
            size=w['gap_bp'] if kind=='gap' else abs(w['start']-w['end'])+1
            members=[]
            if plan:
                rev=plan['start']>plan['end']; strand='-' if rev else '+'
                for m in reversed(plan['members']) if rev else plan['members']:
                    members.append([label(m['dataset']),label(m['name']),m['start']-1,m['end'],strand])
            original.append(dict(id=sid,kind=kind,start=old,end=old+size,members=members,loci=list(target.values())))
            for k in ('tel_left','gap','tel_right'):
                lid=target.get(k)
                if lid:
                    sc=scenes[lid];sc['before']=[old,old+size];loci.append(lid);r=chosen[lid]
                    if r:
                        p=r['patch'];op={'gap':'replace_gap','tel_left':'prepend_tel','tel_right':'append_tel'}[k]
                        if p['original_length']!=size or p['operation']!=op:raise ValueError('manual patch targets another interval')
                        sc['after']=[new,new+p['length']];changed+=1
                        after.append(dict(id=sid,kind=k,start=new,end=new+p['length'],loci=[lid],adopted=True,members=[]));new+=p['length']
                    else:sc['after']=None
                if k=='gap' and not (lid and chosen[lid]):
                    after.append(dict(original[-1],start=new,end=new+size,adopted=False));new+=size
            old+=size
        stat=selection['chromosomes'][chrom]
        if new!=stat['length'] or not SHA.fullmatch(stat['sha256']):raise ValueError('manual display geometry disagrees with the delivered chromosome')
        tracks.append(dict(chr=chrom,length=new,original_length=old,changed=changed,before=original,after=after,loci=loci))
    if by_target or set(selection['chromosomes'])!={r['chr'] for r in tracks}:raise ValueError('manual output chromosome set changed')
    return dict(tracks=tracks,loci=scenes)


def collect_manual_story(layout, batch, directory, summary, owner, owned, verify_content=False):
    if owner.get('schema')=='cgat.manual-genome-publication.v1' and not owned:
        raise ValueError('manual genome receipt has no matching batch summary')
    if not owned or owner.get('schema')!='cgat.manual-genome-publication.v1':
        # A legacy patch bundle is not a whole-genome publication. No implied winner.
        from refine_report import manual_patch_path
        path=physical(layout.root,manual_patch_path(layout,batch).relative_to(layout.root).as_posix())
        legacy=[]; locations=summary.get('loci',{}); verified=False
        try:
            if not path.is_file() or summary.get('delivery')!=path.relative_to(layout.root).as_posix():raise ValueError('no matching local return bundle')
            with ZipFile(path) as z:
                entry=z.getinfo('refinement_results.json')
                if entry.file_size>LIMIT:raise ValueError('oversize legacy result')
                result=json.loads(z.read(entry))
            if result.get('batch_sha256')!=batch or result.get('schema')!='cgat.app-refinement-results.v1':raise ValueError('legacy result identity mismatch')
            if owned and owner.get('result'):
                if fingerprint(result)!=owner['result']:raise ValueError('legacy owner mismatch')
            elif sha256_file(path)!=summary.get('delivery_sha256'):raise ValueError('legacy return bundle changed')
            for row in result['results']:
                item=attempt_row(row);lid=label(row['locus_id']);loc=locations.get(lid,{})
                # The exported locus ID hashes these three fields. A re-edited
                # report cannot attach a genuine tool outcome to a different chr.
                coords=[loc.get(k) for k in ('chr','kind','target')]
                bound=all(isinstance(x,str) for x in coords) and hashlib.sha256(json.dumps(coords,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()==lid
                item.update(chr=label(coords[0]) if bound else None,target=label(coords[2]) if bound else lid)
                legacy.append(item)
            verified=True
        except (OSError,ValueError,TypeError,KeyError,BadZipFile):legacy=[]
        return dict(tracks=None,legacy=legacy,loci={},legacy_verified=verified)
    files=names(layout,batch);hashes=owner['files']; home=directory.relative_to(layout.root).as_posix()
    check_fasta(layout,files['fasta'].relative_to(layout.root).as_posix(),hashes['fasta'],owner,verify_content)
    patch=physical(layout.root,files['patch'].relative_to(layout.root).as_posix())
    if not patch.is_file() or verify_content and sha256_file(patch)!=hashes['patch']:raise ValueError('manual delivery changed')
    path=files['details'].relative_to(layout.root);selection=checked_json(layout,path.parent.as_posix(),path.name,{path.name:hashes['details']})
    mpath=physical(layout.root,home+'/01_inputs/'+MANIFEST)
    if mpath.stat().st_size>MAX_MANIFEST:raise ValueError('oversize manual task manifest')
    manifest=checked_json(layout,home+'/01_inputs',MANIFEST,{MANIFEST:batch})
    check_manifest(manifest)
    spath=physical(layout.root,home+'/01_inputs/snapshot/'+FILE)
    if spath.stat().st_size>LIMIT:raise ValueError('oversize snapshot')
    snap=load_snapshot(spath.read_bytes(),manifest)  # No read sequences or temporary reconstruction needed.
    with ZipFile(files['patch']) as z:
        entry=z.getinfo('refinement_results.json')
        if entry.file_size>LIMIT:raise ValueError('oversize manual result manifest')
        result=json.loads(z.read(entry))
    if (fingerprint(result)!=owner['result'] or result['batch_sha256']!=batch or selection['batch_sha256']!=batch
        or selection['schema']!='cgat.manual-genome-selection.v1' or selection['origin_fasta_sha256']!=manifest['origin_fasta_sha256']
        or not owner['snapshot_sha256']==manifest['snapshot_sha256']==selection['snapshot_sha256']==result['assembly']['snapshot_sha256']
        or selection['selected']!=result['assembly']['selected'] or not selection['genome_sha256']==hashes['fasta']==result['assembly']['genome_sha256']):
        raise ValueError('manual snapshot, result and publication identities disagree')
    return project_snapshot(snap,manifest,selection,result['results'])
