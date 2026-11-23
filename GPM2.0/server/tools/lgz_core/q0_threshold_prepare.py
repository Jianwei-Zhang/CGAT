"""Prepare a supported Q0 backbone; publish only a generation the independent consumer can verify."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from . import q0_preparation as prep
from .common import stable_id
from .q0_alignments import read_paf_observations as _native_observations
from .q0_retained_hits import read_retained_paf, retained_geometry_cache, retained_names
from .q0_paths import PairLink
from .q0_sources import Q0EvidenceError, merged_intervals, split_source
from .q0_threshold_acceptance import MAX_REPAIRS, SCOPE, SEMANTICS, ThresholdRepairRequired, audit


class _CoverageRow:
    """Coverage needs a reiterable operation stream, not a freshly expanded CIGAR tuple."""
    __slots__ = ('hit', 'query_name', 'target_name', 'query_length', 'target_length', 'matches', 'block_length')

    def __init__(self, hit):
        self.hit = hit
        self.query_name, self.target_name = hit.query_name, hit.target_name
        self.query_length, self.target_length = hit.query_length, hit.target_length
        self.matches, self.block_length = hit.matches, hit.block_length

    @property
    def cigar(self): return self.hit._ops()

    def aligned_blocks(self): return self.hit.aligned_blocks()


class _PartitionNames(dict):
    """Validate only encountered names, but against this matrix's exact partition, never a larger dataset."""
    def __init__(self, lengths, canonical):
        self.lengths = lengths
        self.canonical = canonical

    def __missing__(self, name):
        n = self.lengths[name]
        result = self.canonical.get(name)
        if result is None:
            if not name or any(c.isspace() for c in name):
                raise KeyError(name)
            self.canonical[name] = result = (name,n)
        elif n != result[1]:
            raise Q0EvidenceError('draft source length differs between partitions')
        self[name] = result
        return result


class _DraftMatrices:
    """One preparation call, one verified generation. Never a persistent success or cache."""
    def __init__(self, root):
        self.root = root
        self.rows = {}
        self.canonical = defaultdict(dict)
        self.short_geometry = retained_geometry_cache()

    def observe(self, path, *, artifact, query_dataset, target_dataset, query_lengths, target_lengths):
        if artifact in self.rows or path != prep.artifact_path(self.root, artifact):
            raise Q0EvidenceError('duplicate or foreign draft matrix')
        before = prep.file_signature(path)
        hits = []
        for hit in read_retained_paf(path, artifact=artifact, query_names=_PartitionNames(query_lengths,self.canonical[query_dataset]),
                                     target_names=_PartitionNames(target_lengths,self.canonical[target_dataset]), short_geometry=self.short_geometry):
            hits.append(hit)
            yield _CoverageRow(hit)
        if prep.file_signature(path) != before:
            raise Q0EvidenceError('draft matrix changed during initial observation')
        self.rows[artifact] = (query_dataset, target_dataset, before, hits)

    def check_inventory(self, alignments):
        paths = [row['paf'] for row in alignments]
        if len(paths) != len(set(paths)) or set(paths) != self.rows.keys():
            raise Q0EvidenceError('incomplete shared draft matrix inventory')

    def take(self, row):
        artifact = row['paf']
        q,t,before,hits = self.rows.pop(artifact)
        if (q,t) != (row['query_dataset'],row['target_dataset']) or prep.file_signature(prep.artifact_path(self.root,artifact)) != before:
            raise Q0EvidenceError('draft matrix generation or dataset roles changed')
        return hits


class _ThresholdInputs(prep._ProofRepairInputs):
    """Release the already verified source DNA into the first mapper pass, not a second copy."""
    first = None
    matrices = None

    def _read_initial(self):
        # An existing ready generation may be reusable: don't retain millions of hits for a cache check.
        # Wrapped readers keep their original signature, routing provenance and independent draft scan.
        if (prep.workspace_artifact_path(self.root, prep.MANIFEST).exists() or prep._initial_inputs is not prep._native_initial_inputs
                or prep.read_paf_observations is not _native_observations):
            return super()._read_initial()
        self.matrices = _DraftMatrices(self.root)
        return prep._initial_inputs(self.root, matrix_reader=self.matrices.observe)

    def read(self):
        if self.first is None:
            return super().read()
        self.verify()
        first, self.first = self.first, None
        return first


def initial_questions(root, seqs, lengths, assignments, alignments, *, matrices=None, threads=1):
    """Only decision input, not a private ready/catalog. Keep self and cross hits and original CIGAR."""
    from .q0_admission import EvidenceInput, select_q0_paths
    from .q0_threshold_questions import questions
    keys = {(s.dataset, s.contig): s for s in seqs}
    parts, edges, refs, links, by_dataset = {}, [], defaultdict(list), [], defaultdict(dict)
    for key, seq in seqs.items():
        by_dataset[key.dataset][key.contig] = len(seq)
        try:
            info = split_source(key, seq, min_gap=prep.POLICY['min_gap'])
        except Q0EvidenceError:
            continue  # Same invalid-source verdict as ordinary catalog/admission.
        parts.update((p.segment_id,p) for p in info.segments)
        edges.extend(info.adjacencies)
    names = {ds: retained_names(lens) for ds, lens in by_dataset.items()}
    ref_names = retained_names(lengths)
    short_geometry = retained_geometry_cache()
    for dataset, qnames in names.items():
        rel = f'runs/{dataset}_vs_ref/result.paf'
        for hit in read_retained_paf(prep.artifact_path(root,rel), query_names=qnames, target_names=ref_names,
                                     artifact=rel, short_geometry=short_geometry):
            source = keys[dataset, hit.query_name]
            refs[source].append(hit)
    if matrices is not None:
        matrices.check_inventory(alignments)
    for row in alignments:
        q, t, rel = row['query_dataset'], row['target_dataset'], row['paf']
        hits = (matrices.take(row) if matrices is not None else
                read_retained_paf(prep.artifact_path(root,rel), query_names=names[q], target_names=names[t],
                                  artifact=rel, short_geometry=short_geometry))
        for hit in hits:
            left, right = keys[q, hit.query_name], keys[t, hit.target_name]
            links.append(PairLink(hit, left, right))
        del hits
    data = EvidenceInput(seqs,parts,lengths,dict(refs),tuple(links),tuple(edges),{},'threshold-plan-not-published')
    del links, edges  # the immutable selection input now owns these references
    selected = (select_q0_paths(data, screen_threads=threads, progress=lambda msg: print("LGZ q0 first draft: " + msg, flush=True))
                if threads > 1 else select_q0_paths(data))
    need, _ = questions(data, selected, assignments)
    return need, any(r.path is not None for r in selected.paths.values())


def initial_generation(root, snapshot, mapper, *, threads=1):
    initial = snapshot.read()
    seqs,lengths,assignments,options,_,alignments,_,inputs = initial
    if 'q0_supplement_scope' in options:
        raise Q0EvidenceError('set threshold scope on the evidence command')
    tool = prep.executable_identity(mapper); policy = prep.supplement_policy(SCOPE); builder = prep.builder_identity()
    request = stable_id('q0-evidence-input', {'inputs':inputs, 'tool':tool, 'policy':policy, 'builder':builder})
    ready = prep.workspace_artifact_path(root, prep.MANIFEST)
    if ready.is_file():
        old = prep.json_file(ready)
        if old.get('input_fingerprint') == request:
            old = prep.load_verified_evidence(root); snapshot.verify()
            return request, old, True, None
    need, have_path = initial_questions(root, seqs, lengths, assignments, alignments, matrices=snapshot.matrices, threads=threads)
    snapshot.matrices = None
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
    prep.atomic_write_json(prep.workspace_artifact_path(root, name), catalog); snapshot.verify()
    receipt = {'schema':prep.SCHEMA,'status':'success','policy':policy,'builder':builder,'input_fingerprint':request,
               'inputs':inputs,'outputs':[prep.identity(root,name)],'catalog':name,'tool':tool}
    return request, receipt, False, {}


def prepare(root, threads, mapper):
    from .q0_admission import load_evidence_input, select_q0_paths
    if threads < 1:
        raise Q0EvidenceError('q0 evidence threads must be positive')
    root = root.resolve(); prep._readless_package(root)
    snapshot = _ThresholdInputs(root)
    request, receipt, cached, wanted = initial_generation(root, snapshot, mapper, threads=threads)
    full = wanted is None and receipt is None
    for n in range(MAX_REPAIRS+3):
        if receipt is None:
            receipt,_,_ = prep._prepare_evidence_pass(root,threads=threads,minimap2=mapper,supplement_scope=SCOPE,
                draft=True,frontier_override=None if full else wanted,fallback_reason='threshold_full_fallback' if full else None,
                expected_input=request,repair_inputs=snapshot)
        output_paths = [prep.workspace_artifact_path(root, row['path']) for row in receipt['outputs']]
        before = [prep.file_signature(p) for p in output_paths]
        data = load_evidence_input(root,_draft=receipt); selection = select_q0_paths(data)
        try:
            audit(data,selection)
        except ThresholdRepairRequired as stopped:
            if full: raise
            need = stopped.demand
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
                prep.atomic_write_json(prep.workspace_artifact_path(root, prep.MANIFEST), receipt)
            return receipt
        del data,selection
        if need is None or n >= MAX_REPAIRS or wanted is None:
            full = True
        else:
            widened = {**wanted, **{s:merged_intervals((*wanted.get(s,()),*v)) for s,v in need.items()}}
            full = widened == wanted
            wanted = widened
        receipt, cached = None, False
    raise Q0EvidenceError('threshold preparation ended without a verified Q0')
