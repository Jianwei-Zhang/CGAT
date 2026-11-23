"""Record disposable native intermediates at producer completion; no pruning in the job path."""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat

try:
    from workspace_layout import relative_path
except ModuleNotFoundError:
    from .workspace_layout import relative_path

POLICY = 'cgat.native-scratch.v1'
MAX_FILES = 100_000
# Rooted native filenames only. Never glob all FASTA, alignment data, or all of tmp.
# Alignment/correction intermediates may be evidence: only offer COW extent sharing, NOT unlink.
RULES = {
    'degap': (
        ('rebuild', '01.reads_preprocessor', r'(?:hifi|ont)_reads\.idx'),
        ('rebuild', '01.reads_preprocessor/processed_reads', r'(?:hifi|ont)_reads\.(?:fa|fasta)'),
        *(( 'rebuild', f'01.reads_preprocessor/{k}_reads_part', r'[^/]+\.part_\d+\.(?:fa|fasta)(?:\.gz)?') for k in ('hifi','ont')),
    ),
    'lrgapcloser': (
        ('rebuild', 'output', r'(?:LR\.fasta|LR_length|genome_uc\.fasta)'),
        ('rebuild', 'output/tmp', r'x[a-z]{2,}(?:\.(?:fa|fasta))?'),
    ),
    'tgsgapcloser': (('share', '', r'(?:(?:fill|sub|\d+\.\d+)\.paf|ont\.\d+\.\d+\.racon\.fasta)'),),
    'quartet': tuple(('share', sub, r'quartet\.[^/]+\.paf') for sub in ('','tmp')),
}


def identity(st):
    return [st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns]


def role(tool, name):
    p = Path(relative_path(name))
    parent = '' if p.parent == Path('.') else p.parent.as_posix()
    return next((op for op, directory, regex in RULES[tool] if parent == directory and re.fullmatch(regex,p.name)), None)


def capture_scratch(layout, tool, native, artifacts):
    """No extra file-content reads during native execution; hold the workspace lock here."""
    entries = {}
    for sub in sorted({directory for _,directory,_ in RULES[tool]}):
        directory = native/sub
        # Reject redirecting directories, including the native run itself.
        directory = layout.path(directory.relative_to(layout.root).as_posix())
        if directory.is_symlink() or not directory.is_dir():
            continue
        with os.scandir(directory) as children:
            for child in children:
                name = '/'.join(filter(None,(sub,child.name)))
                kind = role(tool,name)
                if not kind:
                    continue
                st = child.stat(follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or not st.st_size: continue
                relative = (native/name).relative_to(layout.root).as_posix()
                entries[name] = {'kind':'share' if relative in artifacts else kind, 'identity':identity(st)}
                if len(entries)>MAX_FILES: raise ValueError('too many scratch members to record')
    return {'policy':POLICY,'files':entries}
