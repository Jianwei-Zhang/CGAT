---
title: 完整工作流
description: 将 GPM Next 的可视化决策与 DEGAP 序列完善连接起来
---

# 完整工作流

## GPM Next 与 DEGAP 的闭环

1. 从 GPM Next 导出目标 chromosome 的 final path TSV、PNG 和必要的 DEGAP 任务信息。
2. 在 Linux 环境运行对应 DEGAP 模式。
3. 检查 DEGAP 日志、summary、HTML/可视化结果以及新生成序列。
4. 在 GPM Next 服务端项目中追加新的 dataset 或重新生成完整交付包。
5. 在桌面端把追加包应用到已有项目，或使用新完整包建立独立项目。
6. 重新检查主视图与 Subview evidence，并由用户确认新的 final path。

::: important
`add_<dataset>.zip` 是应用于已有桌面项目的追加包；新建项目应使用重新生成的完整交付包。
:::

## 计划中的专题教程 {#planned-tutorials}

以下专题已纳入文档规划，但视频尚未完成，因此暂不出现在正式视频目录中：

- 将 DEGAP 生成的新 contig 加入 GPM Next 轨道；
- 多倍体组装；
- 参考序列辅助填补。

专题发布前，本站不会用空视频或不可播放链接占位。
