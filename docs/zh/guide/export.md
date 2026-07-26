---
title: 导出组装结果
description: 从 GPM Next 导出 final path 图、表、日志和序列
---

# 导出组装结果

导出前逐个检查目标 chromosome 的 contig 顺序、方向、删除/隐藏状态以及需要保留的辅助序列。final path 导出菜单按项目数据能力提供以下内容：

| 导出项 | 用途 |
|---|---|
| 图（`.png`） | 保存 final path 的可视化结果 |
| 表（`.tsv`） | 保存 contig 顺序、方向及路径坐标 |
| 日志（`.log`） | 保存路径使用与编辑统计 |
| 序列（`.fasta`） | 输出 final path 序列；需要完整交付包中的 FASTA 载荷 |
| `DEGAP-JOBS` | 为需要序列完善的区域准备 DEGAP 任务 |
| `All` | 连续执行当前项目可用的导出步骤 |

## 导出演示 {#export-video}

<TutorialVideo id="06-export" />

## 完整包与轻量包

- 完整交付包包含 partitioned FASTA 载荷，客户端可以直接导出 final path FASTA。
- 轻量交付包不含 FASTA；客户端隐藏 FASTA 入口，`All` 只导出 PNG 与 TSV。
- 使用轻量包时，可以把客户端导出的 TSV 放回服务端，通过 `export_final_path_fasta.sh` 生成 FASTA。

```bash
bash server/export_final_path_fasta.sh \
  --tsv /path/to/project_Chr01_path.tsv \
  --gpm_server /path/to/gpm_server \
  -o /path/to/project_Chr01_path.fa
```

::: warning 含 ref 对象的 final path
如果项目中某个 chromosome 的 final path 包含 ref 对象，项目导出页仍保留导出功能，但项目统计和 log 导出会关闭。
:::

建议同时保存 TSV 和 PNG：TSV 用于重建与审计路径，PNG 用于快速复核和结果交流。
