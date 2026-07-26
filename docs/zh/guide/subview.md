---
title: Subview 精细检查
description: 使用局部 pairwise evidence、轨道次序和锚点辅助 final path 判断
---

# Subview 精细检查

Subview 用于检查两个 contig 之间的局部 pairwise evidence。双 contig 模式下，A 必须来自主 ds，B 必须来自辅 ds。Subview 支持局部片段查看、翻转、轨道上下交换和锚点调整，但不会替用户自动确认 final path。

## 从 track 进入 {#enter-from-track}

从主视图轨道选择需要比较的对象后进入 Subview。进入前确认当前辅 ds 已选择，并且该辅 ds 在当前 chromosome 中有匹配 contig。

<TutorialVideo id="05-01-enter-subview-from-track" />

## 从 contig 进入 {#enter-from-contig}

也可以直接通过 contig 操作入口发起局部比较。目标组合仍需满足主 ds 与辅 ds 的槽位规则。

<TutorialVideo id="05-02-enter-subview-from-contig" />

## 切换上下轨道次序 {#swap-track-order}

切换上下次序只改变 Subview 的视觉排列，便于观察 alignment bands，不会交换项目中的主 ds 和辅 ds 身份。

<TutorialVideo id="05-03-swap-subview-track-order" />

## 使用锚点 {#anchor}

锚点用于把当前 pairwise evidence 中的对应位置作为局部观察基准。调整锚点时应同时查看两条 contig 的片段边界、方向和 alignment band，避免脱离上下文使用单个命中。

<TutorialVideo id="05-04-anchor" />

## 创建偏移锚点 {#offset-anchor}

在现有锚点基础上可以向左或向右复制一个偏移锚点：

1. 选择“复制偏移锚点”。
2. 指定 `left` / `right`（或左 / 右）。
3. 输入正整数 bp 距离。
4. 比较偏移前后的局部边界与比对证据。

如果偏移超出 contig 范围，软件不会创建锚点。手动创建的偏移锚点可以单独删除。

<TutorialVideo id="05-05-offset-anchor" />

完成局部判断后返回主视图，检查该修改对整个 chromosome final path 的影响。
