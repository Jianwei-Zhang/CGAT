"""Lossless retained PAF geometry and strict one-pass decoding for threshold planning.

Record and artifact identities follow the ordinary PAF reader. A retained row is not a receipt.
"""
from array import array
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from types import SimpleNamespace

from .common import canonical_json
from .q0_alignments import PafAlignment, _CIGAR, _aligned_blocks, open_paf_text, parse_paf_line
from .q0_sources import Interval, Q0EvidenceError

_OPS = 'MIDN=X'
_CODES = {c: i for i, c in enumerate(_OPS)}


def _pack(cigar):
    try:
        return array('I', ((n << 3) | _CODES[op] for n, op in cigar)).tobytes()
    except OverflowError:
        # Valid PAFs need not fit a fixed-width machine word. No clipping/splitting.
        return cigar


@dataclass(frozen=True, slots=True)
class RetainedHit:
    evidence_id: str
    artifact: str
    line_number: int
    record_sha256: str
    query_name: str
    query_length: int
    query: Interval
    strand: str
    target_name: str
    target_length: int
    target: Interval
    matches: int
    block_length: int
    mapq: int
    _packed: bytes | tuple
    _optional_fields: str

    @classmethod
    def from_validated(cls, h, query_name, target_name):
        # Callers supply canonical names from their declared, length-checked inventories.
        if query_name != h.query_name or target_name != h.target_name:
            raise ValueError('retained Q0 alignment name differs from validated PAF')
        return cls(h.evidence_id, h.artifact, h.line_number, h.record_sha256, query_name, h.query_length,
                   h.query, h.strand, target_name, h.target_length, h.target, h.matches, h.block_length,
                   h.mapq, _pack(h.cigar), '\t'.join(h.tags))

    def _ops(self):
        if isinstance(self._packed, bytes):
            return ((word >> 3, _OPS[word & 7]) for word in memoryview(self._packed).cast('I'))
        return iter(self._packed)

    @property
    def tags(self): return tuple(self._optional_fields.split('\t'))

    @property
    def cigar(self): return tuple(self._ops())

    mapping_quality = PafAlignment.mapping_quality

    def _run_view(self):
        return SimpleNamespace(query=self.query, target=self.target, strand=self.strand, cigar=self._ops())

    def aligned_blocks(self): return _aligned_blocks(self._run_view())

    def paired_query_intervals(self): return PafAlignment.paired_query_intervals(self._run_view())


class EvidenceRows(Mapping):
    """Same public rows, without a second four-key dictionary per retained alignment."""
    def __init__(self, rows): self._rows = rows
    def __len__(self): return len(self._rows)
    def __iter__(self): return iter(self._rows)
    def __contains__(self, key): return key in self._rows
    def __getitem__(self, key):
        from .q0_catalog import evidence_ref
        item = self._rows[key]
        return evidence_ref(item) if isinstance(item, RetainedHit) else item


def _geometry(text):
    """Validate the entire ASCII CIGAR; return packed operations and both consumed spans."""
    if (0 < len(text) <= 96 and text[0] in '123456789' and text[-1] in _CODES
            and (digits := text[:-1]).isascii() and digits.isdigit()):
        tokens = [(digits, text[-1])]
    else:
        tokens = _CIGAR.findall(text)
        if not tokens or sum(len(n) + 1 for n, _ in tokens) != len(text):
            raise Q0EvidenceError('malformed or unsupported PAF CIGAR')
    query_span = target_span = 0
    packed = array('I')
    try:
        for digits, op in tokens:
            n = int(digits)
            if op in 'MI=X': query_span += n
            if op in 'MDN=X': target_span += n
            packed.append((n << 3) | _CODES[op])
    except OverflowError:
        # Same unbounded integer semantics as the ordinary parser, even mid-record.
        ops = tuple((int(digits), op) for digits, op in tokens)
        return ops, sum(n for n, op in ops if op in 'MI=X'), sum(n for n, op in ops if op in 'MDN=X')
    return packed.tobytes(), query_span, target_span


def retained_geometry_cache():
    """One bounded short-CIGAR cache per draft, never a global evidence cache."""
    return lru_cache(maxsize=8192)(_geometry)


def retained_names(lengths):
    # Like read_paf, a bad unused inventory name does not invalidate other records.
    return {name: (name, n) for name, n in lengths.items() if name and not any(c.isspace() for c in name)}


def _retained_line(line, artifact, number, prefix, query_names, target_names, short_geometry):
    raw = line.rstrip('\r\n')
    f = raw.split('\t')
    if len(f) < 12:
        raise Q0EvidenceError('short PAF record')
    if query_names is None:
        # A worker never gets the DNA or the inventory. These lengths are only claims
        # until the owner binds BOTH names and lengths to this matrix's exact partition.
        qname, qlen = f[0], int(f[1])
        tname, tlen = f[5], int(f[6])
    else:
        qname, qlen = query_names[f[0]]
        tname, tlen = target_names[f[5]]
    query = Interval(int(f[2]), int(f[3]))
    target = Interval(int(f[7]), int(f[8]))
    matches, length, mapq = int(f[9]), int(f[10]), int(f[11])
    if (int(f[1]) != qlen or int(f[6]) != tlen or query.end > qlen or target.end > tlen
            or f[4] not in ('+', '-') or length < 1 or not 0 <= matches <= min(length, query.length, target.length)
            or not 0 <= mapq <= 255):
        raise Q0EvidenceError('invalid PAF bounds, strand or statistics')
    tags = f[12:]
    cigar = [v[5:] for v in tags if v.startswith('cg:Z:')]
    if len(cigar) != 1:
        raise Q0EvidenceError('expected one cg:Z CIGAR')
    text = cigar[0]
    packed, qspan, tspan = (short_geometry if len(text) <= 96 else _geometry)(text)
    if qspan != query.length or tspan != target.length:
        raise Q0EvidenceError('CIGAR span differs from PAF coordinates')
    digest = sha256(raw.encode('utf-8')).hexdigest()
    # Exactly stable_id('q0-paf', [artifact, number, digest]); only the artifact is invariant.
    evidence = sha256(prefix + str(number).encode('ascii') + b',"' + digest.encode('ascii') + b'"]').hexdigest()
    if query_names is None:
        # Plain scalars travel without pickling millions of dataclasses, repeated file
        # paths or reference inventories. Offsets within the input block supply line IDs.
        return ('q0-paf-' + evidence[:24], digest, qname, qlen, query.start, query.end, f[4],
                tname, tlen, target.start, target.end, matches, length, mapq, packed, '\t'.join(tags))
    return RetainedHit('q0-paf-' + evidence[:24], artifact, number, digest, qname, qlen, query, f[4],
                       tname, tlen, target, matches, length, mapq, packed, '\t'.join(tags))


def _checked_line(line, path, artifact, number, prefix, query_names, target_names, short_geometry):
    if line.startswith('#') or not line.strip():
        return None
    try:
        return _retained_line(line, artifact, number, prefix, query_names, target_names, short_geometry)
    except (ValueError, KeyError):
        # Only exceptional rows revisit the canonical decoder. It is authoritative
        # for valid edge cases and reports the normal file/line diagnostic on damage.
        original = parse_paf_line(line, artifact=artifact, line_number=number)
        q = query_names.get(original.query_name); t = target_names.get(original.target_name)
        if q is None or t is None or (q[1], t[1]) != (original.query_length, original.target_length):
            raise Q0EvidenceError(f'{path}:{number}: PAF names/lengths differ from inputs')
        return RetainedHit.from_validated(original, q[0], t[0])


def read_retained_paf(path, *, artifact, query_names, target_names, short_geometry, threads=1):
    """One ordered physical read. Parallelism changes neither the declared partition nor row identity."""
    if not artifact:
        raise Q0EvidenceError('missing PAF artifact')
    if query_names is None or target_names is None:
        raise Q0EvidenceError('missing PAF source inventory')
    prefix = ('[' + canonical_json(artifact) + ',').encode('ascii')
    def serial(number, line):
        return _checked_line(line, path, artifact, number, prefix, query_names, target_names, short_geometry)
    try:
        with open_paf_text(path, newline='') as stream:
            if threads > 1:
                from .q0_paf_chunks import decode_ordered, worker_budget
                workers = worker_budget(path, threads)
                if workers:
                    yield from decode_ordered(stream, artifact, prefix, query_names, target_names, serial, workers)
                    return
            for number, line in enumerate(stream, 1):
                hit = serial(number, line)
                if hit is not None:
                    yield hit
    except (OSError, UnicodeError) as exc:
        raise Q0EvidenceError(f'cannot read q0 alignment evidence {path}: {exc}') from exc
