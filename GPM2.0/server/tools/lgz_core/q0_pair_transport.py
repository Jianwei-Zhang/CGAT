"""Owner-scoped, read-only DNA transport; no cross-run cache authority.

The owner already holds verified immutable strings. Each needed ASCII source is
written once to a private local file, then sealed read-only. Workers receive only
bounds and a file identity, and read bounded blocks (not entire hundred-Mb
anchors). Parent and workers check identities; no untrusted pickle is read here.
"""
from collections import OrderedDict
from dataclasses import dataclass
import os
import pickle
from pathlib import Path
import shutil
import stat
import tempfile


def signature(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


@dataclass(frozen=True)
class SharedSequence:
    path: str
    identity: tuple
    total: int
    start: int
    end: int

    def __len__(self):
        return self.total

    def __getitem__(self, key):
        if (not isinstance(key, slice) or key.step is not None
                or not self.start <= key.start <= key.stop <= self.end):
            raise ValueError("pair worker DNA access outside its declared interval")
        return _READS.read(self, key.start, key.stop)


class ReadBlocks:
    BLOCK = 256 * 1024
    MAX_BLOCKS = 128  # 32 MiB per worker; no chromosome-sized mappings
    MAX_FILES = 32

    def __init__(self):
        self.files, self.blocks = OrderedDict(), OrderedDict()

    def descriptor(self, source):
        key = source.path, source.identity
        fd = self.files.get(key)
        if fd is None:
            directory = Path(source.path).parent
            st = directory.stat()
            if directory.is_symlink() or st.st_uid != os.getuid() or st.st_mode & 0o077:
                raise ValueError("unsafe shared DNA owner")
            fd = os.open(source.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o222
                    or signature(st) != source.identity or st.st_size != source.total):
                os.close(fd)
                raise ValueError("shared DNA identity changed")
            if len(self.files) >= self.MAX_FILES:
                os.close(self.files.popitem(last=False)[1])
            self.files[key] = fd
        else:
            self.files.move_to_end(key)
        return fd

    def read(self, source, start, end):
        pieces = []
        while start < end:
            offset = start // self.BLOCK * self.BLOCK
            key = source.path, source.identity, offset
            block = self.blocks.get(key)
            if block is None:
                fd = self.descriptor(source)
                if signature(os.fstat(fd)) != source.identity:
                    raise ValueError("shared DNA changed during read")
                raw = os.pread(fd, min(self.BLOCK, source.total-offset), offset)
                if len(raw) != min(self.BLOCK, source.total-offset):
                    raise ValueError("short shared DNA read")
                block = raw.decode("ascii")
                if len(self.blocks) >= self.MAX_BLOCKS:
                    self.blocks.popitem(last=False)
                self.blocks[key] = block
            else:
                self.blocks.move_to_end(key)
            stop = min(end, offset + len(block))
            pieces.append(block[start-offset:stop-offset]); start = stop
        return "".join(pieces)

    def clear(self):
        for fd in self.files.values():
            os.close(fd)
        self.files.clear(); self.blocks.clear()


_READS = ReadBlocks()


@dataclass(frozen=True)
class SharedValue:
    """An immutable Python value written by this private owner, never user pickle."""
    path: str
    identity: tuple
    total: int

    def load(self):
        return _OBJECTS.load(self)


class ReadObjects:
    MAX_BYTES = 64 << 20  # serialized bytes; worker AS also bounds decoded objects
    MAX_ITEMS = 128

    def __init__(self):
        self.rows = OrderedDict()
        self.bytes = 0

    def load(self, reference):
        key = reference.path, reference.identity
        if key in self.rows:
            self.rows.move_to_end(key)
            return self.rows[key][0]
        fd = _READS.descriptor(reference)
        if signature(os.fstat(fd)) != reference.identity:
            raise ValueError("shared metadata changed before read")
        with os.fdopen(os.dup(fd), "rb") as stream:
            stream.seek(0)
            value = pickle.load(stream)
            if stream.read(1) or signature(os.fstat(stream.fileno())) != reference.identity:
                raise ValueError("shared metadata changed during read")
        if reference.total <= self.MAX_BYTES:
            while self.rows and (len(self.rows) >= self.MAX_ITEMS or self.bytes + reference.total > self.MAX_BYTES):
                self.bytes -= self.rows.popitem(last=False)[1][1]
            self.rows[key] = value, reference.total
            self.bytes += reference.total
        return value

    def clear(self):
        self.rows.clear(); self.bytes = 0


_OBJECTS = ReadObjects()


class _BoundedFile:
    """A metadata resource limit, never a scientific exclusion."""
    LIMIT = 128 << 20

    def __init__(self, stream):
        self.stream, self.size = stream, 0

    def write(self, data):
        if self.size + len(data) > self.LIMIT:
            raise BufferError("shared metadata exceeds bounded transfer")
        result = self.stream.write(data); self.size += result
        return result


class SequenceStore:
    def __init__(self, sources, masks):
        self.sources = sources
        # Immutable round snapshot. Workers may retain exact verdicts across
        # tasks only inside this unique owner/policy generation.
        self.masks = {s: tuple(rows) for s, rows in masks.items()}
        self.temp = tempfile.TemporaryDirectory(prefix="q0-pair-dna-")
        self.root = Path(self.temp.name)
        self.rows, self.unavailable = {}, set()
        self.values, self.unavailable_values = {}, set()
        self.written_bytes = 0

    def region(self, source, span):
        if source in self.unavailable:
            return None
        if source not in self.rows:
            sequence = self.sources[source]
            path = self.root / (str(len(self.rows)) + ".dna")
            try:
                if shutil.disk_usage(self.root).free < len(sequence) + (64 << 20):
                    self.unavailable.add(source)
                    return None
                with path.open("xb") as out:
                    # Bounded encoding, preserving case and the exact DNA bytes.
                    for lo in range(0, len(sequence), 4 << 20):
                        out.write(sequence[lo:lo+(4 << 20)].encode("ascii"))
                path.chmod(0o400)
            except (OSError, UnicodeEncodeError):
                path.unlink(missing_ok=True)
                self.unavailable.add(source)
                return None  # exact owner computation, never missing evidence
            identity = signature(path.stat())
            if identity[2] != len(sequence):
                raise ValueError("shared DNA length mismatch")
            self.rows[source] = str(path), identity, len(sequence)
            self.written_bytes += len(sequence)
        path, identity, total = self.rows[source]
        if not 0 <= span.start < span.end <= total:
            raise ValueError("shared DNA interval outside original source")
        return SharedSequence(path, identity, total, span.start, span.end)

    def metadata(self, key, value):
        if key in self.unavailable_values:
            return None
        if key not in self.values:
            path = self.root / (str(len(self.values)) + ".metadata")
            try:
                if shutil.disk_usage(self.root).free < 64 << 20:
                    self.unavailable_values.add(key)
                    return None
                with path.open("xb") as out:
                    pickle.dump(value, _BoundedFile(out), protocol=5)
                path.chmod(0o400)
            except (OSError, BufferError, MemoryError):
                path.unlink(missing_ok=True)
                self.unavailable_values.add(key)
                return None
            identity = signature(path.stat())
            self.values[key] = SharedValue(str(path), identity, identity[2])
        return self.values[key]

    def verify(self):
        for value in self.values.values():
            if signature(os.stat(value.path, follow_symlinks=False)) != value.identity:
                raise ValueError("shared metadata changed before admission completion")
        for path, identity, _ in self.rows.values():
            if signature(os.stat(path, follow_symlinks=False)) != identity:
                raise ValueError("shared DNA changed before admission completion")

    def close(self):
        try:
            self.verify()
        finally:
            self.temp.cleanup()
