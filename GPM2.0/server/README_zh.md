# GPM2.0 Server

**中文** | [English](README.md)

自动修复引擎 **LGZ** 的全称是 **Linking Inter-assembly Units for Genome Zipping**。

Server 实现与新脚本名称使用 `lgz_*`。已有 `grt_*` Python 导入、生成脚本入口及 `--grt-*` 参数继续作为兼容别名，命名别名保留 LGZ 持久化阶段 ID；独立的编号布局和精修包协议变化见下文。 本命名迁移适用于当前源码；在对应 Server 源码附件刷新前，较早发布的安装目录仍应使用旧名称。详见[Server 命名兼容说明](https://github.com/Jianwei-Zhang/CGAT/blob/master/GPM2.0/docs/lgz-server-implementation.md)。

> **当前源码**：LGZ 后四工具精修、编号工作区、旧目录迁移和 App 精修包见[使用指南](REFINEMENT_zh.md)。下方 v2.0.21 下载命令安装的是已发布版本，不包含这里的新产出结构。

## 快速开始

在 Linux 服务端依次执行以下命令：从 [Release v2.0.21](https://github.com/Jianwei-Zhang/CGAT/releases/tag/v2.0.21) 下载 GPM Server 工具包（源码），默认解压到 `~/bin/GPM_Server`（也可自定义），然后安装和运行。官网直连下载失败时回退 GitHub；skill 安装器和更新器也遵循此顺序，并校验版本与摘要。下载摘要见官网或 Release 的 SHA-256 清单。

```bash
# 1. 下载并解压到工具目录，不改变当前项目目录
SERVER="$HOME/bin/GPM_Server"  # 可改为自定义路径；已有安装不要覆盖
(
  set -euo pipefail
  mkdir -p "$(dirname "$SERVER")"
  mkdir "$SERVER"
  cd "$SERVER"
  archive=GPM_Server_2.0.21_source.tar.gz
  curl -fL --connect-timeout 8 --max-time 60 -o "$archive" \
    "https://riceome.hzau.edu.cn/cgat/downloads/v2.0.21/$archive" ||
    curl -fL --connect-timeout 8 --max-time 60 -o "$archive" \
      "https://github.com/Jianwei-Zhang/CGAT/releases/download/v2.0.21/$archive"
  curl -fL --connect-timeout 8 --max-time 30 -o SHA256SUMS \
    https://riceome.hzau.edu.cn/cgat/downloads/v2.0.21/SHA256SUMS ||
    curl -fL --connect-timeout 8 --max-time 30 \
      https://api.github.com/repos/Jianwei-Zhang/CGAT/releases/tags/v2.0.21 |
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

下方下载的已发布 v2.0.21 成功结束时显示 `Final delivery packages` 摘要，按其旧布局交付
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

### 历史工作区来源追踪修复（旧阶段编号）

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
`.lib/` 运行时目录（旧项目 `.prepare_lib/` 与旧版编号工作区的 `.runtime/prepared/` 仅作兼容读取/迁移路径），并与 tools 对齐；在项目外执行，不扫描其他项目。
检查和下载优先走[官网](https://riceome.hzau.edu.cn/cgat/zh/downloads)，失败回退
[GitHub Release](https://github.com/Jianwei-Zhang/CGAT/releases/latest)，校验大小、SHA-256
及包内文件清单。tools 与 skill 来自同一发布源码包，同版本附件刷新也能识别。

- 全部最新且一致：告知“当前已是最新版本，无需更新”。
- 有更新或项目运行库未对齐：展示变更、备份原文件后直接更新，不再询问 Y/N。
- 支持关闭标准输入和批处理任务，不需要 `--check`、`--yes`。
- 保留 skill 整个 `local/`、有效绑定、项目输入、结果、日志、缓存、自定义生成脚本及依赖环境。逐字节识别的旧 `run_all.sh` 会备份后升级。
- 独立安装的 skill 通过 `server_tools_path.sh --set` 登记后一起更新，不扫描 agent 配置。

更新前须停止全部受影响任务，包括其他节点上的任务。运行中任务、路径冲突、已知
自定义改动、依赖配置变化和不支持的旧调度计划会阻止更新，不自动重装环境或重跑分析。
显式执行更新时，没有历史清单的旧文件会列出并在替换前备份；有清单且已被修改的官方文件仍拒绝覆盖。
备份位于项目的 `.run_all/server-update-*`；无项目时位于 tools 目录下。
写入失败会尝试回滚，成功后也会打印回滚命令。更新后重新加载 agent 会话。
旧安装尚无 `update.sh` 时，按 [skill 更新参考](skills/gpm-server/references/official-updates.md)
完成一次性接入，不直接覆盖旧目录。官网可独立完成检查；若镜像滞后，不会把已安装的
较新版本/构建降级。网络或校验失败不会被当作“已经最新”。

### 独立 LGZ 阶段控制与执行配置

新工作区使用 **package schema 4**，执行步骤和实际产物连续编号：

| 阶段 | 脚本 | 输出 |
| --- | --- | --- |
| 证据驱动初始路径 | `prepare_lgz_inputs.sh` | q0 |
| 补丁验证与处理分支 | `run_lgz_step1.sh` | q1 |
| 结构修正与优化补洞 | `run_lgz_step2.sh` | q2 |
| 端粒恢复与最终路径 | `run_lgz_step3.sh` | q3 |

通常由 `run_all.sh` 按顺序执行。各实际步骤有独立检查点，不再产生 q0r1/q0f
等原样复制版本。Step2 启动前验证 Step1 结果；修复代码变化会使决策缓存失效，
内容与参数一致的原始 MUMmer 比对缓存仍可复用。

历史 schema 2/3 包继续按原编号读取，但不原地重编号或迁移为本流程。
使用新策略时准备新的 schema-4 工作目录并保留旧结果；上面的历史恢复说明
适用于与历史工作区匹配的运行库，不代表编号迁移。

新生成的正式工作流默认启用以下优化路线：

- `--lgz-execution-profile optimized`：启用跨染色体共享且受 CPU / 内存约束的 `nucmer` 池、大分区优先调度、分区 FASTA 复用、精确锚点索引与坐标解析缓存复用，并保持输出与平局选择顺序确定性。
- Step1 默认使用 **full 全量范围**。
- `--lgz-step2-mummer-scope gap-screen`：使用锚点安全筛选，选中的原始供体分区仍与完整染色体比对。
- optimized Step2 refill 会同轮合并侧翼查询，并复用经内容校验的 `.mmi` 索引。

如需在**新建工作区**时回退为无筛选基线配置，可向 `run.sh` 或 `prepare.sh` 传入：

```bash
--lgz-execution-profile baseline --lgz-step2-mummer-scope full
```

新 `run.sh` 和新生成的 `run_all.sh` 在分析与运行锁之前先检查更新，更新后重新加载代码，不需要用户配置。联网检查前也会从校验通过的本地安装同步已停止的工作区运行库；旧 updater 漏复制嵌套模块时，离线计算节点不必再下载一次。网络或更新检查在写入前失败时，可继续使用通过完整性校验的已安装运行库；写入或回滚失败则停止启动。Git/开发包及仅查看帮助时不联网更新。停止任务后显式执行 `update.sh` 可同步运行库，并备份后升级逐字节识别的旧 `run_all.sh`；自定义脚本不覆盖。

遇到 Step2 `missing its output gap interval` 时，先同时更新工具和受影响工作区运行库，再恢复运行。结构修复现会登记向前、向后吸收的全部 GAP；部分切入或来源映射歧义将明确拒绝。保留日志、结果和原始比对缓存，无需重装依赖。

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

- `.runtime/logs/progress.log`：精简纯文本进度，多次运行追加记录。
- `.runtime/logs/run_all.log`：完整时间、run ID、事件与性能指标等诊断信息。
- `06_report/01_lgz/report.html`：格式和数据来源不变。原始事件及子进程输出先进入报告和
  缓存判定，再做展示过滤。报告仍保留原有长度限制的输出尾部，完整诊断以日志为准。

在 Server 工具目录执行：

```bash
# 只读查看；Ctrl+C 只退出查看，不停止分析作业。
python3 "$SERVER/tools/view_run_log.py" --server-dir ./gpm_server --follow
# 改为查看完整诊断。
python3 "$SERVER/tools/view_run_log.py" --server-dir ./gpm_server --detailed --follow
# 不使用查看器也能直接查看纯文本。
tail -F ./gpm_server/.runtime/logs/progress.log
```

颜色只用于显示的状态标签。自动模式仅在交互终端上色，Slurm `.out` 和管道默认
不写颜色，并遵循 `NO_COLOR`、`TERM=dumb`。查看器和生成的 runner 都支持
`--color auto|always|never`，显式 `always` 优先于自动检测和 `NO_COLOR`。
磁盘日志和报告数据不写入展示用颜色控制符。如需在**后续运行**中恢复旧的详细
终端格式，使用 `bash ./gpm_server/run_all.sh --log-style detailed`。
这些参数属于 `run_all.sh`，不是 `run.sh`/`prepare.sh` 的参数。

旧项目保留原有内嵌运行库，只有明确更新后才启用新展示。作业运行期间不要替换
工具或运行库；本次展示调整无需删除缓存、重新准备输入或更换依赖环境。

## Minimap2 CIGAR 断言诊断

每次运行会把 minimap2 的路径、版本、SHA-256 和已有输入索引的长度摘要记录到
`.run_all/diagnostics/<run-id>/minimap2_runtime.json`。长序列只是风险提示，不等于
已发生 CIGAR 溢出；此快照不更改参数，也不能替代实际任务日志或 FASTA 内容校验。

`MINIMAP2_CIGAR_ASSERTION` 表示检测到了 `mm_update_extra`/`mm_fix_cigar` 的区间长度
断言。请保留 `command.sh`/`command.txt`/`command.json`、`stderr.log`、
`tool_version.txt`、部分输出和 Slurm 资源记录。失败任务不会被当成成功继续下游；
LGZ 的多次失败分别保留在 `grt/failed/`，不会覆盖同一进程之前的失败证据。

不要通过删除 `-c`、过滤超长查询或静默更改组装预设来绕过失败。对 minimap2 2.31
的 270 Mb 合成序列测试中，已测试的调参不能解决该单操作长度问题；`--max-qlen`
只是丢掉了查询。详见[参数验证记录](validation/minimap2-long-cigar-20261029.md)。
本次不修改 minimap2 二进制或 CGAT 的默认比对参数，也不宣称客户问题已解决。

## 文件用途

| 文件 | 用途 | 何时执行 |
| --- | --- | --- |
| `install.sh` | 创建、更新并验证 `cgat-server` 环境 | 首次安装或依赖更新时 |
| `update.sh` | 检查并更新 Server 工具、已绑定 skill 与项目 `.lib/` 运行库（旧 `.prepare_lib/` 和 `.runtime/prepared/` 作兼容读取/迁移路径） | 日常升级维护或对齐项目运行库时 |
| `env.sh` | `install.sh` 的兼容入口 | 仅供旧命令继续使用 |
| `run.sh` | 自动准备并执行完整流程，已有工作目录按断点继续 | 首次运行或恢复 |
| `prepare.sh` | 兼容原有的仅准备命令 | 需要单独生成脚本时 |
| `export_final_path_fasta.sh` | 根据 App 导出的 Final Path TSV 重建 FASTA | 流程后期按需使用，不是安装步骤 |

重复同一条 `run.sh` 命令，或执行 `bash "$SERVER/run.sh" -o ./gpm_server` 即可恢复；已通过校验的结果会复用。生成的 `run_all.sh` 仍可直接执行。旧作业停止后，可用 `bash "$SERVER/run.sh" -o ./gpm_server --threads 64` 调整线程预算，也可修改 `--lgz-qc-memory-gb`。省略资源参数或直接运行 `run_all.sh` 时沿用上次生效值；恢复前需申请相应调度资源，不会在线调整正在运行的作业。资源修改不改变分析设置，也不会仅因此使其他条件仍有效的已完成结果失效。

非区域模式下，Q0 各染色体的候选比对共享 `--threads N`：独立任务可并行，相同请求共用经过校验的 PAF。依赖上一轮结果的发现步骤仍按顺序执行。只有能核实作业内存预算时才会并发，否则保留单任务执行。在 Donau 提交时请同时申请 CPU 和内存，不需要增加 CGAT 参数；不能把整台节点的空闲内存当作本作业配额。

计算节点无法访问更新源时，启动会校验本机安装，并在无需下载的情况下对齐 `.lib/`（旧工作区兼容 `.prepare_lib/` 或 `.runtime/prepared/`）。检查失败的详细信息保存在 `.runtime/run_all/update-check.log`；离线启动不表示本机已经是线上最新版本。

`--max-fill <bp>` 设置 Step2 两轮优化补洞的长度上限，默认 `1000000`。已有工作目录可用 `bash "$SERVER/run.sh" -o ./gpm_server --max-fill 2000000` 调整；更换输入或其他准备参数时使用新的输出目录。


完整参数和客户端说明见仓库上一级的 `README_zh.md`。

### 初始参考比对的速度与内存

新工作目录默认 `-K 1G`（query 批大小，**不是内存上限**）。
内存不足时可尝试 `-K 500M`，但不保证因此能够放入内存。
用户可显式添加 `-f 0.01` 启用更激进的种子过滤以提速，**可能改变比对结果**；
显式 `-f` 会被保留，不再自动试选过滤参数。这两个参数仅作用于初始参考比对，
长参数名分别为 `--minimap-batch` 和 `--minimap-filter`。

不传 `-f` 时，普通输入通常仍保留 preset 过滤。对于初始参考 `asm10` 任务，
参考至少 5 Gb、普通 query 合计至少 1 Gb，且存在至少一条 20 Mb 的普通 contig 时，
Server 可自动选取少量**完整 contig**进行校准。校准数据不得超过 128 Mb，
普通输入总碱基量还必须达到校准数据的 64 倍；仅仅“大”不会直接触发降精度。
校准最多运行 6 个原生比对，单次最多 20 分钟、总预算 80 分钟，优先试较温和的
`0.005`。只有重复测速和归属、覆盖检查都通过，才用于后续数据。
小输入和用户显式指定过滤参数的任务不进入这条路径。

这由程序内部判定，不要求用户分类、拆 FASTA 或新增配置。日志会显示启动校准
和后续单元进度；已经获得的完整默认结果会保留。筛出的风险 contig 只做有限的
完整记录默认参数复核；预算用完后，当前尚未解决的记录及后续工作转回默认过滤，
**不从头重跑整个组装，也不丢掉已完成结果**。真正失败或损坏的原生输出不会被
当作成功。正式比对保留正常的批大小、线程及资源设置；校准、复核预算不是整个
作业的内存或耗时保证。自动选择仅作用于当前输入，不写回项目的默认过滤设置。

归属检查使用项目实际的 `--score`，包括非默认阈值，不固定按 60% 判断。
这些检查用于限制已观察到的变化，不代表生物学准确性已证明，也不能据此推算
整个组装的加速倍数。新发布的参考 PAF 会附带 `result.alignment.json`，通过输出
哈希绑定实际策略和源比对参数；完整包、无 FASTA 包都将这些记录保存在
`metadata/alignment_provenance.json` 中，不携带私有日志或缓存。
旧结果没有该记录也可正常打包，但不会为其补造策略信息。

大 PAF 审计改用临时磁盘计算精确统计，不再把 64 MiB 当作正式结果的统一上限。
请提供足够的临时空间；审计错误会保留已完成原生工作，供下次续跑。
校准和复核的执行预算仍有限，不通过抽掉记录来让审计通过。

任务停止后，可用 `bash "$SERVER/run.sh" -o ./gpm_server -K 500M`
调整未完成工作的批大小，不重跑校验有效的已完成比对。
旧项目保留原准备默认值；改变 `-f` 时需使用新的输出目录。
后续新增 dataset 的参考比对也继承已保存的过滤和批大小设置。

### 超长序列的初始参考比对

初始参考 `asm10` 比对在启动映射前检查 query 长度。普通序列仍走原生 minimap2；
超过 268,435,455 bp 的记录才进入重叠分窗、原坐标恢复与候选/置信度核验。
不先让整批数据崩溃，不切割普通记录，不要求用户手工拆 FASTA 或编写配置，
也不修改或替换安装的 minimap2 可执行文件。

长序列处理要求 minimap2 `2.31-r1302`。满足条件的大参考采用有界原生分窗投影，
进行整条记录检查和有限风险复核；该路径支持 Linux ARM64，不需要 x86 辅助程序。
旧的置信度恢复路径仍要求包内 Linux x86_64 辅助程序（兼容 glibc 2.17），
普通比对不需要该辅助程序。不支持的恢复会明确失败，不发布部分结果或伪造 MAPQ。
续跑仅复用校验有效的已完成分组及明确审核过的运行库迁移。

保留原输入和失败日志。停止任务后可用原 `run.sh` 命令或 `run_all.sh` 恢复；
只有来源核验通过的未完成初始参考命令会迁移，并保存回滚日志。兼容且已完成的
参考检查点保留。本地合成控制通过不代表已验收尚未提供的客户完整小麦数据。

### 端粒 / 着丝粒库

v2.0.20 Server 发布包已包含以下注释库；不追溯改变旧版发布包。
流程自动使用 **官方库 + 用户本地库 + 本次 `--tel` / `--cen` 参数**。
显式参数是追加，不覆盖库，也不会自动保存为本地条目。

```bash
bash "$SERVER/library.sh" list                 # 显示官方和本地条目及 note
bash "$SERVER/library.sh" list cen
bash "$SERVER/library.sh" add-tel TTTTAGGG 5 --note "依据：我的文献"
bash "$SERVER/library.sh" add-cen ./my_repeats.fa --note "依据：accession 或 DOI"
bash "$SERVER/library.sh" remove <local_id>   # 使用 list 中显示的本地 ID
```

`--note` 可省略或为空。修改条目时先 remove 再 add；v1 不能删除或停用官方条目。
官方数据位于 `$SERVER/library/`，本地数据位于 `$SERVER/local/library/`；更新不会替换本地部分。
初始 tel 包括 TTTAGGG、TTAGGG、TTAGG，自动检查双链；初始 cen 包括拟南芥 CEN180、
水稻 CentO、玉米 CentC 和人类 α-satellite，只是代表序列，不代表覆盖所有物种。

`--cen` FASTA 名称不再要求染色体前缀；旧 `<chr>_centromere` 名称仍可用，但名称不参与归属。
所有重复序列都搜索各染色体的 assembly。结果为**着丝粒候选区域**，不是功能着丝粒证明，
也不用于分配染色体。`--cen-min-identity` 过滤单个 MUMmer 命中；`--cen-min-len` 过滤合并后
命中实际覆盖总长度（重叠只计一次，间隔不算支持）。v1 内部合并间隔暂定 200 bp，待真实数据验收。
没有命中不等于没有着丝粒。

Prepare 将序列、阈值、全部来源 ID、SHA-256 和 note 固化到项目的 `03_lgz/06_annotations/tel/`、`03_lgz/06_annotations/cen/` 和
`.runtime/metadata/annotation_library_snapshot.json`。续跑只读并校验项目快照，工具/库更新不会让旧项目
自动使用新库；要采用新库需显式重新 prepare，建议使用新输出目录。完整交付包含注释 FASTA；
轻量交付仍排除所有 FASTA，只保留来源快照与校验值。v2.0.20 App 保留来源信息，并将 schema 7 或更早的工作区迁移到 8，以保存 Local View 任务；升级前请备份，不保证旧版 App
能打开迁移后的工作区。源码 review 与自动化测试已通过，不代表全基因组生物学或原生窗口验收已通过。
具体来源与证据边界见 `library/SOURCES.md`。

## DEGAP2.0 与 Server 共用环境

下方手动导出 App `DEGAP-JOBS` 的流程对应已发布旧布局协议。当前源码收集器已将编号工作区的人工候选隔离到 `04_refinement/automatic/degap/06_manual/01_catalog/`，不追加原 LGZ metadata；匹配源码构建的 App 现已按实际 Server 布局解析运行库，并按身份/内容定位种子来源，不猜测便携路径。受控的 App 导出—Server 收集—原 App 导入检查通过，手动编辑的 Final Path 未改变；这不是原生工具验收。迁移清单绑定的旧人工包可接续，不重跑原任务/比对；未知旧结果 ZIP 仍拒绝覆盖。最终验收仍待完成。它与 LGZ 后自动精修及导入各工具新版 App 包是两条不同入口；当前源码的项目级手动精修任务（`refinement_tasks.zip`）请使用下文 `refine.py` 入口。

GPM v2.0.20 附带固定版本的 DEGAP2.0 Server 运行时，以及下文配套的 App 任务卡工作流。
请同时更新 Server 和 App 后使用。

仓库内运行 `bash server/install.sh`，
或在解压后的 Server 包内运行 `bash install.sh`，即可把 GPM 和 DEGAP 依赖一起
安装到 **cgat-server**，无需另建 `degap_env`。安装器可以更新已有的 CGAT 管理环境；
`--check` 会检查外部命令和 Python 模块。
更新已有环境前先停止相关任务。旧安装请先运行新包中的安装器，再更新已安装工具和
项目运行库（新项目为 `.lib/`，旧项目 `.prepare_lib/` 和旧编号工作区 `.runtime/prepared/` 仅作兼容读取/迁移路径），保留原项目及结果，不要删除或重新准备项目。代码更新器不会代替用户安装依赖。
如果旧更新器仍拒绝依赖规格变化，请在已有项目目录中，用**新包的更新器**更新原安装：
`python /path/to/new/GPM_Server/tools/update_server.py /path/to/installed/GPM_Server`。
这样使用新的依赖验证逻辑，保留原安装路径绑定。

App 的“自定义 DEGAP 路径”留空即可使用项目内置工具；Server 项目目录、HiFi/ONT
reads 路径仍需填写实际远端位置。自定义 DEGAP 路径保留在高级设置中。

1. 在目标 Final Path 染色体中导出 **DEGAP-JOBS**。将**整个导出目录**传到 Server，
   包括 `jobs.tsv`、`degap_jobs/*.json`、任务脚本及 `prepare_degap_shared.sh`。
   保留原 App 工作区，回传结果需要其中的导出来源记录。
2. 激活 `cgat-server`，进入导出目录，运行 `bash run_degap_jobs.sh`。
   脚本会准备共享 reads、依次运行任务并收集已完成候选。如需通过调度器提交，
   先运行共享准备脚本，再提交各任务脚本，结束后运行 `bash collect_degap_results.sh`。
3. 收集器为候选生成比对，追加 Server 候选元数据，生成 `degap_results.zip`，并在
   `.run_all/degap-publish-*` 保留回滚备份。暂存过程复用只读输入 FASTA，
   不为每个候选复制完整项目。收集期间不要同时执行其他项目写入操作。
   未完成或失败任务会记录在结果包清单中，不会被当作成功修复。
4. 回到原 App 项目，在 DEGAP 任务卡点击“导入 DEGAP 结果”，选择
   `degap_results.zip`。无需逐个挑选 FASTA、填写染色体或轨道。
   导入内容是**候选序列**，请检查比对后再决定是否采用；导入不覆盖或修改 Final Path。

导入会拒绝外来或过期来源记录、已变化的源对象、校验不一致的结果包，以及与既有导入记录不一致的结果。
后续收集包可以包含先前已导入的任务：记录完全一致的旧结果会跳过，只加入新候选；
仅含已导入任务的包会被拒绝。批量导入失败或取消时，会撤回本批次新导入的候选。修改输入或参数后请重新导出；
旧输出目录属于其他输入时须使用新目录。旧版单任务脚本仍可使用自定义 DEGAP，
但自动打包和关联需要重新导出带来源记录的任务。

维护者：`python3 GPM2.0/scripts/sync-degap-runtime.py` 从父仓库固定的
`DEGAP2.0` 子模块提交生成 `server/tools/degap_core`，`--check` 用于验证。
不要直接编辑生成目录；其中的 `SOURCE.json` 记录上游提交和逐文件 SHA-256。

当前固定版本限制：GapFiller 最大轮数需至少为 1，或留空；TelSeeker 仍支持 0 轮。内置入口会明确拒绝 0 轮 GapFiller，不会擅自修改参数。

### LGZ 后自动精修（当前源码）

提供 `--hifi` 和/或 `--ont` 后，`run_all.sh` 在 LGZ 完成后默认运行 DEGAP；无 reads 时只运行 LGZ。已完成的编号 LGZ-only 工作区可以原地追加 reads，不重跑有效的 LGZ/参考比对。

```bash
bash ./gpm_server/run_all.sh --hifi /reads/hifi.fq.gz --ont /reads/ont.fq.gz
bash ./gpm_server/run_all.sh --gapfill-tools degap,tgsgapcloser,quartet,lrgapcloser
```

四工具从同一 LGZ 基线串行、独立运行；`--gapfill-tools none` 只关闭本次精修，不需要 `--final-tool`。reads 分配、固定版本/兼容补丁、保存参数替换规则与恢复边界见[完整指南](REFINEMENT_zh.md)。未编号旧目录必须先显式迁移；不要覆盖 prepare 或删除有效结果。

新建作业从 `05_final/results.tsv` 查直接可用的基线、自动工具和手动批次 FASTA，详情见 `06_report/report.html`。`07_delivery/` 只发布一对项目 Full/Light；补跑自动精修时更新这对包，并提供一份累计自动补丁。导入项目包无需选工具版本。

### 项目级手动精修（当前源码）

对于匹配新版 App 导出的项目级手动精修任务包（`refinement_tasks.zip`），从对应 Server 工作区根目录执行：

```bash
python .lib/tools/refine.py refinement_tasks.zip
# 可选：按需覆盖 HiFi / ONT reads（可重复传入）；默认直接校验、准备并执行。
python .lib/tools/refine.py refinement_tasks.zip --hifi /reads/hifi.fq.gz --ont /reads/ont.fq.gz
# 高级选项：仅校验并准备局部输入，不运行原生工具。
python .lib/tools/refine.py refinement_tasks.zip --prepare-only
```

新项目公开运行时目录为 `.lib/`，旧项目 `.prepare_lib/` 与旧版编号工作区的 `.runtime/prepared/` 仅作为兼容读取/迁移路径。`~/bin/refine.py` 也可作为全局入口，但严格遵循当前项目运行时优先（先 `.lib/`，再兼容旧 `.prepare_lib/` 或 `.runtime/prepared/`），不混用不同项目的运行时版本。

手动批次报告在 `04_refinement/manual/<批次完整摘要>/03_report/`。使用新任务快照时，`05_final/<out>.manual-<批次前16位>.fa` 可直接使用；`07_delivery/manual/<out>.manual-<批次前16位>.patch.zip` 用于在原 App 项目右上角的精修补丁入口导回，不重打项目 Full/Light。无完整快照的历史任务只返回局部补丁。每个 Gap 可多选工具，优先采用完整闭合，同为闭合时按 DEGAP、LR_Gapcloser、TGS-GapCloser、quarTeT；端粒仍固定用 DEGAP TelSeeker。
