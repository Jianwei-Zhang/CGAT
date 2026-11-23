"""Lossless in-memory shape for retained threshold hits. Never changes PAF parsing or cache IDs.

The ordinary strict parser validates each complete row first. Store its ordered CIGAR as packed
unsigned ints and all optional tags in their original order/text. This object is not a receipt.
"""
from array import array
from collections.abc import Mapping
from dataclasses import dataclass
from types import SimpleNamespace

from .q0_alignments import PafAlignment, _aligned_blocks
from .q0_sources import Interval

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
