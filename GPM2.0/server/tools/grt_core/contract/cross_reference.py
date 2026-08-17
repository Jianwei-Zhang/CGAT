from pathlib import Path

from .artifacts import *
from .errors import *
from .schema import *
from .tables import *
def validate_interval(start_value, end_value, label):
    start = parse_int(start_value, f"{label}.start", 1)
    end = parse_int(end_value, f"{label}.end", 1)
    if end < start:
        fail("INVALID_COORDINATE", f"{label} must satisfy start <= end")
    return start, end

def source_catalog(bundle_root, locator_rows):
    catalog = {}
    fasta_cache = {}
    for row_number, row in enumerate(locator_rows, start=2):
        dataset = (row["dataset_name"] or "").strip()
        contig = (row["seq_name"] or "").strip()
        if not dataset or not contig:
            fail("INVALID_VALUE", f"metadata/source_seq_locator.tsv:{row_number} has empty source identity")
        key = (dataset, contig)
        if key in catalog:
            fail("DUPLICATE_ID", f"duplicate source locator for {dataset}:{contig}")
        relpath = row["fasta_relpath"]
        path = bundle_path(bundle_root, relpath, f"source locator {dataset}:{contig}")
        if relpath not in fasta_cache:
            fasta_cache[relpath] = read_fasta(path, relpath)
        if contig not in fasta_cache[relpath]:
            fail("BROKEN_REFERENCE", f"source locator {dataset}:{contig} is absent from {relpath}")
        catalog[key] = fasta_cache[relpath][contig]
    return catalog
