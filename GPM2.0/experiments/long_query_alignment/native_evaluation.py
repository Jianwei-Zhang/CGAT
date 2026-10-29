"""Paired public/private recovery views for deferred downstream acceptance only.

Public recovery keeps unknown MAPQ; the paired private file carries native API
selection on SUPPLIED recovered state. Neither is proof of original DP equality.
No confidence promotion, AS approximation or independent candidate discovery.
"""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import re

import windowed_alignment as wa

MAX_LINE = 32*1024**2
HASH = re.compile(r"[0-9a-f]{64}\Z")
INTEGER = re.compile(r"(?:0|[1-9][0-9]*)\Z")
COMMON = {"cg","nn","NM","zg"}
PUBLIC = COMMON|{"zp"}
PRIVATE = PUBLIC|{"cm","s1","ms","rl","tp"}


def _fields(raw):
    if len(raw)>MAX_LINE or not raw.endswith(b"\n"):
        raise wa.ExperimentError("paired recovery view has an incomplete/oversized row")
    try:
        fields = raw.rstrip(b"\r\n").decode("ascii").split("\t")
    except UnicodeError as exc:
        raise wa.ExperimentError("paired recovery view must be ASCII PAF") from exc
    if len(fields)<12:
        raise wa.ExperimentError("paired recovery view lacks core columns")
    tags = {}
    for tag in fields[12:]:
        items = tag.split(":",2)
        if len(items)!=3 or len(items[0])!=2 or items[0] in tags:
            raise wa.ExperimentError("paired recovery view has malformed/duplicate tags")
        tags[items[0]] = tag
    return fields,tags


def _integer(tag,name):
    prefix = name+":i:"
    if not tag.startswith(prefix) or len(tag[len(prefix):])>10 or not INTEGER.fullmatch(tag[len(prefix):]):
        raise wa.ExperimentError("paired native metadata has an invalid nonnegative integer")
    value = int(tag[len(prefix):])
    if value>wa.INT32_MAX:
        raise wa.ExperimentError("paired native metadata exceeds supported int32")
    return value


def validate_row_pair(public,evaluated,validator):
    """Same ordered candidate/path, differing ONLY in the documented metadata.

    The enclosing producer hashes bind the private tags/MAPQ to its actual native
    selection receipt. This check is not a second MAPQ model and does not invent
    a whole-query equivalence certificate from matching path geometry.
    """
    validator(public)
    pf,pt = _fields(public)
    ef,et = _fields(evaluated)
    if pf[:11]!=ef[:11] or pf[11]!="255":
        raise wa.ExperimentError("public/private recovery candidate order or core geometry differs")
    if set(pt)!=PUBLIC or not PRIVATE<=set(et) or set(et)-PRIVATE-{"s2","zd"}:
        raise wa.ExperimentError("paired recovery view has missing/unsupported metadata; AS is not reconstructed")
    if (any(pt[k]!=et[k] for k in COMMON)
            or pt["zp"]!="zp:Z:experimental-native-selected-unknown-confidence"
            or et["zp"]!="zp:Z:experimental-native-evaluated"):
        raise wa.ExperimentError("public/private CIGAR, statistics or chain provenance differs")
    for key in ("nn","NM","zg","cm","s1","ms","rl"):
        _integer(et[key],key)
    if _integer(et["cm"],"cm")<3 or _integer(et["rl"],"rl")>int(ef[1]):
        raise wa.ExperimentError("native-evaluated candidate lacks valid original chain/query metadata")
    if len(ef[11])>2 or not INTEGER.fullmatch(ef[11]) or not 0<=int(ef[11])<=60:
        raise wa.ExperimentError("native-evaluated MAPQ must be a known native value, not 255")
    if et["tp"] not in ("tp:A:P","tp:A:S"):
        raise wa.ExperimentError("native-evaluated candidate has an unsupported primary type")
    primary = et["tp"]=="tp:A:P"
    if (primary!=("s2" in et)) or (not primary and int(ef[11])!=0):
        raise wa.ExperimentError("native-evaluated primary/subscore/secondary confidence is inconsistent")
    if "s2" in et:
        _integer(et["s2"],"s2")
    if "zd" in et and _integer(et["zd"],"zd") not in (1,2,3):
        raise wa.ExperimentError("native-evaluated candidate has an invalid split flag")
    return int(ef[11])


def validate_pair(public,evaluated,*,public_sha256,evaluated_sha256,validator):
    public,evaluated = Path(public),Path(evaluated)
    if not all(type(h) is str and HASH.fullmatch(h) for h in (public_sha256,evaluated_sha256)):
        raise wa.ExperimentError("paired recovery views need exact producer hashes")
    before = [wa.fingerprint(p) for p in (public,evaluated)]
    digests = [hashlib.sha256(),hashlib.sha256()]
    counts = Counter()
    rows = 0
    with public.open("rb") as source,evaluated.open("rb") as private:
        while raw := source.readline(MAX_LINE+1):
            other = private.readline(MAX_LINE+1)
            counts[validate_row_pair(raw,other,validator)] += 1
            digests[0].update(raw); digests[1].update(other)
            rows += 1
        if private.read(1):
            raise wa.ExperimentError("private recovery view has extra candidates")
    if (not rows or [d.hexdigest() for d in digests]!=[public_sha256,evaluated_sha256]
            or [wa.fingerprint(p) for p in (public,evaluated)]!=before):
        raise wa.ExperimentError("paired recovery views are empty or differ from immutable producer identities")
    return {"public_path":str(public),"public_sha256":public_sha256,
            "path":str(evaluated),"sha256":evaluated_sha256,"rows":rows,
            "mapq_histogram":{str(k):v for k,v in sorted(counts.items())},
            "ordered_candidate_path_equal":True,"AS_reconstructed":False,
            "scope":"native_API_on_supplied_recovered_state_only",
            "whole_query_dp_equivalence_certified":False,"production_ready":False}


def comparison_signature(path):
    """Ordered small-fixture contract, NOT complete PAF/AS/DP equivalence.

    Include every core field (therefore MAPQ) plus path, count, native parent,
    score and split tags used by the branch's native-selection controls. AS is
    intentionally not reconstructed; never call this a byte-equality check.
    """
    result = []
    keys = ("cg","NM","nn","ms","cm","s1","s2","tp","rl","zd")
    with Path(path).open("rb") as source:
        while raw := source.readline(MAX_LINE+1):
            fields,tags = _fields(raw)
            result.append((tuple(fields[:12]),tuple(tags.get(k) for k in keys)))
    return result
