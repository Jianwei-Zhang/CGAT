#!/usr/bin/env python3
"""Verify an explicitly selected full Quality baseline for UI/docs-only packaging."""
import argparse
import json
import re
import subprocess
from pathlib import Path

QUALITY_JOBS = {"Quality gate / Windows app", "Quality gate / Linux server"}
EXACT_PATHS = {
    "README.md", "README_zh.md", "GPM2.0/README.md", "GPM2.0/README_zh.md",
    "GPM2.0/server/README.md", "GPM2.0/server/README_zh.md", "GPM2.0/RELEASING.md",
    ".github/workflows/release-installers.yml", "GPM2.0/scripts/reuse-release-quality.py",
    "GPM2.0/scripts/test_reuse_release_quality.py", "GPM2.0/scripts/test_app_update_feed.py",
}


def verify_baseline(run, jobs, repo, workflow):
    if run.get("repository", {}).get("full_name") != repo or run.get("head_repository", {}).get("full_name") != repo:
        raise ValueError("Quality baseline must belong to this repository, not a fork")
    if run.get("path") != ".github/workflows/release-installers.yml":
        raise ValueError("Baseline must be the full release-installer workflow")
    revision = run.get("head_sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid quality baseline revision")
    quality = re.search(r"(?ms)^  quality:\n(.*?)(?=^  [a-zA-Z]|\Z)", workflow)
    if not quality or "uses: ./.github/workflows/quality.yml" not in quality[1] or not re.search(r"(?m)^      full: true$", quality[1]):
        raise ValueError("Baseline workflow did not request full Quality")
    for name in QUALITY_JOBS:
        matches = [job for job in jobs if job.get("name") == name]
        if len(matches) != 1 or matches[0].get("status") != "completed" or matches[0].get("conclusion") != "success":
            raise ValueError("Full quality job did not succeed: " + name)
    return revision


def verify_changed_paths(paths):
    if not paths:
        return
    rejected = [path for path in paths if path not in EXACT_PATHS
                and not path.startswith("GPM2.0/app/frontend/src/")
                and not re.fullmatch(r"GPM2\.0/releases/v\d+\.\d+\.\d+\.md", path)]
    if rejected:
        raise ValueError("Quality reuse is restricted to reviewed UI/docs changes: " + ", ".join(rejected))


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        raise ValueError("Invalid repository")
    revision = git("rev-parse", args.revision + "^{commit}")
    if revision != git("rev-parse", "HEAD"):
        raise ValueError("Checkout does not match the final packaging revision")
    run = json.loads(subprocess.check_output(["gh", "api", f"repos/{args.repo}/actions/runs/{args.run_id}"]))
    pages = json.loads(subprocess.check_output(["gh", "api", "--paginate", "--slurp",
        f"repos/{args.repo}/actions/runs/{args.run_id}/jobs?filter=latest&per_page=100"]))
    jobs = [job for page in pages for job in page["jobs"]]
    baseline = run.get("head_sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", baseline):
        raise ValueError("Invalid baseline revision")
    baseline = verify_baseline(run, jobs, args.repo, git("show", baseline + ":.github/workflows/release-installers.yml"))
    subprocess.run(["git", "merge-base", "--is-ancestor", baseline, revision], check=True)
    paths = git("diff", "--name-only", "--no-renames", baseline, revision).splitlines()
    verify_changed_paths(paths)
    record = {"quality_run_id": args.run_id, "quality_revision": baseline,
              "packaging_revision": revision, "full_quality_jobs": sorted(QUALITY_JOBS),
              "changed_paths": paths, "scope": "explicitly approved UI/docs-only reuse"}
    args.output.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
