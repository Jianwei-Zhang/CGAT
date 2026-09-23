# GPM2.0 Server

**中文** | [English](README.md)

## 快速开始

```bash
# 1. 安装并验证独立环境
bash install.sh

# 2. 使用安装程序最后打印的命令激活环境，例如
mamba activate cgat-server

# 3. 准备、计算并生成交付包
bash run.sh \
  --ref /path/to/reference.fa \
  --ds /path/to/assembly.fa \
  -o ./gpm_server
```

成功结束时会明确显示 `Final delivery packages` 摘要。最终只交付
`gpm_server.tar.gz`（Full，含 FASTA 和报告）与 `gpm_server.light.tar.gz`（Light，不含 FASTA、
包含报告）两个文件；两者都内置完整的 `gpm_server/report/` 目录，不再单独生成
报告 ZIP。本地报告仍可在 `gpm_server/report/report.html` 直接打开。

默认使用 pigz 多线程压缩为 `tar.gz`；`--archive-format zip` 可保留 ZIP 格式，App 支持两者。

`--ref` 和可重复使用的 `--ds` 都支持 `<名称> <fasta>` 与仅传 `<fasta>`
两种写法。省略名称时，会从 FASTA 文件名自动推导：不区分大小写地移除
`.gz` 及一个 `.fa`、`.fasta` 或 `.fna` 后缀；名称中除字母、数字、点、
下划线和连字符以外的连续字符会替换为 `_`。需要自定义名称时仍可使用显式写法：

```bash
bash run.sh \
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
执行 `run.sh` 时保持环境激活。

外部 QC 命令失败时，Server 主日志会保留其 stdout/stderr 尾部，
即使失败的临时 QC 目录随后被清理，也可查看底层报错。

`run.sh -t 32` 设置总计算线程预算；新准备的工作区会在独立比对任务之间
自动分配线程并行执行。

### Step3 gap 来源修复后的断点恢复

当连续 N 位于原始 contig 内部，或跨越多个路径片段时，旧版可能报错
`cannot map filtered Step3 gap back to q2`。Step3 现在会在过滤过程中
保留这些 gap 的来源，以及合并 gap 的全部原始来源。

已生成的工作区带有独立运行库副本。更新 Server 代码后，在当前目录执行：

```bash
workspace=/path/to/gpm_server
cp tools/grt_step23.py "$workspace/.prepare_lib/tools/grt_step23.py"
```

随后在原环境中重新运行或提交该工作区的 `run_all.sh`。保留原工作区和
缓存，流程可复用兼容的 MUMmer 原始比对，并重新生成修复后的阶段结果。

## 文件用途

| 文件 | 用途 | 何时执行 |
| --- | --- | --- |
| `install.sh` | 创建、更新并验证 `cgat-server` 环境 | 首次安装或依赖更新时 |
| `env.sh` | `install.sh` 的兼容入口 | 仅供旧命令继续使用 |
| `run.sh` | 自动准备并执行完整流程，已有工作目录按断点继续 | 首次运行或恢复 |
| `prepare.sh` | 兼容原有的仅准备命令 | 需要单独生成脚本时 |
| `export_final_path_fasta.sh` | 根据 App 导出的 Final Path TSV 重建 FASTA | 流程后期按需使用，不是安装步骤 |

重复同一条 `run.sh` 命令，或执行 `bash run.sh -o ./gpm_server` 即可恢复；已通过校验的结果会复用。生成的 `run_all.sh` 仍可直接执行。

`--max-fill <bp>` 设置 Step3 两轮优化补洞的长度上限，默认 `1000000`。已有工作目录可用 `bash run.sh -o ./gpm_server --max-fill 2000000` 调整；更换输入或其他准备参数时使用新的输出目录。

完整参数和客户端说明见仓库上一级的 `README_zh.md`。
