# GPM2.0 Release Guide

## Version and build

- Keep the release version aligned in `app/frontend/package.json`, `app/frontend/package-lock.json`, `app/backend/Cargo.toml`, `app/backend/Cargo.lock`, `app/src-tauri/Cargo.toml`, `app/src-tauri/Cargo.lock`, and `app/src-tauri/tauri.conf.json`.
- Commit and push the release version before creating the matching `vX.Y.Z` tag.
- Build installers only with the GitHub Actions `GPM2.0 Release installers` workflow. Do not publish installers built locally.
- A completed release must contain exactly four verified assets: `win-x86`, `win-arm64`, `mac-x86`, and `mac-arm64`.

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

The macOS apps are ad-hoc signed but not Apple-notarized. Drag `GPM2.0.app` to `/Applications` before opening it. If macOS blocks the first launch, open **System Settings -> Privacy & Security** and choose **Open Anyway**. If that control is unavailable, run the following command only for the app downloaded from this official Release:

```bash
xattr -dr com.apple.quarantine /Applications/GPM2.0.app
```

### macOS 首次启动

macOS App 使用 ad-hoc 签名，但未经 Apple 公证。请先将 `GPM2.0.app` 拖入 `/Applications` 再打开。如果 macOS 阻止首次启动，请进入 **系统设置 -> 隐私与安全性** 并选择 **仍要打开**。如果该控件不可用，仅对从本项目官方 Release 下载的 App 执行：

```bash
xattr -dr com.apple.quarantine /Applications/GPM2.0.app
```
````

## Publication checks

- Confirm the quality job and all four installer jobs succeeded for the release workflow.
- Confirm the Release title is `GPM vX.Y.Z`, the tag and embedded app version match, and exactly four installer assets are present.
- Review the published body to ensure English precedes Chinese and both macOS first-launch sections remain intact.
