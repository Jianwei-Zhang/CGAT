"""GRT Step2 candidate generation, structural fallback and Q2 publication."""

from __future__ import annotations

from .repair_common import *
from .repair_mummer import (
    collect_mummer,
    grt_mummer_parameters,
)
from .repair_runtime import (
    execution_context,
    publish_repair_metadata,
)
from .repair_structural import (
    apply_corrections,
    build_correction_candidates,
)


def patch_sequence(candidate: dict[str, object], donor_records: dict[str, str]) -> str:
    sequence = donor_records[str(candidate["ref_record"])][
        int(candidate["patch_start"]) - 1 : int(candidate["patch_end"])
    ]
    return sequence if candidate["patch_orientation"] == "+" else reverse_complement(sequence)


def build_validation_queries(
    candidates: list[dict[str, object]],
    donor_records: dict[str, str],
) -> tuple[list[tuple[str, str]], dict[str, tuple[dict[str, object], str]]]:
    records: list[tuple[str, str]] = []
    query_map: dict[str, tuple[dict[str, object], str]] = {}
    for candidate in candidates:
        if candidate["reason"]:
            continue
        sequence = patch_sequence(candidate, donor_records)
        flank_length = PATCH_FLANK
        if len(sequence) > 1_000_000:
            flank_length = min(int(len(sequence) * 0.05), 200_000)
        flank_length = max(flank_length, 5_000)
        if len(sequence) <= 2 * flank_length:
            flank_length = len(sequence) // 4
        if flank_length < 100:
            candidate["outcome"] = "rejected"
            candidate["reason"] = "patch_too_short_for_validation"
            continue
        candidate["patch_sequence"] = sequence
        candidate["validation_flank_length"] = flank_length
        for side, flank in (("L", sequence[:flank_length]), ("R", sequence[-flank_length:])):
            name = f"validate__{candidate['candidate_id']}__{side}"
            records.append((name, flank))
            query_map[name] = (candidate, side)
    return records, query_map


def parse_validation_paf(
    path: Path,
    query_map: dict[str, tuple[dict[str, object], str]],
    chromosome: str,
    chromosome_length: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n")
            if not line:
                continue
            fields = line.split("\t")
            if len(fields) < 12 or not any(value.startswith("cg:Z:") for value in fields[12:]):
                fail(f"invalid candidate-validation PAF at {path}:{line_number}")
            query, strand, target = fields[0], fields[4], fields[5]
            if query not in query_map or target != chromosome or strand not in {"+", "-"}:
                fail(f"candidate-validation PAF has unknown identity at {path}:{line_number}")
            try:
                qlen, qstart, qend = map(int, fields[1:4])
                tlen, tstart, tend = map(int, fields[6:9])
                matches, block_length, mapq = map(int, fields[9:12])
            except ValueError:
                fail(f"candidate-validation PAF has non-integer fields at {path}:{line_number}")
            if not (
                0 <= qstart < qend <= qlen
                and 0 <= tstart < tend <= tlen == chromosome_length
                and 0 <= matches <= block_length
                and block_length > 0
            ):
                fail(f"candidate-validation PAF has invalid coordinates at {path}:{line_number}")
            candidate, side = query_map[query]
            rows.append(
                {
                    "line_number": line_number,
                    "raw": line,
                    "query": query,
                    "candidate_id": candidate["candidate_id"],
                    "side": side,
                    "qlen": qlen,
                    "qstart": qstart,
                    "qend": qend,
                    "strand": strand,
                    "target": target,
                    "tstart": tstart,
                    "tend": tend,
                    "matches": matches,
                    "block_length": block_length,
                    "mapq": mapq,
                    "identity": matches / block_length,
                }
            )
    return rows


def cached_validation_alignment(
    server_dir: Path,
    chromosome: str,
    q_source_sha256: str,
    q_sequence: str,
    query_records: list[tuple[str, str]],
    query_map: dict[str, tuple[dict[str, object], str]],
    donor_set: dict[str, str],
    minimap: dict[str, str],
    threads: int,
) -> tuple[Path, bool, str]:
    query_payload = fasta_bytes(query_records)
    target_payload = fasta_bytes([(chromosome, q_sequence)])
    parameters = {
        "preset": MINIMAP_PRESET,
        "cigar": True,
        "round_bandwidth": 100,
        "secondary": 5,
        "threads": threads,
        "min_score": PATCH_MIN_SCORE,
        "min_match": PATCH_MIN_MATCH,
        "min_mapq": PATCH_MIN_MAPQ,
        "search_range": PATCH_SEARCH_RANGE,
    }
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "engine_sha256": ENGINE_SHA256,
        "stage": "step2_candidate_validation",
        "chr": chromosome,
        "q_source_sha256": q_source_sha256,
        "q_chromosome_sha256": sha256_bytes(q_sequence.encode("ascii")),
        "query_sha256": sha256_bytes(query_payload),
        "target_sha256": sha256_bytes(target_payload),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "donor_fragment_index_sha256": sha256_file(
            server_dir / "metadata/grt_donor_fragments.tsv"
        ),
        "tool": command_identity(minimap),
        "parameters": parameters,
    }
    fingerprint = json_hash(fingerprint_payload)
    chromosome_key = stable_id("chr", chromosome, 16)
    cache_parent = server_dir / f"grt/cache/step23/step2/validation/{chromosome_key}"
    cache_dir = cache_parent / fingerprint
    checkpoint_path = cache_dir / "cache.json"
    output_names = ["queries.fa", "target.fa", "result.paf", "command.txt", "stdout.log", "stderr.log"]
    if checkpoint_path.is_file():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            hashes = checkpoint.get("output_hashes", {})
            if (
                checkpoint.get("status") == "success"
                and checkpoint.get("input_fingerprint") == fingerprint
                and set(hashes) == set(output_names)
                and all(
                    (cache_dir / name).is_file() and sha256_file(cache_dir / name) == expected
                    for name, expected in hashes.items()
                )
            ):
                parse_validation_paf(cache_dir / "result.paf", query_map, chromosome, len(q_sequence))
                return cache_dir, True, chromosome_key
        except (OSError, TypeError, ValueError, json.JSONDecodeError, SystemExit):
            pass
    cache_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{fingerprint}.", dir=cache_parent))
    try:
        (temporary / "queries.fa").write_bytes(query_payload)
        (temporary / "target.fa").write_bytes(target_payload)
        paf_path = temporary / "result.paf"
        if query_records:
            command = [
                minimap["resolved"],
                "-x",
                MINIMAP_PRESET,
                "-t",
                str(threads),
                "-c",
                "-r",
                "100",
                "-N",
                "5",
                "-o",
                str(paf_path),
                str(temporary / "target.fa"),
                str(temporary / "queries.fa"),
            ]
            run_logged(
                command,
                temporary,
                temporary / "command.txt",
                temporary / "stdout.log",
                temporary / "stderr.log",
            )
            if not paf_path.is_file():
                fail(f"minimap2 did not create candidate-validation PAF for {chromosome}")
        else:
            paf_path.write_bytes(b"")
            (temporary / "command.txt").write_text("skipped: no MUMmer patch candidate\n", encoding="utf-8")
            (temporary / "stdout.log").write_text("", encoding="utf-8")
            (temporary / "stderr.log").write_text("", encoding="utf-8")
        parse_validation_paf(paf_path, query_map, chromosome, len(q_sequence))
        checkpoint = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "engine_sha256": ENGINE_SHA256,
            "stage": "step2_candidate_validation",
            "chr": chromosome,
            "status": "success",
            "input_fingerprint": fingerprint,
            "fingerprint_payload": fingerprint_payload,
            "output_hashes": {name: sha256_file(temporary / name) for name in output_names},
        }
        (temporary / "cache.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        os.replace(temporary, cache_dir)
        return cache_dir, False, chromosome_key
    except BaseException:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"step2-validation-{chromosome_key}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


def best_validation_alignment(
    rows: list[dict[str, object]],
    candidate: dict[str, object],
    side: str,
) -> dict[str, object] | None:
    gap_start0 = int(candidate["target_start"]) - 1
    eligible = [
        row
        for row in rows
        if row["candidate_id"] == candidate["candidate_id"]
        and row["side"] == side
        and int(row["mapq"]) >= PATCH_MIN_MAPQ
        and float(row["identity"]) >= PATCH_MIN_SCORE
        and int(row["qend"]) - int(row["qstart"]) >= PATCH_MIN_MATCH
        and abs(int(row["tstart"]) - gap_start0) <= PATCH_SEARCH_RANGE
    ]
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda row: (
            -float(row["identity"]),
            -(int(row["qend"]) - int(row["qstart"])),
            -int(row["mapq"]),
            int(row["line_number"]),
        ),
    )[0]


def validate_step2_candidates(
    candidates: list[dict[str, object]],
    validation_rows: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    rejections: list[dict[str, object]],
) -> None:
    for candidate in candidates:
        if candidate["reason"]:
            continue
        left = best_validation_alignment(validation_rows, candidate, "L")
        right = best_validation_alignment(validation_rows, candidate, "R")
        reason = ""
        if left is None or right is None:
            reason = "candidate_validation_missing_flank"
        elif left["strand"] != "+" or right["strand"] != "+":
            reason = "candidate_validation_orientation_conflict"
        elif int(left["tend"]) > int(right["tstart"]):
            reason = "candidate_validation_crossed_cut_points"
        elif int(left["tend"]) > int(candidate["target_start"]) - 1:
            reason = "candidate_validation_left_cut_does_not_cover_gap"
        elif int(right["tstart"]) < int(candidate["target_end"]):
            reason = "candidate_validation_right_cut_does_not_cover_gap"
        if reason:
            candidate["outcome"] = "rejected"
            candidate["reason"] = reason
            rejections.append(
                {
                    "stage": "step2",
                    "chr": candidate["chr"],
                    "object_id": candidate["object_id"],
                    "candidate_id": candidate["candidate_id"],
                    "left_line": "" if left is None else left["line_number"],
                    "right_line": "" if right is None else right["line_number"],
                    "reason": reason,
                }
            )
            continue
        sequence = str(candidate["patch_sequence"])
        flank_length = int(candidate["validation_flank_length"])
        insert_start0 = int(left["qend"])
        insert_end0 = len(sequence) - flank_length + int(right["qstart"])
        if insert_start0 >= insert_end0:
            insert_start0 = flank_length
            insert_end0 = len(sequence) - flank_length
        if insert_start0 >= insert_end0 or insert_end0 - insert_start0 > REFILL_MAX_LENGTH:
            candidate["outcome"] = "rejected"
            candidate["reason"] = "candidate_validation_invalid_insert_interval"
            continue
        if candidate["patch_orientation"] == "+":
            local_start = int(candidate["patch_start"]) + insert_start0
            local_end = int(candidate["patch_start"]) + insert_end0 - 1
        else:
            local_start = int(candidate["patch_end"]) - insert_end0 + 1
            local_end = int(candidate["patch_end"]) - insert_start0
        member = members_by_record[str(candidate["ref_record"])]
        source_start, source_end = member_source_interval(member, local_start, local_end)
        fill_sequence = sequence[insert_start0:insert_end0]
        if re.search(r"N{100,}", fill_sequence):
            candidate["outcome"] = "rejected"
            candidate["reason"] = "validated_patch_crosses_unresolved_gap"
            continue
        left_cut = int(left["tend"])
        right_cut = int(right["tstart"])
        candidate.update(
            {
                "source_start": source_start,
                "source_end": source_end,
                "trim_left": int(candidate["target_start"]) - 1 - left_cut,
                "trim_right": right_cut - int(candidate["target_end"]),
                "input_start": left_cut + 1,
                "input_end": right_cut,
                "fill_length": len(fill_sequence),
                "fill_sequence": fill_sequence,
                "identity": (
                    float(candidate["identity"])
                    + float(left["identity"])
                    + float(right["identity"])
                )
                / 3,
                "aligned_length": int(candidate["aligned_length"])
                + int(left["block_length"])
                + int(right["block_length"]),
                "mapq": min(int(left["mapq"]), int(right["mapq"])),
                "validation_left_line": left["line_number"],
                "validation_right_line": right["line_number"],
                "validation_passed": True,
                "outcome": "candidate",
                "reason": "",
            }
        )


def arbitrate_structural_candidates(
    candidates: list[dict[str, object]],
    gaps: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Choose deterministic fixer edits in chromosome/gap order.

    Upstream merges overlapping repair regions.  Server mode represents that
    safely as one accepted edit whose normalized gap carries every absorbed
    origin object.  No donor sequence is consumed by these boundary edits.
    """
    by_object: dict[str, list[dict[str, object]]] = defaultdict(list)
    for candidate in candidates:
        by_object[str(candidate["object_id"])].append(candidate)
    accepted_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    ordered_gaps = sorted(
        gaps,
        key=lambda row: (str(row["chr"]), int(row["start0"]), str(row["object_id"])),
    )
    for gap in ordered_gaps:
        chromosome = str(gap["chr"])
        object_id = str(gap["object_id"])
        gap_start = int(gap["start0"]) + 1
        gap_end = int(gap["end0"])
        covering = next(
            (
                row
                for row in accepted_by_chr[chromosome]
                if int(row["input_start"]) <= gap_start
                and int(row["input_end"]) >= gap_end
            ),
            None,
        )
        rows = by_object.get(object_id, [])
        if covering is not None:
            covered = covering.setdefault(
                "covered_object_ids", [str(covering["object_id"])]
            )
            if object_id not in covered:
                covered.append(object_id)
            for row in rows:
                if row.get("outcome") == "candidate":
                    row["outcome"] = "conflicted"
                    row["reason"] = (
                        "absorbed_by_structural_candidate:"
                        f"{covering['candidate_id']}"
                    )
            continue
        eligible = sorted(
            (row for row in rows if row.get("outcome") == "candidate"),
            key=lambda row: (
                -reference_overlap_score(row),
                -float(row["identity"]),
                -int(row["aligned_length"]),
                int(row["input_start"]),
                int(row["input_end"]),
                str(row["candidate_id"]),
            ),
        )
        selected = next(
            (
                row
                for row in eligible
                if not any(
                    intervals_overlap(
                        int(row["input_start"]),
                        int(row["input_end"]),
                        int(occupied["input_start"]),
                        int(occupied["input_end"]),
                    )
                    for occupied in accepted_by_chr[chromosome]
                )
            ),
            None,
        )
        for row in eligible:
            if row is selected:
                row["outcome"] = "accepted"
                row["reason"] = "accepted_by_structural_gap_order"
                row["source_consumable"] = False
                row["covered_object_ids"] = [object_id]
                accepted_by_chr[chromosome].append(row)
            else:
                row["outcome"] = "conflicted" if selected is None else "rejected"
                row["reason"] = (
                    "target_interval_overlaps_prior_structural_edit"
                    if selected is None
                    else "lower_ranked_structural_candidate_for_object"
                )
    return sorted(
        candidates,
        key=lambda row: (
            str(row["chr"]),
            int(row["target_start"]),
            str(row["candidate_id"]),
        ),
    )



def build_step2_candidates(
    gaps: list[dict[str, object]],
    alignments: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    donor_records: dict[str, str],
    *, use_index: bool = False,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for alignment in alignments:
        grouped[(str(alignment["chr"]), str(alignment["ref_record"]))].append(alignment)
    member_indexes = {key: Step2MemberIndex(rows) for key, rows in grouped.items()} if use_index else {}
    grouped_by_chr = defaultdict(list)
    if use_index:
        for key, rows in sorted(grouped.items()):
            grouped_by_chr[key[0]].append((key, rows))
    candidates: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    for gap in gaps:
        chromosome = str(gap["chr"])
        gap_position = int(gap["start0"]) + 1
        for (candidate_chr, ref_record), member_alignments in (grouped_by_chr[chromosome] if use_index else sorted(grouped.items())):
            if candidate_chr != chromosome:
                continue
            if use_index:
                left_rows, right_rows = member_indexes[(candidate_chr, ref_record)].anchors(gap_position)
            else:
                left_rows = sorted(
                    (row for row in member_alignments if int(row["query_max"]) <= gap_position + 10),
                    key=lambda row: (-int(row["query_max"]), -float(row["identity"])),
                )[:2]
                right_rows = sorted(
                    (row for row in member_alignments if int(row["query_min"]) >= gap_position - 10),
                    key=lambda row: (int(row["query_min"]), -float(row["identity"])),
                )[:2]
            for left in left_rows:
                for right in right_rows:
                    base = {
                        "stage": "step2",
                        "chr": chromosome,
                        "object_id": gap["object_id"],
                        "left_line": left["line_number"],
                        "right_line": right["line_number"],
                    }
                    reason = ""
                    if left["orientation"] != right["orientation"]:
                        reason = "mummer_anchor_orientation_conflict"
                    elif int(right["query_min"]) - int(left["query_max"]) > PATCH_MAX_ANCHOR_DISTANCE:
                        reason = "mummer_anchor_distance_gt_1000000"
                    orientation = str(left["orientation"])
                    if orientation == "+":
                        donor_left = int(left["ref_max"])
                        donor_right = int(right["ref_min"])
                    else:
                        donor_left = int(right["ref_max"])
                        donor_right = int(left["ref_min"])
                    if not reason and donor_left >= donor_right:
                        reason = "mummer_anchor_order_or_overlap_invalid"
                    patch_start = max(1, donor_left - PATCH_FLANK + 1)
                    patch_end = min(len(donor_records[ref_record]), donor_right + PATCH_FLANK - 1)
                    if patch_start >= patch_end:
                        if not reason:
                            reason = "empty_patch_interval"
                        # Rejected pairs remain in the evidence registry. Give
                        # them the increasing donor-local span covered by both
                        # raw anchors instead of serializing the non-executable
                        # reversed patch interval into the public contract.
                        patch_start = min(int(left["ref_min"]), int(right["ref_min"]))
                        patch_end = max(int(left["ref_max"]), int(right["ref_max"]))
                    member = members_by_record[ref_record]
                    source_start, source_end = member_source_interval(member, patch_start, patch_end)
                    payload = {
                        "stage": "step2",
                        "object_id": gap["object_id"],
                        "member_id": member["member_id"],
                        "patch_start": patch_start,
                        "patch_end": patch_end,
                        "orientation": orientation,
                        "left_line": left["line_number"],
                        "right_line": right["line_number"],
                    }
                    candidate_id = stable_id("step2-candidate", payload, 24)
                    candidate = {
                        "candidate_id": candidate_id,
                        **base,
                        "action": "patch",
                        "member_id": member["member_id"],
                        "ref_record": ref_record,
                        "source_dataset": member["dataset_name"],
                        "source_contig": member["contig_name"],
                        "source_start": source_start,
                        "source_end": source_end,
                        "orientation": orientation,
                        "target_start": int(gap["start0"]) + 1,
                        "target_end": int(gap["end0"]),
                        "input_start": int(gap["start0"]) + 1,
                        "input_end": int(gap["end0"]),
                        "trim_left": 0,
                        "trim_right": 0,
                        "fill_length": patch_end - patch_start + 1,
                        "identity": (float(left["identity"]) + float(right["identity"])) / 2,
                        "aligned_length": int(left["query_aligned"]) + int(right["query_aligned"]),
                        "mapq": 0,
                        "patch_start": patch_start,
                        "patch_end": patch_end,
                        "patch_orientation": orientation,
                        "direct_patch_anchor_pair": True,
                        "left_alignment": left,
                        "right_alignment": right,
                        "validation_passed": False,
                        "outcome": "rejected" if reason else "candidate",
                        "reason": reason,
                        "event_id": "",
                        "final_path_segment_id": "",
                    }
                    candidates.append(candidate)
                    if reason:
                        rejections.append({**base, "candidate_id": candidate_id, "reason": reason})
    return candidates, rejections



def step2_strategy(gap_count: int, patch_candidate_count: int, accepted_patch_count: int) -> str:
    """Return the GRT controller branch for one chromosome."""
    if gap_count == 0:
        return "no_gaps"
    if patch_candidate_count == 0:
        return "no_patch_fixer"
    if accepted_patch_count == 0:
        return "full_fixer_reuse_patches"
    return "partial_success_no_fixer"



def step2_strategy_applied(strategy: str) -> str:
    """Map the controller branch to the contract's execution vocabulary."""
    if strategy in {"no_gaps", "partial_success_no_fixer"}:
        return "patcher_result"
    # The upstream PatchRepair fallback runs the whole-chromosome structural
    # fixer.  Its accepted candidates are boundary edits rather than source
    # patches, so this is accurately represented as fixer_only even when the
    # fixer applies one or more edits.
    return "fixer_only"



def run_step2(
    server_dir: Path,
    run_id: str,
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    input_q_rows: list[dict[str, object]],
    donor_set: dict[str, str],
    donor_members: list[dict[str, str]],
    assignments: dict[tuple[str, str], str],
    sources: dict[tuple[str, str], str],
    consumed: list[dict[str, object]],
    tools: dict[str, dict[str, str]],
    minimap: dict[str, str],
    threads: int,
    repair_mode: str = DEFAULT_REPAIR_MODE,
    mummer_scope: str = DEFAULT_MUMMER_SCOPE,
    execution_profile: str = DEFAULT_EXECUTION_PROFILE,
) -> tuple[dict[str, object], bool]:
    stage = "step2"
    if repair_mode not in REPAIR_MODES:
        fail(f"unsupported Step2 repair mode: {repair_mode}")
    if mummer_scope not in MUMMER_SCOPES:
        fail(f"unsupported Step2 MUMmer scope: {mummer_scope}")
    q_input_sha256 = sha256_file(server_dir / "grt/q/q1.fa")
    if execution_profile not in EXECUTION_PROFILES:
        fail(f"unsupported execution profile: {execution_profile}")
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "engine_sha256": ENGINE_SHA256,
        "stage": stage,
        "q_version": "q1",
        "q_source_sha256": q_input_sha256,
        "q_segments_sha256": json_hash(input_q_rows),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "donor_fragment_index_sha256": sha256_file(
            server_dir / "metadata/grt_donor_fragments.tsv"
        ),
        "tools": {name: command_identity(value) for name, value in {**tools, "minimap2": minimap}.items()},
        "mummer_parameters": grt_mummer_parameters(threads),
        "mummer_scope": mummer_scope,
        "execution_profile": execution_profile,
        "execution_helper_sha256": EXECUTION_HELPER_SHA256 if execution_profile == "optimized" else None,
        "validation_parameters": {
            "preset": MINIMAP_PRESET,
            "flank": PATCH_FLANK,
            "min_score": PATCH_MIN_SCORE,
            "min_match": PATCH_MIN_MATCH,
            "min_mapq": PATCH_MIN_MAPQ,
            "search_range": PATCH_SEARCH_RANGE,
        },
        "fallback_parameters": {
            "repair_mode": repair_mode,
            "controller": "server_native_correctrefill_source_retry",
            "strategies": [
                "no_patch_fixer",
                "full_fixer_reuse_patches",
                "partial_success_no_fixer",
            ],
        },
        "consumed_intervals_sha256": json_hash(consumed),
    }
    fingerprint = json_hash(fingerprint_payload)
    cached = checkpoint_result(server_dir, stage, fingerprint)
    if cached is not None:
        print(f"GRT step2 cache hit: {fingerprint}")
        return cached, True
    invalidate_step23_from(server_dir, stage)
    artifact_relpath = "grt/evidence/step2"
    artifact_dir = server_dir / artifact_relpath
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".step2.", dir=artifact_dir.parent))
    q_output_temporary = server_dir / f"grt/q/.q2.fa.tmp.{os.getpid()}"
    try:
        alignments, mummer_identities, _tasks = collect_mummer(
            server_dir,
            temporary,
            artifact_relpath,
            stage,
            q_input_sha256,
            chromosome_order,
            input_records,
            input_q_rows,
            donor_set,
            donor_members,
            tools,
            threads,
            mummer_scope=mummer_scope,
            execution_profile=execution_profile,
        )
        members_by_record = {row["fasta_record_name"]: row for row in donor_members}
        donor_records = dict(read_fasta_allow_empty(server_dir / donor_set["fasta_relpath"]))
        fragment_rows = [
            row
            for row in read_tsv(
                server_dir / "metadata/grt_donor_fragments.tsv",
                DONOR_FRAGMENT_FIELDS,
            )
            if row["donor_set_id"] == donor_set["donor_set_id"]
        ]
        gaps = [gap for chromosome in chromosome_order for gap in gap_objects(chromosome, "q1", input_records[chromosome])]
        candidates, rejections = build_step2_candidates(gaps, alignments, members_by_record, donor_records,
                                                        use_index=execution_profile == "optimized")
        patch_candidate_counts = {
            chromosome: sum(1 for row in candidates if str(row["chr"]) == chromosome)
            for chromosome in chromosome_order
        }
        validation_identities: dict[str, dict[str, str]] = {}
        validation_rows: list[dict[str, object]] = []
        for chromosome in chromosome_order:
            chromosome_candidates = [row for row in candidates if row["chr"] == chromosome]
            query_records, query_map = build_validation_queries(chromosome_candidates, donor_records)
            cache_dir, cache_hit, chromosome_key = cached_validation_alignment(
                server_dir,
                chromosome,
                q_input_sha256,
                input_records[chromosome],
                query_records,
                query_map,
                donor_set,
                minimap,
                threads,
            )
            print(f"GRT step2 validation {chromosome}: {'cache hit' if cache_hit else 'computed'}")
            destination = temporary / "validation" / "by_chr" / chromosome_key
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(cache_dir, destination)
            validation_rows.extend(
                parse_validation_paf(
                    destination / "result.paf",
                    query_map,
                    chromosome,
                    len(input_records[chromosome]),
                )
            )
            validation_identities[chromosome] = {
                "query_relpath": f"{artifact_relpath}/validation/by_chr/{chromosome_key}/queries.fa",
                "query_sha256": sha256_file(destination / "queries.fa"),
                "target_relpath": f"{artifact_relpath}/validation/by_chr/{chromosome_key}/target.fa",
                "target_sha256": sha256_file(destination / "target.fa"),
                "raw_relpath": f"{artifact_relpath}/validation/by_chr/{chromosome_key}/result.paf",
                "raw_sha256": sha256_file(destination / "result.paf"),
            }
        validate_step2_candidates(candidates, validation_rows, members_by_record, rejections)
        reject_candidates_spanning_other_gaps(candidates, gaps, rejections)
        annotate_candidate_fragments(candidates, donor_members, fragment_rows)
        patch_candidates = arbitrate(candidates, consumed)
        validated_patch_counts = {
            chromosome: sum(
                1 for row in patch_candidates
                if str(row["chr"]) == chromosome and row.get("validation_passed")
            )
            for chromosome in chromosome_order
        }
        strategy_rows: list[dict[str, object]] = []
        fallback_candidates: list[dict[str, object]] = []
        fallback_chromosomes: set[str] = set()
        for chromosome in chromosome_order:
            chromosome_gaps = sorted(
                (gap for gap in gaps if str(gap["chr"]) == chromosome),
                key=lambda gap: int(gap["start0"]),
            )
            gap_count = len(chromosome_gaps)
            patch_count = patch_candidate_counts[chromosome]
            first_object_id = (
                str(chromosome_gaps[0]["object_id"]) if chromosome_gaps else ""
            )
            accepted_first_count = sum(
                1
                for row in patch_candidates
                if str(row["chr"]) == chromosome
                and str(row["object_id"]) == first_object_id
                and row.get("outcome") == "accepted"
            )
            strategy = step2_strategy(
                gap_count, patch_count, accepted_first_count
            )
            if strategy in {"no_patch_fixer", "full_fixer_reuse_patches"}:
                fallback_chromosomes.add(chromosome)
                for row in patch_candidates:
                    if (
                        str(row["chr"]) == chromosome
                        and row.get("outcome") == "accepted"
                    ):
                        row["outcome"] = "rejected"
                        row["reason"] = "chromosome_fallback_to_structural_fixer"
                chromosome_alignments = [row for row in alignments if str(row["chr"]) == chromosome]
                fallback_candidates.extend(
                    build_step2_structural_fallback_candidates(
                        chromosome_gaps,
                        chromosome_alignments,
                        members_by_record,
                        repair_mode=repair_mode,
                        use_index=execution_profile == "optimized",
                    )
                )
            accepted_count = sum(
                1
                for row in patch_candidates
                if str(row["chr"]) == chromosome
                and row.get("outcome") == "accepted"
            )
            strategy_rows.append(
                {
                    "chr": chromosome,
                    "strategy": strategy,
                    "strategy_applied": "pending",
                    "gap_count": gap_count,
                    "patch_candidate_count": patch_count,
                    "validated_patch_count": validated_patch_counts[chromosome],
                    "accepted_patch_count": accepted_count,
                    "fallback_candidate_count": 0,
                    "accepted_fallback_count": 0,
                    "reason": "",
                }
            )
        candidates = [*patch_candidates, *fallback_candidates]
        fallback_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in fallback_candidates:
            fallback_by_chr[str(row["chr"])].append(row)
        for strategy_row in strategy_rows:
            rows = fallback_by_chr.get(strategy_row["chr"], [])
            strategy_row["fallback_candidate_count"] = len(rows)
            strategy_row["accepted_fallback_count"] = sum(
                1 for row in rows if row.get("outcome") == "accepted"
            )
            strategy_row["strategy_applied"] = step2_strategy_applied(
                str(strategy_row["strategy"])
            )
            if strategy_row["strategy"] == "no_gaps":
                strategy_row["reason"] = "chromosome_has_no_gap_objects"
            elif strategy_row["strategy"] == "partial_success_no_fixer":
                strategy_row["reason"] = "at_least_one_validated_patch_accepted"
            elif strategy_row["accepted_fallback_count"]:
                strategy_row["reason"] = "patchrepair_structural_fixer_accepted"
            else:
                strategy_row["reason"] = "no_safe_structural_fixer_edit"
        evidence_rows: list[dict[str, object]] = []
        for candidate in candidates:
            mummer_evidence_id = stable_id("ev-step2-mummer", candidate["candidate_id"], 22)
            validation_evidence_id = stable_id("ev-step2-validation", candidate["candidate_id"], 22)
            candidate["evidence_id"] = validation_evidence_id
            candidate["evidence_ids"] = [mummer_evidence_id, validation_evidence_id]
            mummer_identity = mummer_identities[str(candidate["chr"])]
            evidence_rows.append(
                evidence_row(
                    evidence_id=mummer_evidence_id,
                    stage="step2",
                    evidence_type="mummer_gap_anchor_pair",
                    status=str(candidate["outcome"]),
                    q_version="q1",
                    q_source_sha256=q_input_sha256,
                    query_relpath=mummer_identity["query_relpath"],
                    query_sha256=mummer_identity["query_sha256"],
                    donor_set_id=donor_set["donor_set_id"],
                    target_relpath=donor_set["fasta_relpath"],
                    target_sha256=donor_set["fasta_sha256"],
                    candidate=candidate,
                    tool="nucmer/delta-filter/show-coords",
                    tool_version=" | ".join(tools[name]["version"] for name in ("nucmer", "delta-filter", "show-coords")),
                    preset="nucmer-c1000-l100;delta-filter-l10000;show-coords-r-l",
                    parameters=grt_mummer_parameters(threads),
                    raw_relpath=mummer_identity["coords_relpath"],
                    raw_sha256=mummer_identity["coords_sha256"],
                    coordinate_system="mummer_1_based_closed",
                )
            )
            validation_identity = validation_identities[str(candidate["chr"])]
            if candidate.get("fallback"):
                evidence_rows.append(
                    evidence_row(
                        evidence_id=validation_evidence_id,
                        stage="step2",
                        evidence_type=(
                            "patchrepair_structural_fixer"
                            if candidate.get("structural_fallback")
                            else "correctrefill_fallback"
                        ),
                        status=str(candidate["outcome"]),
                        q_version="q1",
                        q_source_sha256=q_input_sha256,
                        query_relpath=mummer_identity["query_relpath"],
                        query_sha256=mummer_identity["query_sha256"],
                        donor_set_id=donor_set["donor_set_id"],
                        target_relpath=donor_set["fasta_relpath"],
                        target_sha256=donor_set["fasta_sha256"],
                        candidate=candidate,
                        tool="grt_step3_structural_adapter",
                        tool_version=str(ENGINE_VERSION),
                        preset=(
                            "grt-type1-type6-structural-fixer"
                            if candidate.get("structural_fallback")
                            else "grt-type1-type6-source-retry"
                        ),
                        parameters={
                            "repair_mode": repair_mode,
                            "fallback_strategy": candidate.get("fallback_strategy", ""),
                            "parent_candidate_id": candidate.get("fallback_parent_candidate_id", ""),
                        },
                        raw_relpath=mummer_identity["coords_relpath"],
                        raw_sha256=mummer_identity["coords_sha256"],
                        coordinate_system="mummer_1_based_closed",
                    )
                )
            else:
                evidence_rows.append(
                    evidence_row(
                        evidence_id=validation_evidence_id,
                        stage="candidate_validation",
                        evidence_type="patch_flank_revalidation",
                        status=str(candidate["outcome"]),
                        q_version="q1",
                        q_source_sha256=q_input_sha256,
                        query_relpath=validation_identity["query_relpath"],
                        query_sha256=validation_identity["query_sha256"],
                        donor_set_id="",
                        target_relpath=validation_identity["target_relpath"],
                        target_sha256=validation_identity["target_sha256"],
                        candidate=candidate,
                        tool="minimap2",
                        tool_version=minimap["version"],
                        preset=MINIMAP_PRESET,
                        parameters=fingerprint_payload["validation_parameters"],
                        raw_relpath=validation_identity["raw_relpath"],
                        raw_sha256=validation_identity["raw_sha256"],
                        coordinate_system="paf_0_based_half_open",
                    )
                )
        direct_gaps = [
            gap for gap in gaps if str(gap["chr"]) not in fallback_chromosomes
        ]
        direct_candidates = [
            row
            for row in patch_candidates
            if str(row["chr"]) not in fallback_chromosomes
        ]
        (
            patch_paths,
            patch_records,
            patch_events,
            usage_rows,
            patch_attempts,
        ) = apply_round(
            run_id,
            stage,
            "q1",
            "q2",
            chromosome_order,
            input_paths,
            input_records,
            direct_gaps,
            direct_candidates,
            assignments,
            q_input_sha256,
            sources,
            action="patch",
        )
        fallback_gaps = [
            gap for gap in gaps if str(gap["chr"]) in fallback_chromosomes
        ]
        (
            output_paths,
            output_records,
            structural_prototypes,
            structural_gap_origins,
        ) = apply_corrections(
            chromosome_order,
            patch_paths,
            patch_records,
            fallback_gaps,
            fallback_candidates,
            sources,
        )
        write_fasta(
            q_output_temporary,
            [
                (chromosome, output_records[chromosome])
                for chromosome in chromosome_order
            ],
        )
        q_output_sha256 = sha256_file(q_output_temporary)
        for event in patch_events:
            event["q_after"]["sha256"] = q_output_sha256
        structural_events, structural_attempts = build_step2_structural_events(
            run_id,
            q_input_sha256,
            q_output_sha256,
            fallback_gaps,
            fallback_candidates,
            structural_prototypes,
            structural_gap_origins,
        )
        events = [*patch_events, *structural_events]
        attempts = [*patch_attempts, *structural_attempts]
        candidate_by_event = {
            str(candidate.get("event_id")): candidate
            for candidate in direct_candidates
            if candidate.get("event_id")
        }
        for event in events:
            candidate = candidate_by_event.get(str(event["event_id"]))
            if candidate is None:
                continue
            event["strategy"] = next(
                (
                    row["strategy"]
                    for row in strategy_rows
                    if row["chr"] == event["chr"]
                ),
                "partial_success_no_fixer",
            )
        for event in structural_events:
            event["strategy"] = next(
                row["strategy"]
                for row in strategy_rows
                if row["chr"] == event["chr"]
            )
        for row in usage_rows:
            row["donor_set_id"] = donor_set["donor_set_id"]
        q_rows = q_rows_for_paths("q2", chromosome_order, output_paths)
        if any(event["q_after"]["sha256"] != q_output_sha256 for event in events):
            fail("internal step2 q output hash disagreement")
        write_tsv(temporary / "candidates.tsv", CANDIDATE_FIELDS, candidate_table_rows(candidates))
        write_tsv(temporary / "rejections.tsv", REJECTION_FIELDS, rejections)
        write_tsv(temporary / "q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
        write_tsv(temporary / "evidence.tsv", EVIDENCE_FIELDS, evidence_rows)
        write_tsv(temporary / "usage.tsv", USAGE_FIELDS, usage_rows)
        write_tsv(temporary / "gap_attempts.tsv", ATTEMPT_FIELDS, attempts)
        write_tsv(temporary / "strategy.tsv", STRATEGY_FIELDS, strategy_rows)
        write_jsonl(temporary / "events.jsonl", events)
        accepted_intervals = [
            {
                "candidate_id": row["candidate_id"],
                "source_dataset": row["source_dataset"],
                "source_contig": row["source_contig"],
                "source_start": row["source_start"],
                "source_end": row["source_end"],
                "stage": stage,
            }
            for row in candidates
            if row["outcome"] == "accepted" and row.get("source_consumable", True)
        ]
        result: dict[str, object] = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "engine_sha256": ENGINE_SHA256,
            "stage": stage,
            "input_fingerprint": fingerprint,
            "q_input_version": "q1",
            "q_input_sha256": q_input_sha256,
            "q_output_version": "q2",
            "q_output_sha256": q_output_sha256,
            "donor_set_id": donor_set["donor_set_id"],
            "target_sha256": donor_set["fasta_sha256"],
            "q_rows": q_rows,
            "evidence_rows": evidence_rows,
            "usage_rows": usage_rows,
            "events": events,
            "attempts": attempts,
            "strategies": strategy_rows,
            "fallback_candidate_count": len(fallback_candidates),
            "accepted_intervals": accepted_intervals,
        }
        (temporary / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        commit_stage_directory(temporary, artifact_dir)
        os.replace(q_output_temporary, server_dir / "grt/q/q2.fa")
        output_relpaths = [
            path.relative_to(server_dir).as_posix() for path in artifact_dir.rglob("*") if path.is_file()
        ] + ["grt/q/q2.fa"]
        write_checkpoint(
            server_dir,
            stage,
            fingerprint,
            fingerprint_payload,
            f"{artifact_relpath}/result.json",
            output_relpaths,
        )
        print(
            f"GRT step2 complete: gaps={len(gaps)}, candidates={len(candidates)}, "
            f"accepted={len(accepted_intervals)}"
        )
        return result, False
    except BaseException:
        q_output_temporary.unlink(missing_ok=True)
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"step2-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise



def build_step2_fallback_candidates(
    gaps: list[dict[str, object]],
    alignments: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    sources: dict[tuple[str, str], str],
    repair_mode: str = DEFAULT_REPAIR_MODE,
) -> list[dict[str, object]]:
    """Turn CorrectRefill structural evidence into an auditable Step2 retry.

    The original GRT controller runs a fixer and then re-runs the patcher.  In
    Server mode only an executable Type1 replacement may reuse its explicit
    donor interval as that retry.  Type4/Type5 overlap evidence belongs to the
    Step3 structural-correction path, while conflicting Type2/Type3/Type6
    anchor pairs remain diagnostic-only evidence.
    """
    structural = build_correction_candidates(
        gaps, alignments, members_by_record, repair_mode=repair_mode
    )
    fallback: list[dict[str, object]] = []
    for correction in structural:
        if not correction.get("eligible", True):
            continue
        if (
            correction.get("validation_passed") is not True
            or correction.get("error_type") != "type1"
            or correction.get("action") != "replace"
        ):
            continue
        source_key = (str(correction["source_dataset"]), str(correction["source_contig"]))
        source_sequence = sources.get(source_key, "")
        source_start = int(correction["source_start"])
        source_end = int(correction["source_end"])
        if source_start < 1 or source_end < source_start or source_end > len(source_sequence):
            continue
        fill_sequence = source_sequence[source_start - 1 : source_end]
        if correction["orientation"] == "-":
            fill_sequence = reverse_complement(fill_sequence)
        if not fill_sequence or len(fill_sequence) > REFILL_MAX_LENGTH or re.search(r"N{100,}", fill_sequence):
            continue
        payload = {
            "stage": "step2",
            "fallback": True,
            "parent_candidate_id": correction["candidate_id"],
            "object_id": correction["object_id"],
            "source_dataset": correction["source_dataset"],
            "source_contig": correction["source_contig"],
            "source_start": source_start,
            "source_end": source_end,
            "input_start": correction["input_start"],
            "input_end": correction["input_end"],
            "error_type": correction.get("error_type", "unknown"),
            "error_subtype": correction.get("error_subtype", "unspecified"),
        }
        candidate = dict(correction)
        candidate.update(
            {
                "candidate_id": stable_id("step2-fallback", payload, 24),
                "stage": "step2",
                "action": "patch",
                "fill_sequence": fill_sequence,
                "fill_length": len(fill_sequence),
                "trim_left": int(correction["target_start"]) - int(correction["input_start"]),
                "trim_right": int(correction["input_end"]) - int(correction["target_end"]),
                "validation_passed": True,
                "outcome": "candidate",
                "reason": "fallback_source_interval_candidate",
                "fallback": True,
                "fallback_parent_candidate_id": correction["candidate_id"],
                "fallback_strategy": "correctrefill_source_retry",
                "repair_reason": correction.get("repair_reason", ""),
                "event_id": "",
                "final_path_segment_id": "",
            }
        )
        fallback.append(candidate)
    return fallback



def build_step2_structural_fallback_candidates(
    gaps: list[dict[str, object]],
    alignments: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    repair_mode: str = DEFAULT_REPAIR_MODE,
    *, use_index: bool = False,
) -> list[dict[str, object]]:
    """Build the upstream PatchRepair fixer branch without inserting D0 bases."""
    candidates = build_correction_candidates(
        gaps,
        alignments,
        members_by_record,
        repair_mode=repair_mode,
        structural_target="ordinary_donor",
        use_index=use_index,
    )
    for candidate in candidates:
        candidate.update(
            {
                "stage": "step2",
                "structural_fallback": True,
                "fallback": True,
                "fallback_parent_candidate_id": candidate["candidate_id"],
                "fallback_strategy": "patchrepair_structural_fixer",
                "source_consumable": False,
                "event_id": "",
                "final_path_segment_id": "",
            }
        )
    return arbitrate_structural_candidates(candidates, gaps)



def build_step2_structural_events(
    run_id: str,
    q1_sha256: str,
    q2_sha256: str,
    gaps: list[dict[str, object]],
    candidates: list[dict[str, object]],
    prototypes: list[dict[str, object]],
    gap_origins: dict[tuple[str, int, int], dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Serialize structural fixer edits and coalesced gap origins for Step2."""
    candidates_by_object: dict[str, list[dict[str, object]]] = defaultdict(list)
    accepted_by_object: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        candidates_by_object[str(candidate["object_id"])].append(candidate)
        if candidate.get("outcome") == "accepted":
            for object_id in candidate.get(
                "covered_object_ids", [str(candidate["object_id"])]
            ):
                accepted_by_object[str(object_id)] = candidate
    prototype_by_candidate = {
        str(row["candidate"]["candidate_id"]): row for row in prototypes
    }
    output_interval_by_object: dict[str, tuple[int, int]] = {}
    for (_chromosome, start0, end0), origin in gap_origins.items():
        for object_id in [
            str(origin["object_id"]),
            *[str(value) for value in origin.get("coalesced_object_ids", [])],
        ]:
            output_interval_by_object[object_id] = (start0 + 1, end0)
    events: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    primary_events: dict[str, dict[str, object]] = {}
    for gap in gaps:
        object_id = str(gap["object_id"])
        accepted = accepted_by_object.get(object_id)
        related = candidates_by_object.get(object_id, [])
        event_id = stable_id(
            "event", [run_id, "step2", object_id, "structural"], 24
        )
        prototype = None
        gapless_junction = False
        if accepted is not None:
            candidate_id = str(accepted["candidate_id"])
            prototype = prototype_by_candidate.get(candidate_id)
            if prototype is None:
                fail(f"Step2 structural event is missing its edit prototype: {candidate_id}")
            gapless_junction = accepted.get("junction_policy") in {
                PRIMARY_OVERLAP_POLICY, DOMINATED_COMPONENT_POLICY,
            }
        if gapless_junction:
            # A deleted gap has no output gap origin. Its event (including any
            # absorbed objects) points at the retained junction, not a fake N.
            q_after_start = int(prototype["intermediate_start"])
            q_after_end = int(prototype["intermediate_end"])
            if (
                int(prototype["replacement_length"]) != 0
                or q_after_start != q_after_end
                or q_after_start < 1
            ):
                fail(f"Step2 gapless edit has an invalid junction prototype: {candidate_id}")
        else:
            interval = output_interval_by_object.get(object_id)
            if interval is None:
                fail(f"Step2 structural event is missing its output gap interval: {object_id}")
            q_after_start, q_after_end = interval
        if accepted is None:
            conflict = any(row.get("outcome") == "conflicted" for row in related)
            status = "conflicted" if conflict else "unresolved"
            reason = (
                "all_structural_candidates_conflicted"
                if conflict
                else "structural_candidates_rejected"
                if related
                else "no_structural_error_detected"
            )
            event = {
                "run_id": run_id,
                "event_id": event_id,
                "stage": "step2",
                "chr": gap["chr"],
                "object_id": object_id,
                "action": "correct_boundary",
                "status": status,
                "reason": reason,
                "q_before": {
                    "version": "q1",
                    "start": int(gap["start0"]) + 1,
                    "end": int(gap["end0"]),
                    "sha256": q1_sha256,
                },
                "q_after": {
                    "version": "q2",
                    "start": q_after_start,
                    "end": q_after_end,
                    "sha256": q2_sha256,
                },
                "source": None,
                "evidence_ids": sorted(
                    {
                        str(evidence_id)
                        for row in related
                        for evidence_id in row.get("evidence_ids", [])
                    }
                ),
                "usage_ids": [],
                "source_card_key": "",
                "final_path_segment_id": "",
            }
        elif str(accepted["object_id"]) != object_id:
            primary_event_id = stable_id(
                "event",
                [run_id, "step2", str(accepted["object_id"]), "structural"],
                24,
            )
            event = {
                "run_id": run_id,
                "event_id": event_id,
                "stage": "step2",
                "chr": gap["chr"],
                "object_id": object_id,
                "action": "correct_boundary",
                "status": "superseded",
                "reason": f"absorbed_by_structural_event:{primary_event_id}",
                "q_before": {
                    "version": "q1",
                    "start": int(gap["start0"]) + 1,
                    "end": int(gap["end0"]),
                    "sha256": q1_sha256,
                },
                "q_after": {
                    "version": "q2",
                    "start": q_after_start,
                    "end": q_after_end,
                    "sha256": q2_sha256,
                },
                "source": None,
                "evidence_ids": list(accepted.get("evidence_ids", [])),
                "usage_ids": [],
                "source_card_key": "",
                "final_path_segment_id": "",
                "superseded_by_event_id": primary_event_id,
            }
        else:
            event = {
                "run_id": run_id,
                "event_id": event_id,
                "stage": "step2",
                "chr": gap["chr"],
                "object_id": object_id,
                "action": accepted["action"],
                "status": "accepted",
                "reason": accepted["classification_reason"],
                "q_before": {
                    "version": "q1",
                    "start": int(accepted["input_start"]),
                    "end": int(accepted["input_end"]),
                    "sha256": q1_sha256,
                },
                "q_after": {
                    "version": "q2",
                    "start": q_after_start,
                    "end": q_after_end,
                    "sha256": q2_sha256,
                },
                "source": None,
                "evidence_ids": list(accepted.get("evidence_ids", [])),
                "usage_ids": [],
                "source_card_key": "",
                "final_path_segment_id": "",
                "edit": {
                    "operation": "replace_interval",
                    "replacement_kind": "none" if gapless_junction else "gap",
                    "input_coordinate_space": "q1_1_based_closed",
                    "input_start": int(accepted["input_start"]),
                    "input_end": int(accepted["input_end"]),
                    "intermediate_output_start": prototype["intermediate_start"],
                    "intermediate_output_end": prototype["intermediate_end"],
                    "replacement_length": int(prototype["replacement_length"]),
                    "replacement_sequence_sha256": sha256_bytes(
                        ("N" * int(prototype["replacement_length"])).encode("ascii")
                    ),
                },
            }
            if accepted.get("junction_policy") == PRIMARY_OVERLAP_POLICY:
                event["junction"] = {
                    "policy": PRIMARY_OVERLAP_POLICY,
                    "left_trim": int(accepted["trim_left"]),
                    "right_trim": int(accepted["trim_right"]),
                    "direct_overlap_bp": int(accepted["direct_overlap_bp"]),
                    "left_source": {
                        "dataset": accepted["primary_left_dataset"],
                        "contig": accepted["primary_left_contig"],
                        "orientation": accepted["primary_left_orientation"],
                    },
                    "right_source": {
                        "dataset": accepted["primary_right_dataset"],
                        "contig": accepted["primary_right_contig"],
                        "orientation": accepted["primary_right_orientation"],
                    },
                    "support_sequence_inserted": False,
                }
            elif accepted.get("junction_policy") == DOMINATED_COMPONENT_POLICY:
                event["junction"] = {
                    "policy": DOMINATED_COMPONENT_POLICY,
                    "dominated_side": accepted["dominated_side"],
                    "support_sequence_inserted": False,
                }
            primary_events[object_id] = event
        classification = accepted or (related[0] if related else None)
        if classification is not None:
            event["classification"] = {
                "error_type": classification.get("error_type", "unknown"),
                "error_subtype": classification.get(
                    "error_subtype", "unspecified"
                ),
                "features": classification.get("error_features", []),
                "confidence": classification.get("confidence", "low"),
                "confidence_score": classification.get("confidence_score", 0.0),
                "gap_in_error_region": bool(
                    classification.get("gap_in_error_region", False)
                ),
            }
            event["repair_mode"] = classification.get(
                "repair_mode", DEFAULT_REPAIR_MODE
            )
            event["repair_reason"] = classification.get("repair_reason", "")
        events.append(event)
        attempts.append(
            {
                "attempt_id": stable_id(
                    "attempt", [run_id, "step2", object_id, "structural"], 22
                ),
                "chr": gap["chr"],
                "object_id": object_id,
                "stage": "step2",
                "status": event["status"],
                "reason": event["reason"],
                "candidate_count": len(related),
                "accepted_event_id": (
                    event_id
                    if event["status"] in {"accepted", "superseded"}
                    else ""
                ),
            }
        )
    for event in events:
        replacement_id = event.get("superseded_by_event_id")
        if replacement_id:
            replacement = next(
                row for row in events if row["event_id"] == replacement_id
            )
            replacement.setdefault("superseded_event_ids", []).append(
                event["event_id"]
            )
    return events, attempts



def execute_step2(args: argparse.Namespace) -> dict[str, object]:
    context = execution_context(args)
    step2, _step2_cached = run_step2(
        context["server_dir"],
        context["run_id"],
        context["chromosome_order"],
        context["q1_paths"],
        context["q1_records"],
        context["q1_rows"],
        context["donor_set"],
        context["donor_members"],
        context["assignments"],
        context["sources"],
        context["initial_consumed"],
        context["tools"],
        context["minimap"],
        args.threads,
        args.repair_mode,
        getattr(args, "step2_mummer_scope", DEFAULT_MUMMER_SCOPE),
        getattr(args, "execution_profile", DEFAULT_EXECUTION_PROFILE),
    )
    publish_repair_metadata(
        context["server_dir"], [step2], context["tools"], context["minimap"]
    )
    donor_set = context["donor_set"]
    if step2["donor_set_id"] != donor_set["donor_set_id"]:
        fail("Step2 does not reference the same frozen donor set as Step1")
    if step2["target_sha256"] != donor_set["fasta_sha256"]:
        fail("Step2 donor FASTA hash drifted from frozen D0")
    print(
        f"GRT Step2 complete: run={context['run_id']}, "
        f"donor_set={donor_set['donor_set_id']}, "
        f"q2_sha256={sha256_file(context['server_dir'] / 'grt/q/q2.fa')}"
    )
    return step2
