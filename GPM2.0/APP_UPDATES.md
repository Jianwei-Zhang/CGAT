# Desktop in-app updates / 桌面应用内更新

## English

### User contract

- Settings ends with **App updates**: current version, status, last successful
  check, manual check, and access to an available/downloaded update.
- After startup settles, check in the background (10-second initial delay,
  six-hour repeat). Defer automatic dialogs while another dialog/task is active.
- The docs feed and docs-hosted update files are authoritative. GitHub Releases
  contain only manual installers, Server source and retained data; they do not
  publish `app.tar.gz`, updater notes or `latest.json`. The legacy GitHub fallback
  in the v2.0.13 App is intentionally unavailable, so updates require the docs
  service to be reachable. A valid but stale docs feed is authoritative until
  synchronized.
- Do not launch a browser or ask the user to locate an installer. Download within
  the App, validate size/SHA-256 and the signed artifact/version, then offer
  **Install and restart**. System permission or installer UI may still appear.
- Installation is explicit, blocked while backend work is pending, and preceded
  by the existing checked project-state flush. A failed save stops installation.
  Downloading may continue in the background. Downloads live in memory for this
  session; restarting the App before installation requires downloading again.
- The dialog uses the existing `app-dialog`, buttons, theme tokens and typography.
  It loads only `en` or `zh`, following the App language. Notes are displayed as
  plain text, never executable HTML; a notes failure does not block downloading.
- **Do not remind me for 24 hours** persists an absolute expiry across restarts
  and suppresses all automatic offers during that interval. Manual checks bypass
  suppression. **Later** without the checkbox suppresses that version for the
  current session. No automatic installation or forced update.

### One-time signing setup (release owner)

Use the current Tauri 2 CLI to generate a dedicated updater key pair in a secure
location outside this checkout. Back up the private key securely. Never commit or
log it. Configure:

| Repository setting | Purpose |
| --- | --- |
| Variable `GPM_UPDATER_PUBLIC_KEY` | Base64 public key; embedded at compile time |
| Secret `TAURI_SIGNING_PRIVATE_KEY` | Matching private signing key |
| Secret `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Key password, if configured |

The updater intentionally stays disabled when the public key is absent (local
preview/quality builds). The release workflow fails before modifying a Release
if its signing configuration is absent. The empty config `pubkey` is not a trust
key: native code supplies the compiled public key. The updater plugin is pinned
at 2.14.0 for artifact/version verification and restore support, requiring Tauri
2.12 or later. Use a current Tauri 2 CLI that records `version:X.Y.Z` in the signed
trusted comment. Updater signatures are separate from Apple code signing/notarization
and Windows Authenticode; this does not change the existing macOS first-launch policy.

Do not rotate this key casually: already-installed clients trust the original
public key. No production key or repository secret is created by this code change.
The first updater-enabled release still needs a one-time manual install for users
of older builds that have no updater.

### Release and docs staging

1. Follow `RELEASING.md`, bump the App version, and finalize the canonical bilingual
   `releases/vX.Y.Z.md`. Never advertise a Server-only source refresh as a new App.
2. Run the approved installer workflow. Windows produces NSIS `.exe` + `.sig`;
   macOS retains the manual `.dmg` and adds `.app.tar.gz` + `.sig`. The final job
   independently verifies each signature against the configured public key using
   Minisign, then generates `latest.json` and `GPM_X.Y.Z_notes_en.txt` / `_zh.txt` from the single
   canonical notes source. It requires exactly one package per OS/architecture and
   embeds all four signatures in `latest.json`. CI then uploads a workflow artifact
   containing the four update packages, both localized notes and `latest.json` for
   docs staging, and removes those internal files plus the four `.sig` files from
   the public Release. The Release keeps only manual installers, Server source and
   retained data.
3. Verify the four update packages through the signatures embedded in
   `latest.json`, confirm none of the internal updater files remain on the Release,
   and verify notes, retained datasets and Server source before publishing. CI
   leaves the Release as a draft and refuses overwriting a published release. Do
   not show internal `.app.tar.gz`, notes or `latest.json` links on the public
   downloads page; those files are hosted only on the docs update mirror.
4. Download and extract the workflow artifact named `GPM app update vX.Y.Z`.
   Treat that directory as the verified updater staging input. Stage the feed with
   this tracked, offline helper (from repository root):

   ```bash
   python3 GPM2.0/scripts/app-update-feed.py stage \
     --assets /path/to/extracted-update-artifact --public docs/public
   ```

   This validates all referenced sizes/hashes/URLs, copies the versioned files,
   rejects version rollback or replacement of an immutable asset, then atomically
   replaces the local `docs/public/downloads/updates/latest.json`. It neither
   connects to production nor edits a GitHub Release.
5. In the separately authorized docs deployment, upload versioned files first,
   verify public bytes, and switch the production latest manifest last. Serve
   `/cgat/downloads/updates/latest.json` with revalidation/no-cache; versioned
   update assets may be cached immutably. The public GitHub Release intentionally
   has no updater manifest, so docs is the sole operational update source.
6. Verify real native upgrades on Windows x64/ARM64 and macOS Intel/Apple Silicon,
   including project preservation, install permissions/restart and signature
   rejection. Also verify that docs unavailability reports a clean update failure;
   GitHub fallback is intentionally not a shipped recovery path. Automated tests
   alone do not establish native desktop visual or installer acceptance.

The local deployment directory `docs_deploy/` is ignored and machine-specific;
this tracked helper is the reproducible integration point for its existing
release-download sync, not a new remote deployment authorization.

## 中文

### 使用行为

- 设置面板末尾增加“应用更新”：当前版本、状态、上次成功检查时间、手动检查及更新入口。
- 启动 10 秒后后台检查，此后每六小时检查一次；关键任务或其他弹窗进行时延后自动提醒。
- 清单、当前语言说明和更新包均由 docs 提供；GitHub Release 只保留手动安装包、Server
  源码和示例数据。docs 服务不可用时，应用内更新会明确失败，不再使用 GitHub 回退。
- 全程在 App 内下载、校验、确认安装；无需跳转网页或手动寻找安装包。系统可能仍要求权限确认。
- 安装前检查正在执行的操作并调用已有项目保存流程；保存失败则停止安装。下载可转后台，
  但本轮下载内容仅保存在当前进程内，退出后需要重新下载。
- 弹窗沿用已有组件样式和主题变量。只加载当前语言说明，使用安全的纯文本显示；说明失败不阻止下载。
- “24 小时内不再提醒”保存精确到期时间，重启有效；手动检查不受影响。未勾选只点“稍后”，
  当前会话不再自动提醒同一版本。不强制更新、不静默安装。

### 首次接入与发布

发布负责人需在仓库外安全生成、备份专用更新签名密钥，并配置上表中的仓库变量和 Secrets。
本次代码不创建生产密钥、不更改线上 Release；缺少公钥的开发构建明确显示更新未启用。
发布流程缺少签名配置时会在操作 Release 前停止。更新签名不等于 Apple 公证或 Windows
代码签名，不改变现有 macOS 首次启动要求。不要随意轮换密钥。

第一版含更新模块的 App 仍需旧用户手动安装一次，之后才可应用内升级。GitHub Release 只保留
四个手动安装包、Server 源码和示例数据；签名、macOS 更新包、更新清单和分语言说明由 CI
artifact 交给 docs 发布，并在公开 Release 前从附件列表清理。CI 保持 Release 为草稿，
禁止覆盖已发布版本。docs 使用上述 `stage` 命令离线校验并准备文件，实际部署仍需单独授权，
先上传版本文件并验证，最后切换最新清单。Server 同版本刷新不触发 App 更新。

上线前仍需真实原生升级验收，覆盖主题、项目保存、安装权限和重启；docs 不可用时还应确认
更新会明确失败。源码检查、自动化测试和构建通过不能替代这些验收。
