# GPM2.0 Server

**中文** | [English](README.md)

## 快速开始

```bash
# 1. 安装并验证独立环境
bash install.sh

# 2. 使用安装程序最后打印的命令激活环境，例如
mamba activate cgat-server

# 3. 准备一个项目工作目录
bash prepare.sh \
  --ref /path/to/reference.fa \
  --ds /path/to/assembly.fa \
  -o ./gpm_server

# 4. 执行计算并生成交付包
bash ./gpm_server/run_all.sh
```

成功结束时会明确显示 `Final delivery packages` 摘要。最终只交付
`gpm_server.zip`（Full，含 FASTA 和报告）与 `gpm_server.light.zip`（Light，不含 FASTA、
包含报告）两个文件；两者都内置完整的 `gpm_server/report/` 目录，不再单独生成
报告 ZIP。本地报告仍可在 `gpm_server/report/report.html` 直接打开。

`--ref` 和可重复使用的 `--ds` 都支持 `<名称> <fasta>` 与仅传 `<fasta>`
两种写法。省略名称时，会从 FASTA 文件名自动推导：不区分大小写地移除
`.gz` 及一个 `.fa`、`.fasta` 或 `.fna` 后缀；名称中除字母、数字、点、
下划线和连字符以外的连续字符会替换为 `_`。需要自定义名称时仍可使用显式写法：

```bash
bash prepare.sh \
  --ref reference /path/to/reference.fa \
  --ds assembly /path/to/assembly.fa \
  -o ./gpm_server
```

安装成功时会明确显示 `GPM Server installation: READY`。以后可执行以下命令只检查、不修改环境：

```bash
bash install.sh --check
```

安装程序依次查找 `mamba`、`micromamba`、`conda`。需要明确选择时使用：

```bash
bash install.sh --manager conda
```

### ARM64 与集群环境

安装器在 Linux ARM64（`aarch64`/`arm64`）上使用独立依赖清单，固定
`blast=2.16.0` 以解决包可用性。Linux ARM64 和 x86_64 统一使用
`meryl=1.4.2`，避开 ARM64 上已复现的 1.4.1 多线程崩溃问题。
部署时请复制完整 `server/` 目录。

如果使用集群 module，需在作业脚本中加载匹配架构的工具及运行库，
并确保 Merqury 安装要求的 `MERQURY` 环境变量已设置。`command -v`
能找到程序不代表程序能正常启动；`GLIBCXX_* not found` 表示 C++ 运行库
不匹配，应加载匹配的 GCC runtime 或使用安装器创建的独立环境。
执行 `prepare.sh` 和 `run_all.sh` 时使用同一套环境。

外部 QC 命令失败时，Server 主日志会保留其 stdout/stderr 尾部，
即使失败的临时 QC 目录随后被清理，也可查看底层报错。

## 文件用途

| 文件 | 用途 | 何时执行 |
| --- | --- | --- |
| `install.sh` | 创建、更新并验证 `cgat-server` 环境 | 首次安装或依赖更新时 |
| `env.sh` | `install.sh` 的兼容入口 | 仅供旧命令继续使用 |
| `prepare.sh` | 检查输入和工具，生成一个项目的 `gpm_server/` 工作目录 | 每个新项目一次 |
| `export_final_path_fasta.sh` | 根据 App 导出的 Final Path TSV 重建 FASTA | 流程后期按需使用，不是安装步骤 |

`prepare.sh` 只负责准备项目；真正的计算由其生成的 `gpm_server/run_all.sh` 执行。

完整参数和客户端说明见仓库上一级的 `README_zh.md`。
