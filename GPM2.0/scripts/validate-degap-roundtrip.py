#!/usr/bin/env python3
"""Opt-in real DEGAP roundtrip on generated data; never uses customer workspaces.

Run inside cgat-server with a freshly built backend CLI. --work-root must not
exist. Supports a Windows .exe invoked from WSL or a native Linux backend.
No GUI/browser, network download, published release or existing project writes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import subprocess


def sequence(path):
    return "".join(line.strip() for line in path.read_text().splitlines() if not line.startswith(">"))


def sha256(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    args = parser.parse_args()
    backend = args.backend.resolve(strict=True)
    root = args.work_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    server_tools = Path(__file__).resolve().parents[1] / "server"

    def native(path):
        return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip() if backend.suffix == ".exe" else str(path)

    def run(name, command, *, success=True):
        result = subprocess.run([str(arg) for arg in command], capture_output=True, text=True)
        (root / (name + ".log")).write_text(result.stdout + "\n" + result.stderr)
        if success:
            result.check_returncode()
        return result

    rng = random.Random(113)
    genome = "".join(rng.choice("ACGT") for _ in range(24000))
    (root / "reference.fa").write_text(">Chr01\n" + genome + "\n")
    (root / "primary.fa").write_text(">left\n" + genome[:10000] + "\n>right\n" + genome[14000:] + "\n")
    (root / "support.fa").write_text(">support\n" + genome + "\n")
    (root / "reads.fa").write_text(">read1\n" + genome + "\n")
    server, app, exports = root / "server", root / "app", root / "jobs"
    run("server", ["bash", server_tools / "run.sh", "--ref", "ref", root / "reference.fa",
                   "--ds", "primary", root / "primary.fa", "--ds", "support", root / "support.fa",
                   "-t", "2", "-o", server])
    run("import-project", [backend, "import-zip", native(root / "server.tar.gz"), native(app)])
    run("initialize", [backend, "initialize-project", native(app), "DEGAP-roundtrip"])
    conn = sqlite3.connect(app / "project.sqlite")
    project = conn.execute("SELECT id FROM project").fetchone()[0]
    ids = dict(conn.execute("SELECT ss.seq_name,c.id FROM assembly_ctg c JOIN assembly_seq s ON s.id=c.assembly_seq_id JOIN source_seq ss ON ss.id=s.source_seq_id WHERE c.project_id=?", [project]))
    # Model a user-edited gapped Final Path without altering the immutable LGZ baseline.
    final_path = {"Chr01": {"chrName":"Chr01", "segments":[
        {"type":"ctg","assemblyCtgId":ids["left"],"start":1,"end":10000},
        {"type":"gap","lengthBp":4000},
        {"type":"ctg","assemblyCtgId":ids["right"],"start":1,"end":10000}]}}
    jobs = [{"jobType":"gapfiller","jobId":"gap-left","chrName":"Chr01", "leftCtg":"left", "rightCtg":"right", "flag":"left",
             "outPath":str(root / "results/gap-left"), "left":{"assemblyCtgId":ids["left"],"start":1,"end":10000},
             "right":{"assemblyCtgId":ids["right"],"start":1,"end":10000}}]
    conn.execute("INSERT INTO project_assembly_view_state(project_id,final_path_by_chr_json,degap_project_state_json,updated_at) VALUES(?,?,?,'fixture') ON CONFLICT(project_id) DO UPDATE SET final_path_by_chr_json=excluded.final_path_by_chr_json,degap_project_state_json=excluded.degap_project_state_json",
                 [project,json.dumps(final_path),json.dumps({"jobs":jobs})])
    conn.commit(); conn.close()
    settings = {"gpmServerPath":str(server), "outRoot":str(root / "results"), "hifiReads":[str(root / "reads.fa")],
                "thread":2,"maximumExtensionRound":1,"kmerFilter":False}
    run("export", [backend,"export-degap-jobs",native(app),str(project),native(exports),
                   "--settings-json",json.dumps(settings),"--jobs-json",json.dumps(jobs)])
    for script in exports.rglob("*.sh"):
        subprocess.run(["bash", "-n", str(script)], check=True)
    run("degap", ["bash", exports / "run_degap_jobs.sh"])
    result_path = exports / "degap_results.zip"
    run("import-results", [backend,"import-degap-results",native(result_path),native(app),str(project)])
    conn = sqlite3.connect(app / "project.sqlite")
    final_after, state = conn.execute("SELECT final_path_by_chr_json,degap_project_state_json FROM project_assembly_view_state WHERE project_id=?",[project]).fetchone()
    assert json.loads(final_after) == final_path, "Final Path changed during candidate import"
    imported = json.loads(state)["jobs"][0]["importedResults"]
    assert len(imported) == 1
    count = conn.execute("SELECT COUNT(*) FROM source_seq").fetchone()[0]
    conn.close()
    candidate = app / "data/derived_ctgs" / (imported[0]["ctgName"] + ".fa")
    assert sequence(candidate) == genome, "Candidate sequence differs from the generated ground truth"
    repeated = run("duplicate-rejected", [backend,"import-degap-results",native(result_path),native(app),str(project)], success=False)
    assert repeated.returncode and "already been imported" in repeated.stderr
    with sqlite3.connect(app / "project.sqlite") as conn:
        assert conn.execute("SELECT COUNT(*) FROM source_seq").fetchone()[0] == count
    report = {"schema":"gpm.degap.validation.v1", "candidate_bases":len(genome), "gap_bases":4000,
              "candidate_matches_reference":True, "final_path_unchanged":True,
              "job_association_persisted":True, "duplicate_rejected_without_mutation":True,
              "package_sha256":sha256(result_path), "backend_sha256":sha256(backend),
              "server_files_sha256":{name:sha256(server_tools / name) for name in
                ("tools/degap.py","tools/degap_results.py","tools/degap_core/SOURCE.json","cgat-server.conda-spec.txt")}}
    (root / "acceptance.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
