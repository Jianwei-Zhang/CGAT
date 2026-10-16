"""Shared staged repair context, metadata publication and CLI arguments."""

from __future__ import annotations

from .repair_common import *


def publish_repair_metadata(
    server_dir: Path,
    results: list[dict[str, object]],
    tools: dict[str, dict[str, str]],
    minimap: dict[str, str],
) -> None:
    metadata = server_dir / "metadata"
    q_rows = [
        row
        for row in read_tsv(metadata / "grt_q_segments.tsv", Q_SEGMENT_FIELDS)
        if row["q_version"] not in {"q2", "q3", "q4"}
    ]
    evidence_rows = [
        row
        for row in read_tsv(metadata / "grt_evidence_registry.tsv", EVIDENCE_FIELDS)
        if row["stage"] not in {"step2", "step3", "step4_telomere", "candidate_validation"}
    ]
    usage_rows = [
        row
        for row in read_tsv(metadata / "grt_donor_usage.tsv", USAGE_FIELDS)
        if row["stage"] not in {"step2", "step3", "step4_telomere"}
    ]
    events = [
        json.loads(line)
        for line in (metadata / "grt_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    events = [
        row
        for row in events
        if row["stage"] not in {"step2", "step3", "step4_telomere"}
    ]
    attempts = [
        row
        for row in read_tsv(metadata / "grt_gap_attempts.tsv", ATTEMPT_FIELDS)
        if row["stage"] not in {"step2", "step3", "step4_telomere"}
    ]
    stage_rows = [
        row
        for row in read_tsv(metadata / "grt_stage_status.tsv", STAGE_FIELDS)
        if row["stage"] not in {"step2", "step3", "step4_telomere", "finalize"}
    ]
    for result in results:
        q_rows.extend(result["q_rows"])
        evidence_rows.extend(result["evidence_rows"])
        usage_rows.extend(result["usage_rows"])
        events.extend(result["events"])
        attempts.extend(result["attempts"])
        stage_rows.append(stage_status_row(server_dir, result))
    tool_rows = [
        row
        for row in read_tsv(metadata / "grt_tool_versions.tsv", TOOL_FIELDS)
        if row["tool"]
        not in {
            "grt_step_engine",
            "grt_step2",
            "grt_step3",
            "grt_step23",
            "step23_nucmer",
            "step23_delta_filter",
            "step23_show_coords",
            "step23_minimap2",
        }
    ]
    tool_rows.extend(
        [
            {
                "tool": "grt_step_engine",
                "version": str(ENGINE_VERSION),
                "executable": ".prepare_lib/tools/grt_core/repair_common.py",
            },
            {
                "tool": "grt_step2",
                "version": str(ENGINE_VERSION),
                "executable": ".prepare_lib/tools/grt_step2.py",
            },
            {
                "tool": "grt_step3",
                "version": str(ENGINE_VERSION),
                "executable": ".prepare_lib/tools/grt_step3.py",
            },
            {
                "tool": "step23_nucmer",
                "version": tools["nucmer"]["version"],
                "executable": tools["nucmer"]["resolved"],
            },
            {
                "tool": "step23_delta_filter",
                "version": tools["delta-filter"]["version"],
                "executable": tools["delta-filter"]["resolved"],
            },
            {
                "tool": "step23_show_coords",
                "version": tools["show-coords"]["version"],
                "executable": tools["show-coords"]["resolved"],
            },
            {
                "tool": "step23_minimap2",
                "version": minimap["version"],
                "executable": minimap["resolved"],
            },
        ]
    )
    strategy_rows = [
        row
        for result in results
        for row in result.get("strategies", [])
    ]
    classification_rows = [
        row
        for result in results
        for row in result.get("classification_rows", [])
    ]
    atomic_write_tsv(metadata / "grt_q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
    atomic_write_tsv(metadata / "grt_evidence_registry.tsv", EVIDENCE_FIELDS, evidence_rows)
    atomic_write_tsv(metadata / "grt_donor_usage.tsv", USAGE_FIELDS, usage_rows)
    atomic_write_jsonl(metadata / "grt_events.jsonl", events)
    atomic_write_tsv(metadata / "grt_gap_attempts.tsv", ATTEMPT_FIELDS, attempts)
    atomic_write_tsv(metadata / "grt_stage_status.tsv", STAGE_FIELDS, stage_rows)
    atomic_write_tsv(metadata / "grt_tool_versions.tsv", TOOL_FIELDS, tool_rows)
    atomic_write_tsv(
        metadata / "grt_step2_strategies.tsv",
        STRATEGY_FIELDS,
        strategy_rows,
    )
    atomic_write_tsv(
        metadata / "grt_step3_classifications.tsv",
        CLASSIFICATION_FIELDS,
        classification_rows,
    )



def execution_context(args: argparse.Namespace) -> dict[str, object]:
    server_dir = args.server_dir.resolve()
    package = read_single(server_dir / "metadata/package.tsv")
    if (
        package.get("workflow") != WORKFLOW
        or package.get("schema_version") != SCHEMA_VERSION
        or package.get("grt_precompute_enabled") != "true"
        or package.get("recipe_locked") != "true"
    ):
        fail("unsupported package workflow/schema; Step2/3 has no legacy fallback")
    recipe = read_single(
        server_dir / "metadata/grt_recipe.tsv",
        [
            "recipe_id",
            "primary_dataset",
            "support_datasets_json",
            "reads_qc_enabled",
            "donor_set_id",
            "tel_donor_set_id",
            "q0_relpath",
            "final_q_relpath",
        ],
    )
    donor_set, donor_members, _donor_freeze = verify_donor_freeze(server_dir, recipe)
    sources = source_catalog(server_dir)
    assignments = assignment_map(server_dir)
    all_q_rows = read_tsv(server_dir / "metadata/grt_q_segments.tsv", Q_SEGMENT_FIELDS)
    q1_rows = [row for row in all_q_rows if row["q_version"] == "q1"]
    if not q1_rows or not (server_dir / "grt/q/q1.fa").is_file():
        fail("Step2 requires a completed q1/Step1 mapping")
    chromosome_order, q1_paths, q1_records = load_q_paths(server_dir, "q1", q1_rows, sources)
    tools = {
        "nucmer": executable_identity(args.nucmer),
        "delta-filter": executable_identity(args.delta_filter),
        "show-coords": executable_identity(args.show_coords),
    }
    minimap = executable_identity(args.minimap2)
    existing_usage = read_tsv(server_dir / "metadata/grt_donor_usage.tsv", USAGE_FIELDS)
    existing_events = [
        json.loads(line)
        for line in (server_dir / "metadata/grt_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    initial_consumed = consumed_intervals(
        [row for row in existing_usage if row["stage"].startswith("step1_")],
        existing_events,
    )
    run_id = stable_id(
        "grt-run",
        {
            "recipe_id": recipe["recipe_id"],
            "donor_set_id": donor_set["donor_set_id"],
            "q1_sha256": sha256_file(server_dir / "grt/q/q1.fa"),
            "engine_version": ENGINE_VERSION,
            "engine_sha256": ENGINE_SHA256,
            "tools": {name: command_identity(value) for name, value in {**tools, "minimap2": minimap}.items()},
        },
        24,
    )
    return {
        "server_dir": server_dir,
        "recipe": recipe,
        "donor_set": donor_set,
        "donor_members": donor_members,
        "sources": sources,
        "assignments": assignments,
        "q1_rows": q1_rows,
        "chromosome_order": chromosome_order,
        "q1_paths": q1_paths,
        "q1_records": q1_records,
        "tools": tools,
        "minimap": minimap,
        "initial_consumed": initial_consumed,
        "run_id": run_id,
    }



def add_common_cli_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--server-dir", required=True, type=Path)
    parser.add_argument("--nucmer", default="nucmer")
    parser.add_argument("--delta-filter", dest="delta_filter", default="delta-filter")
    parser.add_argument("--show-coords", dest="show_coords", default="show-coords")
    parser.add_argument("--minimap2", default="minimap2")
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument(
        "--execution-profile", choices=sorted(EXECUTION_PROFILES),
        default=DEFAULT_EXECUTION_PROFILE,
        help="Exact execution profile: optimized (default) or baseline rollback",
    )
    parser.add_argument(
        "--repair-mode",
        choices=sorted(REPAIR_MODES),
        default=DEFAULT_REPAIR_MODE,
        help="CorrectRefill structural repair mode (default: aggressive)",
    )



def validate_common_cli_arguments(args: argparse.Namespace) -> None:
    if args.threads < 1:
        fail("threads must be a positive integer")
