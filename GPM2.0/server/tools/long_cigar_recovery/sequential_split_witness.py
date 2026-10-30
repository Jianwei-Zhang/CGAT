"""Conditional multi-fragment seed-score accounting, not candidate recovery.

Derived from upstream minimap2 v2.31 mm_split_reg and mm_align_skeleton:
separate the head, then repeatedly split the remaining tail in chain order.
No minimap2 patch or invocation. Implementation is NOT execution-validated yet.
"""
from __future__ import annotations

import struct

import stream_seed_trace as st
from windowed_alignment import ExperimentError

INT32_MAX = 2147483647
MAX_FRAGMENTS = 64


def bounded_integer(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= INT32_MAX:
        raise ExperimentError(f"{name} must be an integer in {minimum}..{INT32_MAX}")
    return value


def float32(value):
    return struct.unpack("f", struct.pack("f", value))[0]


def sequential_scores(original_score, counts):
    """Apply binary32 ratio/multiplication and double .499 at each tail split.

    A score/seed-count partition does not prove these were the aligner's actual
    split boundaries; the caller must separately establish seed provenance and
    compare to a diagnostic oracle. No direct proportional all-at-once shortcut.
    """
    bounded_integer(original_score, "original chain score")
    if not isinstance(counts, (list, tuple)) or not 2 <= len(counts) <= MAX_FRAGMENTS:
        raise ExperimentError("sequential witness requires 2..64 fragment counts")
    counts = tuple(bounded_integer(n, "fragment seed count", 1) for n in counts)
    remaining_count = bounded_integer(sum(counts), "original seed count", 1)
    remaining_score = original_score
    scores, steps = [], []
    for index, head_count in enumerate(counts[:-1]):
        tail_count = remaining_count - head_count
        ratio = float32(float32(tail_count) / float32(remaining_count))
        product = float32(float32(remaining_score) * ratio)
        # Equivalent to ordinary binary32 evaluation of v2.31's expression;
        # no claim for a compiler using excess precision/fast-math evaluation.
        tail_score = int(product + 0.499)
        head_score = remaining_score - tail_score
        if not 0 <= tail_score <= remaining_score or tail_score > INT32_MAX:
            raise ExperimentError("float rounding leaves supported nonnegative int32 score partition")
        steps.append({"fragment_index": index, "parent_seed_count": remaining_count,
                      "parent_score": remaining_score, "head_seed_count": head_count,
                      "tail_seed_count": tail_count, "tail_ratio_binary32": ratio,
                      "tail_product_binary32": product, "head_score": head_score, "tail_score": tail_score})
        scores.append(head_score)
        remaining_count, remaining_score = tail_count, tail_score
    scores.append(remaining_score)
    if remaining_count != counts[-1] or sum(scores) != original_score:
        raise ExperimentError("sequential score partition failed conservation")
    return {"fragment_anchor_counts": list(counts), "reconstructed_chain_scores": scores,
            "split_steps": steps, "rounding_model": "binary32 division/product; double +0.499; truncate toward zero",
            "split_model": "head_then_repeated_tail", "execution_validated": False}


def validate_row(row):
    required = {"query", "query_length", "query_start", "query_end", "strand",
                "target", "target_length", "target_start", "target_end"}
    if type(row) is not dict or not required <= row.keys():
        raise ExperimentError("split row is missing required identity/coordinate fields")
    for key in ("query_length", "target_length"):
        bounded_integer(row[key], key, 1)
    for key in ("query_start", "query_end", "target_start", "target_end"):
        bounded_integer(row[key], key)
    for key in ("query", "target"):
        name = row[key]
        if not isinstance(name, str) or not name or any(not 33 <= ord(c) <= 126 for c in name):
            raise ExperimentError("sequence identity must be a printable ASCII token")
    if row["strand"] not in ("+", "-"):
        raise ExperimentError("unknown strand in sequential witness")


def reconstruct_sequential_splits(trace_path, coarse, fragments, *, trace_budget=None,
                                  max_fragments=MAX_FRAGMENTS):
    """Conditional score witness from original anchors and recovered geometry only.

    Fragment s1/cm/AS/MAPQ are deliberately not read. Unknown, missing, shared,
    nonmonotonic or noncontiguous anchor ownership fails closed. Require QT;
    caller must STILL establish successful trace producer exit and input/tool
    identity outside this function. Output is not authoritative PAF evidence.
    """
    if not isinstance(fragments, (list, tuple)) or not 2 <= len(fragments) <= MAX_FRAGMENTS:
        raise ExperimentError("sequential witness requires 2..64 fragment rows")
    validate_row(coarse)
    bounded_integer(coarse["minimizers"], "original seed count", 1)
    bounded_integer(coarse["chain_score"], "original chain score")
    for row in fragments:
        validate_row(row)
    ordered = st.ordered_fragments(coarse, fragments, max_fragments=max_fragments)
    evidence = st.collect_split_counts(trace_path, coarse, ordered, trace_budget,
                                       max_fragments=max_fragments, require_query_end=True)
    counts = evidence["fragment_anchor_counts"]
    if sum(counts) != coarse["minimizers"]:
        raise ExperimentError("original seed counts do not cover sequential fragments")
    accounting = sequential_scores(coarse["chain_score"], counts)
    return {**accounting, "diagnostic_witness_only": True, "production_ready": False,
            "original_chain_score": coarse["chain_score"], "original_anchor_count": sum(counts),
            "trace_sha256": evidence["trace_sha256"], "trace_resources": evidence["resources"],
            "fragments_in_chain_order": [
                {key: row[key] for key in ("query", "query_length", "query_start", "query_end", "strand",
                                           "target", "target_length", "target_start", "target_end")}
                for row in ordered],
            "actual_aligner_split_events_observed": False,
            "producer_exit_validated_here": False, "oracle_scores_compared": False,
            "candidate_selection_reconstructed": False, "mapq_reconstructed": False,
            "customer_validated": False,
            "assumption": "one retained chain, sequential tail splits, complete unique contiguous seed ownership; no joins/inversion rescue"}


def compare_sequential_oracle(trace_path, coarse, diagnostic_rows, *, trace_budget=None):
    """Independent check AFTER constructing counts/scores without reported cm/s1.

    Intended for short controlled fixtures where original whole-query DP runs.
    An equality here does not establish the complete candidate universe, ranking,
    MAPQ, AS or a general proof that a customer chromosome follows this model.
    """
    witness = reconstruct_sequential_splits(trace_path, coarse, diagnostic_rows, trace_budget=trace_budget)
    ordered = st.ordered_fragments(coarse, diagnostic_rows, max_fragments=MAX_FRAGMENTS)
    reported_counts = [bounded_integer(row["minimizers"], "reported fragment seed count", 1) for row in ordered]
    reported_scores = [bounded_integer(row["chain_score"], "reported fragment chain score") for row in ordered]
    if reported_counts != witness["fragment_anchor_counts"]:
        raise ExperimentError("original seed counts disagree with sequential DP provenance")
    if reported_scores != witness["reconstructed_chain_scores"]:
        raise ExperimentError("sequential seed-derived scores disagree with diagnostic DP scores")
    return {**witness, "oracle_scores_compared": True,
            "reported_dp_chain_scores": reported_scores, "reported_dp_seed_counts": reported_counts}
