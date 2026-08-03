import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "track_member_order.py"
SPEC = importlib.util.spec_from_file_location("track_member_order", MODULE_PATH)
TRACK_MEMBER_ORDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRACK_MEMBER_ORDER)


def load_tool(name):
    path = Path(__file__).parents[1] / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ADD_DATASET_PACKAGE = load_tool("add_dataset_package")
ADD_CTG_PACKAGE = load_tool("add_ctg_package")


ASSIGNMENT_FIELDS = [
    "dataset_name",
    "seq_name",
    "seq_length_bp",
    "assigned_chr_name",
    "support_bp",
    "support_percent",
    "anchor_start",
]
TRACK_MEMBER_FIELDS = [
    "member_dataset",
    "member_ctg",
    "target_chr",
    "target_track",
    "member_role",
    "created_at",
]


def write_tsv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_tsv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def assignment(dataset, ctg, anchor):
    return {
        "dataset_name": dataset,
        "seq_name": ctg,
        "seq_length_bp": "100",
        "assigned_chr_name": "chr1",
        "support_bp": "100",
        "support_percent": "100.000",
        "anchor_start": str(anchor),
    }


class TrackMemberOrderTests(unittest.TestCase):
    def test_sorts_by_anchor_and_preserves_fasta_order_for_ties(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            server_dir = Path(temporary_dir)
            write_tsv(
                server_dir / "metadata" / "chr_assignments.tsv",
                ASSIGNMENT_FIELDS,
                [
                    assignment("ds_a", "ctg_b", 10),
                    assignment("ds_a", "ctg_a", 10),
                    assignment("ds_a", "ctg_c", 5),
                ],
            )

            output_path, rows = TRACK_MEMBER_ORDER.build_member_rows(server_dir)
            TRACK_MEMBER_ORDER.write_atomic_tsv(output_path, rows)

            self.assertEqual(
                [(row["member_ctg"], row["member_order"]) for row in rows],
                [("ctg_c", 1), ("ctg_b", 2), ("ctg_a", 3)],
            )
            self.assertEqual(output_path.read_bytes().count(b"\r\n"), 0)

    def test_sorts_signed_anchor_estimates(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            server_dir = Path(temporary_dir)
            write_tsv(
                server_dir / "metadata" / "chr_assignments.tsv",
                ASSIGNMENT_FIELDS,
                [
                    assignment("ds_a", "ctg_positive", 10),
                    assignment("ds_a", "ctg_zero", 0),
                    assignment("ds_a", "ctg_negative", -5),
                ],
            )

            _output_path, rows = TRACK_MEMBER_ORDER.build_member_rows(server_dir)

            self.assertEqual(
                [(row["member_ctg"], row["member_order"]) for row in rows],
                [
                    ("ctg_negative", 1),
                    ("ctg_zero", 2),
                    ("ctg_positive", 3),
                ],
            )

    def test_equal_anchor_derived_member_follows_existing_authoritative_order(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            server_dir = Path(temporary_dir)
            metadata_dir = server_dir / "metadata"
            write_tsv(
                metadata_dir / "chr_assignments.tsv",
                ASSIGNMENT_FIELDS,
                [
                    assignment("ds_a", "ctg_b", 10),
                    assignment("ds_a", "ctg_a", 10),
                    assignment("derived_ctg", "gap_filled", 10),
                ],
            )
            write_tsv(
                metadata_dir / "track_members.tsv",
                TRACK_MEMBER_FIELDS,
                [
                    {
                        "member_dataset": "derived_ctg",
                        "member_ctg": "gap_filled",
                        "target_chr": "chr1",
                        "target_track": "ds_a",
                        "member_role": "derived",
                        "created_at": "1",
                    }
                ],
            )
            write_tsv(
                metadata_dir / "track_member_orders.tsv",
                TRACK_MEMBER_ORDER.FIELDNAMES,
                [
                    {
                        "target_track": "ds_a",
                        "target_chr": "chr1",
                        "member_dataset": "ds_a",
                        "member_ctg": "ctg_a",
                        "member_order": "1",
                    },
                    {
                        "target_track": "ds_a",
                        "target_chr": "chr1",
                        "member_dataset": "ds_a",
                        "member_ctg": "ctg_b",
                        "member_order": "2",
                    },
                ],
            )

            _output_path, rows = TRACK_MEMBER_ORDER.build_member_rows(server_dir)

            self.assertEqual(
                [
                    (row["member_dataset"], row["member_ctg"], row["member_order"])
                    for row in rows
                ],
                [
                    ("ds_a", "ctg_a", 1),
                    ("ds_a", "ctg_b", 2),
                    ("derived_ctg", "gap_filled", 3),
                ],
            )

    def test_add_dataset_package_contains_only_new_dataset_order_groups(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server_dir = root / "gpm_server"
            package_dir = root / "package"
            metadata_dir = server_dir / "metadata"
            (package_dir / "add_package").mkdir(parents=True)
            write_tsv(
                metadata_dir / "reference.tsv",
                ["reference_name"],
                [{"reference_name": "ref"}],
            )
            write_tsv(
                metadata_dir / "datasets.tsv",
                [
                    "dataset_name",
                    "assembler",
                    "assembler_version",
                    "fasta_relpath",
                    "fai_relpath",
                    "self_alignment_available",
                ],
                [
                    {
                        "dataset_name": "ds_new",
                        "assembler": "test",
                        "assembler_version": "",
                        "fasta_relpath": "data/datasets/ds_new.fa",
                        "fai_relpath": "data/datasets/ds_new.fa.fai",
                        "self_alignment_available": "true",
                    }
                ],
            )
            write_tsv(
                metadata_dir / "chr_assignments.tsv",
                ASSIGNMENT_FIELDS,
                [assignment("ds_new", "new_a", 1)],
            )
            write_tsv(
                metadata_dir / "track_member_orders.tsv",
                TRACK_MEMBER_ORDER.FIELDNAMES,
                [
                    {
                        "target_track": "ds_old",
                        "target_chr": "chr1",
                        "member_dataset": "ds_old",
                        "member_ctg": "old_a",
                        "member_order": "1",
                    },
                    {
                        "target_track": "ds_new",
                        "target_chr": "chr1",
                        "member_dataset": "ds_new",
                        "member_ctg": "new_a",
                        "member_order": "1",
                    },
                ],
            )
            write_tsv(
                metadata_dir / "source_seq_locator.tsv",
                ["dataset_name", "seq_name", "fasta_relpath"],
                [
                    {
                        "dataset_name": "ds_new",
                        "seq_name": "new_a",
                        "fasta_relpath": "data/datasets/ds_new.fa",
                    }
                ],
            )
            write_tsv(
                metadata_dir / "source_seq_n_regions.tsv",
                ["dataset_name", "seq_name", "start_bp", "end_bp", "length_bp"],
                [],
            )
            fasta_path = server_dir / "data" / "datasets" / "ds_new.fa"
            fasta_path.parent.mkdir(parents=True)
            fasta_path.write_text(">new_a\nA\n", encoding="utf-8")
            fasta_path.with_suffix(".fa.fai").write_text("new_a\t1\t0\t1\t2\n", encoding="utf-8")

            ADD_DATASET_PACKAGE.main(
                [
                    "add_dataset_package.py",
                    str(server_dir),
                    str(package_dir),
                    "ds_new",
                    "60",
                    "minimap2",
                    "asm10",
                    "blastn",
                    "1e-10",
                    "no",
                    "asm20",
                    "19",
                    "0.9998",
                    "false",
                    "false",
                    "false",
                ]
            )

            rows = read_tsv(package_dir / "gpm_server" / "metadata" / "track_member_orders.tsv")
            self.assertEqual(
                [(row["target_track"], row["member_ctg"]) for row in rows],
                [("ds_new", "new_a")],
            )

    def test_add_ctg_package_contains_full_affected_group_order_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            server_dir = root / "gpm_server"
            package_dir = root / "package"
            metadata_dir = server_dir / "metadata"
            (package_dir / "add_ctg").mkdir(parents=True)
            manifest_path = metadata_dir / "add_ctg_manifests" / "gap.tsv"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                "package_type\tadd_ctg\nctg_name\tgap\ntarget_chr\tchr1\ntarget_track\tds_a\n"
                "skip_self\ttrue\ncontains_fasta\ttrue\n",
                encoding="utf-8",
            )
            write_tsv(
                metadata_dir / "datasets.tsv",
                [
                    "dataset_name",
                    "assembler",
                    "assembler_version",
                    "fasta_relpath",
                    "fai_relpath",
                    "self_alignment_available",
                ],
                [
                    {
                        "dataset_name": "derived_ctg",
                        "assembler": "derived_ctg",
                        "assembler_version": "",
                        "fasta_relpath": "data/datasets/derived_ctg.fa",
                        "fai_relpath": "data/datasets/derived_ctg.fa.fai",
                        "self_alignment_available": "false",
                    }
                ],
            )
            write_tsv(
                metadata_dir / "derived_ctgs.tsv",
                [
                    "derived_dataset",
                    "ctg_name",
                    "source",
                    "source_fasta_name",
                    "source_fasta_sha256",
                    "created_at",
                ],
                [
                    {
                        "derived_dataset": "derived_ctg",
                        "ctg_name": "gap",
                        "source": "test",
                        "source_fasta_name": "gap.fa",
                        "source_fasta_sha256": "sha",
                        "created_at": "1",
                    }
                ],
            )
            write_tsv(
                metadata_dir / "track_members.tsv",
                TRACK_MEMBER_FIELDS,
                [
                    {
                        "member_dataset": "derived_ctg",
                        "member_ctg": "gap",
                        "target_chr": "chr1",
                        "target_track": "ds_a",
                        "member_role": "derived",
                        "created_at": "1",
                    }
                ],
            )
            write_tsv(
                metadata_dir / "chr_assignments.tsv",
                ASSIGNMENT_FIELDS,
                [assignment("derived_ctg", "gap", 2)],
            )
            write_tsv(
                metadata_dir / "track_member_orders.tsv",
                TRACK_MEMBER_ORDER.FIELDNAMES,
                [
                    {
                        "target_track": "ds_a",
                        "target_chr": "chr1",
                        "member_dataset": "ds_a",
                        "member_ctg": "old",
                        "member_order": "1",
                    },
                    {
                        "target_track": "ds_a",
                        "target_chr": "chr1",
                        "member_dataset": "derived_ctg",
                        "member_ctg": "gap",
                        "member_order": "2",
                    },
                    {
                        "target_track": "ds_b",
                        "target_chr": "chr1",
                        "member_dataset": "ds_b",
                        "member_ctg": "other",
                        "member_order": "1",
                    },
                ],
            )
            write_tsv(
                metadata_dir / "source_seq_locator.tsv",
                ["dataset_name", "seq_name", "fasta_relpath"],
                [
                    {
                        "dataset_name": "derived_ctg",
                        "seq_name": "gap",
                        "fasta_relpath": "data/derived_ctgs/gap.fa",
                    }
                ],
            )
            write_tsv(
                metadata_dir / "source_seq_n_regions.tsv",
                ["dataset_name", "seq_name", "start_bp", "end_bp", "length_bp"],
                [],
            )
            derived_fasta = server_dir / "data" / "derived_ctgs" / "gap.fa"
            derived_fasta.parent.mkdir(parents=True)
            derived_fasta.write_text(">gap\nA\n", encoding="utf-8")
            derived_fasta.with_suffix(".fa.fai").write_text("gap\t1\t0\t1\t2\n", encoding="utf-8")
            ref_run = server_dir / "runs" / "add_ctg" / "gap_vs_ref"
            ref_run.mkdir(parents=True)
            (ref_run / "result.paf").write_text("", encoding="utf-8")

            ADD_CTG_PACKAGE.main(
                ["add_ctg_package.py", str(server_dir), str(package_dir), "gap"]
            )

            rows = read_tsv(package_dir / "gpm_server" / "metadata" / "track_member_orders.tsv")
            self.assertEqual(
                [(row["member_dataset"], row["member_ctg"]) for row in rows],
                [("ds_a", "old"), ("derived_ctg", "gap")],
            )


if __name__ == "__main__":
    unittest.main()
