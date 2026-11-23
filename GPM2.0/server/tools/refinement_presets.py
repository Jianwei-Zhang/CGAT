"""Local editable refinement settings, separate from the authenticated tool lock."""
from __future__ import annotations

import os
from pathlib import Path
from stat import S_ISREG
from tempfile import NamedTemporaryFile
import tomllib

try:
    from workspace_layout import WorkspaceLayout
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout

FILENAME = 'gapfill.toml'
TEMPLATE = Path(__file__).with_name('gapfill.default.toml')
LIMITS = {'max_extension_rounds': '--MaximumExtensionRound', 'max_extension_bp': '--MaximumExtensionLength'}


def regular_bytes(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not S_ISREG(info.st_mode) or info.st_size > 64 * 1024:
        raise ValueError(f'{path}: expected a small regular configuration file')
    with path.open('rb') as stream:
        data = stream.read(64 * 1024 + 1)
    if len(data) > 64 * 1024:
        raise ValueError(f'{path}: configuration file is too large')
    return data


def parse(data, path):
    try:
        config = tomllib.loads(data.decode('utf-8'))
        values = config.get('degap', {})
        if set(config) - {'degap'} or not isinstance(values, dict) or set(values) - (set(LIMITS) | {'kmer_filter'}):
            raise ValueError('unknown section or DEGAP setting')
        for name, value in values.items():
            if name == 'kmer_filter':
                if type(value) is not bool:
                    raise ValueError(f'{name} must be true or false')
            elif value != 'unlimited' and (type(value) is not int or value < 1):
                raise ValueError(f'{name} must be a positive integer or "unlimited"')
        return values
    except (ValueError, UnicodeError) as error:
        raise ValueError(f'{path}: {error}') from error


def defaults():
    values = parse(TEMPLATE.read_bytes(), TEMPLATE)
    if set(values) != set(LIMITS) | {'kmer_filter'}:
        raise ValueError(f'{TEMPLATE}: missing a packaged DEGAP default')
    return values


def workspace_file(layout):
    return layout.path(f'.prepare_lib/tools/{FILENAME}')


def effective(root):
    path = workspace_file(WorkspaceLayout.detect(root))
    data = regular_bytes(path)
    return {**defaults(), **(parse(data, path) if data is not None else {})}


def sync_workspace(root):
    """Called under the workflow lock; no writes to the installation or completed runs."""
    layout = WorkspaceLayout.detect(root)
    link = layout.path('.prepare_lib/server-tools.path')
    binding = regular_bytes(link)
    if binding is None:
        return effective(root)
    installed = Path(os.fsdecode(binding).rstrip('\n'))
    if not installed.is_absolute():
        raise ValueError(f'{link}: installation path must be absolute')
    if not (installed / 'run.sh').is_file():
        return effective(root)
    path = installed / 'tools' / FILENAME
    data = regular_bytes(path)
    if data is None:
        data = TEMPLATE.read_bytes()
    final = {**defaults(), **parse(data, path)}
    copy = workspace_file(layout)
    if regular_bytes(copy) != data:
        # Same-dir atomic replacement; later runs never alter the stored recipe.
        with NamedTemporaryFile(dir=copy.parent, prefix='.gapfill.', delete=False) as stream:
            tmp = Path(stream.name)
            try:
                stream.write(data)
                stream.flush()
                stream.close()
                os.replace(tmp, copy)
            finally:
                tmp.unlink(missing_ok=True)
    return final


def degap_args(values):
    args = []
    for name, flag in LIMITS.items():
        args.extend((flag, str(values[name])))
    args.append('--kmer_filter' if values['kmer_filter'] else '--no-kmer-filter')
    return args
