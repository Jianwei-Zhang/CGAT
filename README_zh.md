# CGAT — 完整基因组组装工具集

[English](README.md) | **中文**

[![CGAT Docs](https://img.shields.io/badge/在线文档与直连下载-riceome.hzau.edu.cn-0f766e)](https://riceome.hzau.edu.cn/cgat/zh/)
[![GitHub Releases](https://img.shields.io/badge/Releases-v2.0.12-2563eb)](https://github.com/Jianwei-Zhang/CGAT/releases)

**CGAT（Complete Genome Assembly Toolkit）** 是面向染色体级基因组组装、多组装共线性复核与长读段定点精修的一体化工具集。它将 Linux 服务端的高通量比对与自动修复（**GPM2.0 服务端**）、Windows / macOS 桌面端的交互式证据检查与路径编辑（**GPM2.0 桌面端**），以及基于 HiFi / ONT 长读段的缺口补洞与端粒延伸（**DEGAP2.0**）紧密衔接在一起。

![CGAT 工作流总览](GPM2.0/app/readme-assets/cgat-main-figure.svg)

---

## 核心组件

| 组件 | 运行平台 | 核心职责 | 文档入口 |
| --- | --- | --- | --- |
| **GPM2.0 服务端** | Linux | 将多套 *de novo* 组装与参考基因组比对，完成染色体分配、GRT 自动修复与证据打包，输出 `Full` / `Light` 交付包与自包含 `report.html` 报告。 | [GPM2.0 指南](GPM2.0/README_zh.md) · [服务端手册](GPM2.0/server/README_zh.md) |
| **GPM2.0 桌面端** | Windows / macOS | 导入服务端交付包，提供染色体级 **Preview** 来源总览、**Assembly** 主视图与 **Subview** 局部比对、**Final Path** 编辑、`DEGAP-JOBS` 任务导出及多格式结果导出。 | [GPM2.0 指南](GPM2.0/README_zh.md#桌面端-app) · [在线文档](https://riceome.hzau.edu.cn/cgat/zh/guide/getting-started) |
| **DEGAP2.0** | Linux | 利用 HiFi 和/或 ONT 长读段进行局部缺口补洞（GapFiller）、contig 连接（CtgLinker）与染色体端粒延伸（TelSeeker）。 | [DEGAP2.0 指南](DEGAP2.0/README.md) · [在线文档](https://riceome.hzau.edu.cn/cgat/zh/guide/degap) |

---

## 快速开始

### 1. 在 Linux 运行 GPM2.0 服务端

下载并安装 `GPM_Server` 至 `~/bin/GPM_Server`（优先使用国内文档站直连下载，失败时自动回退 GitHub Release），随后在项目目录下运行完整流程：

```bash
# 下载、解压并安装独立的 cgat-server 环境
SERVER="$HOME/bin/GPM_Server"
(
  set -euo pipefail
  mkdir -p "$(dirname "$SERVER")" && mkdir "$SERVER" && cd "$SERVER"
  archive=GPM_Server_2.0.12_source.tar.gz
  curl -fL --connect-timeout 8 --max-time 60 -o "$archive" \
    "https://riceome.hzau.edu.cn/cgat/downloads/v2.0.12/$archive" ||
    curl -fL --connect-timeout 8 --max-time 60 -o "$archive" \
      "https://github.com/Jianwei-Zhang/CGAT/releases/download/v2.0.12/$archive"
  tar -xzf "$archive" --strip-components=1
  bash ./install.sh
)

# 按安装程序提示激活环境（micromamba / mamba / conda）
micromamba activate cgat-server

# 运行比对、GRT 修复、报告生成与归档打包
bash "$SERVER/run.sh" \
  --ref /path/to/reference.fa \
  --ds /path/to/primary_assembly.fa \
  --ds /path/to/auxiliary_assembly.fa \
  -o ./gpm_server \
  -t 10
```

运行完成后将生成 `gpm_server.tar.gz`（Full 完整包）、`gpm_server.light.tar.gz`（Light 轻量包）及 `gpm_server/report/report.html`。完整参数与 SHA-256 校验说明见 [GPM2.0/README_zh.md](GPM2.0/README_zh.md)。

### 2. 在 GPM2.0 桌面端复核与编辑（Windows / macOS）

1. 从 [CGAT 在线下载页](https://riceome.hzau.edu.cn/cgat/zh/downloads)（免 GitHub 直连）或 [GitHub Releases](https://github.com/Jianwei-Zhang/CGAT/releases) 下载对应架构的桌面端安装包（`win-x86`、`win-arm64`、`mac-arm64`、`mac-x86`）。
2. 导入 `gpm_server.tar.gz`、`gpm_server.light.tar.gz` 或官方演示包 `test_data.zip`。
3. 在 **Preview** 中浏览各染色体来源与缺口分布，进入 **Assembly** 与 **Subview** 核对共线性证据，在 **Final Path** 中编辑路径并导出 PNG、TSV、日志或 FASTA。

### 3. 使用 DEGAP2.0 进行长读段补洞与端粒延伸（按需）

针对剩余缺口或染色体末端，可从 **GPM2.0 桌面端** 导出 `DEGAP-JOBS` 任务脚本，或直接在 Linux 环境运行 **[DEGAP2.0](DEGAP2.0/README.md)**（支持 `GapFiller`、`CtgLinker`、`TelSeeker`、`TelSeeker Ctg` 与 `AutoGapfiller` 五种模式）。

---

## 文档与下载入口

- **官方文档站与国内直连下载**：<https://riceome.hzau.edu.cn/cgat/zh/>
- **GitHub Releases**：<https://github.com/Jianwei-Zhang/CGAT/releases>
- **GPM2.0 完整指南**：[中文](GPM2.0/README_zh.md) | [English](GPM2.0/README.md)
- **GPM2.0 服务端手册**：[中文](GPM2.0/server/README_zh.md) | [English](GPM2.0/server/README.md)
- **DEGAP2.0 用户指南**：[English](DEGAP2.0/README.md)

---

## 论文引用

如果在研究中使用了 **CGAT**、**GPM2.0** 或 **DEGAP2.0**，请引用以下文献：

- **GPM**：Zhang, J. et al. Genome Puzzle Master (GPM): an integrated pipeline for building and editing pseudomolecules from fragmented sequences. *Bioinformatics* **32**(20), 3058–3064 (2016). <https://doi.org/10.1093/bioinformatics/btw370>
- **DEGAP**：Huang, Y. et al. DEGAP: Dynamic Elongation of a Genome Assembly Path. *Briefings in Bioinformatics* **25**(3), bbae194 (2024). <https://doi.org/10.1093/bib/bbae194>

## 联系方式

如有问题或建议，欢迎通过 [GitHub Issues](https://github.com/Jianwei-Zhang/CGAT/issues) 反馈，或发送邮件至 <jzhang@mail.hzau.edu.cn>。
