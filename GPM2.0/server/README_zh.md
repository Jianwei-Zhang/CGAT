# GPM2.0 Server

**中文** | [English](README.md)

## 快速开始

在 Linux 服务端依次执行以下命令：从 [Release v2.0.12](https://github.com/Jianwei-Zhang/CGAT/releases/tag/v2.0.12) 下载 GPM Server 工具包（源码），默认解压到 `~/bin/GPM_Server`（也可自定义），然后安装和运行。官网直连下载失败时回退 GitHub；skill 安装器和更新器也遵循此顺序，并校验版本与摘要。下载摘要见官网或 Release 的 SHA-256 清单。

```bash
# 1. 下载并解压到工具目录，不改变当前项目目录
SERVER="$HOME/bin/GPM_Server"  # 可改为自定义路径；已有安装不要覆盖
(
  set -euo pipefail
  mkdir -p "$(dirname "$SERVER")"
  mkdir "$SERVER"
  cd "$SERVER"
  archive=GPM_Server_2.0.12_source.tar.gz
  curl -fL --connect-timeout 8 --max-time 60 -o "$archive" \
    "https://riceome.hzau.edu.cn/cgat/downloads/v2.0.12/$archive" ||
    curl -fL --connect-timeout 8 --max-time 60 -o "$archive" \
      "https://github.com/Jianwei-Zhang/CGAT/releases/download/v2.0.12/$archive"
  curl -fL --connect-timeout 8 --max-time 30 -o SHA256SUMS \
    https://riceome.hzau.edu.cn/cgat/downloads/v2.0.12/SHA256SUMS ||
    curl -fL --connect-timeout 8 --max-time 30 \
      https://api.github.com/repos/Jianwei-Zhang/CGAT/releases/tags/v2.0.12 |
      python3 -c 'import json,sys; r=json.load(sys.stdin); print("\n".join(a["digest"].removeprefix("sha256:")+"  "+a["name"] for a in r["assets"] if a["name"].endswith("_source.tar.gz")))' > SHA256SUMS
  grep "  $archive$" SHA256SUMS | sha256sum -c -
  tar -xzf "$archive" --strip-components=1
  # 2. 安装并验证独立环境
  bash ./install.sh
)
```

仅在安装成功后继续；下面的分析命令在你的项目工作目录执行，不在工具目录执行。

```bash

# 3. 使用安装程序最后打印的命令激活环境，例如
mamba activate cgat-server

# 4. 准备、计算并生成交付包
bash "$SERVER/run.sh" \
  --ref /path/to/reference.fa \
  --ds /path/to/assembly.fa \
  -o ./gpm_server
```

成功结束时会明确显示 `Final delivery packages` 摘要。最终只交付
`gpm_server.tar.gz`（Full，含 FASTA 和报告）与 `gpm_server.light.tar.gz`（Light，不含 FASTA、
包含报告）两个文件；两者都内置完整的 `gpm_server/report/` 目录，不再单独生成
报告 ZIP。本地报告仍可在 `gpm_server/report/report.html` 直接打开。

报告表格最多内嵌前 200 行预览，并标明准确总行数与来源路径；全量审计明细仍保留在
Server 工作目录中，不再反复塞入 HTML 和 App 报告快照。搜索与分页只针对已标注的预览。


默认使用 pigz 多线程压缩为 `tar.gz`；`--archive-format zip` 可保留 ZIP 格式，App 支持两者。

`--ref` 和可重复使用的 `--ds` 都支持 `<名称> <fasta>` 与仅传 `<fasta>`
两种写法。省略名称时，会从 FASTA 文件名自动推导：不区分大小写地移除
`.gz` 及一个 `.fa`、`.fasta` 或 `.fna` 后缀；名称中除字母、数字、点、
下划线和连字符以外的连续字符会替换为 `_`。需要自定义名称时仍可使用显式写法：

```bash
bash "$SERVER/run.sh" \
  --ref reference /path/to/reference.fa \
  --ds assembly /path/to/assembly.fa \
  -o ./gpm_server
```

安装成功时会明确显示 `GPM Server installation: READY`。以后可执行以下命令只检查、不修改环境：

```bash
bash "$SERVER/install.sh" --check
```

安装程序依次查找 `mamba`、`micromamba`、`conda`。需要明确选择时使用：

```bash
bash "$SERVER/install.sh" --manager conda
```

### ARM64 与集群环境

安装器在 Linux ARM64（`aarch64`/`arm64`）上使用独立依赖清单。Linux ARM64
和 x86_64 统一使用 `meryl=1.4.2`，避开 ARM64 上已复现的 1.4.1 多线程崩溃问题。
部署时请复制完整 `server/` 目录。

如果使用集群 module，需在作业脚本中加载匹配架构的工具及运行库，
并确保 Merqury 安装要求的 `MERQURY` 环境变量已设置。`command -v`
能找到程序不代表程序能正常启动；`GLIBCXX_* not found` 表示 C++ 运行库
不匹配，应加载匹配的 GCC runtime 或使用安装器创建的独立环境。
执行 `run.sh` 时保持环境激活。

外部 QC 命令失败时，Server 主日志会保留其 stdout/stderr 尾部，
即使失败的临时 QC 目录随后被清理，也可查看底层报错。

`run.sh -t 32` 设置总计算线程预算；新准备的工作区会在独立比对任务之间
自动分配线程并行执行。

### Step3 来源追踪修复后的断点恢复

当连续 N 位于原始 contig 内部，或跨越多个路径片段时，旧版可能报错
`cannot map filtered Step3 gap back to q2`。Step3 现在会在过滤过程中
保留这些 gap 的来源，以及合并 gap 的全部原始来源。
最终阶段的 `accepted event disappeared before q4 without one exact q3 segment`
也可能由 Step2 补片被部分裁剪引起；保留片段修复会记录其精确来源，并保留原始重放历史。

更新方式见下节。完成更新后，在原环境运行或重新提交 `run_all.sh`；流程按需从
Step2 重新生成阶段结果，兼容的 MUMmer 原始比对缓存仍可复用。更新器本身不启动分析。

### 更新工具、skill 与项目运行库

无论只想检查还是准备更新，都执行同一个命令：

```bash
bash ~/bin/GPM_Server/update.sh
```

此入口要求工具包包含 `update.sh`；旧包缺少该脚本时不要直接覆盖安装，先按 Server/skill 更新说明完成一次性接入。

自定义安装请使用实际路径。在项目根目录或子目录执行，会检测当前项目的
`.prepare_lib/`，并与 tools 对齐；在项目外执行，不扫描其他项目。
检查和下载优先走[官网](https://riceome.hzau.edu.cn/cgat/zh/downloads)，失败回退
[GitHub Release](https://github.com/Jianwei-Zhang/CGAT/releases/latest)，校验大小、SHA-256
及包内文件清单。tools 与 skill 来自同一发布源码包，同版本附件刷新也能识别。

- 全部最新且一致：告知“当前已是最新版本，无需更新”。
- 有更新或项目运行库未对齐：展示变更，询问 `是否更新？[y/N]`。
- `Y/y` 更新；`N/n`、回车、EOF 或无交互终端不更新。不提供 `--check`、`--yes`。
- 保留 skill 整个 `local/`、有效绑定、项目输入、结果、日志、缓存、生成脚本及依赖环境。
- 独立安装的 skill 通过 `server_tools_path.sh --set` 登记后一起更新，不扫描 agent 配置。

更新前须停止全部受影响任务，包括其他节点上的任务。运行中任务、路径冲突、已知
自定义改动、依赖配置变化和不支持的旧调度计划会阻止更新，不自动重装环境或重跑分析。
没有历史清单的旧文件会列出供确认，无法据此自动区分用户定制。
备份位于项目的 `.run_all/server-update-*`；无项目时位于 tools 目录下。
写入失败会尝试回滚，成功后也会打印回滚命令。更新后重新加载 agent 会话。
旧安装尚无 `update.sh` 时，按 [skill 更新参考](skills/gpm-server/references/official-updates.md)
完成一次性接入，不直接覆盖旧目录。官网可独立完成检查；若镜像滞后，不会把已安装的
较新版本/构建降级。网络或校验失败不会被当作“已经最新”。

### 独立 GRT 阶段控制与执行配置

新工作区生成独立的 `run_grt_step2.sh` 与 `run_grt_step3.sh` 阶段脚本，分别记录调度状态和 checkpoint。先运行 Step2，再运行 Step3；Step3 启动前会校验兼容的 Step2 结果。两个阶段共用覆盖修复引擎与公共模块的内容指纹：当修复代码更新时，阶段结果会自动从 Step2 重新生成，而输入与参数一致的 MUMmer 原始比对缓存仍可安全复用。

新生成的正式工作流默认启用以下优化路线：

- `--grt-execution-profile optimized`：启用跨染色体共享且受 CPU / 内存约束的 `nucmer` 池、大分区优先调度、分区 FASTA 复用、精确锚点索引与坐标解析缓存复用，并保持输出与平局选择顺序确定性。
- Step2 始终使用 **full 全量范围**。
- `--grt-step3-mummer-scope gap-screen`：使用锚点安全筛选，选中的原始供体分区仍与完整染色体比对。
- optimized Step3 refill 会同轮合并侧翼查询，并复用经内容校验的 `.mmi` 索引。

如需在**新建工作区**时回退为无筛选基线配置，可向 `run.sh` 或 `prepare.sh` 传入：

```bash
--grt-execution-profile baseline --grt-step3-mummer-scope full
```

已有工作区不会随外部工具自动修改；如需对齐旧项目的运行库，请在停止任务后进入该项目目录显式执行 `update.sh`。

## 可选的 AI agent skill

### 给 AI agent 的安装提示词

复制以下内容给你正在使用的 agent：

```text
请为当前 AI agent 安装官方 gpm-server skill：
https://github.com/Jianwei-Zhang/CGAT/tree/master/GPM2.0/server/skills/gpm-server
下载和更新优先使用 https://riceome.hzau.edu.cn/cgat/ 的 Server 源码包，
失败时回退 GitHub Release；skill 位于包内 skills/gpm-server/，请完整安装。
如果已安装 Server tools，请询问我安装路径；未安装则询问是否安装到
~/bin/GPM_Server，也允许我指定其他位置。确认后完成安装与路径绑定，
保留已有 skill 的 local/ 本地经验。
```

### 安装与使用说明

源码内提供官方 [gpm-server skill](skills/gpm-server/SKILL.md)，覆盖首次运行、
安全恢复、失败诊断与结果交付。它是可选入口，不使用 AI 仍可直接执行上面的 CLI。
请让 skill 与配套 Server 源码一起使用；不要假设此前发布的压缩包已包含本次新增内容。

可让 agent 直接阅读该 `SKILL.md`，或按所用 agent 的说明，将**整个**
`skills/gpm-server/` 目录复制到其 skill 目录。`install.sh` 不会修改 agent 配置。
skill 内的 `server-tools.path` 明确记录 Server tools 位置：随源码分发时为相对于
skill 目录的 `../..`；单独复制安装后，执行一次
`bash /实际/skill目录/scripts/server_tools_path.sh --set /实际/Server目录` 绑定绝对路径。
后续 agent 直接读取、校验该记录，不再搜索工具目录；路径失效时明确报错，不自动切换版本。
路径失效时先询问用户现有安装的位置；用户也不清楚时，再询问是否授权限定范围查找或重新安装，确认前均不执行。安装成功提示会列出工具绝对路径和 skill 绑定命令，不额外写入 Server 路径到 `.bashrc`/`.zshrc`。这与原安装器首次引导 micromamba 时已有的 Bash 初始化是两回事。
使用时明确 Server 绝对路径、输入角色（第一个 `--ds` 是主组装）、输出目录、
资源预算，以及所在集群的提交与环境说明。例如：

> 请按 gpm-server skill 操作。Server 工具在 /work/GPM_Server，参考是
> /work/inputs/ref.fa，主组装是 /work/inputs/assembly.fa。先检查环境，再运行到
> /work/runs/sample，最多使用 4 线程。遵循本集群的作业提交规则，不在登录节点
> 计算，不擅自调整科学参数或覆盖已有结果，结束后给出日志和结果位置。

skill 默认自动积累简明的本地经验：问题已修复并验证，且类似坑以后可能再遇到、
记录能减少踩坑时，保存或更新 `local/notes.md`，不再让用户选择记录模式。
后续使用前核对适用条件和证据；用户明确的禁止写入要求及工具权限仍优先。
经验不能授权修改科学参数、破坏性修复或上传数据，详见[本地经验规则](skills/gpm-server/references/local-learning.md)。

skill 的安装和更新与 Server 使用同一套[官方来源及安全规则](skills/gpm-server/references/official-updates.md)：
默认安装位置为 `~/bin/GPM_Server`，保留已有或自定义路径；日常更新只需 `update.sh`。
它是可选 agent 指导，不是后台更新服务或强制权限沙箱。

只想验证能否跑通时，可要求执行 [合成小数据冒烟测试](skills/gpm-server/references/smoke-test.md)。
它使用小型生成数据与真实工具，不用于科学结论。实际覆盖范围与未验证项见
[ARM/Donau 验证记录](validation/agent-skill-v1-180.md)和
[x86/LSF 与工具路径绑定验证记录](validation/agent-skill-v1-140-1.md)；
skill 是操作指导，不是权限沙箱。

## 进度日志与终端颜色

生成的 `run_all.sh` 默认使用精简终端展示：保留阶段起止、有效结果复用、限频的
MUMmer 染色体进度以及警告和错误。逐染色体复制/解析耗时和缓存 hash 保留在完整
日志。运行中的单元静默 60 秒后输出心跳提示；采用逐行追加，不使用终端刷新动画。
未知子进程输出仍保留，不猜测过滤。

- `logs/progress.log`：精简纯文本进度，多次运行追加记录。
- `logs/run_all.log`：完整时间、run ID、事件与性能指标等诊断信息。
- `report/report.html`：格式和数据来源不变。原始事件及子进程输出先进入报告和
  缓存判定，再做展示过滤。报告仍保留原有长度限制的输出尾部，完整诊断以日志为准。

在 Server 工具目录执行：

```bash
# 只读查看；Ctrl+C 只退出查看，不停止分析作业。
python3 "$SERVER/tools/view_run_log.py" --server-dir ./gpm_server --follow
# 改为查看完整诊断。
python3 "$SERVER/tools/view_run_log.py" --server-dir ./gpm_server --detailed --follow
# 不使用查看器也能直接查看纯文本。
tail -F ./gpm_server/logs/progress.log
```

颜色只用于显示的状态标签。自动模式仅在交互终端上色，Slurm `.out` 和管道默认
不写颜色，并遵循 `NO_COLOR`、`TERM=dumb`。查看器和生成的 runner 都支持
`--color auto|always|never`，显式 `always` 优先于自动检测和 `NO_COLOR`。
磁盘日志和报告数据不写入展示用颜色控制符。如需在**后续运行**中恢复旧的详细
终端格式，使用 `bash ./gpm_server/run_all.sh --log-style detailed`。
这些参数属于 `run_all.sh`，不是 `run.sh`/`prepare.sh` 的参数。

旧项目保留原有内嵌运行库，只有明确更新后才启用新展示。作业运行期间不要替换
工具或运行库；本次展示调整无需删除缓存、重新准备输入或更换依赖环境。

## 文件用途

| 文件 | 用途 | 何时执行 |
| --- | --- | --- |
| `install.sh` | 创建、更新并验证 `cgat-server` 环境 | 首次安装或依赖更新时 |
| `update.sh` | 检查并更新 Server 工具、已绑定 skill 与项目 `.prepare_lib/` 运行库 | 日常升级维护或对齐旧项目运行库时 |
| `env.sh` | `install.sh` 的兼容入口 | 仅供旧命令继续使用 |
| `run.sh` | 自动准备并执行完整流程，已有工作目录按断点继续 | 首次运行或恢复 |
| `prepare.sh` | 兼容原有的仅准备命令 | 需要单独生成脚本时 |
| `export_final_path_fasta.sh` | 根据 App 导出的 Final Path TSV 重建 FASTA | 流程后期按需使用，不是安装步骤 |

重复同一条 `run.sh` 命令，或执行 `bash "$SERVER/run.sh" -o ./gpm_server` 即可恢复；已通过校验的结果会复用。生成的 `run_all.sh` 仍可直接执行。

`--max-fill <bp>` 设置 Step3 两轮优化补洞的长度上限，默认 `1000000`。已有工作目录可用 `bash "$SERVER/run.sh" -o ./gpm_server --max-fill 2000000` 调整；更换输入或其他准备参数时使用新的输出目录。


完整参数和客户端说明见仓库上一级的 `README_zh.md`。
