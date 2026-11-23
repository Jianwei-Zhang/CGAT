"""Can an unmodified current reader inherit the original wheat chromosome checkpoints?

Read frozen producer metadata for all units. Copy only the cheapest complete chromosome to
private scratch and exercise the stock reader. This tool cannot migrate or issue a checkpoint.
"""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

from fork_wheat_q0 import copy_bound, member, require, small, write
from run_orchestration import fingerprint
from run_outer_checkpoints import OuterCheckpointManager

SNAP='2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d'
CORE={'workflow','checkpoint_schema_version','execution_engine_version','unit_id','kind',
      'alignment_geometry_version','command_relpath','parameters','tools','inputs'}


def add(rows, by_path):
    for row in rows:
        path=row['path']; p=Path(path); digest=row['sha256']; size=row['size']
        require(not p.is_absolute() and p.as_posix()==path and '..' not in p.parts and '\\' not in path and p.parts and len(digest)==64 and type(size) is int and size>=0,'invalid identity')
        require(len(bytes.fromhex(digest))==32,'invalid digest')
        obj={'path':path,'size':size,'sha256':digest}
        require(by_path.setdefault(path,obj)==obj,'conflicting identities for one path')


def sizes(rows):
    blobs={}
    for row in rows.values():require(blobs.setdefault(row['sha256'],row['size'])==row['size'],'one hash with two sizes')
    return {'paths':len(rows),'logical_bytes':sum(r['size'] for r in rows.values()),'unique_payload_bytes':sum(blobs.values())}


def sealed(path,expected):
    raw=small(path);require(sha256(raw).hexdigest()==expected,'frozen producer bytes changed');return raw


def inventory(control):
    snapshot=json.loads(sealed(member(control,'snapshot.json'),SNAP));source=Path(snapshot['source']); initial={};add(snapshot['files'],initial)
    reader=json.loads(sealed(member(control,'producer/reader.json'),snapshot['producer_reader_sha256'])); units={};all_rows={};ext=Counter()
    for pin in snapshot['producer_checkpoints']:
        raw=sealed(member(control,'producer/'+Path(pin['checkpoint']).name),pin['sha256']); rec=json.loads(raw);p=rec['input_payload'];u=pin['unit']
        require(rec['status']=='success' and p['unit_id']==rec['unit_id']==u and fingerprint(p)==rec['input_fingerprint'],'parent identity mismatch')
        if not u.startswith('q0_chr:'):continue
        require(u not in units and p['kind']=='q0_chromosome_alignments' and CORE<=p.keys(),'invalid chromosome unit')
        extra=tuple(sorted(p.keys()-CORE));require(extra in (('incident_self_execution',),('incident_execution_overrides','incident_self_execution')),'unexpected extension');ext[','.join(extra)]+=1
        rows={};add(p['inputs'],rows);add(rec['outputs'],rows);add(rows.values(),all_rows);units[u]=(pin,raw,rec,rows)
    require(len(units)==22,'incomplete chromosome inventory');both=dict(initial);add(all_rows.values(),both);old={r['sha256'] for r in initial.values()};fresh={p:r for p,r in both.items() if r['sha256'] not in old};require(all(all_rows.get(r['path'])==r for r in reader['additional_inputs']),'extra reader input outside chromosome provenance')
    report={'draft':sizes(initial),'all_chromosome_input_output_rows':sizes(all_rows),'union':sizes(both),'paths_not_in_draft':len(both.keys()-initial.keys()),'unique_bytes_not_in_draft':sizes(fresh)['unique_payload_bytes'],'additional_reader_inputs_in_union':len(reader['additional_inputs']),'producer_extension_fields':dict(ext)}
    return source,reader,units,report


def same_rows(a,b):
    lhs={};rhs={};add(a,lhs);add(b,rhs);return lhs==rhs and len(lhs)==len(a)==len(b)


def probe(control,out):
    root,reader,units,report=inventory(control); require(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(control),'unsafe output')
    unit=min(units,key=lambda u:sizes(units[u][3])['unique_payload_bytes']);pin,raw,rec,rows=units[unit]; cost=sizes(rows);require(unit=='q0_chr:Un' and cost['logical_bytes']<3*(1<<30),'cold trial exceeds bound or scope changed')
    with TemporaryDirectory(dir='/tmp',prefix='wheat-parent-closure-') as tmp:
        private=Path(tmp).resolve();require(shutil.disk_usage(private).free>=cost['logical_bytes']+(8<<30),'insufficient private disk')
        for path,row in sorted(rows.items()):
            src=member(root,path);dst=member(private,path);copy_bound(src,dst,row,80<<20);require(not src.samefile(dst),'private input shares source inode')
        checkpoint=member(private,pin['checkpoint']); checkpoint.parent.mkdir(parents=True,exist_ok=True);checkpoint.write_bytes(raw)
        manager=OuterCheckpointManager(private);prepared=manager.prepare(unit,rec['input_payload']['command_relpath']);require(prepared is not None and prepared.path==checkpoint,'wrong stock checkpoint path')
        accepted,reason=manager.validate(prepared);previous=rec['input_payload'];current=prepared.input_payload; require(current.keys()==CORE,'stock contract changed; reassess')
        differences=sorted(k for k in CORE if previous.get(k)!=current[k]); extra=sorted(previous.keys()-current.keys()); core_outputs=manager._output_identities(prepared); oldouts={r['path']:r for r in rec['outputs']}; corepaths={r['path'] for r in core_outputs}; extra_outputs=[r for r in rec['outputs'] if r['path'] not in corepaths]
        require(all(oldouts.get(r['path'])==r for r in core_outputs),'stock PAF or geometry output differs');require(not accepted and extra,'current reader accepted unexpectedly');require(checkpoint.read_bytes()==raw,'stock reader modified the original')
        additional={r['path']:r for r in reader['additional_inputs']}; labels=Counter(Path(r['path']).name for r in extra_outputs); source_proof=previous['incident_self_execution']; require(source_proof['dependencies']==reader['self_dependencies'] and all(op['unit_id']==unit for op in source_proof['operations']),'parent self profile inconsistent')
        report['cold_trial']={'unit':unit,**cost,'immutable_parent_checkpoint_sha256':pin['sha256'],'original_input_fingerprint':rec['input_fingerprint'],'stock_input_fingerprint':prepared.input_fingerprint,'stock_accepted':accepted,'stock_reason':reason,'core_fields_different':differences,'input_inventory_exact':same_rows(current['inputs'],previous['inputs']),'parent_only_fields':extra,'stock_verified_outputs':len(core_outputs),'parent_outputs':len(oldouts),'extra_outputs_by_filename':dict(labels),'extra_outputs_also_in_reader_declaration':sum(additional.get(r['path'])==r for r in extra_outputs),'producer_self_operations':len(source_proof['operations']),'mapper_calls':0}
    write(out,{'schema':'wheat_parent_checkpoint_fork_closure_v1','snapshot':SNAP,'inventory':report,'limits':'The 22-unit byte budget is metadata only. Only the chosen chromosome closure was copied and hashed. Stock output checks were run independently, not substituted for a successful stock checkpoint. No producer extension was stripped, no new ready or checkpoint issued.'});print(json.dumps(report),flush=True)

if __name__=='__main__':probe(Path(sys.argv[1]).resolve(strict=True),Path(sys.argv[2]).resolve())
