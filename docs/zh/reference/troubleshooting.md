---
title: 常见问题
description: GPM Next 导入、轨道、Subview 和导出问题排查
---

# 常见问题

## 辅 ds 轨道为空

依次检查：

1. 当前项目是否配置了辅 ds；
2. 是否已经在主视图选择辅 ds；
3. 当前辅 ds 是否包含与所选 chromosome 匹配的数据；
4. `辅ds_ctg_len(bp)` 过滤条件是否排除了全部 contig。

## 无法进入 Subview

- 双 contig 模式中，A 必须来自主 ds，B 必须来自辅 ds。
- 切换辅 ds 后需要重新选择 contig。
- 如果服务端使用了 `--skip-self`，同 dataset contig-to-contig Subview 不可用；跨 dataset Subview 不受影响。

## 比对连线过多或过少

组合调整 alignment length、MAPQ 和辅 ds contig length。过滤只改变 evidence 显示；不要把当前不可见直接解释为数据不存在。

## 偏移锚点无法创建

方向必须是 `left` / `right`（或左 / 右），距离必须是正整数 bp。偏移后位置超出 contig 范围时不会创建锚点。

## 客户端没有 FASTA 导出入口

当前项目很可能来自轻量交付包。先导出 final path TSV，再回到保留原始 FASTA 的 Linux 服务端运行 `export_final_path_fasta.sh`。

## 追加包无法用于新建项目

`add_<dataset>.zip` 只用于已有项目。需要新建项目时，在服务端追加 dataset 后重新运行 `package_full_zip.sh` 或 `package_light_no_fasta_zip.sh`。

## `All` 没有生成 FASTA

轻量包的 `All` 只导出 PNG 与 TSV。只有带序列载荷的完整包支持客户端 FASTA 导出。

## 仍然无法解决

在 [GitHub Issues](https://github.com/Jianwei-Zhang/CGAT/issues) 提交问题，并附上：

- GPM Next 或 DEGAP 版本；
- 操作系统与架构；
- 完整包或轻量包类型；
- 可复现步骤和完整错误文本；
- 不包含敏感数据的日志与截图。
