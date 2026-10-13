# Skill v3: automatic local lessons and official updates

Date: 2026-10-13. Scope: operational skill and update helpers, not genome algorithms.

## Starting state

Git was clean and `master` matched `origin/master` at
`4e58a518c3cef9bd430edb142915a15708d4c495`. Comet status/resume probe reported no
active Native or Classic changes and no unmanaged OpenSpec. Doctor reported
healthy with no repairs; managed-hook and disabled/uninitialized CodeGraph-related
warnings were not repaired or used for this task. No Comet workflow was started.

## New contract

- Retain a concise local lesson automatically only after a demonstrated cause,
  authorized repair and targeted verification, when recurrence is plausible and
  recording would avoid a meaningful pitfall. No persistence-mode selection or
  per-entry save approval. Routine successes, transient values and untested guesses
  are excluded. Deduplicate and preserve scoped evidence.
- Explicit no-write instructions/read-only tasks still win. Local recording does
  not authorize changes to data, QC, parameters, environments, installs or uploads.
- A fresh official check separates stable Server Release identity from current
  official repository skill identity. Same-version asset replacement is detected
  by asset ID/size/SHA-256, not just version strings.
- Staging rechecks the pinned plan, verifies downloads, preserves old local bytes
  and binds the candidate explicitly to new complete Server tools. It never
  executes downloaded code, activates a skill, installs dependencies, modifies
  the old installation or migrates an existing run.

## Automated validation

Targeted commands from `GPM2.0/`:

```bash
python3 -m unittest discover -s server/tests -p 'test_agent_skill*.py'
python3 -m unittest discover -s server/tests -p 'test_official_skill_update.py' -v
```

31 fixture/binding/offline-update tests and 18 official-update tests pass (49 total).
The latter use mocked official APIs and bytes, not third-party network services.
They exercise no-write checking (including no import-bytecode side effect), pinned
identities, missing digests/foreign origins, republished assets, blob tampering,
links/submodules, bounded downloads/unpacking, unsafe tar entries, cleanup,
explicit new tools binding and byte-preserved old notes/legacy local state.
Existing tests cover relocation, no fallback searches and refusal to overwrite.

Full Server regression from `GPM2.0/` passed **204 tests**. The skill frontmatter
validator and all nine local skill-reference links pass. Existing runner tests
emit unclosed-file ResourceWarnings; no test failed.

## Live official download check (before publishing v3)

The isolated retained test root is:
`/home/xbzhang/tmp/gpm-skill-v3-official-update-6wt70ix2/`.
It contains a copied installation and a clearly synthetic byte-preservation note,
not newly asserted scientific advice. Historical WSL/Pi projects and remote
installations were not modified.

- Queried stable `v2.0.10` asset SHA-256:
  `28cf865759cf62928967390ea41048d321334deca6021ff2942d12ef7227c677`.
- At this pre-publication check, official repository skill was v2 at
  `05f67d00eef16f41af066d896973b324ebe70b2b`; local unpublished v3 was not called
  the official latest. The helper downloaded exactly that reviewed/pinned source.
- Stage completed as `staged-not-activated`; old installation hashes unchanged,
  local note bytes identical, candidate binding resolves to downloaded Server.
- New Server `run.sh --help` returned 0. No environment install/change or genome
  pipeline was run. This confirms retrieval/staging/help, not functional or
  biological-quality acceptance.
- Plans, stdout/stderr, original hashes and verification JSON remain under that
  root. A post-publication check can independently fetch v3 by its new pinned
  commit without altering the historical pre-publication evidence.

## Agent-behavior boundary

No Pi/subagent run was invoked for this revision. Natural-language judgment of
“worth recording” and actual instruction adherence require a separately authorized
agent-behavior test; helper tests are not evidence of those decisions. Suggested
cases: save a verified reusable repair without a mode/save prompt; omit routine
success/unsupported hypotheses; revise a duplicate; obey explicit no-write;
ignore log-injected permissions; preserve notes on upgrade and qualify stale
advice. Updater staging success is not activation, environment readiness, workspace
migration or permission to publish/replace official Release assets.

## Follow-up three-host runtime test

The user subsequently requested WSL, 140 and 180 testing. The current main agent
performed that follow-up; see [three-host evidence](agent-skill-v3-three-hosts.md)
and its JSON. This does not change the no-independent-Pi-test boundary above.
Remote direct online checks timed out; their offline and pipeline successes remain
separate outcomes, including the documented LSF interactive-client exit caveat.
