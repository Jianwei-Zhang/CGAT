---
title: 安装 GPM Next
description: GPM Next 客户端和服务端准备要求
---

# 安装 GPM Next

GPM Next 采用服务端与客户端分离的工作方式。Linux 服务端负责生成交付包；桌面客户端负责导入、可视化检查、编辑和导出。

## 安装桌面客户端

从 [CGAT Releases](https://github.com/Jianwei-Zhang/CGAT/releases/latest) 下载与设备匹配的安装包：

| 操作系统 | 架构 | Release 资源标识 |
|---|---|---|
| Windows | x86-64 | `win-x86` |
| Windows | ARM64 | `win-arm64` |
| macOS | Intel | `mac-x86` |
| macOS | Apple Silicon | `mac-arm64` |

安装完成后打开 GPM Next。服务端尚未生成交付包时，可以先完成客户端安装，但不能创建包含真实 assembly 数据的项目。

## 准备 Linux 服务端

服务端至少需要：

- SAMtools 1.9 或更高版本
- Python 3
- `zip` 与 `gzip`
- 下列比对引擎之一：
  - minimap2，推荐 2.31
  - BLAST+，推荐 2.17.0，包含 `blastn` 与 `makeblastdb`
  - Winnowmap，推荐 2.03，同时安装 `meryl`

获取代码：

```bash
git clone https://github.com/Jianwei-Zhang/CGAT.git
cd CGAT/GPM2.0
```

运行前确认所选比对引擎和基础命令可用。例如：

```bash
python3 --version
samtools --version
minimap2 --version
zip --version
```

## 输入准备

至少准备：

- 一个参考基因组 FASTA；
- 一个计划作为主 ds 的 de novo assembly FASTA；
- 可选的一个或多个辅 ds FASTA。

文档中的 `hifiasm.fa`、`flye.fa` 和 `canu.fa` 仅用于说明多数据集输入，不限制实际使用的组装软件。

下一步：[生成 GPM Next 服务端交付包](/zh/guide/server-workflow)。
