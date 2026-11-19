"""Launch a hash-verified incident script under a per-process Linux AS limit.

Not a cgroup/group RSS limit. Does not modify an already-running process or add
mapper timeouts. Parent helper, mapper and restoration descendants inherit the
limit. Failure remains a failure; this wrapper never publishes batch success.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import stat
import sys

MAX_LIMIT_BYTES = 64 * 1024**3


def execute(script, expected_sha256, limit_bytes):
    if not sys.platform.startswith('linux') or not hasattr(resource,'RLIMIT_AS'):
        raise ValueError('Linux address-space enforcement is required')
    if type(limit_bytes) is not int or not 0 < limit_bytes <= MAX_LIMIT_BYTES:
        raise ValueError('invalid bounded address-space limit')
    script=Path(script)
    if not script.is_absolute() or script.is_symlink():
        raise ValueError('expected an absolute regular frozen script')
    fd=os.open(script,os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):raise ValueError('script is not a regular file')
        digest=hashlib.sha256()
        while True:
            data=os.read(fd,1024*1024)
            if not data:break
            digest.update(data)
        after=os.fstat(fd)
        signature=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if signature(before)!=signature(after) or digest.hexdigest()!=expected_sha256:
            raise ValueError('frozen script changed before resource admission')
        _soft,hard=resource.getrlimit(resource.RLIMIT_AS)
        if hard!=resource.RLIM_INFINITY and hard<limit_bytes:
            raise ValueError('inherited hard limit is below the staged request')
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_AS,(limit_bytes,limit_bytes))
        if resource.getrlimit(resource.RLIMIT_AS)!=(limit_bytes,limit_bytes):
            raise ValueError('address-space limit did not take effect')
        os.lseek(fd,0,os.SEEK_SET);os.set_inheritable(fd,True)
        print('SELF_RESOURCE_GUARD',json.dumps({'scope':'per_process_virtual_address_space',
            'limit_bytes':limit_bytes,'script_sha256':expected_sha256,'time_limit_added':False}),flush=True)
        # Use the verified open inode, not a pathname that might be replaced.
        # Generated incident scripts use absolute paths, never dirname($0).
        os.execv('/bin/bash',['bash',f'/proc/self/fd/{fd}'])
    finally:
        os.close(fd)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--limit-bytes',type=int,required=True)
    args=parser.parse_args()
    execute(args.script,args.sha256,args.limit_bytes)
