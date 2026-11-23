"""Prepare a supported Q0 backbone; publish only a generation the independent consumer can verify."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from . import q0_preparation as prep
from .common import stable_id
from .q0_alignments import read_paf
from .q0_paths import PairLink
from .q0_sources import Q0EvidenceError, merged_intervals, split_source
from .q0_threshold_acceptance import MAX_REPAIRS, SCOPE, SEMANTICS, audit


class _ThresholdInputs(prep._ProofRepairInputs):
    """Release the already verified source DNA into the first mapper pass, not a second copy."""
    first = None

    def read(self):
        if self.first is None:
            return super().read()
        self.verify()
        first, self.first = self.first, None
        return first


def initial_questions(root, seqs, lengths, assignments, alignments):
    """Only decision input, not a private ready/catalog. Keep self and cross hits and original CIGAR."""
    from .q0_admission import EvidenceInput, select_q0_paths
    from .q0_threshold_questions import questions
    from .q0_retained_hits import RetainedHit
    keys = {(s.dataset, s.contig): s for s in seqs}
    ref_names = {name: name for name in lengths}
    parts, edges, refs, links, by_dataset = {}, [], defaultdict(list), [], defaultdict(dict)
    for key, seq in seqs.items():
        by_dataset[key.dataset][key.contig] = len(seq)
        try:
            info = split_source(key, seq, min_gap=prep.POLICY['min_gap'])
        except Q0EvidenceError:
            continue  # Same invalid-source verdict as ordinary catalog/admission.
        parts.update((p.segment_id,p) for p in info.segments)
        edges.extend(info.adjacencies)
    for dataset, qlens in by_dataset.items():
        rel = f'runs/{dataset}_vs_ref/result.paf'
        for hit in read_paf(prep.artifact_path(root,rel), query_lengths=qlens, target_lengths=lengths, artifact=rel):
            source = keys[dataset, hit.query_name]
            refs[source].append(RetainedHit.from_validated(hit, source.contig, ref_names[hit.target_name]))
    for row in alignments:
        q, t, rel = row['query_dataset'], row['target_dataset'], row['paf']
        for hit in read_paf(prep.artifact_path(root,rel), query_lengths=by_dataset[q], target_lengths=by_dataset[t], artifact=rel):
            left, right = keys[q, hit.query_name], keys[t, hit.target_name]
            links.append(PairLink(RetainedHit.from_validated(hit, left.contig, right.contig), left, right))
    data = EvidenceInput(seqs,parts,lengths,dict(refs),tuple(links),tuple(edges),{},'threshold-plan-not-published')
    selected = select_q0_paths(data)
    need, _ = questions(data, selected, assignments)
    return need, any(r.path is not None for r in selected.paths.values())


def initial_generation(root, snapshot, mapper):
    initial = snapshot.read()
    seqs,lengths,assignments,options,_,alignments,_,inputs = initial
    if 'q0_supplement_scope' in options:
        raise Q0EvidenceError('set threshold scope on the evidence command')
    tool = prep.executable_identity(mapper); policy = prep.supplement_policy(SCOPE); builder = prep.builder_identity()
    request = stable_id('q0-evidence-input', {'inputs':inputs, 'tool':tool, 'policy':policy, 'builder':builder})
    if (root/prep.MANIFEST).is_file():
        old = prep.json_file(root/prep.MANIFEST)
        if old.get('input_fingerprint') == request:
            old = prep.load_verified_evidence(root); snapshot.verify()
            return request, old, True, None
    need, have_path = initial_questions(root, seqs, lengths, assignments, alignments)
    snapshot.verify()
    if need != {}:
        snapshot.first = initial
        return request, None, False, need
    if not have_path:
        raise Q0EvidenceError('no chromosome has a trustworthy q0 path')
    # A publishable base generation needs a real catalog; a discarded planning draft does not.
    base = prep.build_catalog(root,seqs,lengths,assignments,min_gap=prep.POLICY['min_gap'])
    base.payload['supplement_scope'] = {'requested':SCOPE,'effective':'base_only','acceptance':SEMANTICS,
                                        'threshold_request':[],'unsearched_part_intervals':[]}
    catalog = base.finish(); catalog['base_alignments'] = alignments; catalog['supplementary_alignments'] = []
    name = f"grt/evidence/q0_prepare/{stable_id('catalog',catalog)}.json"
    prep.atomic_write_json(root/name,catalog); snapshot.verify()
    receipt = {'schema':prep.SCHEMA,'status':'success','policy':policy,'builder':builder,'input_fingerprint':request,
               'inputs':inputs,'outputs':[prep.identity(root,name)],'catalog':name,'tool':tool}
    return request, receipt, False, {}


def prepare(root, threads, mapper):
    from .q0_admission import load_evidence_input, select_q0_paths
    from .q0_frontier_scope import UnsearchedQ0Context
    from .q0_threshold_questions import questions
    if threads < 1:
        raise Q0EvidenceError('q0 evidence threads must be positive')
    root = root.resolve(); prep._readless_package(root)
    snapshot = _ThresholdInputs(root)
    request, receipt, cached, wanted = initial_generation(root, snapshot, mapper)
    full = wanted is None and receipt is None
    for n in range(MAX_REPAIRS+3):
        if receipt is None:
            receipt,_,_ = prep._prepare_evidence_pass(root,threads=threads,minimap2=mapper,supplement_scope=SCOPE,
                draft=True,frontier_override=None if full else wanted,fallback_reason='threshold_full_fallback' if full else None,
                expected_input=request,repair_inputs=snapshot)
        output_paths = [root/prep._artifact_member(row['path']) for row in receipt['outputs']]
        before = [prep.file_signature(p) for p in output_paths]
        data = load_evidence_input(root,_draft=receipt); selection = select_q0_paths(data)
        try:
            audit(data,selection)
        except UnsearchedQ0Context:
            if full: raise
        else:
            if not any(r.path is not None for r in selection.paths.values()):
                raise Q0EvidenceError('no chromosome has a trustworthy q0 path')
            snapshot.verify(); prep.load_verified_evidence(root,_draft=receipt)
            if (prep._partition_sha256(Path(receipt['tool']['resolved'])) != receipt['tool']['sha256']
                    or receipt['policy'] != prep.supplement_policy(SCOPE) or receipt['builder'] != prep.builder_identity()):
                raise Q0EvidenceError('threshold preparation identities changed before publication')
            if before != [prep.file_signature(p) for p in output_paths]:
                raise Q0EvidenceError('threshold output changed during admission')
            snapshot.verify()
            if not cached:
                prep.atomic_write_json(root/prep.MANIFEST,receipt)
            return receipt
        assignments = ({'dataset_name':d,'seq_name':s,'assigned_chr_name':c} for d,s,c in data.threshold_scope.assignments)
        need,_ = questions(data,selection,assignments)
        del data,selection
        if need is None or n >= MAX_REPAIRS or wanted is None:
            full = True
        else:
            widened = {**wanted, **{s:merged_intervals((*wanted.get(s,()),*v)) for s,v in need.items()}}
            full = widened == wanted
            wanted = widened
        receipt, cached = None, False
    raise Q0EvidenceError('threshold preparation ended without a verified Q0')
