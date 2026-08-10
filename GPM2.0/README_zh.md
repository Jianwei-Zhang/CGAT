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
bash server/env.sh
```

脚本会复用 `mamba`、`micromamba` 或 `conda`；均不存在时，为当前用户无 sudo 安装 micromamba。随后按脚本打印的命令激活环境，例如：

```bash
micromamba activate cgat-server
```

再次运行 `env.sh` 会校验托管环境，仅在依赖配置变化时更新。

| 用途 | 安装或要求的命令 |
| --- | --- |
| 核心流程 | `python3`、`samtools`、`zip`、`gzip` |
| GRT Final Path | `minimap2`、`nucmer`、`delta-filter`、`show-coords` |
| 可选比对引擎 | `blastn` + `makeblastdb`，或 `winnowmap` + `meryl` |
| 可选 reads 质控 | `meryl`、`merqury.sh`、`craq`；仅传入 `--reads` 时使用 |

执行 `prepare.sh` 和生成的 `run_all.sh` 时都应保持该环境已激活。

### 2. 准备工作目录

显式指定输出目录的最简示例：

```bash
bash server/prepare.sh \
  --ref rice_IRGSP_1_0 /path/to/ref.fa \
  --ds hifiasm /path/to/hifi.fa \
  --ds flye /path/to/flye.fa \
  --ds canu2 /path/to/canu2.fa \
  -o ./gpm_server \
  -t 10
```

第一个 `--ds` 固定为 primary dataset，后续初始 `--ds` 为 support dataset。支持普通或 gzip 压缩的 `.fa`、`.fasta`、`.fna` 输入。

#### 通用参数

| 参数 | 必填 / 默认值 | 说明 |
| --- | --- | --- |
| `--ref <名称> <fasta>` | 必填，一次 | 参考基因组名称与 FASTA。 |
| `--ds <名称> <fasta>` | 必填，可重复 | 组装 dataset；第一个为 primary，后续为 support。 |
| `-o, --out <目录>` | `./gpm_server` | 服务端工作目录及生成脚本的位置。 |
| `-s, --score <0-100>` | `60` | 染色体分配的最小覆盖率百分比。 |
| `--aligner <引擎>` | `minimap2` | 主比对引擎：`minimap2`、`blastn` 或 `winnowmap`。 |
| `-t, --threads <数量>` | `10` | 写入生成命令的工作线程数。 |
| `--skip-self` | 关闭 | 跳过同 dataset 自比对；同 dataset Subview 将不可用。 |
| `--tel <motif> <次数>` | 可选，可重复 | 标记双链上的精确端粒样重复。例如 `--tel TTAGGG 20`。 |
| `--cen <fasta>` | 可选 | 参考着丝粒 FASTA；记录名必须以 `_centromere` 结尾，例如 `Chr01_centromere`。 |
| `--cen-min-len <bp>` | `10000` | 着丝粒比对最小长度。 |
| `--cen-min-identity <百分比>` | `80` | 着丝粒比对最小一致性百分比。 |
| `--reads <fastq>` | 可选，可重复 | 启用共享 Meryl 数据及逐 dataset Merqury/CRAQ 质控。 |
| `--grt-qc-memory-gb <数量>` | `80` | 可选 reads 质控的内存上限。 |
| `--grt-kmer-size <数量>` | `21` | 可选 reads 质控的 k-mer 大小。 |

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

### 3. 运行、恢复与监控

```bash
bash ./gpm_server/run_all.sh
```

该命令串行执行生成的计划，遇到首个错误即停止，复用前会重新校验 checkpoint，并在 `gpm_server/` 同级目录生成两个交付包：

| 交付包 | 内容与用途 |
| --- | --- |
| `gpm_server.zip` | 完整 App 包，包含 source/reference FASTA 与权威 q4 FASTA，可在客户端导出 FASTA。 |
| `gpm_server.no_fasta.zip` | 无 FASTA App 包，保留 `.fai`、metadata、Final Path、source-card 状态和 PAF 视图，可导入、浏览并导出 PNG/TSV。 |

恢复时无需附加参数，重新执行同一条 `run_all.sh` 即可。线程数固定为准备阶段的值；不支持运行时 `--threads`、`--from`、`--until` 或 `--stage` 覆盖。

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

新 dataset 会合并进服务端工作目录，但不会加入已经锁定的 GRT recipe，也不会改写预计算 Final Path；其 contig 仍可在 App 中手工编辑。

初次 `run_all.sh` 已自动生成两种交付包。仅在后续执行 `add_dataset.sh`、`add_ctg.sh` 等操作后按需重新打包：

```bash
bash ./gpm_server/package_full_zip.sh
bash ./gpm_server/package_light_no_fasta_zip.sh
```

新建桌面端工作区或完整重新导入时使用重新生成的完整包；追加包只用于已有工作区/项目。

## 桌面端 App

### 安装与导入

从 [GitHub Releases](https://github.com/Jianwei-Zhang/CGAT/releases) 下载与客户端架构匹配的安装包，然后导入任一服务端交付包。

交付包固定 primary/support recipe，并直接载入服务端预计算的 Final Path。项目级路径仍可编辑，并可继续进入 DEGAP 或导出流程。当前仅支持 v2 GRT 交付契约；v1 与非 GRT 包需要使用当前服务端脚本重新生成。

### 从无 FASTA 包导出 Final Path FASTA

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
