---
title: CGAT 概览
description: CGAT 的定位、组成和端到端工作流
---

# CGAT 概览

CGAT（Complete Genome Assembly Toolkit）是一套面向完整基因组组装的工作流。它将多种 de novo 组装结果放入统一的参考锚定环境，通过 GPM Next 进行导入、可视化检查和轻量编辑，再使用 DEGAP 处理 gap、序列连接和端粒延伸等任务。

CGAT 的目标不是把整个组装过程封装成不可检查的单一结果，而是保留证据展示、局部精细检查和用户确认环节。

## 组成

| 组成 | 运行环境 | 主要职责 |
|---|---|---|
| GPM Next 服务端 | Linux | 准备输入、执行参考与数据集间比对、按 chromosome 组织结果、生成交付包 |
| GPM Next 客户端 | Windows 或 macOS | 导入交付包、展示主 ds 与辅 ds、进行主视图编辑和 Subview 检查、导出 final path |
| DEGAP v2 | Linux | 使用 HiFi 和/或 ONT reads 完成 GapFiller、CtgLinker、TelSeeker 和 AutoGapfiller 任务 |

## 端到端工作流

1. 准备参考基因组以及一个或多个 de novo assembly FASTA。
2. 在 Linux 服务端运行 GPM Next 准备脚本和比对任务。
3. 生成完整交付包或轻量交付包。
4. 在桌面端导入交付包，指定主 ds 与辅 ds 并创建项目。
5. 在主视图检查 chromosome 级共线性证据，调整 contig 的顺序、方向和显示状态。
6. 在 Subview 中查看局部 pairwise evidence，使用锚点、局部翻转、轨道交换等方式辅助判断。
7. 导出 chromosome 的 final path 图、表、日志或序列。
8. 对仍需完善的区域运行 DEGAP，并将新序列重新纳入检查流程。

## 主 ds 与辅 ds

- **主 ds（primary dataset）**：用于构建当前项目主要路径的数据集。
- **辅 ds（support dataset）**：提供补充的 contig 和比对证据；一个项目可以配置多个辅 ds，并在主视图中切换。
- **ref**：参考序列提供 chromosome 锚定与坐标背景，不等同于最终路径决策。

在 Subview 的双 contig 选择中，A 来自主 ds，B 来自辅 ds。Subview 展示的是可供判断的局部证据，最终路径仍由用户确认。

## 接下来

- 尚未安装客户端：[安装 GPM Next](/zh/guide/installation)
- 尚未生成交付包：[服务端数据准备](/zh/guide/server-workflow)
- 已有交付包：[创建并导入项目](/zh/guide/getting-started)
