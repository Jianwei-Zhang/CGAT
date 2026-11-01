"""Legacy import forwarding and complete, installation-independent engine identity."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sys


def forward_module(name: str, package: str | None, namespace: dict) -> None:
    """Forward old modules without duplicating globals, exceptions or patch targets.

    Package shims keep their own path so old child imports reach explicit shims;
    each non-package shim aliases the canonical module object in sys.modules.
    """
    target = name.replace("grt_core", "lgz_core").replace("grt_", "lgz_")
    if name == "__main__":
        target = Path(namespace["__file__"]).stem.replace("grt_", "lgz_", 1)
        if package:
            target = package + "." + target
    module = import_module(target)
    if name == "__main__":
        main = getattr(module, "main", None)
        if main is not None:
            raise SystemExit(main())
        return
    namespace.update({key: value for key, value in vars(module).items()
                      if not key.startswith("__") or key == "__all__"})
    if "__path__" not in namespace:
        sys.modules[name] = module


def engine_source_files(tools: Path) -> list[Path]:
    """Include canonical engine and legacy forwarding bytes in the same identity.

    Historical GRT-only trees retain the old file selection. Updated trees hash
    both namespaces; a rename is not proof that old decision checkpoints match.
    """
    names = ("grt_core", "lgz_core") if (tools / "lgz_core/__init__.py").is_file() else ("grt_core",)
    files = [path for name in names for path in sorted((tools / name).rglob("*.py"))]
    files += [tools / "grt_step2.py", tools / "grt_step3.py"]
    if "lgz_core" in names:
        files += [tools / "lgz_step2.py", tools / "lgz_step3.py", tools / "lgz_compat.py"]
    return files
