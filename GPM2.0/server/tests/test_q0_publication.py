from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from server.tests.test_q0_admission import EvidenceFixture, bridge_fixture, dna
from server.tests.test_grt_prepare_inputs import read_tsv, write_tsv
from server.tests.q0_test_support import seed_q0_evidence
from server.tools import lgz_prepare_inputs as producer
from server.tools.lgz_core.common import read_fasta, sha256_file
from server.tools.lgz_core.q0_publication import FREEZE, SELECTION, validate_prepared_q0
from server.tools.lgz_core.q0_sources import Q0EvidenceError

PROJECT = Path(__file__).resolve().parents[2]
TOOL = PROJECT / "server/tools/lgz_prepare_inputs.py"
SCHEMA = json.loads((PROJECT / "server/contracts/grt_precomputed_v2.json").read_text())


def complete_workspace(fixture, directory, *, unassign=()):
    root = fixture.workspace(directory)
    def write(name, rows):
        write_tsv(root / name, SCHEMA["tables"][name]["header"], rows)
    write("metadata/package.tsv", [{"workflow": "gpm_grt_precomputed_v2", "schema_version": "3",
        "package_mode": "fast", "sequence_layout": "partitioned", "preassigned_chr": "true",
        "self_alignment_scope": "chr_partition", "cross_alignment_scope": "chr_partition",
        "chr_assignment_min_coverage_percent": "60", "grt_precompute_enabled": "true", "recipe_locked": "true",
        "final_path_schema_version": "1", "reads_qc_enabled": "false"}])
    write("metadata/datasets.tsv", [{"dataset_name": name, "assembler": "controlled", "assembler_version": "1",
        "fasta_relpath": f"data/datasets/{name}.fa", "fai_relpath": f"data/datasets/{name}.fa.fai",
        "self_alignment_available": "true"} for name in sorted({s.dataset for s in fixture.sources})])
    write("metadata/reference.tsv", [{"reference_name": "ref", "species_name": "controlled", "assembly_label": "ref",
        "fasta_relpath": "data/reference/ref.fa", "fai_relpath": "data/reference/ref.fa.fai"}])
    assignments = []
    for source, hits in sorted(fixture.refs.items()):
        if source in unassign:
            continue
        for chromosome in sorted({h.target_name for h in hits}):
            relevant = [h for h in hits if h.target_name == chromosome]
            support = min(len(fixture.sources[source]), sum(h.query.length for h in relevant))
            assignments.append({"dataset_name": source.dataset, "seq_name": source.contig,
                "seq_length_bp": len(fixture.sources[source]), "assigned_chr_name": chromosome,
                "source_orientation": relevant[0].strand, "orientation_source": "ref_alignment", "support_bp": support,
                "support_percent": str(support * 100 / len(fixture.sources[source])),
                "anchor_start": min(h.target.start for h in relevant) + 1})
    write("metadata/chr_assignments.tsv", assignments)
    write("metadata/source_seq_locator.tsv", [{"dataset_name": source.dataset, "seq_name": source.contig,
        "fasta_relpath": f"data/datasets/{source.dataset}.fa"} for source in sorted(fixture.sources)])
    for fasta in (root / "data").rglob("*.fa"):
        # The fixture helper writes single-line records; retain a valid FAI.
        offset, entries = 0, []
        lines = fasta.read_bytes().splitlines(keepends=True)
        for header, sequence in zip(lines[::2], lines[1::2]):
            name = header[1:].strip().decode()
            entries.append(f"{name}\t{len(sequence.strip())}\t{offset + len(header)}\t{len(sequence.strip())}\t{len(sequence)}\n")
            offset += len(header) + len(sequence)
        Path(str(fasta) + ".fai").write_text("".join(entries))
    seed_q0_evidence(root)
    return root


def run_prepare(root, *, threads=1):
    return subprocess.run([sys.executable, str(TOOL), "--server-dir", str(root), "--threads", str(threads)],
                          capture_output=True, text=True)


class Q0PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_main_entry_publishes_cross_dataset_q0_not_first_ds(self):
        fixture, truth = bridge_fixture()
        root = complete_workspace(fixture, self.directory)
        completed = run_prepare(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(dict(read_fasta(root / "grt/q/q0.fa")), {"chr1": truth})
        selected = read_tsv(root / "metadata/grt_q_segments.tsv")
        self.assertEqual([r["dataset_name"] for r in selected], ["a", "c", "b"])
        evidence = read_tsv(root / "metadata/grt_evidence_registry.tsv")
        self.assertTrue(all(r["stage"] == "q0_construction" and r["raw_artifact_relpath"] == SELECTION for r in evidence))
        self.assertTrue(all(r["evidence_type"] == "q0_path_selection" for r in evidence))
        validate_prepared_q0(root)

    def test_partial_sources_remain_full_donor_context_with_separate_available_ranges(self):
        fixture, _ = bridge_fixture()
        root = complete_workspace(fixture, self.directory)
        completed = run_prepare(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        frozen = validate_prepared_q0(root)
        available = {r["source"]["contig"]: r["available"] for r in frozen["sources"]}
        self.assertEqual(available["a"], [{"start": 2000, "end": 2200}])
        self.assertEqual(available["c"], [{"start": 0, "end": 200}, {"start": 1000, "end": 1200}])
        sets = read_tsv(root / "metadata/grt_donor_sets.tsv")
        ordinary = next(row for row in sets if row["donor_kind"] == "ordinary")
        self.assertEqual(ordinary["member_count"], "3")
        members = [r for r in read_tsv(root / "metadata/grt_donor_members.tsv") if r["donor_set_id"] == ordinary["donor_set_id"]]
        records = dict(read_fasta(root / ordinary["fasta_relpath"]))
        for member in members:
            source = next(s for s in fixture.sources if s.dataset == member["dataset_name"])
            self.assertEqual(records[member["fasta_record_name"]], fixture.sources[source])
        roles = {r["contig_name"]: r for r in read_tsv(root / "metadata/grt_contig_roles.tsv")}
        self.assertEqual((roles["a"]["q_eligible"], roles["a"]["donor_eligible"]), ("true", "true"))

    def test_reordering_dataset_metadata_preserves_q0_source_choices(self):
        fixture, truth = bridge_fixture()
        root = complete_workspace(fixture, self.directory)
        self.assertEqual(run_prepare(root).returncode, 0)
        before = (root / "metadata/grt_q_segments.tsv").read_bytes()
        stale = root / "grt/stages/obsolete/result.txt"
        stale.parent.mkdir(parents=True)
        stale.write_text("obsolete generated result\n")
        stale_metadata = root / "metadata/grt_events.jsonl"
        stale_metadata.write_text("{}\n")
        rows = read_tsv(root / "metadata/datasets.tsv")
        write_tsv(root / "metadata/datasets.tsv", SCHEMA["tables"]["metadata/datasets.tsv"]["header"], list(reversed(rows)))
        seed_q0_evidence(root)
        completed = run_prepare(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(dict(read_fasta(root / "grt/q/q0.fa")), {"chr1": truth})
        self.assertEqual((root / "metadata/grt_q_segments.tsv").read_bytes(), before)
        self.assertEqual(read_tsv(root / "metadata/grt_recipe.tsv")[0]["primary_dataset"], "c")
        self.assertFalse(stale.exists())
        self.assertFalse(stale_metadata.exists())

    def test_original_n_gap_provenance_and_occupancy_are_frozen(self):
        fixture = EvidenceFixture()
        sequence = dna(1200) + "N" * 137 + dna(1500, 71)
        source = fixture.source("assembly", sequence)
        fixture.ref(source, (0, 1200), (0, 1200))
        root = complete_workspace(fixture, self.directory)
        completed = run_prepare(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(dict(read_fasta(root / "grt/q/q0.fa")), {"chr1": sequence})
        frozen = validate_prepared_q0(root)
        self.assertEqual(frozen["sources"][0]["occupied"], [{"start": 0, "end": len(sequence)}])
        self.assertEqual(frozen["sources"][0]["available"], [])
        decisions = json.loads((root / SELECTION).read_text())["construction"]
        join = decisions["searches"]["chr1"]["path"]["joins"][0]
        self.assertEqual(join["kind"], "input_assembly_gap")
        self.assertEqual(join["n_bp"], 137)

    def test_expanded_source_is_not_forged_into_an_original_assignment(self):
        fixture = EvidenceFixture({"chr1": 5000, "chr2": 5000})
        a, b = fixture.source("a", dna(1200)), fixture.source("b", dna(1400, 27))
        fixture.ref(a, (0, 1200), (0, 1200)); fixture.ref(b, (0, 1400), (0, 1400), chromosome="chr2")
        root = complete_workspace(fixture, self.directory, unassign={b})
        original = (root / "metadata/chr_assignments.tsv").read_bytes()
        completed = run_prepare(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        selected = next(r for r in read_tsv(root / "metadata/grt_q_segments.tsv") if r["dataset_name"] == "b")
        self.assertEqual(selected["source_card_key"], "b:b:chr2:grt_promoted")
        self.assertEqual((root / "metadata/chr_assignments.tsv").read_bytes(), original)
        validate_prepared_q0(root)

    def test_reverse_slice_and_no_reads_metadata_are_truthful(self):
        fixture, truth = bridge_fixture(reverse=True)
        root = complete_workspace(fixture, self.directory)
        completed = run_prepare(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(dict(read_fasta(root / "grt/q/q0.fa")), {"chr1": truth})
        source = next(r for r in read_tsv(root / "metadata/grt_q_segments.tsv") if r["contig_name"] == "c")
        self.assertEqual((source["orientation"], source["source_start"], source["source_end"]), ("-", "201", "1000"))
        self.assertTrue(all(row["qv"] == "" and row["reads_qc_pass"] == "not_run" for row in read_tsv(root / "metadata/grt_contig_quality.tsv")))

    def test_complete_cache_reuses_freeze_but_changed_availability_is_detected(self):
        fixture, _ = bridge_fixture()
        root = complete_workspace(fixture, self.directory)
        self.assertEqual(run_prepare(root).returncode, 0)
        stamp = (root / FREEZE).stat().st_mtime_ns
        completed = run_prepare(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("are current", completed.stdout)
        self.assertEqual((root / FREEZE).stat().st_mtime_ns, stamp)
        payload = json.loads((root / FREEZE).read_text())
        payload["sources"][0]["available"] = [{"start": 0, "end": payload["sources"][0]["length"]}]
        (root / FREEZE).write_text(json.dumps(payload))
        with self.assertRaisesRegex(Q0EvidenceError, "availability differs"):
            validate_prepared_q0(root)

    def test_corrupt_required_alignment_preserves_previous_q0_and_freeze(self):
        fixture, _ = bridge_fixture()
        root = complete_workspace(fixture, self.directory)
        self.assertEqual(run_prepare(root).returncode, 0)
        before = {name: (root / name).read_bytes() for name in (FREEZE, SELECTION, "grt/q/q0.fa")}
        (root / "runs/a_vs_ref/result.paf").write_text("corrupt\n")
        completed = run_prepare(root)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual({name: (root / name).read_bytes() for name in before}, before)

    def test_failed_prepublication_reconstruction_does_not_install_new_outputs(self):
        fixture, _ = bridge_fixture()
        root = complete_workspace(fixture, self.directory)
        self.assertEqual(run_prepare(root).returncode, 0)
        before = {name: (root / name).read_bytes() for name in (FREEZE, SELECTION, "grt/q/q0.fa")}
        args = argparse.Namespace(server_dir=root, reads=[], reads_qc="standard", meryl="meryl", merqury="merqury.sh",
                                  craq="craq", threads=2, memory_gb=80, kmer_size=21)
        real = producer.stage_selection
        def corrupt(*args, **kwargs):
            result = real(*args, **kwargs)
            with (args[1] / "grt/q/q0.fa").open("a") as handle:
                handle.write("A\n")
            return result
        with mock.patch.object(producer, "stage_selection", side_effect=corrupt), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, "cannot be reconstructed"):
                producer.prepare(args)
        self.assertEqual({name: (root / name).read_bytes() for name in before}, before)

    def test_step1_replays_new_q0_and_preserves_its_selection_evidence(self):
        fixture, truth = bridge_fixture()
        root = complete_workspace(fixture, self.directory)
        completed = run_prepare(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        frozen_before = (root / FREEZE).read_bytes()
        evidence_before = read_tsv(root / "metadata/grt_evidence_registry.tsv")
        completed = subprocess.run([sys.executable, str(PROJECT / "server/tools/lgz_step1.py"),
                                    "--server-dir", str(root), "--threads", "1"], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for version in ("q0r1", "q0f", "q1"):
            self.assertEqual(dict(read_fasta(root / f"grt/q/{version}.fa")), {"chr1": truth})
        after = [r for r in read_tsv(root / "metadata/grt_evidence_registry.tsv") if r["stage"] == "q0_construction"]
        self.assertEqual(after, evidence_before)
        self.assertEqual((root / FREEZE).read_bytes(), frozen_before)
        validate_prepared_q0(root)

    def test_old_package_version_is_not_a_strategy_fallback(self):
        fixture, _ = bridge_fixture()
        root = complete_workspace(fixture, self.directory)
        rows = read_tsv(root / "metadata/package.tsv"); rows[0]["schema_version"] = "2"
        write_tsv(root / "metadata/package.tsv", SCHEMA["tables"]["metadata/package.tsv"]["header"], rows)
        completed = run_prepare(root)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unsupported package", completed.stderr)
        self.assertFalse((root / "grt/q/q0.fa").exists())


if __name__ == "__main__":
    unittest.main()
