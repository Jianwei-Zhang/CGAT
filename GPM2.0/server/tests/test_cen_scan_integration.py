"""Real MUMmer4 adapter checks; synthetic controls, not species-wide acceptance."""
import csv
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / "tools"))
from annotation_library import fasta_bytes, fasta_records, snapshot, verify_snapshot
from cen_scan import scan


class RealMummerCentromereTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("nucmer") or not shutil.which("show-coords"):
            raise unittest.SkipTest("requires MUMmer4 nucmer and show-coords")
        version = subprocess.run(["nucmer", "--version"], capture_output=True, text=True, check=True)
        if not re.search(r"\b4\.", version.stdout + version.stderr):
            raise unittest.SkipTest("requires MUMmer4, not the legacy MUMmer3 binary")
        cls.units = {path.stem: next(fasta_records(path))[1] for path in (SERVER / "library/cen").glob("*.fa")}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.server = self.root / "tools"
        shutil.copytree(SERVER / "library", self.server / "library")
        snapshot(self.server, self.project, [], None, 10000, 80)

    def run_scan(self, records):
        fasta = self.root / "assembly.fa"
        fasta.write_bytes(fasta_bytes(records))
        scan(self.project, "ChrSynthetic", [f"assembly={fasta}"], 2, self.project / "runs/cen_scan")
        with (self.project / "cen/chr_ChrSynthetic/marks.tsv").open(newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    def test_all_official_units_on_both_strands_and_random_negative(self):
        records, expected = [], {}
        rc = str.maketrans("ACGT", "TGCA")
        for name, unit in self.units.items():
            for strand, sequence in (("plus", unit * 80), ("minus", (unit * 80).translate(rc)[::-1])):
                contig = name + "_" + strand
                records.append((contig, "N" * 250 + sequence + "N" * 250))
                expected[contig] = (name, len(sequence), "+" if strand == "plus" else "-")
        rng = random.Random(731)
        records.append(("unrelated_control", "".join(rng.choices("ACGT", k=20000))))
        rows = self.run_scan(records)
        self.assertEqual({r["ctg_name"] for r in rows}, set(expected))
        self.assertEqual(len(rows), len(expected))
        for row in rows:
            name, length, strand = expected[row["ctg_name"]]
            self.assertEqual((int(row["ctg_start"]), int(row["ctg_end"])), (251, 250 + length))
            self.assertEqual(int(row["align_length"]), length)
            self.assertEqual(row["strand"], strand)
            self.assertEqual(float(row["identity"]), 100.0)
            self.assertEqual(row["mapq"], "0")
            self.assertIn(name, {entry["id"] for entry in json.loads(row["provenance"])})

    def test_real_prepare_assignment_and_scans_enable_library_without_flags(self):
        for tool in ("samtools", "minimap2", "zip", "gzip", "delta-filter"):
            if not shutil.which(tool):
                self.skipTest(f"prepare integration requires {tool}")
        for name in ("tools", "lib", "templates", "contracts"):
            shutil.copytree(SERVER / name, self.server / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy2(SERVER / "prepare.sh", self.server / "prepare.sh")
        rng = random.Random(912)
        sequence = "TTTAGGG" * 30 + "".join(rng.choices("ACGT", k=4000))
        sequence += self.units["cen_rice_CentO"] * 80
        sequence += "".join(rng.choices("ACGT", k=4000)) + "CCCTAAA" * 30
        reference = self.root / "reference.fa"
        assembly = self.root / "assembly.fa"
        reference.write_bytes(fasta_bytes([("Chr01", sequence)]))
        assembly.write_bytes(fasta_bytes([("ctg", sequence)]))
        fresh = self.root / "prepared"
        commands = [
            ["bash", str(self.server / "prepare.sh"), "--ref", "ref", str(reference),
             "--ds", "assembly", str(assembly), "--threads", "2", "--skip-self",
             "--archive-format", "zip", "-o", str(fresh)],
            ["bash", str(fresh / "runs/assembly_vs_ref/command.sh")],
            ["bash", str(fresh / "assign_chr_groups.sh")],
            ["bash", str(fresh / "runs/chr_Chr01/command.sh")],
        ]
        for command in commands:
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-4000:])
        verify_snapshot(fresh)
        with (fresh / "tel/chr_Chr01/assembly.tsv").open(newline="") as handle:
            tel = list(csv.DictReader(handle, delimiter="\t"))
        with (fresh / "cen/chr_Chr01/marks.tsv").open(newline="") as handle:
            cen = list(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual({row["strand"] for row in tel if row["motif"] == "TTTAGGG"}, {"+", "-"})
        self.assertEqual(len(cen), 1)
        self.assertEqual((int(cen[0]["ctg_start"]), int(cen[0]["ctg_end"])), (4211, 16610))
        self.assertEqual(json.loads(cen[0]["provenance"])[0]["id"], "cen_rice_CentO")

    def test_merge_gap_boundary_and_separate_contigs(self):
        unit = self.units["cen_rice_CentO"]
        half = unit * 40
        records = [("gap200", half + "N" * 200 + half),
                   ("gap201", half + "N" * 201 + half),
                   ("left_only", half), ("right_only", half)]
        rows = self.run_scan(records)
        self.assertEqual([r["ctg_name"] for r in rows], ["gap200"])
        self.assertEqual(int(rows[0]["align_length"]), 2 * len(half))
        self.assertEqual(int(rows[0]["region_length"]), 2 * len(half) + 200)

    def test_adjacent_distinct_families_preserve_both_sources(self):
        first = self.units["cen_arabidopsis_CEN180"] * 40
        second = self.units["cen_rice_CentO"] * 40
        rows = self.run_scan([("mixed", first + "N" * 20 + second)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["align_length"]), len(first) + len(second))
        self.assertEqual({e["id"] for e in json.loads(rows[0]["provenance"])},
                         {"cen_arabidopsis_CEN180", "cen_rice_CentO"})


if __name__ == "__main__":
    unittest.main()
