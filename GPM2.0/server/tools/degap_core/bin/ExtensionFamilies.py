"""Persistent, tool-independent extension-family scheduler.

Adapters supply one extension attempt and eligible overlap candidates; the
scheduler owns budgets, history, deterministic selection and recovery.
"""
from dataclasses import asdict, dataclass, field
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import List, Optional, Tuple

SCHEMA_VERSION = 1


def atomic_json(path, value):
    """Publish a complete receipt without truncating the previous checkpoint."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    try:
        with open(path) as stream:
            return json.load(stream)
    except (OSError, ValueError) as error:
        raise ValueError(f"Invalid family receipt {path}: {error}") from error


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def sequence_identity(path):
    """Hash exact FASTA bytes and require exactly one nonempty sequence."""
    path = Path(path).resolve()
    digest = hashlib.sha256()
    headers = length = 0
    with path.open("rb") as stream:
        for line in stream:
            digest.update(line)
            text = line.strip()
            if not text:
                continue
            if text.startswith(b">"):
                headers += 1
            else:
                if headers != 1 or any(chr(c).isspace() for c in text):
                    raise ValueError(f"Invalid single-record FASTA: {path}")
                length += len(text)
    if headers != 1 or length == 0:
        raise ValueError(f"Expected one nonempty FASTA record: {path}")
    return str(path), digest.hexdigest(), length


@dataclass(frozen=True)
class Version:
    family: str
    number: int
    path: str
    sha256: str
    length: int

    @classmethod
    def capture(cls, family, number, path):
        path, digest, length = sequence_identity(path)
        return cls(family, number, path, digest, length)

    def verify(self):
        if sequence_identity(self.path) != (self.path, self.sha256, self.length):
            raise ValueError(f"Family sequence changed: {self.family}/{self.number}: {self.path}")


@dataclass
class Family:
    key: str
    direction: str  # rightward/leftward, NOT the old CLI --flag
    versions: List[Version]
    attempts: int = 0
    added_bases: int = 0
    used_reads: List[str] = field(default_factory=list)
    last_reads: List[str] = field(default_factory=list)
    stop_reason: Optional[str] = None
    anchor_backoff: int = 0

    @property
    def current(self):
        return self.versions[-1]


@dataclass(frozen=True)
class AttemptResult:
    """Normal result; tool faults must raise instead.

    terminal_reason is for a single-ended objective such as a telomere, never a
    substitute for overlap evidence in a paired search. A positive extension may
    stop its family but must still participate in closure checks.
    """
    sequence_path: Optional[str] = None
    used_reads: Tuple[str, ...] = ()
    stop_reason: Optional[str] = None
    terminal_reason: Optional[str] = None
    retry_reason: Optional[str] = None


@dataclass(frozen=True)
class Connection:
    """Eligible overlap, full-sequence coordinates, zero-based/half-open.

    The alignment adapter applies biological eligibility before returning this.
    """
    left_family: str
    left_version: int
    right_family: str
    right_version: int
    identity: float
    overlap: int
    overhang: int
    left_start: int
    left_end: int
    right_start: int
    right_end: int
    evidence: Optional[dict] = None

    def rank(self, order):
        return (-self.identity, -self.overlap, self.overhang,
                order[self.left_family], self.left_version,
                order[self.right_family], self.right_version,
                self.left_start, self.left_end, self.right_start, self.right_end)


class FamilySearch:
    """One primary endpoint versus zero or more candidate endpoint families.

    Schedule: A,B,A,C,A,D,...; stopped families are skipped. With no peers, the
    adapter owns the single-ended success condition. `context` must identify all
    adapter inputs/settings, including their content and tool identities.
    """

    def __init__(self, directory, seeds, *, primary, context,
                 max_rounds=None, max_length=None):
        self.directory = Path(directory).resolve()
        self.checkpoint = self.directory / "families.json"
        for name, limit in (("max_rounds", max_rounds), ("max_length", max_length)):
            if limit is not None and (type(limit) is not int or limit < 0):
                raise ValueError(f"{name} must be a nonnegative integer or None")
        if not seeds or len({s[0] for s in seeds}) != len(seeds):
            raise ValueError("Family keys must be nonempty and unique")
        families = []
        for key, direction, path in seeds:
            if not key or direction not in ("leftward", "rightward"):
                raise ValueError("Each family needs an identity and an extension direction")
            families.append(Family(key, direction, [Version.capture(key, 0, path)]))
        self.order = {f.key: i for i, f in enumerate(families)}
        if primary not in self.order:
            raise ValueError("Primary family is missing")
        direction = families[self.order[primary]].direction
        if any(f.key != primary and f.direction == direction for f in families):
            raise ValueError("Peers must face the primary in normalized orientation")
        self.primary = primary
        peers = [f.key for f in families if f.key != primary]
        self.schedule = [key for peer in peers for key in (primary, peer)] or [primary]
        self.max_rounds = max_rounds
        self.max_length = max_length
        self.contract = {
            "schema": SCHEMA_VERSION, "primary": primary,
            "seeds": [asdict(f) for f in families], "context": context,
            "max_rounds": max_rounds, "max_length": max_length,
        }
        # Normalize tuples etc. to their persistent JSON representation.
        self.contract = json.loads(json.dumps(self.contract, allow_nan=False))
        self.contract_id = fingerprint(self.contract)
        self.families = {f.key: f for f in families}
        self.cursor = 0
        self.pending = None
        self.checked = {}
        self.status = "running"
        self.winner = None
        self.completed_attempts = 0
        if not self.checkpoint.exists() and (
                (self.directory / "checkpoint.info").exists() or (self.directory / "process").exists()):
            raise ValueError("Legacy single-sided task: use a new directory; history is not imported")
        self.directory.mkdir(parents=True, exist_ok=True)
        # Serialize initialization as well as execution: two constructors must
        # never both publish a fresh checkpoint over each other's progress.
        with (self.directory / "families.lock").open("a") as lock:
            self._lock(lock)
            if self.checkpoint.exists():
                self._restore()
            else:
                self._save()

    @staticmethod
    def _lock(lock):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("This family search is already running") from error

    @property
    def total_rounds(self):
        return sum(f.attempts for f in self.families.values())

    @property
    def total_length(self):
        return sum(f.added_bases for f in self.families.values())

    def _save(self):
        atomic_json(self.checkpoint, {
            "schema": SCHEMA_VERSION, "contract_id": self.contract_id,
            "contract": self.contract,
            "families": [asdict(f) for f in self.families.values()],
            "cursor": self.cursor, "pending": self.pending,
            "completed_attempts": self.completed_attempts,
            "checked": self.checked, "checked_diagnostics": getattr(self, "checked_diagnostics", {}), "status": self.status,
            "winner": asdict(self.winner) if self.winner else None,
        })

    def _restore(self):
        state = read_json(self.checkpoint)
        if (state.get("schema") != SCHEMA_VERSION or
                state.get("contract_id") != self.contract_id or
                state.get("contract") != self.contract):
            raise ValueError("Family checkpoint inputs, parameters or schema changed; use a new directory")
        self.checked_diagnostics = state.get("checked_diagnostics", {})
        try:
            restored = {}
            for item in state["families"]:
                item = dict(item)
                item["versions"] = [Version(**v) for v in item["versions"]]
                family = Family(**item)
                expected = self.families[family.key]
                if (family.key in restored or family.direction != expected.direction or
                        not family.versions or family.versions[0] != expected.versions[0]):
                    raise ValueError("Family identity mismatch")
                for number, version in enumerate(family.versions):
                    if version.family != family.key or version.number != number:
                        raise ValueError("Invalid family version chain")
                    version.verify()
                    if number and version.length <= family.versions[number - 1].length:
                        raise ValueError("Non-growing family history")
                if type(family.anchor_backoff) is not int or family.anchor_backoff not in (0, 2000):
                    raise ValueError("Invalid terminal-anchor backoff")
                if (type(family.attempts) is not int or family.attempts < len(family.versions) - 1 or
                        family.added_bases != family.current.length - family.versions[0].length):
                    raise ValueError("Family budget mismatch")
                restored[family.key] = family
            if set(restored) != set(self.families):
                raise ValueError("Missing family")
            self.families = restored
            self.cursor = state["cursor"]
            if type(self.cursor) is not int or not 0 <= self.cursor < len(self.schedule):
                raise ValueError("Invalid scheduling cursor")
            self.pending = state["pending"]
            self.completed_attempts = state["completed_attempts"]
            if self.total_rounds != self.completed_attempts + (self.pending is not None):
                raise ValueError("Attempt budget mismatch")
            if self.max_rounds is not None and self.total_rounds > self.max_rounds:
                raise ValueError("Round budget exceeded")
            if self.pending:
                family = self.families[self.pending["family"]]
                if (self.pending["attempt"] != family.attempts or
                        self.pending["input"] != asdict(family.current) or family.stop_reason):
                    raise ValueError("Invalid pending attempt")
            self.checked = state["checked"]
            allowed = {self._pair_key(a, b): (a, b) for a, b in self._pairs()}
            for key, candidates in self.checked.items():
                left, right = allowed[key]
                for candidate in candidates:
                    self._validate_connection(Connection(**candidate), left, right)
            self.status = state["status"]
            if self.status not in ("running", "closed", "exhausted", "round_limit", "length_limit", "terminal"):
                raise ValueError("Unknown search status")
            self.winner = Connection(**state["winner"]) if state["winner"] else None
            if (self.status == "closed") != (self.winner is not None):
                raise ValueError("Invalid winner state")
            if self.winner and asdict(self.winner) not in [c for cs in self.checked.values() for c in cs]:
                raise ValueError("Winner missing from checked candidates")
            if self.status != "running" and self.pending:
                raise ValueError("Finished search has pending work")
        except (KeyError, TypeError, ValueError, OSError) as error:
            raise ValueError(f"Invalid family checkpoint: {error}") from error

    def _pairs(self):
        primary = self.families[self.primary]
        for family in self.families.values():
            if family.key == self.primary:
                continue
            left, right = (primary, family) if primary.direction == "rightward" else (family, primary)
            for a in left.versions:
                for b in right.versions:
                    yield a, b

    @staticmethod
    def _pair_key(left, right):
        return fingerprint([asdict(left), asdict(right)])

    @staticmethod
    def _validate_connection(candidate, left, right):
        if ((candidate.left_family, candidate.left_version) != (left.family, left.number) or
                (candidate.right_family, candidate.right_version) != (right.family, right.number)):
            raise ValueError("Alignment candidate refers to a different version pair")
        if not math.isfinite(candidate.identity) or not 0 <= candidate.identity <= 100:
            raise ValueError("Invalid overlap identity")
        integers = (candidate.overlap, candidate.overhang, candidate.left_start,
                    candidate.left_end, candidate.right_start, candidate.right_end)
        if any(type(n) is not int for n in integers):
            raise ValueError("Overlap lengths and coordinates must be integers")
        if not (0 < candidate.overlap <= max(left.length, right.length) and candidate.overhang >= 0 and
                0 <= candidate.left_start < candidate.left_end <= left.length and
                0 <= candidate.right_start < candidate.right_end <= right.length):
            raise ValueError("Overlap coordinates outside complete sequence bounds")

    def _check_connections(self, compare):
        candidates = []
        for left, right in self._pairs():
            key = self._pair_key(left, right)
            if key not in self.checked:
                # Finish every comparison before choosing. Save each comparison so
                # interrupted scans do not recompute already validated pairs.
                matches = list(compare(left, right))
                for candidate in matches:
                    self._validate_connection(candidate, left, right)
                self.checked[key] = [asdict(c) for c in matches]
                if hasattr(compare, "diagnostic"):
                    if not hasattr(self, "checked_diagnostics"):
                        self.checked_diagnostics = {}
                    self.checked_diagnostics[key] = compare.diagnostic(left, right)
                self._save()
            candidates.extend(Connection(**c) for c in self.checked[key])
        if candidates:
            self.winner = min(candidates, key=lambda c: c.rank(self.order))
            self.status = "closed"
            self._save()

    def _next_family(self):
        for _ in self.schedule:
            key = self.schedule[self.cursor]
            self.cursor = (self.cursor + 1) % len(self.schedule)
            if not self.families[key].stop_reason:
                return self.families[key]
        return None

    def _finish_pending(self, extend):
        family = self.families[self.pending["family"]]
        attempt_dir = self.directory / "attempts" / str(self.order[family.key]) / str(family.attempts)
        attempt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = attempt_dir / "result.json"
        receipt_id = fingerprint([self.contract_id, self.pending])
        if receipt_path.exists():
            receipt = read_json(receipt_path)
            if receipt.get("receipt_id") != receipt_id:
                raise ValueError("Attempt receipt does not match pending work")
        else:
            # The adapter cannot mutate scheduler state before receipt publication.
            view = Family(family.key, family.direction, list(family.versions),
                          family.attempts, family.added_bases, list(family.used_reads),
                          list(family.last_reads), family.stop_reason, family.anchor_backoff)
            result = extend(view, attempt_dir)
            if not isinstance(result, AttemptResult):
                raise TypeError("Extension adapter must return AttemptResult")
            if result.terminal_reason and len(self.families) != 1:
                raise ValueError("A paired search requires overlap evidence to finish")
            version = (Version.capture(family.key, len(family.versions), result.sequence_path)
                       if result.sequence_path else None)
            if version and version.length > family.current.length and any(
                    version.path == old.path for f in self.families.values() for old in f.versions):
                raise ValueError("Extension output must not overwrite a historical sequence")
            if version and version.length <= family.current.length:
                if version.length < family.current.length:
                    raise ValueError("Extension shortened the cumulative sequence")
                version = None
                stop_reason = result.stop_reason or "no_growth"
            else:
                stop_reason = result.stop_reason
            if result.retry_reason and (version or result.stop_reason or result.terminal_reason or family.anchor_backoff):
                raise ValueError("Invalid terminal-anchor retry request")
            if version is None and not stop_reason and not result.terminal_reason and not result.retry_reason:
                raise ValueError("An unsuccessful attempt must provide a normal stop reason")
            receipt = {
                "receipt_id": receipt_id, "version": asdict(version) if version else None,
                "used_reads": sorted(set(result.used_reads)), "stop_reason": stop_reason,
                "terminal_reason": result.terminal_reason, "retry_reason": result.retry_reason,
            }
            atomic_json(receipt_path, receipt)
        # Verify reused artifacts before accepting their sequence and budget.
        version = Version(**receipt["version"]) if receipt["version"] else None
        if version:
            version.verify()
            if (version.family != family.key or version.number != len(family.versions) or
                    version.length <= family.current.length):
                raise ValueError("Invalid extension receipt version")
        if receipt["terminal_reason"] and len(self.families) != 1:
            raise ValueError("Unexpected terminal objective in a paired search")
        if not version and not receipt["stop_reason"] and not receipt["terminal_reason"] and not receipt.get("retry_reason"):
            raise ValueError("Attempt receipt is missing its stop reason")
        if receipt.get("retry_reason"):
            if receipt["retry_reason"] != "terminal_anchor_backoff" or family.anchor_backoff:
                raise ValueError("Invalid terminal-anchor retry receipt")
            family.anchor_backoff = 2000
        if version:
            family.anchor_backoff = 0
            family.added_bases += version.length - family.current.length
            family.versions.append(version)
            family.last_reads = receipt["used_reads"]
            family.used_reads = sorted(set(family.used_reads).union(family.last_reads))
        family.stop_reason = receipt["stop_reason"] or receipt["terminal_reason"]
        self.completed_attempts += 1
        self.pending = None
        if receipt["terminal_reason"]:
            self.status = "terminal"
        self._save()

    def run(self, extend, compare):
        """Finish pending attempts before checking budgets; their rounds are charged.

        After an exception instantiate afresh to reload the last committed state.
        """
        with (self.directory / "families.lock").open("a") as lock:
            self._lock(lock)
            self._restore()
            while self.status == "running":
                if self.pending:
                    self._finish_pending(extend)
                    if self.status != "running":
                        break
                self._check_connections(compare)
                if self.status != "running":
                    break
                if self.max_rounds is not None and self.total_rounds >= self.max_rounds:
                    self.status = "round_limit"
                elif self.max_length is not None and self.total_length >= self.max_length:
                    self.status = "length_limit"
                else:
                    family = self._next_family()
                    if family is None:
                        self.status = "exhausted"
                    else:
                        family.attempts += 1
                        self.pending = {"family": family.key, "attempt": family.attempts,
                                        "input": asdict(family.current)}
                self._save()
        return self
