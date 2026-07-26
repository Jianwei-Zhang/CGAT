---
title: DEGAP 工具
description: 使用 DEGAP v2 进行 gap filling、contig linking 和 telomere extension
---

# DEGAP 工具

DEGAP v2（Dynamic Elongation of a Genome Assembly Path）运行于 Linux，使用 HiFi 和/或 ONT long reads 对特定 gap、contig 边缘或 chromosome ends 进行延伸和完善。

## 运行环境

推荐根据 `DEGAP2.0/environment.yml` 创建独立环境：

```bash
cd CGAT/DEGAP2.0
micromamba env create -f environment.yml
micromamba activate degap_env
```

至少提供 `--hifi` 或 `--ont` 之一；两者都可以接收一个或多个 FASTA/FASTQ 文件及其 gzip 压缩版本。

## 模式概览

| 模式 | 适用任务 |
|---|---|
| GapFiller | 已知 gap 左、右两端序列时，针对一个 gap 进行延伸与填补 |
| CtgLinker | 从包含 gap 的 contig 集合出发，延伸边缘并尝试连接 contig |
| TelSeeker | 针对指定 chromosome ends 执行端粒方向的序列延伸 |
| AutoGapfiller | 检测 whole-genome assembly 中的 gap 并组织并行任务 |

对于各模式，建议设置 `--MaximumExtensionRound 25`，避免明显无法收敛的任务长期运行。`--kmer_filter` 适合大规模 reads 数据以降低资源消耗；小中型数据或优先追求精度时可以不启用。

## GapFiller {#gapfiller}

```bash
python bin/DEGAP.py --mode gapfiller \
  --seqleft /path/to/gapLeftSequence.fasta \
  --seqright /path/to/gapRightSequence.fasta \
  --hifi /path/to/HiFiReads.fa \
  --ont /path/to/ONTReads.fa \
  --out /path/to/Output \
  --flag left \
  --MaximumExtensionRound 25 \
  --kmer_filter \
  -t 20
```

<TutorialVideo id="07-01-degap-gapfiller" />

该视频同时展示 GPM Next 中的 DEGAP 设置入口。界面中的 DEGAP、HiFi/ONT reads 与 `GPM_server` 路径指向 Linux 服务端资源；客户端用于整理和导出任务，计算仍在配置好 DEGAP 环境的服务端执行。

## TelSeeker {#telseeker}

先检查 chromosome ends：

```bash
python bin/TelSeekerCheck.py \
  --genome /path/to/genome.fasta \
  --motif TTAGGG \
  --out /path/to/telomere_check
```

人工复核 `genome.telomere.check.csv`、`need_extension_chr_end.txt` 和 `uncertain_chr_end.txt` 后，再运行 TelSeeker：

```bash
python bin/DEGAP.py --mode telseeker \
  --genome /path/to/genome.fasta \
  --motif TTAGGG \
  --target_ends /path/to/need_extension_chr_end.txt \
  --hifi /path/to/HiFiReads.fa \
  --out /path/to/Output \
  --telo-read-stringency normal \
  --MaximumExtensionRound 25 \
  -t 20
```

如果 Step 1 报告没有找到 telomeric reads，可以在确认输入与 motif 后尝试 `--telo-read-stringency relaxed`。

<TutorialVideo id="07-02-degap-telseeker" />

TelSeeker 任务同样需要在服务端核对 genome、reads、motif 与目标 chromosome ends，不能只根据客户端界面中的默认值直接运行。

## CtgLinker 与 AutoGapfiller

CtgLinker 使用 `--mode ctglinker --ctgseq <contigs.fasta>`；AutoGapfiller 使用 `bin/AutoGapfiller.py --genome <genome.fasta>`。这两个模式尚无本站视频，但命令行功能已经包含在 DEGAP v2 中。

运行完成后应检查每个任务的结果文件、日志和可视化报告，再决定是否将延伸序列加入 GPM Next 项目。
