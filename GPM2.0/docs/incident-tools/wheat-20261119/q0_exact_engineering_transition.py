"""Narrow authorization for a qualified, byte-pinned engineering successor.

This does not authorize new biological policies. Every file other than the
three reviewed engineering modules must equal the complete 2064cb4c archive.
The complete real-subset admission comparison must pass before preparation.
"""
import ast
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from q0_science_context import checked, digest

BASELINE_REVISION = "2064cb4cfd51b5c886f60af19f020caf0b18950f"
BASELINE_ARCHIVE_SHA256 = "4252ccb4ad2040f045efc73c1ba82aa8b05b1a340096c97b997d0c2d3588c57c"
ENGINEERING_FILES = {
    "q0_admission.py": "cd5e2ee3c63bf7e8f5f42292b396b1befc37d9ee983bab6d62f731f6e12f3aa9",
    "q0_pair_lanes.py": "9232e59786a9913ad961b50c2314d45be7529ca17e228f3f19a71552207327b5",
    "q0_pair_transport.py": "b82e206d706094dbc6b93e1642d28d52ec3a649178473d98830edcc0c28043d6",
}


OWNER_FILES = {**ENGINEERING_FILES, "q0_pair_lanes.py": "cd147a82dbbd887ce1a85571afafcd6e4b324fe44c5537c93b950c612e9abe1f"}


def need(ok, why):
    if not ok: raise ValueError(why)


def contents(path):
    out={}
    with tarfile.open(path,"r:gz") as tar:
        for member in tar:
            name=PurePosixPath(member.name)
            need(not name.is_absolute() and ".." not in name.parts and name.parts[0]=="tools", "unsafe engine archive")
            if member.isdir(): continue
            need(member.isfile() and member.name not in out and member.size<32*1024**2,"nonregular/duplicate/oversize engine file")
            out[member.name]=tar.extractfile(member).read()
    return out


def policy(data, name):
    node=next(n for n in ast.parse(data).body if isinstance(n,ast.ClassDef) and n.name==name)
    return ast.dump(node,include_attributes=False)


def validate(bundle, manifest):
    declaration=manifest.get("exact_engineering_change")
    if declaration is None: return None
    owner = declaration.get("schema") == "q0_exact_owner_pair_v1"
    pins = OWNER_FILES if owner else ENGINEERING_FILES
    need((owner or declaration.get("schema")=="q0_exact_pair_engineering_v1") and
         declaration.get("baseline_revision")==BASELINE_REVISION and
         declaration.get("runtime_revision")==manifest.get("git_revision") and
         re.fullmatch(r"[0-9a-f]{40}",declaration.get("runtime_revision","")),"invalid exact engineering authorization")
    report=json.loads(checked(declaration["qualification"]).read_text())
    if owner:
        need(report.get("schema") == "wheat_owner_pair_qualification_v1" and report.get("owner_only_verified") is True
             and report.get("input_sha256") == "ff00e2329fc9d1b8f60c9ed0d1fdb6e19faf4cf19d961d73475b697a45324aee"
             and report.get("candidate_output_sha256") == "eb50499368308cef375a82619bb043a8d679b9a17238582c75c2556bee7f9a47"
             and report.get("checkpoint_output_sha256") == "99f36fc6fc16535e315aa4d6d0511b2c0028789bc00f3293d9e4a8af1d199b2a",
             "owner-only admission/checkpoint not qualified")
    else:
        need(report.get("schema") == "wheat_pair_engineering_qualification_v1" and report.get("real_worker_dispatch_verified") is True,
             "real wheat field equivalence not qualified")
    need(
         report.get("baseline_revision")==BASELINE_REVISION and report.get("field_exact_equal") is True and
         report.get("mapper_calls")==0 and
         report.get("formal_workspace_modified") is False and
         report.get("baseline_output_sha256")==report.get("candidate_output_sha256") and
         re.fullmatch(r"[0-9a-f]{64}", report.get("candidate_output_sha256","")),"real wheat field equivalence not qualified")
    oldpath=checked(declaration["baseline_archive"]);newpath=checked(declaration["candidate_archive"])
    need(digest(oldpath)==BASELINE_ARCHIVE_SHA256==report.get("baseline_tools_sha256"),"not the original 2064cb4c archive")
    need(digest(newpath)==report.get("candidate_tools_sha256"),"candidate differs from qualified archive")
    old,new=contents(oldpath),contents(newpath)
    prefix="tools/lgz_core/";allowed={prefix+n for n in pins}
    need({n for n in old.keys()|new.keys() if old.get(n)!=new.get(n)}==allowed,"unreviewed change outside exact engineering scope")
    for name,pin in pins.items():
        need(sha256(new[prefix+name]).hexdigest()==pin,"unreviewed engineering bytes: "+name)
    for filename,symbol in [("q0_admission.py","AdmissionPolicy"),("q0_paths.py","PathPolicy"),("q0_collinear.py","ContinuousAdmissionPolicy")]:
        need(policy(old[prefix+filename],symbol)==policy(new[prefix+filename],symbol),"scientific policy changed: "+symbol)
    # Bind the actual transition payload to the exact tree used in qualification,
    # not just the three edited files. Import closure is checked by the preparer.
    for path in (bundle/"runtime").glob("*.py"):
        need(prefix+path.name in new and digest(path)==sha256(new[prefix+path.name]).hexdigest(),"transition differs from qualified engine: "+path.name)
    support=bundle/"support/workspace_layout.py"
    need(digest(support)==sha256(new["tools/workspace_layout.py"]).hexdigest(),"qualified support module differs")
    return declaration


# Scientific successor: source ownership changes by design, not field-exact.
SOURCE_REVISION = "adfe5e31831bc995aaec127a5ab98c1b65a37567"
SOURCE_PARENT = "9291117613910937da5f4f9c3c57beadb7885254"
SOURCE_SCHEMA = "q0_cross_chromosome_source_occupancy_v1"
SOURCE_FILES = {
    "q0_admission.py": "9e34cfddc1418cc114cca19142ca302795fc509d001a517ae4ee96662fa9a3cb",
    "q0_selection_cache.py": "988ea48233538794e91eb9a1b028b04c890e12bed24896dac639fa1442295382",
    "q0_collinear.py": "d77c8ba46a4f2c599ea25f0258afc4af43dbf12a540e70559a5981b2ccb39a13",
}
SOURCE_EVIDENCE = {
    "baseline_archive": "e1b5b25cf6fe0e565cef2bcc8efd6e67714b4ba01fba43ec2d4f6e74f66faed0",
    "candidate_archive": "36c1573bf59a8fa6427fbb8e71d6c3a963ee9b821b16666dd2b27b3800daa560",
    "baseline_replay": "b07c4bafc970c0f2e412946926eb16c947d3e981687b507077345f4f70e279cd",
    "fixed_replay": "03c77fc5a92cbd8f309e2b211c828d40766da8c5415aec9285dcfebf36f6c3cc",
    "census": "06cb554006533b2a35aeb1e5a641c76af7dfc0f621165b3c46274ec28cb5b3c7",
}
SOURCE_TRANSITION = "dbd07f2d31489146a63471e1484d500ae0407b4918c85657e38f6b1f213f09c4"
SOURCE_JOURNAL = "4693c2774cf7be523e6c6854292a45cfd84f09ceb048cb48d39fe2c44e84b1ae"


def validate_source_change(bundle, manifest):
    auth = manifest["source_occupancy_change"]
    need(auth["schema"] == SOURCE_SCHEMA and auth["baseline_revision"] == SOURCE_PARENT
         and auth["runtime_revision"] == manifest["git_revision"] == SOURCE_REVISION
         and manifest["previous_job"] == 43224098 and not manifest.get("exact_engineering_change"),
         "wrong source-occupancy lineage")
    parent = checked(manifest["previous_transition"])
    need(digest(parent) == SOURCE_TRANSITION and digest(parent.parent / "installation/receipt.json") == SOURCE_JOURNAL,
         "not the reviewed installed parent")
    for key, pin in SOURCE_EVIDENCE.items():
        need(digest(checked(auth[key])) == pin, "wrong source change evidence: " + key)
    old, new = (contents(checked(auth[key])) for key in ("baseline_archive", "candidate_archive"))
    prefix = "tools/lgz_core/"
    need({n for n in old.keys() | new.keys() if old.get(n) != new.get(n)} == {prefix+n for n in SOURCE_FILES},
         "unreviewed source-ownership archive change")
    for folder, base in (("runtime", prefix), ("support", "tools/")):
        for path in (bundle/folder).glob("*.py"):
            need(path.read_bytes() == new[base+path.name], "transition file differs from source archive: " + path.name)
    return auth
