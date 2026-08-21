import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]
from server.tests import test_grt_prepare_inputs as prepare_fixture
from server.tests import test_grt_telomere_finalize as telomere_fixture
from server.tools.grt_contract import ContractError, validate_contract
from server.tools.grt_evidence_package import build_ref_evidence
from server.tools.grt_prepare_inputs import read_fasta
from server.tools.grt_step1 import source_assignment


TOOL = REPO_ROOT / "server/tools/grt_evidence_package.py"
SCHEMA = REPO_ROOT / "server/contracts/grt_precomputed_v2.json"


class GrtEvidencePackageTests(unittest.TestCase):
    def test_multi_chr_assignment_is_normal_on_any_assigned_target(self):
        assignments = {("support", "multi"): {"Chr01", "Chr02"}}
        self.assertEqual(
            source_assignment(
                assignments,
                {
                    "source_dataset": "support",
                    "source_contig": "multi",
                    "chr": "Chr01",
                },
            ),
            ("assigned", "normal", "support:multi:Chr01:normal"),
        )
        self.assertEqual(
            source_assignment(
                assignments,
                {
                    "source_dataset": "support",
                    "source_contig": "multi",
                    "chr": "Chr03",
                },
            ),
            (
                "cross_chr",
                "cross_chr_grt_usage",
                "support:multi:Chr03:cross_chr_grt_usage",
            ),
        )

    def test_ref_profile_explicitly_classifies_hit_weak_multi_other_and_no_hit(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server = prepare_fixture.GrtPrepareInputsTests(
                "test_no_reads_builds_traceable_q0_and_frozen_global_donors"
            ).make_server(root)
            dataset_row = next(
                row
                for row in prepare_fixture.read_tsv(server / "metadata/datasets.tsv")
                if row["dataset_name"] == "support"
            )
            reference_row = prepare_fixture.read_tsv(server / "metadata/reference.tsv")[0]
            paf_path = server / "runs/support_vs_ref/result.paf"
            target_hit = (
                "s_assigned\t1500\t0\t1500\t+\tChr01\t5000\t3000\t4500"
                "\t1500\t1500\t60\n"
            )
            other_hit = (
                "s_assigned\t1500\t0\t1400\t+\tChr02\t5000\t100\t1500"
                "\t1400\t1400\t40\n"
            )
            cases = [
                ("hit", "assigned", target_hit, "hit", 3001, 1, 1),
                ("weak", "unplaced", target_hit, "weak_hit", 3001, 1, 1),
                ("multi", "unplaced", target_hit + other_hit, "multi_hit", 3001, 2, 1),
                ("other", "cross_chr", other_hit, "other_chr_only", 777, 1, 0),
                ("none", "unplaced", "", "no_hit", 777, 0, 0),
            ]

            for (
                name,
                assignment,
                paf,
                expected_status,
                expected_anchor,
                source_hits,
                target_hits,
            ) in cases:
                with self.subTest(name=name):
                    paf_path.write_text(paf, encoding="utf-8", newline="")
                    evidence, status, anchor = build_ref_evidence(
                        server,
                        {
                            "dataset_name": "support",
                            "contig_name": "s_assigned",
                            "target_chr": "Chr01",
                            "original_assignment": assignment,
                            "orientation": "+",
                            "source_card_key": f"support:s_assigned:Chr01:{name}",
                            "grt_anchor": 777,
                        },
                        "T" * 1500,
                        dataset_row,
                        reference_row,
                    )
                    parameters = json.loads(evidence["parameters_json"])
                    self.assertEqual(status, expected_status)
                    self.assertEqual(anchor, expected_anchor)
                    self.assertEqual(parameters["source_hit_count"], source_hits)
                    self.assertEqual(parameters["target_hit_count"], target_hits)
                    self.assertEqual(
                        parameters["anchor_source"],
                        "grt_final_path"
                        if expected_status in {"other_chr_only", "no_hit"}
                        else "reference_paf",
                    )

    def write_executable(self, path: Path, source: str) -> Path:
        path.write_text(source, encoding="utf-8", newline="")
        path.chmod(0o755)
        return path

    def make_finalized_server(self, root: Path) -> Path:
        helper = telomere_fixture.GrtTelomereFinalizeTests(
            "test_assigned_and_unplaced_recovery_unresolved_and_exact_resume"
        )
        server = helper.make_server(root)
        tools = helper.make_tools(root)
        env = os.environ.copy()
        env["FAKE_TEL_MUMMER_LOG"] = str(root / "package_tel_mummer.log")
        env["FAKE_TEL_MINIMAP_LOG"] = str(root / "package_tel_minimap.log")
        completed = helper.run_finalize(server, tools, env)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return server

    def write_existing_main_view_results(self, server: Path) -> None:
        assignments = prepare_fixture.read_tsv(server / "metadata/chr_assignments.tsv")
        datasets = prepare_fixture.read_tsv(server / "metadata/datasets.tsv")
        source_records = {
            row["dataset_name"]: dict(read_fasta(server / row["fasta_relpath"]))
            for row in datasets
        }
        chr_name = "Chr01"
        chr_run = server / f"runs/chr_{chr_name}"
        for dataset in datasets:
            dataset_name = dataset["dataset_name"]
            selected = [
                (row["seq_name"], source_records[dataset_name][row["seq_name"]])
                for row in assignments
                if row["dataset_name"] == dataset_name
                and row["assigned_chr_name"] == chr_name
            ]
            if selected:
                prepare_fixture.write_fasta(
                    chr_run / f"datasets/{dataset_name}.fa", selected
                )
                result = chr_run / f"{dataset_name}_vs_self/result.paf"
                result.parent.mkdir(parents=True, exist_ok=True)
                result.write_text("", encoding="utf-8", newline="")
        pair_result = chr_run / "primary_vs_support/result.paf"
        pair_result.parent.mkdir(parents=True, exist_ok=True)
        pair_result.write_text("", encoding="utf-8", newline="")

    def make_minimap(self, root: Path) -> Path:
        return self.write_executable(
            root / "fake_display_minimap2.py",
            r'''#!/usr/bin/env python3
import os
import sys

if '--version' in sys.argv:
    print('minimap2 fixture display 1')
    raise SystemExit(0)

def fasta(path):
    records = []
    name = None
    parts = []
    with open(path, encoding='utf-8') as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith('>'):
                if name is not None:
                    records.append((name, ''.join(parts)))
                name = line[1:].split()[0]
                parts = []
            elif line:
                parts.append(line)
    if name is not None:
        records.append((name, ''.join(parts)))
    return records

args = sys.argv[1:]
output = args[args.index('-o') + 1]
target_name, target = fasta(args[-2])[0]
query_name, query = fasta(args[-1])[0]
with open(os.environ['FAKE_DISPLAY_MINIMAP_LOG'], 'a', encoding='utf-8') as handle:
    handle.write(query_name + '\t' + target_name + '\n')
overlap = min(len(query), len(target))
with open(output, 'w', encoding='utf-8', newline='') as handle:
    handle.write(
        f'{query_name}\t{len(query)}\t0\t{overlap}\t+\t{target_name}\t{len(target)}'
        f'\t0\t{overlap}\t{overlap}\t{overlap}\t60\tcg:Z:{overlap}M\n'
    )
''',
        )

    def run_tool(self, server: Path, minimap: Path, env: dict[str, str]):
        return subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--server-dir",
                str(server),
                "--minimap2",
                str(minimap),
                "--threads",
                "2",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_used_sources_reuse_or_supplement_and_validate_bidirectionally(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server = self.make_finalized_server(root)
            self.write_existing_main_view_results(server)
            minimap = self.make_minimap(root)
            log = root / "display_minimap.log"
            env = os.environ.copy()
            env["FAKE_DISPLAY_MINIMAP_LOG"] = str(log)

            completed = self.run_tool(server, minimap, env)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertGreaterEqual(summary["used_contigs"], 2)
            cards = prepare_fixture.read_tsv(
                server / "metadata/grt_used_contigs.tsv"
            )
            by_contig = {row["contig_name"]: row for row in cards}
            self.assertEqual(by_contig["s_tel_assigned"]["placement_mode"], "normal")
            self.assertEqual(by_contig["s_tel_assigned"]["ref_alignment_status"], "hit")
            self.assertEqual(by_contig["s_tel_unplaced"]["placement_mode"], "grt_promoted")
            self.assertEqual(by_contig["s_tel_unplaced"]["ref_alignment_status"], "no_hit")
            self.assertNotIn("s_tel_short", by_contig)

            evidence = prepare_fixture.read_tsv(
                server / "metadata/grt_evidence_registry.tsv"
            )
            evidence_by_id = {row["evidence_id"]: row for row in evidence}
            assigned_pairwise = [
                evidence_by_id[evidence_id]
                for evidence_id in json.loads(
                    by_contig["s_tel_assigned"]["pairwise_evidence_ids_json"]
                )
            ]
            self.assertTrue(
                all(
                    json.loads(row["parameters_json"])["provenance"]
                    == "existing_main_view"
                    for row in assigned_pairwise
                )
            )
            promoted_pairwise = [
                evidence_by_id[evidence_id]
                for evidence_id in json.loads(
                    by_contig["s_tel_unplaced"]["pairwise_evidence_ids_json"]
                )
            ]
            self.assertTrue(
                all(
                    json.loads(row["parameters_json"])["provenance"]
                    == "grt_supplement"
                    for row in promoted_pairwise
                )
            )
            self.assertTrue(
                all(row["query_artifact_relpath"].endswith("/query.fa") for row in promoted_pairwise)
            )
            self.assertNotIn("s_tel_short", log.read_text(encoding="utf-8"))
            contract_summary = validate_contract(server, SCHEMA)
            self.assertEqual(contract_summary["segments"], summary["segments"])

            calls = log.read_text(encoding="utf-8")
            repeated = self.run_tool(server, minimap, env)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(log.read_text(encoding="utf-8"), calls)

            cards_path = server / "metadata/grt_used_contigs.tsv"
            broken_cards = prepare_fixture.read_tsv(cards_path)
            next(
                row for row in broken_cards if row["contig_name"] == "s_tel_unplaced"
            )["pairwise_evidence_ids_json"] = '["missing-display-evidence"]'
            prepare_fixture.write_tsv(cards_path, list(broken_cards[0]), broken_cards)
            with self.assertRaises(ContractError) as raised:
                validate_contract(server, SCHEMA)
            self.assertEqual(raised.exception.code, "BROKEN_REFERENCE")

    def test_normal_used_card_reuses_signed_target_assignment_anchor(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server = self.make_finalized_server(root)
            assignments_path = server / "metadata/chr_assignments.tsv"
            assignments = prepare_fixture.read_tsv(assignments_path)
            chr01 = next(
                row
                for row in assignments
                if row["dataset_name"] == "support"
                and row["seq_name"] == "s_tel_assigned"
                and row["assigned_chr_name"] == "Chr01"
            )
            chr01["anchor_start"] = "-205687"
            chr02 = dict(chr01)
            chr02["assigned_chr_name"] = "Chr02"
            chr02["anchor_start"] = "-172703"
            assignments.append(chr02)
            prepare_fixture.write_tsv(
                assignments_path, list(assignments[0]), assignments
            )
            with (server / "runs/support_vs_ref/result.paf").open(
                "a", encoding="utf-8", newline=""
            ) as handle:
                handle.write(
                    "s_tel_assigned\t20000\t1000\t20000\t+\tChr02\t60000\t100\t19100"
                    "\t19000\t19000\t60\n"
                )
            self.write_existing_main_view_results(server)
            minimap = self.make_minimap(root)
            env = os.environ.copy()
            env["FAKE_DISPLAY_MINIMAP_LOG"] = str(root / "signed_anchor_display.log")

            completed = self.run_tool(server, minimap, env)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            card = next(
                row
                for row in prepare_fixture.read_tsv(
                    server / "metadata/grt_used_contigs.tsv"
                )
                if row["contig_name"] == "s_tel_assigned"
            )

            self.assertEqual(card["source_card_key"], "support:s_tel_assigned:Chr01:normal")
            self.assertEqual(card["target_chr"], "Chr01")
            self.assertEqual(card["anchor_start"], "-205687")
            self.assertEqual(card["ref_alignment_status"], "multi_hit")
            validate_contract(server, SCHEMA)

    def test_cross_chr_source_is_linked_without_moving_original_card(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server = self.make_finalized_server(root)
            assignments_path = server / "metadata/chr_assignments.tsv"
            assignments = prepare_fixture.read_tsv(assignments_path)
            for row in assignments:
                if row["dataset_name"] == "support" and row["seq_name"] == "s_tel_assigned":
                    row["assigned_chr_name"] = "Chr02"
            prepare_fixture.write_tsv(assignments_path, list(assignments[0]), assignments)

            events_path = server / "metadata/grt_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            changed = False
            for event in events:
                source = event.get("source")
                if (
                    event["status"] == "accepted"
                    and isinstance(source, dict)
                    and source["contig"] == "s_tel_assigned"
                ):
                    source["original_assignment"] = "cross_chr"
                    event["source_card_key"] = (
                        "support:s_tel_assigned:Chr01:cross_chr_grt_usage"
                    )
                    changed = True
            self.assertTrue(changed)
            events_path.write_text(
                "".join(
                    json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                    for row in events
                ),
                encoding="utf-8",
                newline="",
            )
            self.write_existing_main_view_results(server)
            minimap = self.make_minimap(root)
            env = os.environ.copy()
            env["FAKE_DISPLAY_MINIMAP_LOG"] = str(root / "cross_display.log")

            completed = self.run_tool(server, minimap, env)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            card = next(
                row
                for row in prepare_fixture.read_tsv(
                    server / "metadata/grt_used_contigs.tsv"
                )
                if row["contig_name"] == "s_tel_assigned"
            )
            self.assertEqual(card["original_assignment"], "cross_chr")
            self.assertEqual(card["placement_mode"], "cross_chr_grt_usage")
            self.assertEqual(card["target_chr"], "Chr01")
            self.assertEqual(card["ref_alignment_status"], "weak_hit")
            original = next(
                row
                for row in prepare_fixture.read_tsv(assignments_path)
                if row["dataset_name"] == "support"
                and row["seq_name"] == "s_tel_assigned"
            )
            self.assertEqual(original["assigned_chr_name"], "Chr02")
            validate_contract(server, SCHEMA)


if __name__ == "__main__":
    unittest.main()
