#!/usr/bin/env python3
"""Opt-in synthetic minimap2 parameter audit; never run automatically or on customer FASTA.

Example: python3 validation/minimap2_long_cigar_parameters.py --minimap2 /path/to/minimap2 --out /tmp/new-audit
Requires a C compiler and /usr/bin/time; default experiment uses a 270 Mb synthetic
record, two mapping threads, a 10 GiB per-process address-space cap and no core dumps.
This is an experiment, not a parameter workaround or an automatic retry facility.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import time

GENERATOR = '#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\nint main(int argc, char **argv) {\n    if(argc!=2) return 2;\n    uint64_t n=strtoull(argv[1],0,10); uint32_t x=0x12345678;\n    const char bases[]="ACGT"; char line[81]; line[80]=n;\n    puts(">synthetic_270M");\n    for(uint64_t i=0;i<n;) {\n        size_t len=(n-i)<80?(size_t)(n-i):80;\n        for(size_t j=0;j<len;j++) { x^=x<<13; x^=x>>17; x^=x<<5; line[j]=bases[x&3]; }\n        fwrite(line,1,len,stdout); putchar(\'\\n\'); i+=len;\n    }\n    return ferror(stdout)?1:0;\n}\n'


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimap2", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--memory-gib", type=int, default=10)
    args = parser.parse_args()
    if min(args.threads, args.timeout, args.memory_gib) < 1:
        parser.error("resource limits must be positive")
    mm = shutil.which(args.minimap2)
    if not mm:
        parser.error("minimap2 executable not found")
    mm = str(Path(mm).resolve())
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        parser.error("--out must be empty; existing evidence is never overwritten")
    (root / "generate.c").write_text(GENERATOR)
    subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-Werror", str(root / "generate.c"), "-o", str(root / "generate")], check=True)
    for filename, bases in [("reference.fa", 270000000), ("control.fa", 1000000)]:
        with (root / filename).open("wb") as out:
            subprocess.run([str(root / "generate"), str(bases)], stdout=out, check=True)
    version = subprocess.check_output([mm, "--version"], text=True).strip()
    identities = {filename: sha256(root / filename) for filename in ("reference.fa", "control.fa")}
    identities.update(minimap2_path=mm, minimap2_version=version, minimap2_sha256=sha256(Path(mm)))
    (root / "identities.json").write_text(json.dumps(identities, indent=2))
    ref = str(root / "reference.fa")
    idx = str(root / "reference.mmi")
    base = [mm, "-c", "-x", "asm10", "-t", str(args.threads)]
    cases = [
        ("index", [mm, "-x", "asm10", "-t", str(args.threads), "-d", idx, ref]),
        ("control_1M", base + [idx, str(root / "control.fa")]),
        ("baseline_270M", base + [idx, ref]),
        ("no_long_join_narrow_band", base + ["--no-long-join", "-r", "500,1000", idx, ref]),
        ("eqx", base + ["--eqx", idx, ref]),
        ("asm5", [mm, "-c", "-x", "asm5", "-t", str(args.threads), idx, ref]),
        ("query_batch_50M", base + ["-K", "50M", idx, ref]),
        ("index_batch_50M", base + ["-I", "50M", ref, ref]),
        ("zdrop_1", base + ["-z", "1,1", idx, ref]),
        ("sw_cap_1M", base + ["--cap-sw-mem=1M", idx, ref]),
        ("max_qlen_250M", base + ["--max-qlen=250M", idx, ref]),
        ("debug_qname", [mm, "-c", "-x", "asm10", "--print-qname", "-t", "1", idx, ref]),
    ]

    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        size = args.memory_gib * 1024**3
        resource.setrlimit(resource.RLIMIT_AS, (size, size))

    results = []
    for name, command in cases:
        start = time.monotonic()
        result = {"case": name, "command": command, "memory_cap_gib": args.memory_gib}
        print("START", name, flush=True)
        with (root / (name + ".paf")).open("wb") as out, (root / (name + ".log")).open("wb") as err:
            process = subprocess.Popen(["/usr/bin/time", "-v"] + command, stdout=out, stderr=err,
                                       preexec_fn=limits, start_new_session=True)
            try:
                result["returncode"] = process.wait(timeout=args.timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                result.update(returncode=process.returncode, stopped=type(exc).__name__)
        text = (root / (name + ".log")).read_text(errors="replace")
        result.update(seconds=round(time.monotonic() - start, 2),
                      assertion="mm_update_extra" in text and "Assertion" in text,
                      output_bytes=(root / (name + ".paf")).stat().st_size)
        results.append(result)
        (root / "results.json").write_text(json.dumps(results, indent=2))
        print(json.dumps(result), flush=True)
        if (name == "index" and result["returncode"] != 0) or result.get("stopped"):
            break
    print("Audit complete. Exit zero/empty output is NOT successful alignment or a workaround.")


if __name__ == "__main__":
    main()
