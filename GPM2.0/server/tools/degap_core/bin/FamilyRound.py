"""Single-attempt adapter reusing DEGAP read selection and local assembly.

Read preparation/index handles are shared; mutable round state belongs to one
family. Completed reads/assembly stages have content-verified receipts. An
interrupted, uncommitted stage is archived rather than mistaken for completion.
"""
import copy
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

from ExtensionFamilies import AttemptResult, atomic_json, fingerprint, read_json
from FamilyOverlap import file_hash

NORMAL_READ_STOPS = {
    "kmerFilterNoReads", "noExtensionReadsFoundAtMinimumThreshold",
    "noExtensionReadsFoundAfterParameterRelaxation",
}


def _state(obj, excluded=()):
    result = {key: value for key, value in vars(obj).items() if key not in excluded}
    # No pickle/object resurrection: stage state must be plain diagnostic data.
    return json.loads(json.dumps(result, allow_nan=False))


class SingleRound:
    def __init__(self, base, *, context, shared_cache=None):
        self.base = base
        self.context = context
        self.shared_cache = Path(shared_cache) if shared_cache is not None else None

    def _elongation(self, family, directory):
        base = copy.copy(self.base)
        base.family_mode = True
        base.name = getattr(base, "name", "extension")
        base.family_mapping_dir = str(Path(directory).parent / "mapping")
        base.flag = "left" if family.direction == "rightward" else "right"
        base.tag = base.flag
        base.initialSeq = family.versions[0].path
        # Intentionally no fixed terminal. OutputSequence defers family closure.
        base.terminalSeq = None
        input_path = family.current.path
        if family.anchor_backoff:
            from FamilyOverlap import read_sequence
            seq = read_sequence(input_path)
            backoff = min(family.anchor_backoff, max(0, len(seq)-1000))
            work = Path(directory)
            work.mkdir(parents=True, exist_ok=True)
            trimmed = seq[:-backoff] if family.direction == "rightward" else seq[backoff:]
            path = work/"anchor-backoff.fa"
            path.write_text(">anchor_backoff\n"+trimmed+"\n")
            input_path = str(path)
        return SimpleNamespace(
            base=base, roundDir=str(directory), roundNum=family.attempts,
            roundInputSeq=input_path, usedReads=list(family.used_reads),
            lastRoundUsedReads=list(family.last_reads), extensionLen=family.added_bases,
            endSignal=False,
        )

    def _stage(self, root, name, identity, factory):
        directory = root / name
        receipt_path = directory / "stage.json"
        if receipt_path.exists():
            receipt = read_json(receipt_path)
            if receipt.get("identity") != identity:
                raise ValueError(f"Stage inputs changed: {receipt_path}")
            if receipt.get("state_sha256") != fingerprint(receipt["state"]):
                raise ValueError(f"Stage metadata changed: {receipt_path}")
            for relative, digest in receipt["files"].items():
                path = directory / relative
                if not path.is_file() or file_hash(path) != digest:
                    raise ValueError(f"Completed round artifact changed: {path}")
            return receipt["state"]
        if directory.exists():
            # A file's existence is not proof that an interrupted tool finished.
            directory.rename(root / (name + ".incomplete." + uuid.uuid4().hex))
        directory.mkdir(parents=True)
        state = factory(directory)
        # Only persist closed/completed stage outputs; include BAM/GFA/FASTA and
        # evidence so recovery cannot silently accept a truncated alignment.
        files = {str(p.relative_to(directory)): file_hash(p)
                 for p in sorted(directory.rglob("*")) if p.is_file()}
        atomic_json(receipt_path, {"identity": identity, "state": state,
                                  "state_sha256": fingerprint(state), "files": files})
        return state

    def __call__(self, family, directory):
        result = self._call(family, directory)
        if (getattr(self.base, "allow_terminal_backoff", False) and family.current.number == 0
                and not family.anchor_backoff and family.current.length > 3000
                and result.stop_reason in NORMAL_READ_STOPS.union({"no_extension_contigs", "no_growth", "no_new_extension_reads"})):
            # This is a separate scheduler attempt, never hidden extra assembly.
            return AttemptResult(retry_reason="terminal_anchor_backoff")
        if family.anchor_backoff and result.sequence_path:
            from ExtensionFamilies import sequence_identity
            if sequence_identity(result.sequence_path)[2] <= family.current.length:
                return AttemptResult(stop_reason="anchor_backoff_no_net_growth")
        return result

    def _call(self, family, directory):
        if self.shared_cache is None:
            return self._execute(family, Path(directory))
        # Opposite endpoints do not affect a single extension attempt. Reuse its
        # work across endpoint searches, but keep each search's budget independent.
        identity = fingerprint({"context": self.context, "input_sha256": family.current.sha256,
                                "direction": family.direction, "version": family.current.number,
                                "attempt": family.attempts, "used_reads": sorted(family.used_reads),
                                "last_reads": sorted(family.last_reads)})
        cache = self.shared_cache / identity
        cache.mkdir(parents=True, exist_ok=True)
        import fcntl
        with (cache / "stage.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            atomic_json(Path(directory) / "shared-stage.json", {"identity": identity, "directory": str(cache.resolve())})
            return self._execute(family, cache, identity=identity)

    def _execute(self, family, directory, identity=None):
        from GapFillerClass import InputSequence, OutputSequence
        from FindExtensionReads import FindExtensionReads
        from FindExtensionContigs import FindExtensionContigs

        directory = Path(directory)
        identity = identity or fingerprint({"context": self.context, "family": asdict(family)})

        def find_reads(work):
            elongation = self._elongation(family, work)
            seed = InputSequence(elongation)
            reads = FindExtensionReads(seed, list(family.last_reads), list(family.used_reads),
                                       elongation.base.kmer_size, elongation.base.kmer_num,
                                       out=elongation.base.out)
            note = reads.note
            if note and note not in NORMAL_READ_STOPS:
                raise RuntimeError(f"Read selection failed, not a normal family stop: {note}")
            return _state(reads, ("roundInput",))

        reads_state = self._stage(directory, "reads", identity, find_reads)
        mixed = reads_state.get("mixed_mode_status")
        can_assemble = not reads_state["note"] or mixed in ("both_success", "hifi_only", "ont_only")
        if not can_assemble:
            return AttemptResult(stop_reason=reads_state["note"] or "no_extension_reads")

        def assemble(work):
            elongation = self._elongation(family, work)
            seed = InputSequence(elongation)
            reads = SimpleNamespace(**reads_state)
            reads.roundInput = seed
            def cache_assembler(contigs):
                def execute(assembler_work):
                    previous = elongation.roundDir
                    elongation.roundDir = str(assembler_work)
                    try:
                        contigs.hifiasm()
                        return _state(contigs, ("extensionReads",))
                    finally:
                        elongation.roundDir = previous
                saved = self._stage(directory, "assembler", identity, execute)
                vars(contigs).update(saved)
            elongation.base.family_assembler = cache_assembler
            contigs = FindExtensionContigs(reads, elongation.base.data_type,
                                           getattr(elongation.base, "ont_reads", None),
                                           getattr(elongation.base, "original_reads_info", None))
            note = contigs.selectContigNote
            if "No extension contigs or reads found" in note:
                return {"stop_reason": "no_extension_contigs", "contigs": _state(contigs, ("extensionReads",))}
            output = OutputSequence(contigs, elongation)
            result = {
                "sequence_path": output.outputSequence,
                "used_reads": list(output.ExtensionUsedReads),
                "contigs": _state(contigs, ("extensionReads",)),
                "output": _state(output, ("extensionContigs", "Elongation")),
            }
            new_reads = set(output.ExtensionUsedReads).difference(family.used_reads)
            last_reads = set(output.ExtensionUsedReads).intersection(family.last_reads)
            # Preserve the original loop prevention rule, but within this family.
            if not new_reads and not last_reads:
                result["stop_reason"] = "no_new_extension_reads"
            elif not new_reads and contigs.extensionLength == 0:
                result["stop_reason"] = "no_growth"
            return result

        assembled = self._stage(directory, "assembly", identity, assemble)
        return AttemptResult(assembled.get("sequence_path"), tuple(assembled.get("used_reads", ())),
                             assembled.get("stop_reason"))
