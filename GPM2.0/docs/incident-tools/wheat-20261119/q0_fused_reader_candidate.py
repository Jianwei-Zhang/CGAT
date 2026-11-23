"""Diagnostic fused reader; never bypass content, name/length, CIGAR-span or ID checks."""
from array import array
from functools import lru_cache
from hashlib import sha256
from lgz_core.common import canonical_json
from lgz_core.q0_alignments import _CIGAR
from lgz_core.q0_retained_hits import RetainedHit, _CODES
from lgz_core.q0_sources import Interval, Q0EvidenceError


def geometry(text):
    if text and text[-1] in _CODES and text[0] in '123456789' and text[:-1].isascii() and text[:-1].isdigit():
        tokens=[(text[:-1],text[-1])]
    else:
        tokens=_CIGAR.findall(text)
        if not tokens or sum(len(n)+1 for n,_ in tokens)!=len(text):raise Q0EvidenceError('malformed CIGAR')
    q=t=0; packed=array('I'); wide=False
    for n,k in tokens:
        v=int(n)
        if k in 'MI=X': q+=v
        if k in 'MDN=X': t+=v
        if v >= 1<<29:wide=True
        elif not wide:packed.append((v<<3)|_CODES[k])
    return (tuple((int(n),k) for n,k in tokens) if wide else packed.tobytes()),q,t

cached_geometry=lru_cache(maxsize=8192)(geometry)


def prefix(artifact):
    if not artifact:raise Q0EvidenceError('empty artifact')
    return ('['+canonical_json(artifact)+',').encode('ascii')


def parsed(line, artifact, number, pre, qnames, tnames):
    if not artifact or type(number) is not int or number<1:raise Q0EvidenceError('invalid PAF location')
    raw=line.rstrip('\r\n'); f=raw.split('\t');
    if len(f)<12:raise Q0EvidenceError('short PAF row')
    # Name dictionary built only from previously validated inventory names. An invalid name cannot be inserted.
    try:qname,ql=qnames[f[0]]; tname,tl=tnames[f[5]]
    except KeyError as exc:raise Q0EvidenceError('unknown source') from exc
    try:
        qlen,qs,qe=int(f[1]),int(f[2]),int(f[3]); tlen,ts,te=int(f[6]),int(f[7]),int(f[8]);matches,bl,mq=int(f[9]),int(f[10]),int(f[11]); qi,ti=Interval(qs,qe),Interval(ts,te)
    except ValueError as exc:raise Q0EvidenceError('invalid PAF fields') from exc
    if qlen!=ql or tlen!=tl or qe>ql or te>tl or f[4] not in ('+','-') or bl<1 or not 0<=matches<=min(bl,qe-qs,te-ts) or not 0<=mq<=255:raise Q0EvidenceError('invalid row bounds or statistics')
    tags=f[12:]; cg=[tag[5:] for tag in tags if tag.startswith('cg:Z:')]
    if len(cg)!=1:raise Q0EvidenceError('missing or duplicate CIGAR')
    text=cg[0]; packed,q,t=(cached_geometry if len(text)<=96 else geometry)(text)
    if q!=qe-qs or t!=te-ts:raise Q0EvidenceError('CIGAR span differs')
    h=sha256(raw.encode('utf-8')).hexdigest(); eid='q0-paf-'+sha256(pre+str(number).encode('ascii')+b',"'+h.encode('ascii')+b'"]').hexdigest()[:24]
    return RetainedHit(eid,artifact,number,h,qname,qlen,qi,f[4],tname,tlen,ti,matches,bl,mq,packed,'\t'.join(tags))


def names(lengths):
    if any(not name or any(c.isspace() for c in name) for name in lengths): raise Q0EvidenceError('invalid inventory name')
    return {name:(name,n) for name,n in lengths.items()}
