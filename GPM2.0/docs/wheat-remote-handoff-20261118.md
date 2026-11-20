# 小麦远端对照任务：恢复入口（2026-11-18）

先读 `remote-server-targeted-repair.md`。本页包含 **2026-11-18 20:19（Asia/Shanghai）初始快照及文末按时间追加的后续记录**，不是实时状态，也不是自动部署脚本。不得不核实就照抄旧 job ID 取消/重提任务。

## 目标与访问

- 目标：SSH alias `180`，当前 x86 登录方式 `ssh -p 18083 180`，登录节点 `cli-X86-01`，账号 `xbzhang26`。
- 先按仓库/用户 AGENTS 核实 `ssh -G`、远端规则和 skill；不要修改代理、认证或绕过 host-key 校验来连计算节点。
- 工作根目录：`/share/home/xbzhang26/cgat-reads-debug/`。下文路径相对此目录。
- 环境脚本：`jm19-x86-readiness-20261118/environment.sh`。加载后使用 x86 Python 3.10；默认登录 Python 可能是 3.6，不可直接运行这些恢复脚本。
- `djob` 可能需要 `bash -lic`。大数据哈希、比对及分析走计算作业，登录节点只作有界检查、微型测试和提交。

## 两个工作区

| | 旧版对照 | 新版比较 |
| --- | --- | --- |
| 工作区根目录 | `jm19-full-v2.0.20-20261117/` | `jm19-compare-614589f-20261118/` |
| 分析目录 | 根目录下 `gpm_server/` | 根目录下 `gpm_server/` |
| 快照时 job | `42523432` | `42548272` |
| 快照时计算节点 | `agent-X86-60` | `agent-X86-17` |
| 已核实状态 | RUNNING，LGZ `grt_step1` | RUNNING，q0 染色体比对 |
| 版本基线 | `39e3f3d` 私有 runtime | `614589f` 比较基线，包含 `7c29742b` 扫描补丁及下列现场修复 |

旧版 q0 准备于 19:26 成功，生成 22 条染色体、约 14.27 GB q0 FASTA；19:32:52 进入 step1。新版把染色体比对放在 q0 构建之前，**尚不能从阶段编号推断新版整体更快**。

## 新版中断与恢复链

1. `42530015`：`assign_chr_groups.py` 缺少 `import re`，assign 失败。
2. `import-re-fix-20261118/`：仅回补 import；保存备份、哈希与受保护的恢复入口。
3. `42543824`：成功复用参考比对并完成 assign；q0 比对中并发叠加，在 19:41:33 被调度器因 OOM 终止。硬限制 163840 MiB；退出消息为 mem limit，不能误判成普通脚本错误。
4. `memory-resume-20261118/`：本次有效恢复目录。新 job `42548272` 于 19:49:18 启动。
   - 调度器申请 24 CPU，已核实硬内存限制 245760 MiB（240 GiB）；计算线程预算仍为 16。
   - `TwoMappingDispatcher` 同时最多放行 2 个比对进程。
   - `ProtectedCheckpoints` 禁止失效的参考比对/assign 无声重算。
   - 仅对自比对合并 helper 的等价变更进行显式 assign 检查点迁移；完整验证其他输入及全部输出。
   - `wrap_tasks` 为组装间比对保留独立结果记录，重启时验证并复用成功的叶子任务。

**实际复用证据：** 19:51、19:53 两个参考比对记录 `SKIP_VALID`；19:57 assign 记录 `SKIP_VALID`；20:01 的 `2B`、`3B` 组装间比对记录 `CROSS_LEAF_REUSED`。20:02 开始重跑尚未完成的 `2A`、`7B` 比对。

不要直接运行 `run_all.sh` 或旧 `import-re-fix-20261118/resume.py` 来替代本次恢复入口：它们没有本次的并发限制和组装间比对叶子复用包装。下一次重提先重新审计现有状态、脚本和凭据，不要盲目再次提交同一个目录。

## 现场补丁与 master 保存情况

| 修复 | master | 远端实际范围 |
| --- | --- | --- |
| `assign_chr_groups.py` 缺少 `re` | `220be7a` 中已保存 | 新版安装和工作区内嵌工具两份 |
| 端粒信号必要条件预筛，正例仍走原 regex | `15d75cb` | 新版 `lgz_prepare_inputs.py` 两份，后续准备阶段生效 |
| 自比对批次未到齐时不反复哈希完整前缀 | `5c350fb` | 新版 `self_alignment_batches.py` 两份，OOM 后已应用 |
| 本次并发上限、24 CPU/240 GiB 配额、显式检查点迁移、组装间比对叶子复用 | **现场事故包装，尚未通用化进入 master** | `memory-resume-20261118/resume.py` 与 `.dsub` |

不能把现场包装说成仓库已经具有完整的内存自适应调度/通用子任务恢复功能。任务跑通后，应根据实际证据评估并回补通用修复。DEGAP 及新的 `--hifi`/`--ont` 功能没有部署到这两份科学对照运行中。

## 重点文件

以下都在新版工作区根目录 `jm19-compare-614589f-20261118/`：

- `memory-resume-20261118/resume.py`、`resume.dsub`、`launch.sha256`：当前恢复逻辑、资源申请和启动文件校验。
- `memory-resume-20261118/failed-job.json`：OOM 的调度器证据。
- `memory-resume-20261118/receipt.json`：已应用 runtime 文件的 SHA-256 和范围。其状态字段记录部署当时的状态；实际已提交作业以 `submission.txt` 和调度器为准。
- `memory-resume-20261118/assign.before.json`、`reference.before.json`：迁移与工具来源的原始检查点。
- `memory-resume-20261118/assignment-migration.json`：已完成的仅代码身份迁移凭据。
- `memory-resume-20261118/completed-cross.json`、`cross-leaf-checkpoints/*.json`：`2B`/`3B` 已完成组装间比对的来源与内容记录；后续成功比对也在此提交记录。
- `memory-resume-20261118/local-tests.json`：小型定向验证结果；不代表完整小麦运行验收。
- `gpm_server/logs/status.tsv`、`logs/resume_memory_42548272.out`：阶段与当前 run 的实际日志。
- `gpm_server/.run_all/lock`：正常工作区锁；只能通过现有锁协议处理，不能手动偷锁。
- `reference-import-receipt.json`：原始参考比对的验证导入凭据。
- `telomere-prefilter-20261118/receipt.json`：端粒预筛补丁记录。
- `pending-self-merge-prefilter-20261118/`：历史暂存目录，里面的“未应用”记录已被后来的 `memory-resume-20261118/` 部署取代，不能单独据此判断当前状态。

`watch-comparison.py` 是每 60 秒采样的只读观察器，快照时跟踪 `42548272`，PID `3646465`；读取 `watch-comparison-status.json` 与 `watch-comparison-events.jsonl`。PID/状态都要实时核实，锁文件本身不能证明监控还活着。该观察器不会自动修复任务或向聊天主动发通知。

前台代理的双作业采样写到公共工作根目录的 `logs/wheat-live-*.jsonl`。本机 `/tmp/cgat-wheat-live-monitor.py` 只是可丢失的辅助脚本，不是唯一恢复入口。

## 下一次接手

1. 实时查询两个 job；若出现新 job，沿 `submission.txt`、当前日志与最新事故目录追踪，先核实再更新此快照。
2. 检查是否 OOM、低占用、停滞或重复计算；确认正常长尾后允许继续，不为发布补丁机械中止。
3. 验证新版恢复时确实命中上述复用记录，计算进程并发符合上限；同一工作区不能并发提交两个写入作业。
4. 旧版保持对照；需要修改时另行取得授权。
5. 完成判据是调度器与流水线成功、最终交付物及其完整性验证通过。仅“提交成功”“部分阶段成功”或“测试通过”都不是整项任务完成。

## 补充：2026-11-19 凌晨的单线程诊断

本段为后续诊断记录，不把首页的 2026-11-18 快照伪装为实时状态。

- `42578893`：通过 Donau 在 `agent-X86-17` 提交的只读诊断作业，1 CPU，完成 7 次 /proc 采样，覆盖约 60 秒，调度器状态 `SUCCEEDED`。
- 当时新版正在运行 `7D`、`2D` 组装间比对：两个 Minimap2 进程各有一个线程处于运行态，60 秒内分别消耗约 60 秒 CPU；其余线程睡眠。这证明不是整个进程挂起，但尚不能判定具体热点函数或保证计算能很快完成。
- 证据目录：新版根目录下 `proc-diagnostic-20261119/`。包含 `sample.py`、`sample.dsub`、`submission.txt`、`sample_42578893.out`。
- `42580203`：额外的 10 秒低频用户态性能采样尝试。计算节点没有 `perf`，诊断提前退出；没有安装工具或调整权限，也没有改变主任务。日志为 `perf_42580203.out`。**这个 FAILED 状态不是新版分析作业失败。**
- 直接 SSH 到 `agent-X86-17` 时，严格主机密钥检查未通过；没有绕过。上述诊断使用集群正常调度与资源分配，不依赖计算节点 SSH。
- 本次诊断没有修改比对参数、已有结果、主作业进程或工作区锁。


## 补充：2026-11-19 01:34 第二次 OOM 后恢复（须重新核实实时状态）

- 新版 `42548272` 于 **01:25:41 +08** 被调度器以 `job oom` 终止，`memMax=memLimit=245760 MiB`，退出消息 `errCode: 130`。当时 3D 与 1A 组装间比对并行，不能再将“最多两进程”当作足够的内存保护。
- 14 个成功组装间比对标记保存在原 `memory-resume-20261118/cross-leaf-checkpoints/`，新恢复入口继续使用同一目录，逐项验证后复用。失败的 3D/1A 当时 PAF 都为零字节，已另存日志和命令，不接纳为完整结果。
- 新入口 **`memory-exclusive-20261119/resume.dsub`**，作业 **`42646893`** 于 **01:34:02 +08** 在 **agent-X86-29** 启动。调度器核实申请/分配内存与硬限制均为 **327680 MiB (320 GiB)**，申请 32 CPU，分析线程预算仍为 16。显式申请内存，避免仅增加 CPU 硬上限却仍只预留默认 128 MiB。
- `memory_admission.py` 是本次事故的内部保守调度策略：组装间比对最长查询 ≥100 Mb，或自比对批次总查询 ≥100 Mb，均独占；未知/缺失画像也独占；其他任务最多同时两个。读取已有小型 manifest，不重扫 FASTA。阈值是本次小麦的经验性防护，**不是通用 RAM 估算，也不保证单个任务绝不超限**。
- 1364 个实际叶子任务画像检查：34 个独占、1330 个可双并发；此计数包含已完成叶子，不代表尚余任务数。移除 14 个已完成 cross 叶子后，调度模拟确认首个长任务单独准入。覆盖 cross、自比对、未知画像、阈值边界、并发/线程上限的 7 个测试本地与远端均通过。
- **没有改变比对参数、精度、工具、分析工作区脚本或旧版基线**。新入口保留原 `ProtectedCheckpoints` 和 cross 复用包装，并显式把历史凭据/复用目录定位到旧恢复目录；不可直接复制入口而丢失此关系。
- 恢复证据：`memory-exclusive-20261119/{failed-job.json,recovery-receipt.json,admission-profile.json,targeted-tests.txt,launch.sha256,submitted-job.json,submission.txt}`。备份：`interrupted-leaves/`、`cross-leaf-checkpoints.before/`、`assignment.before.json`。新的运行日志：`logs/resume_exclusive_42646893.out`。
- 只读 watcher 已切换到 `42646893`；启动凭据在 `watcher-update.json`。监控采样告警提前到内存 90%，避免仅在 96% 才提醒。仍需代理核实并处理，watcher 不会自行修复。
- 本次 admission 源码和测试存入仓库 `docs/incident-tools/wheat-20261119/`，**仅作为可复现现场补丁，不代表已接入 master 的默认生产调度路径**。原 cross 叶子复用包装和检查点迁移仍属现场恢复机制，后续通用化需另行整合测试。
- 截至本节记录时间仅证实新作业启动与资源生效，**尚不能宣称本次 14 个叶子已全部重新验收或全流程跑通**；继续查新日志中的 `SKIP_VALID` / `CROSS_LEAF_REUSED`。旧版 `42523432` 保持不动，最后已核实仍 RUNNING。


## 补充：2026-11-19 02:00 续跑验收与运行中扩容诊断

- `memory-exclusive-20261119/resume-verified.json` 记录 **01:54:45 +08** 验收：两个 ref 和 assign 均 `SKIP_VALID`，14 个 cross 叶子均 `CROSS_LEAF_REUSED`，**01:52:17** 实际启动的只有 3D cross（3 线程）。这补足上一节“仅提交/启动”的证据，不代表完整流程完成。
- 独立轻量诊断目录 `resource-resize-probe-20261119/`，不触碰两个分析主任务。首个诊断 `42664586` 因 cgroup 限制文件无读取权限提前失败；加了可选诊断读取的异常处理后，`42664681` 于 `agent-X86-09` 完成，调度器 `SUCCEEDED`，90 次心跳的 PID 一直相同。未绕过权限。
- 在第二个诊断 RUNNING 时尝试 `dmod -R cpu=2,mem=2048MB 42664681`，结果为 **succeeded 0 jobs, failed 1 jobs**，原因 `The value of parameter [cpu] cannot be greater than the original value in resource group 0.`。命令返回码却为 **0**；修改未应用，实际仍是 1 CPU、1024 MiB 申请、10240 MiB 硬限制。
- 结论限定于这个实测配置：不能依靠运行中增加 CPU 来提高本次小麦的内存配额；没有测试或采用绕过每核规则的 `-RL` 修改。调度器显示接收请求也不等于修改成功，必须看逐作业结果与实际资源。cgroup 文件不可读，因此不声称读取验证了底层限制值。
- 证据文件：`guarded-before.json`、`guarded-after.json`、`dmod-result.json`、`final.json`、`conclusion.json` 和两次诊断日志。两个主任务均未被修改。02:00 采样仍显示旧版 Step 2 RUNNING、新版独占 3D RUNNING；后续须继续实时核实。


## 补充：2026-11-19 02:25 续跑摘要缓存淘汰诊断（未部署到运行中任务）

- 新版冻结 runtime 与当时 master 的 `run_orchestration.py` 都将进程内 SHA-256 LRU 限制为 **256 项**。实际 assignment 成功检查点包含 557 个输出；随后 22 个 q0 单元输入准备会遍历更多批次文件，导致已读大文件的摘要被小文件挤出。
- 仅按已有检查点/小型 manifest 和文件 stat 回放调用顺序，**没有重读 FASTA 或 PAF**：assignment 输出校验 + q0 输入准备共 3747 次身份请求、3287 个不同路径。256 项模型读取量 259693454592 字节，其中重复读取模型值 **91134019893 字节**；4096/8192 项模型读取量均为 168559434699 字节，此段调用序列无重复字节读取。
- 证据：新版根目录 `hash-memo-diagnostic-20261119/{metadata-replay.json,metadata-trace.json}`。这是稳定输入假设下的**元数据回放，不是实测磁盘流量、耗时或端到端加速倍率**；不覆盖整个工作流，也不意味着后续每次验证都能免读。
- master 将摘要上限提高为 **8192 项**，只缓存摘要和完整 stat 签名，不缓存文件内容，不跨进程持久化摘要。首次出现、内容/身份变化、缓存淘汰仍完整稳定读字节；命中前后仍核验路径、设备、inode、大小、mtime、ctime。
- 回归复现：601 个文件连续两轮校验，旧版发生 1202 次实际哈希读取；修改后 601 次，返回文件身份完全相同。显式补上淘汰后的完整读取回退测试。`test_resume_report_cache.py` 的 14 项和 `test_run_outer_checkpoints.py` 的 6 项均通过，覆盖内容变化/恢复 mtime、inode 替换、并发、读取竞争、输出损坏和 CIGAR 完整性。
- **当前 `42646893` 不重启，不替换其工作区 runtime，故本次已经花掉的恢复校验时间没有被“优化掉”。** 未来必要的安全恢复边界可在入口进程初始化时设置同一容量（保留原磁盘文件身份与全部校验），并单独记录参数/源码；不能直接热换受检查点绑定的 runtime 文件。


## 补充：2026-11-19 03:25 小范围种子过滤试验（两主任务参数未变）

- **5 Mb 窗口试验 `42675569` SUCCEEDED**，目录 `seed-filter-pilot-20261119/`；**20 Mb 窗口试验 `42677292` SUCCEEDED**，目录 `seed-filter-long-window-pilot-20261119/`。每条染色体从最长查询取开头、中间、末尾三个不重叠窗口，仅测 3D/1A；使用冻结 Minimap2、同一 x86 节点与 3 线程。
- 测试前在计算节点核验原输入全文 SHA-256 与工具 SHA；每种配置单次运行，按 baseline、`-f 0.001`、`-f 0.005` 顺序，超时分别为每次 300/600 秒。结果保存在分析工作区之外，没有改动 native 主任务、赋予候选产物正式完成状态或重新跑整套小麦。
- 较大窗口 3D：baseline 250.36 秒 / 22.231 GB RSS，0.001 为 125.41 秒 / 12.700 GB，0.005 为 24.80 秒 / 4.334 GB；1A：229.39 秒 / 19.774 GB，118.41 秒 / 11.580 GB，30.25 秒 / 4.413 GB。计时不含抽样、源文件校验与索引构建，**不是全流程提速倍率**。
- 每 10 kb 将 primary CIGAR 投影到实际 target/strand/position。3D 较大窗口的 5998 个 baseline 采样位置均在两个候选中找到完全相同位置；1A 则分别只有 5972/5981、5965/5981 完全同位，并存在新增/缺失/歧义位置。覆盖接近不能等同于结果等价或真值精度；窗口试验不覆盖整条长查询的链选择，也未验证 self 模式。
- 原始证据：两目录的 `results.json`、`inputs.json`（各染色体子目录）、命令/PAF/stderr，以及第二目录 `cigar-anchor-comparisons.json`、`final-job.json`。源代码和指标测试位于仓库 `docs/incident-tools/wheat-20261119/`，17 个相关小测试通过（含原 admission 7 项）。
- **不能把候选 PAF 贴上原始命令的缓存身份。** 后续若使用近似参数，必须明确记录变化、验证完整输入上下文，并进行可追溯的检查点迁移；不能声称输出等价或静默切换旧版。两主任务仍分别为旧版 `42523432` 和新版 `42646893`。
- 另：`proc-diagnostic-3d-20261119/summary.json` 为只读诊断 `42672842` 的结果。02:45:57–02:47:07 期间，3D 的一个工作线程实际消耗 69.4 秒 CPU，无 swap、无新增磁盘读取；这排除了该采样窗口的磁盘等待，但不证明算法效率或剩余耗时。


## 补充：2026-11-19 03:29 整条 3D 候选验证启动（非主任务重提）

- 独立作业 **`42681096`**，目录 **`seed-filter-full-3D-pilot-20261119/`**，03:29:43 +08 于 `agent-X86-46` 启动；8 CPU / 81920 MiB，Minimap2 实际 3 线程。只运行完整 3D 的 `-f 0.005` 候选，单次命令上限 1800 秒；不是重跑完整小麦。
- 原参对照直接等待当前主任务 `42646893` 的原始 3D 叶子，不再重复提交基线计算。两个分析主任务和其参数/工作区保持不变。原参位于 agent-X86-29、候选位于 agent-X86-46；以后比较时间要披露节点差异，不冒称严格同节点测量。
- 入口 `full_3d_seed_pilot.py` 先验证 assignment 的原命令/两 FASTA 内容身份及冻结工具 SHA，候选成功后验证完整 CIGAR 和输出哈希。只有 native 叶子的成功 checkpoint 存在且输入/工具/输出身份全部一致，才比较完整 PAF；不能凭一个文件存在/非空接纳原参结果。
- 没有完成 native 对照时，候选只标记 `candidate_complete_native_comparison_pending`，**不会自动复制或导入正式结果**。待 native 完成后，可通过新的调度诊断作业运行该入口的 `--compare-only`：只验收和比较，不重跑比对。启动、超时、失败均须查调度器，不能仅凭日志状态判断。
- 凭据：`submission.txt`、`pilot.sha256`、`pilot_42681096.out`、`f0005/{command.json,result.paf,stderr.log,stdout.log}`；成功产出后有 `result.json`。源码和四个比较安全测试已保存至仓库 incident-tools，连同已有测试共 21 项通过。当前只记录已启动，不宣称候选或主任务完成。


## 补充：2026-11-19 03:51–03:56 完整 3D 对照与分层结果（仍未切换主任务）

- 候选 **`42681096` SUCCEEDED**；原参 3D 随后完成并提交 native 叶子 checkpoint；比较作业 **`42685578` SUCCEEDED**，没有重新执行比对。`seed-filter-full-3D-pilot-20261119/result.json` 当前状态为 **`candidate_and_native_compared_not_adopted`**。
- Minimap2 同工具 SHA、同 `asm10`/3 线程：原参 **7091.836 秒、峰值 125.225 GB**；候选 **583.913 秒、18.254 GB**。本次跨 x86 节点观测耗时比约 **12.15**；不是端到端小麦倍率，也不掩盖 node29/node46 的节点差异。
- `full-input-qc.json` 验证候选处理了全部 **113 个查询**、988 个 target，1342 条 PAF；所有名称/长度与 **assignment 检查点绑定的 `metadata/chr_assignments.tsv`** 一致。查询总长 630780213 bp，覆盖率 99.686%（原参 99.625%）。覆盖率不等于准确率；该文件是 03:42 的输入质量快照，native 比较状态随后已更新，应以最新 `result.json` / `compare-final-job.json` 为准。
- 完整原参有 1072 条 PAF，候选有 1342 条。每 10 kb 采样 primary CIGAR：62772 个 baseline 位置中，62577 个在候选中保留完全同位（约 99.689%）；**窗口内的 100% 同位不能外推到整条查询**。
- 分层诊断 **`42686656` SUCCEEDED**，结果在 `stratified-comparisons.json`：>=100 Mb 查询为 28861/28899 完全同位，<100 Mb 查询为 33716/33873；195 个变动/缺失点中 157 个（80.5%）来自后者。即便只看 baseline MAPQ=60，全组仍有 100 个点不完全同位，其中 >=100 Mb 组占 18 个。不能把变化全部解释为低置信度噪声。
- 原参 3D 叶子标记：`memory-resume-20261118/cross-leaf-checkpoints/b8addc3ddb987e62e6b61a9ff130901e20824047d16f7b14b2a58940cfb15ead.json`；继续保留其原生结果与其他成功叶子，**不为安装优化而替换已完成的 3D**。截至 native 3D 完成，新版已有 15 个成功 cross 叶子，仍需核实当前活动叶子与后续 self 任务。
- 后续值得验证的是**按整条 query 长度路由**，让超长 query 走经质量评估的近似参数，其余保留原路径，且不切碎长 query、不丢记录、保留输出顺序及每条记录的参数来源。该方案尚未实现/部署，不能宣称已有自动触发，更不能把上述 12.15 倍直接套给这个拟议混合路径；self 模式仍需独立验证。
- 新增源码 `stratify_full_3d.py` 及测试已保存；23 个相关小测试通过。两分析主任务、原参数、原缓存与发布资产均未修改；后续接入需要新的明确参数来源与检查点迁移，不能让近似 PAF 冒充原参缓存。


## 2026-11-19 05:20 +08 续接快照：1A 完成与隔离路由验证

- 两主作业仍 RUNNING。新版 `42646893` 于 **05:11:13** 完成原参 1A cross，
  同时启动 6A cross（5 线程）；已有 **16 个** cross 成功标记。当前主要任务
  仍使用原生比对命令，未部署新的长记录路由，未取消或重提。
- 旧版 `42523432` 仍在 Step 2；按 `run_all.log` 的 SUCCESS 记录去重，
  1D 已成功 **1357/2402** 个分区。分区编号不是完成数，不按最后一行编号估计。
- 隔离路由原型及测试见 `incident-tools/wheat-20261119/`。初版远端
  `42701257` 成功（21 项）；复查修复了最终回执缺少 preset 身份绑定，
  并补上代码变更、多索引普通路径回退检查。最新本地事故测试 47/47 通过。
- 修订版隔离作业 **42703218** 在 `agent-X86-46` 运行，24 项路由测试已
  全通过，之后执行真实 3D 小型普通记录对照与长记录窗口校准。目录：
  `long-query-router-validation-v2-20261119/`。此快照尚未确认校准结束。
- 不应把这些测试当成原型已接入 master 的默认运行路径或已用于主任务。
  不替换已完成的 3D/1A 结果，不修改活动 q0 的 command/helper/manifest。
- 前一只读监控会话已正常结束，替代监控从约 05:16 开始，仍只负责采样。
  接续时先查作业及 `real-calibration.json`，不得重复提交隔离作业。
- 后续核实：真实 3D 的三个普通记录重新分组后，比对 PAF 与已完成原生结果
  中对应记录 **逐字节相同**；长记录校准仍在运行。这是有界子集证据，不是全数据
  等价保证。只读监控日志为 `logs/wheat-live-20261119-051639.jsonl`。


### 05:22 补充：隔离真实校准已完成

- `42703218` 于 **05:21:28** SUCCEEDED；源码 SHA-256 清单复核全部一致。
- 三个普通记录共 953632 bp，重分组后的 PAF 与原结果逐字节一致。
- 唯一 >=100 Mb 记录 `ptg000049l` 长 289508469 bp；内部默认策略为其
  三个 5 Mb 窗口选择了 `-f 0.005`。1498 个基线采样位置均有精确匹配的候选
  支持，另有 1 个新增候选采样位置。没有执行完整长记录重比对或接入主任务。
- 下一步应验证 **尚未完成** cross 叶子的适用范围及显式检查点迁移，而不是
  重跑已完成的 3D/1A。普通记录默认原参；self 和初始参考比对仍排除在此路由外。
  当前 q0 输入身份已冻结，不能在运行中替换 helper/command/manifest。
- 已保存 `long-query-router-validation-v2-20261119/final-job.json` 和
  `real-calibration.json`。两个主作业在 **05:22:08** 仍均 RUNNING。


## 2026-11-19 05:40 +08：续跑适配已隔离验证，尚未切换主作业

- 当前作业仍为旧版 `42523432` / 新版 `42646893`；新版仍在 6A cross，
  16 个原参 cross 已完成。05:40:45 采样新版约 2 核、74600 MiB，未出现失败；
  旧版 Step 2 约 15.5 核。不要因线程数下降或暂时零 PAF 自动取消长序列任务。
- 只为尚未完成的 **1D、4D、5D、6D cross** 准备了显式执行替换：
  `routing-resume-staged-20261119/routing-plan.json`。6A、Un、所有 self 和初始
  ref 均不在替换范围内。该判定的长度画像只用于选候选；真正运行仍完整读源
  并按内部策略校准，不能把 self manifest 的重命名长度图冒当真实 cross 输入证明。
- 不再计划重写 workspace command 或迁移 assignment 输出。入口在调度时替换
  执行脚本，同时把实际脚本/代码/策略绑定到叶子与 q0 外层检查点。原有命令、
  helper、manifest 未修改，当前主进程未重启。
- 验证 `42706833` 已 SUCCEEDED（05:37:52），远端 15/15；本地事故套件 62/62。
  特别覆盖 q0 收尾重新捕获输入指纹、拒绝将 routed 结果当 native 缓存以及真实
  subprocess 调度的回调身份。证据：`validation-final-job.json`、
  `validation_42706833.out`、`staged.sha256`、`wheat-routing-support.sha256`。
- 已准备 **未提交** `routing-resume-staged-20261119/resume.dsub`，沿用 32 CPU /
  327680 MiB 申请，实际原有全局线程预算不变。新入口在进程内将实际读取得到的
  SHA memo 上限调为 8192，不修改 frozen runtime、不灌入回执摘要。
- 后续安全切换：优先等 6A 完整成功标记；再次核实计划中的四个 leaf 是否已有
  原参完成记录，若有就从新计划中排除，不要替换已完成结果。新入口会拒绝这种
  过期计划。检查当前作业停止和 workspace lock 后才提交，随后确认两个 ref、
  assign 及全部已完成 cross 的有效复用。**不要直接执行普通 run_all.sh。**
- 入口支持文件存入仓库 `docs/incident-tools/wheat-20261119/`，仍是事故适配，
  不代表 master 默认生产运行路径已启用。真实新旧整套任务均未完成。


## 2026-11-19 06:02 +08：已切换，新主作业 42710779

**当前新版主作业是 `42710779`，不是 `42646893`。** 旧版对照仍是 `42523432`。

- 6A 原参 cross 在 **05:55:39** 成功，已完成原参 cross 增至 **17 个**。
  对完成标记的 status、command、run_id、PAF/日志实际大小和 SHA-256 做了有界
  复核。随后只对新版旧作业 `42646893` 发出 `dkill`，其 FAILED 是**受控终止**，
  不是新增 OOM 或算法失败。刚启动的 5D 只有未完成输出，未作为成功缓存接纳。
- 旧作业终态已核实；workspace lock 已自行释放，**没有手动删锁或清理缓存**。
  备份：`routing-resume-staged-20261119/cutover-20261119-0555/`，含 17 个原参
  叶子标记、原外层检查点、6A 完整证明、停止前/后调度信息及 dkill 返回记录。
- **42710779** 于 **05:58:10** 在 `agent-X86-06` RUNNING，申请 32 CPU /
  327680 MiB，实际全局预算 16。入口 `routing-resume-staged-20261119/resume.dsub`；
  日志 **`logs/resume_routed_42710779.out`**；run ID
  `20261118T215811Z-1612976-2eca2eb1`。提交记录位于同目录的
  `submission-intent.json`、`submission-result.json`、`submitted-job.json`，勿重复提交。
- 启动清单全部通过，入口记录了实际执行替换和进程 SHA memo 上限 **8192**。
  **06:00:51、06:02:26 两个 ref 均已 SKIP_VALID**，没有重跑初始参考比对。
  本节时点 assign 和 17 个 cross 的本次复用尚待日志确认，不能提前宣称验收完毕。
- 新的只读采样日志：`~/cgat-reads-debug/logs/wheat-live-20261119-055915.jsonl`。
  持久只读 watcher 已切到 42710779，PID **1577626**（cli-X86-01，已核实进程存活），
  `watch-comparison-status.json` 已报告新 job RUNNING。它只记录状态，不自动修复。
- `run_all` 原生 PREFLIGHT 日志中的 `parameters unchanged` 仅描述它自身的普通
  runtime 风险快照，不能用于宣称这次所有 cross 参数不变；实际替换以
  `EXPLICIT_ROUTING_RESUME`、`ROUTE_EXECUTION_OVERRIDE`、叶子/外层身份及最终
  `routing-receipt.json` 为准。
- **最终交付还需附带 q0 路由审计说明/结果证明。** 已核实 frozen App packager
  仅投影 `recorded_initial_reference_alignments_only` 的 alignment policy，
  不会自动带出 `routing-receipt.json`。不要把 q0 回执伪装成参考比对的 policy，
  也不要把仅有 App 包视为已交付这次现场近似策略的完整审计信息。保留工作区审计，
  全流程完成时生成与输出 SHA 绑定的独立 q0 provenance 附件并随比较结果交付。
- 本次登录节点控制脚本最初误用了系统 Python 3.6，因 `subprocess(text=...)`
  不支持而在任何停止操作前退出；加载已确认的 x86 environment 后执行成功。
  后续控制脚本同样先 source 该环境，不修改系统 Python。


### 06:10 补充：初始阶段与 17 个 native cross 已确认复用

- 当前 run 的两个 ref 已分别于 06:00:51 / 06:02:26 SKIP_VALID；assign 于
  **06:07:09** SKIP_VALID。**17 个** native cross 都出现 CROSS_LEAF_REUSED
  和 exit_code=0 的 TASK_END，包含刚完成的 6A；没有重跑这些比对。
- **06:08:28** 首个实际 routed leaf 为 **5D cross**，日志明确记录
  `ROUTE_EXECUTION_OVERRIDE`，执行 `routing-resume-staged-20261119/route-5D.sh`。
  由作业启动到该叶子执行为 **10 分 18 秒**，包含本次内容校验，不是比对耗时；
  不把跨节点/不同缓存状态的耗时差直接说成缓存优化倍率。
- 06:09:58 检查时，5D stdout 已先后记录 baseline 与 `-f 0.005` 的窗口校准启动，
  stderr 为空。尚未完成整条 5D，不能提前声称其近似分支最终通过或已经提速。
- 复用验收存于 `routing-resume-staged-20261119/resume-verified.json`，包含当前
  run ID、三个 SKIP_VALID 原始事件、17 个原参叶子列表及实际执行替换事件。
  路由的详细阶段在对应 leaf 的 `stdout.log`，不能只看顶层 checksum 日志。


## 2026-11-19 06:27 +08：5D 两条长记录完成，普通记录继续

- 两个主作业仍为 `42523432`（旧版）和 `42710779`（新版），均未出现新的终态失败。
- 新版 5D 的两条完整长记录 `ptg000071l`（105593624 bp）、`ptg000084l`
  （154141050 bp）以 `-f 0.005` 完成组内比对，成功缓存的 native 日志记录
  **245.858 s / CPU 441.563 s / Peak RSS 14.069 GB**，`mid_occ=63`。
  **这不是整个 5D 的耗时**：窗口校准和其余 639 条普通记录另计，普通组仍在运行。
  没有完整原参 5D 对照耗时，不据此声称端到端或单染色体倍数。
- 旧版 1D 成功分区在 **06:27:40** 去重计数为 **1593/2402**，仍属 Step 2。
- 补齐了最终交付用 `export_routing_provenance.py`，输出独立的
  `comparison-audit/q0-routing-provenance.json`。它验证已提交的所有计划内 routed
  叶子，核对实际输出/回执、记录分组与真正采用的 filter；不会冒充参考比对 policy，
  不宣称整套 workflow 完成，也不将未重新读取的 FASTA 摘要说成刚完成的内容校验。
- **42715067** 已 SUCCEEDED（06:22:37）：9/9 exporter 测试及真实工作区“不完整
  范围不得发布审计”的门禁通过；本地整个事故套件 71/71。目录
  `routing-audit-validation-20261119/`，源文件 SHA 清单复核一致，`final-job.json`
  已保存。当前只是工具就绪，**最终审计附件尚未生成**。
- 实际 frozen `alignment_tasks.json` 的 5D 后续 chr 阶段只有 tel/cen 扫描，不包含
  已前置的 cross/self 比对；未因担心重复执行而盲目修改它。审计脚本在独立目录，
  没有热替换当前 q0 捕获的任何依赖。


## 2026-11-19 07:11 +08：5D、4D cross 完整成功，当前 1D

- 主作业仍为 **42710779**（agent-X86-06），旧版对照 **42523432** 保持 RUNNING。
  **5D cross 于 06:36:16 成功，4D cross 于 07:09:47 成功，立即开始 1D cross**
  （4 线程）。共 **19 个**成功 cross 标记：17 个原参 + 2 个路由结果；self/外层
  q0 阶段仍未全部完成，不能据此报整体完成率。
- 5D 整组耗时 **27 分 48 秒**，641 个输入记录完整处理。组内 native 日志：
  2 条近似长记录 245.858 s / 14.069 GB；639 条普通记录
  **1242.760 s / 48.300 GB**。二者以外还有窗口校准及封装开销。
- **42720570** 已 SUCCEEDED（06:52:34–06:54:48），独立核对了真实 5D 最终 PAF、
  回执、记录来源和已完成分组的文件摘要；首次真实路由叶子验收通过。
  4D 回执也已完成：6 条记录中 1 条近似、5 条原参，整组耗时 **33 分 31 秒**；
  组内时间分别 480.339 s / 1432.375 s，不能把长记录时间冒充整组时间。
- 同一诊断复用了现有完整 3D PAF 做长度分层，不重跑 3D；另只跑了一条完整的
  5D **51,086,554 bp** 记录的 `-f 0.005` 候选，原参基线直接复用已完成结果。
  候选 126.046 s / 5.143 GB，但在 10 kb 与 1 kb 网格均约 **3%** 基线位置
  不再有同目标/方向/100 bp 内位置支持，且新增候选位置也超过门槛。
  覆盖率增加不等于结果等价；这不是生物学错误率，也没有该记录单独的原参耗时。
- **没有采用这个候选，没有将主策略降到 50 Mb，没有替换已完成的原参结果。**
  3D 的 50–100 Mb 组平均差异小不代表其他数据都成立。50 Mb 窗口自动门控本身
  尚未测试，不能把完整候选的拒绝当成自动选择器通过/失败的证明。
- 证据目录：`routing-first-leaf-qc-20261119/`；重点读 `first-leaf-qc.json`、
  `length-strata.json`、`medium-record-study.json`、`final-job.json`。
  脚本 `inspect_routed_leaf_and_length_strata.py` 已完成真实数据验证并复核 SHA。
- 05:59 启动的限时只读采样正常结束后，已启动新一轮同任务采样；持久 watcher
  仍跟踪 42710779。没有因观察窗口结束而重启分析作业。

## 2026-11-19 08:45：四个 routed cross 完成，自比对开始

**08:45:41 实时查询：** 旧版 `42523432`（agent-X86-60）及新版
`42710779`（agent-X86-06）均为 RUNNING。旧版仍在 `grt_step2`，
近期 CPU 约 15.5 核；新版当前只有约 1 核、实际内存 22158 MiB。
不得将历史快照中的旧版 Step 1 当作当前阶段。

四个计划内 routed cross 均已提交成功，新增后两项如下：

| cross | 开始 | 成功 | 整个叶子耗时 | 近似 / 原参数记录数 |
| --- | --- | --- | --- | --- |
| 1D | 07:09:47 | 07:38:36 | 28 分 49 秒 | 1 / 285 |
| 6D | 07:38:36 | 08:15:30 | 36 分 54 秒 | 1 / 13 |

- 现有 **21 个成功 cross 叶子**（17 个原参数 + 4 个路由），不是全部
  q0 完成，更不是全小麦完成；Un cross 不能据此推定成功。
- 6D `ptg000007l`（112204859 bp）两个候选过滤值均未通过位置支持门槛，
  实际保留原参数运行；`ptg000065l`（171965627 bp）通过 0.005 校准。
  这是实际自动回退的证据，不是对全部长序列无条件提速。
- 新版在 08:15:30 启动
  `runs/chr_3D/JM19_hifiasm_vs_self/batches/batch-00003/command.sh`。
  查询只有一个完整记录 `gpm_pair_000000004b`，289508469 bp；目标含
  113 个记录、630780213 bp。原命令明确 `-t 1 -X --no-hash-name -m 200 -n 100`。
  `mid_occ=500`。已复用 `target.mmi`；不能把它诊断为每批重复建索引。
- 08:39 检查该批次还没有 `complete.json`，临时 `raw.paf` 为 0 字节；
  08:45 主日志尚无该批次 TASK_END。CPU 持续工作和单核长尾需要调查，
  但零 PAF 不是失败或可丢弃当前计算的证据。

### 路由结果的独立交付审计已导出

作业 `42737813` 于 08:23:46–08:23:48 **SUCCEEDED**，输出：

- 新版根目录 `comparison-audit/q0-routing-provenance.json`，20153 字节。
- SHA-256：`b318e68e3d58de4d1cde3fbba528e440d99baba55b27f2626810f0f3fac1820a`。
- 范围仅四个 routed cross，947 个查询记录：5 个近似、942 个原参数。
- 实际输出/路由记录与完成标记的绑定已验证；源 FASTA 哈希来自完成检查点，
  不冒称导出器重新读取了全部源 FASTA。`certifies_whole_workflow=false`。
- 导出作业证据在 `routing-audit-validation-20261119/export-*.json`。
  最终对照交付必须附带此文件；当前冻结版 App 打包只携带初始参考比对策略，
  不会自动携带这个 q0 路由审计，不能把 App 包单独称为完整审计包。

### 单条完整自比对候选：隔离运行，不自动采纳

- 保留主作业当前原参数自比对作为唯一基线，不复制原参数计算。
- 新作业 **42740281**，08:45:25 开始，agent-X86-61；申请 8 CPU /
  81920 MiB 是为了内存配额，实际 mapper 仍 1 线程。
- 根目录 `self-full-3D-pilot-20261119/`，脚本 `candidate.dsub`；
  候选输出只在其 `candidate/` 子目录，不写分析工作区。
- 保存到仓库的 `full_self_seed_pilot.py` 验证原完整查询、原缓存索引、工具、
  名称映射及恢复脚本；只添加 `-f 0.005`，不切片、不重建索引、不改自比对标志。
  候选实际已加载相同索引，日志 `mid_occ=64`。
- mapper 上限 1800 秒，恢复名称上限 300 秒；超时/中断 kill 并 wait 自己的子进程。
  退出码、完整查询遍历、PAF 名称/长度/坐标/CIGAR、输入稳定性全部通过才记录候选完成。
- 本地事故工具集 **81 项通过**；新脚本 10 项测试也在该远端作业中通过，
  覆盖越界输出、缓存损坏、参数变更、中途输入变化、未完整遍历和超时回收。
- **自比对不能直接用 cross 的 primary-only/window 校准决定采纳。**
  等原批次成功提交后，需比较所有相关自比对命中、配对及坐标支持，并验证原生
  批次完整标记/输出；当前没有采纳逻辑，也没有宣称速度或科学结果等价。
- 只读主任务监控仍为 `logs/wheat-live-20261119-081651.jsonl`，本地执行会话
  `70157`；有限时长监控结束不等于主任务结束。

### 下游仍需防止全量 MUMmer 长尾，尚未修改

已核实实际 prepare options / 生成脚本：旧版 Step 2 为 `full`，
新版对应 LGZ Step 1 **仍为 `full`**；两者下一步分别 Step 3 / Step 2 为
`gap-screen`。q0 cross 结果不能直接视为 MUMmer 修复证据而跳过。
新版 `grt/q/q0.fa` 尚不存在，不能用旧 q0 的 gap/donor 规模代替新数据判断。

现有 `repair_mummer.py` 已跳过无 gap 染色体，并有 donor 分区缓存、共享池
及 gap-screen；不要重复实现这些能力。gap-screen 用 MUMmer 筛选 gap 窗口，
再对选中的 donor 分区跑完整 Q；它不是直接把局部 PAF 当完整证据。
是否内部自动选择此模式，需根据实际 q0 gap 窗口覆盖和 donor 工作量评估，
保留完整参数/缓存身份与已有效的全量结果。**当前未修改 prepare_options、
下游 wrapper、活跃路由依赖或原有检查点。**

## 2026-11-19 08:58：预防下游检查点读取失败，自比对候选成功

### q0 证据读取入口定点修复，无重提

主动检查发现：冻结的 `lgz_core/q0_preparation.py::_initial_inputs()`
独立创建原生 `OuterCheckpointManager`。四个路由外层检查点含显式
`incident_execution_overrides`，主控制器已支持写入，但原生下游 reader
会因输入身份/输出清单不同而拒绝。不是检查点损坏，也不能删除路由字段来绕过。

- `routing_q0_evidence_reader.py` 使用**同一份冻结路由绑定器**，为该子进程
  提供只读管理器；完整验证原输入/输出，并额外验证路由参数、依赖、PAF 和 receipt。
  其 `commit()` 明确拒绝写回比对检查点。
- 原始 q0 科学构建器、policy 和 builder identity 保持不变；实际入口与
  `metadata/incident_q0_routing_reader.json` 作为额外输入纳入证据清单。
  原构建器发布前的身份检查还核实路由依赖和入口/声明未变。
  后续 `lgz_prepare_inputs` / `q0_admission` 仍用未改动的 `load_verified_evidence`。
- 10 项定向测试复现“原生 reader 拒绝、显式 reader 通过”，并覆盖损坏 PAF、
  缺失 receipt、依赖变化、只读边界、恢复模块状态及下游对新增输入的完整性验证。
  **本地全套事故测试 91 项通过**；远端验证作业 **42741013** 于
  08:56:10–08:56:14 SUCCEEDED，10 项通过，且实际冻结模块/路由计划只读导入通过。
- **08:57:34** 仅原子替换 `gpm_server/prepare_q0_evidence.sh`。
  安装前后 `q0_evidence`、`grt_prepare` 都是 pending / attempt 0；
  新版主作业 `42710779` 仍 RUNNING。没有终止、重提、更新安装包或改动活跃比对依赖。
- 已核查已保存检查点不引用此入口，当前 q0 对齐输入集合和路由依赖也不包含它；
  主 Runner 在该阶段开始时读取脚本，报告 START 会重读实际 command text。
- 原入口 SHA：`a64b66847d3f8ea2b132697064d8e3020a8593e9c5278591149eeda49a303eec`。
  新入口 SHA：`21a9dbb0bfad11fdf52a583ad0babb94a8688d256883a25ee52dab6d66f72ff2`。
  reader SHA：`349558353c156c5bd3e7d390f2cbf3ce59ef46e71a0a6842ff5ee4c428b90e90`。
- 证据及备份：新版根目录 `routing-q0-reader-20261119/` 下的
  `validation-final-job.json`、`installation-intent.json`、`installation-receipt.json`、
  `prepare_q0_evidence.original.sh`、`code.sha256`。
- 回退只适用于该阶段尚未启动时恢复备份；恢复原入口也会恢复其“不识别路由”
  的行为，不是端到端可用性保证。证据生成后改入口会使其已绑定身份失效，
  需重新评估，不能悄悄覆盖。
- **当前只是安装了未来阶段入口，尚未执行真实全量 q0 evidence，更不能称该阶段通过。**

### 完整自比对候选已成功，但原参数基线未完成

作业 **42740281 SUCCEEDED**；`self-full-3D-pilot-20261119/final-job.json`
及 `candidate/pilot.json` 已保存。完整 289508469 bp 单查询候选：

- mapper wall **444.913 s**；Minimap2 自报 CPU 442.695 s、峰值 **5.073 GB**。
- raw PAF 9577356 字节，SHA
  `f771401f07a87b68285451cbd9bf98980072ee84c590091f222a07c13adc040b`。
- 恢复原名称后的 PAF 9083238 字节，SHA
  `450269528392fe2e847c44ddd1571a8a830bea0ad73d20492f39c655ba1065b9`。
- 完整遍历、退出码、PAF、输入/索引稳定性校验已通过；状态为
  `candidate_complete_not_compared_not_adopted`。
- **08:58 原参数批次仍无完成标记**；不能计算完整基线加速比或宣布保真。
  实际候选前几行包含 `tp:A:S` 的多位置命中，说明 primary-only cross 检查
  不足以评价这个自比对。后续要按所有相关命中/配对及坐标支持比较；不重复跑基线。


## 2026-11-19 09:13：自比对全命中核验工具就绪，尚待基线完成

- 主作业最近监控采样（09:13:06）：旧版 `42523432` 与新版 `42710779` 都 RUNNING。
  新版仍是 08:15:30 开始的原参数 3D self batch-00003，尚无成功标记。
  不为取得比较基线额外启动同参数任务。
- 新增 `self_paf_comparison.py`：不筛掉 secondary / MAPQ 0；按 query-grid /
  target / strand 对不同目标位置一对一匹配，防止一个候选位置掩盖多个基线位置
  丢失。相同位置重复项合并并另记数量；另对每个有方向的序列对比较 CIGAR 对齐
  区间并集，捕捉采样网格以下的覆盖变化。这些量不是全基因组唯一覆盖或生物错误率。
- `inspect_full_self_pilot.py` 只读已有文件，不启动 mapper。实际比较要求原生
  `complete.json` 的 key、全部三个输出及哈希有效，且原始命令、输入、完整遍历、
  PAF 及前后稳定性验证通过；临时/部分 PAF 不可当基线。比较使用 1 kb、10 kb
  两种网格，**没有自动采纳逻辑**。
- **本地事故工具集 114 项通过**。远端作业 **42744063** 于
  09:11:04–09:11:12 在 agent-X86-18 SUCCEEDED，23 项专用测试通过。
  随后实际验证候选来源/输出并计算清单，无重新比对、无主工作区写入。
- 当时原参数完成标记仍不存在，输出仅
  `self-full-3D-comparison-20261119/candidate-inventory.json`：
  27451 行，其中 **24855 secondary / 2596 primary**；80 个有方向的序列对；
  1 kb 网格有 261140 个不同投影位置、926 个重复位置观察被合并。
  这是实际数据上 primary-only 核验不充分的证据，**不是两种参数已一致**。
- 作业/代码证据在同目录 `final-job.json`、`code.sha256`、`inspection_42744063.out`。
  inspection SHA：`079904c40b1ad5c940566e6cdf19152e696c5fd8a6c7ae12e18d59a8c56b0ef5`；
  comparator SHA：`e8683c9c4196c3afba56379471915fd5a01cf7905d31b039e3e53eefb323b5d5`。
- **下一步**：监控原生 `batch-00003/complete.json` 及主日志 TASK_END；成功后
  提交仅比较的短作业，用同一冻结 inspector、不带 `--candidate-only`，写新的
  `comparison.json`（不得覆盖已有诊断结果）。先核验完成标记再讨论 self 优化。
- q0 routed-reader 修复已经安装，但 q0 evidence 阶段尚未运行；仍需后续实际验收。


## 2026-11-19 后续监控：旧版 1D 完成与 self 任务清单核实

- 旧版日志在 **09:53:09** 明确记录 `LGZ step2 MUMmer 1D: computed`，
  随后继续 4D 分区；Step 2 和整个工作流均未完成。不要把单染色体的
  2402/2402 当作 Step 2 总进度。旧版未作任何改动。
- **10:01:47** 的只读 manifest 清点核实：当前 q0 对齐计划共 **1364** 个任务，
  其中 **1342 个 self batch**；所有清点到的 self batch 都在实际
  `q0_alignment_tasks.json` 中，没有把未计划的旁路目录计入。
- self query 总长度分组：21 个 >=100 Mb（全为单记录）；311 个 20–100 Mb
  （全为单记录）；1010 个 <20 Mb（806 个多记录批次、204 个单记录）。
  >=100 Mb 的 21 个包括当前正在运行的 3D，不能再额外加一次。
- 清点时只有一个 self 完成标记存在：
  `runs/chr_4D/JM19_flye_ABD_vs_self/batches/batch-00029`，查询 20074241 bp，
  单记录，原日志完整遍历耗时 4.335 s / peak RSS 1.225 GB，标记中 raw/result PAF
  均为空文件哈希。该清点**不是全部输出内容重新验收**；真正续跑仍走原有校验。
  不要用这个零命中样本证明过滤参数保真，也不要把最大 3D 的耗时乘以全部 self 数量。
- 资源/排队判断应区分单条长查询和多记录批次。当前 100 Mb 独占策略覆盖
  21 个长批次；其余仍受两个 mapping 并发上限约束，没有在运行中擅自修改调度器。
- 原始规模报告在新版根目录
  `self-full-3D-comparison-20261119/workload-inventory-20261119-1001.json`，
  仅读取 manifest，不扫描 FASTA、不计算新比对、不修改检查点。
- 先前只读监控会话 `70157` 已按时长正常退出，不是主作业退出。
  **当前本地监控会话 `73376`**；日志
  `logs/wheat-live-20261119-091813.jsonl`，30 秒采样，约 90 分钟窗口。
  已增加 self 临时 raw PAF 大小、完成标记存在性和持续单核提示；提示不自动取消任务。
  监控结束后先查主作业状态，再续开只读监控，不要因此重提科学作业。


## 2026-11-19 11:02：局部 self 校准不通过，主任务保持原参数

- **10:55:03** 调度器确认旧 `42523432`、新 `42710779` 均 RUNNING；
  **11:00:28** 监控再次确认。新版仍在 08:15:30 启动的 3D 原参数 self，
  完成标记不存在、临时 PAF 尚空；持续约 1 核、22306 MiB 内存。旧版继续 Step 2。
- 为避免逐条重复长基线，隔离研究了保留名称/完整长度、窗口外填 N 的局部
  native 校准。仅比较窗口内所有命中位置，不切改正式 FASTA，也不修改主任务。
- 三个 5 Mb 窗口：作业 **42749029** 于 10:28:57 FAILED，原因是主动设定的
  300 秒 mapper 超时（returncode 124，300.088 s）；已 kill/wait 自己的 mapper，
  不是主作业失败。证据在 `self-masked-probe-20261119/`，没有完整校准结论。
- 缩到三个 1 Mb 窗口：作业 **42766357 SUCCEEDED**，10:56:04–10:58:50；
  mapper 152.966 s，45 项远端测试通过。证据在
  `self-masked-probe-1mb-20261119/{final-job.json,native-probe/probe.json}`。
- **未通过拟定局部保留门槛，不采纳**：局部 native 40533 个采样位置，
  完整快速候选限制到同窗口后 1770 个位置，100 bp 内一对一匹配 1754，
  38779 个局部基线位置未获得支持；还存在显著配对丢失和配对内覆盖损失。
- **关键限制**：masked native 与完整候选的查询上下文不同，mask 会改变 chaining。
  因此 ~95.67% 是这个局部实验中未支持位置的比例，不能声称是完整序列的丢失率、
  全部来自 `-f` 的效应或生物学错误率。未完成的全原参数基线仍需核验。
- 新增 `masked_self_probe.py` / 测试、扩展 comparator 的窗口裁剪，
  本地事故工具 **126 项通过**。原 `self-full-3D-comparison-20261119/`
  冻结 inspector/comparator 没有被覆盖；正式比较仍可用原冻结文件。
- 当前监控会话 **51160**，日志 `logs/wheat-live-20261119-105627.jsonl`。
  前一会话 `73376` 按 90 分钟时长正常退出，不是主任务退出。
- 下一步仍优先完整原参数批次成功后的已有结果对比；不能仅凭候选快就改全局
  self 参数，也不能为等基线而重复跑完整 native。若继续局部研究，必须控制查询
  上下文差异，区分 mask 效应和过滤参数效应。


## 2026-11-19 11:18：用户再次授权精度换速度，同输入 self 对照完成

- 用户明确超长序列可降低精度提高速度。已将要求补入定点修复规范：不能用
  几乎逐条保留全部重复命中作唯一门槛，也不能每条另跑完整慢基线。触发仍由
  内部自动判定；保留原始参考比对、旧版基线与真实参数来源。
- 下游核对：`q0_preparation._initial_inputs` 将有 aligned block 的关系纳入
  known_pairs；`q0_admission` 对 base_alignments 的所有合法 PAF 行建 PairLink，
  并未按 tp:P 排除 secondary。因此不能把所有次级命中都称为无用。
- 新增隔离 `self_context_control.py`，复用已完成三个 1 Mb masked native
  结果、原 masked FASTA、索引、名称/长度和所有原生 flags；只变 -f，
  每次 mapper 上限 300 秒。没有重复 native，也没有修改两个主工作区。
- `self-context-control-20261119/`：
  - **42767386 SUCCEEDED**，11:14:35–11:15:14，f0.005 mapper 9.281 s。
  - **42767387 SUCCEEDED**，11:14:37–11:16:13，f0.001 mapper 78.602 s。
  - 两个作业均 agent-X86-61，1 CPU / 10240 MiB，54 项远端测试通过；
    每个输出目录保留 control.json、全部 PAF/日志及 final-job.json。
  - 本地事故工具 **135 项通过**。完整 native 局部基线此前为 152.966 s；
    这是不同作业的单次观察，不是整流程加速或控制硬件波动后的基准。
- 同一 masked 输入、100 bp 容差、1 kb 采样，native 全命中 40533 个位置：
  - f0.005 支持 1754，缺失 38779；长且高相似度分层支持 241/728，
    配对覆盖缺失 278317/490574。该激进参数不只是删除零碎重复命中，不采纳。
  - f0.001 支持 22963，缺失 17570；长且高相似度分层支持 **677/728**，
    配对覆盖缺失 **11322/490574（约 2.3%）**，新增采样位置 22。
    这是较温和的接入候选，不等于已在主流程启用，也不是生物学错误率。
  - 长且高相似度分层定义为 PAF block>=10 kb、matches/block>=95%，
    是诊断分类，不是正确性或下游必需性的证明。报告保留 all_hits 和字面
    tp:P 两组，不能隐去后者仍明显变化的事实。
- f0.005 的 masked 结果与已有完整 f0.005 候选在同窗口内：1770 个采样
  位置均一致、配对覆盖无损失。至此该实验里 seed 过滤效应已被同输入对照
  单独观察到；仍不能把局部缺失率外推为完整序列丢失率。
- 下一步以 f0.001 为候选研究超长 self 自动快路径；不要再机械套用 cross
  的 .2% 全命中保留门槛。正式采用须有真实 whole-record 执行与 profile
  身份，涵盖 batch/merge/外层检查点/下游 reader/打包报告；不得把候选伪装
  成原生命令的 complete.json。普通批次和已成功结果不必全部重算。
- 主作业仍为旧 42523432、新 42710779；本轮无取消、重提或参数热修改。
  监控仍使用会话 51160，重用而不是重启。


## 2026-11-19 11:25：完整温和 self 候选已运行，接入约束已核对

- **42767640 RUNNING**，11:21:49 在 **agent-X86-61** 启动，隔离目录
  `self-full-3D-moderate-20261119/`。申请 4 CPU / 40960 MiB 为内存留余量，
  实际 mapper 仍 1 线程；固定原 minimap2 2.31-r1302，避免架构/版本混杂。
- `full_self_moderate_candidate.py` 对原完整 289508469 bp 查询、原缓存索引
  仅增加 `-f 0.001`；不重跑 native、不修改原输入、不写原 complete.json。
  实际 stderr 已加载 113 条 target、mid_occ=232（原参数 500），正在计算。
  mapper 上限 5400 秒；超时仅 kill/wait 自己的子进程，不能当成完整结果。
- 输出将为 `candidate/candidate.json`，成功状态必须是
  `moderate_candidate_complete_not_adopted`。它与旧 f0.005 的 `pilot.json`
  是不同协议，不能直接交给原 inspector 或伪装成 native 成功标记。
  全遍历日志、PAF/CIGAR、恢复原名、原输入和所有输出 SHA 均需要验证。
- 远端 **40 项测试通过**；本地事故工具 **139 项通过**。旧 f0.005 driver、
  冻结 comparator/inspector 及两个主任务均未更换。本轮没有发布 CI。
- 只读任务清点：>=100 Mb 的 21 个单记录批次分布在 **13 个 self operation**，
  都属于 JM19_hifiasm，检查时这些批次均无 native 完成标记。该结论只是
  计划/标记清点；最终接入前必须重新检查，不能覆盖后来已经完成的 native。
- **接入边界（已核对代码，尚未实现/部署）**：
  1. 原 q0 外层输入身份包含 self manifest 和 batch command，不能在运行中直接编辑。
     assignment 本身绑定 q0 task 清单、顶层 command、FASTA/名称映射等，但实际
     assign.before.json 输出清单不含 self_batch_manifest.json 或 batches/ 文件。
     应使用隔离执行 profile/manifest，明确绑定新 batch key 和实际参数，保留
     原文件和所有成功跨组装叶子。当前 cross routing plan 的冻结依赖也不能热改。
  2. 原 helper 的每个 batch 会尝试 native manifest 合并；新 profile key 不匹配
     时它会返回未合并。故不能只替换长 batch mapper：须在受控 controller 的
     self 完成回调中、原回调提交染色体检查点前，调用 profile-aware merge。
     最后完成的可能是普通 native batch，因此回调须覆盖该 operation 的所有批次。
  3. 外层 q0 commit 会重建字面 OuterCheckpointManager 复核身份；profile
     适配须与已有 cross binding 组合，保留收尾复核，绑定合并回执/输出。
     后续独立 q0 evidence reader 和最终可移植 provenance 也须理解相同 profile。
  4. 现有 MemoryBoundedDispatcher 将隔离目录里的新 command 视为 unknown，
     因而独占。若调整并发，必须把执行覆盖映射回真实 self 配置并依据新候选实测
     峰值单独放宽；不能为了 self 把 cross/unknown 的 OOM 保护一并去掉。
- 后续优先检查 42767640 与当前 native batch 的真正完成状态；候选可供后续
  profile 下复用，不是为了“证明速度”再启动一条完整 native。只读主监控仍为
  会话 51160，约 12:27 到时结束；监控结束不代表科学作业结束。


## 2026-11-19 11:42：self profile 执行/复用/合并层验证完成，尚未接入主任务

- 新增 `self_seed_profile.py` 与定向测试，原 runtime/helper/manifest/command
  均未修改。>=100 Mb 单条查询显式 f0.001，profile JSON、原 manifest、代码/
  helper/contract 依赖都受 SHA 绑定；新 batch key 不冒用 native key。
- 支持复用已完成的 moderate `candidate.json`：核实完整输入/索引/实际命令、
  成功状态和全部输出后复制，**不重跑 mapper、不重复恢复名称**。候选来源
  回执也绑定 profile，修改来源/参数/索引证明/结果或失败退出均不能命中缓存。
- 不覆盖已有 native/未知 complete.json；若原任务在切换前已经完成，应刷新
  选择计划保留它。原 manifest/普通批次 key 保持原样。
- 已验证混合 native/profile 的按原顺序合并，包括**普通 native 批次最后完成**。
  原 native merger 会拒绝 profile key，故控制器必须在原 finish 回调提交外层
  检查点之前处理 profile-aware merge。不能只换 batch mapper。
- 本地全部事故工具 **153 项通过**。远端真实冻结 helper/contract 的合成微型
  回归：**42768267 SUCCEEDED**，11:40:38–11:40:40，agent-X86-13，
  **24 项通过**；目录 `self-profile-runtime-validation-v2-20261119/`，有
  SHA 清单、日志、final-job.json。旧 v1 作业 42768225 也成功，保留不覆盖。
  这验证执行协议，不是完整科学数据、整个 q0 或工作流验收。
- 最终 runtime SHA：
  `7f9edd0b236787e4a1aeea687ad0147020516de63972fdc78edaf2f9f0500eb8`。
- **仍未完成，不得部署/取消主任务**：自动 profile 计划生成、控制器覆盖与
  完成回调、cross/self 外层检查点组合、独立 q0 evidence reader、可移植 audit。
  控制器还应以完整 self operation 为单位复用已完成组，避免续跑时每个缓存
  batch 都再次完整合并/校验同一组；不能通过放弃结果内容校验省时间。
- **42767640** 完整 f0.001 候选在 11:41 仍 RUNNING；11:37 左右采样约
  0.93 核、13070 MiB 内存，未完成。不能称为已采用或承诺整条查询的加速倍率。
  两个主任务及当前只读监控 51160 均保持不动。


## 2026-11-19 12:03：self 调度回调与外层检查点适配已测，入口/reader 尚待接好

- 新增 `self_profile_bindings.py` / 定向测试：替换明确选中的 batch command，
  回调保持原任务身份；完整缓存先核验原 query/target/tool 与输出，再复用，
  不启动 native helper 重读派生索引。每组仅在最后成功回调前合并一次，覆盖
  native 最后完成、profile 最后完成、部分/全部缓存、失败和取消。
- 外层适配保留已有 cross-bound input/output，提交前通过原 base class
  重新构造输入再补 self binding；不跳过 q0 最终输入复核。输出附带 profile
  receipt、batch marker 和合并 marker 的内容身份。
- native-only group 可用空 selection：普通 key 和原 native merge marker
  身份都保留，已有合法合并 PAF 不重拷贝。后续计划生成应覆盖全部计划内 self
  operation（本数据 44 个），而不仅是含超长查询的 13 个，避免普通批次续跑
  仍重复扫描。正式改变参数的仍只是自动选出的超长批次。
- 避免新的扫描放大：完整原 batch command 清单在初始化/准备/最终复核检查，
  不在每次 finish 回调遍历全部 1342 项；回调只查受影响组。Profile 的常规
  digest 验证复用现有进程级内容摘要缓存；实测 frozen contract 的缓存签名含
  inode/size/mtime/ctime，缓存只来自真实完整读取。新增同大小、恢复 mtime
  的篡改回归仍被拒绝。新入口/reader 应使用足够的有界缓存容量，不能持久预灌 SHA。
- **更正早先绑定描述**：实际 `assign.before.json` 输出中没有
  self_batch_manifest.json 或 batches/ 文件；它有 44 个 self_name_map 和
  22 个 q0 task 清单等。self manifest/batch command 由 q0 外层输入绑定。
  本轮已更正前文，不改变“不得中途热改原输入”的结论。
- 本地 **165 项通过**；远端 **42768711 SUCCEEDED**，11:57:53–11:57:57，
  agent-X86-65，**36 项通过**，使用真实冻结 helper/contract 的微型测试。
  目录 `self-profile-bindings-validation-20261119/` 保留 code.sha256、日志、
  final-job.json。外层测试覆盖组合协议和 fresh-input guard，但不是完整客户
  q0 科学验收，也不等于新的 resume 入口和 reader 已在远端运行。
- 此快照 SHA：self runtime
  `a820280b32493d93fcceb61e2c45f2c450310cfc039d2f2c7275d1ce112b5b8f`；
  self bindings
  `a6386451fe9fb6729bcb62a985c4e1e77379ba5388445941195bcb54e6440c5a`。
- **下一步真正缺项**：自动计划生成、持锁 resume 入口、cross/self 联合独立
  q0 evidence reader、可移植 provenance；再验证完整 moderate 候选并选择安全
  切换点。不要重写冻结 cross plan/dependencies，不要重新跑完整 native 基线。
- 42767640 于 11:56/后续查询仍 RUNNING，未宣告成功；主作业 42523432、
  42710779 和监控 51160 均未停止。监控约 12:27 到时，届时先查原 handle
  再延长观察，不重提科学作业。


## 2026-11-19 13:10：完整激进结果分层评估、中间档试验与 OOM 边界

- 主作业仍为旧 **42523432**（Step 2，约 15 核、86 GiB）和新 **42710779**。
  新版 3D hifiasm batch-00003 于 **12:28:11** 完成，mapper **15126.361 秒**、
  Peak RSS **21.646 GB**；当前是 4A batch-00001（220255611 bp），12:28:11 开始，
  13:09 仍约 1 核、30125 MiB。未修改/取消两个主任务，长任务独占仍有效。
- >=100 Mb 单条 self 批次共 21：1 完成、1 运行、19 尚未开始。这个计数不含更短
  self 批次；“3–4 天”只是按已完成最慢样本估算的安排余量，不是全流程 ETA。
- 完整 f=.001 候选 **42767640 FAILED**，11:21:49–12:52:07；返回码124，mapper
  5400.187 秒，命中独立试验的 90 分钟上限，没有成功输出可采用；不是主任务失败。
  保留 `self-full-3D-moderate-20261119/candidate/candidate.json` 和 final-job.json。
- 已完成 f=.005 候选 444.913 秒；与原 native 单次 mapper 比约34倍，但为不同
  x86 节点且非端到端提速。原全位置比较 **42786027 SUCCEEDED**（12:36:59–12:39:50），
  目录 `self-native-comparison-20261119/`；没有重跑 native。100bp 容差下缺失
  原始抽样位置93.0954%，该指标不是生物学错误率。
- 新的**只读完整 PAF 分层审计 42800465 SUCCEEDED**（13:03:08–13:03:36，
  agent-X86-14，4CPU/40GiB），目录 `self-fast-evidence-audit-20261119/`，结果
  `results/audit.json`。使用远端实际 q0 PathPolicy.minimum_pair_identity=.95：
  - 必要 identity 过滤后 native140711行、fast8658行；缺失抽样位置89.856%，
    成对 query coverage missing230015952 / baseline282441454 bp。
  - >=10kb 且 identity>=.95 的诊断层：native8092行、fast3378行；缺失位置57.753%，
    成对 query coverage missing26944225 / baseline62132537 bp（约43.36%）。
  - identity 层有8355个抽样的同 contig-pair/query 坐标从多个映射变为单个；其中8116
    是原候选之一。这不是 q0 已实际误判的证明，但不能将删掉竞争位置称为无损去重复。
  - 未运行完整 q0 admission：未评估参考定位、序列复杂度、目标侧唯一性和所有100bp
    冲突重叠。诊断保留 secondary/MAPQ0，不以 primary 标签冒充正确性。
- 中间档 f=.002 同输入局部试验 **42801481 SUCCEEDED**（13:05:41–13:06:31，
  agent-X86-14，1CPU/10GiB），`self-middle-control-20261119/f0002/control.json`。
  复用原153秒的3x1Mb masked native，不重跑原基线；新 mapper39.602秒，约3.86倍。
  长高相似度层 missing51668 / baseline490574 bp（10.53%），位置缺失12.5%；
  全位置层缺失71.84%。只能称局部折中，不能外推完整查询或 q0 最终结果。
- 已提交且 **13:08:47 RUNNING 的完整 f=.002 候选 42802491**，agent-X86-14，
  4CPU/40GiB（实际 mapper1线程），目录 `self-full-3D-middle-20261119/`。
  只运行新参数候选，不重跑原始完整比对，不写主工作区。独立上限5400秒；
  成功后需与现成 native 完整结果比较，不得把局部3.86倍/10.53%当完整结论。
  f=.002 目前不被固定 f=.001 execution profile 接纳，不能混用已有计划/成功key。
- 新的 context/resume/reader/stager 六文件已有初步集成验证：**42784275 SUCCEEDED**，
  12:33:13–12:34:22，**69项通过**，真实冻结工具与实际客户元数据 preview验证成功。
  `self-profile-preview-20261119/` 覆盖44self组、20近似批次、0候选复用，
  `preview_only=true`。**只是隔离预览，不是已部署。** installed q0 launcher 仍是原
  cross-only reader，self 快速参数未进入主任务；联合可移植 audit 和安全切换仍待完成。
- 用户再次提醒历史 OOM：11月18日160GiB溢出，以及11月19日01:25两个 cross
  长比对顶满240GiB。不得因当前低RSS恢复长任务并发。已收紧未部署的 admission/stager：
  即使候选峰值低，fast long也独占，max_fast=1；仅保留已有native-small双进程能力。
  初版预览/验证目录保持冻结，不用其早先允许4fast的代码替换主任务；新代码需新验证目录。
- 旧监控59089在12:52捕获候选终态并正常结束。当前两主任务只读监控 **62156**，
  日志 `logs/wheat-live-20261119-130124.jsonl`，30秒采样、约14:31到时。
  它不跟踪新候选42802491，需单独查询/监控该明确job；监控到时不是主作业失败。
- 所有目录相对于 `jm19-compare-614589f-20261118/`，除 logs/wheat-live 在公共debug根。
  上述终态诊断已各自保存 final-job.json；未运行 update.sh、发布CI、全量重装或 reprepare。

### 13:14 验证补记

- 收紧 long/fast 独占后的本地事故工具 **192项通过**，日志
  `/tmp/wheat-fast-audit-all-tests.log`。包括新 full-evidence 分层/歧义诊断、f=.002
  参数隔离，以及“低峰值不能自动开启长任务并发”的回归。
- **42803719 SUCCEEDED**，13:12:05–13:12:36，agent-X86-40，**70项通过**。
  新冻结目录 `self-profile-integration-exclusive-20261119/`，final-job.json已保存。
  实际工作区元数据 preview 为 `self-profile-preview-exclusive-20261119/`，44组、
  20近似候选、0复用；plan SHA
  `f8fe00fb5b3888005046354043a6f99222cc1bbf0ea40a3268973d087b477d01`。
  entry/reader仅validate-only成功，仍未安装launcher/运行q0/接入主任务。
- f=.002完整候选42802491继续 RUNNING；新增独立只读监控会话 **90604**，
  `/tmp/cgat-wheat-middle-candidate-monitor.py`，30秒采样，终态才结束并保存final-job.json。
  主任务监控62156继续，不因候选失败或监控超时重提主任务。


## 2026-11-19 13:38：按用户进一步放宽 self 精度，已受控切换到 f0.005 入口

- 用户最新明确授权：同一 de novo 内部比对用途低于组装间比对，可进一步放开
  精度下降限制。因此 f0.002 试验不再阻塞 f0.005 self 接入；不是将整个工作流
  或 reference/cross 一并放宽。已完成3D native继续保留，默认触发仍为单条>=100Mb。
- 补充规模/内存实测：13:17新版旧进程30134 MiB/327680 MiB（约29.4/320 GiB），
  3D完成峰值21.646GB；剩余20条超长 query最大263669096bp、target集合最大764542142bp。
  可独立评估self两路，但现阶段只切换参数，不同时解除长任务独占。
- runtime支持显式f0.001/f0.005身份，生产mapper不继承试验5400秒上限。f0.005 final
  staging绑定已完成候选和完整损失审计；不存在伪装native key或采用失败临时输出。
  新增持正常工作区锁安装reader，保留launcher备份/hash回执，已发布q0证据/旧声明
  存在则拒绝隐式迁移。增加portable cross/self companion exporter，输出逐query真实
  参数/输入输出hash/执行key，不泄露私有绝对路径；最终交付必须附带，尚未生成。
- 本地全事故工具 **206项通过**（`/tmp/wheat-aggressive-all-tests.log`）。远端真实
  冻结工具验证 **42811986 SUCCEEDED**，13:30:44–13:31:06，agent-X86-07，
  **88项通过**。源码冻结在 `self-aggressive-runtime-20261119/`；preview成功覆盖
  44组/20近似批次/0候选复用，entry和reader只读加载均通过。
- 替代主任务 **42813048 RUNNING**，13:33:32，agent-X86-36，申请32CPU/320GiB，
  actual mapper并发：long/fast/cross/unknown独占，仅native-small最多2进程。
  `self-aggressive-resume-20261119/resume.dsub`先检查代码SHA并等待明确handoff，
  ready.json确认分配到资源后，才停止原新版 **42710779**。后者FAILED是明确dkill
  的预期终态，不是新bug；正常`.run_all/lock`已释放，未偷锁、未删数据。
  旧对照 **42523432**保持运行，不停止、不修改。
- cutover-before.json、stopped-job.json、handoff.json保存在上述resume目录。final plan
  由新计算节点在旧作业停止后生成，避免误覆盖切换前新完成的native batch。
  final目录 `self-aggressive-plan-20261119/`，SHA
  `9cd695dfb4fdcae362483843239d07f80a088b08c7c2a747ac6c2c110817635d`，44组/20选中/0复用。
- 新entry已经打印EXPLICIT_SELF_PROFILE_RESUME，实际run_id
  `20261119T053543Z-3535567-b85fd419`。13:37:12进入Runner RESUME/PREFLIGHT，
  effective threads16（原resource历史保留）。**此记录时尚未核实第一条f0.005
  mapper真正开始/完成，后续必须补证，不能仅凭提交或入口日志宣称提速已兑现。**
- 主日志 `logs/resume_self_aggressive_42813048.out`。旧监控62156在13:35按旧新版
  停止终态正常结束；需要切换主监控到42813048，并识别profile-attempt-*。
  f0.002候选42802491和其监控90604仍独立，未改变它的运行文件。
- 一次SSH banner超时后同别名重试成功；未修改路由、认证、proxy或关闭共享master。
- 所有上文目录相对于 `jm19-compare-614589f-20261118/`。当前生产reader launcher
  的备份/安装凭据位于final plan的`reader-installation/`。最终q0完成后在计算节点用
  同冻结runtime的self_profile_audit.py导出companion，与已有cross审计一起保留交付。

### 13:41 安装与参考复用补证

- Reader安装回执已存在，old SHA
  `21a9dbb0bfad11fdf52a583ad0babb94a8688d256883a25ee52dab6d66f72ff2`，
  installed SHA `f7a34cdfdd0693ee0a00705c3cd3b1dbe8068ef98f99981cc3403bc132775632`。
  13:38:12 hifiasm ref、13:39:47 flye ref 均 **SKIP_VALID**，不是重新比对。
- 主监控已切换为 **64397**，本地脚本`/tmp/cgat-wheat-live-monitor-aggressive.py`，
  监控42523432/42813048，识别native attempt和profile-attempt。后续先核实新 mapper
  命令、SELF_BATCH_REUSED/SELF_PROFILE_COMMITTED，再称为实际参数提速。
- 若已经有profile批次提交，不能恢复旧cross-only reader/旧入口冒充native续跑。
  应使用同一冻结final plan恢复；改变执行参数/策略需显式迁移，保留所有既有产出。

### 13:47：已确认主任务真实执行 f0.005，不再只是预览或提交

- 新版42813048于 **13:45:45** 开始4A hifiasm batch-00001。实际
  `profile-attempt-sukunpr0/command.json`包含`-c -x asm10 -X --no-hash-name -m200 -n100 -t1 -f0.005`，
  query仍为原完整220255611bp文件，index仍为原731737596bp目标集合；mapper stderr
  mid_occ从原500变为58。已确认真实运行，不是仅看wrapper参数。
- **21条CROSS_LEAF_REUSED + 2条SELF_BATCH_REUSED**（3D hifiasm batch3、4D flye batch29），
  参考两组与assign也均SKIP_VALID，未重跑已完成比对。当前4A原生未完成尝试保持留存，
  新输出使用独立profile-attempt；未把旧空临时PAF作为结果。
- 13:46:42新作业约1核、5053MiB，尚非峰值，也尚未有第一条fast批次完成；不能用此
  早期RSS自动放开并发或宣布完整加速倍数。旧42523432仍Step2、约15核，无本轮修改。
- 主监控64397日志 `~/cgat-reads-debug/logs/wheat-live-20261119-134040.jsonl`，约15:10到时。
- 本轮实现已提交推送master **d80213c** `[skip ci]`。独立UI工作树改动未暂存/提交。
  后续优先检查4A `SELF_PROFILE_COMMITTED`与新完整产出，及下一条自动路由，然后考虑
  在同类实测基础上的两路准入；不能只因为峰值低而改 frozen plan/代码。

## 2026-11-19 14:04：首个主任务激进批次完成，下一条自动接续

- **4A hifiasm batch-00001于13:59:39成功完成**，自13:45:45开始共约13分54秒。
  mapper回执wall_seconds=820.483，minimap日志Real time820.313秒、CPU815.591秒，
  **Peak RSS 5.738 GB**。raw.paf12527275字节、restored result.paf11806087字节；
  成功receipt与complete.json的key/output hashes一致，正式writer完成了内容/CIGAR验证。
- 实际参数f0.005、query220255611bp、target731737596bp。旧native尝试只跑到约66分钟
  就因受控切换停止，**没有完整native耗时，不能给这条宣称精确加速倍率**。
- 新版42813048已于13:59:39自动启动 **1A hifiasm batch-00000，263669096bp**，
  实际profile-attempt command同为f0.005。全体>=100Mb原21条，现在native3D+fast4A共2条
  完成，剩19条未完成（包括当前1A）。这不是4A整组或q0阶段已经完成。
- 新只读进程采样 **42821390 SUCCEEDED**，13:53:02–13:54:04，固定agent-X86-36，
  1CPU/1GiB。`self-memory-sample-20261119/samples.jsonl`含7次当前用户/目标workspace
  minimap2采样，PID3542222：VmRSS/VmHWM约6009536–6010636kB，VmSize/VmPeak
  7117596–7117696kB，Swap0、Threads2。采样不改运行进程；final-job.json已保存。
  这些是约5.73GiB RSS /6.79GiB虚拟空间，支持进一步评估“两路+明确资源保护”，
  不是无上限放开并发的依据。目前max_fast仍1，未部署资源限额wrapper或两路调度。
- 检查了reader/任务组范围：plan与self计划均含22个q0_chr、44个self operation。
  q0_chr:Un当前pending是尚未开始其首个leaf，不是漏出计划；其他21个unit因缓存leaf
  回调已标running，并不代表21个mapper并行。Un两组均无近似selection，原生处理不变。
- f0.002完整候选42802491仍独立运行（90分钟上限约14:39）；不阻塞主任务。
  已将匹配冻结driver的完整比较+身份分层工具准备到`self-middle-inspection-20261119/`，
  code.sha256校验通过，**inspect.dsub未提交**；仅在candidate.json真实完整成功后提交，
  失败/超时则不比较临时PAF。它不重跑native mapper。
- 旧对照42523432仍Step2的4D MUMmer分块，14:00有新的SUCCESS/START；单个分块编号
  不是整体完成百分比。两主监控64397与候选监控90604继续，未重提其他科学作业。


## 2026-11-19 14:46：两路资源overlay已受控切换，保留原科学profile

- 单路f0.005继续成功：1A batch0于14:15:29结束，mapper913.671秒、PeakRSS5.909GB；
  7D batch0于14:26:06结束，PeakRSS5.366GB；4D batch0于**14:42:31**成功结束。
  现在>=100Mb原21条已有native3D+4个fast共5条完成，剩16条；未包含更短self批次。
- 增加独立资源层：`self_memory_guard.py`执行前核实原script SHA/打开inode，设置
  每进程64GiB RLIMIT_AS与CORE0，exec原脚本，子进程继承；不是聚合RSS/cgroup限制。
  `self_two_lane_admission.py`最多两路f0.005、query<=300Mb/target<=800Mb，
  每路预留128GiB，不混fast/native。原native-small的1Gb target边界保持，
  cross/unknown/oversized仍独占。当前job继续32CPU/320GiB，计算预算16。
- `stage_self_resource_resume.py`保持原profile文件/科学参数/原command/所有batch key
  和cross依赖，仅生成新guard脚本及资源元数据。至少两条已完整成功f0.005、输出hash与
  stderr峰值通过核验后才可生成；本次有1A/4A/7D三条。`resume_self_resources.py`明确
  验证新资源模块、选择该模块后执行原冻结entry，不修改原冻结源码。
- 本地全事故工具**222项通过**；随后补了保留native1Gb边界的定向回归（该组5项通过）。
  远端v1 **42828493 SUCCEEDED**（14:28:14–14:28:28）留存不改。v2
  **42828665 SUCCEEDED**（14:32:47–14:32:54，agent-X86-20），**17项通过**，
  加真实minimap2合成检验：两进程guard64GiB输出与非guard非空PAF字节一致；故意
  16MiB限制子例返回-6，stderr`[morecore] insufficient memory`，是预期失败而非主任务OOM。
- 实际冻结runtime为 `self-two-lane-runtime-v2-20261119/`；v1没有部署。
  最终资源plan为 `self-two-lane-plan-v2-20261119/self-plan.json`，SHA
  `348ba78a956e9416e1cbc6c30d0ce962091b08d69bebf81fef0a89ba1b09114d`。
  它复用origin `self-aggressive-plan-20261119/self-plan.json`（9cd695df...），
  保留44self组/20选中script的原科学profile；20是配置数，含已完成缓存，不是要重跑20条。
- 新主任务 **42828863 RUNNING**，14:37:17，**agent-X86-40**，先在
  `self-two-lane-resume-20261119/`等待handoff。明确等4D TASK_END exit0后才于14:42:34
  请求停止单路新版42813048；正常锁释放、旧job终态后放行。仅下一条3A刚启动约数秒
  的未完成工作被中止，4D及此前所有已完成产出保存。旧42523432不修改、不取消。
- 新entry已打印RESOURCE_ONLY_SELF_RESUME / EXPLICIT_SELF_PROFILE_RESUME，
  run_id **20261119T064255Z-773649-4017a74e**；14:44:13进入RESUME/PREFLIGHT。
  **本记录时尚未确认两个实际mapper同时开始，不能只凭max_fast=2声称两路提速已兑现。**
  新主日志 `logs/resume_self_two_lane_42828863.out`。
- 旧主监控64397在单路新版预期终止后结束；新主监控 **45573**，脚本
  `/tmp/cgat-wheat-live-monitor-two-lane.py`，跟踪42523432/42828863。观察两个actual
  TASK_START、SELF_RESOURCE_GUARD和子mapper实际limits，再记录真实并发/内存。
- 资源overlay只约束新启动的任务，不把此前缓存结果标记为曾受guard。若需回退并发，
  不可直接运行原run_all或删profile；保留科学profile和结果，在q0证据未发布的前提下
  走明确的资源/launcher回退或新overlay。guard失败也不得使用临时PAF。

### 中间档完整试验已结束，不阻塞当前激进路线

- **42802491 SUCCEEDED**，13:08:47–14:17:56；完整f0.002 mapper **4128.961秒**
  （约68分49秒）。没有重跑完整native基线。独立比较/分层 **42828539 SUCCEEDED**，
  14:31:02–14:33:30，目录 `self-middle-inspection-20261119/`。
- 完整>=10kb且identity>=95%诊断层：missing pair-query coverage1714819 /
  baseline62132537bp（约2.76%），抽样位置缺失2.52%；这是此层与native一致性，
  **不是整体精度只下降2.8%**。仅identity>=95%的全长短混合层仍缺失156972139 /
  282441454bp成对query覆盖、抽样位置缺失67.98%。完整结果与局部样本并不完全一致。
- f0.002比f0.005保留更多长高相似度证据，但本条耗时约69分钟对比f0.005约7分25秒。
  按用户已进一步放宽内部self精度的授权，主任务继续f0.005；中间结果留作可追溯对照，
  不以此回退/重跑已完成主任务。监控90604已因该候选成功自然结束，后续无需再等待它。


### 2026-11-19 14:59：两路实际生效与下游补比对边界

- 主任务42828863于**14:52:29**同时启动3A hifiasm batch2和1A hifiasm batch2，
  两条均打印SELF_RESOURCE_GUARD。启动时成功复用21cross+6self共27个leaf。
  1A batch2于**14:55:05**成功提交，mapper148.002秒（约2分28秒），随后接上5A batch0。
  >=100Mb原21条此时完成6条、剩15条；这是长self子批次计数，不是染色体或全流程完成度。
- 同节点只读采样作业**42829367**，目录`self-two-lane-memory-sample-20261119/`。
  14:58:48采到3A PID783206和5A PID784763的实际minimap2命令，均有`-f 0.005`；
  两者/proc/limits均为AS soft=hard=68719476736bytes，确认子mapper实际继承保护。
  当时VmRSS分别5392388/5193868kB（约5.14/4.95GiB），VmSize6465784/6012684kB，Swap0。
  这只是采样瞬间，不能推出后续所有任务峰值或整棵进程树均受64GiB聚合限制。
- 新launcher安装收据确认SHA
  `55e231f1c4880226766f99c87c275a25091f6863d7dfc0cb3a3c48946a4226d8`，
  prior仍为f7a34cdf...，plan仍为348ba78a...；不是改写旧冻结reader。
- 当前最终代码本地完整事故工具回归**223项通过，137.433秒**，
  日志`/tmp/wheat-two-lane-final-tests.log`。未运行发布CI，未update.sh或重装。
- 下游审计：远端冻结q0_preparation.py与q0_catalog.py和当前仓库SHA相同。
  `_initial_inputs`的known_pairs记录有实际aligned_blocks的source对，不是所有已计划对。
  `supplemental_groups`有意针对参考重叠/相邻但无命中、split source、跨组来源补证据；
  因此激进过滤后的缺失可能增加后续补比对，不能声称整个q0都已套用快速档或绝不补跑。
  不把所有已计划对冒充为已有命中来粗暴取消该环节。后续若此处成为瓶颈，应先检查
  实际request/query/target范围和可复用证据，再明确拆分内部self与cross策略；当前仅观察，
  没有修改科学builder或正在运行的冻结代码。两路AS保护也没有自动覆盖这些补比对。
- 旧对照42523432仍RUNNING/grt_step2，未修改或取消。32核新作业当前约使用2核：
  当前保守资源额为并发试行/后续阶段预留，不以该阶段低CPU作为失败；不为缩额立即重启。


### 2026-11-19 15:25：继续运行，队首阻塞修复仅保存仓库

- 两主任务仍RUNNING。新版两路在14:52:29后持续推进；截至15:24:39已有36个leaf
  TASK_END成功（含21个复用cross），当前6D hifiasm batch1和1D hifiasm batch4。
  当前主进程资源快照CPU约198%、RSS4342MiB、历史峰值10654MiB；不是后续峰值保证。
- 只读清点1342个self批次：原21个>=100Mb单record；另有1321个<100Mb，
  其中已完成4D flye batch29。其余1320个按最大query分层为：<1Mb 96、1–10Mb 484、
  10–50Mb 679、50–100Mb 61，总query约26.84Gb。它们尚未自动变成f0.005。
  已完成20Mb flye批次native只耗4.335秒，但其PAF为空且query排序靠后，不能代表
  所有短batch。先看实际执行，不从单条快例外推出尾部必快，也不为猜测立即改阈值重启。
- 旧版当前run只读去重：15:17时1D为2402个distinct SUCCESS；4D为805个SUCCESS，
  另16个已START未完成，无重复START的partition ID。日志编号大小不是进度计数：
  repair_mummer.MummerExecution.indices按分区大小安排，后面出现较小编号不是重跑。
- 定向回归复现资源dispatcher队首阻塞：active fast + 较大pending native + 可用pending
  fast时原来返回空，反方向同样存在。仓库现改为先从active pool筛选可运行项，不混池、
  不增加并发/内存上限、不改变无active时的原优先级。新测试先失败后修复通过，admission
  6项及resource overlay 8项通过。**这项改动尚未部署远端，当前仍冻结v2。**
  下一次确有必要资源切换时，从原单路scientific origin plan生成新隔离overlay，保留所有
  原科学profile/key；不要修改v2文件或仅为这个短暂等待重提，避免又付出完整续跑校验。
- 监控45573仍活跃，远端日志`logs/wheat-live-20261119-144627.jsonl`；有限90分钟监控
  到期不等于任务退出。现场持续看实际TASK_START/END，不把21个running外层unit当并发数。


## 2026-11-19 16:53：sub100内部self扩展已切换，等待实际续跑验证

- 用户再次确认内部self可进一步放宽精度，并要求意外对话中断后继续。远端主任务没有
  因对话中断停止。新版42828863自15:32:34并行跑7A hifiasm batch0（99097964bp）和
  2A hifiasm batch4（86825214bp），到切换前仍未完成。两者旧未完成attempt保留。
- 隔离同节点候选**42854191 SUCCEEDED**，agent-X86-40，16:20:14–16:25:57。
  `self-sub100-pilot-20261119/candidate/pilot.json` SHA
  `1e4846102fea15f440fd1b42bf0c4f0c9065bb098432d3de192d49e69dab6e6b`；
  7A 99Mb整条query、同索引、仅新增f0.005，mapper334.302秒、PeakRSS3.835GB。
  仍无完整native对照结果，不能给出精确全程倍数或99Mb精度损失率。候选30分钟试验上限
  没有带入生产映射；candidate在工作区外，没有原生成功标记，准备核验后采纳免重跑。
- 实现新增extended/composite profile：原profile、已完成primary结果/key/script不变；
  只扩展未完成的>=10Mb单record内部self。总共新增**444批次**，加原20个配置共464个
  approximate配置（含已有成功缓存，不是全部待跑）。排除两个已完成native批次，
  多record与较短批次仍native。初始参考/cross/旧对照均不变；两路/64GiB AS/320GiB不变。
- 冻结runtime：`self-extension-runtime-20261119/`，68个Python文件归档SHA
  `0842c4aa119f3be24c29f7bdada8b47b2320401786b9f95790a7de07ba4248de`。
  **42869397 FAILED**是首次远端测试布局问题：cross fixture假设`../../../server/tools`，
  并非主任务失败。没有改冻结代码，新增隔离测试适配器绑定真实tools路径。
  **42874082 SUCCEEDED**，16:46:47–16:47:28，agent-X86-40：237项通过，
  实际stage/原controller validate-only/combined reader validate-only均通过。
  日志`self-extension-validation-20261119/`；本地最终239项通过（187.991秒），多出的两项
  是portable audit按真实owner区分旧/新policy并拒绝损坏receipt，日志
  `/tmp/wheat-extension-final-tests.log`。没有发布CI、重装或update.sh。
- 实际新plan：`self-extension-plan-20261119/self-plan.json`，SHA
  `d9058d48a750a7230adaf125eda29677ccb241b08db62d67284ba829bd5b4434`。
  parent是two-lane-v2 plan348ba78a...。未来最终companion必须调用本runtime里的
  **self_extension_audit.py**及这个active plan；旧self_profile_audit直接入口不支持该factory。
- 新主任务 **42876793 RUNNING**，**agent-X86-29**，32CPU/327680MiB，16:49:35分配资源，
  16:49:55完成validate-only并等待handoff。16:52:26确认旧新版42828863终态、正常锁释放
  后放行。旧42523432完全不动。停止42828863是有意切换低效步骤，不是算法失败。
  交接证据`self-extension-resume-20261119/{ready,cutover-before,stop-command,stopped-job,handoff}.json`。
- 新entry已进入EXPLICIT_SELF_PROFILE_RESUME，run_id **20261119T085235Z-94158-ebf2d842**；
  新reader安装收据SHA **33fc5bea2c85b08ae1705ba4054aa0ab91ac13932c65c7b30c8618c369cf0166**，
  prior为55e231f...；备份/receipt在新plan的`reader-installation/`。此记录时尚未实际启动
  新mapper，不能凭入口日志宣称扩展提速已经兑现。主日志`logs/resume_self_extension_42876793.out`。
- 新监控会话 **22444**，脚本`/tmp/cgat-wheat-live-monitor-extension.py`，观察42523432/42876793。
  原监控86968曾因SSH255中断，已检查远端没有对应监控进程、日志停止；这不代表主作业停止。
  其后41219观察旧新版，交接后应自然终止。持续核实候选实际adoption、原40个leaf复用与
  新extension命令/receipt/内存，不要只看外层running unit数。


### 2026-11-19 17:09：扩展已实际执行，99Mb候选未重跑

- 新主任务42876793已完成续跑校验，实际日志确认**21 CROSS_LEAF_REUSED +
  19 SELF_BATCH_REUSED**，原40个已成功leaf全部复用。不是重跑初始参考或旧self。
- 7A hifiasm batch0于17:05:21进入扩展、17:05:34成功提交；读取真实receipt确认
  `mapping_rerun=false`，原candidate mapping334.302秒被保留为来源记录，不是本次又跑
  334秒。新marker key与receipt一致，raw/result/stderr的记录SHA与原candidate一致。
  schema为incident_self_seed_profile_extended_v1，policy为>=10Mb、f0.005、无mapper时限。
- 2A hifiasm batch4（约87Mb）17:05:21实际启动新扩展mapper；5D hifiasm batch3
  （原有>=100Mb快速profile）17:05:35启动。两条command.json均实际含f0.005，日志均
  打印64GiB AS保护。5D仍调用原two-lane-v2脚本，证明未为了扩展改写旧profile执行来源。
  17:07作业CPU约199%、RSS7524MiB；两个mapper仍在运行，没有新失败。
- 代码与指导文档已提交并推送master **4a9b0a4**；远端采用冻结runtime，不读取活动master。
  新监控22444日志为`logs/wheat-live-20261119-165306.jsonl`。旧42523432仍运行Step2。


### 2026-11-19 20:21：保持当前范围，记录中短序列耗时

- 用户已同意：当前任务不中断、不重提；不再向<10Mb或多record批次全面扩展激进参数。
  当前>=10Mb单record门槛是这次小麦incident策略，不是已经验证的全局默认；未来自动
  触发需结合实际计算成本，不把判断责任交给用户。保留完成结果，初始参考/cross不变。
- 重新通过调度器确认42523432和42876793均RUNNING，无本次运行的新失败。
  新版20:21:09已完成230个leaf（含缓存复用和cross，不能当作230个新增self），
  CPU199%、RSS4906MiB，继续两个受保护的mapper；未改资源策略或冻结profile。
- 20:21:01元数据盘点：1342个self批次中208个有完成marker，其中206个有快速profile
  receipt、2个native。这里只检查receipt与marker的key/输出摘要记录一致，没有在登录节点
  重扫大文件哈希，也不代替最终完整性验证。20:21:19又有一个快速批次完成。
- 已完成、非adoption的快速mapper耗时统计：10–50Mb 133批，中位61.907秒，范围
  4.077–1895.542秒；50–100Mb 53批，中位126.659秒；>=100Mb 20批，中位384.934秒。
  这是完成样本的耗时分布，不是与native的配对加速比，也不是精度验证/全流程ETA。
  诊断证据：远端logs/self-extension-timing-20261119-2022.json。
- 已查较慢例外：1B hifiasm batch2，47,220,644bp，mapper1895.342秒、CPU1890.499秒、
  峰值2.928GB，18:28:15开始、19:00:31成功结束。索引加载仅约1.6秒，时间消耗在实际
  mapper，不是恢复校验/卡死；不重跑已完成结果，也不因这个例外进一步扩大精度损失。
- 旧版Step2：1D去重成功2402/2402，4D去重成功1773/2402、16个已启动未结束。
  数字来自日志成功ID集合，不把当前partition ID当已完成数；旧基线继续不动。
- 上个90分钟监控22444在18:24左右正常到期，不是作业终止。新的只读监控会话57024，
  日志logs/wheat-live-20261119-202008.jsonl，预计21:51左右到期。到期后先确认作业真实
  状态再续接监控，不因观察句柄结束而重启主任务。最终q0/全流程仍未完成，goal保持active。


### 2026-11-19 21:31：大target单路阶段，未改变精度或重提

- 20:50:48盘点确认>=100Mb self 21/21完成（20快速+1保留native）；50–100Mb
  54/61、10–50Mb 193/680、<10Mb 0/580。按批次最大record分箱，不能把所有中短批次
  都当单record。全流程仍在q0，不能由超长完成推断快结束。
- 21:14:54起新版由双路转单路。不是dispatcher丢失任务：active plan的快速准入上限
  maximum_target_bases=800,000,000，而剩余快速批次target约807–925Mb；这些属于
  exclusive池。native上限是1Gb，不能将native规则误用于fast。精度仍是原f0.005。
- 21:16:23从绑定profile/manifest与完成marker盘点，快速未完成126批（包含运行中），
  分布于11个operation，全部target>800Mb。当前<=800Mb的快速池已清空。
  这是性能门槛的可疑保守点，不等于已证明可以无条件取消资源准入。
- 首条2A flye batch5（query77,465,637bp，target885,256,697bp）21:14:54开始，
  21:19:48成功结束；之后7A flye batch18到21:23:58成功，5A flye batch14到21:29:23
  成功。单核持续计算且产出增加，不是卡死、重跑校验或新的OOM。
- 21:31:29调度器仍确认两主任务RUNNING；新版365个成功leaf、CPU99%、RSS3247MiB。
  既定不打断当前任务/不扩大短序列降精度范围保持不变。本轮只观察，未改冻结plan、
  科学profile、800Mb门槛或64GiB AS保护；不要把这里当作放宽准入的用户批准。
- 后续若评估资源门槛，须区分资源调度与精度策略：检查多批实际内存及保护边界、预计
  续跑成本与节省，再以隔离资源overlay验证；保留已完成profile/key，不直接编辑活动
  文件。先确认当前剩余批次，不能使用126这个历史数贸然重提。监控57024仍活跃。


### 2026-11-19 23:23：旧版4D完成，新版进入普通短contig池

- 旧42523432：23:11:37最后一个4D分片成功。去重日志集合确认1D和4D均2402/2402，
  5D已启动16个分片，仍属Step2而非全流程完成。23:22调度器RUNNING，RSS93592MiB、
  历史峰值100789MiB，低于163840MiB配额；保持旧基线不动。
- 新42876793：23:16:38自动切到native普通池，两个2B flye批次batch1/2同时开始。
  batch1为393条record、总19,991,322bp、最大260,668bp；batch2为426条、总19,991,485bp、
  最大172,327bp。target总924,608,183bp，在native的1Gb准入范围内。
  已读实际attempt/command.json：两条均-t 8，不带-f覆盖，保持原参数；不是扩大激进范围。
  23:22:42调度器RUNNING，CPU1596%、RSS12229MiB、峰值15452MiB，437个成功leaf。
  两个新native批次尚未结束，不能由16核忙碌推断已提速或通过验收。
- 普通池和快速池仍不混跑；切池不是所有快速批次已经完成。原参数多record批次可使用
  多query线程，与单条超长query仅占单核不同。PAF暂未写出不单独作为失败判据。
- 22:07完成样本校准：target>800Mb的快速任务22批、9个不同target，比对耗时中位
  99.911秒、Minimap2最高报告峰值3.964GB。是内存/耗时观察，不是准入已放宽或精度结论。
- 只读监控15024在23:22正常到期，已接续38098；新日志
  logs/wheat-live-20261119-232242.jsonl，约11月20日00:53到期。两主任务没有重启。
  当前master存在其他对话的并行提交；远端继续使用冻结runtime，不自动同步活动master。


### 2026-11-20 00:54：native慢批次已完成，保留真实剩余量

- 新版42876793继续RUNNING，462个成功leaf（含21个cross和复用）；从绑定plan/profile
  与self marker盘点：快速414/464、native27/878，总self441/1342。仍有50个快速批次，
  当前在native池执行，不得误报“快速全部完成”或把leaf计数当全流程百分比。
- 第一对native短record批次2B flye batch1/2已成功：393条/426条record，实际-t8，
  mapper387.469/376.104秒，峰值7.339/7.791GB。多query的并行性不能套用到单条超长query。
- 后续混合批次存在真实耗时长尾，均未改参数或中断：
  - 3B flye batch27：5条record、最长17,447,619bp，实际-t1；11月19日23:56:11成功，
    mapper1502.421秒、CPU1498.814秒、峰值4.065GB。
  - 3B flye batch9：10条record、最长9,471,548bp，实际-t3；11月20日00:18:03成功，
    mapper1307.255秒、CPU2668.490秒、峰值5.790GB。
  - 2B flye batch16：2条record、最长17,279,947bp，实际-t1；00:26:45成功，
    mapper1946.509秒、CPU1942.065秒、峰值4.717GB。
  这些记录说明“短/中等长度”不保证便宜，但不是扩大精度损失的自动授权。没有配对
  aggressive对照，不声称加速比或精度差；完成输出保留，不为做对照重跑主任务。
- 00:53:47运行中native为3B flye batch8（00:33:10开始）及2A flye batch33
  （00:49:53开始），CPU199%、RSS8963MiB，历史峰值15452MiB，无新失败。
- 旧42523432的1D/4D均2402成功；00:36:18核查5D为219/2402成功、16活跃，00:53
  调度器仍RUNNING，CPU1595%、RSS90470MiB、历史峰值100789MiB（配额163840MiB）。
- 监控38098于00:53正常到期，已接续40354，日志logs/wheat-live-20261120-005347.jsonl，
  预计02:24左右到期。仅续接只读观察，两个主作业及冻结runtime均未重启/修改。


### 2026-11-20 05:58：隔夜持续产出，两个主任务不变

- 调度器连续确认旧42523432、新42876793均RUNNING，没有本次运行的新失败或OOM。
  新版05:57:23成功leaf548（含21cross及缓存复用），当前普通池双批次；仍未完成q0，
  不能以成功leaf数或某个染色体分片完成宣告整任务完成。
- 05:58:02绑定plan/profile+marker的轻量盘点：快速414/464、native113/878，合计
  self527/1342。尚有50个快速和765个原参数批次未完成（含运行中）；没有再次扩大精度
  损失范围，也未改800Mb快速并发门槛。这里不是重新全量哈希验收。
  私有证据logs/wheat-checkpoint-20261120-0558.json。
- 旧版1D/4D仍均2402/2402成功；5D为949/2402成功、16活跃。按成功ID去重计数，
  不是按日志最后一个partition ID推算；继续保持旧基线不动。
- 2B/3B等混合批次观察到较长耗时，但完成后保留原结果，无须按超时故障重跑。
  3B flye batch8于01:13:01成功：mapper2387.134秒、CPU2381.700秒、峰值5.312GB；
  后续batch16也成功。没有把这些局部原参数耗时当作已完成精度或加速对照。
- 两主任务djob元数据jobWallClockLimit均0（02:26左右核查），未发现显式作业级时限；
  不由此推断集群/队列永远不设限。04:06共享文件系统使用率53%、inode1%；quota -s
  未给出可用用户配额信息，用户级配额未确认。不要把共享空余当作个人额度。
- 隔夜只续接只读监控，没有重提、安装、update.sh或修改冻结runtime。31710已正常到期，
  当前监控7600，日志logs/wheat-live-20261120-052715.jsonl，预计06:58左右到期。
  到期只代表观察会话结束，必须查调度器再续接，不得因此重启主任务。goal仍active。


### 2026-11-20 07:52：继续保留普通批次，明确剩余工作规模

- 新42876793、旧42523432均持续RUNNING；本轮没有重提、改参数、同步master或覆盖结果。
  新版07:51成功leaf576，仍在q0；不能把leaf数当整流程进度。
- 07:52:24轻量profile/marker盘点：快速414/464、native141/878，self合计555/1342。
  剩余50个快速、737个native（含运行中）；私有证据
  logs/wheat-checkpoint-20261120-075224.json。此为元数据盘点，不是内容哈希/科学验收。
- 剩余native按每批最长query分组：<1Mb为48批、1至<5Mb为144批、5至<10Mb为290批、
  >=10Mb为255批。**native并不等于所有record都短于10Mb**：多record批次保留原参数，
  10Mb单record快速规则不覆盖它们。这里没有据此扩大激进策略，不能按已完成样本
  的均值直接承诺全流程ETA；保留现有结果与用户确认的不为精度讨论打断主任务边界。
- 低CPU批次抽查：7A flye batch19为11条record，最长9,460,642bp，-t3、无-f覆盖；
  07:43成功，mapper742.221秒、CPU1139.282秒、峰值4.613GB。此前低占用不是调度卡死。
  3B flye batch18为2条record、最长17,172,492bp，07:27:12启动，07:51仍运行；
  继续观察，不把暂未刷出的raw PAF或单query长尾单独当作失败。
- 旧版07:52的5D为1301/2402成功、16活跃，1D/4D已完成。实际旧日志明确
  chromosomes=22、shared_workers=16；5D结束也不代表整个Step2结束。保持旧基线不动。
- 监控7600已正常到期；当前只读监控28309，日志
  logs/wheat-live-20261120-065819.jsonl，预计08:29左右到期。到期续接观察而非重启主作业。


### 2026-11-20 09:49：普通池资源利用率评估，尚未扩并发

- 已重读定点修复规范。持续低CPU不仅是故障观察项；可以评估不改科学参数的资源优化。
  当前没有部署新资源策略，也不扩大<10Mb/多record批次的降精度范围；旧基线不动。
- 09:46盘点157个有完整stderr统计的native成功批次，其中155个满足query总量<=20Mb、
  target<=1Gb；这155个mapper峰值RSS最大7.791GB、中位4.952GB。其余两个较大原参
  成功批次不混入此范围。待完成native721批全部落在上述规模内，query总量最大
  19,999,010bp、target最大924,608,183bp。证据
  logs/wheat-native-resource-samples-20261120-094626.json；不是新增并发的安全证明。
- 只读同节点诊断42940708已SUCCEEDED（agent-X86-29，09:48:14至09:49:15，1CPU）；
  目录native-memory-diagnostic-20261120-0948/保存脚本SHA、submission、7次/proc采样、
  summary.json和final-job.json。仅读取当前UID/目标工作区及已验证主PID94158。
  两个mapper在约60秒中分别消耗60.02/60.05秒CPU，VmPeak为4.344/4.969GiB，
  VmHWM为3.804/4.765GiB；主控制器VmHWM0.677GiB，两个helper各不到0.05GiB。
  当前native的AS limit均为unlimited；快速批次的64GiB guard并不覆盖native。
- 代码确认当前native也受两路和128GiB/路启发式预留约束；这提供资源优化候选，
  不能直接把两路改四路或把RSS样本当硬限。下一步应先隔离验证native保护与并发，
  检查mapper/helper/restore的进程树边界、线程预算、失败不提交、回调映射、复用和
  reader/audit身份，再决定是否值得切换；优先不改科学profile/key、原命令和已完成输出。
  新资源策略若需要重提，按原规范在收益与切换成本明确且新资源ready后执行，
  不为精度讨论机械中断，也不把原参数长期低效视为只能等待失败。
- 原监控81664的本地句柄因会话中断丢失，先核实远端PID3118685仍活跃，临时只读取
  其日志；09:48核实该PID退出后才续接。当前监控10159，日志
  logs/wheat-live-20261120-094852.jsonl，约11:19到期。两个主任务均未重启；09:48
  新版592个成功leaf，仍在q0。09:18旧5D为1579/2402成功、16活跃。
- 09:18本次新版运行调度日志审计：590个唯一START、588个唯一成功END、2个活跃，
  无重复START/成功END和非零END；cross复用21、self复用19。范围仅本run的leaf调度，
  不代表整个下游不存在重复工作。证据logs/wheat-dispatch-audit-20261120-091759.json。


### 2026-11-20 10:13：四路普通自比对验证通过，用户要求按线程预算扩展

- 用户追问普通任务含义、剩余时间及为何不能更多并发。实际是2套组装（Flye/Hifiasm）
  ×22分组（21条染色体+Un）=44个self operation，按约20Mb query分成1342个子批次；
  不是1342套de novo或重复全量比对。10:04:48快速414/464、native161/878，余717个
  native和50个fast。最近1/2/4/8小时native成功10/18/44/121批；双路普通段粗估
  50–80小时，非整流程ETA，待调度优化后重新测量。
- 用户进一步问每路内存、4路是否太少，以及能否与run_all.sh线程数一致。已明确：
  4路只是验证起点，不是最终固定上限；目标是总线程预算与内存准入共同决定并发，
  单核批次争取8–16路，不能把路数和每路线程都设为--threads而超售CPU。
  已核实prepare_options.tsv threads=32，但.run_all/resources.json有效threads=16
  （2026-11-18资源续跑下调）；调度器当前申请32CPU/320GiB。后续须一起核对有效预算。
- 隔离试验42942033在agent-X86-56上SUCCEEDED，10:04:26–10:13:02；32CPU/320GiB。
  目录native-concurrency-pilot-20261120-1002/保存全部代码SHA、config、submission、
  tests.log、results和final-job.json。四个已完成native基线为2B flye batch1/2、
  3B flye batch0/1，query总量各约20Mb，target约916/925Mb；使用原冻结helper、
  原mapper、原参数和每批8线程，写入完全隔离的batch/merge/cache，未采纳试验输出。
- 每个helper和其顺序启动的mapper/restore子进程继承32GiB RLIMIT_AS；这是单进程
  地址空间限制，不是整棵进程树/RSS总限。四路执行490.524秒、含准备校验510.588秒；
  调度器观测峰值27797MiB。四批raw.paf和result.paf均与既有原参结果逐字节一致；
  单mapper峰值7.309/7.790/7.496/7.435GB。与原任务节点不同，不冒称全流程加速倍率。
  results/pilot.json SHA256=f6b857fe0762df6cb4579436da494fdcfce3c8fbb6bc548b4341dd031478bc7e。
- 新增native_concurrency_pilot.py及test_native_concurrency_pilot.py；本地10项测试
  通过（2.529秒），远端同10项通过（2.100秒），之后才执行真实mapper试验。
  测试用dummy helper只证明隔离/验证/保护机制，不能替代上述真实PAF结果。
- **尚未部署新普通池调度或改主任务参数。** 不能只把self_two_lane_admission.py的
  maximum_processes改成16：当前native无AS保护，且扩展plan verifier明确绑定旧资源
  策略。需要显式的资源层、guarded native命令映射及原回调还原，保留科学profile/key；
  验证原extension来源与新资源变更各自的身份，不能删除旧约束、伪造__file__或只修writer。
  同时覆盖续跑controller、独立reader、portable audit；主任务已加载/指纹绑定的文件
  不热替换，适当完成边界、资源ready、旧新版停止且锁释放后再安全切换。旧对照不动。


### 2026-11-20 10:52：八路原参验证通过，动态普通池组件已实现但未切换

- 上一轮为已验证等待：42942852当时仍RUNNING；本轮确认其SUCCEEDED，10:35:22至
  10:43:57，agent-X86-09，22CPU/220GiB，线程分配8+8+1+1+1+1+1+1。
  八批raw.paf/result.paf均与原生基线逐字节一致；执行478.493秒、总509.675秒；
  调度器峰值31044MiB（约30.3GiB）。不同节点，不据此声称全流程倍数。
- 远端目录位于比较根目录jm19-compare-614589f-20261118/下的
  native-eight-lane-pilot-20261120-1033/（不是cgat-reads-debug的直接子目录）。
  已保留code.sha256、config、submission、19项远端测试（3.046秒）、results及
  final-job.json。results/pilot.json SHA256为
  02794293671a8414f83e9c9ef9c23020620c202ed9571f94d064313e706fe995。
- native_batch_guard.py对真实冻结helper单独装配subprocess适配器：helper软限2GiB、
  硬限16GiB；同步mapper子进程软硬限16GiB；restore软硬限2GiB。helper本身不提高
  软限；每路预留18GiB。不是整棵进程树的RSS/cgroup上限。原参/原key不变；已有缓存
  不补造guard执行证明；新执行才以create-only方式发布native-resource-receipt.json。
- 新增候选native_resource_admission.py：原fast双路规则不变；native仅接受已验证的
  wrapper，保持desired线程分配，按CPU余量与288/18=16路内存准入填空；未知/未保护
  native独占，不混池。native_resource_bindings.py保留原SelfBindings科学层和复用，
  只替换待运行eligible命令并恢复原任务回调；新成功先验证guard receipt再merge/commit；
  独立新建reader bindings走同样receipt/output验证。没有修改当前冻结运行文件。
- **尚未部署、尚未重提**：仍需资源变更stager/verifier、明确的context/entry/reader/
  portable audit接入和计算节点整体验证。不能伪造__file__或删除原extension约束；先按
  原验证器验证旧计划，再独立证明新计划只改资源层。plan需新增native_runtime、
  native_support/native_guard/fast_admission等依赖，operation新增native_specs/scripts。
  原科学profile、原命令、native key与完成结果保持不变。资源ready、适当完成边界、
  仅停止新版且确认子进程/锁释放后，才在正常锁内将有效threads16恢复32并续跑。
- 10:49:09新版42876793仍RUNNING，604个成功leaf，活跃7B flye batch13和2A flye
  batch1，无失败；旧42523432仍在grt_step2，CPU约1597%、内存86857MiB。
  监控10159仍活跃，预计11:19结束；观察器结束不代表主任务结束，不因此重启任务。
- 本地定点验证42项native guard/pilot/admission/bindings测试全部通过（58.650秒），
  原fast双路准入6项回归通过（0.001秒）；不运行版本CI。测试覆盖16个单核批次、4个
  八线程批次、CPU空隙填充、内存满额阻止第17路、未知命令独占、禁止混池、旧缓存
  不执行/不冒称保护、回调还原、缺receipt不得完成、新reader验证及篡改拒绝。
  这些是组件测试，不替代后续真实staged controller/reader/audit闭环。


### 2026-11-20 11:21：普通池资源层完成实际切换，新版作业改为42943728

- 新增stage_native_resources/native_resource_bootstrap/native_resource_context、
  resume_native_resources/read_native_resources/native_resource_audit，严格独立验证旧
  extension来源与新资源差异，不改旧验证器断言、不伪造模块身份、不改科学profile/key。
  本地新增7项stage/bootstrap测试通过（589.782秒）、6项owner顺序测试通过（0.047秒）、
  3项audit测试通过（73.766秒）；之前42项native组件及6项fast准入测试仍是已记录基线。
- 计算节点预检42943568 SUCCEEDED，agent-X86-18，11:11:11至11:12:04，2CPU/20GiB，
  峰值222MiB。真实plan staging、controller configure、独立reader与audit preflight
  全部通过；没有用这个小资源作业执行正式流程。计划包括876个eligible native（含已完成
  可复用者）、464个原fast、2个已完成超范围native，共44 operations/1342 self批次。
- 新immutable bundle位于比较根目录native-resource-candidate-20261120-1110/，plan为
  plan/self-plan.json，SHA=cad752a468ec890170d1ad6730a851ccc0b359d8804b1d570c8312ec470b5950。
  9份实际代码、verify.dsub及code.sha256均已传输校验。44个operation对应任务清单的现场检查确认：
  22个q0_alignment_tasks.json的max_concurrent均未另设上限，不会再被隐藏两路限制卡住。
- 正式接替作业42943728，agent-X86-32，11:15:25启动，32CPU/327680MiB；11:15:41
  ready gate就绪。handoff目录native-resource-handoff-20261120-1115/保存gate/resume.dsub
  和launch.sha256、submission、ready、切换前原owner、scheduler snapshots及handoff。
  ready后再次核对资源、原owner PID94158/runID和受保护旧版42523432仍RUNNING。
- 只dkill新版原作业42876793（不使用force），11:18:29终态FAILED，原因明确为
  Job was terminated by xbzhang26，是本次有意切换，不是新故障。结束时610个成功leaf；
  仅4B flye batch1与2B flye batch18尚未完成（此前长7B批次已完成）。它们的临时attempt
  保留，所有已完成结果保留。调度器子进程列表为空且正常lock消失后才放行，不删锁。
- gate于11:19:43接受handoff，正式新run=20261120T031955Z-3903530-2bc35443，PID3903530，
  11:19:55正常持锁。原读取入口备份在plan/reader-installation/，原resource配置备份为
  plan/resources-before-20261120T031955Z-3903530-2bc35443.json。正常resource API已将
  effective threads16恢复32，history已记录；只安装新reader launcher，没有运行update.sh、
  发布CI、整体替换runtime或reprepare。日志logs/resume_native_resource_42943728.out。
- 原观察器10159在发现被有意终止的42876793后正常退出；INSPECT_NOW是该切换的终态提示，
  不是需要重启旧作业的原因。新观察器72919使用/tmp/cgat-wheat-live-monitor-native.py，
  跟踪42523432与42943728，额外记录复用数量、guarded starts/receipts及实际线程预算。
  首次输出日志路径需从当前session核实；90分钟观察窗口结束不等于主任务结束。
- 截至11:20:43新owner已进入正常Runner preflight，线程32。还需核实已有结果真正复用、
  新普通批次实际并发、CPU/内存及首批guard receipts；不能把preflight当q0/整流程完成。
  最终portable audit要用新native_resource_audit.py而非直接调用旧extension CLI。
- 新观察器日志已核实为logs/wheat-live-20261120-112048.jsonl，约12:51到期；session72919。
  11:21:51已看到ref:JM19_hifiasm的SKIP_VALID（原参考结果复用，未重新比对）；11:22:18
  新任务RUNNING、约单核用于续跑完整性验证，尚未启动普通mapper，不把这个启动阶段
  误当并发策略失效。后续要确认ref:JM19_flye、assign及self/cross缓存复用和实际并发。
- 新reader安装receipt已核实：prior_sha=33fc5bea2c85b08ae1705ba4054aa0ab91ac13932c65c7b30c8618c369cf0166，
  installed_sha=43766e880e7cb4196eb70519d79ffc8918238c30a53245bba2db88d1230f0e33。
  master另有其他会话的1fe41ab5（v2.0.21发布准备），不因此更新远端冻结runtime；本轮
  仅提交自己的incident工具/文档，不夹带其他会话的版本或发布改动。


### 2026-11-20 11:43：610个既有结果全部复用，真实普通池已跑满32线程

- 新run中ref:JM19_hifiasm于11:21:51、ref:JM19_flye_ABD于11:23:33、assign于11:25:57
  均为SKIP_VALID。随后21个cross leaf与589个self批次验证后复用，共610个，无初始比对
  或这些已完成批次的重新计算。11:28:14开始新的计算；不是一直停在校验。
- 新普通池此前没有启动的原因已现场查清：优先级队首是原策略仍独占的fast批次，target
  大于800Mb；不是普通池仍被两路限制。11:31:34的inventory-113134.json记录703个待跑
  eligible native、45个待跑exclusive fast，首个native之前有12个exclusive fast；这里只读
  manifest/marker清单，不是输出验收。其字段guarded_native表示新池资格，**不代表旧
  completed native曾用新guard**；实际执行必须看此次日志与native-resource-receipt。
- first-progress-113321.json记录最初8个新增fast成功，每个16–71秒。没有为了这些持续
  完成的短任务再次重启。到11:40:00之前共新增17个fast成功，总成功leaf达到627。
- **11:40:00普通池正式同时启动7路**，线程分配8+4+7+1+3+5+4=32：4B flye batch1、
  2B flye batch18、4B flye batch0、4A flye batch25、4B flye batch34、1B flye batch36、
  1B flye batch8。前两条是上次有意切换时尚未完成者，旧attempt保留而不冒充成功。
- 11:40:53.428443调度器实测CPU3086%（约30.86核），RSS31197MiB（约30.5GiB），
  当时峰值32109MiB，配额327680MiB；32线程预算实际用起来了，不必硬凑16/32个进程。
  只读观察器日志中的这一组原始样本已另存handoff目录native-pool-first-active.json。
  当时guarded starts=7、guarded成功receipt=0，尚需继续核实首批普通输出成功及后续峰值。
- 旧版42523432继续运行。11:26:04只读统计：1D、4D各2402/2402完成；5D为2021/2402、
  16活跃。这仅是Step2某个染色体组，不是全部旧任务进度。原baseline未改动。
- 监控仍为72919，日志logs/wheat-live-20261120-112048.jsonl；任务未因短时低CPU或观察器
  轮询间隔再重启。规范文档补充了不同资源池、总线程预算和历史复用/新增guard证明的区分。
- 11:45:44已核实首批**2个正式普通池成功**（不仅是pilot）：1B flye batch36，11:40:00
  至11:42:16，5线程；4B flye batch34，11:40:00至11:44:51，3线程。两者TASK_END=0，
  resource receipt与spec、native key、complete marker SHA和输出身份记录一致，mapper
  16GiB AS/restore 2GiB AS子进程均returncode0。证据native-pool-first-successes.json；
  登录节点仅核对小receipt/marker/spec与文件stat，没有额外扫描大型PAF，完整内容验收由
  正式helper/controller完成。helper_maxrss是进程历史高水位，不应误当当前RSS或AS上限。
- 11:44:54观察到动态扩为10路、线程之和仍32；guarded starts12、guarded成功2、总成功
  leaf629=610复用+17新增fast+2新增native。CPU2658%（约26.6核），RSS38406MiB、
  当时峰值41297MiB（约40.3GiB），无OOM/失败。后续根据每批线程需要自动增减路数，
  不是固定7/10/16路，也不为凑32个进程超卖线程。整流程和整个q0尚未完成，需继续监控。


### 2026-11-20 13:15：观察器已续接；发现线程偏好造成长期绕过，候选验证中

- 原观察器72919于90分钟窗口正常结束（exit0），不是主作业结束。确认退出后启动67604，
  使用/tmp/cgat-wheat-live-monitor-native-compact.py；新日志
  logs/wheat-live-20261120-125232.jsonl，约14:23到期。完整样本仍写JSONL，控制台只打印
  简要状态和最长两条活动leaf，避免16路时输出巨大。两个主作业仍是42523432和42943728。
- 12:56:33新版累计738成功leaf=610复用+17新增fast+111新增普通，16路/32线程，
  CPU2172%、RSS57051MiB，峰值73227MiB（约71.5GiB），无OOM或非零退出；3D flye
  batch12此前执行约37分钟后也正常完成，没有按固定时间阈值杀任务。旧版仍运行Step2。
- 已确认22个q0 unit都在55-unit执行计划中，包含q0_chr:Un；self plan的22个unit与其
  完全一致，没有“Un未计划”的问题。当前active只显示21个，是Un尚未启动，不能据此补跑。
- 新发现：当前native_resource_admission.py把desired线程当作必须一次满足的数量，
  不足时不断回填较小任务。13:14:59现场fairness-audit-131459.json记录2A flye batch3
  （偏好5线程）仍未启动，从11:48:29起已有117个work更小的native启动；1B flye batch45
  （偏好8线程）亦未启动，已有109个更小任务启动。运行中的admission SHA仍是
  e06fdfd7f0f6119a0372f597e27c965fd39da8100770d96a095ba039658625a7。
  这是已观察到的绕过/排队长尾风险；不能直接宣称修正一定缩短整体makespan。
- 新增独立候选native_fair_admission.py（**未部署**），改为对优先native分配
  min(desired, available)，不改native cache key、mapper科学参数、内存guard或fast池。
  test_native_fair_admission.py的14项通过（2.464秒），包含旧策略绕过head而候选以2线程
  启动head的直接复现；原native_resource_admission.py和原11项测试保持原样、仍通过。
  没有修改当前远端冻结文件，也没有终止/重提主任务。
- native_concurrency_pilot.py新增显式allow_thread_rebudget+baseline_threads验证模式，
  未显式启用或无split guard则拒绝改线程；baseline原命令逐项核对，实际输出必须raw与
  restored PAF均逐字节相同。报告增加baseline/actual grants和driver源码前后SHA检查。
  更新后16项试验测试通过（4.034秒），dummy测试不是生物学等价验收。
- 真实小试验42947499，13:00:01在agent-X86-37启动，4CPU/40960MiB；两条已完成的
  2B flye batch1/2从原8线程各改2线程，在完全隔离目录重放，不采纳结果。目录为比较根下
  native-thread-rebudget-pilot-20261120-1258/。pilot driver SHA=
  6762b6939d15f02fb2b7c8d65d50a132da2baaf4f3a90e2ae5ef66fbcf01de6d；config SHA=
  152e3c9d1c2c11711ab62d80b2cc600656169b8bb244de2cc7886bbf11c42afc。
  13:15查询仍RUNNING，两个helper PID2129546/2129547，映射试验预算1800秒（仅试验，
  不是主作业超时）；首批旧8线程基线曾耗时约350秒，2线程可能需要约20多分钟。
- 下一步先看试验终态与完整PAF比较。不能仅因候选测试通过就停止主作业。
  若确需切换，必须实现显式resource-plan revision/reuse，而不是重新生成所有native specs：
  已完成native-resource-receipt绑定旧spec SHA、guard源码路径和实际thread_grant。
  保留原native_guard/native_support依赖、每个operation的native_specs/native_scripts、
  native_runtime及科学profile/key；用新admission/owner/context/reader/audit构建新计划。
  旧stager当前强制MODULES同目录且prior_launcher指向最初extension，需要一个经过验证的
  previous-native-plan分支：用旧bootstrap/旧stager/旧admission验证旧资源计划，再独立验证
  新资源差异与当前reader的prior_launcher。不要伪造__file__、不删除receipt检查、不把旧
  结果追认为新策略执行。这个revision机制**尚未实现**，新候选也尚未挂入默认stager。
- 保留原8路试验作为native_calibration（内存guard与并发范围依据）；本次2路降线程试验
  不能替换那个要求8路的槽位。若未来revision使用fair候选，应另行绑定完整的线程重预算
  验证报告，而不是放松旧8路校验。候选代码单独存为native_fair_admission.py，原默认
  native_resource_admission.py及其测试未修改，避免把未完成试验的策略悄悄当成默认入口。


### 2026-11-20 13:24：两例8→2线程完整重放通过，尚未切换fair候选

- 隔离试验42947499 SUCCEEDED，agent-X86-37，13:00:01至13:24:29。2B flye batch1/2
  原8线程改为各2线程，两个raw.paf/result.paf对均逐字节一致，原科学参数/输入不变。
  mapping执行1439.490秒，总driver1455.098秒，调度器峰值7016MiB。少线程使单批变慢
  是预期；这不是“降线程让单批更快”的证据，也不是整体调度加速倍率。
- 远端16项pilot测试先通过（5.577秒）；final-job.json已保存。完整report SHA为
  e7f9f9c7ec42cd7f7073fb71c5818288c08197e1d2590ecb9b13baa83d9ff44f，driver仍为
  6762b6939d15f02fb2b7c8d65d50a132da2baaf4f3a90e2ae5ef66fbcf01de6d。未采纳试验输出。
- 候选源码/定点测试/调查文档已通过4b038cbd保存推送；当前运行中的42943728仍使用原
  e06f...dispatcher，没有中断。下一步必须保留现有native specs/guard receipts实现资源
  计划revision并验证producer/reader/audit后，才考虑新的ready/安全切换；这个机制仍未实现。


### 2026-11-20 13:52：保留receipt的资源修订完成预检，主任务尚未切换

- 当前旧42523432、新42943728仍RUNNING。13:49:53调度器记录新版CPU2490%、RSS65737MiB、
  峰值73227MiB；旧版CPU1593%、RSS90186MiB、峰值102143MiB。没有OOM或主任务重启。
- 13:51:47新版成功leaf 822（610复用+17此次fast+195此次guarded native），16路仍活跃。
  2A flye batch3、1B flye batch45仍未启动，此前11:48:29起被更小work插队的现象还存在。
  这是调度绕过风险，不是已经量化的全流程性能损失；不要冒称候选已带来提速。
- 旧版Step2的1D/4D/5D分组均2402/2402完成，当前3D为84/2402、16个活跃分片；不是
  整个Step2快完成（还含其他染色体）。保持旧对照不动。
- 原观察器67604本地句柄退出143，不能据此判主作业终态。重新核实两主任务RUNNING后，
  仅续接只读观察器26767；日志logs/wheat-live-20261120-133819.jsonl，约15:08自然到期。
  先poll这个句柄，不重复启动观察器，不把观察超时当作主作业失败。
- 新增stage_native_revision.py，独立于仍未改动的默认stage_native_resources.py。
  native_resource_bootstrap.py增加previous_resources：用原资源计划绑定的实际旧bootstrap、
  旧stager、旧admission验证旧计划，临时canonical module选择在成功/异常后恢复。
  只接受第一代旧资源计划；显式拒绝revision链，避免不经验证的递归/循环引用。
- 新修订完整保留operations（含native_specs/native_scripts）、native_runtime、native_guard、
  native_support、原8路native_calibration、科学origin/profile/key及资源预留。只绑定新
  owner/context/reader/audit/bootstrap/stager/fair admission；prior_launcher必须指向上一代
  native reader的实际hash。用单独native_thread_calibration和native_thread_pilot依赖绑定
  已完成两例8→2线程试验，不替换8路内存校准。试验guard是同内容隔离副本，不冒用生产路径。
- 8项修订专项测试及原staging/owner/audit/bindings/新旧admission共58项通过（2.722秒）。
  测试在SHA核对的Linux临时源码副本中运行，避免Windows挂载盘元数据开销；合成fixture
  只证明身份/复用/调用链，不冒称生物学验收。测试日志本地/tmp/wheat-native-revision-focused-tests.log；
  副本位置索引/tmp/wheat-native-revision-test-root。没有CI、浏览器、整版更新或重新prepare。
- 独立远端包native-fair-revision-20261120-1350/（比较根下）；预检42949276在agent-X86-18
  以2CPU/20480MiB运行，13:47:54–13:49:18 SUCCEEDED/exit0，峰值132MiB。staging保留并
  接受当时189个guarded成功receipt，随后controller --validate-only、reader
  --validate-reader-only、audit --validate-only全部通过，明确q0_completed:false。
- 新plan SHA=343f1d1933c71d79105405f958b5241887d1fa0f0c936ed1a3d3a70befe039f3；
  prior plan SHA仍cad752a468ec890170d1ad6730a851ccc0b359d8804b1d570c8312ec470b5950。
  新bootstrap SHA=6d33e4ae6753f26c130a3e37d14c6f013bac90a74063f10d81a4356248c21367；
  revision stager SHA=53472528d9d4d869eb885ab99a0eb76683fe19ebcacc75a507e055d45e01a4f1；
  fair admission SHA=a54c3d5cdfc830f95986dd23d42bd35dbd22046f23cdb04076b98133b05a67bf。
  目录内code.sha256、final-job.json、plan/staging-receipt.json、verify_42949276.out和
  post-preflight-observation.json保存证据。新资源计划没有重新生成任何native spec/script。
- **尚未切换主任务。** 安装reader SHA仍43766e880e7cb4196eb70519d79ffc8918238c30a53245bba2db88d1230f0e33，
  新版42943728仍是原e06f...dispatcher、原正常锁持有者；旧42523432未触碰。候选预检成功不代表
  全q0通过或主任务正在使用fair。下一步先核实时序/在途批次成本和资源，若切换则新建ready/handoff，
  等新32CPU/320GiB资源ready后仅停42943728，确认正常children/lock释放，备份并安装新reader。
  不能复用旧handoff中针对42876793的终态证明。当前还没有提交替代主作业或新handoff gate。


### 2026-11-20 14:10：fair调度已安全接管，当前新版42949582

- **当前新版改为42949582**（agent-X86-64，32CPU/327680MiB）；旧对照仍42523432。
  原新版42943728是有意终止，不再是应持续监控的运行任务，不要重提它或复用其旧handoff。
- 新作业13:58:20启动，13:58:38资源ready，尚未占分析工作区。新交接目录比较根下
  native-fair-handoff-20261120-1357/；gate.py SHA=
  7246cfb9da9e4d3c57f071a2cd1cf90e5a42e5bd1c2c9f8f3cbcd46f312b17f4，resume.dsub SHA=
  ac6791e7d25a127fac489fc5608f2fb7cd9cad875b2fe919c31ae24cdbed96a1。新gate增加旧子进程
  PID空、protected_baseline身份、实际硬内存额度检查；12项合成gate测试通过（0.052秒）。
  仓库native_fair_handoff_gate.py保存原字节，仅是本次交接存档，不是通用可执行入口。
- 等2D flye batch15、7D flye batch12两条较长在途批次都TASK_END exit0后才切换（14:03:44
  两者确认完成）。stop_previous.py用新鲜djob/ready、正常owner PID/run_id、reader SHA、
  原在途成本核验后，仅dkill 42943728，不使用force。停前成功leaf845=610复用+17新fast+
  218新native；未完成16个，保留attempt目录，不把临时PAF当缓存。估计在途线程预留时间
  204.45线程分钟，不是实测CPU时间或承诺的墙钟损失。prestop-leaf-snapshot.json保存清单。
- 42943728于14:05:24终态FAILED，exitCode10003，明确Job was terminated by xbzhang26。
  随后确认scheduler pids为“-”、正常.run_all/lock不存在；旧42523432仍RUNNING。
- release_handoff.py重新核对两个作业与protected baseline、ready SHA/新32核320GiB额度，
  以临时文件fsync+create-only link发布handoff.json，避免gate读到半份JSON。14:06:07
  handoff accepted；ready SHA=b1c7042345bd5d3bcbba7a4dfdcf0c2121cf3677209ce62bfdbe01b44237990f。
  old-terminal.json、新new-ready-scheduler.json、baseline-at-handoff.json、stop-request.json、
  prior-owner.json、post-installation.json等都在新交接目录。stop/release helper的SHA记录在
  helpers.sha256；没有触碰142、没有改旧对照或删除已完成产出。
- 新正常owner 14:06:16取得锁：PID1538453，process_start6256597221，
  run_id=20261120T060616Z-1538453-726e2805。采用预检通过的新plan
  native-fair-revision-20261120-1350/plan/self-plan.json（343f1d...），admission a54c3d...；
  不是修改旧e06f...文件。source/archive实现已通过0bfaa532保存到master。
- reader新SHA=69dc816929da34bfe075f5796cbc23670c052be93147e0dc85e3145672ddffd0；
  plan/reader-installation/prepare_q0_evidence.sh备份SHA仍43766e880e7cb4196eb70519d79ffc8918238c30a53245bba2db88d1230f0e33。
  同目录receipt.json绑定run/plan/prior/installed。资源文件在plan/resources-before-
  20261120T060616Z-1538453-726e2805.json备份后，经冻结resource API保持32线程，前后字节一致。
- 新log为logs/resume_native_fair_42949582.out。14:07:31 RUN/RESUME，14:08:32 hifiasm参考
  SKIP_VALID，14:10:07 flye参考SKIP_VALID；**此刻尚未确认全部leaf复用或fair实际新mapper执行**。
  后续看assign跳过、845个叶子复用、新head任务开始与实际grant/guard receipts，不能仅凭
  controller预检或换了entry就宣布科学任务完成或整体加速倍率。
- 观察器26767已因有意终止42943728正常INSPECT_NOW退出，不是新故障。新只读观察器19945，
  source=/tmp/cgat-wheat-live-monitor-fair-compact.py，log=logs/wheat-live-20261120-140639.jsonl，
  约15:37到期。新job资源启动早于旧job取消，failed/active阶段归属改按新log的真实RUN id时间
  过滤，而非仅按djob startTime，避免将旧owner取消记录误报为新失败。先poll19945，勿并行重复
  启动主观察器。旧对照仍Step2；全q0、后续LGZ、最终portable audit均未完成。
- 如新owner真失败，先看调度/日志/正常锁；不覆盖冻结源码或重prepare。需要回退时，先停止新
  owner并确认子进程/正常锁释放，再按原reader备份及旧plan做受控回退；不能在运行中覆盖launcher。
  旧native specs/guard/support完全相同，新旧实际1..8 grant的receipt仍可核验，不需删除成果。


#### 14:20复用与首批执行确认

- 14:14:07 assign也SKIP_VALID。14:17:41统计824个SELF_BATCH_REUSED、21个CROSS_LEAF_REUSED，
  **845个停前成功leaf全部复用**。14:20:23将prestop-leaf-snapshot.json完整success集合与
  新log的TASK_END/实际EXECUTION_OVERRIDE逐一比对，全部完成且已完成leaf重执行交集为空。
- metadata-only审计再次核对218个旧native-resource-receipt与保留spec SHA、native key、
  runtime/policy/manifest、complete-marker SHA及输出identity一致。不是登录节点重hash大型PAF；
  PAF内容有效复用由新主控制器的真实验证/跳过路径证明，也不把历史receipt追认为新guard执行。
  证据新handoff目录first-reuse-audit.json。
- 此次新做的先是剩余fast profile：2A flye batch4于14:17:18开始、14:18:30成功（72秒），
  后续5A flye batch20、3A flye batch29也成功，14:20:23共848个成功leaf；当时运行4A flye
  batch10。这些仍是原科学profile及原fast/独占资源规则，不是新native admission没生效。
  **截至该快照native新启动数仍0**；继续观察普通池进入及实际fair grant/receipt，不能仅因
  现在看到单条快速任务就再次重启，也不能据本次预检/安装声称整体加速已测得。


#### 14:25普通池与实际降grant成功确认

- 普通native池14:21:29开始，已完成此前4个剩余fast profile后切入。14:25:02记录10次native
  实际启动、3个新native成功、4次实际grant低于原desired，其中1例已经成功。它们是当前
  42949582的新执行，不是把218个旧receipt重新计数。
- 1A flye batch32原desired8、实际3线程，14:21:55启动、14:22:29成功；新receipt SHA=
  715e531df38924292f4704e574c04caf8fab7758a99e5335dac9f7afe5d45568，实际grant3，mapping
  AS16GiB/restore AS2GiB均exit0、complete-marker/output身份一致。该例证明真实capped-grant
  成功，不是全数据/所有线程组合等价或整体提速倍率证明。
- 原被绕过的1B flye batch45在14:21:30以8线程开始、14:21:55成功；2A flye batch3在14:21:29
  以5线程开始，当时尚未结束。6B hifiasm batch31原desired8只拿到1线程亦已开始；1A flye
  batch29原desired8实际3、batch28原desired7实际5。各路总grant仍不超过32，不为凑32路超售。
- 14:22:43快照7路活跃、grant合计32、CPU3054%、RSS25089MiB（约24.5GiB）。这是这一批
  多query任务的实际利用率，不把当前低内存外推给超长任务，也不把7路解释为退回固定小路数。
- 证据新handoff目录first-fair-native-execution.json。native实际executed路径仍在旧
  native-resource-candidate-20261120-1110/plan/native/，这是刻意保留spec/guard身份，
  **不代表用了旧dispatcher**；active plan343f1d...和admission a54c3d...已由新owner验证。
  继续poll19945；旧对照42523432仍RUNNING，完整q0/LGZ/portable audit尚未完成。


#### 15:38长批次完成与观察器续接

- 新版42949582在15:37:47仍RUNNING，915个成功leaf，16路活跃、grant合计31，CPU2687%、
  RSS49376MiB、峰值55713MiB/限额327680MiB；当前比对阶段总1364，剩449（含运行中）。
  总数按冻结plan的1342个self batches与22个cross leaves计，不是完整工作流的完成比例。
  其中845个为此前成功复用、4个为本轮新增fast、66个为本轮新增guarded native。
- 先前安静约一小时的3D Flye batch0已在15:29:08 TASK_END exit0；14:28:52启动，实际grant1。
  stderr记录276条query、mapper Real3612.017s/CPU3602.668s/PeakRSS2.328GB，说明该批次持续
  使用所分配的一核，不是挂起。mapping/restore均exit0；小型complete-marker与stderr SHA
  均匹配guard receipt。raw/result分别42027923/42593451字节；没有在登录节点重hash大型PAF。
  receipt SHA=ab8e9fce195dc33d0eeea83b4db35f2cd7ce973403421ef80bb754ef65dc2d9d。
- 6B Hifiasm batch31仍未结束（14:21:30开始、grant1）。其他批次持续成功，不能仅凭它暂时
  没有PAF输出取消；需继续区分真实停滞和低grant计算长尾，也不能把整体CPU冒充单批次CPU。
- 旧对照42523432仍RUNNING/grt_step2，CPU1594%、RSS90044MiB；本轮未改动或重提任一任务。
- 观察器19945已按181轮窗口正常exit0（末次15:37:08）；这是观察器到期，不是计算任务退出。
  核实两作业仍RUNNING后仅续接只读观察器：**session79134**，source仍为
  /tmp/cgat-wheat-live-monitor-fair-compact.py，新日志logs/wheat-live-20261120-153747.jsonl，
  首次15:37:47，预计约17:09到期。优先poll79134，不重复启动观察器；此快照须实时核实。


#### 16:00观察通道恢复（非计算任务重启）

- 本地观察session79134在15:58前后exit143，早于计划窗口到期，不能据此认定计算任务失败。
  15:58:23独立djob核实42949582与42523432均RUNNING、owner和计算子进程仍在。
  原远端observer PID791947及shell791158短暂仍在，等到15:59:24确认两PID均消失后才续接，
  未重复运行观察器、未中断计算任务；断开原因尚未确定。
- 新只读观察session **42743**，脚本仍为/tmp/cgat-wheat-live-monitor-fair-compact.py，
  log=logs/wheat-live-20261120-155941.jsonl。15:59:41新版951/1364个leaf成功，16路、grant31，
  CPU2344%、RSS51759MiB；旧版仍grt_step2。新监控预计约17:31到期，优先poll42743。
- 1B Hifiasm batch41已在15:51:25成功（14:54:19启动、grant1），mapper Real3422.943s、
  CPU3414.746s、PeakRSS2.128GB；mapping/restore exit0、complete marker SHA匹配guard receipt。
  6B Hifiasm batch31仍运行；当前没有新增失败，不以单批安静时长为由重提。


#### 16:18只读观察器与SSH生命周期解耦

- session42743亦提前exit143。16:16:56再次独立djob确认两作业RUNNING，登录节点已无原
  `python3 -u -`观察进程；原日志末次16:16:47。没有把观察退出当作作业失败，也没有重提计算。
- 为避免SSH断开中止采样，将同一观察脚本原样保存到
  ~/cgat-reads-debug/wheat-observer-20261120-1618/monitor.py，传输后核验SHA=
  329074a0550e486dd886d282c11b596e26a25033ba999b9a1d0a8484386153ae。
  经原environment.sh加载后nohup运行，stdin=/dev/null，stdout/stderr均到该目录console.log。
  **当前监控不再以本地session为句柄**：observer.pid记录远端PID **2636895**；16:17:51
  `ps`确认真实python进程、PPID1、命令路径匹配。续接先核实PID/完整命令与日志新鲜度，
  不凭pid文件判断存活；PID重用、观察退出均不能作为重启计算任务的理由。
- 全量采样log=~/cgat-reads-debug/logs/wheat-live-20261120-161744.jsonl；每30秒采样，仍为
  181轮有限窗口，约17:49结束；告警仅打印INSPECT_NOW并结束观察，不会自动取消或修改任务。
  观察仍只读取调度器、状态、日志和小型完成记录，不在登录节点处理大型FASTA/PAF。
- 首次16:17:44新版973/1364成功，16路/grant32、CPU3021%、RSS51860MiB；q0_chr:Un也已开始。
  旧版仍grt_step2、CPU1594%；两者无新增失败。本次只改观察器运行方式，不改科学参数或runtime。


#### 17:25近三小时6B普通批次的进程级诊断

- 对6B Hifiasm batch31不凭日志安静直接取消。先查x86队列OPEN/ACTIVE、agent-X86-64
  cpuFree16/memSched52100MiB，确认有余量，再提交同节点只读诊断**42956948**，1CPU/1GiB请求，
  17:20:48–17:21:49 SUCCEEDED。只读当前UID、指定新版workspace及已核实owner1538453的/proc；
  未读其他用户数据，未重做比对或改变主任务。目录native-long-batch-diagnostic-20261120-1721/。
- 七次采样跨60.19395秒：目标mapper PID1551781、同一start_ticks及全部采样同一TID集合，
  CPU增加60.06秒（0.998核），worker为R，VmSwap0；末次RSS1781312KiB（约1.70GiB），
  HWM2117160KiB（约2.02GiB），AS soft/hard均16GiB。实际grant1。
  **该窗口是持续计算而非I/O/内存阻塞**；不能外推整个三小时都无停滞，也不证明算法耗时最优。
- 其他mapper线程会退出或重建，不能直接用两端“存活线程CPU之和”相减冒充进程累计CPU；
  summary对全七次PID身份/TID集合不稳定的进程置CPU估算null并注明原因，保留原始samples。
  目标6B满足稳定集合与单调计数条件。summary SHA=
  e4912e899055af5f6afff9b711262104bd380180a7d251490bf46d4ccb008971。
- sampler.py（文件名sample.py）SHA=34b76e2345f83edf54d44b06bfbea0b28dfb7677a321b47438bab59eb243607c；
  sample.dsub SHA=c207c51e063c8160e5f08875d5f4abe1693ac70956826c680d7615399f86e633。
  code.sha256、submission.txt、final-job.json、samples.jsonl、summary.json均保留；新主任务未重提。
- 17:23:38新版1057/1364个比对leaf成功，16路、grant31；旧对照仍RUNNING/grt_step2，无新增失败。
  当前观察仍为远端PID2636895，非本地短时读取session；目录/日志见16:18条目，预计17:49到期。


#### 17:50 6B长尾成功完成、观察窗口续接

- 6B Hifiasm batch31在**17:45:23 TASK_END exit0**，自14:21:30起约3小时24分钟；实际grant1。
  mapper日志mapped194 sequences，Real12230.173s/CPU12197.438s/PeakRSS2.019GB。
  mapping/restore均exit0，complete-marker及stderr摘要匹配guard receipt；raw/result分别
  24464378/23001626字节，未在登录节点重hash大PAF。receipt SHA=
  840b7dd96f0098a0fe58a740f7ffe26a73456ef23f85a84e05d3ea3cab482e14。
  该批没有取消重跑、没有改科学参数，原计算投入保留；不把完成证明外推成所有批次最优性能。
- 原远端observer2636895已完成181轮采样，末次17:48:17。17:49:19确认实际进程不存在，
  再独立djob确认新旧任务均RUNNING后，仅续接只读观察窗口，未重提任何计算任务。
- **当前观察PID2727810**，目录~/cgat-reads-debug/wheat-observer-20261120-1750/，
  monitor.py与上次逐字节相同（SHA329074a0550e486dd886d282c11b596e26a25033ba999b9a1d0a8484386153ae），
  nohup独立运行，PPID1，console.log及observer.pid在同目录。
  全采样日志logs/wheat-live-20261120-175000.jsonl，17:50:00首样；约19:21窗口到期。
  本地只读查询脚本/tmp/wheat-detached-observer-poll.py已更新到该PID文件/日志，传1为立即单次，
  传6为间隔60秒六次查询；本地查询被中断不影响远端采样，禁止据此重复启动观察器。
- 17:50新版1104/1364个leaf成功、剩260，16路/grant28，CPU2343%、RSS45261MiB；
  已无上述6B batch31长尾，当前最长5D Flye batch11约20分钟。旧版仍RUNNING/grt_step2。
  q0完整合并、GRT/LGZ后续与最终audit仍未完成，不能以leaf计数宣布全流程成功。


#### 19:23首批q0染色体收尾与观察窗口续接

- 新主任务42949582及旧对照42523432仍RUNNING。新版已有4个q0染色体单元SUCCESS并提交正常
  checkpoint：1B 19:18:39、6D 19:19:37、7D 19:20:56、5D 19:22:14。
  19:23:23按冻结plan与本轮TASK_END核对1315/1364成功，剩49（19个guarded native self、
  29个fast self、1个cross）。普通self有11个已启动未TASK_END；不把pending成功回调都说成
  当前正在运行的mapper。旧版仍grt_step2，18:53已核实当前3D为698/2402，后续须实时刷新。
- 19:17后出现多条complete.json已生成但TASK_END尚未写出的批次，调度CPU从约16核降至3核；
  随后整染色体SUCCESS陆续出现、19:22重新启动一批普通任务，grant合计30。
  这是需要区别于mapper停滞的收尾/汇总窗口；现有证据尚未证明重复扫描，未为短暂下降重提。
  若持续串行或重复工作，再沿callback/merge/最终验证调用链排查，仍保留完整性校验。
- observer2727810完成181轮（末次19:20:35）后退出；19:22确认实际进程不存在，并独立djob
  确认两计算任务RUNNING，才续接远端只读观察。**当前观察PID1022372**，PPID1，目录
  ~/cgat-reads-debug/wheat-observer-20261120-1923/；monitor.py与上次完全相同，SHA=
  329074a0550e486dd886d282c11b596e26a25033ba999b9a1d0a8484386153ae。
  log=logs/wheat-live-20261120-192243.jsonl，首样19:22:43，预计约20:54窗口到期。
  /tmp/wheat-detached-observer-poll.py已更新到新观察目录/日志；仍先查真实PID/命令及日志新鲜度。
  本轮未改变主任务runtime、参数、结果，也未重提计算或触碰旧版。


#### 19:30普通池结束，切入剩余快速profile

- 19:30:15新版1334/1364个leaf已TASK_END成功；普通受保护876个与历史未保护2个均已完成，
  剩29个fast self和1个cross。12个q0染色体单元已SUCCESS：1A、1B、1D、2A、2D、3D、4B、
  4D、5D、6A、6D、7D。完整q0、下游LGZ与最终audit仍未完成。
- 19:17–19:30存在完成标记已写但等待父控制器merge/commit的回调，低CPU期间上述checkpoint
  持续提交。19:30:16已真实启动3B Hifiasm batch22的SELF_EXECUTION_OVERRIDE，grant1，
  SELF_RESOURCE_GUARD AS64GiB；这是原快速profile/原内存规则的阶段切换，不是16路普通池失效。
  不因当前只有一个fast mapper而无条件解除长任务隔离、增加路数或再次重提。
- 源码检查发现潜在后续精简点：SelfBindings.finish最后一个batch调用Profile.merge，merge
  遍历validate_batch；外层SelfBindings.output_identities对selected batches再次validate_batch。
  selected路径包含validate_paf(require_cigar=True)，哈希memo不等于PAF格式校验memo。
  这是已定位的重复调用路径，尚未隔离测得其独立耗时，也未部署新缓存或跳过验证。
  本轮收尾持续推进且已切入新pool，未为该候选优化重启支付校验成本；如后续确认收益足够，
  需采用内容/文件身份约束的成功验证复用、失败/变化回退，覆盖普通/快参及cross类似路径，
  保留最终完整审计，不能直接修改运行中的冻结依赖或去掉检查点。
- 当前只读observer仍为PID1022372，目录wheat-observer-20261120-1923/，日志192243.jsonl；
  新旧计算job均未重提，旧对照不变。
