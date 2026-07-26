---
title: 主视图编辑
description: 在 GPM Next 主视图中调整 contig 并控制证据显示
---

# 主视图编辑

主视图在 chromosome 坐标背景下同时展示 ref、主 ds 和当前辅 ds。轨道之间的 alignment bands 用于观察不同序列对象之间的对应关系。

## 拖动 contig {#drag-contig}

拖动用于调整 contig 在当前编辑视图中的位置，便于与参考坐标和辅 ds 证据对齐比较。拖动后应继续检查相邻 contig、alignment bands 与 final path，而不是只依据视觉位置判断结果。

<TutorialVideo id="04-01-drag-contig" />

## 翻转 contig {#flip-contig}

当比对方向和相邻证据支持反向放置时，可以翻转 contig。翻转会改变该对象在当前路径中的方向显示；完成后检查其两端连接关系。

<TutorialVideo id="04-02-flip-contig" />

## 删除 contig {#delete-contig}

界面提供两种删除入口。无论使用哪个入口，确认对话框都会明确目标 contig；确认前请核对 chromosome 和 contig 标识。

<TutorialVideo id="04-03-01-delete-contig-method-1" />

<TutorialVideo id="04-03-02-delete-contig-method-2" />

## 撤销删除 {#undo-delete}

删除或隐藏后，可以从主 ds 轨道成员区域执行重置，恢复已删除或隐藏的成员。恢复后重新检查当前 chromosome 的路径。

<TutorialVideo id="04-03-03-undo-delete-contig" />

## 隐藏主 ds contig {#hide-primary-contig}

隐藏用于暂时减少主图中的对象或 evidence clutter，不等同于删除。可以通过 contig 操作菜单隐藏，也可以对已框选的多个 contig 批量隐藏或解除隐藏。

<TutorialVideo id="04-04-hide-primary-dataset-contig" />

## 镜像辅 ds contig {#mirror-support-contig}

镜像功能把当前辅 ds 轨道中的 contig 显示到 mirror 轨道，便于和主路径并行比较。只有当前辅 ds 轨道中存在的 contig 才能镜像；需要时可以撤销镜像。

<TutorialVideo id="04-05-mirror-support-dataset-contig" />

## 视图与证据控制 {#view-controls}

### 切换 chromosome

切换后，主视图、辅 ds 选择和当前 chromosome 的编辑状态会共同决定显示内容。

<TutorialVideo id="04-06-01-switch-chromosome" />

### 切换辅 ds 轨道

一个项目配置多个辅 ds 时，可以切换当前显示的数据集。切换辅 ds 后，需要重新选择用于 Subview 的 contig。

<TutorialVideo id="04-06-02-switch-support-dataset-track" />

### 过滤辅 ds contig

`辅ds_ctg_len(bp)` 用于控制辅 ds 轨道中参与显示的 contig。复杂区域可先降低视觉负担，再逐步放宽阈值复核短 contig 证据。

<TutorialVideo id="04-06-03-filter-support-dataset-contigs" />

### 控制主视图比例

比例设置影响 chromosome 区域在画布中的显示尺度，不改变序列或比对数据本身。

<TutorialVideo id="04-06-04-adjust-main-view-scale" />

### 按比对长度过滤

提高 alignment length 阈值可以隐藏较短的比对关系。过滤只改变当前证据显示，不应被解释为自动删除 contig。

<TutorialVideo id="04-06-05-filter-alignment-length" />

### 按 MAPQ 过滤

MAPQ 阈值用于控制可见比对。高阈值有助于聚焦高置信证据，但也可能隐藏复杂或重复区域中的有效线索，应结合区域背景调整。

<TutorialVideo id="04-06-06-filter-alignment-mapq" />

需要检查局部 contig-to-contig 关系时，继续阅读 [Subview 精细检查](/zh/guide/subview)。
