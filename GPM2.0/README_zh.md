# GPM2.0

**中文** | [English](README.md)

GPM2.0 将多种 de novo 组装结果统一到以参考基因组为锚点的流程中，用于导入、浏览、轻量编辑和 Final Path 导出。

## 项目架构

| 组件 | 职责 |
| --- | --- |
| Linux 服务端 | 执行比对与 GRT 计算，生成 App 交付包。部署时上传仓库中的 `server/` 目录。 |
| 桌面端 App | 导入交付包，提供可视化、编辑、DEGAP 集成与导出。 |

`win-x86`、`win-arm64`、`mac-x86`、`mac-arm64` 安装包发布在 [GitHub Releases](https://github.com/Jianwei-Zhang/CGAT/releases)。开发和发布检查见[质量门禁](QUALITY_zh.md)。

## 服务端流程

![GPM 服务端流程](app/readme-assets/serve_pipeline_zh.png)

### 1. 创建环境

首次在 Linux 服务端执行：

```bash
bash server/install.sh
```

脚本会复用 `mamba`、`micromamba` 或 `conda`；均不存在时，为当前用户无 sudo 安装 micromamba。也可用 `--manager conda|mamba|micromamba` 明确选择。安装结束显示 `GPM Server installation: READY` 后，按脚本打印的命令激活环境，例如：

```bash
micromamba activate cgat-server
```

随时可以只检查、不修改环境：

```bash
bash server/install.sh --check
```

再次运行 `install.sh` 会校验托管环境，仅在依赖配置变化时更新；原 `env.sh` 入口继续兼容。只部署 `server/` 目录时，从其中的 [服务端快速入门](server/README_zh.md) 开始。

| 用途 | 安装或要求的命令 |
| --- | --- |
| 核心流程 | `python3`、`samtools`、`zip`、`gzip` |
| GRT Final Path | `minimap2`、`nucmer`、`delta-filter`、`show-coords` |
| 可选比对引擎 | `blastn` + `makeblastdb`，或 `winnowmap` + `meryl` |
| 可选 reads 质控 | `meryl`、`merqury.sh`；仅传入 `--reads` 时使用 |

执行 `run.sh` 时保持该环境已激活。

### 2. 运行完整流程

显式指定输出目录的最简示例：

```bash
bash server/run.sh \
  --ref /path/to/rice_IRGSP_1_0.fa \
  --ds /path/to/hifiasm.fa \
  --ds /path/to/flye.fa \
  --ds /path/to/canu2.fa \
  -o ./gpm_server \
  -t 10
```

`--ref` 和 `--ds` 均支持 `<名称> <fasta>` 与仅传 `<fasta>` 两种写法。省略名称时，会从 FASTA 文件名自动推导：不区分大小写地移除 `.gz` 及一个 `.fa`、`.fasta` 或 `.fna` 后缀；名称中除字母、数字、点、下划线和连字符以外的连续字符会替换为 `_`。例如 `/data/primary assembly.fa.gz` 会得到名称 `primary_assembly`；需要其他名称时仍可使用原有显式写法。

准备工作目录时，第一个 `--ds` 作为主 ds，其余 `--ds` 作为辅 ds；这些角色用于本次 GRT 计算并保持不变。支持普通或 gzip 压缩的 `.fa`、`.fasta`、`.fna` 输入。生成的 `add_dataset.sh` 同样支持名称可省略的 `--ds` 写法。

#### 通用参数

| 参数 | 必填 / 默认值 | 说明 |
| --- | --- | --- |
| `--ref [<名称>] <fasta>` | 必填，一次 | 参考基因组 FASTA；省略名称时从文件名自动推导。 |
| `--ds [<名称>] <fasta>` | 必填，可重复 | 初次输入的组装数据集；省略名称时从文件名自动推导。第一个为主 ds，其余为辅 ds。 |
| `-o, --out <目录>` | `./gpm_server` | 服务端工作目录及生成脚本的位置。 |
| `-s, --score <0-100>` | `60` | 染色体分配的最小覆盖率百分比。 |
| `--aligner <引擎>` | `minimap2` | 主比对引擎：`minimap2`、`blastn` 或 `winnowmap`。 |
| `-t, --threads <数量>` | `10` | 总计算线程预算，在独立比对任务及 reads QC 任务之间分配。 |
| `--skip-self` | 关闭 | 跳过同 dataset 自比对；同 dataset Subview 将不可用。 |
| `--tel <motif> <次数>` | 可选，可重复 | 标记双链上的精确端粒样重复。例如 `--tel TTAGGG 20`。 |
| `--cen <fasta>` | 可选 | 参考着丝粒 FASTA；记录名必须以 `_centromere` 结尾，例如 `Chr01_centromere`。 |
| `--cen-min-len <bp>` | `10000` | 着丝粒比对最小长度。 |
| `--cen-min-identity <百分比>` | `80` | 着丝粒比对最小一致性百分比。 |
| `--reads <fastq>` | 可选，可重复 | 启用共享 Meryl 数据及逐 dataset Merqury QV 评估；`--threads` 总预算会分配给各 dataset。 |
| `--grt-qc-memory-gb <数量>` | `80` | 可选 reads 质控的内存上限。 |
| `--grt-kmer-size <数量>` | `21` | 可选 reads 质控的 k-mer 大小。 |
| `--max-fill <bp>` | `1000000` | Step3 两轮优化补洞的长度上限；恢复时可修改。 |

#### 比对引擎专属参数

| 引擎 | 参数 | 可选值 / 默认值 |
| --- | --- | --- |
| `minimap2` | `--minimap-preset` | `asm10` 或 `asm5`；默认 `asm10` |
| `blastn` | `--blastn-task` | `blastn`、`megablast` 或 `dc-megablast`；默认 `blastn` |
| `blastn` | `--blastn-evalue` | 正数；默认 `1e-10` |
| `winnowmap` | `--winnowmap-preset` | `asm20`、`asm10` 或 `asm5`；默认 `asm20` |
| `winnowmap` | `--winnowmap-kmer` | 正整数；默认 `19` |
| `winnowmap` | `--winnowmap-repeat-fraction` | `(0, 1)`；默认 `0.9998` |

引擎专属参数只能与对应的 `--aligner` 一起使用。GRT 计算始终从 `PATH` 解析 `minimap2` 和 MUMmer4 命令。

### 3. 恢复与监控

```bash
bash server/run.sh -o ./gpm_server
```

该命令串行执行生成的计划，遇到首个错误即停止，复用前会重新校验 checkpoint，并在 `gpm_server/` 同级目录生成两个交付包：

| 交付包 | 内容与用途 |
| --- | --- |
| `gpm_server.tar.gz` | 完整 App 包，包含 source/reference FASTA、权威 q4 FASTA 和完整 `report/` 目录，可在客户端导出 FASTA。 |
| `gpm_server.light.tar.gz` | Light App 轻量包，不含 FASTA，保留 `.fai`、metadata、Final Path、source-card 状态、PAF 视图和完整 `report/` 目录，可导入、浏览并导出 PNG/TSV。 |

默认使用 pigz 多线程压缩为 `tar.gz`；`--archive-format zip` 可保留 ZIP 格式，App 支持两者。

这两个压缩包 是仅有的最终交付文件，不再单独生成报告 ZIP。可直接打开服务端工作目录或任一解压后交付包中的 `gpm_server/report/report.html`。`prepare.sh` 从输入准备阶段开始记录，`run_all.sh` 在阶段结束时更新报告；失败或中断也保留报告及尚未执行的阶段。GRT 首次发布的阶段事件与最终协调后的状态分别保留，缓存复用明确标注。重跑前一份报告保存在工作目录的 `.report_history/` 下。

为避免校验值引用包含自身的压缩包，报告记录嵌入 `report/` 之前的 App 数据载荷校验值。两个最终压缩包 完成后，`run_all.sh` 会明确打印其路径、大小、SHA-256、用途和本地报告路径；同一摘要也写入 `logs/run_all.log`。

复制或解压整个 `report/` 后，可在原工作目录不可访问、网络断开的情况下重新生成：

```bash
python3 /path/to/report/render_report.py
```

生成器只读取报告目录内的记录，不重新计算比对或修复。报告不携带原始 FASTA/reads；未测量的质量指标不显示为零。报告中的 gap 统计指连续至少 100 个 N，显式连接 gap 与 N 碱基总数分别记录。当前自动报告覆盖 `prepare.sh` 和 `run_all.sh`；单独执行增量脚本或打包脚本不会更新此前的运行报告。详见 [报告格式与边界](server/REPORT.md)。

首次 `run.sh` 会自动准备并运行完整流程；恢复时重复原命令，或仅指定 `-o`。原有 `prepare.sh` 和生成的 `run_all.sh` 仍兼容。线程数固定为准备阶段的值；不支持运行时 `--threads`、`--from`、`--until` 或 `--stage` 覆盖。

```bash
tail -F ./gpm_server/logs/run_all.log
```

当前单元状态写入 `gpm_server/logs/status.tsv`。同一工作目录同时只允许一个 runner。

### 4. 追加数据与重新打包

向已有桌面端工作区/项目追加一个 dataset：

```bash
bash ./gpm_server/add_dataset.sh \
  --ds ds4_name /path/to/ds4.fa \
  -o ./gpm_server/add_ds4_name.zip
```

新数据集会合并进服务端工作目录，但不参与已经完成的 GRT 计算，也不会改写预计算的 Final Path；其 contig 仍可在 App 中手工编辑。

初次 `run_all.sh` 已自动生成两种交付包。仅在后续执行 `add_dataset.sh`、`add_ctg.sh` 等操作后按需重新打包：

```bash
bash ./gpm_server/package_full_zip.sh
bash ./gpm_server/package_light_zip.sh
```

新建桌面端工作区或完整重新导入时使用重新生成的完整包；追加包只用于已有工作区/项目。

## 桌面端 App

### 安装与导入

从 [GitHub Releases](https://github.com/Jianwei-Zhang/CGAT/releases) 下载与客户端架构匹配的安装包，然后导入任一服务端交付包。

macOS App 使用 ad-hoc 签名，未经 Apple 公证。请先将 `GPM2.0.app` 拖入 `/Applications` 再打开。如果 macOS 阻止首次启动，请进入 **系统设置 -> 隐私与安全性** 并选择 **仍要打开**。如果该控件不可用，仅对从本项目官方 GitHub Release 下载的 App 执行：

```bash
xattr -dr com.apple.quarantine /Applications/GPM2.0.app
```

交付包保留 GRT 计算时确定的主 ds 与辅 ds 角色，并直接载入服务端预计算的 Final Path。项目级路径仍可编辑，并可继续进入 DEGAP 或导出流程。

### 项目数据集表格

新项目会在每段连续 `N`/`n` 处分割组装序列，单个 N 也参与分割。可编辑 ctg 不含 N，并保留来源坐标、方向、原始 gap 长度和同源片段的连接关系。gap 显示在片段之间，比对端点使用同一片段布局。原始 FASTA 和数据集统计不变。已有编辑项目不会自动拆分；新建项目即可使用这套初始化方式。全 N 序列保留在来源目录中，不生成空 ctg。Final Path 的来源片段会映射到新 ctg，并保持导出序列一致；缺少 CIGAR 的裁剪比对会标明近似投影。

项目页汇总参考、主组装、辅助组装及派生数据集的序列数、总长度、N50、N90。统计包含全部序列，不按 N 拆分，也不受组装视图中 contig 移动或隐藏的影响；Light 轻量包同样支持。

可编辑显示名称和备注，原始标识、文件名和序列名保持不变。

### 从 Light 轻量包导出 Final Path FASTA

先在 App 中导出 Final Path TSV，再将 TSV 放回保留原始 FASTA 的服务器：

```bash
bash server/export_final_path_fasta.sh \
  --tsv /path/to/project_Chr01_path.tsv \
  --gpm_server ./gpm_server \
  -o /path/to/project_Chr01_path.fa
```

`gpm_server/` 内生成的 helper 会自动识别工作目录：

```bash
bash ./gpm_server/export_final_path_fasta.sh \
  --tsv /path/to/project_Chr01_path.tsv \
  -o /path/to/project_Chr01_path.fa
```
