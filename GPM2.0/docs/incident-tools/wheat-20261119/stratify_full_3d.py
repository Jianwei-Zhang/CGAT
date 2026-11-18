"""Read-only full-3D comparison stratified by query length and baseline MAPQ."""
import json
import sys
from pathlib import Path
from paf_anchor_comparison import compare
from seed_filter_pilot import ROOT, WORK, measure


def main():
    sys.path.insert(0, str(WORK / ".prepare_lib/tools"))
    from run_orchestration import sha256_file
    root = ROOT / "seed-filter-full-3D-pilot-20261119"
    report = json.loads((root / "result.json").read_text())
    assert report["status"] == "candidate_and_native_compared_not_adopted"
    marker = json.loads(Path(report["native_leaf_checkpoint"]).read_text())
    baseline = WORK / next(r["path"] for r in marker["outputs"] if r["path"].endswith("result.paf"))
    candidate = root / "f0005/result.paf"
    assert sha256_file(baseline) == next(r["sha256"] for r in marker["outputs"] if r["path"].endswith("result.paf"))
    assert sha256_file(candidate) == next(r["sha256"] for r in report["outputs"] if r["path"].endswith("result.paf"))
    output = root / "stratified"
    output.mkdir()
    groups = [("all", lambda f: True), ("long_query_ge100M", lambda f: int(f[1]) >= 100_000_000),
              ("short_query_lt100M", lambda f: int(f[1]) < 100_000_000)]
    summaries = []
    for name, accept in groups:
        for quality in (0, 20, 60):
            directory = output / (name + "_baseline_mapq" + str(quality))
            directory.mkdir()
            paths = []
            for label, source in (("baseline", baseline), ("candidate", candidate)):
                path = directory / (label + ".paf")
                with source.open() as src, path.open("w") as dst:
                    for line in src:
                        f = line.rstrip("\n").split("\t")
                        # Only the baseline is quality-filtered: candidate MAPQ
                        # changes must not masquerade as a changed destination.
                        if accept(f) and (label != "baseline" or int(f[11]) >= quality):
                            dst.write(line)
                paths.append(path)
            result = compare(*paths)
            result.update(group=name, minimum_baseline_mapq=quality)
            result["baseline_metrics"], _ = measure(paths[0])
            result["candidate_metrics"], _ = measure(paths[1])
            summaries.append(result)
    (root / "stratified-comparisons.json").write_text(json.dumps(summaries, indent=2) + "\n")
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == "__main__":
    main()
