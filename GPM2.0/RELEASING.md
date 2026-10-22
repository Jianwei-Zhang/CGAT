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

- Describe changes relative to the installers users received in the previous Release. If those assets were replaced after the tag was created, use the replacement workflow run's `headSha` as the comparison base so already shipped work is not repeated.
- Write a complete English section first and a complete Chinese section second.
- Use the headings `Updates since vX.Y.Z` and `相对 vX.Y.Z 的更新`.
- Group related commits into a short list of user-visible changes. Keep the notes concise even when the commit range is large.
- State that installers are provided for Windows x86/ARM64 and macOS x86/Apple Silicon.
- Retain the macOS first-launch sections below while releases use ad-hoc signing without Apple notarization.

### Required macOS first-launch text

````markdown
### macOS first launch

The macOS apps are ad-hoc signed but not Apple-notarized. Drag `GPM.app` to `/Applications` before opening it. If macOS blocks the first launch, open **System Settings -> Privacy & Security** and choose **Open Anyway**. If that control is unavailable, run the following command only for the app downloaded from this official Release:

```bash
xattr -dr com.apple.quarantine /Applications/GPM.app
```

### macOS 首次启动

macOS App 使用 ad-hoc 签名，但未经 Apple 公证。请先将 `GPM.app` 拖入 `/Applications` 再打开。如果 macOS 阻止首次启动，请进入 **系统设置 -> 隐私与安全性** 并选择 **仍要打开**。如果该控件不可用，仅对从本项目官方 Release 下载的 App 执行：

```bash
xattr -dr com.apple.quarantine /Applications/GPM.app
```
````

## Publication checks

- Confirm the quality job and all four installer jobs succeeded for the release workflow.
- Confirm the Release title is `GPM vX.Y.Z`, the tag and embedded app version match, and exactly four installer assets are present, plus the matching Server source archive and all retained/approved supplemental attachments from the preflight inventory. Verify the four README guides point to that published Server archive.
- Review the published body to ensure English precedes Chinese, both macOS first-launch sections remain intact, and retained test-data filenames and provenance appear in both languages. Verify fresh public downloads, including the retained dataset, before declaring completion.

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
3. Keep the previous source attachment and Release metadata locally for rollback.
   Replace only the approved source attachment, preserving its public filename.
   Add a concise refresh bullet in each existing language section; do not remove
   the installer-platform or macOS first-launch instructions.
4. Download the replacement through its public Release URL. Verify gzip/tar
   integrity, safe paths, size, API/upload/download SHA-256 equality, and every
   packaged source file against the pinned Git tree. From a fresh extraction,
   check `run.sh --help`, the relative skill binding and applicable skill tests.
5. Re-read the Release and confirm only the intended asset/notes changed. Record
   the source revision, quality run, asset identity/digest and validation boundary.
   Do not call the task closed until public-download verification is complete.
