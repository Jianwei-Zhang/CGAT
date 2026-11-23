#!/usr/bin/env python3
"""Preview native scratch compaction; changing files requires the exact preview digest."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import errno
import fcntl
import json
import os
from pathlib import Path
import platform
import re
import stat
import struct
import sys
import uuid

from refinement_compact_plan import build_plan, HEX
from refinement_commit import PublicationError, layout_and_lock, read_json
from refinement_scratch import identity, role
from refinement_tools import fingerprint
from run_all_runner import RunnerError, WorkspaceLock, new_run_id
from run_orchestration import sha256_file
from workspace_layout import relative_path, TOOL_DIRECTORIES, WorkspaceLayout
from workspace_migration import durable_json, ensure_directory, sync_directories

HOME='.runtime/refinement/compaction'
PLAN_KEYS=('schema','root','tools','publication','files')
DIR=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
UNSUPPORTED={errno.EOPNOTSUPP,errno.ENOTTY,errno.ENOSYS,errno.EINVAL,errno.EPERM,errno.EACCES,errno.EXDEV}


def mount_id(fd):
    for line in Path(f'/proc/self/fdinfo/{fd}').read_text().splitlines():
        if line.startswith('mnt_id:'): return int(line.split(':',1)[1])
    raise PublicationError('cannot establish Linux mount identity for compaction')


@contextmanager
def directory_fd(root, directory):
    """Pin every parent directory on the workspace mount, including during crash recovery."""
    with ExitStack() as stack:
        parent = os.open(root, DIR)
        stack.callback(os.close, parent)
        mount = mount_id(parent)
        for part in directory.relative_to(root).parts:
            if relative_path(part) != part: raise PublicationError('invalid maintenance directory')
            parent = os.open(part, DIR, dir_fd=parent)
            stack.callback(os.close, parent)
            if mount_id(parent) != mount: raise PublicationError('compaction cannot cross a mount')
        yield parent


@contextmanager
def member_fd(root,name,flags=os.O_RDONLY):
    path = root / relative_path(name)
    with directory_fd(root,path.parent) as parent:
        fd = os.open(path.name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or mount_id(fd) != mount_id(parent):
                raise PublicationError('not a private regular file on the job filesystem')
            yield parent,path.name,fd
        finally: os.close(fd)


def share(root,row):
    # Linux fs.h: FIDEDUPERANGE uses a 24-byte header and a 32-byte per-destination result.
    # The kernel compares the ranges; later writes are copy-on-write, never hard-linked.
    if platform.machine().lower() not in ('aarch64','arm64','x86_64','amd64'): return 0,'unsupported ABI'
    with member_fd(root,row['copy']) as (_,__,src), member_fd(root,row['path'],os.O_RDWR) as (_,__,dst):
        if identity(os.fstat(src))!=row['copy_identity'] or identity(os.fstat(dst))!=row['identity']:
            raise PublicationError('extent-sharing input changed after preview')
        size=row['identity'][2]; pos=0
        while pos<size:
            n=min(16*1024**2,size-pos)
            arg=bytearray(struct.pack('=QQHHIqQQiI',pos,n,1,0,0,dst,pos,0,0,0))
            try: fcntl.ioctl(src,0xc0189436,arg,True)
            except OSError as e:
                if e.errno in UNSUPPORTED: return pos,'unsupported by filesystem or permissions'
                raise
            done,status=struct.unpack_from('=Qi',arg,40)
            if status<0 and -status in UNSUPPORTED: return pos,'unsupported by filesystem or permissions'
            if status!=0 or done>n: raise PublicationError(f'kernel refused equal-range sharing: status={status}')
            if not done: return pos,'no further shareable extent'
            pos+=done
        return pos,'shared ranges (not a measurement of freed disk space)'


def check_plan(layout,p):
    if (p['schema']!='cgat.native-compaction-plan.v1' or p['root']!=str(layout.root)
        or fingerprint({k:p[k] for k in PLAN_KEYS})!=p['plan_sha256'] or not HEX.fullmatch(p['plan_sha256'])):
        raise PublicationError('invalid stored compaction plan')
    names=set()
    for r in p['files']:
        tool,run=r['tool'],r['run']
        if tool not in TOOL_DIRECTORIES or not re.fullmatch('[a-f0-9]{32}',run):raise PublicationError('invalid native attempt')
        base=layout.tool_relative('04_refinement',tool); prefix=f'{base}/03_native/{run}/'
        path=relative_path(r['path']);policy=role(tool,path[len(prefix):]) if path.startswith(prefix) else None
        if (not policy or path in names or r['op'] not in ('unlink','share') or r['op']=='unlink' and policy!='rebuild'
            or not HEX.fullmatch(r['sha256'])):raise PublicationError('unsupported or duplicate compaction action')
        if r['op']=='share' and not relative_path(r['copy']).startswith(f'{base}/02_jobs/{run}/native_units/'):
            raise PublicationError('extent copy is not a sealed native unit member')
        names.add(path)


def move_one(layout,row,hold,index):
    with member_fd(layout.root,row['path']) as (parent,name,fd):
        if identity(os.fstat(fd))!=row['identity']: raise PublicationError('scratch changed after preview')
        with directory_fd(layout.root,hold) as dest:
            slot=str(index)
            if os.path.lexists(hold/slot):raise PublicationError('unexpected occupied holding slot')
            os.rename(name,slot,src_dir_fd=parent,dst_dir_fd=dest)
            os.fsync(parent);os.fsync(dest)
            # Rename changes ctime. Check the still-open original fd, retained bytes and inode
            # BEFORE authorizing deletion; a racing replacement is held, not destroyed.
            if not os.path.samestat(os.fstat(fd),os.stat(slot,dir_fd=dest,follow_symlinks=False)) or not intact(hold/slot,row):
                raise PublicationError('quarantined file differs from the preview; retaining it for recovery')


def intact(path,row):
    st=path.lstat()
    return stat.S_ISREG(st.st_mode) and identity(st)[:4]==row['identity'][:4] and sha256_file(path)==row['sha256']


def finish(layout,home,state):
    p=state['plan'];check_plan(layout,p);op=state['operation']
    if not re.fullmatch('[0-9a-f]{32}',op) or state['state'] not in ('prepared','committed'):
        raise PublicationError('invalid compaction journal')
    active=home/'pending.json';hold=layout.path(f'{HOME}/hold-{op}'); committed=state['state']=='committed'
    if hold.is_symlink() or hold.exists() and not hold.is_dir():raise PublicationError('invalid compaction holding directory')
    files=[(i,r) for i,r in enumerate(p['files']) if r['op']=='unlink'];slots={str(i) for i,_ in files}
    if hold.is_dir() and any(s.name not in slots for s in hold.iterdir()): raise PublicationError('unowned compaction holding member')
    unconfirmed=[]
    for i,r in files:
        path=layout.path(r['path']);slot=hold/str(i)
        if not os.path.lexists(slot):
            if not committed and (not os.path.lexists(path) or not intact(path,r)):
                # No holding slot was erased before commit; don't overwrite a changed/removed
                # original just because the stale preview mentioned it. Report it separately.
                unconfirmed.append(r['path'])
            continue
        st=slot.lstat()
        if not stat.S_ISREG(st.st_mode) or identity(st)[:2]!=r['identity'][:2] or committed and not intact(slot,r):
            raise PublicationError(f'holding slot differs from receipt; preserved at {slot} (original path: {path})')
        with directory_fd(layout.root,hold) as held:
            if not os.path.samestat(st,os.stat(slot.name,dir_fd=held,follow_symlinks=False)):
                raise PublicationError('holding slot changed during recovery')
            if not committed:
                with directory_fd(layout.root,path.parent) as dst:
                    try: os.link(slot.name,path.name,src_dir_fd=held,dst_dir_fd=dst,follow_symlinks=False)
                    except FileExistsError: pass
                    if not os.path.samestat(st,os.stat(path.name,dir_fd=dst,follow_symlinks=False)):
                        raise PublicationError(f'cannot restore over another file: {path}; preserved at {slot}')
                    os.fsync(dst)
            os.unlink(slot.name,dir_fd=held);os.fsync(held)
    if hold.exists():hold.rmdir();sync_directories(home)
    result={'operation':op,'state':'completed' if committed else 'rolled_back','plan_sha256':p['plan_sha256'],
            'unlink_count':len(files) if committed else 0, 'unlinked_allocated_bytes':p['unlink_allocated_bytes'] if committed else 0,
            'unchanged_by_recovery_but_no_longer_matching_preview':unconfirmed,'shared':state.get('shared',[]),'receipt':str(home/(op+'.json'))}
    durable_json(home/(op+'.json'),{**result,'plan':p});active.unlink();sync_directories(home)
    return result


def compact(root,tools,apply=None,recover=None):
    root=Path(root).resolve(); layout=WorkspaceLayout.detect(root)
    if not layout.project_delivery:raise PublicationError('this command only operates on new project-delivery jobs')
    home=layout.path(HOME); active=layout.path(HOME+'/pending.json')
    lock=WorkspaceLock(root,new_run_id());lock.acquire()
    try:
        layout_and_lock(root,lock)
        if active.exists() or active.is_symlink():
            state=read_json(active);token=state['plan']['plan_sha256']
            if recover!=token: raise PublicationError(f'compaction interrupted; recover this operation first: --recover {token}')
            if state.get('state')=='committed':
                check_plan(layout,state['plan'])
                build_plan(root,lock,state['plan']['tools'],quarantined=state['plan']['files'])
            return finish(layout,home,state)
        if recover:raise PublicationError('no pending compaction operation')
        plan=build_plan(root,lock,tools)
        if not apply:return plan
        if apply!=plan['plan_sha256']:raise PublicationError('preview no longer matches this job/tool set; nothing changed, preview again')
        if not plan['files']:return {'state':'nothing_to_compact','plan_sha256':apply}
        check_plan(layout,plan);ensure_directory(home);op=uuid.uuid4().hex;hold=layout.path(f'{HOME}/hold-{op}')
        state={'operation':op,'state':'prepared','plan':plan,'shared':[]};durable_json(active,state)
        try:
            hold.mkdir(mode=0o700);sync_directories(home)
            for i,r in enumerate(plan['files']):
                if r['op']=='unlink': move_one(layout,r,hold,i)
                else:
                    try: count,why=share(root,r)
                    except OSError as exc:
                        if exc.errno not in UNSUPPORTED|{errno.EROFS}: raise
                        count,why=0,'not supported or not permitted'
                    state['shared'].append({'path':r['path'],'bytes':count,'status':why})
            # A missing public/archive/measurement dependency aborts before the first byte is erased.
            check=build_plan(root,lock,tools,quarantined=plan['files'])
            if check['publication']!=plan['publication']:raise PublicationError('published ownership changed during compaction')
            layout_and_lock(root,lock)
        except Exception:
            finish(layout,home,state);raise
        state['state']='committed';durable_json(active,state)
        return finish(layout,home,state)
    finally: lock.release()


def main():
    ap=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    ap.add_argument('--out',type=Path,default=Path.cwd(),help='project job root (default: current directory)')
    ap.add_argument('--tool',choices=sorted(TOOL_DIRECTORIES),action='append',help='limit the preview/application to this tool; repeatable')
    group=ap.add_mutually_exclusive_group();group.add_argument('--apply',metavar='PLAN_SHA256');group.add_argument('--recover',metavar='PLAN_SHA256')
    args=ap.parse_args()
    try:
        if any(v is not None and not HEX.fullmatch(v) for v in (args.apply,args.recover)):raise ValueError('use the full 64-character plan SHA-256')
        layout=WorkspaceLayout.detect(args.out)
        if not layout.project_delivery or layout.path('.lib/tools/compact_refinement.py')!=Path(__file__).resolve():
            raise PublicationError("use this project's own .lib/tools/compact_refinement.py on a new project-delivery job")
        print(json.dumps(compact(args.out,set(args.tool or TOOL_DIRECTORIES),args.apply,args.recover),indent=2,ensure_ascii=False));return 0
    except (OSError,ValueError,RunnerError,KeyError,TypeError) as exc:
        print(f'compaction refused: {exc}',file=sys.stderr);return 2


if __name__=='__main__': sys.exit(main())
