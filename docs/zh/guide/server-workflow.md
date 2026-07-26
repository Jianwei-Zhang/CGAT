---
title: 服务端数据准备
description: 运行 GPM Next 服务端比对并生成完整或轻量交付包
---

# 服务端数据准备

本页在 Linux 环境中执行。准备脚本会登记参考序列和多个 assembly dataset，生成后续比对命令、chromosome 分组结果和桌面端可导入的项目数据。

## 运行准备脚本

在 `GPM2.0/` 下执行：

```bash
bash server/prepare.sh \
  --ref rice_IRGSP_1_0 /path/to/ref.fa \
  --ds hifiasm /path/to/hifiasm.fa \
  --ds flye /path/to/flye.fa \
  --ds canu /path/to/canu.fa \
  --out /path/to/gpm_server \
  --aligner minimap2 \
  --minimap-preset asm10 \
  --threads 10
```

`--ref` 接收参考名称和 FASTA 路径；`--ds` 可以重复使用，每次登记一个 dataset。常用参数如下：

| 参数 | 说明 |
|---|---|
| `-o, --out` | 输出目录，默认为当前目录下的 `gpm_server` |
| `-s, --score` | chromosome 分配阈值，默认 `60` |
| `--aligner` | `minimap2`、`blastn` 或 `winnowmap`，默认 `minimap2` |
| `-t, --threads` | 生成的比对命令使用的线程数，默认 `10` |
| `--skip-self` | 跳过同 dataset self alignment |
| `--tel MOTIF MIN_REPEAT` | 扫描端粒样串联重复，可重复指定 |
| `--cen FASTA` | 可选的完整参考着丝粒 FASTA |

引擎专属参数只能与对应 `--aligner` 一起使用。传入不匹配的参数时，脚本会在写入输出前失败。

## 执行批量任务

```bash
bash /path/to/gpm_server/run_all.sh
```

执行顺序是严格的：

1. 完成所有 `*_vs_ref/result.paf`；
2. 执行 `assign_chr_groups.sh`；
3. 执行每个 `runs/chr_<chr>/command.sh`。

`run_all.sh` 已按这一顺序组织任务。如果改为手动调度或集群调度，仍需保持阶段依赖关系。

::: warning 关于 `--skip-self`
启用后，导入、方向矫正和跨 dataset Subview 仍可用，但同 dataset 的 contig-to-contig Subview 不可用。
:::

## 生成交付包

服务端会生成两个打包助手：

```bash
# 完整交付包：带有 final path FASTA 导出所需的序列载荷
bash /path/to/gpm_server/package_full_zip.sh

# 轻量交付包：不包含 .fa/.fasta 载荷
bash /path/to/gpm_server/package_light_no_fasta_zip.sh
```

| 能力 | 完整包 | 轻量包 |
|---|---:|---:|
| 导入与可视化检查 | ✓ | ✓ |
| PNG / TSV 导出 | ✓ | ✓ |
| 客户端 final path FASTA 导出 | ✓ | — |
| 体积 | 较大 | 较小 |

完整包不会重复携带原始单体 FASTA，而是保存 locator 清单引用的 partitioned FASTA。轻量包排除全部 `.fa` 与 `.fasta` 载荷。

## 向已有项目追加 dataset

完成初始服务端项目后，可以追加一个 dataset：

```bash
bash /path/to/gpm_server/add_dataset.sh \
  --ds new_dataset /path/to/new_dataset.fa
```

默认生成 `add_new_dataset.zip`。这是应用于已有桌面项目的追加包，不是用于新建项目的完整交付包。

如果需要一个已经包含新 dataset、可用于新建项目的完整包，请在追加完成后重新运行：

```bash
bash /path/to/gpm_server/package_full_zip.sh
```

## 使用轻量包时在服务端导出 FASTA

先从客户端导出 final path TSV，再将 TSV 放回保存原始 FASTA 的服务端：

```bash
bash server/export_final_path_fasta.sh \
  --tsv /path/to/project_Chr01_path.tsv \
  --gpm_server /path/to/gpm_server \
  -o /path/to/project_Chr01_path.fa
```

下一步：[在 GPM Next 中导入交付包并创建项目](/zh/guide/getting-started)。
