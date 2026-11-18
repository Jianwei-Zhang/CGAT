"""Second isolated pilot: 3 x 20 Mb per chromosome; no production mutation."""
import json
from pathlib import Path
import seed_filter_pilot as pilot
from paf_anchor_comparison import compare


def main():
    pilot.HERE = pilot.ROOT / "seed-filter-long-window-pilot-20261119"
    pilot.WINDOW = 20_000_000
    pilot.TIMEOUT = 600
    pilot.main()
    from run_orchestration import sha256_file
    comparisons = []
    for root in (pilot.ROOT / "seed-filter-pilot-20261119", pilot.HERE):
        results = json.loads((root / "results.json").read_text())
        lookup = {(row["chromosome"], row["variant"]): row for row in results["results"]}
        for chromosome in ("3D", "1A"):
            base = lookup[(chromosome, "baseline")]
            for variant in ("f0001", "f0005"):
                row = lookup[(chromosome, variant)]
                if base["returncode"] or row["returncode"]:
                    comparisons.append({"directory": str(root), "chromosome": chromosome,
                                        "variant": variant, "status": "not_comparable"})
                    continue
                before = root / chromosome / "baseline/result.paf"
                after = root / chromosome / variant / "result.paf"
                assert sha256_file(before) == base["paf_sha256"]
                assert sha256_file(after) == row["paf_sha256"]
                metrics = compare(before, after)
                metrics.update(directory=str(root), chromosome=chromosome, variant=variant)
                comparisons.append(metrics)
    (pilot.HERE / "cigar-anchor-comparisons.json").write_text(json.dumps(comparisons, indent=2) + "\n")
    print("CIGAR_ANCHOR_COMPARISONS", json.dumps(comparisons), flush=True)


if __name__ == "__main__":
    main()
