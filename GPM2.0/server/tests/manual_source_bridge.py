"""Controlled Windows App export/WSL Server bridge. No real DEGAP acceptance claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import sys
import tempfile

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from workspace_layout import initialize_workspace, workspace_join, WorkspaceLayout

BASE_METADATA = {
    "prepare_options.tsv": "key\tvalue\nthreads\t1\nalignment_engine\tminimap2\nminimap_preset\tasm10\nskip_self\tfalse\nsequence_layout\tpartitioned\npreassigned_chr\ttrue\nself_alignment_scope\tchr_partition\ncross_alignment_scope\tchr_partition\n",
    "datasets.tsv": "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\nds\tasm\t\tdata/datasets/server_ds.fa\tdata/datasets/server_ds.fa.fai\ttrue\n",
    "reference.tsv": "reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\nref\tspecies\tasm\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
    "reference_chr_locator.tsv": "reference_chr_name\tfasta_relpath\nChr01\tdata/reference/ref.fa\n",
    "source_seq_locator.tsv": "dataset_name\tseq_name\tfasta_relpath\nds\ttigA\tdata/datasets/server_ds.fa\nds\ttigB\tdata/datasets/server_ds.fa\n",
    "source_seq_n_regions.tsv": "dataset_name\tseq_name\tstart_bp\tend_bp\tlength_bp\n",
    "chr_assignments.tsv": "dataset_name\tseq_name\tseq_length_bp\tassigned_chr_name\tsource_orientation\torientation_source\tsupport_bp\tsupport_percent\tanchor_start\nds\ttigA\t8\tChr01\t+\tref_alignment\t8\t100\t1\nds\ttigB\t8\tChr01\t+\tref_alignment\t8\t100\t1\n",
    "track_member_orders.tsv": "target_track\ttarget_chr\tmember_dataset\tmember_ctg\tmember_order\nds\tChr01\tds\ttigA\t1\nds\tChr01\tds\ttigB\t2\n",
}



def owned(home):
    home = home.resolve()
    if (home / ".owned-fixture").read_text() != "cgat.manual-source-bridge.v1\n":
        raise ValueError("not an owned controlled bridge fixture")
    return home


def from_windows(value):
    path = PureWindowsPath(value)
    if path.drive.lower() == "d:":
        return Path("/mnt/d").joinpath(*path.parts[1:])
    raise ValueError("controlled bridge expects a D-drive fixture")


def run_server(home, *, collect_only=False):
    home = owned(home)
    exported = json.loads((home / "exported.json").read_text())
    server = Path(exported["server"])
    if server != home / "server" or (server.exists() and not collect_only):
        raise ValueError("controlled Server must use its fresh owned fixture root, or explicit collect-only resume")
    if collect_only:
        return resume_collect(home, exported)
    layout = initialize_workspace(server)
    runtime = layout.path(".prepare_lib/tools")
    runtime.mkdir(parents=True)
    for source in TOOLS.glob("*.py"):
        shutil.copy2(source, runtime / source.name)
    for name in ("long_cigar_recovery", "grt_core", "lgz_core"):
        shutil.copytree(TOOLS / name, runtime / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    metadata = workspace_join(server, "metadata")
    metadata.mkdir()
    for name, content in BASE_METADATA.items():
        (metadata / name).write_text(content)
    sequence = ">tigA Server-only wrapping\nAACC\nGGTT\n>tigB Server-only wrapping\nTTTT\nCCCC\n"
    for relative, content in (("data/datasets/server_ds.fa", sequence), ("runs/chr_Chr01/datasets/ds.fa", sequence),
                              ("data/reference/ref.fa", ">Chr01\nAACCGGTT\n")):
        path = layout.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    # This actual Server deliberately has no App portable data/partitions path.
    assert not layout.path("data/partitions/chr/Chr01/ds.fa").exists()
    (server / "controlled_reads.fa").write_text(">read\nAACCGGTT\n")
    shared = server / "manual-jobs/shared_prepare"
    (shared / "processed_reads").mkdir(parents=True)
    (shared / "processed_reads/hifi_reads.fa").write_text(">read\nAACCGGTT\n")
    (shared / "hifi_reads.idx").write_text("controlled custom-engine fixture; no real read index\n")
    (shared / "hifi_reads_part").mkdir()
    native = server / "controlled_degap.py"
    native.write_text("from pathlib import Path\nimport argparse\np=argparse.ArgumentParser()\np.add_argument('--out')\np.add_argument('--seqleft')\np.add_argument('--seqright')\na,_=p.parse_known_args()\n"
                      "read=lambda value: ''.join(line for line in Path(value).read_text().splitlines() if not line.startswith('>'))\n"
                      "out=Path(a.out); out.mkdir(parents=True,exist_ok=True)\n"
                      "(out/(out.name+'.final.fa')).write_text('>controlled_candidate\\n'+read(a.seqleft)+'GT'+read(a.seqright)+'\\n')\n")
    script = from_windows(exported["script"])
    export_dir = from_windows(exported["export_dir"])
    if not script.resolve().is_relative_to(home) or not export_dir.resolve().is_relative_to(home):
        raise ValueError("exported bridge script escaped its owned fixture")
    controlled_bin = server / "controlled-bin"
    controlled_bin.mkdir()
    # A real activated cgat-server environment supplies `python`; this protocol
    # fixture uses the current test Python for its explicitly custom producer.
    (controlled_bin / "python").symlink_to(sys.executable)
    controlled_aligner(controlled_bin)
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                   "PATH": str(controlled_bin) + os.pathsep + os.environ["PATH"]}
    for command in (["bash", str(script)], ["bash", str(export_dir / "collect_degap_results.sh")]):
        completed = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=90)
        print(completed.stdout)
        if completed.returncode:
            raise RuntimeError(completed.stderr)
    finish_evidence(home, exported)


def controlled_aligner(folder):
    path = folder / "minimap2"
    if path.exists():
        return
    path.write_text("#!/usr/bin/env python3\nfrom pathlib import Path\nimport sys\n"
                    "def first(path):\n name=None; seq=[]\n for line in Path(path).read_text().splitlines():\n  if line.startswith('>'):\n   if name is not None: break\n   name=line[1:].split()[0]\n  elif name is not None: seq.append(line)\n return name,len(''.join(seq))\n"
                    "q,ql=first(sys.argv[-1]);t,tl=first(sys.argv[-2]);n=min(ql,tl)\n"
                    "Path(sys.argv[sys.argv.index('-o')+1]).write_text(f'{q}\\t{ql}\\t0\\t{n}\\t+\\t{t}\\t{tl}\\t0\\t{n}\\t{n}\\t{n}\\t60\\tcg:Z:{n}M\\n')\n")
    path.chmod(0o755)


def finish_evidence(home, exported):
    server = Path(exported["server"])
    layout = WorkspaceLayout.detect(server)
    sequence = ">tigA Server-only wrapping\nAACC\nGGTT\n>tigB Server-only wrapping\nTTTT\nCCCC\n"
    expected = {"metadata/" + name: content for name, content in BASE_METADATA.items()}
    expected.update({"data/datasets/server_ds.fa": sequence, "runs/chr_Chr01/datasets/ds.fa": sequence,
                     "data/reference/ref.fa": ">Chr01\nAACCGGTT\n"})
    for name, value in expected.items():
        if layout.path(name).read_text() != value:
            raise ValueError("manual bridge changed original Server science: " + name)
    actual = {path for name in ("01_inputs", "02_alignments", ".runtime/metadata")
              for path in (server / name).rglob("*") if path.is_file()}
    if actual != {layout.path(name) for name in expected}:
        raise ValueError("manual bridge added/lost an original scientific file")
    export_dir = from_windows(exported["export_dir"])
    recipe = json.loads(next((export_dir / "degap_jobs").glob("*.json")).read_text())
    proof = json.loads((Path(exported["out"]) / ".gpm_degap_source_proof.json").read_text())
    if proof["labels"]["seqleft"]["binding"] != "interval_content":
        raise ValueError("bridge did not verify the actual App source interval")
    evidence = {"schema": "cgat.controlled-manual-source-bridge", "server": str(server),
                "native": "controlled custom producer, not DEGAP acceptance", "alignments": "controlled PAF producer, not minimap2 acceptance",
                "original_science_unchanged": True, "export_token": recipe["token"],
                "result_zip": str(export_dir / "degap_results.zip"), "seed_sources": proof}
    (home / "server-evidence.json").write_text(json.dumps(evidence, indent=2))
    print("CONTROLLED_SERVER_BRIDGE_OK", home)


def resume_collect(home, exported):
    server = Path(exported["server"])
    native = Path(exported["out"]) / ".gpm_degap_result.json"
    if not native.is_file():
        raise ValueError("collect-only resume requires the completed native receipt")
    completed = {path: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
                 for path in native.parent.glob("*.fa")}
    completed[native] = (native.stat().st_mtime_ns, hashlib.sha256(native.read_bytes()).hexdigest())
    controlled_bin = server / "controlled-bin"
    controlled_aligner(controlled_bin)
    export_dir = from_windows(exported["export_dir"])
    result = subprocess.run(["bash", str(export_dir / "collect_degap_results.sh")], capture_output=True, text=True,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PATH": str(controlled_bin) + os.pathsep + os.environ["PATH"]}, timeout=90)
    print(result.stdout)
    if result.returncode:
        raise RuntimeError(result.stderr)
    for path, before in completed.items():
        if (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()) != before:
            raise ValueError("collect-only resume changed/reran completed native work")
    finish_evidence(home, exported)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("init", "server"))
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    if args.mode == "init":
        parent = Path("/mnt/d/tmp")
        parent.mkdir(exist_ok=True)
        home = Path(tempfile.mkdtemp(prefix="cgat-manual-source-", dir=parent))
        (home / ".owned-fixture").write_text("cgat.manual-source-bridge.v1\n")
        print(json.dumps({"fixture": str(home), "windows": str(PureWindowsPath("D:/tmp") / home.name),
                          "server": str(home / "server")}))
    else:
        run_server(args.fixture, collect_only=args.collect_only)


if __name__ == "__main__":
    main()
