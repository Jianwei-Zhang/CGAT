"""Incremental private JSON parsing and comparison, without a file-size veto.

Read buffers are bounded; load() still owns the requested decoded state and the
largest scalar. compare() validates against an existing object without a second
container tree. fields= discards unneeded top-level values while validating ALL
input syntax. This is not a constant-RSS claim for arbitrary decoded state.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import hashlib
import math
import os
from pathlib import Path
import re
import stat

CHUNK = 64 * 1024
MAX_DEPTH = 128  # Generated schemas are shallow; protect the parser call stack.
_BUILD, _SKIP = object(), object()
_SPECIAL = re.compile(r'["\\\x00-\x1f]')
_SPACE = re.compile(r"[ \t\r\n]*")
_END = re.compile(r'[ \t\r\n,\]\}]')


class MetadataError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise MetadataError(message)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _source(path, limit=None, expected_sha256=None):
    path = Path(path)
    before = path.lstat()
    _require(stat.S_ISREG(before.st_mode), "metadata must be an unlinked regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "r", encoding="utf-8", newline="") as stream:
        opened = os.fstat(stream.fileno())
        _require(_identity(before) == _identity(opened), "metadata changed before reading")
        if limit is not None:
            _require(type(limit) is int and limit >= 0, "invalid explicit metadata budget")
            _require(opened.st_size <= limit, "oversized fixed-schema metadata")
        if expected_sha256 is not None:
            # hashlib.file_digest is Python 3.11+. Keep the same exact-byte
            # binding on supported Python 3.10 cluster environments as well.
            digest = hashlib.sha256()
            while block := stream.buffer.read(CHUNK):
                digest.update(block)
            _require(digest.hexdigest() == expected_sha256, "metadata digest differs")
            stream.seek(0)
        yield stream
        _require(_identity(opened) == _identity(os.fstat(stream.fileno()))
                 == _identity(path.lstat()), "metadata changed during reading")


class _Reader:
    def __init__(self, stream):
        self.stream, self.buffer, self.pos = stream, "", 0

    def peek(self):
        if self.pos == len(self.buffer):
            self.buffer, self.pos = self.stream.read(CHUNK), 0
        return self.buffer[self.pos:self.pos + 1]

    def whitespace(self):
        while self.peek():
            self.pos = _SPACE.match(self.buffer, self.pos).end()
            if self.pos < len(self.buffer):
                return self.buffer[self.pos]
        return ""

    def take(self, char):
        _require(self.whitespace() == char, "invalid or truncated JSON metadata")
        self.pos += 1

    def string(self):
        self.take('"')
        start, pieces, escaped = self.pos - 1, [], False
        while True:
            if escaped:
                if self.pos == len(self.buffer):
                    pieces.append(self.buffer[start:])
                    _require(bool(self.peek()), "truncated JSON string")
                    start = 0
                self.pos += 1
                escaped = False
            match = _SPECIAL.search(self.buffer, self.pos)
            if match is None:
                pieces.append(self.buffer[start:])
                self.pos = len(self.buffer)
                _require(bool(self.peek()), "truncated JSON string")
                start = 0
                continue
            self.pos = match.end()
            char = match.group()
            if char == '"':
                tail = self.buffer[start:self.pos]
                return json.loads("".join([*pieces, tail]) if pieces else tail)
            _require(char == "\\", "unescaped control character in JSON string")
            escaped = True

    def scalar(self):
        pieces = []
        while True:
            match = _END.search(self.buffer, self.pos)
            end = match.start() if match else len(self.buffer)
            pieces.append(self.buffer[self.pos:end]); self.pos = end
            if match or not self.peek():
                break
        def invalid(text):
            raise MetadataError("non-finite JSON number: " + text)
        value = json.loads("".join(pieces), parse_constant=invalid)
        _require(not isinstance(value, float) or math.isfinite(value), "non-finite JSON number")
        return value

    def value(self, expected=_BUILD, *, depth=0, fields=None):
        _require(depth <= MAX_DEPTH, "JSON metadata nesting exceeds supported schema")
        char = self.whitespace()
        _require(bool(char), "truncated JSON metadata")
        comparing = expected is not _BUILD and expected is not _SKIP
        if char == "{":
            if comparing:_require(type(expected) is dict, "metadata object differs")
            self.pos += 1
            result, seen = {}, set()
            if self.whitespace() != "}":
                while True:
                    key = self.string()
                    _require(key not in seen, "duplicate JSON object key")
                    seen.add(key); self.take(":")
                    if comparing:
                        _require(key in expected, "unexpected metadata key")
                        mode = expected[key]
                    else:
                        mode = _SKIP if expected is _SKIP or fields is not None and key not in fields else _BUILD
                    value = self.value(mode, depth=depth + 1)
                    if mode is _BUILD:result[key] = value
                    if self.whitespace() == "}":break
                    self.take(",")
            self.take("}")
            if comparing:_require(len(seen) == len(expected), "missing metadata key")
            return result if expected is _BUILD else None
        if char == "[":
            if comparing:_require(type(expected) is list, "metadata array differs")
            self.pos += 1
            result, count = [], 0
            if self.whitespace() != "]":
                while True:
                    if comparing:_require(count < len(expected), "extra metadata array item")
                    value = self.value(expected[count] if comparing else expected, depth=depth + 1)
                    if expected is _BUILD:result.append(value)
                    count += 1
                    if self.whitespace() == "]":break
                    self.take(",")
            self.take("]")
            if comparing:_require(count == len(expected), "missing metadata array item")
            return result if expected is _BUILD else None
        value = self.string() if char == '"' else self.scalar()
        if comparing:
            numeric = type(value) in (int, float) and type(expected) in (int, float)
            _require((type(value) is type(expected) or numeric) and value == expected,
                     "metadata scalar differs")
        return value if expected is _BUILD else None

    def finish(self):
        _require(not self.whitespace(), "extra content after JSON metadata")


def load(path, *, expected_type=dict, fields=None, limit=None, expected_sha256=None):
    with _source(path, limit, expected_sha256) as stream:
        reader = _Reader(stream)
        if fields is not None:
            _require(expected_type is dict and reader.whitespace() == "{", "field selection requires an object")
        value = reader.value(fields=fields)
        reader.finish()
        _require(type(value) is expected_type, "JSON metadata has the wrong container type")
        return value


def compare(path, expected):
    """Validate every token against existing metadata without decoding a second tree."""
    with _source(path) as stream:
        reader = _Reader(stream)
        reader.value(expected)
        reader.finish()
