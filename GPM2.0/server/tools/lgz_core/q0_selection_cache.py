"""Published, same-generation formal selection; never a first-request checkpoint.

The ready manifest binds the complete artifact bytes. Its header binds the
same evidence generation (excluding this one sidecar), selector and policies.
Only expensive placement/graph/ranking is reused: consumers still verify all
evidence, enforce source occupancy, audit acceptance and reconstruct sequence.
"""
from dataclasses import fields, asdict
from collections import defaultdict
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import tempfile

from .common import stable_id
from .q0_sources import Q0EvidenceError, SourceKey, Interval

SCHEMA = 'lgz_q0_accepted_selection_v1'
FIELD = 'accepted_selection'
PATTERN = r'grt/evidence/q0_prepare/selections/q0-selection-[a-f0-9]{24}/selection.jsonl'


def output_path(manifest):
    relative = manifest.get(FIELD)
    if relative is None:
        return None
    if (not isinstance(relative, str) or not re.fullmatch(PATTERN, relative)
            or 'threshold' not in manifest.get('policy', {}).get('decision_frontier', {})):
        raise Q0EvidenceError('invalid accepted Q0 selection output')
    return relative


def base_manifest(manifest):
    relative = output_path(manifest)
    if relative is None:
        return manifest
    rows = manifest['outputs']
    if sum(row['path'] == relative for row in rows) != 1:
        raise Q0EvidenceError('accepted Q0 selection is not bound exactly once')
    return {**{k:v for k,v in manifest.items() if k != FIELD},
            'outputs':[row for row in rows if row['path'] != relative]}


def binding(manifest):
    from .q0_admission import AdmissionPolicy, selector_identity
    from .q0_paths import PathPolicy
    return {'schema':SCHEMA, 'evidence_generation':stable_id('q0-selection-evidence',base_manifest(manifest)),
            'input_fingerprint':manifest['input_fingerprint'], 'selector':selector_identity(),
            'admission_policy':asdict(AdmissionPolicy()), 'path_policy':asdict(PathPolicy()), 'quality_pass':None}


@lru_cache(maxsize=1)
def _types():
    from .q0_paths import Placement, ReferenceAnchor, Join, Slice, Path as Q0Path, SearchResult
    return {t.__name__:t for t in (SourceKey,Interval,Placement,ReferenceAnchor,Join,Slice,Q0Path,SearchResult)}


def encode(value):
    t = type(value)
    if _types().get(t.__name__) is t:
        return {'object':[t.__name__,[encode(getattr(value,f.name)) for f in fields(value)]]}
    if t is tuple:
        return {'tuple':[encode(x) for x in value]}
    if t is list:
        return [encode(x) for x in value]
    if isinstance(value,dict):
        return {'map':[[encode(k),encode(v)] for k,v in value.items()]}
    if value is None or t in (str,int,bool) or t is float and math.isfinite(value):
        return value
    raise Q0EvidenceError('unsupported accepted Q0 selection value')


def decode(value):
    if type(value) is list:
        return [decode(x) for x in value]
    if type(value) is dict:
        if set(value) == {'object'}:
            name,args = value['object']; cls = _types().get(name)
            if cls is None or not isinstance(args,list) or len(args)!=len(fields(cls)):
                raise Q0EvidenceError('invalid accepted Q0 selection object')
            return cls(*(decode(x) for x in args))
        if set(value) == {'tuple'}:
            return tuple(decode(x) for x in value['tuple'])
        if set(value) == {'map'}:
            pairs = [(decode(k),decode(v)) for k,v in value['map']]
            result = dict(pairs)
            if len(result)!=len(pairs):
                raise Q0EvidenceError('duplicate accepted Q0 selection map key')
            return result
        raise Q0EvidenceError('unknown accepted Q0 selection tag')
    if value is None or type(value) in (str,int,bool) or type(value) is float and math.isfinite(value):
        return value
    raise Q0EvidenceError('invalid accepted Q0 selection scalar')


def _write_line(stream,row):
    json.dump(row,stream,ensure_ascii=True,separators=(',',':'),allow_nan=False)
    stream.write('\n')


def store(root,manifest,data,selection):
    """Called only after the formal threshold audit succeeds, before ready publication."""
    from . import q0_preparation as prep
    from .q0_admission import PathSelection, AdmissionPolicy
    if (type(selection) is not PathSelection or selection.admission.policy != AdmissionPolicy()
            or data.threshold_scope is None or data.input_fingerprint != manifest['input_fingerprint']
            or data.ready_manifest_identity != stable_id('q0-ready-evidence',manifest)
            or set(selection.paths) != set(data.reference_lengths)):
        raise Q0EvidenceError('only a complete same-generation formal Q0 selection may be stored')
    stamp = binding(manifest)
    relative = f"grt/evidence/q0_prepare/selections/{stable_id('q0-selection',stamp)}/selection.jsonl"
    target = prep.workspace_artifact_path(root,relative)
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_symlink() or not target.parent.resolve().is_relative_to(root.resolve()):
        raise Q0EvidenceError('accepted Q0 selection escaped workspace')
    fd,name = tempfile.mkstemp(prefix='.selection-',dir=target.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as out:
            _write_line(out,['header',stamp])
            for placement in selection.admission.placements:
                _write_line(out,['placement',encode(placement)])
            for record in selection.admission.records:
                _write_line(out,['admission_record',encode(record)])
            for segment in selection.admission.unplaced_segment_ids:
                _write_line(out,['unplaced',segment])
            for source,intervals in selection.admission.ambiguous_intervals.items():
                _write_line(out,['ambiguous',encode(source),encode(intervals)])
            for chromosome,search in selection.paths.items():
                _write_line(out,['group',chromosome,encode(search)])
            _write_line(out,['end',len(selection.admission.placements),list(selection.paths)])
            out.flush();os.fsync(out.fileno())
        os.replace(name,target)
    finally:
        Path(name).unlink(missing_ok=True)
    result = base_manifest(manifest)
    return {**result,FIELD:relative,'outputs':[*result['outputs'],prep.identity(root,relative)]}


class VerifiedSelection:
    def __init__(self,selection,data,stamp):
        self.selection,self.ready,self.input,self.stamp = selection,data.ready_manifest_identity,data.input_fingerprint,stamp

    def for_data(self,data,admission_policy,path_policy,quality_pass):
        from .q0_admission import selector_identity
        if quality_pass is not None:
            raise Q0EvidenceError('accepted threshold selection does not cover reads QC')
        if (self.ready!=data.ready_manifest_identity or self.input!=data.input_fingerprint
                or self.stamp['selector']!=selector_identity() or quality_pass is not None
                or self.stamp['admission_policy']!=asdict(admission_policy)
                or self.stamp['path_policy']!=asdict(path_policy)):
            raise Q0EvidenceError('accepted Q0 selection generation or policies changed')
        return self.selection


def load(root,manifest,data):
    """The caller has verified the ready manifest; verify this artifact at consumption too."""
    from . import q0_preparation as prep
    from .q0_admission import Admission, AdmissionPolicy, PathSelection, _occupy_path
    from .q0_paths import Placement, SearchResult
    relative=output_path(manifest)
    if relative is None:
        return None
    if (data.ready_manifest_identity!=stable_id('q0-ready-evidence',manifest)
            or data.input_fingerprint!=manifest['input_fingerprint'] or data.threshold_scope is None):
        raise Q0EvidenceError('accepted Q0 selection belongs to another evidence input')
    expected=next((r for r in manifest['outputs'] if r['path']==relative),None)
    if expected is None or prep.identity(root,relative)!=expected:
        raise Q0EvidenceError('accepted Q0 selection bytes changed')
    stamp=binding(manifest)
    if relative!=f"grt/evidence/q0_prepare/selections/{stable_id('q0-selection',stamp)}/selection.jsonl":
        raise Q0EvidenceError('accepted Q0 selection identity changed')
    placements=[];records=[];unplaced=[];ambiguous={};searches={};occupied=defaultdict(list);ended=False
    try:
        with prep.artifact_path(root,relative).open(encoding='utf-8') as stream:
            if json.loads(stream.readline())!=['header',stamp]:
                raise Q0EvidenceError('accepted Q0 selection header differs')
            for raw in stream:
                row=json.loads(raw);kind=row[0]
                if kind=='placement':
                    p=decode(row[1])
                    if type(p) is not Placement:raise Q0EvidenceError('wrong accepted placement type')
                    placements.append(p)
                elif kind=='admission_record':records.append(decode(row[1]))
                elif kind=='unplaced':unplaced.append(row[1])
                elif kind=='ambiguous':
                    key=decode(row[1])
                    if key in ambiguous:raise Q0EvidenceError('duplicate ambiguity source')
                    ambiguous[key]=decode(row[2])
                elif kind=='group':
                    chromosome=row[1];search=decode(row[2])
                    if (chromosome in searches or chromosome not in data.reference_lengths or type(search) is not SearchResult
                            or search.path is not None and search.path.chromosome!=chromosome):
                        raise Q0EvidenceError('invalid accepted chromosome selection')
                    searches[chromosome]=search;_occupy_path(data,search,occupied)
                elif kind=='end':
                    if row!=['end',len(placements),list(searches)] or stream.read(1):
                        raise Q0EvidenceError('invalid accepted selection trailer')
                    ended=True;break
                else:raise Q0EvidenceError('unknown accepted selection record')
    except (OSError,ValueError,TypeError,KeyError,IndexError) as exc:
        raise Q0EvidenceError(f'cannot read accepted Q0 selection: {exc}') from exc
    if (not ended or list(searches)!=sorted(data.reference_lengths)
            or len({p.placement_id for p in placements})!=len(placements)):
        raise Q0EvidenceError('incomplete accepted Q0 selection')
    if prep.identity(root,relative)!=expected:
        raise Q0EvidenceError('accepted Q0 selection changed during consumption')
    selection=PathSelection(Admission(tuple(placements),records,tuple(unplaced),ambiguous,AdmissionPolicy()),searches,occupied)
    return VerifiedSelection(selection,data,stamp)
