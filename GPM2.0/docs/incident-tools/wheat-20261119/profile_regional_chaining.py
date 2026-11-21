"""Isolate chaining from CIGAR cost; approximate PAF is NEVER accepted evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time


def records(path):
    name=None;seq=[]
    with path.open() as f:
        for line in f:
            if line.startswith(">"):
                if name is not None:yield name,"".join(seq).encode()
                name=line[1:].strip();seq=[]
            else:seq.append(line.strip())
    if name is not None:yield name,"".join(seq).encode()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-site",type=Path,required=True)
    p.add_argument("--minimap2",type=Path,required=True)
    a=p.parse_args();site=a.source_site.resolve(strict=True);out=Path.cwd().resolve()
    if site==out or site in out.parents:raise ValueError("isolated diagnostics required")
    proof=json.loads((site/"inputs.json").read_text());identities={}
    for filename in ("query.fa","target.fa"):
        path=site/filename;identities[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        found={}
        for name,seq in records(path):
            if name in found:raise ValueError("duplicate input name")
            found[name]=hashlib.sha256(seq).hexdigest()
        expected={"query":proof["query_sha256"]} if filename=="query.fa" else proof["target_sequence_sha256"]
        if found!=expected:raise ValueError("window sequences differ from extracted input record")
    if hashlib.sha256(a.minimap2.read_bytes()).hexdigest()!=proof["tool_sha256"]:raise ValueError("mapper changed")
    command=[str(a.minimap2),"-x","asm10","-D","-P","--dual=yes","--no-long-join","-t","1",str(site/"target.fa"),str(site/"query.fa")]
    def guard():resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    started=time.monotonic();timed=False
    with Path("approximate.paf").open("wb") as output,Path("stderr.log").open("wb") as log:
        proc=subprocess.Popen(command,stdout=output,stderr=log,start_new_session=True,preexec_fn=guard)
        try:code=proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            timed=True;os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            code=proc.returncode
    for path,sha in identities.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError("diagnostic inputs changed")
    report=dict(status="chaining_only_timeout" if timed else "chaining_only_exit",exit_code=code,seconds=time.monotonic()-started,
                argv=command,input_sha256=identities,tool_sha256=proof["tool_sha256"],
                approximate_output_bytes=Path("approximate.paf").stat().st_size,production_modified=False,
                approximate_output_is_accepted_evidence=False,scientific_acceptance=False)
    Path("summary.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report),flush=True)
    if code and not timed:raise RuntimeError("chaining diagnostic mapper failed")


if __name__=="__main__":main()
