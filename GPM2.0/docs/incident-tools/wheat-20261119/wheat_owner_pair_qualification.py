"""Qualify production owner-only admission and its independently reloaded checkpoint."""
import gzip
from hashlib import sha256
import json
from pathlib import Path
import pickle
import re
import subprocess
import sys

from wheat_pair_exact_qualification import BASELINE, digest, need, replay, write

INPUT = "ff00e2329fc9d1b8f60c9ed0d1fdb6e19faf4cf19d961d73475b697a45324aee"
FULL = "eb50499368308cef375a82619bb043a8d679b9a17238582c75c2556bee7f9a47"
CHECKPOINT = "99f36fc6fc16535e315aa4d6d0511b2c0028789bc00f3293d9e4a8af1d199b2a"


def verified_logs(logs):
    modes = [s for s in logs if s.startswith("placement pair work") and "cpu_budget=" in s]
    reports = [s for s in logs if s.startswith("placement pair work") and "worker_parts=" in s]
    need(modes and all(s.endswith(" lanes=1 mode=owner_only") for s in modes), "not production owner mode")
    need(reports and all(" worker_parts=0 " in s for s in reports) and
         any(re.search(r"owner_parts=[1-9]", s) for s in reports), "missing nonempty owner round")
    need(any(s.startswith("reference screen:") and s.endswith(" lanes=8") for s in logs), "reference screening allocation")


def run(mode, root):
    from lgz_core import q0_admission as adm
    from wheat_selection_checkpoint import Store, PlacementSaved, encode
    selector = adm.selector_identity(); binding = [INPUT, selector, "qualified-owner-request"]
    def forbidden(*args, **kwargs): raise RuntimeError("external program disabled during qualification")
    subprocess.Popen = forbidden
    if mode == "full":
        need(digest(root/"subset.pickle") == INPUT, "unreviewed subset")
        replay(root, "candidate")
    elif mode == "write":
        folder = root/"selection"; folder.mkdir(); logs = []
        need(digest(root/"subset.pickle") == INPUT, "unreviewed subset")
        with (root/"subset.pickle").open("rb") as f: data = pickle.load(f)
        def log(s): logs.append(s); print(s, flush=True)
        try: adm.select_request_paths(data, screen_threads=32, progress=log, checkpoint=Store(folder,binding,True))
        except PlacementSaved: verified_logs(logs)
        else: raise ValueError("placement checkpoint was not published")
    elif mode == "read":
        result = Store(root/"selection", binding, False).load_admission()
        b = json.dumps([encode(p) for p in result.placements],sort_keys=True,separators=(",",":")).encode()
        old = root.parent/"q0-owner-checkpoint.Fad4KC1a/baseline-placements.json"
        need(sha256(b).hexdigest() == CHECKPOINT and b == old.read_bytes(), "checkpoint scientific fields differ")
        candidate = json.loads((root/"candidate.json").read_text()); verified_logs(candidate["logs"])
        need(candidate["selector_identity"] == selector and candidate["input_sha256"] == INPUT, "mixed qualification")
        with gzip.open(root/"candidate-admission.json.gz") as f: new = f.read()
        with gzip.open(root/"baseline-admission.json.gz") as f: original = f.read()
        need(original == new and sha256(new).hexdigest() == candidate["output_sha256"] == FULL, "admission differs")
        write(root/"qualification.json", dict(schema="wheat_owner_pair_qualification_v1",baseline_revision=BASELINE,
              input_sha256=INPUT,field_exact_equal=True,owner_only_verified=True,checkpoint_output_sha256=CHECKPOINT,
              baseline_output_sha256=FULL,candidate_output_sha256=FULL,candidate_selector_identity=selector,
              candidate_tools_sha256=digest(root/"candidate-tools.tgz"),baseline_tools_sha256=digest(root/"baseline-tools.tgz"),
              output_bytes=len(new),checkpoint_bytes=len(b),placements=len(result.placements),records=candidate["records"],
              mapper_calls=0,formal_workspace_modified=False))
    else: raise ValueError(mode)

if __name__ == "__main__": run(sys.argv[1], Path.cwd())
