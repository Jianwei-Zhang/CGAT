# 质量门禁

GPM2.0 使用仓库内脚本作为本地开发、Pull Request、`master` 和安装包发布的
统一质量契约。脚本遇到首个失败命令即退出，不负责安装依赖，也不会修改测试夹具。

## 权威命令

在 Windows 宿主机的项目根目录执行桌面端与 Rust 门禁：

```powershell
pwsh -NoLogo -NoProfile -File scripts/quality-gate-windows.ps1
```

从 WSL 调用同一个宿主机门禁：

```bash
'/mnt/c/Program Files/PowerShell/7/pwsh.exe' \
  -NoLogo -NoProfile \
  -File "$(wslpath -w "$PWD/scripts/quality-gate-windows.ps1")"
```

在 Linux 执行服务端门禁：

```bash
bash scripts/quality-gate-server.sh
```

Windows 门禁检查已跟踪文本文件的 LF 行尾、全部前端测试、前端生产构建，以及两个
Rust crate 的格式、严格 Clippy 和测试。Linux 门禁检查 LF 行尾、shell 语法、全部
服务端 Python 测试、专项 shell 测试和 GRT server-to-app 端到端契约。

完整 Windows 门禁需要 `python`、Node.js/npm、Rust、`rustfmt` 和 `clippy`；执行前先
在前端目录运行 `npm ci`。完整 Linux 门禁需要 `python3`、Bash、Node.js、Rust 和
`zip`。专项 shell 测试自带假的生信命令，无需安装真实比对工具链。

在 WSL 中，Rust 验证按项目规则交给 Windows 宿主机；仅检查服务端非 Rust 部分时可用：

```bash
GPM_SKIP_GRT_SERVER_APP_E2E=1 bash scripts/quality-gate-server.sh
```

该开关会打印醒目的 `SKIP`，代表本地门禁不完整；CI 和发布验证绝不设置此开关。

## 定向诊断

根据失败的分组名，仅重跑对应命令：

```bash
# 全部 59 个前端测试文件（门禁建立时共 809 项测试）
cd app/frontend && npm test

# 服务端 Python 测试（门禁建立时共 80 项）
python3 -m unittest discover -s server/tests -p 'test_*.py'

# 只读检查 GPM2.0 已跟踪文本文件的 LF 行尾
python3 scripts/check_line_endings.py
```

Windows 门禁执行的 Rust 命令为：

```powershell
cd app/backend
cargo fmt --all -- --check
cargo clippy --all-targets --locked -- -D warnings
cargo test --locked

cd ../src-tauri
cargo fmt --all -- --check
cargo clippy --all-targets --locked --no-default-features -- -D warnings
cargo test --locked --no-default-features
```

门禁建立时，backend Rust 测试为 116 项，Tauri Rust 测试为 7 项。测试数可以增长；
门禁会发现完整测试集，并不锁死这些数量。

## CI 与发布

`.github/workflows/quality.yml` 会在 Pull Request 和推送到 `master` 时执行同一组脚本。
`Release installers` 在创建 Release 和构建任何安装包之前调用可复用质量工作流，因此
发布流程无法绕过门禁。前端 `dist/`、Rust `target/`、临时测试工作区等构建产物继续
保持忽略状态，禁止提交。
