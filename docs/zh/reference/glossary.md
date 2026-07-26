---
title: 术语表
description: CGAT、GPM Next 和 DEGAP 常用术语
---

# 术语表

| 术语 | 含义 |
|---|---|
| CGAT | Complete Genome Assembly Toolkit，整合 GPM Next 与 DEGAP 的完整基因组组装工作流 |
| dataset / ds | 一套导入 GPM Next 的 assembly 序列及其比对结果 |
| 主 ds | 当前项目主要编辑路径使用的 primary dataset |
| 辅 ds | 用于提供互补 contig 和比对证据的 support dataset |
| ref | 提供 chromosome 锚定和坐标背景的参考序列 |
| contig / ctg | assembly 中的连续序列对象；界面和输出中可能使用 `ctg` 缩写 |
| chromosome / chr | 当前浏览和组织 final path 的 chromosome 分组 |
| track | 在主视图或 Subview 中承载一组序列对象的水平轨道 |
| alignment band | 连接不同轨道序列区域的比对关系显示 |
| MAPQ | 比对的 mapping quality；在界面中作为 evidence 显示过滤条件 |
| 主视图 | 在 chromosome 背景下查看 ref、主 ds、辅 ds 和 alignment bands 的编辑视图 |
| Subview | 检查局部 contig-to-contig pairwise evidence 的精细视图 |
| anchor | 在 Subview 中用于对齐和观察局部对应位置的锚点 |
| 偏移锚点 | 从已有锚点向左或向右移动指定 bp 后创建的手动锚点 |
| final path | 用户检查和编辑后确认的 chromosome 路径及其顺序、方向和坐标信息 |
| 完整交付包 | 带有 partitioned FASTA 载荷、支持客户端导出 final path FASTA 的 zip |
| 轻量交付包 | 不含 FASTA 载荷、仍支持导入、浏览和 PNG/TSV 导出的 zip |
| 追加包 | 把一个新 dataset 应用到已有桌面项目的小型 zip，不用于新建项目 |
