# GPM2.0 Server

**中文** | [English](README.md)

## 快速开始

```bash
# 1. 安装并验证独立环境
bash install.sh

# 2. 使用安装程序最后打印的命令激活环境，例如
mamba activate cgat-server

# 3. 准备一个项目工作目录
bash prepare.sh \
  --ref reference /path/to/reference.fa \
  --ds assembly /path/to/assembly.fa \
  -o ./gpm_server

# 4. 执行计算并生成交付包
bash ./gpm_server/run_all.sh
```

安装成功时会明确显示 `GPM Server installation: READY`。以后可执行以下命令只检查、不修改环境：

```bash
bash install.sh --check
```

安装程序依次查找 `mamba`、`micromamba`、`conda`。需要明确选择时使用：

```bash
bash install.sh --manager conda
```

## 文件用途

| 文件 | 用途 | 何时执行 |
| --- | --- | --- |
| `install.sh` | 创建、更新并验证 `cgat-server` 环境 | 首次安装或依赖更新时 |
| `env.sh` | `install.sh` 的兼容入口 | 仅供旧命令继续使用 |
| `prepare.sh` | 检查输入和工具，生成一个项目的 `gpm_server/` 工作目录 | 每个新项目一次 |
| `export_final_path_fasta.sh` | 根据 App 导出的 Final Path TSV 重建 FASTA | 流程后期按需使用，不是安装步骤 |

`prepare.sh` 只负责准备项目；真正的计算由其生成的 `gpm_server/run_all.sh` 执行。

完整参数和客户端说明见仓库上一级的 `README_zh.md`。
