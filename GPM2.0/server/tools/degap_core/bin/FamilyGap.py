"""Public two-boundary gap filling through the shared family engine."""
import copy
from pathlib import Path
import shutil
from types import SimpleNamespace

from ExtensionFamilies import FamilySearch
from FamilyOverlap import MummerOverlap
from FamilyResult import publish_search
from FamilyRound import SingleRound
from FamilyTools import content_hash


def reject_legacy_output(directory):
    root = Path(directory)
    if not (root / "families.json").exists() and any(
            (root / name).exists() for name in ("checkpoint.info", "process", "process.log")):
        raise ValueError("Legacy single-sided output detected; use a new output directory. Old histories are not imported.")


def prepare_context(base, overlap_contract):
    """Identify actual read inputs once and pin their resolution for all families."""
    from FindExtensionReads import FindExtensionReads
    finder = FindExtensionReads.__new__(FindExtensionReads)
    finder.roundInput = SimpleNamespace(elongation=SimpleNamespace(base=base, roundDir=base.out))
    platforms = ["hifi", "ont"] if base.data_type == "mixed" else [base.data_type]
    files = {}
    reads_info = dict(getattr(base, "original_reads_info", None) or {})
    reads_info.update(getattr(base, "reads_info", None) or {})
    for platform in platforms:
        path = Path(finder._get_reads_path(platform)).resolve()
        files[str(path)] = content_hash(path)
        reads_info["working_" + platform] = str(path)
    base.reads_info = reads_info
    from PreparedReads import sources
    if "hifi" in platforms:
        for source in sources(reads_info.get("original_hifi") or getattr(base, "original_hifi_reads", None)):
            files[source["path"]] = source["sha256"]
    # Quality changes must invalidate assembly/checkpoint reuse even when the
    # normalized FASTA is unchanged. Build the shared quality index lazily.
    if "ont" in platforms:
        from ONTAssemblyReads import original_ont, source_contract
        base.ont_quality_sources = source_contract(original_ont(base))
        base.ont_quality_cache = str(Path(base.out).resolve() / "ont-quality-cache")
        for source in base.ont_quality_sources:
            files[source["path"]] = source["sha256"]
    if getattr(base, "kmer_filter", False):
        for platform in platforms:
            part_directory = Path(base.out) / (platform + "_reads_part")
            parts = sorted(part_directory.glob("*.fa*"))
            if not parts:
                raise FileNotFoundError(f"Missing prepared reads parts: {part_directory}")
            for part in parts:
                files[str(part.resolve())] = content_hash(part)
    for filename in ("HiFi.reads.stat", "ONT.reads.stat"):
        path = Path(base.out) / filename
        if path.exists():
            files[str(path.resolve())] = content_hash(path)
    tools = {}
    names = ["minimap2", "samtools", "hifiasm"]
    if getattr(base, "kmer_filter", False):
        names += ["seqkit", "parallel", "rg"]
    for name in names:
        path = shutil.which(name)
        # Initial direct closure needs no assembly tools. If extension is needed,
        # checked execution reports a missing tool rather than a biological stop.
        tools[name] = {"path": path, "sha256": content_hash(path) if path else None}
    code_files = ["FamilyGap.py", "ExtensionFamilies.py", "FamilyOverlap.py", "FamilyRound.py", "FamilyTools.py",
                  "FindExtensionReads.py", "FindExtensionContigs.py", "GapFillerClass.py", "ONTAssemblyReads.py", "JunctionRepair.py",
                  "PreparedReads.py", "FamilyResult.py", "FamilyReport.py", "FamilyReportStyle.py",
                  "JunctionReport.py", "ReportStyle.py"]
    return {
        "driver": "family-gap-v1", "files": files, "tools": tools, "overlap": overlap_contract,
        "code": {name: content_hash(Path(__file__).parent / name) for name in code_files},
        "parameters": {name: getattr(base, name, None) for name in
                       ("data_type", "seedLen", "hifiSeedLen", "ontSeedLen", "edge", "thread",
                        "kmer_size", "kmer_num", "kmer_filter", "filterDepthHifi", "filterDepthOnt", "allow_terminal_backoff")},
    }


def run_gap(base):
    reject_legacy_output(base.out)
    local = copy.copy(base)
    local.out = str(Path(base.out).resolve())
    local.thread = int(local.thread)
    local.allow_terminal_backoff = True
    overlap = MummerOverlap(Path(local.out) / "family-overlaps", int(local.edge))
    context = prepare_context(local, overlap.contract)
    seeds = [("L", "rightward", local.seqleft), ("R", "leftward", local.seqright)]
    overlap.configure_boundaries(local, seeds)
    search = FamilySearch(local.out, seeds,
                          primary="L", context=context,
                          max_rounds=getattr(local, "MaximumExtensionRound", None),
                          max_length=getattr(local, "MaximunExtensionLength", None))
    search.run(SingleRound(local, context=context), overlap)
    result = publish_search(search)
    return SimpleNamespace(search=search, result=result,
                           finalSeq=str(Path(local.out) / result["final_sequence"]),
                           roundNum=search.total_rounds, extensionLen=search.total_length,
                           endSignal=True, status=search.status)
