# GPM2.0 Server

**中文** | [English](README.md)

## 快速开始

在 Linux 服务端依次执行以下命令：从 [Release v2.0.11](https://github.com/Jianwei-Zhang/CGAT/releases/tag/v2.0.11) 下载 GPM Server 工具包（源码），解压并进入工具目录，然后安装和运行。

```bash
# 1. 下载、解压并进入 Server 工具目录
curl -fLO https://github.com/Jianwei-Zhang/CGAT/releases/download/v2.0.11/GPM_Server_2.0.11_source.tar.gz
tar -xzf GPM_Server_2.0.11_source.tar.gz
cd GPM_Server

# 2. 安装并验证独立环境
bash install.sh

# 3. 使用安装程序最后打印的命令激活环境，例如
mamba activate cgat-server

# 4. 准备、计算并生成交付包
bash run.sh \
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
bash run.sh \
  --ref reference /path/to/reference.fa \
  --ds assembly /path/to/assembly.fa \
  -o ./gpm_server
```

安装成功时会明确显示 `GPM Server installation: READY`。以后可执行以下命令只检查、不修改环境：

```bash
bash install.sh --check
```

安装程序依次查找 `mamba`、`micromamba`、`conda`。需要明确选择时使用：

```bash
bash install.sh --manager conda
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

### Step3 gap 来源修复后的断点恢复

当连续 N 位于原始 contig 内部，或跨越多个路径片段时，旧版可能报错
`cannot map filtered Step3 gap back to q2`。Step3 现在会在过滤过程中
保留这些 gap 的来源，以及合并 gap 的全部原始来源。

已生成的工作区带有独立运行库副本。更新 Server 代码后，在当前目录执行：

```bash
workspace=/path/to/gpm_server
cp tools/grt_step2.py "$workspace/.prepare_lib/tools/grt_step2.py"
cp tools/grt_step3.py "$workspace/.prepare_lib/tools/grt_step3.py"
cp -R tools/grt_core "$workspace/.prepare_lib/tools/"
```

以上更新适用于已有独立 Step2/Step3 入口的工作区，且须先确认工作区未在运行。
随后在原环境中重新运行或提交 `run_all.sh`。保留缓存，流程可复用兼容的
MUMmer 原始比对，并重新生成阶段结果。仍使用 `run_grt_step23.sh` 的旧工作区
应保留其原配套运行库；仅复制文件不会将旧调度计划迁移为独立阶段。

### 独立 GRT 阶段控制

新工作区生成 `run_grt_step2.sh`、`run_grt_step3.sh`，分别记录调度状态和
checkpoint。先运行 Step2，再运行 Step3；Step3 会拒绝缺失、已改变或引擎
不兼容的 Step2 完成结果。算法实现也已分离：`grt_core/step2_engine.py`、
`grt_core/step3_engine.py`，共用比对、结构分析和元数据服务位于同目录的
`repair_*.py`。源码不再分发 `tools/grt_step23.py`；旧工作区内已有的组合入口
及运行库不自动修改。

Step2/Step3 共用一个覆盖两个引擎、入口和共用模块的内容指纹。更改任一部分
会使阶段结果失效并要求重新执行 Step2；输入、工具和参数均一致时，独立的
MUMmer 原始数值缓存仍可复用。

新生成的正式工作流默认启用以下优化路线：

- `--grt-execution-profile optimized`：跨染色体共享且受 CPU/内存约束的
  nucmer 池、大分区优先调度、校验后的分区 FASTA 复用、精确锚点索引与
  已校验坐标解析结果复用。输出和候选平局选择仍保留原顺序。
- Step2 继续使用 **full 全量范围**，不启用会改变诊断的 Step2 筛选。
- `--grt-step3-mummer-scope gap-screen`：使用修订的锚点安全筛选，选中的
  原始 donor 分区仍与完整染色体比对。
- optimized Step3 refill 同轮合并 flank query，恢复每条染色体的 query／命中
  顺序，并复用内容校验的兼容 `.mmi`。首次比对在同一次调用中保存索引；
  目标字节、preset 或工具变化都会使索引失效。空 query 仍跳过。

如需回退，在用 `run.sh` 或 `prepare.sh` **新建工作区**时传入
`--grt-execution-profile baseline --grt-step3-mummer-scope full`。
Python 入口对应支持 `--execution-profile baseline|optimized`、
`--step2-mummer-scope`／`--step3-mummer-scope`，默认 optimized、Step2 full、
Step3 gap-screen；refill 合批随 execution profile 开关。

已有工作区脚本和运行库不会自动升级，不要修改正在运行的工作区。筛选通过
不代表所有数据都已证明完整证据等价；发布前会用完整数据集与保留的旧结果
对照，不重跑旧版。缓存辅助计时不能当作完整冷启动流程的耗时。

## 可选的 AI agent skill

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

Skill v3 默认自动积累简明的本地经验：问题已修复并验证，且类似坑以后可能再遇到、
记录能减少踩坑时，保存或更新 `local/notes.md`，不再让用户选择记录模式。
后续使用前核对适用条件和证据；用户明确的禁止写入要求及工具权限仍优先。
经验不能授权修改科学参数、破坏性修复或上传数据，详见[本地经验规则](skills/gpm-server/references/local-learning.md)。

[官方版本检查与更新](skills/gpm-server/references/official-updates.md)由
`official_update.py check` 分别查询官网指向的正式 Server Release 和官方仓库当前 skill，
使用附件摘要及固定提交识别版本，而不是依赖历史版本号。`stage` 复核已审阅的计划，
校验下载到新目录，保留本地经验并将候选 skill 绑定到新 tools。
校验、启用及环境变更仍是单独步骤，不覆盖运行中的安装、不迁移已有任务、不改 agent 配置。
已下载的可信本地 skill 仍可用 `stage_skill_update.py` 准备升级。
这是 agent 指导，不是后台更新服务或强制权限沙箱；验证范围见 [v3 记录](validation/agent-skill-v3-official-updates.md)。

只想验证能否跑通时，可要求执行 [合成小数据冒烟测试](skills/gpm-server/references/smoke-test.md)。
它使用小型生成数据与真实工具，不用于科学结论。实际覆盖范围与未验证项见
[ARM/Donau 验证记录](validation/agent-skill-v1-180.md)和
[x86/LSF 与工具路径绑定验证记录](validation/agent-skill-v1-140-1.md)；
skill 是操作指导，不是权限沙箱。

## 文件用途

| 文件 | 用途 | 何时执行 |
| --- | --- | --- |
| `install.sh` | 创建、更新并验证 `cgat-server` 环境 | 首次安装或依赖更新时 |
| `env.sh` | `install.sh` 的兼容入口 | 仅供旧命令继续使用 |
| `run.sh` | 自动准备并执行完整流程，已有工作目录按断点继续 | 首次运行或恢复 |
| `prepare.sh` | 兼容原有的仅准备命令 | 需要单独生成脚本时 |
| `export_final_path_fasta.sh` | 根据 App 导出的 Final Path TSV 重建 FASTA | 流程后期按需使用，不是安装步骤 |

重复同一条 `run.sh` 命令，或执行 `bash run.sh -o ./gpm_server` 即可恢复；已通过校验的结果会复用。生成的 `run_all.sh` 仍可直接执行。

`--max-fill <bp>` 设置 Step3 两轮优化补洞的长度上限，默认 `1000000`。已有工作目录可用 `bash run.sh -o ./gpm_server --max-fill 2000000` 调整；更换输入或其他准备参数时使用新的输出目录。


完整参数和客户端说明见仓库上一级的 `README_zh.md`。
