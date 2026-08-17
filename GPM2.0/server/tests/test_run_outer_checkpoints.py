#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
from server.tools.run_outer_checkpoints import OuterCheckpointManager


PAF_LINE = "query\t10\t0\t10\t+\ttarget\t12\t1\t11\t10\t10\t60\n"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class OuterCheckpointTests(unittest.TestCase):
    def make_server(self, root: Path) -> tuple[Path, Path]:
        server = root / "gpm_server"
        fake_bin = root / "bin"
        minimap2 = fake_bin / "minimap2"
        write(minimap2, "#!/usr/bin/env bash\necho minimap2-fixture\n")
        minimap2.chmod(0o755)

        write(server / "data/reference/ref.fa", ">target\nAAAAAAAAAAAA\n")
        write(server / "data/reference/ref.fa.fai", "target\t12\t8\t12\t13\n")
        write(server / "data/datasets/ds.fa", ">query\nAAAAAAAAAA\n")
        write(server / "data/datasets/ds.fa.fai", "query\t10\t7\t10\t11\n")
        write(
            server / "metadata/reference.tsv",
            "reference_name\tfasta_relpath\tfai_relpath\n"
            "ref\tdata/reference/ref.fa\tdata/reference/ref.fa.fai\n",
        )
        write(
            server / "metadata/datasets.tsv",
            "dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\n"
            "ds\tds\t\tdata/datasets/ds.fa\tdata/datasets/ds.fa.fai\ttrue\n",
        )
        write(
            server / "metadata/package.tsv",
            "schema_version\tchr_assignment_min_coverage_percent\tself_alignment_scope\n"
            "fixture\t70\tall\n",
        )
        write(
            server / "metadata/prepare_options.tsv",
            "key\tvalue\n"
            "alignment_engine\tminimap2\n"
            "threads\t8\n"
            "minimap_preset\tasm10\n"
            "chr_assignment_min_coverage_percent\t70\n"
            "skip_self\tfalse\n"
            "tel_enabled\tfalse\n"
            "cen_enabled\tfalse\n",
        )
        write(server / ".prepare_lib/tools/track_member_order.py", "# fixture\n")

        write(server / "runs/ds_vs_ref/command.sh", "#!/usr/bin/env bash\n# ref\n")
        write(server / "runs/ds_vs_ref/result.paf", PAF_LINE)
        write(server / "runs/ds_vs_ref/tool_version.txt", "minimap2-fixture\n")

        write(server / "assign_chr_groups.sh", "#!/usr/bin/env bash\n# assign\n")
        write(server / "metadata/chr_assignments.tsv", "dataset_name\tseq_name\nds\tquery\n")
        write(server / "metadata/track_member_orders.tsv", "track_id\tmember_id\nt\tm\n")
        write(
            server / "metadata/source_seq_locator.tsv",
            "dataset_name\tseq_name\tfasta_relpath\nds\tquery\tdata/partitions/chr/Chr1/ds.fa\n",
        )
        write(
            server / "metadata/source_seq_n_regions.tsv",
            "dataset_name\tseq_name\tstart_bp\tend_bp\tlength_bp\n",
        )
        write(
            server / "metadata/reference_chr_locator.tsv",
            "reference_chr_name\tfasta_relpath\nChr1\tdata/reference/chrs/Chr1.fa\n",
        )
        write(server / "data/reference/chrs/Chr1.fa", ">Chr1\nAAAAAAAAAAAA\n")
        write(server / "data/partitions/chr/Chr1/ds.fa", ">query\nAAAAAAAAAA\n")

        write(server / "runs/chr_Chr1/command.sh", "#!/usr/bin/env bash\nbash ./generated_command.sh\n")
        write(
            server / "runs/chr_Chr1/generated_command.sh",
            "#!/usr/bin/env bash\nbash ./ds_vs_self/command.sh\n",
        )
        write(server / "runs/chr_Chr1/datasets/ds.fa", ">query\nAAAAAAAAAA\n")
        write(server / "runs/chr_Chr1/ds_vs_self/command.sh", "#!/usr/bin/env bash\n# self\n")
        write(server / "runs/chr_Chr1/ds_vs_self/result.paf", PAF_LINE)
        return server, fake_bin

    def path_environment(self, fake_bin: Path) -> dict[str, str]:
        return {"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"}

    def write_grt_stage(self, server: Path, stage: str) -> dict[str, str]:
        output_relpath = f"grt/evidence/{stage}/result.txt"
        output = server / output_relpath
        write(output, f"{stage}\n")
        checkpoint_relpath = f"grt/checkpoints/{stage}.json"
        checkpoint = server / checkpoint_relpath
        write(
            checkpoint,
            json.dumps(
                {
                    "workflow": "gpm_grt_precomputed_v2",
                    "stage": stage,
                    "status": "success",
                    "input_fingerprint": f"input-{stage}",
                    "output_hashes": {
                        output_relpath: hashlib.sha256(output.read_bytes()).hexdigest()
                    },
                },
                sort_keys=True,
            )
            + "\n",
        )
        return {
            "stage": stage,
            "q_input_version": "q0",
            "q_input_sha256": "a" * 64,
            "q_output_version": "q1",
            "q_output_sha256": "b" * 64,
            "donor_set_id": "donor",
            "status": "success",
            "checkpoint_relpath": checkpoint_relpath,
            "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        }

    def test_reference_checkpoint_reuses_valid_empty_paf_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            server, fake_bin = self.make_server(Path(temporary))
            result_path = server / "runs/ds_vs_ref/result.paf"
            result_path.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, self.path_environment(fake_bin)):
                manager = OuterCheckpointManager(server)
                prepared = manager.prepare("ref:ds", "runs/ds_vs_ref/command.sh")
                self.assertIsNotNone(prepared)
                assert prepared is not None
                self.assertFalse(manager.validate(prepared)[0])
                checkpoint_path = manager.commit(prepared)
                self.assertTrue(manager.validate(prepared)[0])
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                result = next(
                    output
                    for output in checkpoint["outputs"]
                    if output["path"] == "runs/ds_vs_ref/result.paf"
                )
                self.assertEqual(result["size"], 0)

                result_path.write_text("malformed\n", encoding="utf-8")
                valid, reason = manager.validate(prepared)
                self.assertFalse(valid)
                self.assertIn("PAF line 1", reason)

    def test_reference_fingerprint_tracks_fasta_options_command_and_tool(self):
        mutations = {
            "source FASTA": lambda server, fake_bin: write(
                server / "data/datasets/ds.fa", ">query\nCCCCCCCCCC\n"
            ),
            "prepared threads": lambda server, fake_bin: write(
                server / "metadata/prepare_options.tsv",
                (server / "metadata/prepare_options.tsv")
                .read_text(encoding="utf-8")
                .replace("threads\t8", "threads\t16"),
            ),
            "command bytes": lambda server, fake_bin: write(
                server / "runs/ds_vs_ref/command.sh",
                "#!/usr/bin/env bash\n# changed\n",
            ),
            "tool binary": lambda server, fake_bin: write(
                fake_bin / "minimap2",
                "#!/usr/bin/env bash\necho changed-minimap2-fixture\n",
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                server, fake_bin = self.make_server(Path(temporary))
                with mock.patch.dict(os.environ, self.path_environment(fake_bin)):
                    manager = OuterCheckpointManager(server)
                    prepared = manager.prepare("ref:ds", "runs/ds_vs_ref/command.sh")
                    assert prepared is not None
                    manager.commit(prepared)
                    mutate(server, fake_bin)
                    changed_manager = OuterCheckpointManager(server)
                    changed = changed_manager.prepare("ref:ds", "runs/ds_vs_ref/command.sh")
                    assert changed is not None
                    self.assertNotEqual(prepared.input_fingerprint, changed.input_fingerprint)
                    self.assertFalse(changed_manager.validate(changed)[0])

    def test_assignment_and_chromosome_output_manifests_are_hash_validated(self):
        with tempfile.TemporaryDirectory() as temporary:
            server, fake_bin = self.make_server(Path(temporary))
            with mock.patch.dict(os.environ, self.path_environment(fake_bin)):
                manager = OuterCheckpointManager(server)
                write(server / "runs/chr_dataset_vs_ref/result.paf", PAF_LINE)
                assignment = manager.prepare("assign", "assign_chr_groups.sh")
                assert assignment is not None
                manager.commit(assignment)
                self.assertTrue(manager.validate(assignment)[0])

                assignment_output = server / "metadata/track_member_orders.tsv"
                assignment_output.write_text(
                    assignment_output.read_text(encoding="utf-8") + "t\tchanged\n",
                    encoding="utf-8",
                )
                self.assertFalse(manager.validate(assignment)[0])

                chromosome = manager.prepare("chr:Chr1", "runs/chr_Chr1/command.sh")
                assert chromosome is not None
                chromosome_result = server / "runs/chr_Chr1/ds_vs_self/result.paf"
                chromosome_result.write_text("", encoding="utf-8")
                manager.commit(chromosome)
                self.assertTrue(manager.validate(chromosome)[0])

                chromosome_result.write_text(PAF_LINE, encoding="utf-8")
                self.assertFalse(manager.validate(chromosome)[0])

    def test_grt_stage_mapping_requires_checkpoint_status_and_output_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            server, _fake_bin = self.make_server(Path(temporary))
            rows = [
                self.write_grt_stage(server, stage)
                for stage in ("step1_round1", "step1_filter", "step1_round2")
            ]
            fields = list(rows[0])
            write(
                server / "metadata/grt_stage_status.tsv",
                "\t".join(fields)
                + "\n"
                + "".join("\t".join(row[field] for field in fields) + "\n" for row in rows),
            )
            manager = OuterCheckpointManager(server)
            valid, reason = manager.validate_grt_unit("grt_step1")
            self.assertTrue(valid, reason)

            (server / "grt/evidence/step1_filter/result.txt").write_text(
                "corrupt\n", encoding="utf-8"
            )
            valid, reason = manager.validate_grt_unit("grt_step1")
            self.assertFalse(valid)
            self.assertIn("output hash changed", reason)

    def test_evidence_and_package_completion_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            server, _fake_bin = self.make_server(Path(temporary))
            summary = {
                "workflow": "gpm_grt_precomputed_v2",
                "schema_version": "2",
                "q0_sha256": "a" * 64,
                "q4_sha256": "b" * 64,
            }
            write(server / "metadata/grt_contract_summary.json", json.dumps(summary) + "\n")
            write(server / "metadata/grt_used_contigs.tsv", "source_card_key\n")
            write(server / "metadata/grt_final_path.json", "{}\n")
            write(server / "grt/q/q4.fa", ">Chr1\nA\n")
            manager = OuterCheckpointManager(server)
            with mock.patch(
                "server.tools.run_outer_checkpoints.validate_contract",
                return_value=summary,
            ):
                self.assertTrue(manager.validate_evidence()[0])
                recorded = {**summary, "q4_sha256": "c" * 64}
                write(
                    server / "metadata/grt_contract_summary.json",
                    json.dumps(recorded) + "\n",
                )
                self.assertFalse(manager.validate_evidence()[0])

            self.assertFalse(manager.validate_package("full")[0])
            write(server.parent / f"{server.name}.zip", "archive\n")
            self.assertTrue(manager.validate_package("full")[0])
            write(server.parent / f"{server.name}.no_fasta.zip", "")
            self.assertFalse(manager.validate_package("light")[0])


if __name__ == "__main__":
    unittest.main()
