# GPM2.0 Release Guide

## Version and build

- Keep the release version aligned in `app/frontend/package.json`, `app/frontend/package-lock.json`, `app/backend/Cargo.toml`, `app/backend/Cargo.lock`, `app/src-tauri/Cargo.toml`, `app/src-tauri/Cargo.lock`, and `app/src-tauri/tauri.conf.json`.
- Commit and push the release version before creating the matching `vX.Y.Z` tag.
- Build installers only with the GitHub Actions `GPM2.0 Release installers` workflow. Do not publish installers built locally.
- A completed release must contain exactly four verified installer assets: `win-x86`, `win-arm64`, `mac-x86`, and `mac-arm64`.
- Carry forward previously published test-data attachments unchanged by default; absence from the immediately previous Release is not permission to omit them. New or changed test datasets require explicit approval. Name all test-data attachments in both release-note sections and verify their downloaded SHA-256 against the preserved original.

## Required preflight: Server commands and retained attachments

Before creating a new version tag:

1. Update the Server download/install and tool-update commands in all four guides: `README.md`, `README_zh.md`, `server/README.md`, and `server/README_zh.md`. Every active Release link, archive filename and extraction command must use the new version and match the Server asset being published. Do not rewrite historical validation records.
2. Inventory the previous Release's assets and inspect earlier official Releases for retained examples such as `test_data.zip`. If the immediately previous Release omitted the dataset, use the most recent official Release that contains it rather than repeating the omission. Record the source Release, asset name, size and SHA-256 before uploading anything.
3. Download the retained dataset and verify its archive integrity and SHA-256. Carry the exact bytes and original filename into the new Release; do not regenerate, rename, or silently omit existing test data. Removing or changing a retained dataset requires explicit user approval. Never delete earlier Releases' attachments as part of a new-version release.
4. Freeze the expected asset inventory before publication: four platform installers, the matching `GPM_Server_<version>_source.tar.gz`, and every retained/approved supplemental attachment. A workflow that builds only installers does not satisfy this inventory by itself.
5. Keep the new Release as a draft until the required jobs succeed and the expected assets and bilingual notes are ready. After publication, independently download every asset and compare name, size and SHA-256 with the uploaded file and GitHub metadata. Recheck the original dataset asset as well. Do not report release completion while any expected attachment or public-download check is missing.

## Release notes

For drafting, updating, condensing or reviewing Release Notes, use the project
skill `.agents/skills/changelog-generator/SKILL.md`, adapted from the
[upstream Changelog Generator](https://github.com/ComposioHQ/awesome-claude-skills/blob/master/changelog-generator/SKILL.md).
Do not invoke it for unrelated development or documentation. Its user-facing
summaries, categorization and noise filtering take precedence over older writing
conventions; do not maintain a duplicate style guide here.

- Write complete **English first, Chinese second**, with equivalent content and
  separate **Server / App** parts inside each language.
- Use the actual shipped App installers and Server source snapshot as separate
  baselines; do not present unshipped source changes as released installer features.
  For a Server-only refresh, state under App that installers are unchanged.
- Name the Windows x64 (`win-x86`)/ARM64 and macOS Intel/Apple Silicon (ARM64)
  downloads, and retain the test-data names and preservation scope.
- Preserve the following macOS first-launch text in each matching language section,
  including applicability to Apple Silicon / ARM64, while builds remain ad-hoc
  signed and not Apple-notarized.

This skill governs note-writing, not publication authorization. All existing
artifact-preservation, quality and publication checks in this guide still apply.

### Versioned archive and single source

- Keep final, actually published notes in `GPM2.0/releases/vX.Y.Z.md`, under Git.
  Use JSON-string YAML frontmatter: `version`, `published` (GitHub UTC date),
  `updated`, `summary_en`, `summary_zh`. The body contains `## English` followed
  by `## 中文`; each has Server, App, downloads and the required macOS notice.
  Keep unpublished drafts outside this version-file pattern.
- Generate localized docs and their newest-first index from that source; never
  edit the generated pages or maintain separate release text in docs. A same-version
  Server refresh updates its existing version entry/date, not a new App version.
- The docs archive initially covers v2.0.10–v2.0.12, with an earlier-release link.
  Earlier entries may be curated from published evidence later; do not invent them.
- For a newly approved release or refresh, update the canonical notes, regenerate
  docs, export the GitHub body from the same source, and publish/synchronize both
  destinations before reporting completion. Archive installation alone does not
  authorize rewriting historical GitHub Releases or changing any attachments.

```bash
# Run from the repository root. These commands are local and do not publish.
python3 GPM2.0/scripts/render-release-docs.py
python3 GPM2.0/scripts/render-release-docs.py --check
python3 GPM2.0/scripts/render-release-docs.py --release-body vX.Y.Z > /tmp/GPM-vX.Y.Z-notes.md
# Only within an authorized release/notes update, after the normal checks:
# gh release edit vX.Y.Z --notes-file /tmp/GPM-vX.Y.Z-notes.md
```

### Required macOS first-launch text

````markdown
### macOS first launch

This guidance applies to both Intel and Apple Silicon (ARM64) builds.

The macOS apps are ad-hoc signed but not Apple-notarized. Drag `GPM.app` to `/Applications` before opening it. If macOS blocks the first launch, open **System Settings -> Privacy & Security** and choose **Open Anyway**. If that control is unavailable, run the following command only for the app downloaded from this official Release:

```bash
xattr -dr com.apple.quarantine /Applications/GPM.app
```

### macOS 首次启动

以下提示同时适用于 Intel 和 Apple Silicon（ARM64）版本。

macOS App 使用 ad-hoc 签名，但未经 Apple 公证。请先将 `GPM.app` 拖入 `/Applications` 再打开。如果 macOS 阻止首次启动，请进入 **系统设置 -> 隐私与安全性** 并选择 **仍要打开**。如果该控件不可用，仅对从本项目官方 Release 下载的 App 执行：

```bash
xattr -dr com.apple.quarantine /Applications/GPM.app
```
````

## Publication checks

- Confirm the quality job and all four installer jobs succeeded for the release workflow.
- Confirm the Release title is `GPM vX.Y.Z`, the tag and embedded app version match, and exactly four installer assets are present, plus the matching Server source archive and all retained/approved supplemental attachments from the preflight inventory. Verify the four README guides point to that published Server archive.
- Review the published body to ensure English precedes Chinese, both macOS first-launch sections remain intact, and retained test-data filenames and provenance appear in both languages. Verify fresh public downloads, including the retained dataset.
- Finish with [Required final step: docs alignment](#required-final-step-docs-alignment); successful builds and verified GitHub assets alone are not release closure.

## Installer-only refresh of an existing version

For an approved same-version installer replacement, preserve the official tag,
Release title, target commit and original publication time. Keep all seven app
version locations unchanged; record the actual rebuild revision in the notes.

1. Back up the Release metadata, bilingual notes and existing assets, verifying
   their size and SHA-256 so the previous downloads can be restored.
2. Create a temporary **draft** Release and dispatch `release-installers.yml`
   from the reviewed, pushed source branch with that draft as its `tag` input.
   Do not publish the draft. This isolates the workflow's installer-deletion
   step from the official Release and keeps existing downloads available.
3. Wait for the full quality gate and all four installer jobs to succeed.
   Download and verify the staged assets, including version, type, size and
   SHA-256, alongside the workflow's native architecture/signing checks.
4. Upload the verified, newly timestamped installers to the official Release
   without overwriting old filenames. Verify fresh anonymous public downloads
   before deleting only the four superseded installer assets.
5. Preserve Server/test-data attachments and their identities/digests. Update
   both language sections with the rebuild revision and workflow run while
   retaining the platform list and both macOS first-launch sections.
6. Re-read the official Release and verify the final asset set and preserved
   metadata. Delete only the temporary staging draft and any tag it created;
   never move the official version tag. Retain local rollback/audit evidence.
7. Finish with [Required final step: docs alignment](#required-final-step-docs-alignment),
   including the refreshed installer filenames and download digests.

## Server-only source asset refresh

For a fix to published Server code or its bundled skill, update the existing
`GPM_Server_<version>_source.tar.gz` attachment as part of task closure. This is
not a desktop-installer rebuild or a version bump unless the user requests one.

1. Read current Release metadata and preserve the tag, target commit, title,
   original publication time, four installer assets and approved other attachments.
2. Run the applicable Server tests and wait for successful quality CI on the
   pinned source revision. Export only tracked `server/` files with a
   `GPM_Server/` archive root; exclude environments, caches and user-local notes.
   Include `SOURCE.json` with release, Git revision/tree, build time and CI run.
   Also include a `files` map keyed by each tracked Server-relative file path,
   with its SHA-256 and numeric mode (`420` for 0644 or `493` for 0755). Exclude
   `SOURCE.json` itself from that map. The code-only tools/workspace updater
   requires this manifest; verify the map against the same pinned Git tree.
3. Keep the previous source attachment and Release metadata locally for rollback.
   Replace only the approved source attachment, preserving its public filename.
   Follow the changelog-generator skill to consolidate the refresh into the Server
   part of each language section, rather than stacking per-commit audit bullets.
   State under App that installers are unchanged, and retain the platform list,
   test-data scope and both macOS first-launch instructions.
4. Download the replacement through its public Release URL. Verify gzip/tar
   integrity, safe paths, size, API/upload/download SHA-256 equality, and every
   packaged source file against the pinned Git tree. From a fresh extraction,
   check `run.sh --help`, the relative skill binding and applicable skill tests.
5. Re-read the Release and confirm only the intended asset/notes changed. Record
   the source revision, quality run, asset identity/digest and validation boundary.
   Public-download verification is required but does not replace docs alignment.
6. Finish with [Required final step: docs alignment](#required-final-step-docs-alignment),
   updating the existing version entry and source-archive mirror without implying
   that unchanged App installers were rebuilt.

## Required final step: docs alignment

Docs alignment is the **last required closure step** after GitHub publication and
public-asset verification. It applies to new versions, same-version installer
refreshes, and Server-only source refreshes. Prepare documentation earlier when
needed, but reconcile it against the **actually published** assets and notes at
the end. Do not report a release/update complete while docs are stale or pending.

1. **Reconcile the release source and bilingual changelog.** Update
   `GPM2.0/releases/vX.Y.Z.md` to match the final published scope, export the GitHub
   body from that source, and regenerate the English/Chinese changelog pages and
   index. For a same-version refresh, update the existing entry and `updated`
   date rather than inventing a new version. Preserve the separate shipped App
   and Server baselines, retained test-data scope and macOS first-launch guidance.
2. **Align downloads and mirrors.** Reconcile `docs/en/downloads.md`,
   `docs/zh/downloads.md`, and the site's download mirror, `release.json` and
   `SHA256SUMS` with the verified official assets: version, filenames, platform,
   size and SHA-256. Refresh same-version bytes/digests too; an unchanged tag or
   filename is not evidence that a cached archive is current. Read
   `docs_deploy/sync-release-downloads.py` before using it: it selects the latest
   stable Release, so do not use it blindly for an older-version or prerelease
   update, or replace the site's current default downloads unintentionally.
3. **Align the affected bilingual guides.** Review installation, quick start,
   Server/tool updates, commands, options and workflow descriptions against what
   actually shipped. Keep the four project/Server README guides consistent with
   the affected `docs/en/` and `docs/zh/` pages; update only relevant content.
   Do not document unshipped source features as installed App behavior or rewrite
   historical validation records.
4. **Validate locally, then publish within authorization.** From the repository
   root, run the changelog regression tests and generated-page check:

   ```bash
   python3 -m unittest discover -s GPM2.0/scripts -p 'test_render_release_docs.py'
   python3 GPM2.0/scripts/render-release-docs.py --check
   ```

   Follow the current `docs_deploy/README.md` and
   `docs_deploy/FORMAL_DEPLOYMENT.md` for
   formal-site build, backup, publication, HTTP verification and source archival.
   Use the docs toolchain's own host/dependencies, not the GPM App frontend's
   `node_modules`. Before remote access, confirm the documented target with
   `ssh -G`, then verify hostname and service paths after connecting. Back up
   affected files and record SHA-256 and rollback steps before publication.
   This checklist does not itself authorize production deployment or changes to
   unrelated assets; if authorization/access is missing, report docs alignment
   as pending rather than bypassing the deployment gate.
5. **Verify the formal site and record closure evidence.** Check both languages'
   download pages, changelog index/version entry, affected guides and translation
   links. Compare the served content with the verified build, and verify fresh
   site-hosted downloads against the official asset sizes/SHA-256, including
   retained test data. Do not substitute a local build, Git push or development
   preview for formal-site verification. Record the release tag, App/Server
   source baselines, docs source snapshot/digest, deployment/backup identifiers,
   online checks and any outstanding items. The docs source and deployment
   workspace are currently ignored by Git; use the deployment source archive
   rather than force-adding ignored site files, backups or credentials. Distinguish
   source/automated/HTTP evidence from browser or native-App visual acceptance.

**Completion gate:** the published Release, canonical notes, bilingual docs and
formal-site downloads agree, and the required verification evidence is recorded.
If any check or deployment is still pending, report the Release as published but
**docs alignment incomplete**, not as a completed release/update.

## Signed in-app updates

See [App update delivery](APP_UPDATES.md) before the first updater-enabled release.
The desktop checks docs first and contacts GitHub only on failure. CI must provide
`GPM_UPDATER_PUBLIC_KEY` and the Tauri signing secrets; it generates signed updater
artifacts, `latest.json`, and separate English/Chinese notes. Existing manual
installers, Server source and retained datasets remain required. Additional updater
assets do not replace any of those deliverables.

The installer workflow refuses published-release replacement and leaves new
Releases as drafts. After all four platform bundles and the ordinary release
inventory are verified, stage every referenced file on docs and promote its
`downloads/updates/latest.json` **last**. Do not advertise an incomplete release.
A successful but stale docs manifest intentionally does not query GitHub; keep
both feeds synchronized. Do not rotate the signing key or enable downgrade updates
as part of an ordinary release. A Server-only source refresh must not change the
App version or regenerate its updater artifacts.
