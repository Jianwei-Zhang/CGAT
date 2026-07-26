---
title: 创建并导入项目
description: 将服务端交付包导入 GPM Next 并建立第一个项目
---

# 创建并导入项目

开始前请准备由 GPM Next 服务端生成的完整交付包或轻量交付包。追加包只适用于已有项目，不能代替初始交付包。

## 导入交付包 {#import-package}

1. 打开 GPM Next 并进入项目工作台。
2. 使用导入入口选择服务端生成的 zip 交付包。
3. 查看导入过程列出的参考、dataset、chromosome 与比对文件。
4. 等待导入完成，再进入创建项目步骤。

<TutorialVideo id="01-import" />

::: tip 完整包与轻量包
两者都能用于主视图、Subview 以及 PNG/TSV 导出；只有带序列载荷的完整包支持客户端直接导出 final path FASTA。
:::

## 创建项目 {#create-project}

创建项目时需要指定项目名称、参考序列、主 ds，并按需要选择一个或多个辅 ds。主 ds 构成当前项目的主要编辑路径，辅 ds 提供互补 contig 与比对证据。

创建前确认：

- 参考、主 ds 和辅 ds 均来自同一个已导入服务端项目；
- dataset 与 chromosome 命名符合本次分析预期；
- 需要使用同 dataset Subview 时，服务端没有使用 `--skip-self` 跳过对应比对。

<TutorialVideo id="02-create-project" />

## 完成最简操作路径 {#minimal-path}

创建项目后，可以先用一条最短操作流程确认数据和界面均正常：

1. 选择一个 chromosome。
2. 确认 ref、主 ds 轨道以及至少一个辅 ds 轨道能够显示。
3. 检查主 ds contig 与参考、辅 ds 之间的比对连线。
4. 在不确定区域进入 Subview；无需调整时可直接保留当前路径。
5. 打开 final path 区域并执行一次 PNG 或 TSV 测试导出。

这里的“最简路径”指首次验证项目的最短操作流程，不表示软件用单一算法自动替代用户的组装判断。

<TutorialVideo id="03-minimal-path" />

接下来可以学习[主视图编辑](/zh/guide/main-view)和[Subview 精细检查](/zh/guide/subview)。
