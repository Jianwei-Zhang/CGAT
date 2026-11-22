"""Actual fixed DEGAP HTML generators; controlled diagnostics, no biology run."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path


def module(name):
    path = Path(__file__).resolve().parents[1] / "tools/degap_core/bin" / (name + ".py")
    spec = importlib.util.spec_from_file_location("controlled_" + name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def create(native, gap=None):
    native = Path(native)
    gap_file = native / "03.gap_filling/gap_filling_results.json"
    if not gap_file.exists():
        gap_file.parent.mkdir(parents=True, exist_ok=True)
        value = {"gaps": [{"chromosome": gap.chromosome if gap else "chr1", "gap_id": 1,
                          "gap_start": gap.start if gap else 4, "gap_end": gap.end if gap else 9,
                          "filled": True, "fill_direction": "left", "fill_type": "extension", "rounds": 0}],
                 "summary": {"total_gaps": 1, "filled_gaps": 1, "unfilled_gaps": 0, "fill_rate": "100%"}}
        gap_file.write_text(json.dumps(value))
    data = json.loads(gap_file.read_text())
    first = data["gaps"][0]
    config = native / "03.gap_filling/job_manager_config.json"
    jobs = json.loads(config.read_text())["jobs"] if config.exists() else []
    renderer = module("GapfillerVisualizer")
    for direction in ("left", "right"):
        directory = native / "03.gap_filling" / (str(first["chromosome"]) + "." + str(first["gap_id"]) + "." + direction)
        directory.mkdir(parents=True, exist_ok=True)
        log = directory / "process.log"
        log.write_text("Controlled native visualization diagnostic; no gap-closing algorithm executed.\n")
        output = directory / "visualization_output"
        with contextlib.redirect_stdout(io.StringIO()):
            parsed = renderer.GapfillerLogParser(log).parse_log()
            parsed["initial_info"].update(hifi_seed_len=100, ont_seed_len=200, primary_seed_len=100, data_type="hifi")
            renderer.HTMLReportGenerator(parsed, output, max_extension_length=1000, extension_flag=direction).generate_report()
        if not any(job.get("direction") == direction for job in jobs):
            jobs.append({"job_name": directory.name, "job_dir": str(directory), "chromosome": first["chromosome"],
                         "gap_id": first["gap_id"], "direction": direction})
    config.write_text(json.dumps({"jobs": jobs}))
    global_renderer = module("AutoGapfillerVisualizer")
    with contextlib.redirect_stdout(io.StringIO()):
        global_renderer.GapFillingVisualizer(native).generate_report()
    return native
