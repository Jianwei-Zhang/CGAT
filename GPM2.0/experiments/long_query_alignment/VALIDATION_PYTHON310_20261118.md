# Python 3.10 result-publication compatibility

## Incident and scope

The real x86 wheat continuation (Donau 42416332) reached Flye scientific
admission, then failed on 2026-11-18 at 05:07:50 CST in
`alignment_policy_receipt -> metadata_json._source`: Python 3.10.12 does not
provide `hashlib.file_digest`. The previous read-only admission check did not
exercise this later publication boundary. Its passing result did not establish
end-to-end delivery compatibility.

The parent workflow interrupted hifiasm ordinary unit 9/16. All 26 previously
completed unit markers were rehashed unchanged after failure; unit 9 has a
28,540,928-byte partial PAF but no complete native PAF. Partial output is not a
completed checkpoint and cannot be used as one. No whole-assembly restart is
required. The queued ARM job had already been canceled after genuine x86
execution was observed; it is not a remaining fallback job.

## Changes

- Replace the unsupported digest API with bounded exact-byte SHA-256 reads in
  metadata validation, DEGAP candidate export and the development replay helper.
  No checksum, file-identity, regular-file or publication check is removed.
- Add the exact prior runtime profile to the reviewed migration inventory. The
  mapper kernels are unchanged. The frozen prior file inventory is tested;
  arbitrary runtime changes remain rejected.
- Generated runtime synchronization verifies 41 files with zero drift.
- New regressions make the newer digest API unavailable and verify matching and
  incorrect checksums, small chunk boundaries, binary payloads and empty files.
- On the x86 node, 12 immediate chmod operations produced identical ctime values.
  Existing metadata tests now explicitly wait (bounded to three seconds) for
  their changed-ctime precondition; corruption tests also establish that change.
  This does not alter production caching or claim detection of an external
  same-size rewrite with all observed timestamps unchanged.

## Verification

- Local alignment suite: 840 tests, one optional native-source oracle skipped,
  remaining tests passed (230 seconds), using pinned minimap2 and the portable
  native helper. A subsequent test-only timestamp-precondition adjustment was
  exercised in the actual Python 3.10 run below.
- Donau job 42430613: SUCCEEDED, agent-X86-26, 05:30:39–05:31:47 CST.
  Python 3.10.12: 80 focused alignment/resume/publication tests and eight DEGAP
  tests passed without skips. Earlier validation jobs 42428464 and 42430067
  exposed the timestamp-precondition issue; they did not submit scientific work.
- Both real existing attempts passed the exact runtime compatibility check.
- The real Flye candidate receipt was bound to the failed adapter receipt and
  its existing successful admission. Policy generation and atomic publication
  completed in a separate private directory. The 1,061,893,273-byte PAF retained
  SHA-256 `8d3295b062f66ba14ca609270c3be25d0ad5945f49e2b7ae9ad53b10035f22df`.
  The generated policy contains 20 native sources.
- This is a post-admission publication-boundary check, not a repeat of scientific
  admission. Mapping/external execution was prohibited, and an audit hook denied
  writes to the original workspace. The source PAF digest matched before/after;
  mapper calls were zero and the original workspace was not modified.
- Full local Server suite: 477 tests, one skip, remaining tests passed
  (471 seconds).
- Release-note renderer: 17 tests passed; generated bilingual pages checked.

Operational evidence is retained under
`docs_deploy/release-v2.0.20/server-python310-20261118/` and the remote private
`~/cgat-reads-debug/jm19-python310-fix-20261118/` directory. At this validation
snapshot, the fix is not yet published or installed and full scientific
continuation has not been resubmitted. Full customer acceptance still requires
all workflow stages and final delivery archives to succeed.
