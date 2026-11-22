"""Run the exact pinned CLI with bounded consumed-output recovery hooks.

Invoked using the managed Python's -I -B flags. No edits to upstream sources, no
alternate scientific command or hidden corrected-reads claim.
"""
from __future__ import annotations

from pathlib import Path
import runpy
import shutil
import sys

# -I intentionally ignores PYTHONPATH and the entrypoint directory. Bootstrap
# only the CGAT runtime that owns this launcher and the verified native source.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from refinement_native_units import UnitStore, checked_json, helper_hashes, owned, validate_paf, REQUEST
from refinement_path import PathError


def install_quartet_hook(util, store, native_directory):
    original = util.minimap
    native_directory = Path(native_directory).resolve()

    def minimap(reffasta, qryfasta, prefix, suffix, minimapoption, plot, overwrite, aligner, allow_empty=False):
        if (plot is not False or overwrite is not False or aligner != "minimap2" or allow_empty is not True
                or prefix != "quartet" or not suffix.startswith("flank_map_")):
            raise PathError("unexpected pinned quarTeT execution boundary")
        name = prefix + "." + suffix + ".paf"
        if Path(name).name != name or "\\" in name:
            raise PathError("unsafe quarTeT PAF name")
        final, root_paf = native_directory / "tmp" / name, native_directory / name
        for path in (final, root_paf):
            owned(store.root, path)
            if path.exists() or path.is_symlink():
                raise PathError("unsealed native PAF already exists in fresh attempt")
        inputs = {"reference": Path(reffasta).absolute(), "query": Path(qryfasta).absolute()}
        for path in inputs.values():
            owned(store.root, path)
            # Native input FASTAs may be content-bound files in 01_inputs or
            # native-generated flank/split files; no output-tree symlink reuse.
            if not path.is_file():
                raise PathError("native alignment input is not a regular file")
        unit = {"kind": "quartet.minimap", "prefix": prefix, "suffix": suffix,
                "options": minimapoption, "plot": plot, "overwrite": overwrite,
                "aligner": aligner, "allow_empty": allow_empty}

        def execute():
            result = Path(original(reffasta, qryfasta, prefix, suffix, minimapoption,
                                   plot, overwrite, aligner, allow_empty=allow_empty)).absolute()
            if result != final:
                raise PathError("pinned quarTeT helper returned an unexpected PAF path")
            return result

        def restore(source):
            final.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, final)
            return final

        result = store.run(unit, inputs, execute, restore,
                           lambda path: validate_paf(path, allow_empty=allow_empty))
        return str(result)

    util.minimap = minimap


def main():
    if len(sys.argv) < 6 or sys.argv[1] != "--request" or sys.argv[3] != "--":
        raise PathError("native launcher requires its sealed request")
    request_path = Path(sys.argv[2]).absolute()
    # The request location supplies the root without trusting a path inside JSON.
    root = request_path.parents[4]
    request = checked_json(root, request_path)
    if (request.get("schema") != "cgat.native-refinement-launch" or request.get("schema_version") != 1
            or request.get("root") != str(root) or request.get("tool") != "quartet"
            or request.get("helpers") != helper_hashes() or request["session"]["helpers"] != request["helpers"]
            or request.get("cwd") != str(Path.cwd()) or request["command"][3:] != sys.argv[4:]
            or request["command"][1:3] != ["-I", "-B"]):
        raise PathError("native launcher request does not match invocation")
    expected = root / "04_refinement/03_quartet/02_jobs" / request["run_id"] / REQUEST
    if request_path != expected:
        raise PathError("native launcher request has an unowned location")
    entrypoint = Path(request["command"][3])
    sys.path.insert(0, str(entrypoint.parent / "source"))
    from quartet import util
    store = UnitStore(root, "quartet", request["run_id"], request["session"], request["command"])
    install_quartet_hook(util, store, request["cwd"])
    sys.argv = request["command"][3:]
    code = 1
    try:
        runpy.run_path(str(entrypoint), run_name="__main__")
        code = 0
    except SystemExit as error:
        code = 0 if error.code is None else error.code
        if type(code) is not int:
            code = 1
            raise
    finally:
        store.write_summary(code)
    return code


if __name__ == "__main__":
    sys.exit(main())
