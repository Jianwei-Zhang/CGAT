# Installation and coordinated updates

## Sources: docs first, GitHub Release on failure

- Primary: `https://riceome.hzau.edu.cn/cgat/`.
- Fallback: `https://github.com/Jianwei-Zhang/CGAT/releases/latest`.
- Repository skill source: `https://github.com/Jianwei-Zhang/CGAT/tree/master/GPM2.0/server/skills/gpm-server`.

Use the complete `skills/gpm-server/` from the **same stable Server source archive**
for normal installation/update. Do not combine repository-current skill files with
an older Release runtime and call them an aligned release.

`scripts/official_download.py` reads docs `build-info.json` and its relative
`releaseAssetManifest`, or falls back to the GitHub Release API when that fails.
It obtains the tag, source filename, size and SHA-256 without needing GitHub when
docs works. Downloads try docs first, then GitHub on timeout, transfer error or
size/digest mismatch. The fallback must match the **same pinned identity**; a
mirror mismatch is never permission to skip verification. Fail when neither
source verifies. A working mirror is the version authority for that check;
synchronization lag cannot be ruled out without contacting GitHub. An installed
newer version/build is never downgraded. Same-version refreshed assets are detected
by file hashes and `SOURCE.json` revision, not only the version label.

The HTTPS allowlist, request timeouts, compressed/unpacked size limits, safe tar
paths and per-file source manifest validation apply to both sources. No tokens,
agent settings, SSH keys, local notes or project data are read for network access
or uploaded. No third-party proxy or unverified download execution is a fallback.

## First install and binding

Ask for an existing tools path first. If absent, offer `~/bin/GPM_Server` or the
user's own destination. Use `bash "$SKILL/scripts/install_tools.sh"` after agreeing
installation scope; it asks for the destination and confirmation, verifies the
bundle, refuses an existing directory and records the absolute tools binding.
It separately asks before `install.sh` changes the dependency environment, including
its possible micromamba bootstrap/Bash initialization. Do not automatically reinstall
an existing managed or site-module environment.

For existing tools, run `server_tools_path.sh --set /actual/absolute/path` to validate,
bind and register the installed skill. Registration is stored in
`TOOLS/.gpm-server-skills.json`; it is explicit, not a scan of agent directories.
Old registrations for moved/rebound skills are reported and not followed to a
new tools installation. Current bindings and installed paths always override the
new-install default. Keep project outputs outside `~/bin/GPM_Server`.

## One update command

```bash
bash "$SKILL/scripts/update.sh"
# Or: bash /actual/GPM_Server/update.sh
```

Keep the caller's cwd inside the intended project to include its `.prepare_lib/`.
The nearest ancestor with project markers is validated; other projects are not
scanned. Legacy projects inside a separate, unmanaged subdirectory of tools are
supported; projects overlapping managed code directories are refused. New workspaces record `.prepare_lib/server-tools.path` and `SOURCE.json`.
A conflicting binding stops the update; a legacy missing binding is shown in the
plan and recorded only after confirmation. Legacy merged-Step2/3 plans are not
migrated. All prepared `lib/`, Python tools/core and JSON contracts are aligned;
generated scripts, inputs, caches, outputs and logs are not rewritten.

No arguments. A matching installation is reported without asking; otherwise the
plan asks `[y/N]`. Only `Y/y` proceeds. Blank/negative/EOF/noninteractive input leaves
installations untouched. Do not automate an affirmative answer for the user.
Temporary verified downloads may be created for checking, then discarded.

The updater preserves both bundled and registered skills' entire `local/` trees
and saved tools bindings. Manifest-known custom edits cause a stop; legacy files
without a baseline are explicitly listed for review before approval. Manifest-owned
retired files are removed only when their original hash still matches; unlisted
user files remain. Dependency-spec changes stop the code-only update for separate
environment/compatibility review. Updates never resume scientific computation.

Stop affected jobs on **all nodes** before confirming. Locks and local Linux process
inspection protect normal runs; they cannot detect every remote standalone process
or prevent a new independent command from starting after inspection. No lock stealing.
A write/verification failure attempts all-root rollback. Each successful update keeps
`.run_all/server-update-*/` under the project, or under tools for a tools-only update.
The printed advanced rollback command is `python3 /actual/GPM_Server/tools/update_server.py
--rollback /absolute/backup`; quote paths containing spaces. Rollback refuses files
changed since the update. Keep the environment unchanged and reload the agent session
after successful skill updates; a retained note still needs scope revalidation.

## Older installations without update.sh

Do not reinstall over an old tools directory. Install this whole skill first and
bind/register the existing tools. Use the advanced, non-activating helpers once:

```bash
python3 "$SKILL/scripts/official_update.py" check --installed "$SKILL" > /tmp/gpm-update-plan.json
python3 "$SKILL/scripts/official_update.py" stage \
  --plan /tmp/gpm-update-plan.json --installed "$SKILL" --out /a/new/staging-directory
```

Use an explicit new staging path outside agent discovery; check/stage use the same
docs-first bundle source and never activate it. Inspect the staged report, manifest
and impact. After user approval to use the verified updater, run from the target
project: `python3 /a/new/staging-directory/GPM_Server/tools/update_server.py
/actual/old/GPM_Server`. It checks again and asks `[y/N]` before changing anything.
After this one-time adoption, use the single `update.sh` entrypoint. The staged skill
is not an installed/active skill. Keep staging out of agent discovery roots.

`stage_skill_update.py` remains an offline candidate helper for trusted local bundles;
it preserves `local/` but does not activate a candidate. Legacy v1 Python APIs in
`official_update.py` exist for historical fixtures/plans, not the normal CLI route.
This skill does not authorize publishing official Releases or altering site content.
