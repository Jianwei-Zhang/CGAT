"""One deterministic native invocation per selected refinement tool.

Reads support is a pinned recipe decision, not inferred from executable names.
No user-supplied corrected-reads assertion is required. Native TGS ONT Racon is
an explicit logged stage; no extra external correction pipeline is introduced.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys

try:
    from refinement_tools import TOOLS, ToolError, load_lock, source_location, validate_runtime, fingerprint
except ModuleNotFoundError:
    from .refinement_tools import TOOLS, ToolError, load_lock, source_location, validate_runtime, fingerprint


@dataclass(frozen=True)
class Invocation:
    tool: str
    command: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]
    required_outputs: tuple[str, ...]
    recipe: dict


def select_tools(value: str | None, *, has_reads: bool) -> tuple[str, ...]:
    if value is None:
        return ("degap",) if has_reads else ()
    if value == "none":
        return ()
    selected = value.split(",")
    if not selected or any(name not in TOOLS for name in selected) or len(set(selected)) != len(selected):
        raise ToolError("--gapfill-tools requires unique comma-separated degap,tgsgapcloser,quartet,lrgapcloser or none")
    if not has_reads:
        raise ToolError("selected refinement tools require --hifi and/or --ont reads")
    return tuple(name for name in TOOLS if name in selected)


def select_reads(tool: str, groups: dict) -> dict:
    if tool not in TOOLS or set(groups) != {"hifi", "ont"}:
        raise ToolError("invalid tool/reads selection")
    if any(not isinstance(paths, list) or any(not isinstance(p, str) or not p for p in paths) for paths in groups.values()):
        raise ToolError("reads inputs must be path lists")
    groups = {kind: [str(Path(path).resolve()) for path in paths] for kind, paths in groups.items()}
    seen = [path for paths in groups.values() for path in paths]
    if not seen or len(seen) != len(set(seen)):
        raise ToolError("reads must be nonempty and cannot be supplied twice or as both technologies")
    selected = {kind: list(paths) for kind, paths in groups.items()}
    if tool in {"tgsgapcloser", "lrgapcloser"}:
        selected["ont" if groups["hifi"] else "hifi"] = []
    ignored = {kind: [path for path in paths if path not in selected[kind]] for kind, paths in groups.items()}
    return {"selected": selected, "unused": ignored,
            "mode": "mixed" if all(selected.values()) else "hifi" if selected["hifi"] else "ont"}


def native_safe_path(path: Path):
    # The pinned upstream shell writers interpolate paths. A list argv alone
    # cannot make their nested shell strings safe. Fail before invoking them.
    if re.fullmatch(r"[A-Za-z0-9_./-]+", str(path.absolute())) is None:
        raise ToolError("native refinement workspace/runtime paths cannot contain spaces or shell metacharacters")


def make_invocation(tool: str, baseline: Path, prepared_reads: dict, native_dir: Path, threads: int,
                    *, prefix: Path | None = None, runtime: dict | None = None, lock=None) -> Invocation:
    prefix = Path(prefix or sys.prefix).resolve()
    lock = lock or load_lock()
    runtime = runtime or validate_runtime(prefix, lock)
    if tool not in TOOLS or type(threads) is not int or threads < 1:
        raise ToolError("invalid refinement tool/thread budget")
    if runtime.get("lock_sha256") != fingerprint(lock):
        raise ToolError("native invocation runtime belongs to a different tool lock")
    definition = lock["tools"][tool]
    inputs = select_reads(tool, prepared_reads)
    reads = inputs["selected"]
    baseline, native_dir = baseline.absolute(), native_dir.absolute()
    for path in (prefix, baseline, native_dir, *(Path(p) for paths in reads.values() for p in paths)):
        native_safe_path(path)
    environment = dict(os.environ)
    environment.update(LC_ALL="C", LANG="C", PATH=str(prefix / "bin") + os.pathsep + environment.get("PATH", ""),
                       PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS=str(threads),
                       OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1")
    for key in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(key, None)
    recipe = {"name": definition["recipe"], "tool": tool, "version": definition["version"],
              "revision": definition["revision"], "runtime_sha256": fingerprint(runtime),
              "reads": inputs, "threads": threads, "parameters": definition.get("parameters", {}), "packaging_patches": definition.get("patches", [])}
    bash, python = str(prefix / "bin/bash"), str(prefix / "bin/python")
    # bash is not necessarily a conda package; using the system interpreter does
    # not substitute the pinned native tool or its declared scientific dependencies.
    if not Path(bash).is_file():
        bash = "/bin/bash"
    if tool == "degap":
        engine = Path(__file__).resolve().parent / "degap_core/bin/AutoGapfiller.py"
        native_safe_path(engine)
        command = [python, "-B", str(engine), "--genome", str(baseline), "--output", str(native_dir),
                   "--work", "1", "--thread", str(threads)]
        for kind, paths in reads.items():
            if paths:
                command += ["--" + kind, *paths]
        outputs = ("03.gap_filling/gap_filling_results.json", "04.genome_integration/genome.filled.fasta")
        cwd = native_dir.parent
    elif tool == "quartet":
        basenames = [Path(path).name for paths in reads.values() for path in paths]
        if len(basenames) != len(set(basenames)):
            raise ToolError("quarTeT input FASTA basenames must be distinct to prevent native alignment reuse")
        command = [python, "-I", "-B", str(source_location(prefix, definition) / "quartet_runner.py"), "GapFiller",
                   "-d", str(baseline), "-g", *reads["hifi"], *reads["ont"], "-t", str(threads),
                   "-a", "minimap2", "--minimapoption", "-x asm5", "--noplot", "-p", "quartet"]
        outputs = ("quartet.genome.filled.fasta", "quartet.genome.filled.detail", "quartet.genome.filled.modified.agp")
        cwd = native_dir
    else:
        paths = reads[inputs["mode"]]
        if len(paths) != 1:
            raise ToolError(f"{tool} requires one content-bound combined FASTA for the selected technology")
        if tool == "tgsgapcloser":
            parameters = definition["parameters"][inputs["mode"]]
            command = [bash, str(prefix / "bin/tgsgapcloser"), "--scaff", str(baseline), "--reads", paths[0],
                       "--output", str(native_dir / "tgs"), "--thread", str(threads),
                       "--tgstype", parameters["tgstype"], "--minmap_arg", " " + parameters["minimap"]]
            if parameters["correction"] == "none":
                command += ["--ne"]
            else:
                command += ["--racon", str(prefix / "bin/racon"), "--r_round", str(parameters["racon_rounds"])]
            outputs = ("tgs.scaff_seqs", "tgs.updated_scaff_infos", "tgs.orignial_scaff_infos", "tgs.name_map")
            cwd = native_dir
        else:
            parameters = definition["parameters"]
            command = [bash, str(prefix / "bin/LR_Gapcloser.sh"), "-i", str(baseline), "-l", paths[0],
                       "-s", parameters[inputs["mode"] + "_platform"], "-t", str(threads),
                       "-n", str(parameters["tag_partitions"]), "-r", str(parameters["iterations"]), "-o", str(native_dir)]
            outputs = ("iteration-1/gapclosed.fasta",)  # Native may stop early when no Ns remain.
            cwd = native_dir.parent
    return Invocation(tool, tuple(command), cwd, environment, outputs, recipe)


def prepare_native_reads(tool: str, groups: dict, cache_root: Path) -> dict:
    try:
        from refinement_reads import prepare_fasta
    except ModuleNotFoundError:
        from .refinement_reads import prepare_fasta
    selection = select_reads(tool, groups)
    if tool == "degap":
        return {"original_selection": selection, "prepared": selection["selected"], "conversions": {}}
    prepared, conversions = {"hifi": [], "ont": []}, {}
    for kind, paths in selection["selected"].items():
        if paths:
            conversion = prepare_fasta(paths, cache_root)
            prepared[kind] = [conversion["fasta"]]
            conversions[kind] = conversion
    return {"original_selection": selection, "prepared": prepared, "conversions": conversions}
