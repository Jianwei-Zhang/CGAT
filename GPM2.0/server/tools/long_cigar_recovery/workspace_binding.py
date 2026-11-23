"""Use the Server layout resolver without changing standalone legacy experiments.

Numbered paths are never duplicated here. A marked workspace requires the exact
layout module shipped beside this runtime (or the canonical source counterpart).
"""
from functools import lru_cache
import importlib.util
from pathlib import Path
import sys


@lru_cache(maxsize=1)
def _resolver():
    here = Path(__file__).resolve()
    candidates = (here.parent.parent / "workspace_layout.py",
                  here.parents[2] / "server/tools/workspace_layout.py")
    for path in candidates:
        if path.is_file() and not path.is_symlink():
            name = "_cgat_recovery_workspace_layout"
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module.workspace_join
    raise ValueError("numbered workspace requires the bundled Server layout resolver")


def workspace_path(root, *parts):
    root = Path(root)
    private = root / ".runtime"
    if private.is_symlink() or any((private / name).exists() or (private / name).is_symlink()
                                  for name in ("workspace.json", "migration.json")):
        return _resolver()(root, *parts)
    return root.joinpath(*parts)


def workspace_relative(root, logical):
    root = Path(root).resolve()
    return workspace_path(root, logical).relative_to(root).as_posix()
