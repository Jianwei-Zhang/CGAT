"""Deferred final-validation cases. NOT executed during implementation phase."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import review_isolation as ri


class ReviewIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.counter = 0
        self.harness = hashlib.sha256(Path(ri.__file__).with_name("isolate_minimap2.py").read_bytes()).hexdigest()

    def evidence(self, *, selected=None, case="locate", zero=False, stopped=None):
        output = "/data/new output"
        plan = {"reference":"/data/ref.fa", "query":"/data/query.fa", "output":output,
                "case":case, "query_id":selected, "execute":True, "production_ready":False,
                "automatic_retry":False, "expected_version":"2.31-r1302"}
        command = ["/tools/minimap2", "-c", "-x", "asm10", "-t", "1", "--print-qname"] + ri.CASES[case]
        command += ["-o", output+"/alignment.diagnostic.partial.paf", plan["reference"],
                    output+"/selected.query.fa" if selected else plan["query"]]
        plan["command"] = command
        inputs = {}
        for key, records, digest in (("reference", {"ref":20}, "a"*64), ("query", {"first":8,"second":4}, "b"*64)):
            inputs[key] = {"path":plan[key], "content_scanned":True, "sha256":digest,
                           "records":records, "total_bases":sum(records.values()), "max_length":max(records.values())}
        if selected:
            inputs["selected_query_sha256"] = "d"*64
        stderr = b"[M::main] loaded/built the index for 1 target sequence(s)\n"
        completed = 0
        if selected is None:
            stderr += b"QR\tfirst\t0\t8\nQT\tfirst\t0\t0.01\n"
            completed += 1
        stderr += b"QR\tsecond\t0\t4\n"
        candidate = {"query_id":"second", "thread_id":0, "length":4, "target_index_part":1}
        if zero:
            stderr += b"QT\tsecond\t0\t0.02\n"
            completed += 1
            candidate = None
        else:
            stderr += ("minimap2: align.c:301: mm_update_extra: Assertion `"+ri.ASSERTION+"' failed.\n").encode()
        trace = {"same_assertion":not zero, "completed_query_events":completed, "index_parts_seen":1,
                 "trace_well_formed":True, "active_query_at_assertion":candidate, "independent_replay_required":True}
        report = {"plan":copy.deepcopy(plan), "status":"diagnostic_completed", "production_ready":False,
                  "customer_recovered":False, "harness_sha256":self.harness,
                  "input_stats_unchanged":True, "tool_unchanged":True,
                  "tool":{"path":"/tools/minimap2", "version":"2.31-r1302", "sha256":"c"*64},
                  "trace":trace, "execution":{"returncode":0 if zero else -6,"stopped":stopped},
                  "alignment_exit_zero":zero,
                  "outcome":stopped or ("exit_zero_unvalidated" if zero else "alignment_assertion")}
        return {"plan.json":plan, "report.json":report, "inputs.json":inputs,
                "stdout.log":b"", "stderr.log":stderr}

    def archive(self, data, extra=()):
        self.counter += 1
        path = self.root / f"receipt-{self.counter}.tar.gz"
        with tarfile.open(path, "w:gz") as stream:
            for name in ri.MEMBER_ORDER:
                if name not in data:
                    continue
                raw = data[name]
                if not isinstance(raw, bytes):
                    raw = json.dumps(raw).encode()
                member = tarfile.TarInfo(name)
                member.size = len(raw)
                stream.addfile(member, io.BytesIO(raw))
            for member, raw in extra:
                stream.addfile(member, io.BytesIO(raw) if raw is not None else None)
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def review(self, data, **kwargs):
        path, digest = self.archive(data)
        return ri.review_archive(path, digest, expected_tool_sha256="c"*64, **kwargs)

    def test_localized_candidate_is_not_repair_and_review_is_read_only(self):
        path, digest = self.archive(self.evidence())
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        with patch("subprocess.Popen", side_effect=AssertionError("must never launch commands")):
            result = ri.review_archive(path, digest, expected_tool_sha256="c"*64)
        self.assertEqual(result["status"], "assertion_candidate_localized")
        self.assertEqual(result["candidate_query"]["query_id"], "second")
        for key in ("production_ready","repair_accepted","customer_recovered","commands_executed","files_extracted"):
            self.assertFalse(result[key])
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_zero_exit_and_resource_stop_are_never_accepted_repairs(self):
        self.assertEqual(self.review(self.evidence(zero=True))["status"], "exit_zero_unvalidated")
        result = self.review(self.evidence(stopped="timeout"))
        self.assertEqual(result["status"], "resource_guard_stopped")
        self.assertIsNone(result["candidate_query"])
        self.assertFalse(result["repair_accepted"])

    def test_hash_source_version_tool_and_plan_disagreement_rejected(self):
        path, digest = self.archive(self.evidence())
        with self.assertRaisesRegex(ri.ReviewError, "SHA-256 mismatch"):
            ri.review_archive(path, "0"*64)
        with self.assertRaisesRegex(ri.ReviewError, "source"):
            ri.review_archive(path, digest, expected_harness_sha256="0"*64)
        with self.assertRaisesRegex(ri.ReviewError, "tool hash"):
            ri.review_archive(path, digest, expected_tool_sha256="0"*64)
        data = self.evidence()
        data["report.json"]["tool"]["version"] = "2.26-r1175"
        with self.assertRaisesRegex(ri.ReviewError, "tool identity"):
            self.review(data)
        data = self.evidence()
        data["plan.json"]["query"] = "/changed.fa"
        with self.assertRaisesRegex(ri.ReviewError, "disagrees"):
            self.review(data)

    def test_unknown_duplicate_traversal_and_link_members_rejected(self):
        for name, kind in (("query.fa", tarfile.REGTYPE), ("../outside", tarfile.REGTYPE),
                           ("plan.json", tarfile.REGTYPE), ("stderr.log", tarfile.SYMTYPE)):
            info = tarfile.TarInfo(name)
            info.type, info.linkname = kind, "/tmp/not-extracted"
            path, digest = self.archive(self.evidence(), [(info, b"" if kind == tarfile.REGTYPE else None)])
            with self.subTest(name=name, kind=kind), self.assertRaises(ri.ReviewError):
                ri.review_archive(path, digest)

    def test_archive_symlink_and_truncation_rejected(self):
        path, digest = self.archive(self.evidence())
        link = self.root / "link.tar.gz"
        link.symlink_to(path)
        with self.assertRaisesRegex(ri.ReviewError, "regular file"):
            ri.review_archive(link, digest)
        path.write_bytes(path.read_bytes()[:-10])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises((ri.ReviewError, EOFError, tarfile.TarError)):
            ri.review_archive(path, digest)

    def test_oversized_json_log_line_and_expansion_fail_closed(self):
        data = self.evidence()
        data["plan.json"] = b" "*(ri.MAX_JSON+1)
        with self.assertRaisesRegex(ri.ReviewError, "member exceeds"):
            self.review(data)
        data = self.evidence()
        data["stderr.log"] += b"x"*(ri.MAX_LINE+1)+b"\n"
        with self.assertRaisesRegex(ri.ReviewError, "log line"):
            self.review(data)
        path, digest = self.archive(self.evidence())
        with patch.object(ri, "MAX_EXPANDED", 1024):
            with self.assertRaisesRegex(ri.ReviewError, "expanded archive"):
                ri.review_archive(path, digest)

    def test_duplicate_json_and_nonfinite_constants_rejected(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ri.ReviewError):
                ri.decode_json(raw)

    def test_trace_disagreement_truncation_and_wrong_query_events_rejected(self):
        for change in (lambda raw:raw.replace(b"second",b"unknown"),
                       lambda raw:raw[:-1], lambda raw:raw.replace(b"\t0\t4", b"\t1\t4")):
            data = self.evidence()
            data["stderr.log"] = change(data["stderr.log"])
            with self.assertRaisesRegex(ri.ReviewError, "attribution disagrees"):
                self.review(data)
        data = self.evidence(selected="second", zero=True)
        data["stderr.log"] = data["stderr.log"].replace(b"second\t0\t4", b"first\t0\t8").replace(b"QT\tsecond", b"QT\tfirst")
        with self.assertRaisesRegex(ri.ReviewError, "attribution disagrees"):
            self.review(data)

    def test_declared_candidate_and_length_summaries_cannot_override_raw_evidence(self):
        data = self.evidence()
        data["report.json"]["trace"]["active_query_at_assertion"]["query_id"] = "first"
        with self.assertRaisesRegex(ri.ReviewError, "attribution disagrees"):
            self.review(data)
        data = self.evidence()
        data["inputs.json"]["query"]["total_bases"] = 999
        with self.assertRaisesRegex(ri.ReviewError, "length summary"):
            self.review(data)

    def test_unsupported_command_or_missing_cigar_flag_rejected(self):
        data = self.evidence()
        data["plan.json"]["command"].remove("-c")
        data["report.json"]["plan"] = copy.deepcopy(data["plan.json"])
        with self.assertRaisesRegex(ri.ReviewError, "command differs"):
            self.review(data)

    def test_incomplete_and_changed_identity_are_not_localized(self):
        for status, expected in (("diagnostic_error","diagnostic_incomplete"), ("input_or_tool_changed","identity_changed")):
            data = self.evidence()
            data["report.json"]["status"] = status
            for name in ("inputs.json","stdout.log","stderr.log"):
                data.pop(name)
            result = self.review(data)
            self.assertEqual(result["status"], expected)
            self.assertIsNone(result["candidate_query"])

    def test_independent_replay_and_contrast_identity_gates(self):
        original = self.review(self.evidence())
        replay = self.review(self.evidence(selected="second"))
        self.assertIn("same_assertion", ri.compare_reviews(original, replay)["conclusion"])
        contrast = self.review(self.evidence(selected="second", case="eqx", zero=True))
        result = ri.compare_reviews(replay, contrast)
        self.assertIn("exited_zero_only", result["conclusion"])
        self.assertFalse(result["repair_accepted"])
        with self.assertRaisesRegex(ri.ReviewError, "independently failing"):
            ri.compare_reviews(original, contrast)
        changed = copy.deepcopy(contrast)
        changed["inputs"]["reference"]["sha256"] = "f"*64
        with self.assertRaisesRegex(ri.ReviewError, "identity changed"):
            ri.compare_reviews(replay, changed)
        changed = copy.deepcopy(contrast)
        changed["selected_query_sha256"] = "f"*64
        with self.assertRaisesRegex(ri.ReviewError, "selected-record bytes"):
            ri.compare_reviews(replay, changed)

    def test_deadline_and_json_output_rejection_are_bounded(self):
        with self.assertRaisesRegex(ri.ReviewError, "time budget"):
            ri.check_deadline(0)
        path, _ = self.archive(self.evidence())
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = ri.main([str(path), "--expected-sha256", "wrong"])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out.getvalue())["commands_executed"])


if __name__ == "__main__":
    unittest.main()
