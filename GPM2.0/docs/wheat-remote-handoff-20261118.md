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


#### 20:01全部比对leaf与22个q0染色体检查点完成

- 最后一个leaf为3B Hifiasm batch17，19:59:20 TASK_END exit0；最后的q0_chr:3B在
  **20:00:31 SUCCESS**。**1364/1364个比对leaf、22/22个q0染色体单元（含Un）已成功**。
  主job42949582继续运行，**20:00:39自动START q0_evidence**，不是全流程完成。
- 已以当前冻结plan（343f1d...）绑定的22个task manifests重新构建预期command集合，逐项核对
  本轮成功TASK_END集合完全相等、无缺项/额外项、无未结束leaf。22个status均success，并核对
  SUCCESS日志所指checkpoint的unit/status与文件摘要，未在登录节点重新hash大型PAF/FASTA。
  这是metadata-only阶段验收，不替代主控制器内容验证或最终portable audit。
- 证据native-fair-handoff-20261120-1357/alignment-stage-completed-20261120-2001.json，SHA=
  ccd4488e011a85c4a6c9a5cbf516c336cfa8d1bb192d7b9604bc3b74d1fd0859。
  不把876个eligible native的历史缓存追认为全部受新guard实际执行；保持已有来源分层。
- 下一步重点监控q0_evidence reader的真实性能/身份核验，然后LGZ准备、step1/2/3与最终产物。
  前述重复PAF格式验证仍只是源码定位的候选精简项，未为此修改冻结runtime或重提。
  当前远端observer1022372、目录wheat-observer-20261120-1923/、日志192243.jsonl持续运行，
  约20:54窗口结束后按真实进程/调度状态续接；旧对照42523432仍grt_step2，保持不变。


#### 20:14 q0_evidence读取路径的只读诊断

- q0_evidence仍运行；incident_q0_routing_reader.json于20:03:37生成（420776字节），说明初始
  provenance_inputs已通过。随后主job RSS从约0.5GiB增长到约45GiB，未接近320GiB上限。
  metadata/grt_q0_evidence.json尚未发布；不能将metadata声明当作科学汇总成功。
- 为区分全序列加载、检查点校验与构建known_pairs，在确认agent-X86-64 cpuFree32、
  memSched183172MiB及x86队列OPEN/ACTIVE后，提交只读诊断**42964604 SUCCEEDED**，
  20:11:27–20:13:29，1CPU/1GiB请求；七次采样约120秒，仅访问当前UID/指定workspace进程的
  /proc状态和fd路径/偏移，不读取基因组内容、不附加调试器、不改变主进程。
- reader PID1754951（read_native_resources.py，--threads32），parent owner1538453处于等待。
  reader同一start_ticks，120.22594秒内CPU增加118.72秒（0.987核），持续R，非卡死或零CPU等待。
  20:11:28打开1B Flye self/result.paf offset460652544，之后切到1B Hifiasm self PAF与1B Flye
  分组FASTA，再于20:12:28回到1B Flye self PAF offset78577664，至20:13:28推进到361291776。
  同一PAF确实被再次读取；单凭这点不能把不同语义消费都删掉。
- 源码_initial_inputs先manager.prepare/validate检查q0 checkpoint，再按alignment验证分组FASTA，
  用read_paf及aligned_blocks构建known_pairs。它持有完整sources序列；当前低CPU属于这个串行
  路径，不能说成mapper并发失效。后续候选是融合/复用内容受约束的验证及避免不需要的PAF对象
  构建，仍需保留名字、方向、区间、CIGAR及内容身份检查，不能盲目跳过整个_initial_inputs。
  **本轮尚未部署性能修改或重提任务**，也未测得独立提速倍率。
- 证据q0-reader-diagnostic-20261120-2012/：code.sha256、sample.py、sample.dsub、submission.txt、
  final-job.json、samples.jsonl、summary.json。sample.py SHA=
  dd2c564e6ad802b44a5a7dfec9a885b8bb714b635e9399d03c918e5ed4d27915；summary SHA=
  dced28bcd2a2cc288a72ccd8eb95fa23f5200174eea76f94b9a196784dc017f7。
  当前observer1022372不变；本地poll工具现在也显示active单元，避免只重复已完成leaf数量。


#### 20:34分组FASTA重复解析的仓库定点修复（尚未部署远端）

- 仅用远端descriptor及文件stat盘点：66个基础PAF共12522376422字节；44个唯一分组FASTA共
  30374062385字节，但query/target角色合计132次读取，代码逻辑解析量91122187155字节。
  这些是清单/大小统计，不是在登录节点重新扫描数据，也不把它当成实际I/O计数。
- 仓库q0_preparation._initial_inputs现在在单次调用/单个染色体的固定sources与group上下文内，
  按(dataset,path,实际内容SHA)复用已成功的分组序列/成员校验；self两个角色及cross复用同一路径。
  每次取摘要仍走既有run_orchestration稳定内容哈希memo，校验完整stat签名，失效回退完整字节读取；
  新内容重新解析，首次解析前后摘要不同则失败，不按存在/非空/mtime单独跳过。输入清单不删项。
  缓存不跨调用/染色体，不保留整份分组序列，不改变PAF、CIGAR、known_pairs或科学选择参数。
- 相似路径核对：q0_admission已按dataset一次加载原始序列，不存在该query/target分组重复读取；
  routing/self reader包装会调用同一个_initial_inputs，无需另复制实现。PAF重复消费问题仍未修复。
- 5项新增回归覆盖角色复用/跨调用重验、同大小且恢复mtime的内容修改、解析中修改、字节相同
  的文件替换、不同dataset角色不得误用缓存。test_q0_preparation共28项通过（11.497s），
  test_q0_admission共28项通过（3.186s），合计56项；仅针对性测试，无整版CI/发布。
- 40Mb合成分组FASTA的实际前后AST校验代码块微基准：三轮交替顺序、每轮清空内容哈希memo，
  旧6次解析/121500048字节，新2次/40500016字节；中位0.375478s→0.154806s，局部约2.43倍。
  报告docs/incident-tools/wheat-20261119/partition-role-reuse-benchmark-20261120.json。
  **不是整套小麦/q0提速，也不代表总I/O减少同等比例**；新旧仍需内容哈希及其他验证。
- 当前远端42949582冻结runtime未变，20:33仍q0_evidence、约1核/46GiB、无失败。它已读了约
  半小时；仅凭局部微基准不足以证明中断重读更划算，因此本轮保存源码修复但不强制重提。
  若后续自然失败/续跑或新增实测表明切换净收益为正，再按绑定plan/正常锁的规则部署；
  不能把master补丁冒称已在当前远端生效。当前observer1022372不变。


#### 20:55 q0 reader继续推进、观察窗口续接

- 第二次只读进程诊断**42965098 SUCCEEDED**，20:37:52–20:39:53，agent-X86-64、1CPU/1GiB请求，
  sampler与42964604逐字节相同，目录q0-reader-diagnostic-20261120-2038/。
  reader仍PID1754951，同一start_ticks；120.19893秒内CPU119.11秒（0.991核）。
  读取位置从3D Flye self PAF offset153608192持续到440213504，随后3D Hifiasm self PAF，
  20:39:53进入4A Hifiasm batch1/query.fa身份检查。与20:11的1B采样相比，明确不是原地等待。
  summary SHA=50eab7bf6c3744e84dc3c196d4616955e6d7813aefe0148f855ab1c974f54089。
  这是原冻结reader进展，不是master的57f6d8ff补丁生效；该补丁尚未部署远端。
- observer1022372完成181轮，末次20:53:08；20:54确认PID已不存在，独立djob确认两作业
  仍RUNNING，才续接。**当前远端observer PID3067484**，PPID1，目录
  ~/cgat-reads-debug/wheat-observer-20261120-2055/，源码SHA仍为
  329074a0550e486dd886d282c11b596e26a25033ba999b9a1d0a8484386153ae。
  log=logs/wheat-live-20261120-205456.jsonl，首样20:54:56，预计约22:26到期。
  /tmp/wheat-detached-observer-poll.py已更新目录/日志；仍以实际PID/完整命令和采样新鲜度确认存活。
- 首样新版42949582在q0_evidence，约1核、RSS47502MiB/限额327680MiB，25个外层单元成功
  （2ref+assign+22q0_chr），1364leaf全部成功；485次本轮guarded native实际执行/receipt完成。
  旧版42523432仍grt_step2，CPU1595%、RSS85357MiB。无新增失败，未改主runtime或重提计算。


#### 21:34 q0 reader后续只读诊断（未切换runtime）

- 诊断42965792 SUCCEEDED，21:11:08–21:13:09，目录q0-reader-diagnostic-20261120-2111/。
  同一reader PID1754951在120.197秒内消耗117.41秒CPU；已推进到7B，先读Flye self PAF，
  再读Hifiasm self PAF，随后重新读Flye PAF。文件位置复位是不同消费步骤的重读，不能说成
  单次扫描一直向前，也不直接证明可删除某次语义校验。summary SHA=
  ef4c2645759a1152ab3f0a03eb0072fe7c7c2c9e42919b75934c6800fd721a74。
- 21:22起新版RSS由约47GiB降至约33GiB。为区分等待与计算，资源检查确认agent-X86-64仍有
  16空闲CPU/52100MiB可调度内存、x86 OPEN/ACTIVE后，提交1CPU/1GiB请求的同节点只读诊断
  42966572；调度器SUCCEEDED，实际七次采样21:31:01–21:33:01。
  sampler与前次完全相同，SHA仍dd2c564e6ad802b44a5a7dfec9a885b8bb714b635e9399d03c918e5ed4d27915；
  目录q0-reader-diagnostic-20261120-2130/，dsub SHA=
  f08126708e16bb3cc8af328eb0dfada72d87ab10067b8558db44ea8a491a32f7。
  reader同一start_ticks，120.191秒内CPU119.96秒（0.998核），七次均无工作区打开文件句柄。
  这说明采样期间在CPU计算，不能凭无输出判为I/O卡死；没有Python栈，不能据此指定某个函数。
  summary SHA=f5c84453a57adb706a75c19bbdad7135e257fe0b4fd926275a4464b52706b125。
- 仅以checkpoint JSON和文件stat盘点其输入/输出并集：4851个路径、134041746043字节，
  其中1474个FASTA共121496040434字节、66个PAF共12522376422字节。额外provenance清单
  1679条共3879386字节。没有在登录节点读取基因组内容；这是清单逻辑体量，不是本轮实际I/O，
  也不能据此声称这些文件都被无谓重算。后续重复内容身份计算优化仍须保留完整性与变更检测。
- 21:34两主作业仍RUNNING，新版q0_evidence、旧版grt_step2；新版manifest和补充任务目录
  尚未出现。observer3067484仍存活且采样新鲜，预计22:26窗口结束。未改冻结runtime、
  未重提主任务；57f6d8ff仓库性能补丁依旧未部署。诊断final-job.json/samples.jsonl/summary.json
  均保留在各自目录，不能将诊断SUCCEEDED误当成小麦主任务已成功。


#### 21:47 非暂停式栈采样定位source索引，保存无损局部优化（未部署）

- 同节点只读诊断42966973 SUCCEEDED，21:42:34–21:43:15，目录
  q0-stack-diagnostic-20261120-2143/；1CPU/1GiB请求，实际峰值14MiB。
  登录环境module/PATH未找到py-spy，因此仅在独立诊断目录放置官方benfred/py-spy v0.4.1
  x86_64 wheel内的单文件工具，不安装到主环境、不改变主runtime。wheel对照Release资产
  SHA=6a80ec05eb8a6883863a367c6a4d4f2d57de68466f7956b6367d4edd5c61bb29；传输后binary SHA=
  e7c2de2dc54449ec88c086f1859555b4e34e63ccdcf3f8804496f9306cd44de6。
- 验证同UID、reader命令路径、start_ticks=6258771188后，每20秒一次共3次
  dump --nonblocking --full-filenames --json。节点原有ptrace_scope=0，未改权限/内核设置，
  未用locals/native/core、未发暂停/终止信号；3次全部退出0。
  调用链均为prepare_evidence -> build_catalog -> split_source：一次source SHA计算，
  两次set(sequence)字符校验。证明已进入source索引，不再只靠RSS下降猜测；仅3次样本，
  不能用2/3当作准确耗时比例。summary SHA=
  67150d283d678a17e4718a1bc78cbcba07990e0b9ecca5daf0e78a7aa5b3154a。
- 仓库split_source定点优化：按同一DNA_ALPHABET生成非法字符regex，保留先upper的规范化
  与空/非法输入拒绝；完整source已经算过SHA时，仅对恰好覆盖全长的未切分segment复用digest，
  所有真正子区间仍独立计算。源/segment SHA、ID、坐标、短N计数、长N边界/连接均不改变。
  q0_catalog、q0_admission、q0_publication、source_intervals共用该函数，无需复制补丁。
  structural_support的ACGT-only局部复杂度判断是不同语义，不随之改写。
- 针对性测试：q0_evidence/preparation/admission/paths共119项（15.166s），
  q0_publication/source_intervals共32项（46.673s），151项全部通过。新增覆盖256字符及Unicode
  upper语义、未切分源只算一次摘要、内部/终端长N子片段仍分别哈希（含全N）。
- 实际旧/新函数的400例随机等价核对及两种30Mb合成样本三轮交替微基准均完整SourceIndex相等。
  未切分样本中位0.371519s→0.293784s（局部1.265倍），300段长N样本0.307086s→0.273087s
  （局部1.124倍）。报告incident-tools/wheat-20261119/source-index-reuse-benchmark-20261120.json。
  不代表客户小麦/整套q0提速。远端实读q0_sources SHA仍为旧版
  8f26d53ead816a66438f8489a3565bb617558893adcc6f5600581ab1b28c2bad，仓库新版SHA=
  2fd88802d000d57b672420dc9270220f8865b1140dd6048f16c0955f8e497aa0。
- 当前reader已运行约106分钟；小幅局部收益不足以抵消重读成本，本轮不切断它。
  此补丁会改变builder源码身份，不能直接拷贝进冻结runtime冒充原计划；后续有必要受控续跑时
  与57f6d8ff一起按绑定reader/plan及完整复用门禁评估。21:46两主任务仍RUNNING，新版
  q0_evidence约1核/34GiB，manifest/补充任务尚未出现；observer3067484不变。


#### 22:27 候选目录进入首个补充比对，观察窗口续接

- 低频只读诊断42968143 SUCCEEDED，22:00:06–22:20:08，agent-X86-64、1CPU/1GiB请求，
  目录q0-phase-diagnostic-20261120-2155/（目录时间仅是标签，以调度器/采样时间为准）。
  每120秒一次，共11个非暂停Python栈+自身reader的/proc元数据样本；仍不读取locals、
  不发信号、不改变主runtime，所有栈采样退出0。1200.729秒墙钟内reader CPU1196.88秒。
  22:00–22:08依次观测Hifiasm参考PAF offset38281216→215801856→358547456→414892032→556687360；
  22:10起进入interval_rows/merged_intervals及候选区间列表构建，不是重新跑参考mapper。
  sample.py SHA=77f3588d4c16e77dc49d99606693afaab87f7fa61092a63bb92744cd5e664dc1；
  summary SHA=e37cd68c4366d24527889a5cef1e1aa980b6c1c126c9697927d4999ace5cf93f。
  **该20分钟诊断已结束**，不要把最后22:20的栈当成实时位置；本地poll现在同时显示采样时间、
  age和sampling_complete。final-job.json/samples.jsonl/stack-*.json/summary.json均保留。
- 22:21首次观测到补充目录grt/evidence/q0_prepare/tasks/q0-map-8024dde83cbf20e7ffa6d8ee/。
  至22:25 query.fa已15168078字节、target.fa已32088868779字节；command.json显示150个query
  segment、38117个target segment，ID集合不相交。真实mapper命令保持原q0补充策略：
  minimap2 -c -x asm10 -D -P --dual=yes --no-long-join -t 32；未套用内部self快速近似参数。
  command.json SHA=c8380c36daa8d00a3703ed09160aa23d6e7c0b1a95a37adcae3f1545444a4829。
  22:26调度器出现新增子进程PID1839627、作业CPU约1.6核，RSS94824MiB（限327680MiB）；
  stderr/临时PAF尚空、无success.json，不能把输入准备完成称为补充比对成功，也不据安静日志杀任务。
  第一批1364leaf仍完整，不是被重新计算；最终q0 manifest仍未出现。
- observer3067484完成181轮（末样22:25:22）后自然退出。22:26独立核验PID不存在、181行
  和两主作业djob RUNNING后，才续接同字节只读observer。**当前PID944455**、PPID1，
  目录~/cgat-reads-debug/wheat-observer-20261120-2226/，log=logs/wheat-live-20261120-222639.jsonl。
  源码SHA仍329074a0550e486dd886d282c11b596e26a25033ba999b9a1d0a8484386153ae；首样22:26:39，
  预计约23:58到期，仍须以实际PID/日志新鲜度核实。/tmp/wheat-detached-observer-poll.py已更新。
  旧版42523432仍grt_step2、约16核，未改动；新版42949582仍q0_evidence。
  仓库57f6d8ff、8f33a52e两个局部性能补丁均未部署到当前冻结任务，未重提主计算。


#### 23:08 补充mapper降并发的线程级只读核查

- 新版仍在首项q0-map-8024dde83cbf20e7ffa6d8ee补充比对。22:29–22:44曾约32核，随后
  CPU逐步降至4核；不能据低于申请核数就重提。23:04节点检查为OK、32CPU空闲、
  183172MiB可调度内存、仅主任务运行，x86 OPEN/ACTIVE。
- 同节点只读诊断42970316 SUCCEEDED，23:05:35–23:06:36，1CPU/1GiB请求，目录
  q0-supplement-thread-diagnostic-20261120-2305/。核对同UID和精确补充query路径后，
  只读/proc状态、进程/线程CPU及I/O计数，不读序列、不attach、不发信号。
  sample.py SHA=55b173e021bab6a263d9e3c954693361f188309a9da65f7d1089b4aaa73474cf；
  dsub SHA=90c5a7af7b61ad2a76b20cfb4f75faf1f5a60d557ad9fc2ba832fc7861945eb8。
- mapper确认为PID1839627、命令包含原补充任务；4次采样共60.068秒，进程CPU239.74秒
  （3.991核）。6个TID集合未变，其中4个线程各增加约59.93秒CPU并处于R，另2个没有明显
  CPU增量。mapper RSS38355176KiB、HWM54741052KiB、VmSwap=0；I/O计数全窗口未变。
  这排除了“整个mapper都在等磁盘/交换”的解释，符合少数计算线程长尾；没有读取线程局部变量，
  不能声称已经定位到具体4条query，也不能由此给出完成时间。
  summary SHA=f7ffcf7b9b75bbb610705d74f7131d8055d11b14ee512dfe1fab7abbd585d9f8。
  使用进程CPU独立计数；未用幸存线程CPU和冒充进程累计CPU。
- 23:07主作业RSS约124000MiB/限327680MiB，无失败；补充success.json和q0 manifest仍未生成。
  未修改或重启主任务/旧版。observer944455仍活跃（预计23:58窗口结束）；所有计算节点
  只读诊断现已结束，无持续占用诊断作业。本地poll仍每分钟核实，重复输出仅保留首末及状态变化，
  原远端30秒完整采样不变；已结束的Python栈不再当实时位置显示。


#### 23:30 后续补充输入的提前核查提示（仅本地只读poll）

- 23:24起新版补充任务CPU约2核、RSS约122558MiB，仍无success.json/最终manifest，未出现
  错误；本轮未重启。旧版3D持续新增MUMmer SUCCESS，不能仅用同一grt_step2标签认为它停滞。
- 核对后续代码partial_source_request：只要已放置segment存在达到100bp的未覆盖区间，
  请求中仍使用**整段source segment**作为query上下文，并非只比对那100bp。因此后续补充
  query总量/最长序列可能与当前150段约15MB显著不同；不能沿用本轮低内存给后续任务背书。
  这只是源码风险识别，当前尚无下一项实际大query，未把推测说成已发生OOM或重复计算。
- /tmp/wheat-detached-observer-poll.py增加metadata-only提示：未人工核查过的补充query.fa
  大于100000000字节时输出supplement_large_input_requires_review，并以exit3停止**本地poll**
  以便立即检查；不停止主任务，不改mapper参数/精度/资源，也不把总FASTA大小当最长contig长度。
  100MB只是保守排查阈值，不是资源准入/精度自动触发或OOM判定；后续应在计算节点核查
  真实长度分布、mapper是否已启动及剩余资源，再决定是否需要受控修复。不能为清提示直接
  kill/restart。明确审查后才可在helper的reviewed_large_tasks记下任务ID；单凭success.json
  存在不会免除提示。当前第一项15MB不触发，正常退出0已实测。
- 本地稀疏文件/假proc目录测试5项通过：小输入exit0、大输入exit3、仅有marker仍exit3、
  显式已核查ID exit0、主作业失败仍优先exit2。只测试只读探针，不触碰远端进程。
  helper此刻SHA=2820fcc103e496d0fea4178d759b136d09684d1b37532025ff015d7853e0b1d9。原远端30秒observer944455未变；上述提示依赖本地poll运行，
  不冒称远端已部署自动干预服务。
- 共享文件系统df显示54%使用、inode约1%使用；quota -s退出1且无输出，故未取得用户级
  配额信息，不能把共享空间充足等同于已确认账号无配额限制。


### 2026-11-21 14:15 续接监督：初始任务完成，第二项补充范围和内存告警前核查

- 昨日 observer944455已完成181轮，最后样本为11-20 23:57:05；今日核实PID不存在。
  这段空窗不能称为持续监督。14:02、14:09独立djob确认新版42949582、旧版42523432
  都RUNNING，之后才续接同字节observer3770106（PPID1），目录
  `~/cgat-reads-debug/wheat-observer-20261121-141009/`，日志
  `logs/wheat-live-20261121-141010.jsonl`，源码SHA仍
  `329074a0550e486dd886d282c11b596e26a25033ba999b9a1d0a8484386153ae`。
  181轮/30秒，正常窗口约至15:41，遇真实告警会提前结束；不是自动修复/聊天通知服务。
  本地`/tmp/wheat-detached-observer-poll.py`只更新observer路径，未抹去大输入审查提示。
- 新版初始1364leaf完整、25外层unit成功、22个q0_chr成功，现仍q0_evidence。
  首项`q0-map-8024dde83cbf20e7ffa6d8ee`比对在03:43:21结束（19062.863秒，
  mapper峰值84.185GB），03:52:27提交success.json，result.paf为2666514061字节。
  今日核验receipt status/spec、四项输出路径/大小及小型command SHA一致；大FASTA/PAF
  的全内容摘要未在登录节点重读，不把该元数据复核称为独立全内容审计。
- 第二项`q0-map-a6056c2d8fcb81f6ca19d1a7`的command写于11:20:43。
  query.fa32021891617字节、35879个query；target.fa32104036857字节、38267个target，
  所有query ID都在target集合中。实际命令仍`-c -x asm10 -D -P --dual=yes
  --no-long-join -t 32`；没有把self近似档偷偷套到混合补充任务。
  这与partial_source_request只要参考未覆盖区间>=100bp就请求整段source的扩张风险一致；
  尚未靠当前Python栈独立确认调用行，不能把推断写成现场栈证据。
  不能用1364/1364推断全流程接近结束，也不能按query FASTA字节读取比例推算比对进度。
- 14:02至14:14新版作业内存293692→293770MiB，峰值300194MiB，硬限制327680MiB；
  当前约286.9GiB，峰值293.2GiB，余量约33GiB，近期稳定但不保证下一批安全。
  旧版仍grt_step2、约16核，保持未改动；新版约21核，并非闲置无CPU。
- 同节点只读诊断42998141 SUCCEEDED（14:11:25–14:12:27），1CPU/1GiB请求，目录
  `jm19-compare-614589f-20261118/q0-large-supplement-diagnostic-20261121-1413/`。
  sampler SHA `edb4f32eeb4160629b9a45faf4465da632585510f666563478f3a850ef6aca8a`；
  核实同UID、精确query路径、mapper PID2282216/start_ticks6264302243；四次60.065秒
  采样累计进程CPU1258.16秒（20.947核）。mapper RSS174223736KiB、上层reader
  RSS125594368KiB，两者VmSwap=0；I/O计数不变，query fd约1.09GB、target fd约8.12GB，
  result.paf.tmp仍0字节。采样时mapper已运行约2小时50分，不能从凌晨首项完成时间推算
  该mapper已跑10小时。没有读取序列、修改主进程、发送暂停/终止信号。
  summary SHA `ed563e97230ab8a93695538ecb8b1b64be143039b869d2d08ff3eb28bf84f8fb`。
- 追补昨晚native perf诊断：42971611因计算节点没有/usr/bin/perf而准备失败，不是主任务失败。
  之后42971802 SUCCEEDED（11-20 23:48:59–23:49:10），目录
  `q0-supplement-perf-diagnostic-20261120-2348/`在新版运行目录下；使用私有perf及依赖，
  不安装共享软件/修改kernel权限。对首项mapper1839627采10秒用户态CPU-clock指令地址，
  189样本、0丢失，98.41%在ksw_extd2_sse41、1.06%在mm_update_extra。
  仅证明当时单核长尾窗口以原生比对扩展计算为主，不代表整个首项或当前第二项的占比。
  已补存final-job.json，SHA `aa233f34dbd1f4b5ef24fbb77de7ca30f5566e40fd57bc87defeb8840eb181cc`。
- 当前未重启/重提主作业、未修改科学策略或冻结runtime；57f6d8ff/8f33a52e仍未部署。
  下一步应依据真实query长度和混合比较范围评估补充任务的资源准入、可复用证据及分片，
  不盲目加并发，不将partial PAF视作完成，不绕过builder/外层检查点绑定。

- 真实query长度诊断42998164 SUCCEEDED（14:13:10–14:16:33），目录
  `q0-supplement-shape-diagnostic-20261121-1415/`在新版运行目录下。
  1CPU/1GiB请求，流式只读扫描201.392秒，核验前后文件stat未变化且全部ID/顺序与command
  相同；不输出序列、不接受或改写主任务缓存。脚本SHA
  `9ab17e6f9d22c42961b0b3f804bd9d2f716b3e7143af33457d95f8527c8eee33`，
  本地192个分块边界fixture通过。实际35879条、31625089260bp，中位49667bp；
  >=1Mb 2807条、>=20Mb 334条、>=100Mb 21条，最长289508469bp。
  summary SHA `4d4294eb661445d3eb68d42e99139ca47a8f2b244ac7e83a3b22a69274de4977`。
  因而不能以首项15MB查询的行为估计当前整轮，也不能称“后面没有长序列”。
  两个本日只读诊断均已结束并存final-job.json。14:17主任务仍RUNNING，
  新版293788MiB/327680MiB、CPU2094%，旧版89948MiB/163840MiB、CPU1596%。
- 完成上述实际范围、长度、资源及进程核查后，本地poll才将该特定task加入reviewed集合；
  这仅消除已处理的“大输入待核查”重复提示，不代表该任务资源准入安全或低效问题已修复。
  新任务仍触发提示，调度器/内存/失败告警保持原样。第二项参数仍未改动，最终manifest未出现。


### 2026-11-21 定向优化进行中：补充关系复用与缺失窗口隔离试验

用户已明确要求“好，推进定向优化”，当前目标仍未完成；不能把下面的局部源码/试验
当成已部署的新流程。新版42949582、旧版42523432均保持运行，未替换冻结runtime。

- 覆盖诊断42999168 SUCCEEDED，agent-X86-18，81.475秒计算、峰值305MiB。目录
  `q0-partial-coverage-diagnostic-20261121-1426/`在新版运行目录下；源码SHA
  `f63d361d9e2c3371d0e40915df8193a808b78c7986a861744274b54d4c7a13f3`。
  基于现有参考PAF的真实CIGAR配对块/MAPQ/identity，不拿比对跨度填补I/X空洞，不重跑比对。
  本例原始FAI共38267条，长N区间metadata为空；诊断得到2155+33724=35879条partial query，
  总长31625089260bp，与当前补充任务实测完全一致。先前“partial_source范围扩张”获得实数支持。
  >=100bp未覆盖区间合计6039640131bp；各加1kb上下文为7296994757bp、10kb为12535595342bp、
  100kb为27581766179bp。上述是未额外长窗口分块的尺寸，不是时间倍率或实际mapper内存保证。
  最长ptg000049l的289508469bp在该筛选下全部未覆盖，单纯加flank不解决此类超长查询。
  源码、原始摘要与scheduler终态存入incident-tools的partial_coverage_sizing.py及
  partial-coverage-sizing-20261121.json；探针对真实production解析器的随机双链CIGAR差分测试通过。
- 生产源码先修复一条确实漏掉的复用链：unplaced和partial补充PAF成功后，把已观察到配对块的
  source pair纳入known_pairs，再规划后续missing-neighbor任务。空/仅indel记录不算成功关系，
  split和out-of-group显式补充仍保留，失败/未完成PAF不能进入此链。不是跳过全部后续任务。
  修改q0_catalog.py、q0_preparation.py；新增两项回归检查实际调用链及不误删显式任务。
  当前远端进程早已加载旧代码，**此修复尚未在远端生效**。
- 新增q0_query_windows.py作为隔离候选，尚未接入_supplement/默认生产执行：候选触发阈值为
  partial query总量>=1Gb或最长>=20Mb；保留>=100bp缺失core、两侧10kb上下文，core上限1Mb。
  相邻缺口共用上下文，长core带上下文分块，末尾不足100bp的分块尾巴仍保留；不删目标染色体。
  PAF严格校验后回投原segment坐标，正负链都使用forward query偏移；CIGAR和完整原序列保留。
  仅context命中/原segment自身命中不变成donor证据，indel跨度不能假装覆盖core。
  此路径改变比对上下文，不能声称与整段原算法完全无损；没有放宽跨组装种子/比对阈值。
- 定向测试：q0 windows/preparation/admission/evidence/paths共131项通过（14.564秒），
  覆盖诊断另3项通过（含>1800个production CIGAR双链差分）；本地真实minimap2 2.26-r1175
  的小型正/负链、分块接缝控制保留全部指定core配对覆盖。不是远端2.31性能或全小麦验收。
- 隔离真实试验43000618 RUNNING，agent-X86-25，8CPU/80GiB，14:37:31开始。
  目录`q0-partial-window-pilot-20261121-1440/`（目录标签不是实际开始时间）。
  pilot.py SHA `093235a7b7b7f3d76eea2d3b12aa8c3565771ab139c087619e34dda51ed39943`；
  window helper SHA `c6b26d90f0a2d3f8367bf551eb937c1582b8b53a43375fce6e6117b30e183b05`。
  对最长289.5Mb实际query选择首/中/末三个窗口，索引只写私有symlink旁边，读取完整selected
  segment核对当前command的成员SHA，再对原32GB目标运行同一个2.31-r1302、原asm10/flags。
  14:40:43已进入mapper；显式64GiB地址空间上限、900秒mapper诊断预算，仅作用于本pilot。
  超时只终止本pilot新建进程组，不动主任务、不接纳partial PAF。不以pilot成功冒充主任务receipt。
  需继续查scheduler终态、完整四个target index分区、最终raw/projected回执和RSS；不要重提仍活着
  的pilot，不能将安静日志/一次SSH超时当失败。主observer3770106仍至约15:41有限窗口。

下一步（未完成，不能据上述局部测试结案）：
1. 收取真实pilot证据，核查保留的跨来源命中/成本/内存；必要时补代表性缺口与长重复区对照。
2. 窗口路径需要实际接入partial request的精确未覆盖坐标、分片/资源预算及不同执行身份；
   同时更新receipt/manifest验证和独立下游读取，保留raw PAF与变换来源，不把window结果冒充native。
   核查已有完整native补充结果的优先复用；缺失部分才算，旧成功结果不改名或删除。
3. 续跑前还应审查catalog的query/target区间累积：add_pairwise_candidates目前为每个hit/anchor
   累积大量重复Interval，末尾才union。可评估精确的分批union降低整理时间/驻留内存；不能删证据ID
   或把跨gap hull当覆盖。首项receipt到第二项命令约7.5小时只是阶段间隔，尚不是该函数独占耗时证明。
4. 当前native-fair plan有native_previous，禁止盲目再套revision链。只改未完成q0工具有希望保留
   同一controller/reader，但必须实际检查调用者、输入指纹和独立消费者，不能仅凭“后续步骤”热替换。
   已查原memory-resume receipt.runtime_files只列self_alignment_batches的两处、assign_chr_groups、
   lgz_prepare_inputs；这不是其他绑定不存在的证明。先备份/SHA/真实冻结模块回归，再受控停止新版、
   确认子进程/正常锁退出并续跑。旧版不动，不跑update.sh/发布CI/重prepare。


### 2026-11-21 15:45 定向优化续接：窗口预算结果、精确区间union与候选选择对照

**目标仍active，优化尚未部署到两项主任务；不能用以下控制测试/隔离作业宣告已提速。**

- 1Mb窗口试验43000618 FAILED，14:55:44结束：900秒mapper诊断预算耗尽，首个target part
  尚无mapped完成行；峰值32669MiB。100kb同位置试验43002943 FAILED，15:13:09结束：
  900秒内完成两个target parts，进入第三个但未完成全部四个；峰值33534MiB。
  不是主任务失败或OOM，不接受任何partial raw PAF。两者final-job.json、timeout凭据、日志和
  原始partial输出都保留；紧凑事实在window-pilot-outcomes-20261121.json。缩短窗口本身不足以
  证明全量可用，不能因局部单测通过就把1Mb/100kb方案直接接上32GB主计算。
  100kb试验目录q0-partial-window-100k-pilot-20261121-1456，pilot.py SHA
  0a116d00b424d06e576789c8645c560df17ad19ae96feb50276b63508ab3598b；旧window helper
  均为c6b26d90f0a2d3f8367bf551eb937c1582b8b53a43375fce6e6117b30e183b05。
- 已实现精确区间union优化，同时覆盖build_catalog和add_pairwise_candidates两处：
  重复geometry分批合并，保留全部evidence/anchor ID；不跨真实gap合并，不删阈值外的数据。
  如果区间持续不相交，buffer阈值随已保留union增大，避免反复扫描大集合造成平方级工作。
  同时不再为每个block反复构造setdefault的空字典/list/set，仅保留MAPQ最大值，保持None/0/255区别。
  新增4项回归含10万不相交区间、随机反序输入、重复证据全部保留和MAPQ边界。
  控制对照每种3轮交替运行，完整catalog payload SHA逐轮相同。reference模式中位4.082→2.827秒、
  进程峰值185320→25284KiB；pairwise模式3.305→2.957秒、109380→22100KiB。
  这是本地Python3.12.3合成重复CIGAR对照，非远端小麦整流程倍率。baseline ba6d9cba，
  old module SHA3db9b93fd026496c64a41580206a96a3bd3743e9ffe668010af04d7db571465b，
  new module SHA523b999ec6c69bebaa3223a4a237dd2d1097149356e4d8484ad9140920423e13。
  复现脚本catalog_union_benchmark.py，结果catalog-union-benchmark-20261121.json。
- 额外覆盖诊断43003112 SUCCEEDED，15:04:33–15:07:17，计算162.444秒、峰值738MiB；
  目录q0-geometric-coverage-diagnostic-20261121-1506，sampler SHA
  eebd37f5c8d50d2b030df07716e3fbd2d4ab10d95fa0f6f2da3a02bc85674f00。
  仅作诊断地将MAPQ阈值降到0并包括255，仍要求identity>=0.90的实际M/=配对块：未覆盖量变为
  3968712740bp（原严格覆盖6039640131bp），10kb上下文未分块尺寸11549581880bp。
  longest ptg000049l原assign为3D、98.489%参考支撑；严格筛选把全289508469bp都请求为partial，
  此几何诊断则只有4929703bp、4401个>=100bp空洞，最长空洞364967bp。
  这区分了“没有比对”和“已有比对但未通过置信度门槛”；不能把MAPQ0/255提升成可信定位。
  生产DISCOVERY_REFERENCE_MAPQ/AdmissionPolicy尚未改变；该宽松诊断不是新科学策略的许可或验收。
  只改变覆盖筛选仍会选择33414个whole query、约31.545Gb，不能冒称它单独解决整段重算。
  原始摘要在geometric-coverage-sizing-20261121.json，参考PAF SHA与前次严格诊断相同。
- 依据minimap2 v2.31原始minimap2.1/options.c核查：-P保留全部chain，不做primary选择，
  此时-p/-N不生效。不能只在保留-P的命令末尾加-N就声称已限制候选。
  旧版initial-reference的approximate_reference_cells用native_window_selection而非全链保留；
  server_alignment等入口明确initial_reference_asm10_only，不能直接绕过scope拿来运行q0。
- 正在做两个独立、完整原结果可对照的实验；均针对已成功的首项q0-map-8024dde83cbf20e7ffa6d8ee
  的150查询/原target，不再重跑原参数。基线原mapper19062.863秒、32threads；候选都是8threads，
  因此时间/内存对照不是纯参数倍率。生产跨组装策略不自动扩展，两个实验都scientific_acceptance=false。
  * 43003122，q0-supplement-seed-f001-pilot-20261121-1515，15:22:19 RUNNING，15:24:35进入mapper；
    仅增加-f0.001，原-P保留。首次mid_occ=461（原500）。script SHA
    f842147a0bc939ddc4f5492806e4b811bcc0b55a66d2147ff1675afeb006d341；geometry helper为eebd37f5...。
    1800秒仅mapper诊断预算，64GiB AS、8CPU/80GiB；预计预算到15:54:35，实际以日志/状态为准。
  * 43003161，q0-supplement-secondary100-pilot-20261121-1541；8CPU/80GiB、64GiB AS，1800秒mapper预算。
    删除-P，显式-p0 -N100，保留-D/--dual=yes/--no-long-join和原seed/preset，不混合-f调参。
    script SHA7bbbf49394722368f214b405be2bdc2398d10478f4bbf6f4b48cd4609c30884a；geometry helper同上。
    必须刷新scheduler确认真实运行/终态；提交成功不等于试验完成。
  脚本replay_supplement_seed_pilot.py会核验完整native receipt四项输出SHA、真实FAI、工具身份；
  完成后流式比较identity>=0.95且>=100配对bp的M/= query覆盖和有方向query-target-strand集合。
  输出每query原覆盖保留量与原配对集合保留数，不能把全局query覆盖保留冒充所有竞争定位/最终正确率。
  新增6项参数/指标回归，显式验证保留query覆盖但丢失替代target时仍报告配对损失。
  两种candidate代码均只写隔离目录，超时只停止本实验进程组；不能伪造main success.json。
- 已修正window projection候选的置信度边界：不把窗口局部MAPQ/primary标签/chain score套到
  原整段source身份。投影MAPQ=255，只保留原cg/NM/nn及qw来源标记；原raw PAF必须单独绑定保存。
  小型真实minimap对照同时覆盖-P和-p0/-N100，保留所需正负链core；这不是小麦竞争定位验收。
  因而当前仓库window helper已不同于上述已结束窗口试验的c6b旧SHA；不要谎称新helper已通过远端全量。
- observer3770106完成181轮后自然退出；核实PID/最后样本及两个主job实时RUNNING且无>90%内存
  告警后，续接PID1470693、PPID1。目录wheat-observer-20261121-154150，log
  logs/wheat-live-20261121-154151.jsonl，源码SHA
  abf4895be8a97acd808785a9c92715554ff51e5f1a712827ee26715154adaf14。
  仅把range(181)改为range(2881)，30秒一次，正常窗口约至11-22 15:42，遇告警仍提前结束。
  这是只读长窗口，不自动修复/向聊天通知。launch.json式凭据实际名observer-launch.json。
  /tmp/wheat-detached-observer-poll.py已更新到新路径，保留已核查任务ID与其他告警条件。

部署前的重要新确认：
- self_profile_evidence_reader.prepare生成的declaration包含scientific_builder_identity；当前
  metadata/incident_q0_routing_reader.json已有旧值。即使只改q0代码、不改native plan，直接重提也会
  因旧declaration与新builder不同而失败。不得删receipt或忽略其一致性检查。
- 需要显式、持锁的builder/reader声明迁移：备份旧runtime和旧declaration，核对旧builder来自实际
  旧源码字节；仅允许列明的q0模块/策略差异，原self/cross配置、全部已完成产出和launcher保持不变；
  生成新declaration并把迁移凭据绑定入新q0 evidence输入/最终报告。独立reader/consumer也要验证。
  native-fair仍不支持任意revision链，不能为此盲目调用旧stager或伪造module.__file__。
- 大parent进程目前约120GiB RSS；不要把小pilot的preexec_fn直接照搬到主进程来设64GiB AS，
  fork时可能已继承超过限制的地址空间。可复用独立guard进程模式，exec清掉parent映射后再设限制。
- 候选窗口路径尚未接入_supplement、receipt/manifest/cache验证。需要区分raw mapping与投影身份，
  让投影/校验小修复能复用已完整提交raw，不冒用原native缓存；已完成native补充优先复用。
  还可优化_initial_inputs只需known_pairs却构造全部PafAlignment/CIGAR对象的路径，但必须保留
  每行完整CIGAR几何、名字/长度和输出内容核验，不能因为已见source pair就跳过后面的非法记录。

## 2026-11-21 17:25 接续：停止同类参数盲调，量化已有覆盖与候选范围

- 本节是带时间的快照；NEW 42949582、OLD 42523432 未修改/重启。17:24 observer 两项仍
  RUNNING，新版 q0_evidence、初始1364/1364；内存293038MiB/327680MiB，约17.94核。
  17:19直接检查第二补充 q0-map-a6056c2d8fcb81f6ca19d1a7，仍仅完成首个索引构建，
  result.paf.tmp=0；不能把 CPU 活跃说成完成，也不能据此给可靠的整体剩余时间。
- 前节43003122/43003161的RUNNING已过期：分别于15:54:38和16:13:20在明确1800秒
  mapper试验预算后失败退出，未完成任何target index part。峰值35902/35057MiB，
  不是OOM，也不是主任务失败。两项原始final-job.json、pilot-timeout.json保留；
  仓库supplement-profile-pilot-outcomes-20261121.json记录终态。结合先前两个窗口试验，
  四项mapper试验均无完整成功结果，不接受部分PAF、不宣称候选保留率或生产加速。
- source_part_lookup.py通过已完成首补充spec.members中的sequence SHA、原dataset/FAI
  以及当前全target FAI的长度提示，重算规范q0-source-part ID并唯一匹配，恢复38267条
  整段source的dataset/contig/length；不是按长度猜身份。59805次hash尝试，无DNA扫描。
  结果目录q0-source-part-lookup-20261121-1600，lookup SHA
  2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89；
  脚本SHA d4856f7c6fb3d3a364ab33abe5774ea73d0e45293c4c04c69377091aab61e797。
  标签恢复不等于重新验证source DNA，也不提供定位置信度；拆分或不完整inventory必须失败。
- 候选范围诊断43005051成功，目录q0-candidate-scope-diagnostic-20261121-1615；
  16:32:40—16:33:50，峰值79MiB，reference PAF SHA核验通过。按染色体组累计整source长度：
  原assignment 30,372,872,267bp；全部reference candidates 515,439,624,122bp；
  原分组加identity>=0.90、已知MAPQ>=20且单hit>=100 M/=bp仍449,942,513,615bp。
  原始摘要candidate-group-scope-20261121.json。它是跨组重复计入的潜在whole-source范围，
  不是真实新增DNA、已做的计算量或实测运行时间倍率；还未计pairwise discovery扩张。
  只用强hit筛选whole-source membership不能解决局部支持被扩展为整条contig的问题。
- 精确区间集合优化覆盖reference和pairwise catalog两条路径：buffer自适应压缩，已有union
  完全包含的新区间无需再次入buffer；保留全部evidence ID、真正空隙、MAPQ None/0/255区别。
  catalog_union_benchmark.py的三轮交替、独立进程合成对照，完整catalog payload SHA一致：
  reference中位4.851→1.920s、peak188620→25208KiB；pairwise3.483→1.707s、109248→21612KiB。
  最终q0_catalog.py SHA e6f9b81b8dfe0dbb226d8d3dbc842185e44ac25c65231d7bd4af1399c2102a16。
  原buffer-only试验及补丁嵌套保存于catalog-union-benchmark-20261121.json，不覆盖历史证据。
  这不是整套小麦倍率，尚未部署。194项q0定向测试完成（1项skip）；本轮额外诊断工具
  15项测试通过（已有cross覆盖5、profile6、source lookup3、candidate scope1）。
- 新诊断measure_existing_cross_coverage.py只读22项完整initial cross PAF加完整首补充，
  验证成功checkpoint/receipt中的PAF完整SHA、大小与前后stat；扫描每行CG/名字/长度，
  即使低identity/重复source也不跳过几何验证。以不同dataset、identity>=0.95、单hit至少
  100 M/=bp作实际双侧覆盖，精确扣减严格reference遗留>=100bp孔洞。不把X/跨度hull当覆盖，
  不用MAPQ把它升级为定位证据，不采用在跑的第二补充partial。结果仅用于选择下一步工作，
  不是生产cache验收/唯一定位证明；source DNA不重读，reference基线来自先前有SHA的诊断。
  * 43007242，q0-existing-cross-coverage-20261121-1735：17:21:20退出，诊断脚本误假设
    最早strict摘要已有后来新增的MAPQ字段；未扫描PAF，主任务不受影响。原脚本/日志保留。
  * 已修正为只兼容精确SHA f63d361d... 的旧strict producer，不对任意无标记摘要放宽。
    增加完整临时workspace/receipt端到端测试以及同尺寸PAF内容漂移拒绝测试。
    43007245，q0-existing-cross-coverage-20261121-v2，17:23:54 RUNNING，1CPU/8GiB，
    同x86环境以保持受控诊断一致；script SHA
    db064ec14e2241cce5f31e7d8639740493f4bd3411a0393fe1050633154db598。
    17:25已扫描完22项initial cross，正在首补充PAF，尚无最终summary时不得宣布成功。
- 下一步先读这个诊断的完整summary及residual-coverage.json，按实际剩余区间决定复用和
  query/target双侧局部化方案。不要再启动同类全32Gb-target的参数试验。生产切换仍须遵守
  前节的builder/reader声明显式迁移；不能简单复制代码后重提，不能清旧receipt。

## 2026-11-21 17:38：已完成覆盖扣减核算，局部目标首次通过真实mapping试验

### 完整已有证据覆盖核算

43007245于17:31:04 SUCCEEDED，运行427.854s；扫描22项完整initial cross及首补充
7,129,991行，逐文件完整SHA与成功记录一致。摘要existing-cross-coverage-20261121.json：
严格reference待补充区间6,039,640,131bp，减去已有合格cross双侧真实配对覆盖后为
2,319,791,151bp（其中Hifi410,109,446，Flye1,909,681,705），约61.59%的原区间已有覆盖。
仅initial cross后残余2,327,423,110bp，首补充再减少7,631,959bp。
残余source数量1179 Hifi+30799 Flye；若仍取整条source则需18,569,109,697bp，所以
仅删已完全覆盖source而继续整条重比对仍浪费；必须局部化，不是再改一个mapper参数。

原289,508,469bp的JM19_hifiasm:ptg000049l，扣减后17段共898,616bp，最大孔洞：
[51382261,51827674) 445,413bp；[160451708,160637412) 185,704bp；
[160343284,160451467) 108,183bp；[128161634,128201675) 40,041bp。
这是实际配对覆盖的复用口径，不证明所有其他target关系已发现，也不等于最终唯一定位/准确率。
若生产跳过已有覆盖区间的进一步全局发现，仍要如实声明其潜在新增关系召回取舍。

### 局部目标规模与成功试验（不同于四个全目标超时试验）

- measure_local_target_scope.py在计算节点读取原reference PAF，按同三处100kb core、
  10kb query context定位reference配对区间，再取所有相关source的实际局部区间，
  source/ref各10kb上下文；保留identity>=0.90的所有参考候选染色体，包括未知MAPQ。
  不把whole-source membership作为目标范围，不读DNA、不伪造source-source PAF。
  显式排除原ptg000049l自身（不是仅不同window ID就允许同ctg自比对）。
- 43007257，q0-local-target-scope-20261121，17:31:51—17:32:29 SUCCEEDED，37.182s。
  script SHA 7c2ad6c36bfb8b07b4bc69fb57fe19df9ba945b7b0f97fc36ae4cb6c291e35e3。
  参考PAF的完整SHA与前次相同。三个core分别0、145000000、289000000；局部target为
  3,378,269 / 3,299,084 / 3,183,945bp，各108/88/90条source、133/114/124个窗口；
  对应whole-source总长分别约3.47/3.14/3.89Gb，全原target约32Gb。
  摘要local-target-scope-20261121.json；远端local-target-plan.json SHA
  4cfee244371cc2e6d5862d9b20a2ccb7f149bd13e2ac1c3ec95ea033f1b000f6。
- 43007259，q0-local-target-pilot-20261121，17:36:12—17:36:30 SUCCEEDED。
  script pilot_local_target_windows.py SHA
  f4ea2b9738031f824fb23bb080ad52cd841efc780cd7c046ef200807c5e2b388。
  helpers db064ec14e.../eebd37f5...，相同x86 minimap2 2.31及cb7e8f22...二进制；
  保持-c -x asm10 -D -P --dual=yes --no-long-join，2threads、2CPU/8GiB申请，
  每mapper AS4GiB、300s诊断预算。未使用-f或-p/-N新参数。三项均真实exit0：
  * core0：3.484s，433 raw PAF行；原cross 99,999配对bp，精确坐标保留99,999。
  * core145Mb：6.183s，851行；原cross 100,000配对bp，保留100,000。
  * core289Mb：4.279s，486行；原cross 100,000配对bp，保留100,000。
  原cross比较键为target原part、strand、paired-coordinate diagonal和core query区间，
  不是只看query覆盖或同名target；移到同target其他重复位置不会冒充保留（新增回归）。
  原22cross的SHA重核，窗口提取按原FAI逐字节读取，保存每window SHA及raw PAF SHA；
  source FASTA前后stat不变，但此pilot不声称重验全部32Gb DNA内容/达到生产cache验收。
  FAI提取测试覆盖跨行、CRLF、大小写；坐标测试覆盖正负链与错误重复定位。
  摘要local-target-pilot-20261121.json；所有FASTA/PAF/输入列表只留远端隔离目录。
- 这三个位置是此前同位置全target 100kb试验的匹配区，不是真正未覆盖孔洞；此前8threads
  三query全target900秒未跑完，而现在2threads局部target三项各数秒，只证明局部化路线
  在这三个已知区间可行，不能外推整套小麦倍率/所有全局替代位置保留/最终科学正确率。
  raw window MAPQ仍不是原whole-source MAPQ，不能直接写进生产身份。

### 下一步关键路径（不要重复已完成试验）

1. 针对上面三个真实大孔洞验证局部发现，不能拿三个已匹配core替代未覆盖区间验收。
   当前planner只投影query自身已有reference M/=块；真正孔洞可能没有这样的块。
   需要独立、显式的邻近anchor检索上下文（例如先保守测量source ±1Mb对应的reference区域），
   但mapping query仍只取100kb core+10kb上下文。多染色体/不一致flank/no-anchor不能默默丢掉，
   必须有可审核的扩大搜索或其他回退、完整source保留和未穷尽搜索标记。
2. 当前pilot要求原cross core对照>0；真正残余孔洞按定义可能为0。不要删除这一断言来伪造
   “100%保留”。给缺失区间试验独立scope，绑定residual-coverage.json、确认core确实落在孔洞内，
   报告新增配对覆盖/无结果，而非不存在的native保留率；保护原完整证据。
3. 真正孔洞也验证后再接入生产大数据自动策略、query/target双侧投影与raw/projected分离缓存，
   明确科学取舍和回退。初始参考、1364完成批次与首补充必须原样复用。
4. 按前文reader/builder声明迁移门禁做小范围续跑切换，不能直接覆写五个builder模块后重提。
   新旧主任务截至17:33都仍RUNNING，完全未改；本轮只成功了隔离试验，尚未部署到42949582。
   先核实主任务是否已有新的成功产物再决定切换，不丢弃后来完成的有效结果。

精确union与前述诊断提交50229c18已推送master（[skip ci]）；本节新脚本/摘要继续按任务文件
定向提交，不触碰其他会话笔记/output，不发布Release、不update.sh、不替换整套runtime。

## 2026-11-21 18:40 接续：真实残余区间已完成 CIGAR 试验，生产接入仍未开启

本节替代前节“只测过已匹配core”的状态。OLD 42523432、NEW 42949582仍未改/重启；
不是生产完成。所有新job都在隔离目录、同一x86工具环境；所有无CIGAR输出仅供诊断。

### 真正孔洞与范围控制

- 43007272，q0-residual-regional-pilot-20261121：17:44:27—17:45:15 FAILED。
  选ptg000049l真实residual中的三个100kb core：51382261、160451708、160343284。
  将source邻域±1Mb全部映射到参考，再加100kb参考上下文、桥接2Mb参考间隙，造成
  447.6/517.8/538.0Mb target；触发100Mb试验输入预算，在启动mapper之前停止。
  不是OOM、不是主任务失败，也不是把预算直接取消。scope摘要已归档。
- 改为每个候选chr/strand分别选最近左右flank，保留相同距离的所有候选，不只选原分组。
  一致方向且距离相容的flank才生成搜索包络；不一致flank仍分别保留，不强行连成大包络。
  包络仅选择mapper输入，绝不是已覆盖区间或真实比对。query仍100kb+10kb上下文；
  source anchor检索±1Mb，reference/target上下文10kb。范围缩到12,222,116 /
  17,724,628 /15,844,054bp。三个区间分别有1组相容flank；另外9/13/12组不相容flank，
  它们的独立搜索窗口保留，但不能将其解释为生物学邻接或唯一定位。
- 43007279，q0-residual-nearest-pilot-20261121：17:57:44—18:03:32 FAILED，首个
  native -P/-c mapper在300秒诊断预算后退出，peak748MiB。首个12.2Mb target索引仅0.88s，
  mid_occ=337，之后未完成CIGAR；没有完整PAF可采纳。
- 43007289，q0-regional-secondary100-pilot-20261121：18:07:21—18:12:50 FAILED。
  去掉-P、显式-p0 -N100，原三个匹配控制样本完整通过，连>=100bp的regional精确配对
  坐标也都保留，但第一个真正孔洞仍300秒预算失败。不要继续把-N当作这处瓶颈的解药。
  完整control报告独立保留，未把缺失区间partial当基线；FAILED是该隔离job的终态。

### 已用消融定位：昂贵的是弱链的碱基层延伸，不是找候选链

- 43007294，q0-regional-chaining-diagnostic-20261121，18:14:41—18:14:44 SUCCEEDED。
  相同第一孔洞query/target输入逐window序列SHA核验，相同2.31-r1302 cb7e8f22...二进制，
  只拿掉-c并用1线程，完整chaining仅1.195s；approximate.paf=1,337,984 bytes。
  这份PAF没有cg，永远不能进入q0 evidence或冒充完成的精确比对。
- 43007318，q0-regional-chain-statistics-20261121，18:26:33—18:26:37 SUCCEEDED。
  读取完整chaining输出：12058条候选链、13个target window。按s1链得分门槛：
  40→12058条；200→1990；500→244；1000→55；2000→6（一个target window）；5000→1。
  原始摘要regional-chain-statistics-20261121.json，PAF SHA
  2c9f529d8accfe86f82eca6116292e156eebbb110372100a770d5c9fd33501dd。
  无-c时的matches/span只是估算字段，不能当真实base identity套用0.95准入门槛；
  最强链s1=26338、span37354，其估算比例约0.705，不能据此认定真实同一率低或删去。

### 成功的真实孔洞候选：保留-P，仅增加-m2000

- 43007334，q0-regional-score2000-pilot-20261121，18:37:00—18:37:16 SUCCEEDED。
  pilot_local_target_windows.py SHA
  06e9c730fa13ab13c705e8719a5d6fc10b0ce6c01d687782acb571ac96f2612e；
  nearest scope helper e4f7153c432c55ff0010018c07b84045c9d8695c614fc3af0185b4ef2937af7b。
  2CPU/8GiB、每mapper AS4GiB，真正执行-c -x asm10 -D -P --dual=yes --no-long-join
  -m2000 -t2；不叠加-f或-N变化。仍有独立300秒诊断预算，不是生产统一超时规则。
- 先跑原三个control，完整initial cross精确坐标都100%保留；对已成功regional -P基线，
  >=10000bp/hit且identity>=.95的配对坐标/原source-strand关系也都100%保留（1/6/2对）。
  **不是无损**：>=100bp/hit的regional配对坐标仅保留366591/514788、295474/390067、
  110054/163639；source-strand关系24/54、30/45、2/34。明显减少短的附加/多重命中。
  不可将这些比例当最终准确率，也不能把这个profile无差别推广到普通/便宜任务。
- 三个真正residual core均完整退出、原始CIGAR几何和输入身份验证通过：
  * 51382261：1.425s，8行，合格cross core覆盖27381bp；within覆盖0。
  * 160451708：1.674s，84行，合格cross core覆盖99998bp；within覆盖25422bp。
  * 160343284：1.074s，69行，合格cross core覆盖100000bp；within覆盖22571bp。
  这三个core原completed cross覆盖为0，retention字段正确为null，而不是捏造100%保留。
  新的覆盖仍不是唯一定位/最终补洞完成；后续admission必须照常检查竞争关系。
  摘要regional-score2000-control-20261121.json和regional-score2000-residual-20261121.json。
- 已提交只读自动触发标定43007382，目录q0-cigar-work-calibration-20261121。
  在3个控制+3个真实孔洞的已完成输入上，做无-c的廉价预扫描，记录低seed得分密度、
  长span链的query_span*target_span代理量，区分便宜的正常窗口与弱链DP爆炸窗口。
  这不是实测DP细胞数，更不是base identity；阈值/生产自动策略尚未开启。刷新终态后归档，
  不要为标定重跑完整慢-c基线。script SHA
  2b4e05951e9ed7df989b67dacbf71cad3147a11ead6764c2ba17f8b3ca58ce14，
  phase helper 9f18d717fe07c55d2dfa501b95600b23745e34346d95273a1dbbb31de5a4cc52。

### 已实现的接入部件和一个不能直接上线的索引方案

- q0_catalog新增ObservedSourcePairs和partial_source_intervals：按合格cross真实M/=双侧
  坐标减去已有覆盖，保持普通set语义和原native partial_source_request默认行为；检查原source
  长度和split偏移，保留真正空隙，不用X、同dataset或低identity命中掩盖缺失区间。
  **尚未在_initial_inputs自动启用此collector**，当前默认生产仍是原native路径。
- q0_query_windows新增TargetWindow/project_regional_paf：双侧偏移投影、同segment自比对排除、
  保留原cg并复验geometry，MAPQ=255，去除局部primary/secondary/score，仅增加qw/tw追溯标记。
  不重复应用原source的N切分偏移。原query-only投影兼容；合成真实minimap两链、两profile
  比较实际配对坐标通过，不替代全小麦验收。
- q0_catalog可选regional_factory在已有严格reference扫描内喂routing index，不重新扫描PAF；
  plain/indexed catalog完整payload相同，N切分相对坐标和sealed重开测试通过。
  不把搜索网格/包络写成候选的真实query/reference coverage。默认不调用此factory。
- q0_regional_index.py的100kb稀疏SQLite网格曾做全量只读诊断43007288，18:04:48—18:18:06
  SUCCEEDED。旧候选模块SHA01bf2a0e00979292ce92bd649658c327a1128cd2bff542f22d99b23a09c7ccaf，
  probe SHA280313b160257b056a0b01f869a107a771cd6b60eb1f6abe43a45c694efc983f。
  67,860,323 paired blocks、68,737,740 proposed links、5,581,699去重links，memo避免
  63,156,041重复插入；796.809s，DB183,439,360bytes，SHA
  6ea2508f1a679ff61580e45b3578e4e06b449f78aad371087a927ec2195c9c56。
  六个控制/孔洞的精确计划目标区间都未丢，但网格过度扩大：控制target86–149Mb，孔洞
  458–712Mb，远大于已测的3Mb/12–18Mb。**不能把“无遗漏”当成已满足提速目标直接上线**。
  当前module后加build_report方法以支持catalog单遍hook，源SHA已不同于该remote probe。
- 下一步优先把网格只作候选筛选并精确细化，或改为带原PAF字节offset的record空间索引：
  SQLite R-tree筛选source/query或reference/target范围，再只解析命中记录的真实CIGAR；
  保留最近flank/tie/方向判断，产出与已验证exact nearest plan相符的窄目标区间。
  避免每个window重扫670万行PAF，也避免将整100kb source/ref网格作为最终mapper窗口。
  180环境SQLite3.45.1已验证四维rtree可用（仅空表/一行模块能力探测，无基因组数据）。
  如给read_paf增加offset回调，要保留UTF-8、CRLF/CR、注释/空行的真实byte offset与原record
  identity；默认调用/普通任务不变。caller仍需完整输入SHA和sealed/成功回执验证。
- 208项q0定向测试已完成（1项skip），未跑发布CI/浏览器/整版替换。所有新快路径仍需
  raw mapping与投影独立身份、完整receipt/manifest/consumer适配、精确输入复用与资源预算；
  已完成native补充优先复用，不能把旧结果追认为执行过新profile。

### 切换协议仍需实现；不要为绕过声明更改冻结文件

已读实际resume_native_resources.py：它硬核验work/prepare_q0_evidence.sh SHA等于当前冻结
plan.dependencies.launcher；原read_native_resources.py最终进入self_profile_evidence_reader。
不能直接替换launcher再调用原entry，也不能把scientific_builder_modified=false悄悄解释成
此次科学代码从未变过。原reader-helper的旧声明等值校验必须保留。

可考虑正交的q0科学变更adapter：绑定当前冻结resource plan、真实新entry/reader/launcher、
旧runtime/declaration备份和新source SHA；原始self/cross/profile/checkpoint验证继续交给原
冻结模块，新的q0声明明确scientific_builder_modified=true及差异。正常WorkspaceLock下
安装/迁移，原旧版作业不动；新job资源ready、原新版正常退出/锁释放后才切换。
这是待实现设计，不是已获接受的迁移凭据；不要伪造module.__file__、删声明、改旧计划冒认
科学profile未变化，或盲目给native_previous再套任意revision链。

### 18:49 标定终态与内部触发部件

43007382于18:48:38—18:49:00 SUCCEEDED，六项无-c扫描各0.43–1.22s。
对span>=1000bp、s1/max(query_span,target_span)<0.25的弱链，span乘积累计：
三个正常control分别2.510/3.132/4.223×10^9；三个真实residual分别
220.948/18.856/14.091×10^9。摘要regional-cigar-work-calibration-20261121.json。

已实现但**未接入prepare_evidence默认流程**的q0_cigar_policy.py：需完整、输入绑定的
chaining扫描；仅asm10、reference>=5Gb、query context>=20kb、弱链span乘积>=10^10时
附加-m2000，保留-P；其他窗口保持native参数。它在这六个测量样本中只选择三项residual，
不会为省少量时间把三项便宜control也降档。不是整个dataset一律使用激进参数，也不是让
用户手工判断。原结果复用、近似/精确身份和完整算法回退仍须在调用层接好。
此门槛是当前有限样本的可追溯工作量策略，不保证所有物种/工具版本/窗口都同样表现；
低seed得分密度不能代替base identity或唯一定位。新增4项阈值、普通/小查询/不同preset、
完整性和成本累积测试通过；此前208项q0测试（1 skip）覆盖本轮其余core改动。
另注意QueryWindow helper默认core仍为1Mb；目前真正成功的小麦候选用的是显式100kb，
生产接入时必须绑定实测参数，不能不传policy就拿默认1Mb宣称已经验证。

另已修复raw window身份与core选择耦合：QueryWindow.window_id现在只绑定原segment、
长度与上下文start/end，完整record仍包含cores，留给投影receipt绑定。相同上下文因相邻
core/tile裁剪而重复时合并cores，不生成重复FASTA header；不填平真实core间隙。
因此以后仅变更缺失core选择/投影规则时可以复用不变的完整raw mapping，而不必重比对。
这是新的候选协议，不能将旧私有pilot的literal query/target-n头冒认成新协议执行结果。
双侧投影/窗口/工作量策略/已有覆盖/索引组件最后32项测试通过；旧普通native路径仍未启用
任何区域策略。本轮已完成的mapper候选足以支持下一轮接入，不再重复这些控制样本或全局慢基线。

## 2026-11-21 21:00 后：区域 API 已通过真实数据验证，本地流程已接入，远端尚未切换

### 当前主任务与本轮操作边界

- 21:00:58 调度器快照：新版 `42949582` 仍在 `agent-X86-64` RUNNING，CPU recent
  1396%，RSS287478MiB、峰值300194MiB；旧版 `42523432` 在 `agent-X86-60`
  RUNNING，CPU1596%、RSS86036MiB。两个主任务、安装、launcher、reader 声明均未修改。
- 已完成1364批初始比对、第一补充 `8024dde...` 仍保留；第二补充 `a6056c...` 的
  20:30 快照仍只有0字节 result.paf.tmp。不要把下面隔离probe成功写成主任务已经提速。
- 只取消了已被替代的共享盘索引查询probe `43007951`（20:31:57终止、调度器显示
  FAILED），不是主作业失败；它的完整 sealed DB 和 index-built.json 全部保留。

### 精确记录索引：复用已完成 DB，不重建

- `q0-exact-reference-index-20261121/reference.sqlite`：5867562条合格原始PAF记录，
  1295220736 bytes，SHA `18677df675e1a3c5fe9071d3edcd908215c8a20d2fbba4d5effd39411c0909a3`。
  构建1510.180s；首个probe构建完成后共享盘随机查询长时间低CPU。
- `43008134` / `q0-exact-reference-index-local-20261121` 于20:30:50 SUCCEEDED。
  仅将该DB逐字节复制到计算节点/tmp并验证SHA；六个窗口的 reference_regions 和
  target_intervals 与此前独立精确规划完全相等，omitted_bp均0，查询0.28–1.91s。
  summary SHA `aca20008cb7c1e153db297779f2381b7fdbd071bd6d1f6519095c83ec7ef165f`。
- 新 `q0_reference_index.py` 是记录级Rtree粗检索＋原始CIGAR精确投影，不使用100kb
  网格作为最终mapper输入；read_paf回调保留UTF-8/CRLF/CR的真实byte offset。
  支持N分段的绝对/段相对坐标以及>2^31参考坐标，完整原PAF身份仍为权威。
- 曾尝试为每条记录额外构造 paired-run数组（`43008143`，隔离目录
  `q0-exact-reference-index-paired-20261121`）。六窗口几何仍相等，但未证明提速，
  冷查询观测反而较慢，且不同节点计时不能作严格倍数对照；**已撤回此候选代码**。
  当前core不含该数组缓存，若重访必须先做同节点受控比较，不要因“索引”名字自动采用。

### 区域 mapper/cache/projection API 的真实端到端验证

- 第一隔离API probe `43008128` 在完成选中源序列验证后失败，原因是薄测试包导入
  q0_preparation 时提前拉入整个 outer workflow/缺 contract.py；不是小麦mapper失败。
  已改为惰性加载默认checkpoint manager，并保留模块级 `OuterCheckpointManager`
  注入点供冻结reader替换；probe也在读取14Gb源序列前先导入所需模块。
- `43008133` / `q0-regional-api-integration-20261121-v2` 于20:35:11 SUCCEEDED。
  923条选中原始源序列、14006064823bp实际内容/canonical part验证；不是全数据验证。
  总315.875s，峰值14203MiB，真实大父进程下fresh-exec guard的4GiB子mapper限制可用。
  summary SHA `248a0ab7b16a592edaa286e56355d5641bcde8c123ff695eac34f47622985aba`。
- 三普通control自动保持native flags；API各6.136/10.096/6.466s，原跨组装paired坐标
  99999/100000/100000bp全部保留。三真实residual自动选择 `-m 2000`、仍保留-P；
  API各5.294/5.415/5.762s，cross core覆盖27381/99998/100000bp。
  这些不是最终唯一定位、组装质量或整任务加速倍数。
- 三层缓存分别绑定完整chaining、真实-c raw mapping、原坐标projection。
  改核心core但不改上下文时，禁止Popen的测试仍成功复用raw receipt。完整投影产出后
  可再生的窗口query/target FASTA被清理，完整PAF/receipt/失败输入不作为垃圾清理。
- 近似无-c结果永远不是科学PAF；manifest验证会核验完整依赖闭包和原坐标投影。
  本地ready manifest→未修改的admission consumer也已贯通验证。

### 当前本地自动路线（仍待远端迁移）

- `q0_regional_discovery.py` 已接入正常 prepare_evidence：仅asm10且参考>=5Gb自动触发，
  核心100kb＋两侧10kb；完整初始cross和完整第一补充的双侧M/=覆盖先用于减少重复发现。
  缺口统计不把已有覆盖解释成唯一性或穷尽全部备选关系。
- 若原完整whole-source partial receipt已有效，优先复用，不追认它执行过区域策略。
  无参考目标或目标总量>100Mb的parent保留显式native full-source/all-anchor回退；
  不丢弃、不接受半成品。决定整个parent是否回退后再启动其窗口，避免先做一半再重复。
- 目前mapper池最多4路、每路最多2线程/4GiB地址空间；总线程不超过run budget。
  **尚未实现并行target规划**，不能将线程池误报成所有规划步骤已并行；后续应结合实测
  扩池/规划进程池，并把parent大堆与各child预算分开，不盲目设置32路×32线程。
- partial窗口的全部PAF作为同一发现round流式合并，不能每个窗口重建/排序一遍全catalog，
  也不能让前一个窗口新增的anchor无意改变后一个窗口的科学语义。
- LocalReferenceCache在/tmp构建/查询、将完整sealed DB＋成功身份持久化；续跑逐字节复用。
  **还应把已完成隔离DB按正确输入绑定采纳到该cache位置，不能让主流程重建它。**
- 后续 `candidate_chr` 目前仍是原生 supplemental_groups（策略中明确记录），尚未解决
  先前515Gb累计whole-source扩大问题。不能称“新版后面都已区域化”；在正式远端切换前
  需处理这一已知后续重复范围，以及下面的串行规划开销。

### 更广规划样本与局部PAF镜像

- `43008137` / `q0-regional-scope-coordinator-20261121`：仅元数据＋sealed索引，不读DNA、
  不运行mapper。实际partial策略将31978个residual parent计划成61087个窗口；这是
  **候选区域工作量，不是已经提交61087个作业，也不是整pipeline剩余任务数**。
- 选两dataset的长parent及长度分位点，共46parent/240window。该probe完成1154.803s，
  46个parent均可区域化，无native回退；最长289508469bp的ptg000049l是20个窗口，
  最大目标17899444bp。样本不能证明剩下全部parent同样可路由。
- 此较广样本仍确认共享盘原PAF随机seek造成显著等待：DB已本地，但 `_hit` 读PAF仍共享盘。
  已针对同类I/O问题增加**内容校验过的本地PAF镜像**。原PAF仍每次open完整SHA核验，
  镜像复制后也核验完整SHA；查询期间原文件和镜像都有stat fence，任一变化即拒绝。
  不是跳过原输入检查或把镜像冒充原始证据。
- `43008150` / `q0-exact-reference-index-local-pafs-20261121`：该镜像路径六个精确计划
  全部相等，查询0.243–1.830s，probe总58.238s。`43008151` /
  `q0-regional-scope-local-pafs-20261121` 正在跑相同46/240规划样本；查最新终态/summary，
  不重复提交。早期29parent/151window累计规划154.611s，尚不代表完整终态。

### 下一步优先顺序（不要再重复已完成mapper对照）

1. 核实43008151终态和同样本路由/坐标、CPU/内存；必要时优化串行规划/有保护并发。
2. 精简后续candidate_chr的重复whole-source范围，不能只解决第二补充又留下已知巨大重复。
3. 实现明确的q0科学迁移adapter：保留原resource/self/cross计划与其checkpoint指纹，
   独立绑定新entry/reader/runtime；新声明scientific_builder_modified=true。原冻结
   load_context严格检查调用者，不能传旧caller或伪造__file__来绕过。
4. 新资源ready、正常锁/旧新版children退出之后才安装窄补丁并续跑；旧版不动。
   本轮尚未生成/应用有效迁移receipt，两个主任务仍运行原runtime。

### 21:12 终态补记与当前验证边界

- `43008137` 于21:08:45 SUCCEEDED；`43008151` 于21:11:10 SUCCEEDED。
  同46parent/240window规划结果的dataset/contig/长度/窗口数/route/reason/最大target bp
  全部一致，均无native回退。没有记录全部240窗口的完整target区间逐项对照；完整区间
  等值实测是前述六窗口，不要扩大为240项坐标输出全部已独立比对。
- 共享PAF版本累计规划1123.030s，完整probe1154.803s；本地PAF版本累计规划256.592s，
  完整probe286.132s，峰值3166MiB。CPU平均27%→93%，符合减少随机远端I/O等待的判断。
  前者agent-X86-61、后者agent-X86-18，**不是严格同节点计时**；约4.4倍仅为同样本规划
  观测值，不是因果隔离的加速比，更不是整个小麦任务加速比。
- 本地PAF版本最长ptg000049l的20窗口规划23.932s、最大target17899444bp。
  summary SHA `5276a8f857f6236c227d1415d748432fcbcace9f17ec2472084be05a7f3e8c7f`。
- 237项q0定向测试通过（1 skip），冻结routing-reader的10项测试通过；随后member循环精简
  再通过53项相关回归和7项区域API测试（含新增长度/SHA拒绝测试）。未运行发布CI、
  浏览器、update.sh或整套替换。源码中checkpoint manager仍保留可注入入口；skip-self
  仅在真的请求同dataset不同part关系时拒绝，不应拒绝纯cross窗口。
- 项目另有DEGAP2.0 submodule dirty及会话/output未跟踪目录，均与此任务无关，不纳入提交。

最后源码复核还消除了两处随窗口数放大的校验开销：ready-manifest的source member映射只建
一次；单任务member长度/SHA核验改成每个window单次查找，仍检查全部window，不再按每个
source重新扫整个target列表。partial合并与验证两端都避免重复扫描，并非省略完整性校验。

迁移时额外注意：完整native第一补充receipt.spec.tool.command实际为字符串`minimap2`，
resolved仍是readiness/bin/minimap2、SHA cb7e8f...。**继续保持该调用字符串**；不要为了
显式路径把新reader改成绝对路径参数，否则当前native raw key包含command字段，会导致
有效的第一补充缓存不命中。隔离API probe以绝对路径调用工具，其raw key因此不同；不能
改写旧key或冒认主任务执行来强制采纳这些小probe结果。先保住5.3小时的native结果。

## 2026-11-21 晚间：candidate_chr 去重复与实际缺失 native seed

### 本地接入，不冒称远端主任务已切换

- master起点已由另一对话推进到 `ab6ed207`（DEGAP submodule更新）；保留该提交，不混改。
- 新 `q0_neighbor_requests.py` 用活动区间计数/未选择集合代替密集缺失pair枚举，保持旧版
  supplemental_groups的query集合完全一致。300组随机重叠/间隙/相同source/已知pair与原
  算法逐项对照；10000个密集缺失关系的测试不再枚举约5000万pair。
- 新 `q0_regional_candidates.py` 在大数据路径执行这些请求：合并同一source跨染色体的
  合格M/= query足迹，而不是每条染色体重复整条source；查询只保留参考局部尚未观察到的
  关系。target bitset在读取原始CIGAR之前就排除已完成/不需要的source；同一原始contig
  的N分段不能仅凭whole-source存在某个hit就全部略过。
- 这是显式recall/work-selection变化：仅>=0.90 identity的M/=参考足迹用于额外区域扩展；
  source已有合格锚点时，弱参考独占的其他候选区域不再整条重比对，但所有原始参考证据和
  catalog候选保留。原始任务、初始参考/cross/self参数均不因此改变。
- **Complete native矩阵可含零hit，但绝不代表已覆盖或已放置。** NativeScopes验证实际
  tool/preset/flags/members/完整receipt结构，最终发布再核对所有输出SHA。它把一次完整
  native query×target搜索作为已测试的无序source-part关系，不声称穷尽两个方向的启发式
  mapping。初始近似self任务并不因此被冒认为完整native矩阵。

### 真实上界规划probe发现61条弱参考source

- `43008440` / `q0-candidate-regional-scope-20261121` 完成174.515s。此probe故意不使用
  初始known pairs，且把全部parts当候选target，是工作量上界样本，不是生产完整计划；
  不运行mapper，不声称重新校验全基因组DNA或第一补充全部内容。
- 全部38267parts /31706122489bp；38056有>=.90的M/=参考路由，211条无路由，合计
  18928468bp。已完成第一补充的150条为14974672bp；其余 **61条为3953796bp**。
- 16个source的34个首/中/尾候选窗口：最大target46240603bp，没有触发100Mb预算回退。
  source完整候选window数可到数千（例如82Mb Flye为850），不能把34个样本当剩余数量。
- 重要修正：不能让每条正常长source为这61条分别whole-source回退，更不能为了归并
  fallback key把289Mb query自身加入一个原本只有4Mb的target集合——即使-D抑制自比对，
  建索引仍要付出这289Mb。现在把无路由source放在短query侧批处理完整矩阵。

### seed必须在partial之前，避免两阶段重复做

- 优先探测原完整partial任务缓存（a605...）仍在最前：若它完成且通过完整验证，不再启动
  区域partial或额外seed。无有效缓存时，对“有参考候选但没有合格参考路由”的source先
  做一次完整native seed，然后把真实hit加入候选/双侧已观察覆盖。
- 小麦这一任务正好是61条query→38117条原参考target，target列表与第一补充完全一致。
  `CompletedNativeScopes` 供partial/candidate两端共用；partial仅在所有请求target关系
  已经被完整矩阵测试过时跳过该parent，零hit测试不会修改cross_coverage。
- 候选阶段按已完成矩阵重新计算仍缺的无路由关系，因此后续可能还需初次150条已发现
  source之间的小矩阵；每次成功后重新规划，不能重复150→38117的5.3小时工作。
- `_copy_prepared_target` 允许独立任务逐字节复制已完成target输入：核对receipt身份、
  target IDs、所有target成员SHA、实际FASTA SHA与复制期间的stat fence；不建立指向
  原输入的symlink/hardlink，原始receipt嵌入新command.json。只为重用输入，不挪用结果。
- q0 identity改用现有run_orchestration稳定字节SHA memo，首读仍完整哈希，后续以
  dev/ino/size/mtime/ctime围栏复用；同大小改写再恢复mtime的测试仍拒绝旧摘要。
  已消除最终发布前旧supplement输出变化仍写success的窗口，复用已有最终SHA，不再多扫。
- `_initial_inputs` 只保留reference的名字/长度，仍逐条解析完整reference FASTA，不再
  同时常驻整个reference DNA字典。de novo源仍保留供实际窗口提取；未跳过输入完整性验证。

### 正在执行的生产性独立任务（不是重复完整小麦或超时benchmark）

- **job43008458**，目录 `q0-unroutable-native-seed-20261121`，22:29:56启动于
  agent-X86-53；32CPU/160GiB，fresh小父进程与mapper继承112GiB RLIMIT_AS。
  没有诊断wall-clock timeout。只写隔离artifacts，原新版/旧版工作区均不修改。
- 驱动 `produce_unroutable_native_seed.py`：重新验证61条query DNA，复用第一补充完整
  target输入，不在第二个父进程载入31.7Gb完整de novo字符串。保留tool.command=`minimap2`。
- 实际raw key：**`q0-map-4aafb69f1d98272cd023d208`**。
  私有artifact根：`q0-unroutable-native-seed-20261121/artifacts`；其中task目录仍使用正常
  `grt/evidence/q0_prepare/tasks/<id>`布局。target.fa32088868779 bytes，query.fa4005749。
- 成功后驱动还会调用原生cache-only API验证可复用，并写summary.status=
  `complete_isolated_native_seed`。**现在尚未成功，不能把tmp或存在target.fa当结果采用。**
  若a605成功标记在启动或输入复制后出现，驱动只写deferred状态，须先验证main结果，不冒充
  完成了seed。两种状态都不可仅看调度器SUCCEEDED判断科学任务完成。
- 22:52快照：seed仍RUNNING，CPU recent199%/avg506%，RSS35132MiB、峰值49542MiB，
  result.paf.tmp仍0；首个8013225629bp target index已构建，仍在原生-P比对。
  **它也出现少数query的低核CIGAR长尾，不可把“提交了小query集合”描述成已获得高效执行。**
  后续若持续，针对这个已确认热点处理，不盲目一直等待。可基于已完成第一补充选择少量
  原始whole-query controls，验证全局target下-m2000/温和阈值；不要重复native大基线。
  区域-m2000已验证不等于全局target也已验证，参数变化必须独立raw key/真实flags和明确
  science profile；不能给当前4aaf...改key补写参数或伪装成native成功。
- 两个主任务22:52仍RUNNING：新版42949582 CPU1197%、RSS283653MiB；旧版42523432
  CPU1595%、RSS94829MiB。旧版未动，新版尚未安装/执行本轮q0代码。

### 交接门禁与下一步

1. 先查43008458真实进度；处理原生CIGAR低核长尾，同时推进并行规划和新entry/reader迁移，
   不要把等待这条任务当作停止所有本地工作的理由。尚未做并行规划：当前区域mapper池
   仍最多4路×2线程，不能称已经用满run_all的32线程预算。
2. 完成且验证seed后，按真实4aaf... key采纳到新版缓存；可在正常workspace lock下原子
   迁移完整task目录以避免再复制32Gb，记录原路径、全部身份与回滚路径，不覆盖已有目标。
   保留producer/采纳receipt。它执行native flags，完全不同于只成功了6个窗口的诊断。
3. 冻结native plan的launcher依赖实际在隔离目录
   `native-fair-revision-20261120-1350/plan/prepare_q0_evidence.sh`，SHA69dc8169...，
   不是工作区launcher本身。因此保留原隔离依赖，另立新q0迁移契约是可行路径。
4. 原base entry为`memory-exclusive-20261119/resume.py`，其HERE实际指向兄弟目录
   `memory-resume-20261118`，不能猜receipt在entry父目录。该receipt绑定4个runtime：
   GPM_Server和.prepare_lib两份self_alignment_batches.py、assign_chr_groups.py、
   lgz_prepare_inputs.py；没有绑定lgz_core/q0_*.py。必须保持这4个文件与旧plan不动。
5. 新context应真实绑定新entry/reader，逐项验证原context的cross/self/resource约束并保留
   原plan/checkpoint指纹；不要传旧caller或改__file__冒认新执行是旧entry。新reader声明
   scientific_builder_modified=true，旧声明先备份再在正常锁内明确迁移。
6. 本轮259项q0定向测试通过（1 skip）；没有发布CI、update.sh、整版替换或main切换。

## 2026-11-22 00:07 CST：新 q0 入口预检、全目标快速参数对照与缓存待采纳

### 已完成的真实试验，不等于主任务已切换

- 全目标 whole-query `-m2000` 对照 **43009156 SUCCEEDED**（目录
  `q0-global-native-score2000-controls-20261121`）。只从已完成 FIRST 原生补充中选取
  同家族的两条完整 query（47,662 bp / 745,038 bp）；没有重跑150条的大基线。
  保留 `-P`，12线程、104GiB fresh AS guard；实际 mapper 979.336秒，完整PAF 6,952行，
  SHA `4523c78aeaebe17ec30f051a3f1eca5bb50add9158e4aa68aa3a8eb61cfa467f`。
- **原精确坐标保留门槛未通过**：两条 >=10kb native 比对的同target/strand/diagonal
  M/=坐标保留率为3.09% / 5.01%。不能宣称全目标参数等价，也不能把这个结果当61条
  缺失query已经测试。`summary.json` 的 `all_long_control_coordinates_retained=false` 保留。
- 为区分重复落点损失与源关系损失，进行无mapper的二次诊断 **43009288 SUCCEEDED**，
  `q0-global-controls-inspection-20261121-v2/diagnostics.json`：两条原有target/strand关系
  各2个，均保留；查询总覆盖各100%；按target的查询边际覆盖约94.96% / 98.66%，
  **target边际覆盖仅23.32% / 80.92%**。这是更粗的诊断，不能替代精确坐标，更不能把
  阈值失败改写成通过。首次诊断43009270因漏传read_paf长度表失败，已定点修正，新增
  使用真实PAF reader的回归测试；保留失败目录，没有重跑mapper。
- **43009293 RUNNING**：`q0-unroutable-score2000-seed-20261122`，针对真正缺的61条
  query开展独立显式参数试验，32CPU/160GiB、112GiB fresh AS，无wall-clock timeout。
  `produce_unroutable_native_seed.py --experimental-minimum-chain-score 2000` 仅在隔离进程
  改变raw mapping flags，真实command和raw key含`-m 2000`；不改main策略、不伪装native。
  成功状态应为`complete_experimental_profiled_seed_not_adopted`，且
  `normal_native_cache_contract_verified=false`、`production_profile_admitted=false`。
  当前默认`CompletedNativeScopes`仍拒绝这一新profile；后续必须明确设计限域自动门槛、
  真实profile与复用契约，不能直接挪进main并声称已采用。原native61任务43008458保留。
  远端producer是纯函数重构前的冻结快照，行为相同但不要冒称其文件SHA等于后续仓库版。

### 新 entry / reader / 安装事务已准备，主任务没有改动

- `q0_science_context.py` 真正绑定新caller，分别验证原native/science/resource来源，
  不传旧caller、不改`__file__`、不篡改原plan；`origin_probe`不能安装或执行新science。
- 只读来源探针 **43009212 SUCCEEDED**，137秒；44 self operations / 876 eligible native
  batches。`q0-science-origin-probe-20261121/summary.json` 确认workspace未改、q0未安装。
  原plan SHA保持`343f1d1933c71d79105405f958b5241887d1fa0f0c936ed1a3d3a70befe039f3`。
- `resume_q0_science.py` / `read_q0_science.py` / `stage_q0_science.py`：正常workspace
  ownership、55-unit/no-DEGAP/CPU预算检查、仅13个lgz_core文件与launcher/declaration的
  显式备份替换、异常回滚、保留原初始比对身份、新reader如实声明science改变。
  这些安装/执行路径目前是定向测试通过，**尚未在main执行安装**。
- **43009226 RUNNING**，`q0-science-transition-20261121-2352`：2CPU/16GiB，只读核验
  q0之前全部25个outer checkpoints。到00:07已通过两条ref及q0_chr:1A/1B/1D/2A；
  不能提前说25个全部通过。使用普通只读OuterCheckpointManager，不调用可能迁移assignment
  的旧ProtectedCheckpoints.validate；不创建Runner、不占main锁、不写主工作区。
  成功应有`validation.json`和`q0_transition_all_initial_checkpoints_verified_only`状态。

### 已完成索引的直接复用已准备

- **43009290 SUCCEEDED**（61秒），`q0-reference-cache-adoption-20261122/ready.json`。
  未重建索引、未重跑参考比对，只复制并核对已有sealed DB、catalog绑定和原PAF内容。
- 待采纳目录位于上述目录的
  `artifacts/grt/evidence/q0_prepare/indexes/reference-index-fdad41a395b84a35a2176f31`。
  DB 1,295,220,736 bytes，SHA
  `18677df675e1a3c5fe9071d3edcd908215c8a20d2fbba4d5effd39411c0909a3`；
  正常cache success.json SHA
  `69b80ca1859b83018376434f803707f396f5c4b304cb10c40e2ab81bd69f9e68`。
  **尚未采纳到main**。需在正常锁内无覆盖原子迁移，记录来源/全部身份/回滚路径；
  正常builder仍须验证真实catalog与原PAF，不凭ready.json跳过内容检查。

### 当前主任务及下一步边界

- 00:07快照：NEW42949582 RUNNING，recent1196%、RSS284012MiB；OLD42523432 RUNNING，
  recent1593%、RSS94314MiB。OLD未动；NEW仍旧q0执行路径。native61任务43008458仍RUNNING，
  已约97分钟，recent199%、RSS35190MiB，不能当成已经高效解决长尾。
- 本轮45项定向测试通过，另有真实origin/context和sealed-index复用验证；不跑发布CI、
  不做update.sh、不整版替换。区域规划仍串行，mapper最多4路×2线程，不冒称32核已用满。
- 下一步核对43009226完整预检、43009293实际flags/结果及43008458进展；完成明确profile
  与缓存采纳门禁之后，才安排实际资源已就绪的NEW正常锁交接。保留FIRST 5.3小时结果、
  初始1364任务和原native plan。不要只提交库/探针便宣称主任务完成优化。

## 2026-11-22 01:23 CST：三块补比对已完整，准备实际 q0 交接

### 新证据与限域策略

- **43009226 SUCCEEDED**，`q0-science-transition-20261121-2352/validation.json`：
  全部25个初始outer checkpoints通过真实只读验证，未改工作区，耗时2317秒。
- **43009293 SUCCEEDED**：61条query/3,953,796 bp到38,117 targets的显式`-m2000`
  raw任务 `q0-map-2b19c2c859bdfb5f2e9177e8`。mapper913.901秒，peak47.594GB，
  进程完整退出、PAF与normal cache-only同profile验证均完成，不是采用tmp。
- 发现61条中9条短于20kb（最短702bp，总123,348bp），不能对它们宣称-m2000的
  negative关系已完成；全部targets中1,427条也短于20kb，需保留原生短target关系。
- **43009370 SUCCEEDED**，`q0-unroutable-short-native-seed-20261122`：9条短query到
  原38,117 targets，原生`-D -P --dual=yes --no-long-join`完整产出；不降低短query灵敏度。
- 剩下52条长弱query与1,418条非弱短target（21,227,900bp）的关系，改向让短target作
  query、52条弱source（3,830,448bp）作target。**43009787 SUCCEEDED**，目录
  `q0-native-short-target-completion-20261122-v2`；原生flags、8线程、24GiB fresh AS，
  mapper260.986秒/peak5.383GB，raw key `q0-map-b30137a13323db8a99874448`。
  前次43009393是32线程/8GiB AS，RSS约6GiB后morecore内存不足、非零退出；没有success，
  保留失败目录。缩小target不自动证明dense-repeat内存小，已同时限制该路径线程预算。
- 已有用户授权大数据精度换速度，不再要求所有重复落点精确复现。但必须保留真实变化：
  全目标-m2000对照两条主要target关系与查询总体覆盖均保留，按target查询覆盖约95/99%，
  替代重复落点明显减少；不是结果等价。内部自动门槛为asm10、reference>=5Gb、target>=5Gb、
  无合格参考路由、query cohort<=8Mb、最长query<=1Mb；近似完成scope仅覆盖query与target
  都>=20kb的关系。小reference、普通有路由query、其他preset和短关系保留原生。
- `CompletedNativeScopes` 现在显式区分原生矩阵和限域近似矩阵；短query/short-target
  negative不能被近似矩阵吞掉；三块真实矩阵补齐后才跳过已测试关系，不捏造coverage。
  完整旧原生cache始终优先于新参数；真实flags进入独立raw key与最终policy/证据声明。
  `POLICY.version=5`；candidate policy version2；普通supplement raw identity仍不变。

### 缓存采纳与实际切换（此快照尚未切换）

- **43009762 / 43009788 / 43010042 均SUCCEEDED**，分别为fast/short-native/short-target的
  正常新API cache-only采纳验证，不启动mapper。ready.json目录：
  `q0-cache-adoption-fast-20261122`、`q0-cache-adoption-short-native-20261122`、
  `q0-cache-adoption-short-target-20261122`。fast有效scope52 query×36,690 long targets；
  所有raw文件身份和真实producer来源仍保留。
- `stage_q0_science.py` 在正常锁内原子移动完整task/index目录，不再复制两个32GB target；
  每个文件先验证byte SHA，核对raw key和receipt，目标必须不存在。runtime/declaration备份
  完成后才动目标；中途失败回滚runtime与已移动cache，记录安装journal，不清理失败目录。
- 新gate `q0_science_handoff_gate.py` 先取得真实单节点32CPU/320GiB allocation，写ready，
  校验原NEW terminal且pids已清空、正常锁释放、scheduler凭据和各来源绑定，才启动新owner。
  gate不杀job，也不删锁；若原a605 whole-partial恰好完整，则拒绝切换，先重新stage。
- 正在stage目录 `q0-science-cutover-20261122-0130`；以其submission/ready/scheduler为准，
  不把目录存在视为已运行。不取消OLD42523432；只在新allocation ready后处理NEW42949582。
  原native61 job43008458仍运行，不能把它的部分PAF当完成，也暂不因新试验快而随意丢弃。
- 本轮275项q0定向测试通过（1 skip），80项incident/reader测试通过，另6项gate测试通过。
  未跑发布CI、update.sh、整版替换。下一步必须实际交接并检查优化后主任务执行，不能以
  提交这些库/测试或资源ready就称完整目标已经实现。

## 2026-11-22 01:43 CST：已实际切换到新 q0 owner，正常检查点复用进行中

- 正式资源ready后，**01:27请求正常终止NEW42949582**，01:28核实调度器FAILED、pids空、
  正常锁已释放，才放行新owner。FAILED是本次主动交接的终态，不是新的科学计算错误。
  原a605 incomplete PAF和日志保留，不采纳tmp；OLD42523432未取消/修改。
- 第一次交接43010044在安装前被入口guard拦截：冻结来源校验合法导入了旧q0 geometry
  helpers，粗粒度“发现任意q0模块已加载就拒绝”与实际调用链冲突。没有installation目录，
  runtime/cache未动，正常锁释放。**没有绕过检查或重新运行比对**。
- 定点修正为新reader的`--describe-only`独立进程：真实绑定的新reader读取真实新builder，
  生成科学声明；parent保留原来源校验已加载的旧geometry对象，不reload、不改`__file__`。
  子进程失败仍触发安装事务回滚，stderr进入定点诊断。新增测试覆盖旧模块存在而不冒认新
  builder、真实子进程argv、返回声明身份拒绝。原initial science/context契约保持不变。
- **当前主任务NEW43010068，agent-X86-43，32CPU/320GiB**；目录
  `q0-science-cutover-20261122-0140`。真实transition SHA：
  `eef0517b215789ffaafc07d779b14ff6b92c0ec673f659f3000545b58a29ff46`。
  正常run ID `20261121T173455Z-2452020-6b3aa1b6`；01:34获得正常workspace lock。
- **installation/receipt.json状态installed**，15个runtime/launcher/declaration目标已精确
  备份并替换，sealed参考索引与三个完整任务已原子移动入正常cache，无覆盖原目标：
  - fast61 `q0-map-2b19c2c859bdfb5f2e9177e8`；
  - native9 `q0-map-a2e519761e94eff6ca09e121`；
  - native短target补齐 `q0-map-b30137a13323db8a99874448`；
  - sealed DB `reference-index-fdad41a395b84a35a2176f31`。
  FIRST802...仍在原处。采纳只是完整cache可用，**尚未声称本轮主q0已消费它们**。
- 01:39:30打印`EXPLICIT_Q0_SCIENCE_RESUME`，进入真正的55-unit Runner；当前是正常初始
  检查点的内容复核，而非重新比对。01:40:30 `ref:JM19_hifiasm`、01:42:04
  `ref:JM19_flye_ABD` 均`SKIP_VALID`；下一步assignment及22条q0_chr的完整复用。
  不因这段校验CPU较低再次中断。旧预检25项通过不替代当前内容检查。
- 01:44核对远端冻结bundle的18份Python源码（13个core+5个入口/迁移工具）与当前仓库
  内容SHA全部相同。没有发布CI、update.sh、完整runtime更新或新Release。
- 旧observer1470693在监控到主动停止的42949582后正常告警退出。临时observer1450366
  发现非TTY stdout不含RUN header后被替换（仅停此只读observer，不动计算作业）。
  **当前observer PID1505606 / PPID1**，目录`wheat-observer-20261122-014110`，log
  `logs/wheat-live-20261122-014111.jsonl`，源码SHA
  `5c0ad2317fbc304d2bc0b3319adfffb8731ea7c5bb0186bc237ab83b49d7130a`。
  从真实`gpm_server/logs/run_all.log`取最后一轮RUN段，避免把旧轮取消行当新失败；
  2881×30秒只读采样，监控OLD42523432/NEW43010068，不自动修复或主动聊天通知。
- **任务未完成**：继续核对43010068，实际进入q0并消费上述三块cache、sealed index、
  开始区域化任务后再评价主流程提速。区域规划仍串行，mapper最多4×2线程，不能声称
  32核已用满。孤立原native61任务43008458仍保留，按真实完成状态决定是否采纳/终止。

### 2026-11-22 02:11 CST：本轮25项全部SKIP_VALID，新q0已实际启动

- NEW43010068的正常Runner从01:39:30开始复核，到02:08:26完成全部25项`SKIP_VALID`，
  包括两条ref、assignment和22条q0_chr；没有重新运行初始mapper。
- **02:08:29 `[26/55] [START] [q0_evidence]`**，真实执行已安装的新reader和q0代码。
  02:11调度器仍RUNNING，child PID2470600，RSS2134MiB，正在启动读取/验证输入。
  四个supplement成功标记（FIRST+本轮三块）及sealed索引在正常cache；尚不能声称主q0
  已逐项命中三块缓存或开始区域mapper，应以之后真实进度/日志核实。
- 孤立原native61作业43008458在替代三块完整、正常API验证通过、实际采纳且新q0启动后，
  于02:10:50正常请求终止；02:11核实FAILED、pids空。原tmp/log/source目录保留。
  其共运行约3小时41分仍未完整结束，不继续浪费32核/160GiB allocation。该终态是主动
  停止冗余计算，不是新版失败；OLD42523432从未终止。FIRST完整5.3小时结果仍保留。
- 代码修复已推送`0dabbde1`、`52f634d5`；后者18份Python源码与实际冻结bundle完全一致。
  对应`source-repository-receipt.json`已写入cutover目录，实际安装15个文件摘要复核通过。
  后续只改交接记录不代表更换运行代码。只读observer1505606继续监控当前新旧主任务。

## 2026-11-22 03:03 CST：定位输入扫描热点；保存跨Python版本验证的轻量解析优化

### 当前运行证据（没有重提主作业）

- 同节点只读诊断 **43010171 SUCCEEDED**，目录`q0-live-phase-20261122-0218`。
  对当前reader PID2470600 / start_ticks649928865，在02:18:37–02:28:38采6次非暂停栈及
  自身`/proc`元数据；不读locals、不改ptrace设置、不发主任务信号。600.558秒墙钟里CPU
  增加591.8秒，VmRSS约31GiB、swap0。经过1B、1D到2A的PAF，读取位置持续推进。
- 栈定位到`run_orchestration.validate_paf`的CIGAR校验，以及
  `q0_alignments.parse_paf_line / _initial_inputs / observe_alignment`的证据收集。
  是已有PAF的校验与关系扫描，**不是重跑参考mapper，也不是已证明卡死**。
  6个稀疏样本只用于定位，不能把命中比例当准确耗时分解。
- 后续同节点诊断 **43010201**，目录`q0-live-phase-20261122-0255`，6次/180秒的有界只读
  窗口；03:03采到`chr_4B/JM19_flye_ABD_vs_self/result.paf`，offset95813632，仍在真实
  `parse_paf_line -> _initial_inputs`；scheduler NEW43010068 RUNNING、RSS33249MiB、recent99%。
  OLD42523432保持运行；没有再中断NEW来追求显示更多并发。

### 新的源码定点优化（已验证，尚未装入这条存活作业）

- 两个相同热点一起处理：`run_orchestration.validate_paf`与`q0_alignments.parse_paf_line`。
  用非重叠正则匹配的总覆盖长度证明完整CIGAR语法，不再为校验而重建整条CIGAR字符串。
  原生validator将同一长度的重复int转换合并；q0保留返回完整operation tuple及C层sum。
  全部M/I/D/N/=/X跨度、边界、记录SHA/evidence ID、输入输出完整性检查保留；不丢行、不
  改mapper参数、不改checkpoint schema或执行引擎版本，也没有关闭任何检查点。
- 不能只信本地Python3.12微基准：首次in-place融合q0跨度循环在本地快，但真实x86
  Python3.10对照 **43010196** 的长CIGAR旧/新比仅0.883（回退）。**拒绝该实现**，保留
  `paf-validator-*-inplace-rejected-20261122.json`及其远端冻结源码/结果，未装进主运行。
- 修正为保留Python3.10的C层sum后，真实节点对照 **43010200 SUCCEEDED**，目录
  `paf-validator-calibration-20261122-0245-v2`。同一输入5轮交替、原生和q0完整返回值相等：
  native普通/长CIGAR为1.231x/1.167x，q0普通/长CIGAR为1.084x/1.129x。
  native长CIGAR的Python分配峰值18361885→9892421 bytes，q0分配峰值基本持平。
  **这只是合成数据的解析函数微基准，不是job RSS改善或完整小麦提速倍率**。
- `benchmark_paf_validation.py`只读提取固定Git revision的旧函数，与候选实函数对比；HPC
  模式使用SHA绑定的旧源码副本，不联网、不用客户数据、不改主环境。local/HPC JSON均保存。
  真实远端contract文件SHA899b629c...与仓库旧文件整体不同，但`validate_paf`、数值解析、
  PafSummary及异常类4项AST逐项完全一致；q0旧模块整体SHA也相同。该区别明确保存在
  `paf-validator-runtime-function-binding-20261122.json`，不冒称整个旧runtime与master相同。
- 新增1200组有效CIGAR、8000组畸形文本等价检查、72001-operation长记录、Unicode/零长度/
  不支持opcode/大整数/跨度错误及记录身份回归。最终21项validator/outer测试通过；275项
  q0定向测试通过（1 skip），没有发布CI、App构建、update.sh或发布操作。
- 当前NEW仍运行**52f634d5对应的冻结q0 bundle**，没有现场覆盖这些新源码。现阶段重启
  会丢掉已有输入扫描进度并再付冷校验成本，局部收益不足以支持这种做法；后续若有其他
  必须重提的修复，再按正常锁/独立transition/精确备份门禁合并采用。

### 下一阶段关注点

- 继续核对NEW实际完成输入扫描、命中FIRST和三块seed缓存、复用sealed index后再进入区域
  mapper；不要将“缓存存在/采纳成功”写成已证明主流程命中。
- 区域规划仍是串行、mapper最多4x2线程。若实际吞吐仍受限，优先评估**小metadata规划
  进程与受限mapper池共享32线程预算**；不要从携带31Gb DNA的父进程fork再套小AS限制。
  必须做真正fresh进程、精确计划对照、当前RSS/硬额度/返回计划余量评估，以及失败保留并
  回退完整计划的机制。不借此放开未经测量的超长原生mapper并发，也不做多节点改造。

## 2026-11-22：区域规划的 fresh-process 并行与同作业资源凭据

### 真实小麦小样本，不重跑完整比对

- 新增 `lgz_core/q0_regional_execution.py`，供部分覆盖补比对与候选染色体两条路径共用。
  owner 保留原有关系选择，worker 只拿源分段元数据/窗口/索引；使用 `spawn`，不复制或
  fork 31Gb DNA 堆。结果按原父序列/窗口顺序消费，有界预取；父序列整体回退决定先完成。
  返回计划过大、MemoryError、损坏的进程池均在 owner 中精确重算；内容身份错误继续失败。
- 同节点、同 Python3.10.12 的第一轮 **43010282 SUCCEEDED**：46个实际父序列、240窗口，
  三进程138.640秒（含委托快照、spawn和退出），串行292.373秒，2.109x；全部坐标/回退
  决定逐父比较一致。结果保存在 `regional-planning-hpc-initial-20261122.json`。
- 加上数据库生命周期/源分段绑定栅栏及真实调度器凭据后，最终 **43010293 SUCCEEDED**：
  同一批窗口，三进程135.722秒，串行275.728秒，**2.032x**。46份有序完整计划摘要与
  第一轮完全一致，且本地38份core源码逐字节匹配这次冻结包；结果保存在
  `regional-planning-hpc-guarded-20261122.json`。远端目录为
  `q0-planner-calibration-20261122-0350-v3`，同节点agent-X86-06。
- 两轮均只读原有元数据和PAF，无DNA读取、无mapper、无主工作区改动。串行在并行之后，
  可能受益于已热的OS页缓存；不把这个约2x说成完整小麦或候选染色体全部场景的提速倍率。
  最终owner峰值300179456 bytes、单个child最大280571904 bytes，scheduler作业峰值
  3592MiB（不同统计口径，不能相加或当成实际mapper峰值）。
- 首次隔离校准包 **43010279** 因缺少 `run_resources` namespace依赖在导入阶段失败；
  未开始基因组计算，也未改主任务。补全真实包依赖，并在提交前分别验证 namespace/flat
  两种导入布局；没有删测试断言、伪造服务器目录或重装主环境。

### CPU、内存与完整性边界

- 32线程、现场内存预算足够时，上限为 **owner1 + planner3 + mapper14×2 = 32**；这不是
  32路各32线程，也不等于已在主任务实际启动14路。owner峰值在池建立时重新测量，不使用
  先前34GiB快照作为永久依据。小预算保留owner CPU；1线程时规划与mapper严格不重叠。
- 规划进程各8GiB AS；mapper仍各4GiB AS，原生全长回退与整个区域池不重叠。预算另外
  预留owner增长、每路提取/解析、预取和展开计划内存。守住限制，不用低RSS样本推断
  长原生任务也能扩池；RSS/AS/作业cache统计仍不是同一个口径。
- 实际Donau进程能看到 `container_<jobid>_rg0_...` cgroup，但标准路径下读不到有效
  memory limit，最终报告的 `cgroup_memory_limit_bytes` 为null，不能据此猜320GiB。
  新gate通过 `_GPM_Q0_SCHEDULER_PROOF` + `_GPM_Q0_SCHEDULER_SHA256` 转交已经核实的
  **当前job** djob JSON；reader自动核对SHA、RUNNING、单节点、主机、账号、CPU/内存及
  自身cgroup的完整job ID。不是用户填内存数值，也没有新增让用户承担判定的命令行参数。
- 最终校准真实交接了当前43010293的6CPU/60GiB凭据；实际helper返回64424509440 bytes，
  与调度器核定值一致。没有有效proof或cgroup额度时仍串行规划、最多4 mapper；显式但
  不匹配的proof则失败，不静默放开资源。普通运行环境不凭节点物理内存扩池。
- PAF/镜像先由正常open/seal完成整份内容验证，worker只继承此次存活owner的内存证明、
  元数据和稳定文件身份，自己开SQLite/文件句柄；逐记录SHA仍校验，不重复全扫PAF。
  数据库在seal/open起即绑定稳定身份，委托前核对分段绑定，worker/owner生命周期均有
  数据库、原PAF和镜像漂移栅栏。此委托不保存成下次续跑的内容凭据。
- 原有区域搜索本身的召回边界不变；本次调度改动不另加精度损失。native/approx矩阵
  关系范围、短序列补齐、窗口/target选择、mapper flags和raw cache身份保持原样。
  新执行器纳入builder identity，不能把它冒充旧builder或热改冻结源码。
- 最终本地 **q0测试287项：286通过、1跳过**，resource-ready gate **7项**通过；真实HPC
  冻结包 **11项**进程/资源/完整性定向测试通过，再完成240窗口校准。没有release CI、
  App构建、update.sh、网站发布或整套runtime替换。

### 主任务仍独立推进，不能把源码完成当作已部署

- NEW **43010068** 仍是52f634d5对应的冻结bundle：本次执行器以及7cbcf887解析优化均
  **尚未安装到这个存活reader**。OLD **42523432**只监控，未改变、未取消。
- 同节点只读诊断 **43010285 SUCCEEDED**，03:52:46–03:56:47由chr_7D推进到chr_Un，
  240.229秒墙钟内reader CPU增加238.77秒、swap0，并非死锁。目录
  `q0-live-phase-20261122-0355`；observer1505606继续存活。
- 后续短诊断 **43010298 SUCCEEDED**，目录 `q0-live-phase-20261122-0420`，04:17:12已看到
  `build_catalog -> prepare_evidence` 读取既有Flye参考PAF（offset813146112）。因此
  **已经离开_initial_inputs**；这是参考证据目录构建，不是重跑参考mapper。reader RSS
  首样本约49.7GiB、swap0；04:18:12第二样本已到offset879910912，RSS约51.2GiB。
  60.075秒内CPU增加59.87秒，完整summary和终态已保存在该诊断目录；主任务未被改变。
- 下一步先核实完成扫描后实际命中既有矩阵、进入区域池的真实任务量/吞吐。若收益支持
  切换，按资源ready、正常锁释放和新transition迁移，保留全部完整结果。新runtime文件
  `q0_regional_execution.py`尚不在旧安装中，需核对installer对“原来不存在”的文件的
  备份/回滚表示；若同时装入7cbcf887的外层validator，还须显式处理既有runtime whitelist。
  不直接覆盖当前15项安装journal，不伪造旧文件摘要，不为了基准数字重启旧版基线。

## 2026-11-22：下一轮 q0 接管准备工具（尚未部署到主任务）

- 核对发现旧installer已经支持`prior_sha256=null`的新文件及失败后删除自有新增文件；
  不应为不存在的缺口重写安装机制。本轮补充了真实“旧文件+新增模块”混合库存测试，
  以及不重写内容相同的runtime、备份完成后逐项重核旧身份、拒绝中途出现的未知新文件
  或父目录软链接。完整备份/已安装库存仍保留，journal另记实际`replaced`路径。
- 新增`prepare_q0_runtime_transition.py`：仅在隔离bundle写新的transition/launcher/准备
  receipt。绑定上一次安装journal、真实reader声明和源码；按候选builder自动收集14文件
  闭包，核对4项科学policy的AST不变，保留原native origin，不重做已经采纳过的cache移动。
  发现源码/声明漂移、未知目标、已发布q0或已有候选输出即停止，不覆盖、不停作业、不改锁。
- 本地安装/上下文/gate/准备器定向测试83项通过；真实master的14文件闭包及4项policy与
  当前52f634d5科学声明相等已核实。这里只验证准备机制，不能当作真实25初始检查点预检。
- 下一包刻意只取q0 runtime闭包及新的入口/门禁，不顺带替换`run_orchestration.py`。
  因此外层contract维持原现场字节，7cbcf887的外层validator暂不部署；q0内层parser与
  并行执行器随闭包进入候选。避免为一项小解析收益扩大旧native provenance/加载边界。
- 04:46调度器快照：NEW43010068仍RUNNING/q0_evidence，79371MiB，recent99%；
  OLD42523432 RUNNING/grt_step2，recent1595%。阶段函数需重新采样；不能把04:18的
  build_catalog栈当作当前栈。两份原参考PAF分别683392866/1061893273 bytes，仅stat，
  没有登录节点基因组扫描或重比对。后续要实际stage候选、在计算节点做25项只读预检，
  再核对区域阶段剩余量/吞吐与资源ready条件，才决定何时正常接管。

## 2026-11-22：合并缓存校验与证据消费，减少无用几何和重复键对象

- 追踪到`_supplement`的完整cache命中原来先独立`read_paf`校验，再由调用者完整解析一次
  收集证据。现在未放置发现、partial之前的弱seed、以及完整原生partial cache支持同步
  `on_cache_hit(task,hits)`：全部输入/输出SHA和spec仍先核对，用同一个已校验记录流完成
  原有消费，并强制读完尾部、复核receipt语义与所有outputs。callback或尾部错误直接失败，
  不在catalog已部分更新后重跑一个耗时mapper，也不发布manifest。无callback的API和新
  mapper成功提交路径仍保留原来校验，未取消任何检查点。
- 检查了同类路径：多路regional partial仍合并为原来的**一次**发现轮次，不提前把某窗口
  新候选变成后续窗口的anchor；candidate阶段只有验证、没有当场消费的cache仍完整校验。
  新原生mapper仍先完成完整校验、原子提交成功，再消费；没有拿不完整PAF当结果。
- `_add_pairwise_candidates`只需要query区间，不再为每个M/=/X构造用不到的target区间和
  AlignmentBlock；新query-only投影保持正负链、I/D/N与原顺序。`ObservedSourcePairs`
  对不产生跨组装coverage的记录只判定是否存在M/=/X关系，不生成无用坐标；X关系仍保留，
  gap-only仍不是关系。跨组装合格覆盖继续逐块精确求并集，边界检查在快速分支之前保留。
- 同一bound source键在关系集合中共享对象。受控64 sources/2016边的值完全一致，边中
  不同SourceKey对象由4032降至64；这不是整套小麦RSS降低倍率，也没有删除任何边/覆盖。
- 本地297项q0回归（1跳过、无失败）：新增完整catalog/manifest的受控双遍/单遍对照，
  不重跑缓存mapper、尾部损坏、consumer错误、输入/工具漂移、500组混合CIGAR双链/偏移
  几何及共享键等价检查。原有语法、跨度、record SHA/evidence ID与最终输出完整性检查保留。
- 真实x86/Python3.10控制 **43010321 SUCCEEDED**，目录
  `q0-cache-consumer-calibration-20261122-052902`。只读取已有小型原生cache b30137...：
  3955602 bytes、12774记录，5轮交替，对照中位数3.703886秒→1.511862秒（2.450x）。
  完整有序记录/CIGAR、query投影、source关系及精确coverage摘要相等，解析遍数2→1；
  共享parser/旧aligned_blocks/interval union与bfc6d7a1基线的AST校验通过。全部新core
  源码与冻结包逐字节相符，报告`cache-consumer-hpc-benchmark-20261122.json`已保存。
  同包10项定向测试通过。读取了约25MB生成FASTA进行内容核验，没有加载整套DNA、运行
  真实mapper或写主工作区。2.45x只对应这个受控记录处理组合，不是整套小麦/大矩阵倍率。
- 当前NEW没有热改。短诊断 **43010314**（目录`q0-live-phase-20261122-050103`）05:02
  已看到reader读取原有FIRST cache8024.../result.paf，offset683032576，栈在`_runs`；
  至少确认主流程已离开参考catalog并实际读取FIRST，而不是只确认缓存被搬进目录。
  不把未显示的3块seed命中或区域mapper启动当作已证实。后续按新源码一起冻结候选；
  不覆写3c57fd10以前已经冻结的文件，仍先预检/资源ready，再正常接管。

## 2026-11-22 06:03 CST：组合补丁已真实stage，25项只读预检进行中

- 候选来自已推送master **ec093edf**（此前准备器/installer修复 **3c57fd10**）。远端
  bundle：`q0-parallel-cutover-20261122-054517`；transition SHA
  `47d3bd36960518a6dcc1c5c8b98bf1b5fd61f6a076a42a3109d1d44e128acc01`。
  通过可信压缩包SHA与全部代码校验后，用实际Python3.10运行了准备器，真实准备receipt
  也存入仓库`q0-parallel-candidate-prepared-20261122.json`。
- 已核对上次安装journal/reader声明/全部旧文件及4项科学policy，列明14个runtime：
  **7个改变（含新增executor1个）、7个内容不变**。新installer不会重写那7个不变文件。
  不重做已采纳的cache移动，native origin、4个原始受保护runtime及外层contract仍不变；
  contract SHA仍899b629ca3d2d2fb2d7e768f3368bd1e94a049d345a571928c09442090ba4ffb。
  `source-repository-receipt.json`核对20份候选源码并记录保护范围；没有安装到工作区。
- 真实只读预检 **43010327 RUNNING，agent-X86-18，2CPU/16GiB**。冻结包83项准备/
  installer/上下文/gate测试已通过；06:02:48实际验证 **9/25** 初始检查点，最近为2D，
  RSS约129MiB、recent99%，`validation.json`尚未生成。这不是失败或卡住，继续查同一job，
  不重复提交、不因一次SSH/观察超时而重启。预检有一小时诊断上限，不是主流程超时。
- **主任务已真正进入区域阶段**。run_all.log记录05:42:18 fast61、05:43:01 native9、
  05:43:14 native1418→52分别完成；结合既有cache/收据可核对其复用，而非仅看目录存在。
  05:51:15完成100窗口，05:57:39完成200窗口，计划列表61000、fallback_sources=0。
  这里是区域窗口，不是61000次全基因组比对；计划列表也不能不扣复用直接当精确剩余数。
  OLD42523432仍运行未动；NEW43010068仍为原52f bundle，当前4×2池、还没启用新执行器。
- 06:02前后只读observer1505606仍存活，NEW内存约90GB（scheduler 90171MiB）、recent
  249%；已有参考/assignment/22条q0_chr仍保留。新的2.03x规划、2.45x缓存记录处理均
  是隔离对照，不是这条存活作业已经获得的倍率。
- **下一步**：先等43010327实际SUCCEEDED且25项完整proof，核对transition SHA/所有
  源码仍一致；再生成该bundle的handoff-config和32CPU/320GiB资源ready作业。新allocation
  已ready后才正常停止旧NEW43010068，确认子进程清空/普通锁释放，再交给新gate安装，
  绝不停止OLD42523432或改旧journal。当前已有区域raw/project成功缓存保留复用；不要
  因新模块/validator源码变化删除它们。切换后更新observer目标job及区域progress读取，
  以真实新产出证明恢复；还没到可宣告“已部署/任务完成”的阶段。

## 2026-11-22 06:26 CST：并行规划与缓存单遍补丁已实际接管 NEW

- **当前 NEW 主任务改为43010335**，`agent-X86-53`，单节点32CPU/320GiB；正常run ID
  `20261121T222113Z-1973018-f3b56813`。bundle仍为
  `q0-parallel-cutover-20261122-054517`，transition SHA仍47d3bd36960518a6dcc1c5c8b98bf1b5fd61f6a076a42a3109d1d44e128acc01。
  源码冻结自master **ec093edf**，现在不再是“只上传、未安装”。旧对照 **42523432**仍
  RUNNING/grt_step2，约16核，未中止、未改动；后续不要把43010068当作存活NEW。
- 只读预检 **43010327 SUCCEEDED**，06:18:17结束，25项初始检查点全部通过，冻结包83项
  定向测试也通过。`validation.json` SHA
  `f3e96ee771316f8e044dc7980f951b165847098acbfd75ccc65b980c8d586075`。这是实际预检，
  不是从目录存在或日志片段推断成功。没有重复提交预检。
- 新allocation06:19已RUNNING，ready PID1973018确实在调度器进程表中，核对32CPU、320GiB
  allocation及硬内存限额后才在06:20:12请求 **正常dkill 43010068**，没有force。06:20:51
  核实原NEW终态FAILED、pids清空、正常锁消失，06:20:52才原子放行handoff。FAILED是此次
  主动性能交接，不是新计算错误；旧run最后记录completed=500/planned=61000区域窗口。
  不删除锁、不采用未完成PAF、不清理中断现场，也不把61000当作完整基因组比对次数。
- 06:21:13新owner取得正常锁，06:24:35已核实journal **installed**。库存16项（14个core
  runtime、launcher、显式科学声明），实际替换9项：7个core含新增executor、launcher、声明。
  另外7个内容不变的runtime没有重写。全部旧备份SHA、新安装SHA、20份候选源码逐项相等；
  新模块原来不存在，其backup=null/present=false准确，不伪造原文件。未重复移动任何cache。
- 四个原始受保护runtime和外层`run_orchestration.py` SHA均未改变，外层7cbcf887解析优化
  仍刻意不部署。25个原initial checkpoint文件的SHA均仍与预检相同；没有重写原生检查点。
  四块完整raw cache的success marker保留（FIRST150/fast61/native9/native1418→52）；本次
  登录节点检查只查小型receipt，并不冒称重新验证其完整大输出，真实reader消费时仍校验。
- 新reader声明绑定真实新builder/reader，`initial_alignment_profiles_modified=false`、
  `native_checkpoint_rewritten=false`。仍是原55项对照workflow，不加入DEGAP或其他master
  新功能。本次并行与记录处理优化没有额外改变4项科学policy、mapper flags或精度范围。
- 06:24:48真实Runner开始RESUME；06:25:56已经 **SKIP_VALID ref:JM19_hifiasm**，未重跑
  参考mapper。**当前仍在正常初始校验，不是已经完成25项复用或进入区域14路池**。预检25项
  与主流程实际SKIP_VALID计数分开报告；不要因为校验期单核或日志安静再次中断。
- 安装验证receipt已同步仓库：`q0-parallel-deployment-verified-20261122.json`；远端
  `deployment-verified.json`、`installation/receipt.json`、`normal-stop-request.json`、
  `old-scheduler-terminal.json`、`new-scheduler-allocation.json`及`handoff.json`均保留。安装
  journal SHA `9e77800daa968f9a476956d04924a808acc4cfd8984a75dc08c7b1b87239c60e`。
- 原observer1505606已因旧NEW终止自然退出，未手工杀它。新只读observer **3037575** 位于
  此bundle的`observer.py`，SHA `8ac77d55799884af0e03547ecee3a9d6759c3ed949e43d62034ec3e56aca45f4`，
  日志`~/cgat-reads-debug/logs/wheat-live-parallel-20261122-062306.jsonl`。按真实新run过滤旧
  中断记录，并读regional progress，不再拿native leaf=0误报区域任务没动。该observer是
  现场运维副本，不是新增科学runtime；只记录和提示检查，不自动修复/取消或主动聊天通知。
- **接续重点**：查43010335而非重新提交；核实后续25项SKIP_VALID、q0 reader真正启动、
  四块既有矩阵实际命中，再量测新区域池资源证明、planner/mapper并发和每100窗口吞吐。
  32线程有充分内存时的上限是owner1+planner3+mapper14×2，不能在尚未进入该池时就宣称
  14路已生效。原区域raw caches保留，projection因builder身份变化可重新验证，不能因此
  删除全部cache。若再修复，以此次transition/journal为新prior，不重放旧handoff或旧安装。
  整套小麦尚未完成；不把受控2.03x/2.45x倍率当作整套已测加速。不跑release CI、update.sh、
  全runtime替换、重新prepare或网站发布。

## 2026-11-22：25项真实复用完成，新q0 reader已执行

- 当前仍是 **NEW43010335 / agent-X86-53**，没有再次重提或改runtime。对实际run
  `20261121T222113Z-1973018-f3b56813`逐项提取日志，25个SKIP_VALID的unit及顺序与只读
  预检完全一致；初始阶段没有任何START重跑。06:53:33实际开始第26项`q0_evidence`。
  这次是主流程实际复用25/25，不再仅是预检或“首个参考已复用”。
- 真实reader **PID1990559 / start_ticks404157417**。同节点只读诊断 **43010343 SUCCEEDED**，
  目录`q0-parallel-live-phase-20261122-0655`，不读取locals、不改变主进程。06:55:49看到
  其验证既有chr_7B自比对PAF的SHA；06:56:49已进入真实新`lgz_core/q0_preparation.py`
  的`_initial_inputs -> read_fasta`，参考FASTA offset6340870144。60.100秒内CPU增加54.54秒、
  swap0，阶段已实际推进，不是仅凭job活着或锁存在推断正常。
- 诊断还核实两项资源proof环境变量确实传到实际reader，指向本次新allocation的
  `new-scheduler-allocation.json`，SHA ba501c27cf71025649f496600f08303a1cac13fce55817cf3ed39e34514e0c36；
  reader cgroup明确为43010335，proof也绑定同一job。并发准入没有退化成随意信任一个
  内存环境数字。**这仍不等于已经观察到区域14路池启动**，当前处于q0输入读取阶段。
- 远端`initial-reuse-and-reader-verified.json`及诊断`summary.json`/终态保留；前者已同步
  仓库`q0-parallel-initial-reuse-verified-20261122.json`，SHA
  774f7978b7f1d1e95e2e7dc6cf506f30492bff3f26e8a1e353c17e0b1bd5a3d4。
  此轮核实时NEW与OLD42523432均RUNNING，旧基线没有改动；observer3037575继续记录。
  后续跟踪实际矩阵缓存消费和区域池吞吐，保留当前进程，不能仅因输入阶段单核再次重启。

## 2026-11-22 09:05 CST：已核实的持续等待与诊断队列

- NEW43010335仍RUNNING/q0_evidence，reader仍PID1990559，25项初始复用未失效；09:04
  调度器recent99%、81227MiB、swap0，320GiB限额。没有新FAILED/INTERRUPTED，也没有重提
  主任务或改runtime。四块完整native cache的成功receipt SHA仍与安装验证一致；这里只查
  小receipt/文件元数据，不把它说成已经确认新reader消费完全部矩阵或重做大输出校验。
- 追加只读诊断 **43010349 SUCCEEDED**，目录`q0-parallel-live-phase-20261122-071329`；
  07:13:33–07:14:34从2B的PAF消费推进到2D的原checkpoint格式验证，60.059秒内CPU增加
  59.0秒。`summary.json` SHA 6965133238fc612ee615ce1cfb3839eb9508053b3e1ac73fd17eb53c1e79a469。
  **该栈是历史采样，不能拿2D当09:05的实时位置。**
- 后续只读诊断 **43010357 PENDING**，目录`q0-parallel-live-phase-20261122-073445`，固定
  同一agent-X86-53，1CPU/1GiB；提交时该节点CPU_FREE=0，尚未取得样本。继续查同一job，
  不重复提交，不把诊断排队/观察窗口结束当主任务失败，也不为采样另迁移或重启主任务。
  PENDING的Donau JSON可能省略taskExecNodes等执行字段；观察脚本用get读取可选字段，
  不要因打印KeyError误报计算失败。真正的allocation gate仍须严格核对RUNNING资源证明。
- OLD42523432继续RUNNING、recent1594%，MUMmer的2D组持续产生SUCCESS；09:04可见
  1184/1185号成功、1200/1201号START。启动编号不是已完成数量，不据此虚报完成百分比。
  observer3037575仍活着。当前没有区域池实测证据，下一步等实际q0缓存/区域progress或
  上述诊断新样本，不能把已部署和受控倍率说成整套已验证提速。
- 本轮监督快照保存在当前cutover bundle的`monitor-verified-20261122-090444.json`，SHA
  d4321206876916c22550f07ad29bea5602007e536c00de67ff29024dc5c31535；只记录已确认的等待，
  不标记整套任务完成。继续使用此前冻结transition和安装journal，不重放任何旧安装。

## 2026-11-22：FIRST矩阵有界片段热点分析，不冒充主任务实时栈

- 同节点43010357仍排队时，另外提交可在任意x86计算节点运行的**只读小片段**诊断，
  不扫描完整矩阵、不载入整套DNA、不调用mapper或改主工作区。新增运维工具
  `profile_q0_paf_prefix.py`及8项真实parser/资源依赖测试；记录数/字节/单行长度都有上限，
  截断行不进入parser，坏记录仍失败，任何结果均声明`whole_cache_validated=false`。
- 第一包43010374在测试导入前FAILED：只带38个lgz_core文件，漏掉真实package initializer
  引入的run_resources等依赖。**不是小麦失败**，没有消费数据。保留该包不覆盖；新包完整
  携带原已成功control的42个Server tools源码，核对所有SHA及4个直接使用的q0模块与主
  runtime一致。用真实依赖和独立import smoke核验，不注入sys.modules或替换__init__。
- **43010375 SUCCEEDED**，agent-X86-61，Python3.10.12，1CPU/8GiB；8项测试通过。目录
  `q0-first-prefix-profile-20261122-092001`。读取FIRST150矩阵开头**5000条/2098539bytes**，
  相对完整PAF2666514061bytes不足0.1%；1.531秒（**含cProfile开销，不能当生产吞吐**），
  峰值RSS92258304bytes。没有重新校验32GB生成FASTA或创建任何成功cache标记。
- 该片段parse_paf_line累计0.848秒、paired_query_intervals累计0.334秒；累计时间有嵌套，
  不能直接相加。仅产生13个关系，cross-coverage摘要等于空集合摘要，因此**没有实际覆盖
  合格cross-coverage更新分支**。没有建模真实reference-anchor catalog/fanout，也未覆盖
  大目录、完整PAF、原native checkpoint验证或主任务当前调用栈。不得据此宣称整个任务
  的热点或倍率，不为这份小样本结果再次中断主任务，也不贸然改区间合并算法。
- 完整profile和源码SHA已同步仓库`q0-first-prefix-hotspot-20261122.json`，SHA
  62d81c4cb21ddcae3cd7b86f6bbed25814ea9f2c02270e389d395b38bcfa3116；远端还保留完整
  `code.sha256`、`runtime-source-verified.json`、`final-job.json`及失败前包。工具运行时
  必须使用完整Server tools依赖闭包，不能只复制lgz_core目录。主任务仍是43010335，
  runtime没有因这次诊断改变；下一步继续等实际q0缓存/区域进度和43010357的新样本。

## 2026-11-22 10:31 CST：已进入真实区域池，确认两层队首阻塞

- NEW仍为 **43010335 / agent-X86-53**，原reader **1990559 / start_ticks404157417**，
  冻结runtime仍ec093edf；本轮未替换远端runtime或重提主任务。实际weak-seed日志于09:24–25
  记录fast61、native9及reverse1418→52；区域进度从09:28的100到10:31:25的**2300**，
  planned=61000、fallback_sources=0。planned是该阶段窗口总量，包含可跳过父查询，不能
  直接当作剩余原生全基因组比对数，也不拿前500个缓存复用窗口推算新计算吞吐。
- 10:18元数据实证：1717个完整raw成功标记中528个为此前已有、1189个为此次新增；1748个
  新projection中528个绑定此前raw receipt的真实SHA。完成标记的元数据统计不是独立全输出
  验收，真实reader仍执行正常内容/几何验证。主native缓存和区域raw均保留，不删除有效结果。
  实测1189条新raw native命令均t2、4GiB RLIMIT_AS，real中位3.601秒、最长326.033秒；
  stderr打印的Peak RSS约82GB不能当作当前单mapper RSS或相加推导OOM，尚未证明其成因。
  详见`q0-regional-live-verified-20261122.json`，SHA
  0f5ef3ce7c1f8e2729eba4a7d2e746aaa807b8768dc36fb697ad3924ca750c00。
- 先前排队的 **43010357已SUCCEEDED**，不能再写成PENDING。同节点09:47:16真实栈显示
  主线程在`RegionalExecutor.ordered -> Future.result`等待规划队首；**14个mapper线程
  全部在thread.py:81的work_queue.get(block=True)空闲等待**。PID、start_ticks、cgroup及
  scheduler SHA均绑定43010335。09:46另一采样中mapper还在运行，故这是实际空窗的实证，
  不是整段持续空闲的时长测量；不凭一次栈宣称整套倍率。只读诊断的结构化证明
  `q0-regional-head-of-line-observed-20261122.json` SHA
  95cb706d030d29e3c6097c8f3589d22af27f447f6c2e5c59cf54798043c252a0。
- 对应源码有两处同类问题：规划有界预取始终取队首、partial/candidate mapper始终pop(0)。
  本地定点修改三模块，先完成先回收补位；最终任务、原生回退组及组内query/报告列表恢复
  原顺序。保持3planner+14mapper×2的预算、预取上限、全父查询回退判定和全部科学参数；
  不扩大池、不放松guard、不新增科学功能。保留ordered接口供原序消费者使用。
- 本地**55项regional定向测试通过**，包含阻塞队首仍能补位、真实spawn结果逐项等价、
  有界预取、取消/内容错误传播、资源失败精确重算、原生交错分组还原、单CPU不重叠；
  扩展q0测试**共305项，其余通过、1项环境条件跳过**，106.287秒。没有跑release CI或update.sh。
- 仅提交隔离实样control **43011908**，目录`q0-completion-dispatch-control-20261122-103546`，
  x86单节点6CPU/60GiB（实际3规划+owner），对照与主任务相同架构/依赖。42文件完整工具
  闭包先对照原成功包SHA，再覆盖ec093edf的14模块和此次3模块；全部52项代码/脚本/输入
  manifest验证后执行。实际ready与djob同为agent-X86-06，资源证明SHA已绑定；不写主工作区。
  以原guarded calibration相同46父查询/240窗口元数据分别跑FIFO与completion，两者须逐项
  匹配原serial-owner hashes。该control不读DNA、不运行mapper，结果只用于规划等价/可用性；
  **后续须查43011908的真实终态及summary，不要因提交成功就写成已加速或已部署主任务。**
- 当前旧基线42523432仍RUNNING/grt_step2，约1596%CPU；未改动。新版10:32约642%CPU、
  memReal89781MiB、max95956MiB、swap0，320GiB额度。当前一次再续跑已实测约3小时的
  正常初始复用验证+q0输入/catalog/cache消费成本；新补丁须先验证并评估净收益，不能只为
  展示新调度再次重启。只读observer3037575继续运行，不能声称它能自动修复或主动聊天通知。

### 10:47 CST补记：实样control完成，暂不再次重启主任务

- **43011908 SUCCEEDED / agent-X86-06**，实际HPC三模块39项测试全部通过。原46父查询/
  240窗口的FIFO与completion结果hash均逐项等于此前guarded serial-owner；无pool故障或
  owner资源重算。FIFO135.9539秒、completion118.7441秒，小样本墙钟少12.66%（1.1449x）。
  FIFO先跑，后者可能受益于OS/索引预热；不包含DNA、实际mapper或科学catalog消费，故
  **不是整套提速倍率，也不足以单独证明值得支付约3小时重启前缀成本**。
- 完整报告`regional-dispatch-hpc-control-20261122.json` SHA
  e7d4600c83a616cab6f4b9f98a113a6ad139cb1fd73b63ea9d41f9de68be34a0；
  `regional-dispatch-hpc-verified-20261122.json`绑定终态、代码manifest及全部3个补丁模块SHA，
  本地源码也逐项核对相等。control远端`verified.json`/`final-job.json`/allocation和所有日志保留。
- 10:46:42只读observer实际查到主新版43010335仍RUNNING；最新进度为**2700窗口**
  （10:44:57）、fallback0，recent461%、memReal89103MiB、max95956MiB；旧42523432仍RUNNING、
  recent1594%。本次源码修复保存到master，但**没有安装到正在执行的ec093edf实例**。
  保留主任务继续产出，不重新执行handoff/update.sh、不动原锁或基线。后续须结合实际
  mapper长尾/队列损失与剩余阶段评估净收益，再决定是否正常停止并定点续跑。

## 2026-11-22 11:30 CST：真实原生队列对照约1.92x，候选已准备，主任务未停

- 原生control **43011969 SUCCEEDED / agent-X86-10**，目录
  `q0-native-dispatch-control-20261122-110235`，单节点16CPU/160GiB；使用与生产预算一致的
  7路×2线程、每路4GiB RLIMIT_AS。只重建选中窗口，不加载整套源DNA；**1505544121bytes
  的生成FASTA先逐一匹配原context完整SHA/size**，原完整raw receipt/命令/tool/PAF也核对。
  选取新raw完成队列中第43号起连续64个窗口，各历史native real<=45秒，故不覆盖326秒
  极端尾部，也不是随意剪掉生产任务。直接调用真实`q0_regional_mapping._execute`，保留
  原raw argv/精度profile，仅替换隔离目录输入路径；不写主工作区或采纳诊断副本为新结果。
- 旧→新→新→旧 **ABBA** 同节点运行，墙钟分别114.9371 / 61.6519 / 59.6847 / 118.5239秒。
  **256次完整原生stdout均逐字节等于各自原完成PAF**，mapper数/线程/guard未变；两次合计
  原生子步骤1.9241x、墙钟减少48.03%。本地/HPC的6项定向helper测试通过。仍不测规划/
  pre-CIGAR/catalog消费；control owner没有生产85GiB DNA堆，未覆盖真实大堆fork成本。
  **不冒称整套1.92x，也不与前一规划1.14x相乘。**
- 此前1189条真实raw耗时的all-ready模型：14路FIFO1790.303秒、完成顺序606.815秒，约2.95x；
  模型不含规划、chaining、I/O、future未完成部分及缓存验证。仅用于识别长尾队首损失；
  此次真实原生ABBA才是更强的子步骤证据。完整报告
  `regional-mapper-dispatch-hpc-control-20261122.json` SHA
  8d774d0fd5ac8652f503375a75c997c8182852041d5fe052e3c6a88c66047901，
  `regional-mapper-dispatch-hpc-verified-20261122.json`绑定全部源码/终态/资源proof及原输出SHA。
- 为避免把61000个planned窗口误判为“多数已由native矩阵满足”，另做纯元数据界限诊断。
  **43011989 SUCCEEDED / agent-X86-18**，1CPU/2GiB，2项测试（5000种随机+边界几何与真实
  plan_query_windows比对）。4个native成功receipt SHA均不变，完整矩阵query侧并集1629part、
  共40156368bp。即使把这些父查询全部算作可跳过，它们也最多对应**2573个**100kb窗口；
  因而planned61000里至少58427窗口并非已被当前native矩阵完整覆盖。
- 11:27只读observer所见最新completed4100（11:24:01）、fallback0；再扣除最大可跳过数和
  未打印/待回收完成的保守余量后，仍有**54214个planned窗口待交代**。这不是独立mapper
  次数：有的父查询可能转为整组native fallback，统计也不是大输出重新验收。partial targets
  包含原38117个reference anchors，可能还包含pairwise新增候选；此处证明只用其ref子集。
  完整界限/源码证明见`regional-native-matrix-skip-bound-20261122.json`及其`-verified-`文件。
  前一43011984结果保留；v2只澄清target集合是包含ref子集而非恰等于ref，未更改界限算法。
- 三模块候选已隔离prepare，**尚未安装**。目录
  `q0-completion-cutover-candidate-20261122-110559`，源码冻结748fddd0；新transition SHA
  **c0f3ce957eb59138dc8ffce9771bacfd351afa6a942ed682b2676bc6a729f210**，prior仍为当前ec
  transition47d3bd...，绑定当前安装journal9e7780...与previous_job **43010335**，保护42523432。
  仅3个`q0_regional_{execution,discovery,candidates}.py`改变，另11核心模块为no-op，4项科学
  policy AST全部相同；无新core文件、未改outer contract、未改initial profile/native checkpoint。
  `q0-completion-candidate-prepared-20261122.json`记录`workspace_modified=false/job_stopped=false`。
- 候选只读初始预检 **43011976 RUNNING / agent-X86-41**，11:09:48开始，2CPU/16GiB，
  83项针对性handoff/transition/context测试已通过，继续核对真实25项initial checkpoints。
  最后查询时尚无最终validation.json；**不能拿测试通过或进程活着代替25项完整预检终态**。
  原主任务在预检期间继续产出，11:23仍43010335/ec093edf、completed4000、recent720%、
  memReal89776MiB/max95956MiB；旧42523432仍RUNNING、recent1596%。没有再停任何主任务。
- **接续动作**：先查43011976终态、validation.json是否25/25且work_modified=false，核对
  当前run仍q0_evidence且最终q0证据尚未发布。上述真实native收益+仍有大量未被矩阵覆盖的
  窗口支持推进受保护切换，但不把任一子步骤倍率当作已证明的完整净收益；保留约3小时
  既有续跑前缀成本作判断。届时新申请32CPU/320GiB资源ready gate（**目前尚未提交**），
  得到并严格核对新job资源后，才正常stop **43010335**；等旧pids/正常锁释放，再原子handoff。
  只安装3模块及新launcher/declaration，保留所有native和新增regional成功缓存。不触碰旧
  基线，不删锁、不重跑update.sh/发布CI，不重prepare，不采纳或覆盖诊断PAF为主结果。
- 新候选本地索引`/tmp/q0-completion-cutover-candidate.json`，当前live索引
  `/tmp/q0-next-transition-current.json`仍指原主43010335；不要提前覆盖。原bundle的旧config
  仍指43010068，**不能重放**。新handoff-config/resume.dsub尚未生成，须绑定新transition、
  新preflight validation SHA、old_job43010335、protected42523432。observer3037575只读仍在，
  不具备自动修复/聊天通知功能。后续真实新reader启动时须核对新增admission日志
  `dispatch=completion_order result_order=original`、25项实际SKIP_VALID及缓存命中后新工作吞吐。


### 2026-11-22 11:50 CST：窗口必要性/复用只读调查，先不提交新切换作业

- 用户追问“怎么这么多计划窗口，都是必要的吗，能精简/复用吗”。本轮不改科学策略、不停止主任务；
  先判断工作量来源，不能只修调度后让明显冗余工作继续跑。当前 goal 继续推进，没有暂停授权。
- 候选预检 **43011976 已 SUCCEEDED**（替代上一节 RUNNING 快照）；`validation.json` SHA
  `a46396d126d9f1620acf010ff4b5559c64c62c9fdbc75cfbbe138ccb298e6fee`，25 个唯一 initial
  checkpoint，transition 仍 c0f3ce...；workspace_modified/main_task_submitted/q0_runtime_installed 均 false。
  **尚未提交新 32CPU 主作业、未安装 completion-order 补丁**；不要因读到上一节接续动作就直接切换。
- 元数据几何普查 **43012019 SUCCEEDED / agent-X86-61**，1CPU/4GiB，约25秒，峰值217MiB。
  复用冻结748核心包，核对原47文件manifest；仅读SHA绑定lookup/residual，不读DNA/PAF，不改主工作区。
  结果在 `q0-window-geometry-census-20261122-114749/census.json`（相对当前compare根目录），SHA
  `d8a5a1f741e35b9356ed82f0a697b7eef5fd6a0df55e94f03dccc477b5c1139f`；同目录保留源码、manifest、作业脚本和日志。
- **冻结 residual 不是当前实时 holes**：原100kb+双侧10kb策略得 **61087窗口/31978父contig**，
  现场日志 planned61000；差87，不能把冻结统计冒充当前精确计划。当前61k不是全基因组比对次数，
  whole-parent缓存跳过或fallback仍会改变真实执行数量。
- 冻结分布：flye 30799父/51231窗口（83.87%）；hifiasm 1179父/9856窗口。
  25454父仅1窗口，6524父合计35633窗口；不是仅几条巨型contig切出了所有任务。
  核心未覆盖共2319791151bp，查询context累计4066065198bp；其中context重叠344580512bp，
  不能把所有flank/context都视为可无损删除的重复比对。
- 只变核心上限、仍保留同样核心bases的**几何估算**：200kb=>49205（-19.45%），
  500kb=>43452（-28.87%），1Mb=>42097（-31.09%）。各有11260/7237/6215窗口超过现有
  120kb硬guard；不是可直接上线参数，也未测耗时/内存/结果一致性。不能简单取消guard扩大窗口。
- 丢弃 <1kb 单个残余洞的几何估算：56701窗口（-7.18%），少探索41223235bp（核心bases的1.777%）；
  <10kb=>44807（-26.65%），少探索572324942bp（24.671%）。这是遗漏探索范围，不是最终精度损失比例；
  尚未采用。用户允许有限降精度，也不能把24.7%遗漏解释为轻微代价。
- 已确认源码差异：partial 在父查询级调用 remaining_targets()==0 跳过已完成矩阵，但
  plan_parent/index.targets 未传逐pair selection；candidate 已传 eligible target mask。
  可以调查“只对尚缺 pair 缩目标集”，**尚未量化收益/更改实现或证明输出等价**。保留既有完整raw/project
  优先命中，避免一改窗口/目标集合就让已完成缓存全部换身份。当前4个矩阵的query侧并集/2573窗口界限仍适用，
  不能宣传61k大多数已被全局结果覆盖；参考坐标投影不自动等价为精确contig间CIGAR。
- 11:46:29只读observer：NEW43010335仍RUNNING，最新11:46:14 completed4700/planned61000/fallback0；
  OLD42523432仍RUNNING/grt_step2。仅新增上述25秒诊断，原任务和旧基线均未中断。


### 2026-11-22 12:11 CST：复用收益实样核对后，已受保护切换 completion-order

- 用户继续推进定向优化。本轮从源码潜在缺口落实到实际目标核对，而非直接上线逐pair过滤。
  **43012023 SUCCEEDED / agent-X86-61**：39父/51窗口、三个完整native矩阵，过滤前后最终
  target windows均33766、target bases均974533380；lookup合计53.6516/52.5129秒，不能支持大幅收益。
- **43012034 SUCCEEDED / agent-X86-18**再次纳入第4个快速矩阵。按真实sealed reference记录
  核对61个fast queries无qualified routing，再用原weak_global_seed_scope限制到52个有效query和
  其原目标范围，不把快速矩阵扩大成原生全覆盖。同一51窗口最终目标仍完全不变；lookup
  43.5834/43.8653秒，PAF decode计数88345/85840（少2.84%，并非少了mapper任务）。这是
  分层元数据样本、不代表全队列或所有输入；**不实现本轮逐pair目标裁剪、不采用丢小洞/扩大窗口**。
  报告 `regional-completed-target-pruning-sample-20261122.json` SHA
  `4ebd66f050be82cdb6b8c78b6d166311b421a3ddb39d37d87e8e961f63705505`，对应verified文件绑定源码/终态。
  原执行脚本留远端 `q0-partial-target-reuse-20261122-115906-all-scopes`；仓库helper仅修正
  顶部docstring，除docstring外AST逐项相同，两个SHA均明确记录，未冒称修订文件就是原执行字节。
- 继续已有强证据的调度修复，不为未证实的少算路线延误。新主资源 **43012037 RUNNING /
  agent-X86-39，32CPU/327680MiB**。12:02:39严格核对ready PID1245020属于新job、单节点资源、
  旧reader1990559属于43010335、当前旧run仍q0_evidence、旧基线RUNNING。新config SHA
  `005254ecab0d41e0641c542e84402e2533d85f8d29efe5fddf2e35f5169cd24a`，旧job明确43010335，
  **不是43010068，不是42523432**；真实25项preflight列表与上一主作业完整一致。
- 12:03:44仅执行一次正常 **dkill 43010335**，force=false。12:04:40旧job已FAILED（本次
  主动正常停止的调度终态）、全部pids消失、正常lock已释放；未手工删除lock或强杀。
  新job仍RUNNING/同host/32CPU/320GiB，12:04:41原子发布handoff，SHA
  `778e8f932ae347315e9487d98bed8a969cbcb62db8b55fd9c83f1b993f09639b`。12:04–05新gate接受handoff。
- **安装已完成并验证，不只是prepare。** 新run **20261122T040506Z-1245020-39aa9341**，owner1245020。
  `installation/receipt.json` status=installed，SHA
  `030694dff7efe342927c2ad74091df273a8b069dbd15197d45afe08bd714603c`。16份原文件备份SHA及16项
  安装清单均逐一核对；仅3个regional模块+launcher/declaration替换，另11core no-op不重写，
  原self_alignment/assign_chr/lgz_prepare_inputs/outer contract 5项保护SHA全部未变。四个完整native
  success receipt SHA不变；metadata统计5453 raw success / 5981 project success，**不是本轮
  完整PAF重验、不是当前进度计数**。保留所有原cache，原窗口/精度/预算/policy AST不变。
- 12:10安装验收见 `q0-completion-installation-verified-20261122.json`，SHA
  `111fa1e0c0c518211e01188d2156028979ffa189d559cd7f189713a21dc8b3fd`。
  本地三个regional测试模块再次 **39/39通过**（2.537秒）；真实预检83项和此前原生ABBA证据仍保留。
- 12:10:28新observer确认43012037 RUNNING，12:09:38已有新run PREFLIGHT事件，CPU99%、memReal175MiB；
  尚在正常续跑前缀，不是mapper池低占用证据。**尚未证明新run实际25项全SKIP_VALID，也尚未看到
  新run的completion-order admission/新增窗口吞吐；不能把安装成功说成整麦已提速验收通过。**
  OLD42523432仍RUNNING/grt_step2、recent1594%，未改动。
- 当前live索引 `/tmp/q0-next-transition-current.json` 已指43012037（previous_main_job43010335）；
  候选索引同步记录installed_initial_resume_pending。新只读observer **3593216**，源码SHA
  `7a14c6d07ed94bd7e716b9f45ea5daa0a80cb537ff9d011c0d885334610719b2`，日志
  `~/cgat-reads-debug/logs/wheat-live-completion-20261122-120557.jsonl`，过滤上述新run；无自动修复/通知。
  原旧observer会在旧job终态后自然退出，不再把旧索引当活跃主任务。
- **下一步**：只读跟踪当前43012037，先核对25项实际SKIP_VALID、q0真实reader/当前资源proof，
  再核对native/区域缓存命中和`dispatch=completion_order result_order=original`；只有其后新工作
  的吞吐才可判定现场收益。不因正常前缀/观察超时再次停任务。继续留意失败、明确低效步骤和内存；
  不跑发布CI/update.sh/全量替换，不修改旧基线。整个小麦任务尚未完成，goal保持active。

### 2026-11-22 13:20：25项实际复用已确认；61k候选流程优化不是简单减窗口

- 主任务仍为 **43012037 / agent-X86-39**，run
  `20261122T040506Z-1245020-39aa9341`。12:41:21实际完成25个唯一初始单元的
  `SKIP_VALID`并进入`q0_evidence`，不是只有预检通过。只读watcher将实际run/log/checkpoint
  身份与原25项preflight对应，凭据 `q0-actual-initial-reuse-20261122.json` SHA
  `d7a428781ee7f12a74d21b98acf5f867fb2425261bc0cd41c5420b3410b804b2`。
  watcher没有再次独立全量hash输出；实际验收由主流程完成。13:13:46新job仍RUNNING、
  CPU99%、memReal32472MiB、无当前run失败，处于输入/目录建立前缀；尚未见真实区域池
  admission/新增工作吞吐，不因安静或单核立即再次重启。旧42523432仍RUNNING/grt_step2，未改动。
- **初始染色体self/cross矩阵也查了，不把四个supplemental矩阵当作全部历史信息。**
  只读诊断 **43012104 SUCCEEDED / agent-X86-61**（13:01:48），39父/51窗口、66个初始
  矩阵绑定。原974533380 target bp；若profile/上下文允许复用初始self范围，条件重叠
  后846034253；若所有初始矩阵都允许，则792322251（约少18.7%）。没有一个查询窗口
  变成全空。**这是矩阵成员范围重叠，不是已准入的无损负结果复用**；初始profile、
  window seed上下文、目标范围差异仍需证明，未接入生产。最终报告
  `regional-initial-matrix-opportunity-20261122.json` SHA
  `d720483712797bc6f8c0e1aa7a883ccc9532188316e05b0a9d8fb1cf1ddd26eb`。
  此job后半段约15分钟为共享FS上的5453个已完成raw/coarse元数据inventory；
  不是主任务卡死/原生比对，统计不能替代完整内容验收，不重复启动这个全目录扫描。
- 当前区域代码已有no-CIGAR粗比对，但主要用于选CIGAR工作档，随后仍对原全部targets执行
  `-c`。因此61k是现有窗口计划量，不等于必须付出61k次相同成本的全目标精比对；可评估
  候选短名单、批量查询/共享index、按工作量触发的分层策略，不能只讨论并发。
- **静态短名单探针43012133 SUCCEEDED**：64受控anchors+64分层已完成窗口，128例，
  完整旧raw/coarse PAF校验。按每core/每dataset选top4 intra、top8 cross并保留方向多样性，
  原target bp3186047602→557985390，旧高质量core覆盖保留约99.46% intra/99.81% cross。
  对无旧coarse的例子保留全部targets。报告
  `regional-candidate-static-probe-20261122.json` SHA
  `b2b8b2b06cd25aa9c511b198e406c308d00736923dce615f584471d00060a438`。
  **只是旧精确PAF的子集覆盖评估，不是候选mapper实测或全麦精度保证。**
- **真实原生ABBA 43012150 SUCCEEDED / agent-X86-37**（13:11:24）：同x86工具、
  16CPU/160GiB、7路×2线程、每进程4GiB AS，核对ready PID/uid/job成员后才放行。
  64个原窗口FASTA共1505544121 bytes逐一验证；完整目标A两次精确stdout均等于历史PAF，
  筛目标B两次也彼此一致。A=68.151/76.273秒；B=88.140/89.444秒，
  **筛目标后精比对target bp1480706136→72098048（少95.13%），总mapper管线却慢约23%。**
  原生stderr显示部分例子精比对本身反而变慢，不只是生成子集文件开销；目标上下文变化
  影响seed/index行为，不能用目标bp缩减直接承诺提速。
- 上述B的跨组装旧高质量core区间实际损失1285/2241593bp（约0.057%），intra损失
  3724/2302580bp（约0.162%）；新获得的区间单独记账，**不能用净覆盖增加掩盖旧区间损失**。
  个例intra覆盖可全失（ordinal63原831bp），加权平均不是每个case的保证。报告
  `regional-candidate-native-pilot-20261122.json` SHA
  `7e450069554e0a147af73d2a5fd0c0a18dd84fac2534c0a561d566a3dd9d3572`。
  helper/test和原执行源码SHA在verified文件绑定；本地/HPC均12项针对性测试通过。
  **拒绝将该较慢方案直接安装到主任务，尚未启用新的科学筛选策略。**
- 下一轮为独立原生批量试验 **43012243 / agent-X86-37**，目录
  `q0-batched-native-pilot-20261122-131841`：单批最多4个不同query、原exact flags兼容、
  union targets≤100Mb，七路/2线程/4GiB AS不变；每个原query只消费自己原目标范围的输出，
  校验所有额外PAF行。比较legacy / batch / batch+显式f0.005，再逆序复测；原每query的
  CIGAR档在本试验冻结，**尚未实现生产的batch粗筛后逐query选档**。公共输入验证/批量输入
  准备耗时分开记录；原始A再次要求stdout历史字节一致，候选按实际区间差集计损益。
  此f0.005只在隔离诊断启用（也会作用于cross），不是已授权或已通过验收的生产cross档。
  本地7项batch helper测试通过，资源ready PID2055419与当前job/uid100399/16CPU/160GiB
  一致，分配凭据SHA `f04968acb54ebab66ad79af34fd4a73141dd9c0251b32f803e7d90a4eabcb1be`。
  结果待核实；不改初始比对、不改旧基线、不热改主runtime，不重跑release CI/update.sh。

#### 批量原生试验已完成；进一步拆分“目标上下文”和“过滤参数”的效果

- **43012243已于13:28:34 SUCCEEDED**。legacy两次64.067/74.975秒；batch两次
  69.366/75.865秒，mapper批次64→18但仍慢约4.45%；batch+f0.005为59.430/58.051秒，
  mapper阶段约1.18倍，另有48.892秒的批量输入准备未计入该倍率。不能将18批或1.18倍
  推成整流程收益。所有legacy输出再次字节匹配历史，两个候选各自两次输出一致，PAF全量
  语法/几何验证、逐query恢复原target白名单、core区间差集比较均通过。
- batch未过滤时，样本cross旧core损失为0，intra损失2648/2302580bp；但batch+f0.005
  cross损失14906/2241593bp（约0.665%），intra损失15980/2302580bp（约0.694%），
  **个例ordinal0 cross损失约15.93%**。这点mapper提速及平均保留率不足以证明该策略值得
  上线，特别是计入准备成本和个例损失后。未安装任何batch/seed近似生产补丁。
  `regional-batched-native-pilot-20261122.json` SHA
  `93bc1f4f2b64559484b937eb3348eb4a5e8754a5e1a4f0f5860d7f2cbcadccf1`，verified文件绑定终态/
  原执行源码/资源proof。HPC7项batch helper测试通过；本地四组diagnostic测试合计23项通过。
- 已提交下一项更窄的隔离控制 **43012261 / agent-X86-37**，目录
  `q0-full-seed-pilot-20261122-133010`，索引`/tmp/q0-full-seed-pilot-current.json`：
  **保持完整原target、原coarse/逐query CIGAR档不变，仅精比对加温和f0.001**；同一64个
  anchors进行ABBA，再按真实区间损失分开报告intra/cross。这样才能区分之前变慢来自
  batch/shortlist上下文还是seed参数，不能把两个改动的总差值当作单因素效果。
  ready PID2064983/uid100399/当前job成员/16CPU/160GiB已核实，allocation SHA
  `2cc2c41448253c02a11adbf321054dfddb1d32abb7868e318aa0f3114125aa6a`。
  仍是非held-out的诊断；即使样本胜出，也要核对尾部/独立样本、明确科学profile与缓存/
  消费者兼容迁移，**不能借原AST等价资源迁移的门禁悄悄改变科学策略**。主任务不因此停止。

### 2026-11-22 13:48：已定位all-chain精比对策略；强档有实测收益但不能直接上线

- **43012261 SUCCEEDED / agent-X86-37，13:35:43**：原完整target上仅exact加f0.001，
  ABBA legacy68.812/67.080秒、candidate64.774/65.122秒，只有约1.046倍。cross旧core
  损失67/2241593bp，intra2380/2302580bp，仍有单例intra损失7.19%；不将小幅样本收益
  作为再次中断主任务的理由。报告 `regional-full-seed-native-pilot-20261122.json` SHA
  `320913aaa08d434520abe3cc37117f8b0cc944abe3cd706375aca620097809e4`，执行源码、终态、资源
  proof由verified绑定。尚未安装该档。
- 更关键的是现有区域exact命令同时含 **`-P -c`**：no-CIGAR粗筛本来可以保留全部链，
  但精比对也继续保留全部链会延伸大量重复候选。已按实际工具2.31核对官方v2.31手册/
  cookbook（原始文件SHA见 `regional-chain-budget-primary-source-check-20261122.json`）。
  **保留`-P`时`-p`/`-N`不生效**，不能只增加`-N`就宣称限制了候选；`-N`限制secondary，
  也不是整个PAF严格只有N行。只测区域候选exact，不全局修改initial/native/self/cross flags。
- 原生控制 **43012281 SUCCEEDED / agent-X86-37，13:43:32**：保持完整target/原coarse
  及旧CIGAR档，仅candidate exact移除`-P`、增加`-p0.5 -N50`。64个受控anchors，
  legacy69.454/67.070秒，candidate27.008/26.790秒，**mapper管线实测2.538倍**；
  两次A精确stdout均匹配历史，两次B彼此一致、全PAF语法/几何通过。
  但cross旧core损失111712/2241593bp（4.98%），intra135142/2302580bp（5.87%），
  多个例子的intra/cross旧覆盖全失。**这是定位策略瓶颈的证据，不是可上线的精度验收；
  不能用加权保留率掩盖个例全失，也不能推成整麦2.5倍。**
  `regional-chain-budget-native-pilot-20261122.json` SHA
  `869c48d41cf9de5d939fd5e72de043b09963d5600b08c2c926a1182d27c00d3e`。
- 已递进更宽松档 **`-p0.1 -N200`**，而不是反复跑同一64短例子：独立作业
  **43012312 / agent-X86-47**，目录 `q0-chain-heldout-pilot-20261122-134621`，索引
  `/tmp/q0-chain-heldout-pilot-current.json`。明确选择static probe ordinal64–83、90/100/105/119
  的24窗口，与64原生调参anchors不相交，含两个组装、短query、空旧PAF、>100Mb父contig
  片段及旧单条326秒长尾；它们已出现在静态probe，**不是未见过的独立基因组数据**。
  698706029 target bp按FAI窗口读取，不整套载入DNA；每份FASTA必须与原执行input size/SHA
  完全一致，original A两次仍要求历史stdout一致。原tool/coarse/profile/完整target均保持。
  输入准备另计，7路×2线程/4GiB AS/16CPU160GiB不变；40分钟仅为独立诊断上限，不是主任务超时。
  ready PID1371668、uid100399、当前job成员/单节点资源已严格核实，allocation SHA
  `3a3680d32d4050299c7f739af2d2aebb91b65a4951e6c6ac584458336816e190`；HPC5项cohort/policy
  tests通过；实际24份输入合计709820980 bytes已在38.222秒重构并逐份size/SHA验收，
  已进入原生ABBA（最近采样CPU697%、memReal2850MiB），终态/质量/耗时待核实。若更宽松档仍丢跨组装关键信息，
  下一步考虑按组装保留候选与core覆盖不足的完整回退，不能以用户允许少量精度下降为由
  静默接受大面积局部丢失。
- 主运行13:47:24仍43012037/RUNNING/q0_evidence，25done、无当前失败、CPU99%、memReal32545MiB；
  前缀尚无区域pool admission记录，不据单核/安静取消；旧42523432/RUNNING/grt_step2未改。
  本轮新科学策略**全部仍隔离试验，没有安装到主runtime，没有取消或重提主任务**。
  仓库`c8eb6df6`已推送前半轮证据，后续按命名路径提交，不接触并行DEGAP提交/其他输出。

### 2026-11-22 14:09：增加逐core/逐dataset的原生回退试验；主任务未中断

- 前一goal turn属于**实际进展**：定位exact all-chain成本，提交原生控制和源码证据，并启动
  独立24窗口长尾控制；不能把其强档2.538倍缩写成已经部署或整麦收益。当前继续该目标，
  goal仍active，完整小麦及新策略现场收益均未验收完成。
- **43012312 / agent-X86-47**仍RUNNING。24窗口的ABBA已完成A0=472.375秒、
  B1(`-p0.1 -N200`)=249.840秒、B2=179.058秒；A3和最终逐case区间损失尚待终态报告。
  两次B差异较大，说明节点/运行时波动不可忽略。**不能只拿A0/B1或两次B就发布倍率或精度结论**。
  仅需继续读取同一job/日志，不重提、不动其冻结源码、不把观察超时当失败。
- 新增隔离控制 **43012347 / agent-X86-30**，目录
  `q0-gated-chain-pilot-20261122-135748`，索引`/tmp/q0-gated-chain-pilot-current.json`。
  64原生anchors上ABBA测试“快速候选 + 不足则原生完整补算”：coarse、full target与原CIGAR
  档不变；candidate exact为`-p0.5 -N50`且移除`-P`。只从经过完整PAF验证的高相似paired
  exact块计算覆盖；对**每一个core、每一个目标dataset分别**要求cross98%、intra90%，
  任一不足则补跑原完整exact，不再重复coarse。空candidate不能冒充精确负结果。
- 每份原生回退都要求stdout SHA与历史完整raw一致；候选和回退文件均留存。
  A两次仍须历史字节一致，B两次不仅比较最终输出，也比较candidate SHA和回退决定，
  防止最终回退相同掩盖前一候选不确定性。局部短core不能被大core平均覆盖，某dataset
  不能替另一dataset“补足”。六项针对性gate测试覆盖这些边界，本地/HPC均通过；
  本地连同前述诊断七组共39项通过。只是诊断，不是已接入生产的policy。
- ready PID2072907/uid100399、当前job成员、单节点16CPU/160GiB均已核实，allocation SHA
  `1d6b22d894a095d863eabac60e8c321d73c7e36baaeca402f5ca6265cb6fac0c`；资源保护仍7路×2线程、
  mapper AS4GiB。输入1505544121 bytes逐份SHA验证完成，但本节点耗165.255秒（此前节点
  约33–42秒），运行条件有波动；14:07原始A0还有任务，尚无完整ABBA/收益报告。
  不能把离线任务耗时回放约1.3倍冒称此job实测；需要把额外candidate、回退和验证成本都算上。
- 14:04:58主43012037仍RUNNING/q0_evidence，25done、无当前run失败、memReal32588MiB、
  CPU98%；仍未见区域池admission。旧42523432仍RUNNING/grt_step2，未改动。尝试安排同节点
  只读`/proc`采样前查到agent-X86-39 CPU_FREE=0/CLOSE_FULL，**没有提交采样job**；
  `/tmp/q0-reader-openfile-sample-current.json`明确status=not_submitted、job_id=null，
  不是运行中的观察器。不能为采样挤占主任务或改host-key/SSH认证。
- **上线前必须补齐的生产约束**：旧完整raw先复用；candidate raw仍与cores分离，回退决定
  必须单独绑定本次cores/policy/目标dataset，不能将某次core验收写成所有投影均适用。
  审查discovery/candidate两条调用者、raw/投影验收器、ready-manifest和最终companion消费者；
  当前`load_verified_evidence`给regional verifier的是length/SHA元组，新dataset角色不能只
  信投影自报，须由catalog源身份绑定。科学flags改变需要显式科学profile迁移，不走旧AST等价
  的资源-only门禁，不修改初始native/参考或旧基线。
- 此gate的95%高质量core只是诊断/回退代理，**不证明同一ortholog、全部替代拷贝、染色体/
  方向候选或最终组装等价**。实际catalog也消费其他paired关系，不能把proxy保留率说成所有
  消费者信息都保留。试验原始工具未启用`--eqx`；当前100paired-record proxy与生产
  `ObservedSourcePairs`的100 M/=资格还须在正式集成时统一（排除X对门槛的贡献），不能热改
  本轮已执行的冻结helper、伪造源SHA或把补做验证追认为当时执行过。

### 2026-11-22 14:35：长尾温和档被否决，回退诊断超时；转测不改变精度的启动开销

- **43012312 / agent-X86-47 / SUCCEEDED**，24个未参与64个原生调参窗口的慢/短/空/长父序列例。
  完整原参数A=472.375/743.537秒，宽松限制`-p0.1 -N200`的B=249.840/179.058秒，
  样本mapper管线2.835倍；节点波动大，不外推整麦。两次A历史stdout匹配、两次B彼此匹配。
  **拒绝部署**：旧高质量cross core实际丢195729/537230bp（36.43%），intra丢203194/477057bp
  （42.59%）。ordinal8跨组装原89338bp全失，ordinal22丢约68%。宽松档在长尾样本上的代价
  远高于强档在64个调参窗口中的平均代价，不能用后者替代该验证。
  报告 `regional-chain-budget-heldout-native-20261122.json` SHA
  `75065648ee7c8525b0d2550fa681e9caf63937bc6c50dfa40b009f9b602d1f3c`。
- **43012347 / agent-X86-30 / FAILED，jobExitCode=124**，14:25:33达到隔离诊断1500秒上限。
  原参数A0=494.076秒、带逐core/dataset原生回退B1=699.133秒；没有完整ABBA、最终质量或提速
  验收，不接纳任何试验产物到主任务。无需盲目放宽时限重提相同64样本。主新版不受其超时影响。
- 在已完成的A0日志抽查8个case（0/1/3/8/25/37/50/63）的coarse/exact：慢节点上
  `stderr mtime - command.json mtime - minimap2自报real`约16.7–18.9秒/调用，之前节点同一批
  约0.1–0.7秒/调用。它是文件时间戳估算，可能包含stdout/stderr打开、子进程启动、远端文件系统
  及缓冲的延迟，**不直接证明guard或某个文件系统是因果**。原参数与回退本来做同样比对，却跨
  节点耗时显著不同；这种条件下不应仅靠更多剪枝调参去掩盖固定开销。
- 已提交同为x86、拿到**同一慢节点agent-X86-30**的无DNA启动诊断 **43012713**，
  4CPU/4GiB，目录 `q0-guard-startup-20261122-143421`，索引 `/tmp/q0-guard-startup-current.json`。
  以小命令隔离`command.json`落盘后open/Popen/child.wait；原guard、Python`-S`、相同guard
  脚本放节点`/tmp`、系统`prlimit`按轮反序比较。每种都验证PID保持、PG继承、4GiB软/硬限制
  等值；不把无保护作为性能候选。不改主runtime，不引入新运行时依赖，不重跑任何小麦序列。
- 14:34:35主43012037仍RUNNING/q0_evidence，25初始单元已经实际复用、无失败，memReal
  42148MiB/320GiB；CPU recent约31%。尚无实际区域池吞吐，不能把它当作窗口速率或卡死证据。
  旧42523432仍RUNNING/grt_step2且不改。14:30 agent-X86-39仍无可用CPU槽，没有提交同节点
  主任务进程采样。目标继续active，完整小麦和新的现场加速仍未验收。

#### 14:44：启动固定开销已在慢节点重现，真实mapper单变量控制在跑

- **43012713 / agent-X86-30 / SUCCEEDED，14:36:45**。无DNA启动对照12次，子PID/PG和4GiB
  软/硬上限均等。原Python guard记录命令后中位18.436秒，其中`Popen`0.050秒、等子进程
  18.188秒；本地guard脚本18.200秒、`-S`17.832秒、`prlimit`11.962秒（均为记录命令后）；
  不足以解释或解决整段延迟。由同一慢节点重现，排除“必须运行小麦或改变科学档才慢”，但
  尚不能把全部延迟归到某个库或文件系统。报告 `regional-guard-startup-native-20261122.json`
  SHA `3349855fb0d2d751246053602fe351ce5a97c583dc56b2c4fecf3a113041b605`。
- 运行环境为MUMmer和模块栈设置了共享库搜索路径；区域minimap2自身是动态链接程序。
  对照 **43012781 / agent-X86-08**，目录 `q0-regional-loader-path-20261122-144307`，索引
  `/tmp/q0-regional-loader-path-current.json`。只改变诊断子进程的`LD_LIBRARY_PATH`，先比较
  原/候选解析出的库绝对身份；只有相同才继续。原/候选均以相同Python保护器核查PID/PG/软硬限额，
  用3个已完成窗口在同一节点跑继承/清理/清理/继承的coarse+exact，要求**每份历史PAF字节相同**，
  输入不超过50MiB，库与原工具、guard和FASTA的SHA前后不变。7项本地启动/loader测试通过。
  这不是全环境卸掉库路径，也没有改共享环境/MUMmer/生产任务；若不能等价则不继续映射。
- 14:43:38主新版43012037仍`q0_evidence`，25初始单元已复用、无失败，memReal46249MiB，
  CPU recent约33%；尚未见区域池admission。旧42523432仍运行，不动；禁止仅凭低CPU中断。

#### 14:52：子进程加载路径对照有部分收益；删除生产区域代码的等价冗余扫描

- **43012781 / agent-X86-08 / SUCCEEDED**。仅在诊断子进程清掉`LD_LIBRARY_PATH`时，Python、
  `resource`、minimap2和限额探针Bash的动态依赖解析到同一批文件；输入、工具、guard和原依赖库
  SHA前后一致。保持原参数、原工具、原软/硬4GiB限制与PID/PG；3个已完成窗口各做coarse+exact，
  四次ABBA合计24份stdout均逐字节匹配已封存的历史结果。A=61.156/68.636秒，B=55.392/56.995秒，
  合计样本wall少13.4%（1.155倍）。空限额探针子进程耗时16.06→4.976秒，**仍有残余启动开销**，
  三窗口不能外推全麦，也未证明其他环境清空库路径仍等价。报告
  `regional-loader-path-native-20261122.json` SHA
  `5815c68f349da8c03df4764d6b889dc54c2fac76e4c185bd2d881bd4cb63388b`。
  不把`unset`写入共享环境或MUMmer流程；若进入下一轮生产候选，需只作用于核对过依赖身份的
  区域子进程，并保留原环境回退、命令/环境真实来源及跨节点重复验证。
- 已在仓库实现精确且可复用的独立改动：`prepare_regional_mapping`的新coarse输出验证一遍后直接
  使用其`ChainWork`，不再次解析刚原子改名的PAF；移除raw预投影重复geometry扫描，但新raw
  仍先验证再发布；投影生成和最终receipt replay继续校验每条raw CIGAR、window名/长度及内容。
  discovery与candidate共用此入口；无参数、科学policy、guard、receipt格式或已有raw/project key变化。
  回归覆盖已有raw/投影无重算、恶意/损坏的匹配digest记录仍因错误window长/无效UTF-8拒绝、
  不新增带错误证据的projection成功标记。`test_q0*.py`共307项（306通过、1跳过）；不跑CI发布。
  当前仅提交仓库，**未改或重启43012037**；未测该去重对整麦的提速，不和加载路径小样本倍率混算。

### 2026-11-22 15:16：参考证据目录精确提速；核实当前 reader 的真实位置

- 原`build_catalog`对完整落在同一原始source part内的命中，仍逐个CIGAR配对块二分查找、
  求交和重建已正确的两侧坐标。现在用整个query envelope的包含关系只选择快速路径；**绝不把
  envelope当覆盖**。每个实际M/=/X块、真实偏移和方向、全部证据ID及MAPQ/qualified规则不变。
  跨part/N gap仍逐块裁剪，纯I/D不新增候选；相同part的证据集合/最大MAPQ不按块重复更新。
- **43012908 / agent-X86-47 / SUCCEEDED，15:11:35**。两套真实小麦参考PAF有界分段样本
  （34,168条证据、779条完整原source记录，未重跑mapper），在同一节点重用真实sealed index，
  冻结`ac670f24`旧目录builder与候选builder做ABBA。A=38.512/44.398秒，B=26.575/26.734秒，
  **目录构建样本wall减少35.7%（1.555倍）**。完整catalog payload/每条证据、routable parts、
  按source/chromosome的footprint与index报告总摘要四次完全一致：
  `e28d1eca405d004efa781e9d1e001915ec982e8648f07b59002c6592995a37bb`。
  `reference-catalog-source-fast-path-native-20261122.json` SHA
  `1789785f7e060309686e1481f3f16cd38e363481c761770c411445f3cc09bbe5`。
  这是前置目录构建的有界样本，不是整麦或61k窗口mapper的倍率。
- 同时修复已封存ReferenceIndex缓存命中时的重复共享盘I/O：此前`open`已按内容校验并复制原
  PAF至节点本地，catalog却重新从共享原路径顺序读一遍。现在读取**已验证的同字节本地镜像**，
  证据仍记录原PAF相对路径/行号/hash；镜像或原件在扫描中漂移都拒绝，fresh index及无镜像
  保留原读取路径。此镜像修改不在上面ABBA测速候选中，不能与35.7%相加。
- 聚焦测试17项通过；挂载目录完整套件出现2次读取builder小文件`Errno 12`，分别重测通过。
  用相同四个候选源/测试文件及真实仓库基线在独立Linux磁盘冻结的**完整310项q0套件：
  309通过、1跳过**。未跳过失败测试或改降验证。两项改动不改变raw/project key与mapper
  精度；最终prepared manifest仍绑定新的真实builder身份，不冒用旧manifest。
- **15:14:48新版43012037**仍RUNNING/q0_evidence，25项初始缓存已复用、无本轮失败、
  RSS统计59713MiB、recent CPU约99%，未开始记录区域池吞吐。**旧42523432**仍RUNNING/grt_step2，
  未改。主节点agent-X86-39重新有16个CPU槽后，已提交独立1CPU只读诊断**43012967**，
  索引`/tmp/q0-reader-openfile-sample-current.json`；只采样当前主job拥有者/reader的进程、
  打开文件/offset元数据，不读序列、不附加调试器、不暂停或重启主任务。
- 当前主reader仍旧冻结版本；前置已经运行很久，不能为这个建设性优化再重做已付出的扫描。
  新代码进master供后续切换或续跑，仍以现场实际阶段、吞吐和净收益决定是否安装。

- **43012967 SUCCEEDED**，与主新版同在`agent-X86-39`。15:16:53–15:18:53七次采样，
  主reader **1966058** 进程起始时间一致、单线程；120.71秒中增加120.34秒CPU，swap 0。
  打开的已有`runs/JM19_hifiasm_vs_ref/result.paf`（683392866 bytes）offset
  **236519424→285130752**，前进48611328 bytes；瞬时位置会在解析长记录时暂时不动。
  这是既有参考PAF前缀的实际读进度，不是重新运行参考比对，也不等于窗口mapper吞吐。
  未取函数栈；按命令与文件位置、单核计算及进度判断为q0参考证据处理，先继续保留计算。
  只读采样输入原始digest `68e2f50525c3315bf1b69efbea2afc76b1bf62e2a256c0bd696057b559f010ea`，
  精简的可核查证据 `q0-live-reference-scan-20261122-1519.json`。本轮源码`f7c82ea2`已推到master，
  未安装到这个reader；下一步继续核实Hifiasm扫描结束后真实candidate/partial事件，记录实际
  新工作而不是把已复用窗口计入提速，未验收完成前保持目标active。

### 2026-11-22 15:42：只限单次DP规模，对长尾效果好；先守住跨组装目标关系

- 延续不砍候选名次的思路。核对与隔离mapper版本对应的minimap2 v2.31源码`options.c`与`align.c`：
  默认`max_sw_mat=100000000`，超过的是单次DP子问题query×target的规模，而不是区分所有
  secondary的数量，也不是mapper进程的4GiB AS上限。`--cap-sw-mem 10m`会跳过部分扩展，
  **绝不是无损守卫**；粗找链、全部target/`-P`、既有CIGAR档和真实AS硬限制都保持。
- **43012991 / agent-X86-08 / SUCCEEDED，15:38:00**。13个有界旧窗口、345931620字节已封存
  FASTA逐份SHA确认；保留已完成旧raw作为对照，不重复coarse，不重跑13份完整原参。仅补做
  两条同节点原参exact对照、旧stdout逐字节一致；10m下原生wall分别**69.456→10.277秒**及
  **216.507→27.789秒**（6.76和7.79倍）；同节点CPU得出相同量级。13件的历史CPU和候选CPU
  分别1283.230秒和186.013秒，但历史部分不是同节点配对，不据此报整麦或真实生产倍率。
  原始报告 `regional-dp-budget-native-20261122.json` SHA
  `35d9a4a7076a99b4deea29a1eeecab74ebc0010a1cd150f3fcaa1f889b02a44b`；
  4项参数隔离、反向块及“覆盖不变但目标丢失”的测试本地/HPC通过。
- **拒绝全局启用**：13窗的原有高质量cross核心查询覆盖差集1421/387877bp，看似只约0.37%，
  但按原target-window+方向分别跟踪，仍丢了**32个原有支持至少1kb的cross关系**、旧目标侧
  逐组区间458673/1315722bp未被覆盖；其中ordinal4的cross核心union完全不变，仍少27个长组。
  intra核心少4530/387205bp、少55个≥1kb的组。无命中、验证失败或诊断产物都不冒充精确缓存。
- 用已有coarse工作候选**暂定**密度筛选（query窗口≥20kb、chains≥9000、chains≥30×target
  windows），只在校准组命中1/8/20/21/22五窗；cross核心差集197/298445bp，≥1kb cross
  目标方向组无全失。它只来自**3个源part**，其中8/20/22是同一part，**不能据此启用**。
  原`weak_span_product>=1e10`也不能直接拿来替代：这五个原始决策全是ordinary weak work，
  另有便宜样本因weak span大已选`-m2000`。判断候选须对照有效的原profile，而非只看长度。
- 50份真实小型历史原生receipt/context/decision的只读计数，未重hash大PAF、未读DNA：冻结
  1189条旧区域raw中全部20条CPU≥30s，暂定门槛命中11条、2150.518/2758.424历史CPU秒；
  但**仅1个命中的慢窗口是原13窗未用过的source part**。30条确定性普通样本也有1个
  **1.554秒**廉价误触发。该统计是旧顺序的有界样本而非全队列推算。下轮先验证独立源part、
  检查实际消费的目标/方向关系，考虑更宽的DP cap，不再试统一大幅裁剪，不直接改主科学策略。
- **43013000 SUCCEEDED**，主job的独立1CPU只读采样；15:35:46–15:36:46同一个reader从
  637812736推进到658128896/683392866字节（文件约96.3%），4次均D状态，60.39秒内16.0秒CPU，
  仍有进展，未重跑参考mapper；共享盘读取阶段是已实证的局部瓶颈，不把个别D状态当卡死。
  `q0-live-reader-followup-20261122-1537.json`保留证据。15:41:26主43012037仍RUNNING/
  q0_evidence，25初始单元复用无新失败、暂无区域池日志；OLD42523432仍RUNNING/grt_step2未改。
  本轮无主任务切换、无runtime热替换、无新证据采纳；新策略仍需验证后才判断净收益。

### 2026-11-22 15:55 CST：把“61k个计划窗口”拆成两类优化目标

- 61k是当前策略根据未覆盖区间切出的计划量，不是固定科学要求或尚未完成的任务数。冻结几何
  61087窗/31978父中，25454个父只有1窗，不能靠合大窗口解决；200kb几何上少约19.5%，
  但11260窗超过原120kb保护线。不能为减计数撤掉内存约束。已测缩小target和粗暴并批
  都没有实际节省本批mapper墙钟（见上文），不重做同类全量试验。
- 已冻结的`operational-trace.json`（SHA `e74626d25d32da75377c79092f275f77501ccb3e340dcca100aedd3ec8b387be`）
  1189个已提交成功的**原生精比对**样本共8409.9 CPU秒：135窗（11.35%）各≥10秒，合计
  4458.0秒（53.01%）；20窗（1.68%）各≥30秒，合计2758.4秒（32.80%）。不是全麦速率，
  未含chaining、准备、共享盘开销和失败；只说明优先优化少数高成本窗口比统一降精度有针对性。
  128窗静态对照中，103窗实际有coarse凭据且都非空；25窗未执行coarse，不能把它们当作
  “粗筛无命中”跳过精比对，其中22窗有旧的合格高质量core覆盖。
- **流程级候选：先消费已有精确结果，再只提交尚缺的工作。** 当前partial在入口冻结holes和整个
  `windows`，一并运行后才调用`add_pairwise_candidates(...observe_part_hits(...))`，所以本轮
  一个window已得到的跨组装配对证据即使覆盖另一未提交窗口的目标端，也不会反馈到本轮规划。
  建议先用已完成raw/project做冻结计划的只读回放：校验实际CIGAR/源序列帧，按同一已有跨组装
  合格规则将真实配对块同时落到两端；只计算此前未覆盖核心中被回填的区间以及可以免算的窗、
  加权CPU和后续候选差异。统计按确定性阶段而非线程先后；缓存始终优先，原窗口/目标/完整凭据
  不被重写。参考共定位或粗链只用于提名，不能冒充真正的配对证据或负结果。
  “有覆盖”不等于“备选关系齐全”：保留不同target/方向/位点以及唯一/冲突/无锚情况，
  若采纳缩减必须独立验证跨组装关系和最终Q0/Q1候选，而非只报覆盖率。仅对确属重复的子工作
  跳过或缩小；尚无该回放的节省比例或生产准入，不动正在跑的科学策略。
- **同一工作量的精确去重候选：** 对本来就跑coarse和CIGAR且目标完全相同的窗口，试验在
  coarse同时创建原target索引、CIGAR读节点本地同一索引；不更改目标集、参数和既有粗筛档。
  按同节点ABBA，包含写/读索引耗时，并要求两阶段都和历史PAF字节一致。`43013056`初次
  探针由于隔离包未列出旧loader测试模块，测试阶段即退出、未启动mapper；补齐明确文件清单且
  本地从隔离包6测通过后，在新目录重提`43013065`，不改主任务。测试结果待核验。
- **当前前置位置已核实，61k池还没重新开始。** 只读`43013068 SUCCEEDED`在同一计算节点观察到
  15:54:58–15:55:29相同reader PID1966058/start_ticks6576032463已离开参考PAF、在读取既有首轮
  `q0-map-8024dde83cbf20e7ffa6d8ee/result.paf`。文件2666514061字节，已成功的150×38117
  矩阵（receipt同size、PAF SHA `a77bb782873d4a5c25596a1d9377c817ec36d7cb27c7b8712902b1b416c3965c`）；
  本次仅读receipt和FD元数据，未重新hash大文件或运行mapper。偏移320782336→378970112，三次
  R、1线程、swap0，30.32秒累计CPU30.24秒。原始样本在
  `q0-reader-openfile-followup-20261122-155401/samples.jsonl`，SHA
  `f7742704e9b6f4777e823c5004c2c39d807558f94682f95f1505d3f6bf286471`。15:56:30主43012037
  仍RUNNING/q0_evidence、25项已复用、无新失败；旧42523432仍RUNNING/grt_step2。继续区分
  读取/消化历史成果与新算。避免为了省这次已付的串行前缀而重启；未来再优化大缓存消费的重复
  全文件I/O，不能跳过内容、CIGAR或证据身份的验证。

### 2026-11-22 16:04 CST：索引复用ABBA不提速；启动已完成证据的两波回放

- **43013065 SUCCEEDED / agent-X86-47**（15:59:31 CST）。原三窗3830万bytes，4个阶段共24份
  coarse/CIGAR stdout均与历史字节一致；候选仍使用相同完整目标和参数。原两次64.608、66.037秒，
  复用本地索引71.259、61.630秒（包含写后读；每窗索引约20–26 MB）。候选均值慢约1.7%，幅度小于
  同档两次波动，**没有观察到净提速，不接入生产**。结果
  `regional-index-reuse-native-20261122.json` SHA
  `020df60d328fbd1c8084bff9bc31b33a56164247c4f6ee4c4fedfac13cda9977`；保留远端完整终态、
  命令、独立guard/PAF、同节点峰值与`code.sha256`，无主任务修改。
- **43013071**（1CPU/4GiB）在独立目录运行两波只读回放：冻结64原生window作种子，另64
  分层window作对照，按原投影及≥95%比对身份、≥100 paired M/= bp保留真实跨组装目标端块。
  每份原raw receipt、context、源part长度/内容绑定、PAF bytes与SHA验证；不读DNA、不调用mapper，
  不写主workspace。对冻结61087窗从机会统计扣除已缓存seed；报告目标端命中的完整/部分核心。
  对完整覆盖的对照窗另核对原跨组装目标part、方向和两端位置，**有覆盖不等于可跳过**。
  队列按冻结顺序，不依赖线程完成顺序；候选不改变任何资源/运行参数。
  本地和独立打包4项针对性测试通过；旧baseline与新主作业均未停止或替换。
- **两波回放43013071 SUCCEEDED / agent-X86-61**：SHA `b1f52ae860b905a5a446a6710dc473bc0e9f200e5181dc0fe102caa87699ba1d`，
  171.27秒内复核128份原raw，共48741723 bytes。64个种子覆盖562个目标part，1407组反向映射后的
  有向part对；将这些已验证目标端配对块与冻结计划相交，64个种子之外仅**22窗完全覆盖，96窗部分
  覆盖**，合计1574898/2317367692核心bp（约0.068%）。64个独立对照无一个与这些块相交，
  所以不能证明这22窗的其他目标/方向均可由种子替代，也无对照CPU节省率。只说明确有双端回填
  机会，而不是可跳过22个真实新mapper，不能按比例外推全梯队或修改现场计划。要扩大验证，按真实
  对侧有交集的query确定留出组，再检测其原始候选/方向和两端位置；不要重复抽互不相交的样本。
  16:08主43012037仍RUNNING/q0_evidence（25项复用、无本轮失败与新区域池日志），旧42523432
  仍RUNNING/grt_step2。当前两种备选均未启用，继续保留完成缓存和主进程。
- **16:09:58现场读进度**：`43013082 SUCCEEDED`仅观察原reader，同FIRST已成功矩阵从
  1431658496→1473093632/2666514061字节（53.69%→55.24%），三次均R/单线程/无swap；原始证据
  `q0-first-reader-followup-20261122-160835/samples.jsonl` SHA
  `205173fef0e73eea7ce1acc71043ad946e5b178ba17c34bfa3ab1451084b00c3`。正在解析/消费旧结果，非
  重新比对，55%只指这一个文件，不是Q0或整麦完成百分比。新区间池未报进度前不估全程ETA。

### 2026-11-22 16:25 CST：定向对照否决按覆盖删窗口，改掉每行重建目标清单

- **43013109 SUCCEEDED / agent-X86-18**。固定同一64个种子，从SHA绑定1189份完成窗口的原
  trace 按真实对侧核心相交找留出，不查看其PAF才选择。6测通过；实际 1 全覆盖、2 部分覆盖，
  3份完整原PAF均从原receipt/context验证并按原投影重放。全覆盖窗仅155bp、原精比对0.268 CPU秒，
  相同目标part/方向仍少310bp目标侧区间。部分覆盖的11769bp窗，即使只免算已覆盖的3363bp，
  仍会少**100组**各有≥1kb证据的原跨组装有向关系；另一部分覆盖窗也有两端坐标差。
  现有策略不能按coverage union作为免算门，未改科学策略、未复用粗链作负证据。报告
  `regional-reciprocal-matched-20261122.json` SHA `a71090c05195f7017b121533a79934b135cd21c0309ec927720dd26139a9555c`。
  现存三条对照非全麦抽样；优先无损复用/验证重复路径，不继续扩大这一未经关系校验的删窗法。
- **已实现无损定点修复**：区域投影在每条PAF行构造相同的整个target-window字典（实际样本
  667–2344个目标窗）。将query/target清单在每个PAF流建一次，并在producer、verify replay共用
  `_projected_lines`；原`project_regional_paf`、CIGAR/坐标验证、artifact/行号、原序/字节和SHA复核
  都保留。`q0_query_windows.py`、`q0_alignments.py`及raw/projection规格未动，原coarse、raw和project
  路径仍由同一键生成，不触发已完成窗口换身份。Q0外层builder身份仍按源码正常更新，不能假装
  在跑进程已加载补丁。测试守护清单只枚举一次、注释/空行后原行号、两向投影/真实mapper和已有
  cache读取；本地针对27项及隔离Linux fixture齐全的311项（310 pass/1 skip）通过。
- **实样投影ABBA 43013115 SUCCEEDED / agent-X86-61**：独立验证并读取12窗原raw 1710494 bytes，
  6个中等/6个目标窗最多的case；48次渲染输出逐case SHA/行数一致。聚合CPU由1.519→0.905秒
  （**投影子步骤少40.4%**；大清单6例少57.4%）。仅内存内的投影而非mapper、读盘、整麦或重启净收益。
  `regional-projection-inventory-20261122.json` SHA
  `bbea75c4012b391705d3b9945b2f0dfd3fdc701d9e0f113bab3039f211b3b075`，verified绑定原调度终态、源码
  和远端manifest。未安装到活跃任务；不为1个子步骤收益支付已付过的串行前缀、提交或发布代价。
- **同节点只读43013119 SUCCEEDED**。旧FIRST缓存PAF在16:24:47→16:25:02读位从
  2639273984到2654502912/2666514061（98.98%→99.55%）；16:25:17同PID1966058、同start ticks
  仍R，原PAF的FD已关闭。原始`q0-first-reader-followup-20261122-162351/samples.jsonl` SHA
  `445059701f6aba23a250d3bc7a9d26bffa699da467cd285cc178000451967810`。这不是区域池开始的凭据，也
  不能凭FD关闭宣称整轮Q0完成。新版与旧42523432均RUNNING且未重启；下一次核实原生区域池实际
  admission、缓存回收及首批新raw，而非用61000或首轮文件速率硬给整麦ETA。

### 2026-11-22 16:35 CST：主作业实际进入14路区域池，继续核对新算产出

- 新版43012037同一run在16:31:07、16:32:37、16:32:50依次记录61→38117（既有快速矩阵）、
  9→38117、1418→52（既有原精度矩阵）。已核对三个`success.json`的历史提交时间、query/target
  数和原PAF字节大小；都是已有成果的本次消费，不是新跑了这些mapper。
- **16:33:45** 当前真实run日志打印 `phase=partial planners=3 mappers=14 mapper_threads=2
  total_threads=32 dispatch=completion_order result_order=original`，这确认实际启用了完成顺序补位，
  不是只预估池上限；但不能把启动配置等同于14路都实际忙碌或已产生新raw。等到计划/回收及新原生
  产出分开可证再估吞吐，不能把最初已完成缓存计为新增。原主job与旧基线均未停止或更新runtime。
- 已单独启动 **43013129**（x86，7CPU/16GiB、每mapper4GiB AS、2线程），独立目录
  `q0-regional-dp-cap-ladder-20261122-163020`。在三个不同源part已归档、已逐字节验证输入的
  样本上，保留所有原目标和`-P`、`-m`档位等选项，只比较原命令/30m/10m DP cap。包含一个独立
  慢case及两个以前的慢case（密度命中/不命中），不全量重跑任何主数据；9项沿用测试在打包隔离及
  HPC通过，新增3项cap argv针对性测试本地通过。仍属隔离候选，主任务未改生物学参数。
- 临时只读1CPU `43013145`检查启池后进程、输出位置和节点资源，等确认后再评价实际并发或是否
  有共享盘开销；不调试attach、不读取DNA/PAF内容、不抢占主任务线程。

### 2026-11-22 16:47 CST：区分活跃缓存回收与新增比对，去掉验证器内重复哈希

- 主43012037同一run在16:46:41已报**1000/61000、fallback=0**；旧42523432仍RUNNING/grt_step2。
  16:35:52–16:37:23作业43013145观察到reader线程增至17，打开了旧区域PAF，4个采样点没有看到
  原生mapper（仅短采样，不排除间隔运行）。原样本SHA
  `5673f86e221e1d10492711f30b4569b7e1601502cd6abf07875369f0faa77488`。截至16:47:45，
  区域context/project顶层mtime和链接数仍与12:03切换前一致；16:46:37封存稳定命名边界
  `q0-live-regional-boundary-20261122-164637/boundary.json`（5457个context、5981个project名称）SHA
  `ff1ac61ea5a853e9876ea8d69f645e78c8a750805bfb27be2bc6eb6e0ef8d3f3`。隔离`delta.py`仅看
  目录及小型完成回执，未验收所有内容，不把名称当作完成marker，也未证明现存不完整context内没有
  新raw。暂未确认新原生结果，1000是阶段回收总计，**不作为新增mapper吞吐**；待新命名/回执后关联合格样本。
- **43013129 SUCCEEDED / agent-X86-65（16:42:40）**。三个同节点原参均与历史原PAF逐字节一致，
  新增30m cap仅精比对CPU分别47.676→22.842、235.472→50.168、170.799→23.630秒（2.09/4.69/7.23倍）。
  30m均未丢跨组装core并集或整组≥1kb，并非无损：独立样本跨组装目标组少893/23642bp（3.78%），
  另一慢例少25bp；密度阴性的第三样本原无跨组装高质量支持，组装内部core仍少947bp。该case
  同时证明链密度不是覆盖所有慢例的判据，不用一个阈值授权全量近似，不启动重跑。
  `regional-dp-cap-ladder-20261122.json`复核SHA
  `9c868e678b47947c38332c41812d4d37911f193b917a07896e600a239d699f34`，主科学策略未改。
- 区域独立验收器先对chaining/raw叶子的PAF等做完整identity，随后为project完整闭包再重读
  同一批文件。补丁在一次调用中先验叶子规格和清单，再对完整project闭包统一验真，叶子每份
  输出和其receipt身份必须与已验证的闭包逐项相同；仍全量做coarse统计、命令/guard与raw→project
  CIGAR几何重演。不跨run记忆mtime，不以清单/缓存命中替代哈希，规格、现有raw/project键不变。
  新测试覆盖3份PAF各只验一次、解析器会忽略但哈希必须发现的注释漂移，以及仅叶子SHA与已验真闭包
  不符的反例。27项定向测试通过，Linux隔离fixture齐全Q0共312（311 pass/1 skip）。
  首个隔离作业43013152缺失自身旁边用于验证源文件hash的两个模块，未做出结果；重提43013158时
  完整补齐两份同版本原文件并以manifest核验，不伪造源文件绑定。主运行未安装或重启。
- **同节点真实闭包验证ABBA 43013158 SUCCEEDED**。8个冻结既有project（4个中位、4个最大raw
  PAF），两版每个case都返回原同一完整receipt。每轮汇总PAF identity调用40→24，全部identity读取量
  85.63→54.52MB（**少36.3%**）。A两轮59.443/51.519秒、B两轮39.433/33.133秒（均值耗时
  少34.6%）；CPU14.421→14.301秒。这是8个已完成窗口的独立验收路径，不是整轮续跑或整麦提速率，
  不包含其他阶段或完整工作区读写。原始`regional-verify-closure-20261122.json` SHA
  `db04a965326d89d989a7856f24685431bf166e18863a8021ef6f01e1b1c12fcf`，verified绑定源码、作业
  终态与manifest。仅合入仓库、不为此重启现场的活跃缓存消费和后续计算。

### 2026-11-22 16:58 CST：缓存命中的完整核验只做一次

- 区域生成端即使已经存在完整project，仍先用`_reuse`读/哈希全闭包，随后用同一个独立
  verifier再验同一完整闭包。现在完整命中直接走一次独立验收；先前coarse/raw叶子的独立复用
  和最终coarse选择/命令/CIGAR几何重演仍保留。失败后不混淆可修复的投影缓存损坏与科学/规格
  不符：原闭包若内容确实不符，才按原流程保留坏目录、从已验原生raw重建；完整SHA匹配但几何或
  命令不符仍失败。命中不靠mtime、未改参数/清单/内容键，也未跳过下游发布验收。
- 新测试锁定完整cache路径只读project PAF一次、原raw/coarse仍各由叶子与终验核对；另确保
  “内容SHA正确但多出合法PAF行”必拒绝、不伪装为cache miss。29项定向测试通过；隔离Linux目录
  的fixture齐全Q0共314项（313 pass/1 skip）。原版本输出、复用无mapper和修复坏project测试仍通过。
- 主43012037继续用原冻结代码；不把此修改称为现场已安装。16:55:51仍无新context/project名称、
  新版已报1900且fallback=0，旧42523432仍RUNNING。缓存回收次数不作新比对速度。
- **43013168 SUCCEEDED / agent-X86-61**。同8份真实归档、同节点ABBA，上一版`33e0f8bc`的
  project预查+终验对比一次终验。4轮全部接受同一原success receipt；这一段的PAF哈希48→24，
  全部identity读取量106.96→54.52MB（少49.0%）；A 63.093/49.147秒，B 50.630/53.926秒。
  平均56.120→52.278秒（少6.85%），在样本间共享盘波动内，不承诺稳定或全程速度。仅测投影
  cache命中到独立验收，不含之前coarse/raw叶子判断、整个续跑或新比对。报告SHA
  `87947354efb4734696d21409689c038fc31fe1d19d2acd5f4412daf5a1257366`；上一诊断源码仍可按
  `33e0f8bc`及其绑定SHA获取，当前benchmark仅新增显式`--projection-cache-hit`对照。
- 截至17:00:19主阶段报2400/61000、fallback=0、无新失败；稳定命名边界仍无新context/project，
  不能拿该速率估新增或总耗时。两主作业均RUNNING并保持原作业与策略。下个检查优先追真正的新
  raw/project成功回执和预算，避免将每轮前缀验收误当成重新执行，也不为小型I/O改动重启。

### 2026-11-22 17:08 CST：消除 Q0 最终证据依赖验收的二次方路径

- `load_verified_evidence()` 把 `inputs | set(outputs)` 放在逐证据行的生成器内部：每一行
  都重建一次完整文件路径集合。即使所有文件已核验、所有记录都合法，仍做
  `O(证据条数 × 文件数)` 无效工作。Q0证据载入、构建后复核以及准备下游输入均经过这条路径，
  不只是区域mapper的单窗热点。现用已完成索引的 `inputs` 集合和 `outputs` 字典逐条查键，
  保留任一路径已绑定即有效、两边均无则报错的原语义，额外开销与证据行数成正比。完整SHA、
  清单、命令、CIGAR几何与后续消费规则均未修改，raw/project键不变。
- 受控CPU微基准直接提取变更前后的实际成员检查语句，使用冻结trace的路径形态扩展为1万/5万输出
  条目，各2000证据条目。ABBA平均原检查1.17/9.61秒，新检查两组均<1毫秒；追加未绑定项时两版
  均拒绝。无PAF读盘、无比对；只用于避免数量增长的算法风险，不是整麦/现场验收倍率。真实端到端
  任务未结束，不对实际总节省外推。加入绑定输入、绑定输出和SHA一致但无绑定路径的集成测试；
  preparation+regional定向47项通过，隔离fixture齐全Q0共315项（314 pass/1 skip）。
- **不热改当前job。** `q0_preparation.py` 属于本轮启动前捕获且出版前重新计算的builder身份；
  运行中换文件会导致阶段收尾的身份核验失败。即使等上游产出后切换，也必须走显式等价迁移并保留
  原输入、产物字节和旧回执；绝不因提速直接放宽旧builder验收。先等实测以及受保护边界。
- 17:07:51观测同run `43012037` 为RUNNING，进度3100/61000、fallback=0，无新失败；截至这个
  采样仍无新顶层窗口context/project路径与可确认的新比对回执。已在已冻结的命名边界目录附加
  41次/每分钟的有限只读采样 `live-window-delta-1707-v2.jsonl`、关联既有观察器run ID；不提交
  新计算任务，不扫描PAF/DNA，也不把路径差异当完整验收。仍不能给可靠整套ETA。旧42523432
  继续运行、没有修改。后续只在出现新的原生完成证据、实际瓶颈或故障时决定是否再定点切换。

### 2026-11-22 17:32 CST：新版已开始新算窗口；区别冗余命中和用于排除错误的证据

- 新旧作业 `43012037` / `42523432` 均仍运行。新版17:30:15报 `5500/61000`、`fallback=0`。
  17:26之后观测到本轮新提交的raw成功回执，已抽查回执SHA及`result.paf`声明，不再只是读缓存；
  17:31:56命名边界增量86个context、76个project，抽样上限16份raw回执。名称计数与回执样本
  都不是全量验收，本轮精比对阶段的新吞吐尚需独立观察，不能使用前缀复用速率估剩余时间。
- 不以“最终用了几条”决定能否限精度：`qualify_pair_blocks` 的竞争门会检查未入选的相反方向或
  不同坐标映射；丢掉它们可能意外放行原本不唯一的连接。新增隔离重放工具，从三个既有慢窗的冻结
  原/30m/10m PAF调用真实区域投影及配对门，按源对、方向和仿射映射分别统计失去与新增的合格
  块，包括原先观察到但未通过的新合格块。它没有上下游全量证据或真实参考锚，不是完整组装验收。
- 原竞争扫描反复展开并扫描同一源对的CIGAR。改为两侧分别建索引，只比较阈值以上的单条paired
  block，以不同映射的前两名可达端点识别竞争；不合并短CIGAR块来伪造阈值、保留反向/双向以及
  同一映射不自我冲突的规则。随机300次新旧完整有序输出一致；64条、320个无竞争块的ABBA
  微基准0.291→0.00566 CPU秒（合成的资格检查，不能外推整麦）。路径/准入/出版定向测试通过。
- **诊断独立运行**：原扫描重放 `43015130` 触发240s诊断上限（`errCode:124`），没有完整报告；
  `43015235` 在既有原生输出上同节点逐调用比较新旧门的有序返回，仍待终态。不重算比对、不重启
  主任务、不替换现有runtime或旧版基线，也未放行任何30m生产档。

### 2026-11-22 17:49 CST：配对门发现精度风险；新算窗口先查启动开销

- 隔离 `43015255` 已 `SUCCEEDED`。同一组冻结原/30m/10m输出投影后，由索引版真实配对资格门重放，报告
  `regional-dp-cap-consumer-20261122.json` SHA `6fcd254a0695df5c8579a9b7c838ccd68fdb8057d43678689a7be91a264371ba`。
  30m 在样本1的中性跨组装源对上丢失40,855个按方向/映射分别并集的合格paired-bp；在样本72中，原档已
  观察但未通过竞争门的362跨组装、1,324组装内paired-bp在快档中变为合格。不能将它们与新增覆盖抵扣，
  也不能当作丢失/错误拼接的真实组装bp。未加载真实参考锚、其它窗口或完整Q0路径。`43015235` 的逐调用
  旧门复算 hit 360s诊断上限，**没有**全样本新旧实件等价结论；已有本地等价测试记录不受影响。
  不给混合目标窗口全量启用30m；后续只测独立intra作用域和完整路径决定/补洞变化。
- 新任务17:37 sidecar中16个新raw回执摘要见 `regional-live-stage-latency-20261122.json`。每窗输入5.2–46.4MB；
  contextual FASTA清单完成→raw成功的中位40.38s，其中精比对原生日志中位5.60s（含native内部I/O），15个
  有chaining的粗比对中位1.36s。命令提交文件→原生最后stderr，减掉mapper自报wall，中位粗14.41s、精14.07s；
  另有少数post-native回执尾部。不把文件时间差当函数级因果、CPU时间或随机抽样ETA。
- `43015251` 只trace本诊断派生的子进程，未attach任何主任务进程。3GiB分支前命中170s诊断壁钟，留下完整
  8个轻父进程对照：`Popen`/`posix_spawn`/显式fork的启动调用返回均小于0.13s，首个Python用户代码仍需
  8.91–11.85s，`-S`也未消掉主要耗时。不是证实“大父进程fork慢”，不要为此放松FD关闭或内存保护；
  引导/动态依赖/共享盘因素继续查。trace `1a6647925b479bf4b71ea6111db0df52a33b90183d4cd4e3a01e1ea3f7b345ea`。
- 同节点真实原生复跑正在比较原guard、系统Python、系统`prlimit`（`43015254`），以及仅mapper子进程的
  `LD_LIBRARY_PATH` 环境对照（`43015257`）。登录节点上当前minimap2与guard Python两种搜索路径的依赖解析
  位置相同，但仍需计算节点与真实PAF/资源边界验收；不全局清除环境、不碰samtools/MUMmer和旧版。
  未改远端两个主作业、缓存/checkpoint或科学参数。
- `43015254` / `43015257` 均已 `SUCCEEDED`。同节点一个归档普通窗，所有10次真实原生PAF与历史逐字节一致，
  4GiB soft/hard限制和工作目录独立验证通过。仅清mapper子进程`LD_LIBRARY_PATH`的ABBA墙钟24.750/20.732→
  11.501/9.512秒（均值22.741→10.506秒）；减掉各自原生日志墙钟后的差额均值18.201→6.000秒。系统Python或
  prlimit也有局部收益但没有消掉继承的动态库搜索开销；不更换机制或移除资源限制。报告
  `regional-launch-scope-20261122.json` 含两次原报告SHA。主job所在agent-X86-39上独立复验`43015264`已
  RUNNING，检查原/候选的ELF依赖路径和文件SHA再测3窗。单个归档普通窗的倍率不作为整麦或生产验收。

### 2026-11-22 18:06 CST：主节点无损复验通过；真实补丁已stage，现有作业继续运行

- **43015264 / agent-X86-39 / SUCCEEDED**。主任务所在同一节点三份归档普通窗、同一mapper及原科学参数，
  6次真实输出各与其原PAF SHA一致；原和候选的ELF依赖解析位置及实际文件SHA相同；独立验证工作目录、4GiB
  软/硬限额。平均墙钟 **19.05→8.55秒**（三窗，非整麦）；扣原生日志墙钟的差额均值 **15.81→5.14秒**。
  原报告`eda54fb84f1bc24e8d3558da2e31554ec9dd28d5cce73b57d402921d0954ccf8`，依赖证明
  `995486813b2904d31d2c29144ab426c2b864be5f27e67638aae2dec1e18cbf23`，归档摘要
  `regional-launch-main-node-20261122.json`。不把诊断结果当主任务产物，也不调整30m精度档。
- 已推 `99843b65`。区域CIGAR/粗筛共用 `_execute`，仅显式绑定的事故reader启用loader同依赖核验。
  在目标job重新核对Python、resource和mapper解析到的运行库路径/内容；探测失败或启动环境/mapper
  不再匹配时保留原环境。只给该子进程传入环境副本，不改全局、其它工具、实际argv/guard/科学policy；
  command receipt记录选择和依赖摘要，独立verifier验证来源字段，不使已有raw/project失效。
  本地66项 Server +97项迁移/reader定向测试通过；未跑整版CI、未发release。
- 真实隔离目录 `q0-child-loader-cutover-20261122-180258`；source SHA通过校验、候选transition
  **95c2b13113ee94f7f4fb6fe17d484c5797163a0115a72a862a38e6ca7e2fe497**，prior安装
  `030694dff7efe342927c2ad74091df273a8b069dbd15197d45afe08bd714603c`。14模块中只有
  `q0_regional_mapping.py`（子进程和现有等价投影/验收修复）和`q0_preparation.py`（线性成员核验）改变；
  12个原模块保留748版本、4项policy AST一致。证据 `q0-loader-cutover-candidate-prepared-20261122.json`。
- 只读真实25个初始检查点预检 **43015292** 已启动（测试输出里的`initial:*`不是生产节点验收）；真实
  writer/旧project复用 smoke **43015291** 已验过两个真实旧窗口完整project闭包并原样返回。初版smoke用
  精比对argv删`-c`推导粗比对，遗漏两者`-m 2000`差别，**不得**引用其粗比对为生产等价；以改为从SHA
  绑定原粗比对回执取argv的独立诊断 **43015295** 为准。未就绪前不能停止主新版，两个诊断的超时/失败
  与主任务无关。旧42523432不改；43012037同run在18:03:32达6100/61000、fallback=0，仍在运行。
- 下个动作：确认43015295真实粗/精PAF完全相同、新执行命令含经核对的环境来源、旧两个project完全可读；
  确认43015292生产25项及末尾validation.json。两者通过后才能申请32CPU/320GiB等待资源的主切换作业；
  在新job真实节点重新验证loader兼容、成功写ready且保守净收益为正后，再正常停止当前新版与等锁释放。
  不重跑已有比对、不删除cache或锁，不改旧基线，不重放旧handoff/旧installation。

### 2026-11-22 18:16 CST：真实粗/精writer验收通过；切换资源门已准备，主作业未动

- **43015295 / agent-X86-39 / SUCCEEDED**。纠正试验命令后，真实候选 `_execute` 按SHA绑定的原粗、精argv
  在隔离产出中各得到逐字节相同的历史PAF，均记录已核对的子进程环境、保持原4GiB guard；候选独立读取
  两份旧project完整闭包并原样返回。`regional-loader-writer-smoke-20261122.jsonl` SHA
  `04128820aef899c062bdbe0aae39ba3cd3408e2daeae77edf25c612a2060f861`。被替代的43015291仅为
  粗测试命令带了精比对的额外参数而失败；不据此认为生产代码或在跑的任务失败，不采纳任何诊断PAF。
- 新资源门 `prepare_q0_loader_launch.py` + `probe_q0_loader_allocation.py`：准备真实25项校验完成后的独立
  启动脚本，先比较旧/新校验全清单（包含每项input fingerprint与checkpoint SHA），随后在**实际新分配节点**
  核对装载库、mapper路径/SHA/`--version`与既有region key（同SHA不等于version不会超时成为`unknown`）。
  必须先有 `loader-ready.json`，再进入原资源门 `ready.json`；原旧进程未终止/有pids/有锁时仍不会安装。
  新配置只准备/校验，不会自己停任务、改数据或提交。针对性6项本地+180纯fixture测试；真实新资源还未申请。
- 只读预检43015292（不是主新版）18:15仍RUNNING。`43015567 / agent-X86-18 / SUCCEEDED`：仅观测
  绑定当前UID/作业的`/proc`元数据，PID3640947连续3次D状态但50秒CPU ticks 600→688，`rchar`
  85.4→95.5MB，不能认定卡死/崩溃或具体大文件，保留预检继续跑。报告
  `preflight-readonly-181454/samples.jsonl` SHA `fb727e077c8ff7092389f43872cdba4b676d1717ab7aa67fffe3ec76ba43ca72`。
- 现主新版原run在18:14:37 **6300/61000，fallback=0**，过去 ~100个/5–6分钟；旧42523432仍RUNNING
  且不动。仅作切换成本参考：按历史首个新raw约5h16m、留6h、14个mapper槽和保守扣除2573完整矩阵
  可跳窗，目前要平均省约5.8秒/待做窗口才能覆盖恢复成本。三份真样本只精比对即省约10.5秒/次，另有
  粗筛和验证收益，值得继续走预检；样本与理想并行测算不保证端到端，切换时重核实际工作量、资源和收益。

### 2026-11-22 18:29 CST：续跑预检仍在核对绑定；移除通用文件身份的重复路径解析

- 主新版43012037、旧42523432均仍运行；18:25:16 新版报6500/61000、fallback=0。43015292只读预检
  尚未提交最终`validation.json`，不能用测试fixture里的25项冒充真实校验。没有申请新32核主资源、没有停现job。
- `43015880 / agent-X86-18 / SUCCEEDED` 只采同UID、同作业cgroup及确切启动tick的只读预检PID3640947，
  不暂停、不读locals、不向主任务发信号。18:23:12先观察到`SelfBindings.verify(full=True)`逐个命令身份的
  `file_identity→file_signature→realpath`，18:23:37已进入`NativeBindings.verify_native_resources`的原包装/规格
  核验（`_sha256_read/open`），18:24:02仍在该模块的`expected_spec`匹配。其源/原输出的25项最终核验未过；
  不能把高I/O等待等同于挂死。report `preflight-stack-182148-v2/samples.jsonl` SHA
  `376872432559bb47700fee15f44b78df57d4fdd1ebac8c0e2e497062a87ab682`。初次43015877仅因诊断把
  相对的`resume_q0_science.py`参数误当非目标而拒绝，未读取不匹配PID或改动权限；修订后仍绑定实际cmd/cwd/job。
- 已推 `51febb4f`：通用`file_identity`的size/摘要共用同一次前与后路径签名，原4次resolve/stat降为2次；
  不去掉实际冷哈希、打开文件描述符前后的一致性检查，及命中后路径/设备/inode/大小/mtime/ctime核对。
  回归覆盖热缓存期间链接改向与冷读取后原子替换；47项orchestration/checkpoint/report定向测试，46通过+1跳过。
  冻结旧实现与候选在400个合成命令路径同字节ABBA，本地冷约54.5→35.8ms、热约54.7→29.2ms（非现场倍率）。
  实样小文件只读ABBA `43015894`仍RUNNING；不修改受绑定的远端`run_orchestration.py`，不把这项混进已验证的
  两模块loader候选或冒称已减少本轮真实预检时间。

### 2026-11-22 18:36 CST：准备条件式资源申请，不提前打断在跑任务

- `43015894 / agent-X86-61` 在360秒诊断上限到达后终止（errCode 124）。最后一个热baseline未结束，
  **不是完整ABBA**。其余7段均逐项返回503个原冻结命令文件完全相同的 `path/size/SHA`。冷路径A
  55.78/45.28s、B 33.97/33.33s；热只列实测 A 44.48s、B 12.37/12.74s，不计算完整ABBA倍率。
  每次完整清单的真实路径签名调用2012→1006；CPU时间仅0.2–0.56s/段，说明此处样本主要在等文件系统，
  这不是25项预检或整麦加速结果。`q0-checkpoint-identity-scoped-partial-20261122.json` SHA
  `575ea11f19cde03a0c062a01e622bb3461387e2b4f0026a7b8f6c1b372688569`，全stdout/调度终态/源码留在
  当前cutover下`identity-abba-182603`。`51febb4f`仍未热改远端保护模块或加入当前切换。
- **登录节点观察器PID1991023**（已复查PPID1、存活；脚本来自 `bba04342`），首条18:35:38；目录仍为
  `q0-child-loader-cutover-20261122-180258`，`loader-watcher.log` / `loader-watcher-config.json`，后者SHA
  `8f7a60afec103d8dfa519de201fe83f4728c157f52187f60646fda6ac6957775`。有界45轮、每分钟按同一作业查询。
  只有43015292调度成功、43015295实样仍获成功、现新版43012037和旧42523432均RUNNING、主run/锁所有者
  仍吻合且Q0未完成时，才比较真实新旧25项内容身份并至多**提交一次**32CPU/320GiB等候资源。用独占
  `loader-resource-submit-intent.json`防dsub结果含糊时盲重投，以`loader-resource-submitted.json`读新job；
  仅观察到超时/失败不误认终态；若真实预检失败或任一来源漂移则不提交。10项相关fixture本地和180通过。
- 观察器没有stop/install/写handoff权限路径。新资源仍须在真实节点拿到`loader-ready.json`和正常`ready.json`，
  之后才由人工核对新旧job、资源、Q0边界、锁释放和净收益；不为抢节点提前停止正产出的43012037。
  如果已出现intent但没submitted，先查同一目录与调度器，绝不另起watcher或直接重复提交。

### 2026-11-22 18:45 CST：预检已进入染色体；避免后续Q0再扫无关候选对

- 新版43012037同run 18:45:16 `6800/61000`, fallback=0；旧42523432仍RUNNING/grt_step2，均不修改。
  只读43015292已完成前4项（两份参考、assign、1A），18:38→18:45 CPU累计329→465秒，真实前进，尚未
  有最终`validation.json`。单次诊断上限不等同主任务故障。PID1991023仍轮询原作业，未申请新资源，
  没有`loader-ready`/`ready`/`handoff`；不得提前终止当前新版。
- `811266f5` 把后续 `q0_admission` 的跨chr尾候选、同chr连续性、分轮扩展与anchor扩展四处
  全placement枚举改成只连接**实际存在证据的源对**，共享双向link列表、保留同源排除和整个竞争集合、
  按原placement快照顺序交给原准入条件。`construct_q0`还改为一次按两端源共同候选染色体分发PAF
  记录，避免每条染色体重扫跨组装全量；各图仍保留相关原顺序、所有方向/冲突和非重叠同源的可能连接。
  不少算已观测证据，不变参数和精度。80项路径/准入/出版定向测试通过；隔离旧模块与新模块完整
  fixture对照18项序列/路径和决定完全一致（只剔除应因源码变化而不同的selector身份），4个边界同样
  拒绝。稀疏合成2500候选、5000 links的邻居枚举单核2.70s→4.9ms（不含其余Q0计算、不能当整麦
  倍率）；没有拿当前6.8k mapper进度宣称该候选已生效。这是后续selector优化，未装入远端当前或已
  冻结的loader切换包；不得在其已经捕获selector身份后热替换。

### 2026-11-22 19:10 CST：只读预检到既定上限，保持两个主任务，再跑同一套核验

- `43015292 / agent-X86-18` 已由 Donau 确认 **FAILED / jobExitCode 124**，终态时刻 19:05:29 CST。
  这是 `preflight.dsub` 内 `timeout 3600s` 的退出，不是观察超时，也不是新版主任务故障。日志中真实
  参考、assign、染色体检查点共通过 **11/25**；`initial:*` 仍是测试条目，不计入。无 `validation.json`，
  这 11 行不作完整检查点证明。原观察器 PID1991023 遇预检真实失败退出，无资源提交 intent 或切换产物。
  原 Donau JSON 已封存 `preflight-43015292-terminal.json`，SHA
  `3be9587f7e1c0b7b50c11d6020139e32a4334c855b6de8ff949516fa89afbae7`。
- 在同一隔离候选目录只增加 `preflight-3h.dsub`（SHA
  `b6f8efcad327ec6f1dc2c29225a6d6db6dde21b3424f331d097b2e2dc0860723`）：除独立名称/日志，从 3600s
  调到 10800s，真实源、校验代码、25 项检查条件和 2 CPU / 16 GiB 都不变。不以历史日志替代这次校验，
  不提高或给生产 mapper 引入超时。原新旧作业、主锁 run、smoke 终态及未发布 Q0 边界验证后，以独占
  intent 单次提交 `43015921`，19:08:56 已实际在 `agent-X86-18` 起跑。提交回执
  `preflight-3h-retry-submitted.json` SHA `5bf23ed061d8db52ef0097e42632d6f4812f8c94375159d502172bbf2cd475b0`。
- PID **3458598** 是复用原脚本的 120 轮、每分钟只读观察器；`loader-watcher-3h-config.json` SHA
  `2fe731ef11857fb728405dc8a0fae4485bfd70b8a5a695bbf5ed37c039aed21b`，日志 `loader-watcher-3h.log`。
  仍仅在完整预检、实样、原锁和调度终态门禁通过后申请一份等待资源。若约 21:08 观察期结束而预检仍活，
  查询同一作业，不重投；若出现提交 intent 先查调度及 receipt；若只读通过但没有观察器再按原门禁续接。
  有待验证的资源就绪或 staging 不代表应立刻停止 `43012037`，仍需重算剩余有效窗口、实测增益和切换成本。
- 19:10 两个生产作业均 RUNNING；新版 `43012037` 最近 `7100/61000`（19:04:53，fallback=0），
  旧版 `42523432` 未改。无整版替换、CI、发布，旧基线未触碰。

### 2026-11-22 19:15 CST：消除区域 mapper 和固定投影代码的重复全文件读取

- 仓库候选把每次 coarse/precise 前后同一 `minimap2` 的全读 SHA、同一 projector/validator 代码在
  生成/回放中的重复全读，以及全原生补充路径的同类工具复核，改用已有的进程内稳定摘要 memo。
  第一次必须打开真实文件并核对 fd 前后身份；命中仍核对解析路径、设备、inode、size、mtime、ctime，
  变化回到完整读/hash。不改 mapper 参数、结果路径、PAF/guard 验收、科学命中或 checkpoint schema；
  子进程执行前后仍分别核对。新增真实两次 mapper 测试仅冷读工具一次，同时测试运行中改同尺寸字节并恢复
  mtime 仍拒绝写 success。六组定向测试 89 项通过，全部 `test_q0_*.py` 327 项中 326 通过、1 跳过。
- 只读 `43015930 / agent-X86-18 / SUCCEEDED`：冻结真实 1,326,552 字节工具与两份现用静态代码，
  不读序列、不起 mapper。每臂各文件 48 次、144 次 SHA 全同，直接读 A1/A2 **6.274 / 6.081 秒**，
  稳定 memo B1/B2 **0.239 / 0.018 秒**（第一臂也做真实冷读）。隔离目录 `runtime-digest-abba-1912`，
  `bench_43015930.out` SHA `86863dc78fe5c689fbd2d47bc971cc95144cc4cc6bc353608cc25658b86aa3b5`，
  `manifest.sha256` SHA `54928d224ce752842ab1664979bc868a391a7a331bf0dbeec5ddc7dd45fe8f9c`。
  局部收益依赖文件系统：WSL 挂载目录的小脚本测得 memo 的多路径分量 stat 比直接读慢；不报整麦倍率。
  此候选不混入当前冻结的 loader/preflight 包，不为它重启主作业。
- 19:15 已实时确认新版 `43012037` 最新 **7200/61000，fallback=0**（19:11:24），旧版 `42523432`
  与同一只读预检 `43015921` 均仍 RUNNING，PID3458598 仍在轮询。无新资源提交/手工切换。

### 2026-11-22 19:24 CST：用相同核数验证更多普通区域 mapper，而非加速超长任务

- 保持两个主作业及 `43015921` 预检。`43012037` 19:18:09 最新 **7300/61000，fallback=0**；19:23
  Donau 单节点实际 32 CPU/327680 MiB，近期 CPU 141% 只是瞬时采样、不能代表整个阶段；当前/峰值内存
  89156/91863 MiB、swapMax 0。没有凭这个总峰值去加长序列并发。
- 独立作业 `43015934` / `agent-X86-08` 已实际获得 16 CPU / 81920 MiB，隔离目录
  `q0-regional-thread-split-20261122-1922`，`allocation.json` SHA
  `d98ceef9f7df5f1c7794df5ab2f20d086a409abf75bdf21f114ae8016cb2ba8e`。从此前完整旧归档中按真实
  precise 耗时分层固定 28 条有 coarse+precise 的普通窗口，直接用已验原 SHA 的窗口 FASTA，不重新拆整套
  DNA。ABBA 同节点两档 **7 路 × 2 线程 / 14 路 × 1 线程**；两档保守使用同一 14 线程预算及每路 4 GiB
  AS 原 guard。只改 `-t`、资源分配及归档读路径，原 preset、chain 策略、目标、PAF 顺序均有独立核对，
  每个真实 coarse 和 precise 的完整 stdout 都必须逐字节等于各自已完成原 PAF；任何不一致就不采纳。
- `job.sha256` SHA `de42c4ee2183cf11908f2535ddc0dca6eea6b81378626af61c9a01d1a7adc18b`；
  本地八项试验 helper 测试通过。该试验测两段原生子步骤和调度，不包含生产 owner 的大堆、规划和消费；
  不预先改主任务，不把 14 路诊断结果换算成所有长序列并发或整麦倍率。若真实有效再按 32 核生产配置重算
  owner/规划/地址空间和文件系统余量及切换净收益。诊断 15 分钟上限不适用于主任务。
- `43015934` 19:25:27 终态 FAILED/1：本轮新增的两项 helper 测试均通过，但作业还声明调用了旧
  `test_benchmark_regional_mapper_dispatch.py`，该测试文件未在首份 staging manifest 中；原生 ABBA 未启动。
  已在 `q0-regional-thread-split-20261122-1922-r2` 定点补齐该文件，并按脚本实际调用核对四份 Python
  文件和环境 SHA。`job.sha256` SHA `a43b269b0c86229a55fa56a3cf307c91c6bc5c55a7ac67f5ab57c532138d462a`，
  旧作业终态 JSON SHA `a216cf6079ba0a0b6669b0ce765896bf38e3f0c8faf91c9a34873bee18723f64`。
  同一方案 `43015937` 19:26:38 已在 `agent-X86-08` 启动，真实 16 CPU/81920 MiB 资源证明 SHA
  `ab262552233f98043413c8c96ff23f12d73f468516fae63c62850f49300377da`；续查同作业是否有 `inputs_verified`
  及 `artifacts/report.json`，不把 RUNNING 当成性能验收，不再提交其他等价试验。主新版仍独立产出，19:24:36
  达 **7400/61000，fallback=0**；预检 `43015921` 仍在运行，未触碰新旧主任务。

### 2026-11-22 19:36 CST：两档并发诊断按原始参数顺序核对；减少 FASTA 逐行写入

- `43015937` 的远端八项 helper 测试均通过；随后在首个实际精比对参数绑定拒绝、终态 FAILED/1，
  未启动任何 mapper。原因是试验脚本把 raw receipt 的 `-c` 放在 `-x asm10` 后，而实际原命令是
  `-c -x asm10`。不是比对差异、主故障或 OOM。不放宽参数检查：分别验证 coarse/precise 原始格式，
  固定所有 flag 位序后再替换 `-t` 和隔离归档路径。本地八项通过，登录节点仅仅读 JSON 已将同一组选定的
  **56 个真实命令**逐一与两个 arm 对齐；没有读 FASTA 或启动 mapper。`metadata-precheck.json` SHA
  `d0472299c2641857eb2d8c2235f48652572ee658933986a9a4225c25140b2e83`，旧终态 JSON SHA
  `4f2b78a1028329ad7250643e3282532244b6554e817a0da43cc37c9e81e8722a`。
- 隔离 `q0-regional-thread-split-20261122-1922-r3` 的同一方案 **43015966** 19:33:42 在
  `agent-X86-57` 起跑，已确认 16 CPU/81920 MiB 并放行同一作业，完整资源证明 SHA
  `6e8dbe855d80f476aa3fff8a8729cfec89fb09f7e53ae61cb0474a3feadfa652`；`job.sha256` SHA
  `dea22d11d515fb6f492dcd0ac75715ec648a91e48c2e479938d9f9d9183fe4c4`。已过 x86 参数门禁，
  仍在输入核验，无测速结论。之前作业未得 mapper 输出，不做时间对照；继续查询 `43015966`，不重投。
- 仓库 `lgz_core.common.write_fasta` 仍是原 UTF-8、LF、80 字符折行；每 1024 行成块写一次，
  不复制整个 contig，不省略输入和 SHA 核对。两项新测分别覆盖输出同字节、分块上界；连同区域 mapper、
  evidence preparation 和 GRT prepare 共 64 项通过。641 条/17,077,468 字节合成窗口同 SHA，
  实际新旧 writer 在本地临时盘 ABBA 四次 33.26/17.34/21.40/35.22 ms。是写入 CPU/接口开销，
  不是共享盘实测或端到端时间；不改当前冻结的 loader/preflight 包，不因此重启。
- 19:36 新旧主作业及预检 `43015921` 均 RUNNING；新版 19:31:30 达 **7500/61000**、fallback=0。

### 2026-11-22 19:50 CST：核实可单独降精度的目标范围，同时让并发对照完成回程

- 主新版 `43012037` 最近 **7700/61000**（19:44:35，fallback=0），旧版 `42523432` 仍运行。
  此前约一小时实测 900 窗口/小时，取 19:38 的 7600 作为见证点；不是 mapper 进程数或整套进度。
  当前同一只读预检 `43015921` 仍 RUNNING、PID3458598仍跟踪，未触发资源提交/安装。
- 抽查当前 `43012037` 早先新提交的 32 份、由观察快照 SHA 绑定的实际成功 raw 回执，**12** 条
  精比对有 `-m 2000`，20 条维持原档。不是随机抽样，不能用 12/32 外推或指称利用率触发；是现有
  自动弱链工作量门禁。尚未启用更强 DP cap。最终未选中的证据仍可能阻止歧义连接，不能以利用率单裁。
- `43015966` 已完整核验 28 窗/776,558,919 bytes，A1 7×2 **212.433s**，B1/B2 14×1
  **163.538s / 158.850s**，三个已结束 arm 的粗/精 PAF 每份均匹配原字节。A2仍RUNNING，未见
  完整报告，不能据前三段当作最终吞吐验收、不能推整麦速度。新增本地真实 mapper 回归：已提交的
  1线程 coarse+precise/project 用2线程预算续跑，阻断任何 Popen，依赖和原 task 完整复用；
  mapping/执行 33 项测试通过。无生产资源或精度改变。
- 先核实“组装内专用降精度”有多大可行范围。`measure_regional_intra_scope.py` 对已冻结的1189个
  完成raw回执和 context 逐份按 SHA 绑定，按原始 lookup 区分纯组装内、纯跨组装、混合；统计旧
  native >=30s 长尾，不把目标碱基占比解释为真正耗时、证据利用率或充分性。没有读取任何序列/PAF、
  没有再次跑原生比对。不把混合任务当成可全体降精度；先量范围再判断有无必要做分拆对照。
  登录节点实样 7 个均是混合，其中一件历史 229.263s、组装内237,711bp/跨组装153,851bp；
  只是预检，不外推。局部两个测试和旧 helper 共8项本地通过，后续计算节点两个范围测试也通过。
- 隔离 `q0-regional-intra-scope-20261122-1947` 作业 **43016008**，1 CPU/4096 MiB，19:47:10
  在 `agent-X86-18` 启动，仍 RUNNING。`job.sha256` SHA
  `2649006e1d315e8d64b881c89a7db6b6b7f8f089427d36536f3abbd912fb96bf`，`smoke.json` SHA
  `3f548f727e5b5042243c59caa3dd07bacd04fbf0028b793753d4db86f02486f1`。以同一作业终态和
  `full-scope.json` 验收，不再提交同类扫描。
- 19:51:03 `43015966` 已真实到隔离诊断上限，终态 FAILED/124；不是主任务故障，未生成完整 ABBA
  报告。第四 arm A2 日志有 28/28 coarse、25/28 precise 的原生结束行，但不作为完整 SHA/回合验收。
  已完成的 A1/B1/B2 仍是 168 次全 PAF 字节核对；B 两次相对唯一完整 A1 各少约23%/25%墙钟，
  说明资源重分值得关注，不是最终倍率。终态 `terminal-43015966.json` SHA
  `0dfdc2eb5944269694b16035768636ee2d1c334638d4370704b2e063e0d961d1`，日志 SHA
  `647ddadcc153bcaac198cd22164ea3a1745b9088d90660d1a717ce38fa2a95fd`。保留原证据，不重跑整组
  实验、不据缺尾样本一次切入主任务。若需要补证，只补对照臂或做更贴近生产资源的有界验证。
  主 `43012037` 19:50:56 进到 **7800/61000，fallback=0**，只读预检与组装内范围作业仍运行。

### 2026-11-22 20:13 CST：排除整窗“组装内”近似路径，找到续跑 PAF 校验的小读瓶颈

- `43016008` / `agent-X86-18` 在 19:57:48 **SUCCEEDED**。按冻结的 1189 个已完成原始窗口逐份
  核对回执与输入 context，**1189 个全是混合组装内、跨组装，纯组装内 0 个**；原 `-m 2000` 497 个。
  这不是剩余窗口的随机样本，也不等同最后利用率。20 个 native wall ≥30s 的窗口占该 cohort
  原生 CPU 2758.424 / 8409.892s（约32.8%）；其中19个的同组装目标碱基至少一半，不能据此认定
  CPU耗在组装内或放宽整窗精度。只值得先测少数、不同源part的实际长尾，组装内外物理分开；把新增
  mapper/准备成本和跨组装配对门变化一起算。若分拆改变必要跨组装证据或净耗时不降，则不接入。
  `full-scope.json` SHA `d8a96fc3b87e5c2f2dccacf1a40a11e470f0fa1094907ce220734157116c738d`。
- `43015921` 同一个只读预检开跑约50分钟时仍无整体 unit marker，不是挂死。1CPU只读
  同节点观测 `43016012 / SUCCEEDED`（目录 `preflight-43015921-observe-1957`），严格绑定
  scheduler job/pid/cgroup/uid/命令/进程start_ticks，无 attach、不读序列/PAF 内容。
  19:58:45–19:59:25同进程在 `runs/JM19_hifiasm_vs_ref/result.paf`（683392866 B）偏移
  629719040→644595712，CPU ticks 增长，`syscr` +1816、偏移 +14876672 B，等价平均每次8192 B。
  三次采样均 D；是活着且缓慢读数据的证据，不能把路径采样墙钟当整次核验速度。至20:06已出现
  真实首项 `ref:JM19_hifiasm`，不取消/另投预检。观测 `samples.jsonl` SHA
  `0d1b14237099224ea73338813f2ed2fca8cae1e46d284b3851af39f04f371e6f`。
- 源码共用 `open_paf_text`：保留 Python 原 UTF-8 解码、通用换行、行号、CIGAR/名字/尺寸/投影、
  原 LF/CRLF/CR 及原始 byte-offset 义务；底层只把共享盘的小读合并成 1 MiB 有界二进制预读取，
  不是只抽查几行或取消内容校验。同类调用覆盖 outer `validate_paf`、Q0 reference/PAF index、
  区域 coarse、原始 PAF 投影及最终重放。85项定向测试通过，覆盖 UTF-8/CRLF/无末尾换行、跨块
  长CIGAR、真实 byte-offset、损坏和完整性拦截。临时字符分块候选增加CPU，未采用；最终采用原生解码器。
- 最终实样 `43016017 / agent-X86-18 / SUCCEEDED`：同一 16,777,379 B / 67,745 行输入前缀，
  四次行序/字节 SHA 一致，read 系统调用（含计数文件一读）从 **2051降到19**，CPU约75ms不变；
  A1/B1/B2/A2 wall 0.411/0.247/0.206/0.181s，有缓存波动，**不是全量预检测速，不能宣称核验快百倍**。
  目录 `q0-preflight-paf-read-abba-20261122-2003-readahead`，`report.json` SHA
  `eef09c57fdb315f95f7bd63f4fc578359e3c1cf67ba9c6e87d0a4bbf781e30ee`，`source.sha256` SHA
  `312ec4b100cde106db8634eb7fa462e44c2fda749b22b044e718569ab23401de`。生产三个模块须同一版本，
  **不热替换**经源SHA绑定的远端预检/旧模块，不混入当前冻结loader包；不为此重启。真实Q0新旧大任务
  都仍RUNNING，新版20:11:16到 **8100/61000，fallback=0**。

### 2026-11-22 20:30 CST：两条真实长尾开始测物理拆分，跨组装不降精度

- 主新 `43012037` 最近 **8300/61000**（20:24:15，fallback=0），旧 `42523432` 仍 RUNNING。
  原只读预检 `43015921` 继续、同一观察器仍跟踪；到20:30只见首个真实参考 unit，未获完整
  `validation.json`，没有切换或安装。`dd872187` 只在仓库，不替换冻结预检。
- 基于1189窗范围审查，仅取两个已存档慢窗（72/77，两个不同源part，先前有弱链密度阳/阴），
  复用 63,189,781 B 已有窗口 FASTA，登录节点仅核对 actual argv、原回执/原 context 和文件大小。
  原独立输入完整 SHA 在计算节点重验。按组装把原完整目标 FASTA 记录分开，保留每组顺序及序列字节、
  查询、原最小链分数、2线程及4 GiB guard。每窗只跑原混合档一次、跨组装原档一次、组装内原档一次、
  组装内30m DP cap一次；跨组装绝不启用 cap，不重跑粗比对/全套小麦。混合回放必须字节等于旧 PAF；
  先区分目标拆分本身和 DP cap 的影响，再按真实配对资格门比较 paired 位置、方向及新放行冲突。
- 诊断 `43016142 / agent-X86-25` 20:28:47 实际起跑，6 CPU / 24576 MiB，目录
  `q0-regional-intra-split-20261122-2027`。`job.sha256` SHA
  `3dbc993d88e6a4338b45f5fef3a386ac857d4a90c46eaf043b36474464af586e`，`metadata-smoke.json` SHA
  `df83ee68c378a50e30eeda6d79e3f9bc7122ed95c61dcfd7bda609948e2f5612`。新三项及原配对/参数测试
  共10项本地通过；源身份、诊断时限和原守卫独立。只有同一作业成功和 `artifacts/report.json`
  才是两窗完整结果，不能凭进程/临时 PAF 下结论。候选耗时必须计入拆分、第二次 mapper 启动、
  原档跨组装计算；即便配对门不变也不是整条 Q0 路径/后续补缺验收，不自动用于新版主任务。

### 2026-11-22 20:45 CST：否决物理拆分上线；将完整 PAF 校验和原始 SHA 合并为一次读取

- `43016142 / agent-X86-25` 20:43:26 **SUCCEEDED**，两份同节点原混合命令都与原存档 PAF
  字节完全相同。计入目标拆分和两个子进程，72 号精比对 313.099→145.123s，77 号 221.120→160.333s。
  **不接入生产**：跨组装未改任何精度 flag，单把组装内外目标分开，72 号在真实配对资格门已少
  7,123、增加1,948个按有向 paired 坐标并集的 bp，其中95 bp 是旧观测但旧门不通过；77号也多
  1,035 bp。切组本身会改变链/定位/竞争关系，不能把收益当作单纯组装内近似，不保证真实参考下路径或
  补洞安全。仅在分拆后的原档与30m之间，跨组装为0差异，证明作用域没有越界，但不弥补拆分损失。
  `artifacts/report.json` SHA `d5830335d28257bc52da2fe7874a9afa8d1529c91ec2eceac55d5a4e5a0be982`；
  `terminal-43016142.json` SHA `abaef1c796c31cafa95af8832148349a1d0739e8831cd3d7a09b04d04ee2f3ca`。
  不再在同一物理拆分上盲调阈值。后续如有目标内选择性候选，必须保留原混合目标上下文与跨组装证据。
- 仓库 outer checkpoint 原逻辑先完整扫 PAF/CIGAR，再为同一输出计算 SHA。新
  `paf_file_identity` 在同一有界读取中调用**原完整几何验证**并计算解码前的原始字节 SHA；
  末端要等到真实完整读及 fd、path、inode、size、mtime、ctime 全部吻合，才能填入原 content memo
  并返回原路径/大小/SHA 格式。若原始字节已有有效的同进程摘要，仍逐行严格几何验证，不增加温读哈希。
  `reference_alignment`、`q0_chromosome_alignments`、legacy `chromosome_local` 等共同输出入口使用；
  非PAF、其它输入清单与原数据协议不改。新测覆盖冷路径禁止第二次 hash 读取、UTF-8/CRLF 原字节、
  几何校验完成后原子替换必须拒绝、摘要命中亦不能放过坏行；74项定向测试通过。
- 完整原参考比对 PAF（683,392,866 B）现场对照 **43016156** 已提交；只重验同一份旧输出，两个
  路径均检查原 checkpoint 的 SHA / geometry，记录系统读取量及耗时，隔离目录
  `q0-reference-paf-onepass-20261122-2044`。`job.sha256` SHA
  `f93095d3430e2a994995f1146c0b0c4881ed9a78d6ffe4b09789b64ddb8268f3`，`source.sha256` SHA
  `e4bfb1bb9adfe84ae8a0a40bcd19563422304066a424120c0197c222074d6285`。待真实成功报告；
  不改或终止冻结的预检 `43015921` 及主任务；不可把这项 future 优化算进当前速度。

### 2026-11-22 20:54 CST：真实参考 PAF 核验少读一遍，未测得壁钟收益

- `43016156 / agent-X86-23` 于20:52:47 **SUCCEEDED/0**。本轮的新旧代码都使用1MiB read-ahead；
  在同一个683,392,866字节完整参考 PAF 上做原完整几何验证并返回相同的 path/size/SHA，均与原
  checkpoint 的输出项一致。新方案的 `/proc/self/io` `rchar`（含少量采样）
  **1,366,785,830→683,392,970**、read调用 **1310→656**。CPU秒 **51.66→51.33**，
  但壁钟 **196.76→204.52秒**；此单次固定顺序没有证明壁钟提速，也不能区分缓存和共享盘波动，
  更不是完整25项预检测速。保留仓库 `3c15342d` 的等价少读实现；**不为它重启或更换远端预检/main**。
  job/source manifest再次校验通过。`q0-reference-paf-onepass-20261122-2044/report.json` SHA
  `38fc0c3dc2193c8a1b6e089754a39dd9e29bf93802a81685425fd7205e84f48a`；`terminal-43016156.json`
  SHA `25c3befbb506dee23f1992422609b318b85032509c5cb0ffa16338d49c55f3b5`。
- 20:53新版 `43012037` 在同一节点继续产出，20:51:12 **8700/61000 / fallback=0**；
  调度器一拍 recent CPU 329%、memReal 89,624 MiB（约87.5GiB）、swap=0。近期吞吐仍约
  900窗/h，不是核数耗尽；不能从一拍指标确定剩余时间花在何处或缩掉为后续阶段保留的内存。
  关注已排查的 mapper 进程启动/共享盘开销，不把加线程或更强近似当默认解。
- 只读 `43015921` 同作业仍 RUNNING，实际又通过第二份 `ref:JM19_flye_ABD`，共2/25；
  不把单项成功当完整恢复门禁。没有资源提交intent或ready/handoff，旧 `42523432` 仍运行且未改。
  继续核对 PID3458598 及同一预检的权威状态；观察器自然到限且没有intent时才按照 19:10 的规则续接，
  不重提活着的预检，不提前停新版主任务。

### 2026-11-22 21:07 CST：合并区域回执的路径核对，不变配对规则

- `q0_preparation.identity` 服务于区域raw/project回执、原生补证和最终evidence inventory。原来在
  `artifact_path` / `is_file` / `sha256_file` / 最后一次额外大小`stat`中重复查询目录。现复用通用
  `file_identity`的同一对签名，按哈希真正绑定的解析路径验证workspace约束，同时继续验证原逻辑路径
  在读前后（包括温memo）未被换向。输出原始逻辑`path`、size、SHA完全照旧，不放松缓存验收。
  93项定向测试全部通过；全`test_q0_*.py` 331项（330通过、1跳过）。新测覆盖原label、一次真实冷读、
  拒绝workspace外链接且不读取，以及命中摘要期间链接换向仍拒绝。
- `43016380 / agent-X86-08` 21:06:08 **SUCCEEDED/0**。只读32份历史成功raw回执及各自的原
  command/guard共96个小文件，118,967字节，8段均与冻结的96项`path/size/SHA`逐项相同。
  每段Python层`Path.resolve` **384→288**、`Path.stat` **576→192**（非内核调用计数）。
  A1/A2冷memo **9.51/5.43s**，B1/B2 **5.37/5.41s**；温memo A **0.89/0.89s**、B **1.04/0.88s**。
  受共享盘波动影响，尤其温memo未证明壁钟改善；不把小文件批对照当整麦吞吐。未读FASTA/PAF，未
  写主 workspace。隔离目录`q0-artifact-identity-abba-20261122-2102`，`job.sha256` SHA
  `87e1710d29377874e576b28819f0efc878b4ae3514c383c71731605d77dc45e5`，`report.json` SHA
  `c20d623895acde3e53007285912ce238a0035f1bdfcd742a88ceae307b623edb`，`terminal-43016380.json` SHA
  `8152fa37e082c983498b1435f88d1d5138c4a4a7c957c4eafda471ac7f3783cb`。
- 新版 `43012037` 21:04:17报 **8900/61000 / fallback=0**，两份主作业仍RUNNING。只读预检
  `43015921` 又完成 `assign`，正式已验3/25。冻结的生产文件、预检及原等待资源门不换，不因此重启。
- 原观察器3458598于 **21:08:09** 有界到期、进程已退出；原预检未终止。核对同一 preflight 和两
  原 job 都运行、原 workspace 锁匹配、无 submit intent/ready/handoff 后，使用原验证过的环境、
  相同脚本及3h-config SHA，一次续接 **PID488989**（21:11:56，断开重连验证PPID1）。已有
  `loader-watcher-3h-relay.once`、`.pid`、`.log`；切勿并起另一份。仍最多90轮且只准在25/25等
  原门禁通过后申请一份等候资源；不会动主任务。21:12 已有 `q0_chr:1A`（实际4/25），新版
  21:10:48 到 **9000/61000**、fallback=0；旧版仍RUNNING。尚未建立任何资源提交凭据。

### 2026-11-22 21:20 CST：实测节点本地 FASTA 周转收益，不碰当前运行

- 新诊断 `43016417 / agent-X86-08 / RUNNING`，实际6 CPU/16384 MiB、2路×2线程，每路仍4 GiB
  地址空间保护。固定抽取8份已完整提交原coarse+precise的归档窗口，ABBA比较**共享盘直接读 FASTA**
  与**同一窗口完整复制至私有节点本地 `/tmp`、SHA核验后两次共用**，把复制/核验计入B。只替换两个
  输入路径；原guard、mapper、参数/顺序和共享stdout/stderr位置不变，两段stdout都须等于历史全量原字节SHA。
  目录`q0-regional-local-io-abba-20261122-2118`，`job.sha256` SHA
  `d72fc959305f2508ae284c53085caede1c90d255a0dd66976d0fed8fcf45ac2e`。仅对隔离作业设20分钟上限；
  本地4项针对性测试通过。无完整实测之前不以“共享盘慢”推出搬到本地一定省时间，不改主任务或回执协议。
- 21:20 两份主作业仍RUNNING，新版 `43012037` 于21:17:38报 **9,100/61,000**、fallback=0；
  `43015921`同一预检仍RUNNING、4/25（两参考、assign、1A），观察器PID488989确认存活。仍未切换。
- 首份 `43016417` 在 **21:24:24 FAILED/1**：计算节点测试中，对同长度文件快速改写后，原测试用的
  stat签名没有可靠改变，原试验只验证“本地副本等于当下读出的源”不够。没有进入原生对照，不是主任务失败。
  终态 JSON SHA `bffab6f33883f2886f11ec938c4ac4e80c58dde8e10eaea486ca4824ad77b3cb`。
  改为每次本地暂存同时核对**冻结原回执SHA、实际源字节和新副本SHA**，并在完整ABBA后重读共用归档
  复核；测试显式模拟元数据相同但内容错误的情况，必须拒绝。保留两阶段全量stdout SHA和原参数门禁。
  本地三组10项测试通过。新作业 **43016420** 在`q0-regional-local-io-abba-20261122-2118-r2`单次
  提交；test的临时文件只落私有节点本地目录，并增加独立240s测试预算；`job.sha256` SHA
  `390961549fc9f2c53c12597899fa275120d2e59d20d2213153b733383e63f8d9`。等待该作业终态再判断净收益。

### 2026-11-22 21:37 CST：预备全量只读缓冲校验，不再盲重投本地 FASTA 对照

- `43016420 / agent-X86-60` 在21:34:20 **FAILED/124**，出在独立240s单测预算（尚未完成测试、
  未创建 native artifacts、没有任一组mapper/速度结果）。与主分析的资源、旧版进度、真实比对精度无关；
  `terminal-43016420.json` SHA `1eaddb9b50814105a5224c23d84e0105eae622ea9e3089267433000c09251cfb`。
  不将该诊断终态当成节点本地一定慢/原主失败；不再投同样的测速包，先保留已有投入。
- 回查上次真实25项证明 `a46396d126d9f1620acf010ff4b5559c64c62c9fdbc75cfbbe138ccb298e6fee`：
  本次工作区25份原checkpoint JSON的当前内容SHA全部相同。其声明的输出里有68份 PAF，参考
  1,745,286,139字节、区域初始染色体 12,522,376,422字节（合计约14.27 GB）；**只核验JSON元数据，
  不表示本次重新读过PAF或25项通过**。原真实预检8 KiB读取已实地观察到，不再靠增加旧诊断上限解决。
- 已准备隔离 `q0-buffered-preflight-probe-20261122-2137`，真实独立 `origin_probe` 角色绑定
  基础transition/原native origin、原25项proof和 SHA 锁定工作区冻结 verifier，原有输入 fingerprint、
  native/cross/self及最终封套验证完整保留。只替换输出PAF流为1MiB缓冲、完整几何/CIGAR与原字节SHA
  同次读取；逐项匹配原成功预检的真实input fingerprint和 checkpoint SHA。23项本地定向测试通过。
  `job.sha256` SHA `39191ac388f95c7d0bb8895a989b2b2840b5e3a92e1289019e233dbc39059599`，
  `config.sha256` SHA `392ef9630cc6643f0825925ec635abb005055b17d2da0b9ce686c7d1ce2004fc`。**已stage
  未提交**；只有原 `43015921` 权威终态未通过且没有有效交接凭据，再判断是否提交一次，不并跑相同全量
  校验。隔离结果写`buffered-proof.json`，不能冒用被冻结切换控制器的`validation.json`，不安装/停作业。
- 截至21:37：新版 `43012037` 于21:32:16 报 **9300/61000、fallback=0**；旧 `42523432`仍运行。
  原 `43015921` 仍RUNNING、实际4/25、PID488989仍跟踪，未产生新的资源提交或切换。

### 2026-11-22 21:45 CST：只读预检验证超时后才自动启动缓冲候选

- `43015921` 未结束；已另过`q0_chr:1B`和`q0_chr:1D`，实际 **6/25**，旧loader资源观察器
  PID488989仍活，没有`validation`、`loader-resource-*`或handoff。原 `43012037` 21:39:45 达
  **9400/61000 / fallback=0**，旧`42523432`仍RUNNING，两个主作业不重启、不改精度。
- 隔离缓冲验证目录已启用一次性的条件发起器 **PID1952872**，21:44:36启动、重连验证PPID1：
  `retry-launcher.json`、`retry-watcher.log`、`retry-watcher.pid`，`retry-watcher.sha256` SHA
  `83368f2a730e5007ed47ec815234f092e5c44e9e580b58d14ddd36aef85a9bdc`。55轮每分钟有界查看。
  只有同一原诊断经Donau确认**FAILED/124且子进程确实退出**、原job与脚本receipt匹配、没有任何新
  校验/切换凭据、两个主作业及原工作区锁匹配、真实loader smoke仍通过时，才校验缓冲诊断的两个冻结
  manifest并发起一次2CPU/16GiB只读缓冲验证。独占`submission.intent`后不盲重投含糊dsub返回；
  不发停止命令或申请32核切换资源，也不生成原`validation.json`；原预检成功则直接退出，不再跑一遍。
  本地关联12项测试、远端Python3.10现场5项均通过。截至21:45尚无该缓冲诊断新job或提交intent。

### 2026-11-22 21:55 CST：为缓冲结果准备独立验收，不替换原预检报告

- `43015921` 原只读预检仍RUNNING，实际 **9/25**（已过 `q0_chr:2D`）；观察器PID488989、缓冲
  候选单次发起器PID1952872均存活、无缓冲候选提交、无`loader-resource-*`、ready或handoff。
  两主项目仍在原job；新版21:48:53报 **9500/61000、fallback=0**。不改精度、原门禁或主任务。
- 缓冲proof如最终实际通过，使用**独立、可追溯的兼容入口**：冻结原`validation.json`要求不变，不仿写
  该文件。只有明确提供 `--buffered-proof` 和关联真实`SUCCEEDED/0`的 Donau 终态 JSON时，才额外检查
  缓冲独立启动回执/旧超时、原state/transition/native origin、探针和读取器SHA、同序25项完整原
  fingerprint和checkpoint SHA，并重核对25份当前commit JSON。分配节点在ready前及handoff后分别
  验证该独立证据及控制代码SHA；真正owner获取正常锁后仍重验初始结果。其他loader、资源、原作业结束
  和独占锁门禁不削弱，绝不由准备脚本停止或提交主作业。
- 控制文件只stage在同级隔离 `q0-buffered-handoff-controls-20261122`，未替换原cutover目录及源码，
  `controls.sha256` SHA `c54a6730e36774d5b8d36bc7123044102b6ca16d4867a7d544822297bf1f9b35`。
  本地27项、180同原保护模块12项定向测试通过。并非真实候选的验证成功；在完整缓冲结果出现前不运行
  这个接口，不写原handoff文件，不申请备用分配。若原预检成功，沿原观察器路径，不动此备选入口。

### 2026-11-22 22:12 CST：原只读预检到限，改跑缓冲探针；两主作业未停

- Donau确认 `43015921` **22:10:59 FAILED/124**、无残留进程。这是3小时**诊断**预算终态；
  最后完成到`q0_chr:4B`，真实 **14/25**，没有`validation.json`，原资源观察器未提交也未切换。
  `q0-child-loader-cutover-20261122-180258/preflight-43015921-terminal.json` SHA
  `b85e0bf1762a1111be1ce70e5469b342e36784a22e2917c3792620c99ddec8a9`。
- 条件发起器扫描到该终态后只提交了一次 **43016469**；22:11:43 在 `agent-X86-18` RUNNING，单节点
  2 CPU/16384 MiB，文件 SHA 已在作业内核验通过。目录 `q0-buffered-preflight-probe-20261122-2137` 的
  `submission.intent` SHA `a49cec5dbcb0468c5f111612d069a69de6ce6c86874b6ed1c9e632b3e1d8b7b5`、
  `submit.txt` SHA `258b3343ddf3a20227ba0844d453e435012223aff5ec1c4b8b9dc482c7b9578d`。两个有界
  观察器均已退出；跟同一个已提交诊断，不另重投，不把启动/manifest成功当25项验证。只有独立
  `buffered-proof.json`及真实调度终态同时通过才验收，预检本身不安装、不动两个主任务。
- 新版 `43012037` 22:07:20报 **9700/61000 / fallback=0**，旧 `42523432`仍RUNNING。截至21:57
  的精确一小时窗口约803窗/h（8800→9600/3588秒），后段100窗口花573秒；当前速度有波动，不用一天
  的混合缓存/新增平均估计。此轮未修改运行代码、科学参数、资源或任何真实结果。

### 2026-11-22 22:21 CST：真实主作业仍主要受进程启动/等待限制，优先验证无损 loader 路线

- 同节点1CPU只读 `43016507 / agent-X86-39 / SUCCEEDED/0`。12次、间隔约5s，绑定真实
  `43012037` 的工作区锁、原reader/owner PID、start ticks、同作业 cgroup 和当前UID。只取进程树、
  状态及任务分类，不attach/发信号/读FASTA或PAF；1项聚合绑定回归通过。隔离目录
  `q0-mapper-slot-sample-20261122-2218`，`sample.sha256` SHA
  `c5b48d90e5ba7d9865a150bd19d9b2b453e53494eb44e86f25531b6e23d61610`，`samples.jsonl` SHA
  `a48d4452f404265cc57948aafd83f2fe4e289ec76cea070d6086bb95ebc61433`，`terminal-43016507.json` SHA
  `cb34821a0f4815353e7db6e3b06565fc1faad85e143543ba4ccfa464bb15dbcd`。
- 12个瞬时采样每次可见 **9–13个**区域子进程（均值11.5，池上限14）；总138个进程观测中，
  **68个尚为Python guard、69个已是minimap2、1个处于其它区域启动状态**。guard观测64/68为D；
  native观测37/69为D。等待通道多数不可读（0），主进程状态不代表其所有线程；不是耗时百分比、
  不据此归因到具体文件。现象不支持把“多加线程或全局提速档”作为第一步；优先完成已做真实字节
  对照的child-only loader路径，不取消guard。缓冲预检 `43016469` 仍RUNNING，无完整proof。
- 主新版22:20:32 **9900/61000，fallback=0**，从21:24:43的9200起700窗/3349秒，约**753窗/h**；
  旧版仍RUNNING、未动。余51,100窗若维持此速约68h仅指当前阶段。假定一次实际切换损失6h、且所有剩余
  待做窗口同质，候选需约826窗/h以上才抵消；仅是成本门槛，不是新吞吐预测，真正切换时须以完整预检、
  实际有效剩余/续跑损失和同节点配置验证重算。不热换代码或参数，不预先停当前主作业。

### 2026-11-22 22:28 CST：量化无损启动优化在并发池的净收益

- `43016593 / agent-X86-16` 已真实RUNNING，隔离 `q0-loader-pool-abba-20261122-2229`，单节点
  10 CPU / 32768 MiB、4路×2线程、每路原4GiB AS guard。按历史耗时预选8份有双阶段归档的窗口；
  同节点ABBA仅切换mapper子进程的 `LD_LIBRARY_PATH`，调用冻结候选真实探针，必须与已有writer smoke的
  依赖路径及内容SHA证明相等。粗筛和精比对全部stdout都与原归档逐字节一致才能收下；独立计完整pool墙钟、
  单窗服务时间及一次性loader探测。没有规划、发布、锁切换或完整主进程，不外推整麦吞吐。
  本地8项、180同Python3.10 1项定向通过；`job.sha256` SHA
  `bebc7db93dab397b9802a79a8dfd95537a2d078ab250e2b2c0ff5869440bd079`。目前仅到作业启动，未得到结果。
- 新版22:26:27 **10000/61000（16.4%）、fallback=0**；从21:32:16的9300起700窗/3251秒，约775窗/h。
  两主作业仍RUNNING，`43016469`仍RUNNING，未提交完整buffered proof、未申请主切换资源。没有把无损
  loader候选或隔离测量部署到主运行，也没有降低精度。待原生并发对照和真实25项证明后再评估净切换收益。

### 2026-11-22 22:41 CST：启动开销实测有收益；下一步以减少有效计算为目标

- 原严格跨节点 `43016593` 在 22:28:51 **FAILED/1**、未起 mapper；不假定是二进制不同。
  后续仅在隔离对照 `43016623 / agent-X86-16` 显式允许记录并诊断本节点证明差异。实际只有
  `inherited_path_sha256` 不同，工具及解析后的依赖路径/内容 SHA 相同；本节点仍比较清理前后
  的实际依赖，冻结生产切换证明不放宽。该对照 22:37:54 **SUCCEEDED/0**，8 个真实双阶段窗口、
  196,369,277 B，4路×2线程、原地址空间 guard。ABBA 墙钟 A=58.478/54.912s，B=36.007/45.821s，
  同节点并发池墙钟少 **27.8%**，64 份粗/精 stdout 均等于各自历史完整 PAF；20.90s 一次性
  loader 探针单记。此对照不含大 owner、规划、投影及切换成本，不外推整麦倍率，无安装授权。
  `q0-loader-pool-abba-20261122-2229-node16/artifacts/report.json` SHA
  `021b503a0585cb94e367d42d7e1e2e21b25e4998dce9becdcfc17c72a975a55c`，`job.sha256` SHA
  `0e6fb68232a48b6189883fa25da731f22894d24d8cbe2b8cfb66cfa90db94e00`。
- **少算而不是调大并发**：完整、同身份、同搜索范围的成功结果才能无损跳过；不把对侧已有覆盖
  当作所有备选配对已经找到。16:25 实样已反证按覆盖跳窗，13:20 实样已反证按目标碱基缩减估加速。
  下一项算法验证先用已存档精比对，在不改参考/跨组装证据、不改混合目标列表的前提下，重放
  有/无低价值组装内补充时的候选与冲突判定；最终去向没变化的前提是同样的歧义也被识别，不能只数
  入选证据或算覆盖率。只有确认哪类证据不影响决策、且扣掉回补还有净墙钟收益，才做按证据充足度
  自动触发的延后补算；缺锚、边界和冲突保留原路径。现在尚未确认能批量跳过多少，不改正在跑的科学策略。
- 22:41 观察两主作业均 RUNNING。新版 `43012037` 22:35:02 **10100/61000**、fallback=0，
  从21:57:47起500窗/2235秒，约805窗/h；旧 `42523432` 仍在 `grt_step2`。`43016469` 已有
  两个参考 unit 的真实独立校验回执，尚无完整 buffered proof。保持两主作业不动，不部署本轮对照，
  不预支尚未证明的续跑/算法收益。

### 2026-11-22 22:58 CST：用归档慢窗试验「跨组装已定位，组装内能否延后」

- 提交独立只读 **43016650 / agent-X86-18**，实际22:52:55 RUNNING，单节点1CPU/4096MiB。
  用冻结1189窗trace选最多24个不同父contig：高CPU、短内部core、一般窗各至多8个，选择不看原PAF。
  逐份核对原raw成功凭据、完整PAF SHA及窗/源几何，再原样投影；配对资格门复制**当前运行代码同SHA**
  至隔离目录，逐源对、方向及实际对应位置比较。原生mapper未运行，不写主workspace。
  隔离目录 `q0-regional-intra-deferral-20261122-2253`、`job.sha256` SHA
  `529de299fe683dc6a6091586cf9853cc1e7e658fe39849b509a04bb47ccd40e9`。本地15项、远端4项定向通过；
  截至22:58调度器仍RUNNING，尚无完整归档报告或可用于决策的逐窗结果。
- 这个探针先证伪一条便宜门：窗口核心不在端部，已有**唯一**跨组装有向位点完整支撑核心时，检查原样
  组装内命中是否仍提供合格配对、是否还带有未过门的备选位点。不把不同target/方向的union冒作唯一。
  使用中性placements与本窗档案，只能排除过宽策略，不能证明生产Q0选择、冲突或补洞等价。即使局部
  合格组装内命中少，也要用真实锚和base PAF验收；另外 `known_pairs` 会影响下一轮 `supplemental_groups`，
  必须把由此新增的补算计入净耗时，不能把后移计算当成删除。
- 22:58 两个主作业仍RUNNING。新版 `43012037` 最新 **10400/61000**、fallback=0；旧 `42523432`
  保持 `grt_step2`。只读 `43016469` 同个作业已真实校验8/25项，无完整缓冲proof，不申请主切换资源。
  不改变两个主运行、不在隔离对照之外降低精度。盯同一 `43016650` 终态与 `report.json`；若旧配对门
  在慢窗超隔离预算，非主任务失败：优先用已存在索引资格门做有界候选筛查，再让旧门仅核对候选与反例，
  不重复同一慢对照，也不把筛查替代真实证据验证。

### 2026-11-22 23:10 CST：归档实样不支持按唯一跨组装覆盖延后组装内比对

- 原只读 `43016650` 23:06:14 确认 **FAILED/124**，12分钟诊断预算内没有一个完整窗；不是两份主作业故障。
  原配对门完整跑所有目标，而多数窗不满足候选必要条件。另行只读 `43016697` 在相同 `agent-X86-18`
  保留同一批窗、原源码SHA及PAF完整验收，只把明显不合格的窗提前排除：端部直接不入候选；余下比较
  实际已观察到的有向坐标映射，只有单一完整覆盖的源对才进入原资格门。候选仍传同源对全部命中，核心外
  的冲突也能否决；未计算的资格字段为null，不能当0。先处理短内部窗；未替换活跃工作区任何代码。
  18项本地（包括150组与不预筛的结果对照）、7项HPC单测通过。
- **43016697 / SUCCEEDED/0**，23:07:16到23:09:31，科学重放部分45.33s、不执行原生比对；24窗
  完整验证21,182,208 B。14窗无单一完整观察map、7窗为端部；只有3窗通过初筛。**高成本组0/8**，
  其中一个原精比对325 CPU秒的窗有3737个相交跨组装映射，不属于该策略能推迟的补证。通过的三窗
  原整个精比对仅3.396 CPU秒，非代表性24窗合计1064.629 CPU秒；这只是本组潜在范围上界，不是节省。
  并且3窗里2窗仍有合格的组装内位置（分别2和41个按目标/方向/偏移归并的maps）；不宣称这些位置
  都会被最终选用，但不能把唯一跨组装覆盖当作无损跳过充分条件。该门不接入主任务，不扩大试验重复找阈值。
- 证据：`q0-regional-intra-deferral-20261122-2305-r2` 内 `job.sha256`
  `47ebcbdec6837d81768354d382899d965ccd628c1d17370f7ee600e65c6ad452`，`prior-terminal.json`
  `28deb1791f70a37875713cd0c416df847b19db766a94b5475db89d2a98db84aa`，`report.json`
  `8132d1db33878660de75a81065846b73598ea45d3a8b88ddc39ae93f076cf6ee`，`terminal-43016697.json`
  `141ecafe68d8302f0b6ea05ad6103791b1e74bef0b52891e0c881011de2d9e3a`。
- 回到无损切换路线：独立 `43016469` 已实证11/25，尚无完整验收；当前不申请切换资源，不重启。
  新版 `43012037` 23:09:07 **10500/61000**、fallback=0，旧 `42523432` 继续 `grt_step2` 未动。

### 2026-11-22 23:26 CST：确认其它 x86 节点可复现归档输出，补上实际续跑节点的装载验证

- 不用「随便换节点」绕过 writer smoke。原门仍优先要求与旧 smoke 完全相同；只有明确走独立缓冲
  proof并启用`--allocation-replay`，且**仅**继承的`LD_LIBRARY_PATH`字符串摘要不同、既有工具
  （包括`--version`）及被加载的实际库路径/内容SHA一致时，才在**将要续跑的同一分配节点**用
  原4GiB guard、原两线程及原FASTA字节回放一份粗/精窗口。两阶段全stdout分别等于归档才允许
  `loader-ready.json`；依赖、工具或输出变化仍拒绝，保持原父环境。后续`ready.json`绑定小回执，
  交接时重核控制文件及两份本节点回放；真正owner仍须普通锁与原阶段核验。不修改冻结原启动包、
  预检或主工作区。本地22项控制/原生对照helper测试通过。
- 隔离工具试验 `43016716 / agent-X86-65 / SUCCEEDED/0`，23:21:34–23:25:15，18项远端控制
  测试通过。65号节点的工具装载证明与原 writer smoke 完全同一（与16号节点只有继承字符串不同
  的现象区分）。另外强制执行**诊断-only**归档回放，同节点用候选guard核对10,270,923 B，
  两阶段完整PAF字节SHA均通过，回放28.371s。这不是主32CPU作业的分配或真实接管，不能用于
  跳过新分配节点的核对。隔离目录`q0-buffered-loader-controls-20261122-2321`，`controls.sha256`
  SHA `dbe38c7c4f1f70393e8ceac3df33495a86492d5e813cb407384616b188f43bd8`，
  `archive-diagnostic.json` SHA `734ca6a7023d3bbfb3065a149d8c892702563e03c665ce2110a7af80d057b7b6`。
- 23:25:45 两个主作业仍RUNNING；新版最新23:18:16 **10600/61000、fallback=0**，旧版仍
  `grt_step2`。`43016469` 同一隔离预检实测已过17/25（至5B），未生成完整proof。只在完整25项与
  同作业成功终态通过后使用上述隔离目录的准备入口，先核对旧主锁和相关凭据；不提前申请交接作业，
  更不因诊断成功停新版或动旧版。是否切换仍以实际资源、子进程验证、进度和净收益门判断。

### 2026-11-22 23:38 CST：预检完成后单次排候选资源；独立加测14路实际收益

- 独立预检 `43016469` 仍RUNNING，实际校验到 **22/25（7A）**。已在 `q0-buffered-loader-controls-20261122-2321`
  启动一次有界 observation **PID2684077**（23:33启动，重连实见PPID1；最多60×45s，日志
  `resource-watch.log`），源码/启动/冻结旧查询 helper 的 `resource-watch.sha256` SHA
  `1aac519a0cc66a1d6e94e0e0b980cef9435287eda6aae0a992a955b5fc8fa15f`，原 controls SHA仍不变。
  只在同一预检成功终态+完整proof、旧 writer smoke、两主作业及owner/阶段仍一致时，才准备并**至多
  一次**申请待交接 x86 32CPU/320GiB 资源；先用独占 intent 去重，dsub回包歧义禁止自动重投。脚本不会
  停任务、发布handoff、安装代码或改工作区。27项本地相关测试、4项180同环境通过。
- 不把4路小样本约28%直接套在同阶段剩余时间上。用一小时 `10000→10700` 约705窗/h，假设
  扣除已有完整矩阵理论上限2573窗，50,300计划剩余中的47,727窗用于**情景估算**。按14路与历史
  到首个新raw约5h20min，给6h续跑损失时需要≥774窗/h或每slot-window有效节省约6.34s；
  给7.5h损失时需≥793窗/h或7.92s。原4路8窗的绝对槽位换算7.89s仅略高于6h净门，未证明到生产
  大池子仍成立。非承诺实际窗剩余、阶段ETA或该选项必部署。
- 因此只起一项更接近当前并发的隔离对照 **43016759 / agent-X86-57**：实际RUNNING/单节点32CPU，
  申请98,304 MiB，每mapper保持4GiB AS、2线程；原档/验证子环境/验证子环境/原档ABBA，14路28个
  已完整归档窗口、不重建DNA、不改变target/flags，四轮224份粗精stdout均需等于历史完整PAF。
  另记已验证输入和一次性预检开销，不测真实大owner和规划；算`墙钟差/每轮完成窗口`后再做净收益判断。
  路径 `q0-loader-pool-production-shaped-20261122-2337`，`job.sha256` SHA
  `6f135d92a70104e99a5dad1413ca1717fda49b40c44b46f4a1cf7c01cba26e2f`，仅此隔离对照有12分钟实验上限。
- 23:37两主作业均RUNNING，新版23:36:01 **10800/61000、fallback=0**；未改两主任务。
  等同一个14路试验终态、真实25项proof和新分配再决定是否交接。若14路受控收益不足以抵消近期真实
  吞吐和复用回放成本，不要因新资源已经ready而停止原主任务。

### 2026-11-22 23:54 CST：14路原生对照与25项预检均通过，候选分配已起跑、尚未交接

- `43016759 / agent-X86-57 / SUCCEEDED/0`（23:48:57）。完全同一输入及工具，14路×2线程、
  每路4GiB guard。原 A=123.066/125.008s，优化 B=93.361/77.462s，墙钟平均少 **31.14%**；28窗、
  776,558,919 B，四轮的 **224** 份粗/精完整输出均匹配历史SHA。最慢优化轮仍比最快原轮少29.705s，
  每窗批次摊销 **1.061s**（均值1.379s）。按目前待做规模的示例，即使出于混合任务/调度噪声
  只按较保守差值的70%估算，减去旧任务已知回读的6–9小时，仍值得走受保护接管；**这不是生产吞吐
  或总ETA保证**，真正复用及新增产出仍要云端验证。`artifacts/report.json` SHA
  `0cf232c32b398c9baa0e7d28d15c6d92cbf3cc8a09c6622d2573fa65ca2a7175`，`terminal-43016759.json`
  SHA `fec2b806a344cac76e807ae9f7b0b69f2ea72fd414f500cae6f04dd5f043fc2d`。
- `43016469 / SUCCEEDED/0` 于23:51:20，25项均真校验且核对原指纹，`buffered-proof.json` SHA
  `3ca88d2fe478c78f04582f007ba543b5ea4839c06b61761234af1544404cbf15`、`terminal-43016469.json`
  SHA `a89bdbd37004d3552918bd16378f5b7a14aa128372e89c335103524a17d82515`。观察器一次性申请
  **43016881 / agent-X86-57** 23:52:02 RUNNING，确为同一14路实验节点，单节点32 CPU/327680MiB
  硬限制。首次23:53仍校验启动包，不能把RUNNING或manifest成功当ready，也不能提前停原NEW。`loader-resource-submitted.json`
  SHA `511f66cac5fc25d656c69be266c49bd967ef425a7880547f3597229e81ea4be9`，`handoff-config.json`
  SHA `fe1d1234b0c3e34b2f4b2f884ffe8b3c1ea16a67c42f05966cf5e767abcb3522`。
- 另查后续Q0选路径热点：线上和当前候选包的 `q0_paths.py` 还都是原反复扫竞争配对版本，仓库
  `02b19c60` 的索引版未装；此模块属于 selector/publication 身份，不属于区域 evidence builder
  指纹。`43016878 / agent-X86-42 / SUCCEEDED/0` 用16,350,606 B SHA绑定原始区域PAF，22真实源对
  （5对含双方向），按两方向、两种支持模式共88项，**有序坐标和 evidence IDs均相同**。受控门核
  CPU 0.1078→0.0164s，不预测完整Q0选路径时间，不把中性placements当完整真实布局验收。
  `q0-indexed-pair-narrow-replay-20261122-2347/report.json` SHA
  `760752f0d998bcd56ba1a62a1234f5b164e0cf169e17c64baab21ee882312e6f`，实验未热改活跃runtime
  或原候选包。需在实际下游入口/已绑定依赖范围另证后再考虑应用，不拿它拖延当前已验证的mapper优化。

### 2026-11-23 00:08 CST：实际候选接管已放行；保留了原节点遗留的失效锁

- 11月22日23:56候选 `43016881 / agent-X86-57` 已有真实`loader-ready.json`及`ready.json`，
  ready PID **1781624** 与Donau新单节点32CPU/327680MiB分配相符。旧NEW仍同一run和owner，末次
  11月22日23:53:40 **11000/61000**、fallback=0。以上一节14路实测最保守差、再打7折，以及
  假设最大已有矩阵可跳窗口后作情景计算，约9.78小时节省对比9小时停机/回读预留；这是是否值得
  切换的模型，不是线上ETA。`loader-prestop-verified.json` SHA
  `799d8bb46fdc0827b98b5f70fc2ea93d598420a9754a514823d3e3fd5080b9a8`，含停止前两主作业/候选
  资源和完整owner绑定。`ready.json` SHA `81ef0e4f346243c5ad3b63f32cbcf55a568a9c11796ed4801e61a89d39b95754`。
- 只对**原新版43012037**在11月22日23:57:42执行一次正常`dkill`，未使用force。23:58:12
  Donau确认 `FAILED/143`（本次主动终止、不是分析失败），调度器无pids，但旧`lock/owner.json`
  未释放。候选继续等待，没有发布handoff或自动清理。此前常规交接均正常释放；这次节点一度为
  `CLOSE_FAULT`，不能据此认定残留锁原因。首个只读旧节点探针 `43016892` 因看不到PID1的procfs
  记录失败，未把权限限制误作进程消失。第二个 `43016893 / agent-X86-39 / SUCCEEDED/0` 用信号0
  （仅存在查询）确认原owner和停止前记录的20个PID全部不存在、且终态为空、owner内容未变；无权限
  或有任何PID便拒绝。`q0-stale-lock-probe-20261123-0004-r2/same-node-proof.json` SHA
  `5df026e7f86db756d1f912a1199ced570eafffd9ffcee5ec42a9eb6244ba9af5`。
- 再确认新分配、原生guard/loader proof、25项小回执、旧NEW终态、旧版仍RUNNING之后，只**原子归档**
  完整旧锁到工作区 `.run_all/.stale-owner.43012037-preserved-20261123`，原`owner.json` SHA
  `16dfbaac7ff4ec5c847e36f0ae594c7a815b275c1af171ef0266618733054cd2`，不删除锁，不写新owner，
  不把这次说成旧进程正常释放。归档凭据 `stale-lock-archive-intent.json` SHA
  `b4f153fda8263344a0f478d2a41c3a47fcdd29c5400356a50613804b2f812867`。新接管仍须普通新锁。
- 11月23日00:05:57原子发布 `handoff.json` SHA
  `c8cacddc9bcc094ac7da8edd3dd688db4a0bd3aba3e033ebfdf2ead2717721dc`，候选日志实际出现
  `Q0_HANDOFF_ACCEPTED`。截至00:08尚在核验前缀，不能把门禁接收当成runtime安装、25项实际复用
  或新版完成。仍需按新owner/run核对`installation/receipt.json`、真实SKIP_VALID、`verified_child_only`
  及14路区域池新增产出。旧 `42523432` 未改变，所有已完成初始比对和区域缓存保留。

### 2026-11-23 00:26 CST：接管进程仍在锁前校验，缩减后续可避免的重复读取

- 00:26 Donau 实查 `43016881 / agent-X86-57 / RUNNING`，同一 PID1781624；日志已确认
  `Q0_HANDOFF_ACCEPTED`，还没有新 `owner.json`、安装凭据或 `SKIP_VALID`。00:14→00:26
  调度器累计 user CPU 8→15秒、RSS 34→122 MiB，说明同一进程有活动，但不能定位具体文件或
  宣称卡死。57号节点无空闲CPU，不发同节点采样作业挤占资源，也不重启、跳校验或热改冻结包。
  只读观察器 PID137993（PPID1）在等待由 `43016881` 实际获得的锁，锁与调度器 PID/节点匹配后
  才切到新 run 日志。旧 `42523432` 实查仍 RUNNING，未改动。
- 源码审查发现 `NativeBindings` 在同一操作内对每个批次都重新取同一 manifest/restore 身份，
  且已核对 wrapper 内容 SHA 后又重读规范 wrapper 文本。SHA 绑定的真实 native plan 有44个操作、
  876个 wrapper；仅按一次全量 `verify_native_resources()` 静态调用计数，共用身份查询可从
  1752次降至170次，标准 LF wrapper 不再逐个二次读文本。仍核对每个 wrapper/spec 的实际内容 SHA、
  完整清单和规范参数；共用身份在该操作开始/结束各查一次，不跨调用缓存；换行等非标准字节仍走原
  文本判定。无输入/结果格式变化。44项既有定向回归和2项新增回归通过。
  这不是已定位 `43016881` 当前等待的调用栈，也不是现场壁钟实测；**仅改仓库的后续复用路径**，
  当前运行及原生验证包保持原SHA，不为这个改动再次中断接管。

### 2026-11-23 00:40 CST：新作业已取得工作区锁，16份安装备份已核验

- 新版 `43016881 / agent-X86-57` 在 **00:30:29** 自行取得普通工作区锁，实际 run
  `20261122T163029Z-1781624-e66acac9`、同 Donau PID1781624；接管放行后约24分32秒。
  `owner.json` SHA `ea5fa953280a0e2a7774fc987d425562019a7eaeafa9e732a67165be1db5d740`。
  原只读等待器 PID137993 已切到该真实 run，日志 `logs/wheat-live-loader-20261123-003034.jsonl`，
  start receipt SHA `1b6c5d270ae6d7951a92425428854ce5fd0fdb5d8b6489e1be56e7d25f9965a2`。
  00:39:56安装回执仍 `backed_up`，实际复核16份旧文件备份的内容SHA和路径，未把备份/持锁当
  `installed` 或复用成功。该快照无本轮 `SKIP_VALID` 或新区域窗；旧 `42523432` 仍在Step 2。
- 与主节点独立的1CPU只读实样 ABBA `43017053 / agent-X86-18 / SUCCEEDED/0`，00:34:13–00:36:13。
  从冻结真实 native plan 选小/中/大三组、合计69个 wrapper/spec，用原及 `9173170a` 的真实
  verifier 校验相同输入；每轮清空该诊断进程 SHA/JSON memo、不操纵共享盘缓存。四轮全部通过，
  共用身份查询138→10；墙钟 A=15.829/12.520s、B=9.655/9.267s，均值14.17→9.46s，约少33%。
  样本限于 wrapper/spec verifier，不含原始profiles构建、输入/PAF校验或全套启动，不推算主任务
  壁钟；不把该仓库候选部署给活跃 `43016881`。目录 `q0-native-binding-read-abba-20261123-0034`，
  `job.sha256` SHA `20b3e00320efcefd2be185985c703fa8ca301dac24cad839eff59b187fc35ea6`，
  `report.json` SHA `48098d69e2c64fd296214406be827ae5f0816b96328aa5b42ed1703903bcb6c0`，
  `terminal-43017053.json` SHA `0973e9c3a6b1fa588365f41ba8f1efdc0bfbce7837f954c8e0a5ae0afa047f02`。


### 2026-11-23 01:09 CST：定向删除重复安装前审计，并收紧 native 回执读取

- 当前新版 `43016881 / agent-X86-57` 仍 RUNNING；01:06 复核为 `wallclock=4445s`、`cpuUtilAvg=2`、`cpuUtilRecent=6`、`memReal=260MiB`，`installation/receipt.json` 仍为 `backed_up`，没有新科学输出或 `installed` 回执。该作业没有被本次源码改动热替换、没有重启；旧版 `42523432` 继续保持不变。
- 代码审阅确认 `resume_q0_science.execute(..., --install-runtime)` 的调用者先 `ctx.verify()`，随后事务安装器 `stage_q0_science.install()` 又立即执行同一份完整 pre-install 审计；安装器自身仍在安装前和安装后各保留一次完整验证。因此删除调用者这一份重复审计，不削弱 direct-resume 路径（无安装时仍保留 `ctx.verify()`），也不改变安装器的备份、回滚、所有权或安装后验证。
- `native_resource_bindings` 的后续定点优化继续保留每个 wrapper/spec 和 receipt/output 的逐项完整性检查，但把同一 operation 的 manifest/restore 身份查询、receipt inventory 和 wrapper canonical-byte 判定合并为有界操作级验证；`native_resource_audit` 复用同一验证结果，不重复逐 receipt 扫描。冻结真实小麦计划上 44 个 operation、876 个 wrapper 的读取画像显示，逐 receipt 触发的 operation 全量检查约 19,236 次降为约 1,749 次（约减少 90.9% 的同类 operation 级扫描）；这是 verifier/启动阶段收益，不冒充比对阶段壁钟收益。
- 本地定向验证：`test_resume_q0_science.py`、`test_native_resource_bindings.py`、`test_native_resource_audit.py`、`test_stage_q0_science.py` 共 **78/78** 通过；另有 native binding/audit 独立 **14/14** 通过。未运行整版 CI、未 update、未替换 Release。
- 该补丁仍未安装到活跃 `43016881`；待当前任务终态后再按“有效结果保留、正常锁释放、只对新版切换”的规则决定是否采用。

### 2026-11-23 03:12 CST：不重提，保留 Q0 续跑校验优化

- `43016881` 是有意受控停止，不是科学计算失败。后续 `43017096 / agent-X86-57` 当前仍 RUNNING；01:31:10 启动，01:52:30 取得工作区锁，02:52:08 安装验收完成。03:12 实查本轮已复用两项参考比对、归组以及 1A/1B，共 **5/25**，尚未进入 `q0_evidence`；旧 `42523432` 不改。只读小时巡检记录在 `~/cgat-reads-debug/logs/jm19-hourly-43017096-20261123/samples.jsonl`，回看时仍按实际 job、owner、run 校验。
- 用户明确本次不为优化校验而重提。实际冻结入口仍在取锁后和安装器内重复调用审计；`45145cc2` 已去掉调用者这次重复，并减少同一 native operation 的回执扫描。留给下一次合法 transition，重新冻结源码、校验绑定后使用，不热替换。**不**复用跨进程的裸摘要作为成功证明，不跳过产物、SHA、PAF 几何或内容身份的完整性验证。
- 仓库 runner 把外层检查点耗时拆成 `checkpoint_prepare`（输入和身份准备）与 `checkpoint_validate`（检查点及输出核验），均为单调时钟壁钟。原 `elapsed=0.000s` 和状态表仍表示没重跑命令，不是校验耗时。下次在保留相同检查点的只读对照中，分别测安装审计、25 项外层核验及 Q0 旧窗口回读；先按耗时定位重复 I/O，再用相同的复用判定和输出摘要验证优化，不把并行或 I/O 减量直接当成实测收益。

### 2026-11-23 04:04 CST：首个完整小时巡检，定位尚未接入的单遍 PAF 校验

- 小时间隔的第二份快照已落盘（03:04→04:04），监控 PID3590703 仍活。新版 `43017096` 同一 run 由 **3/25→8/25**，最后一次在 03:45:09 复用 2B，无本轮失败或新 Q0 窗口；累计 CPU 从 577→980 秒，仍在推进，不中断。旧 `42523432` 仍在 Step 2。
- 1B→1D 的 `SKIP_VALID` 日志间隔为 **19:00**，上一个新版 run 同段 **1:01**；同一 1D 检查点的隔离缓冲预检报告为 **120.4 秒**。现场时间差包含输入准备和输出核验，不是受控同节点测速，不能全归因给某个读法或文件系统。57 号节点调度余量为 0 CPU，本轮不挤占节点做诊断。
- 实际工作区 `run_outer_checkpoints.py` SHA `e066d7950f99b35822512c3840ae2a9e0683eede275f30f29747879b32be0035`；仍对 PAF 先做完整 CIGAR/几何校验，再走独立 SHA 路径。这正是此前缓冲验证 `43016469` 绑定的旧 verifier。下次合法续跑，优先纳入已有 `dd872187` 和 `3c15342d`（缓冲 + 单遍几何校验/原字节 SHA），以实际主任务路径复测；该独立预检虽逐项通过 25 个检查点，不能替代主任务的输入/产物验收，也不能证明线上壁钟收益。保留当前运行及全部检查点，不热替换。

### 11/23 05:24 — Q0 按路径决策补比对：前置派发对照；否决通用中档 DP 上限

- 目标不是填满所有未覆盖窗口，而是为尚未解决且能改善路径的端点、原始断口、片段取舍补证。据实际 `PathGraph.joins`，无 N 切换需要**同一条已通过竞争检查的精确链**同时接到两个相向端点；多个内部高质量块、甚至覆盖率不变，都不替代这一条件。目前按路径端点前后各 100 kb 取实验范围，选中窗口仍跑完整的原目标集合、方向与上下文。保留 target-only 命中，不按已有 PAF 行筛选，不把缺证据记作无竞争。
- 已在隔离临时空间用 MH63RS3 第一条记录的两个天然序列区间，构造人工断点、刻意留空初始 contig 间 PAF 的控制。真实 minimap2 `2.26-r1175`；参考/原始组内的科学输入身份四轮一致 `q0-control-input-1c6d5da997f2898307630b09`；真实补比对每轮从空缓存派发，强制进入区域分支，不改变参数或输入窗口内容。按全补/定向/定向/全补对照，**12→6** 个区域作业，两段的 FASTA、来源区间、方向、精确切换坐标一致。一段的未知断口如实保留；另一段保留两条精确切换，重构等于 10 kb 参考裁片。另做不补的离线对照，第二段少两条精确切换，只剩未知断口，少覆盖 800 bp 参考坐标。不是“补比对全部可省”。
- 时间为准备＋仅定向组额外的基础证据读取/判定（未把裁片生成、各组共同初始比对或下游 LGZ 算入）：全补均值 3.657s，定向均值 2.581s，约省 29%。不是小麦速度预测。`incident-tools/wheat-20261119/run_q0_frontier_control.py` 复现实验；`probe_q0_decision_frontier.py` 可对已有完整 ready 作只读三臂重放，区分映射次数和投影次数。报告 `q0-decision-frontier-control-20261123.json` SHA-256 `3f2d902d6ff01328c400cc3a30a24cf363f5dfdad69ae6b10d2e7e37dd9c5ea2`。此组强制分支和派发筛选只在一次性实验目录，不生成可部署产品。
- 独立 Donau `43017430 / agent-X86-17` 05:08:03→05:23:48 SUCCEEDED，`q0-moderate-dp-20261123-050719/artifacts/report.json` SHA-256 `dd145e37c1693de54ec123d80ec3a1643e9d6770b67b3bc62c18e1fa06a48f5d`。7 个已封存的小麦窗口，原命令复跑均与归档原始 PAF 字节相同。只重跑精确阶段，同一节点、原 target/order/flags/4 GiB guard；累计单窗口派发墙时原版 1052.93s、50m 451.17s、70m 544.18s（不是管线用时）。两档均在 4/7 窗口触发暂定的配对保留门槛，其中 3/7 出现原来未通过的跨组装配对，最坏增加 15512/11835 bp；部分有 ≥1 kb 的定向目标缺失，即使跨组装核心区并集不降也会发生。是门槛变化，不是已证明的错误最终连接；两档均拒绝作为通用默认，不切换。
- 下一步优先在有重复/跨染色体竞争的真实小麦闭合子问题上，独立重跑有/无端点派发，计入规划、回退、竞争复核、完整性校验及下游供体/缺口。仅按“保守保留 N 或不自动纳入”定义可接受损失；不能按少查到的竞争授予新切换。探索按真正要出具的精确链反查其两侧竞争范围：无法闭合搜索的切换留 N/回退；跨度超过固定窗口则针对同一相向端点候选改用能覆盖两端的上下文，不拼伪链。控制实验证实筛选在同一闭合图里可少做一部分，不是已通过小麦上线。
- 未改旧作业 `42523432`、新版 `43017096`、安装 runtime 或持久化 profile。05:23 调度两者仍 RUNNING，新版 05:22:45 已复用至 **17/25**（5B）。用户要求后续只本地 commit，不 push。

### 11/23 05:45 — 冻结天然小麦验证小组，保留多染色体竞争

- `prepare_wheat_frontier_panel.py` 从原分组坐标预先选定三个 1 Mb bin，再保留入选**完整天然 contig**及其跨全参考染色体的所有原始六列以上 PAF 记录；不在人为边界裁切 FASTA/PAF、不把主分组之外的落点删掉。各 contig 的序列和完整分组集合与已归档 `source-part-lookup.json` 核对，原跨组装和自比对只保留两端均为入选成员的原字节记录，所有含成对成员的原分组均纳入。冻结过程按原成功回执验证被读取的原始 PAF 字节，结果小组各自有完整内容 SHA。不是小麦全基因组闭合竞争集合，不能把未采纳的其他 contig 当作已证伪。
- 初次只取主分组的冻结 `43017433` 明确失败：4B 小组已有多个原分组的 contig，不能把该原分组信息静默忽略。修正后 `43017435` 05:37:51→05:41:03 SUCCEEDED，读取 34 个原基础 PAF（7,695,848,111 字节，仅扫一遍）；封存结果 `q0-natural-frontier-20261123-053719-complete-base/panels/report.json` SHA-256 `61c6427dade7e96287757cc48bad6ce87dfd0ca25d0817e0cfacbdd6069596c5`。4B-358 Mb 6 条/698,417 bp；5B-596 Mb 19 条/2,279,390 bp；3D-589 Mb 97 条/2,985,675 bp，最后一组涉及 15 个原分组，其中 14 个有成对成员的原证据。整组所有原参考 PAF 保持原长与坐标体系。没有将小组的实验产物称为生产 ready。
- `run_wheat_frontier_panel.py` 隔离跑不补、全补、定向补，其中后两者实际运行原补比对的 mapper、规划器和下游 Q0 选择器。完整原目标集合或 native 回退不变；额外统计比较最佳路径、FASTA、原区间与方向、切换坐标；对精确切换的同一对来源，在 query/target 两轴统计尚未搜索且可能影响结论的完整窗口。该审计只给出需复核的工作量和局限，不证明全基因组无竞争。模块环境的 minimap2 2.31-r1302，SHA `cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3`。作业 `43017437` 已于 05:41:05 在 agent-X86-22 启动，实查进入首个小组的区域 partial 派发；未得到本次小麦提速/路径验收结论。主程序未改。
- 本地校验：隔离探针定向 13 项通过；原 Server Q0 preparation、paths、admission 109 项通过（使用各自的 PYTHONPATH 分开启动，避免同一模块被顶层/包名重复注册）。已做真实 minimap2 的小型适配器冒烟，原与定向路径相同且都消费真实区域成功回执。05:44 新版 `43017096` 与旧版 `42523432` 均 RUNNING；本轮新版最后可见 19/25 初始检查点复用。仅本地 commit，不 push。

### 11/23 06:05 — 天然小麦小组 4B/5B 已完成，定向补比对未改路径

- `43017437` 的天然小麦面板已完成 4B-358Mb 与 5B-596Mb 两组；3D-589Mb 仍在读取/构造初始对照，尚未给结论。4B 报告 `ab-4B/report.json` SHA-256 `57245504a366a3242d82a35de0c268af1e8b900378ca1832d8f82b514398316e`；5B 报告 `ab-5B/report.json` SHA-256 `5313786f1f373d2ba2febdacfa8547d81437333d3b4ddca11f7e3cf675dd1825`。
- 4B：区域任务 4→2；全补准备＋读取选择约 135.27 s，定向约 118.66 s，净约 12.28%。5B：区域任务 6→4（另有 1 个 partial native-scope 保留）；约 193.67 s→163.99 s，净约 15.33%。这些是隔离小组的真实 mapper/规划器时间，不是全麦预测。
- 两组 `targeted_vs_full` 的最终 Q0 FASTA、路径连接种类、切换坐标和源区间均一致；两个小组都没有精确 `sequence_overlap` 连接，因此只能证明“没有误伤已有结论”，不能证明对真正有精确桥接的染色体足够。全补与定向均保留完整目标列表，定向只省掉不触及当前决策前沿的区域窗口；未知竞争仍未被当作不存在。
- 这两组当前 `runtime_known_competitor_audit` 和保守 oracle audit 均为 0 个受影响精确连接；这是小组事实，不扩展为全基因组安全证明。下一步等待 3D 组，它包含 97 条 contig、15 个原分组，最有机会暴露竞争路径差异。

### 11/23 06:28 — 定向补比对已落成显式 opt-in，3D 面板超时不作科学结论

- 本地 `master` 初版增加显式 `decision_frontier` opt-in（后续改在证据命令传入，见下）：先用已完成的参考证据和跨组装基础 PAF 构造 provisional Q0，只在路径端点和未解决 join 两侧保留 source-coordinate shoulder；区域 query/target 窗口仍保留原目标全集，未选窗口不会被写成负证据。若 provisional Q0 无路径或区域路由未启用，回到 `full`；损坏证据等异常仍报错。scope、实际 omitted 数和 frontier 大小写入 catalog；self 矩阵不参与 provisional join 证明。
- 该策略只作用于 `prepare_partial`/`prepare_candidates` 的区域窗口派发；native fallback、完整已完成矩阵、PAF 原始字节、下游 Q0 admission/竞争门不变。没有安装到远端 `43017096`，没有修改当前运行任务，也没有改默认 `full`。
- 本地 Q0 定向测试 **136/136** 通过，其中包含真实 bridge fixture 的 provisional-frontier 读取冒烟；另有决策前沿单元测试与真实小麦 4B/5B 隔离结果。新策略的证据边界仍是允许的信息损失：它可能不再发现不触及当前 provisional 路径的新候选，不得称为无损等价。
- 3D 天然面板作业 `43017437` 于 05:41:05 启动，最终因诊断脚本独立 `timeout` 以 `exitCode=124` 结束；已生成 24 个区域项目回执但没有完整 3D report。该终态是诊断预算耗尽，不是比对科学失败，不重提同一诊断。4B/5B 已完成的结果仍有效。新版 `43017096` 与旧版 `42523432` 仍 RUNNING，06:26:32 已推进到 **23/55**（7B）。
- 用户约定继续只本地 commit，不 push。

### 11/23 06:55 — Q0-only 参数绑定与 3D 回执续测

- `43017096` 06:37:26 复用了第 25/25 项初始检查点（Un），06:37:27 启动 `q0_evidence` attempt=5。未改运行工作区，也未改旧版 `42523432`。不把子步骤 `[START]` 当成新 mapper 进度。
- 改为仅在 evidence 命令显式传 `--supplement-scope decision_frontier`。不写 `prepare_options.tsv`：该文件也在初始染色体检查点输入内，绕用它会导致不必要的失效。显式试验档的 ready 指纹绑定 scope、带宽、规划选择器身份和全量输入；原 `full` 不使用定向 ready，完整的底层 PAF 仍各按原回执复用。无 provisional path 或非区域路由可以正常回退，坏证据抛错。保留实际 `--skip-self` 检查；provisional 直接复用 catalog 中既有长 N 原始邻接，省一次整套 contig 拆分。不是证明加速档与 full 等价，也不是生产启用。
- 初次只读全麦诊断 `43020545` 06:38:35 退出（隔离脚本环境相对路径错误，未读输入）。不再提交会并行扫整套大麦输入的副本；改续做已冻结的天然 3D 对照。独立诊断 `43020546 / agent-X86-18` 使用现有冻结源码和真实 mapper，工作目录在计算节点本地 `/tmp`；对已终态 `43017437` 的 full arm，仅准备复用能逐项验证的 24 个区域成功回执和 1 个 native 成功回执依赖，不复制未提交的产物。定向 arm 不使用该缓存。其 full 准备时间不与定向当成冷启动 A/B 倍率比较；证据/决策差异、上下文数量以及各阶段计时仍有用。06:53 查到作业仍在 provisional 计算，尚无 3D 终态结论。
- 本地 backend 定向 139 项、事故探针 10 项通过。验证了两个 scope 使用相同初始检查点内容、ready 不能互冒、选择器变动拒收、原 N-gap 邻接和坏回执拒收。仍只做本地提交，不 push。

### 11/23 07:09 — 定向档记录未搜索范围，实测生产 loader 已接入

- 截至 07:04 实查，新版 `43017096` 仍运行，实际 owner/run `20261122T175230Z-1840546-b3d5993f` 已复用初始检查点 **25/25**（06:33:13）；06:37:27 进入 `q0_evidence`，07:00:35 在该 run 下出现 `LGZ q0 regional mapper loader: verified_child_only`。这是子进程 loader 绑定已生效的证据，不等于实际吞吐已提升。截至本次观察未看到同一 run 的新增成功区域窗口，不能用旧窗口累计数报进度或 ETA。旧版 `42523432` 仍 RUNNING，不改。
- 本地实验档将每个**主动省略**区域窗口的 query 与原始全部 target 坐标按 source part 合并，绑定到 catalog/ready。只要选中的精确 sequence overlap 的任一证据轴，或选中的 pairwise 定位，与这些未搜索区间相交，就拒绝发布，要求以 `full` 求证；不以“没有搜”推断“不存在”。保守检测可能多拒，且不承诺找回所有遗漏的新候选或其他选路差异。依然只显式 opt-in，不改当前远端、默认策略或原始 PAF。
- 本地 142 项定向回归通过；覆盖真实 bridge fixture 中 target 轴单独遗漏时拒绝发布，以及无关遗漏保留原决定。`43020546` 于 07:00 左右完成 3D-589Mb 小组基础加载和选路，合计 **708.4 s**；截至 07:05 仍在区域阶段，尚未出报告。这是包含 self 的冻结诊断基线路径，不是当前生产选路耗时。独立只读阶段计时 `43020552` 复用同一冻结小组/源码，只取 1 CPU、不启动 mapper，区分输入读取、准入、图构造/搜索和成品整理；路径 `q0-natural-frontier-3d-phase-profile-20261123-0712/`。不重复全麦读取，不重提生产。继续只本地提交，不 push。

### 11/23 07:17 — 定向规划直接读选路坐标，不再预制 Q0 成品

- `decision_frontier` 只需要切换坐标、方向及未解决连接。复用正式构建的同一个 admission/图搜索和跨染色体源区间互斥检查，不再为规划重建整套序列（含反向互补）、展开完整决策报告或为全部基础 PAF 预制一套报告证据字典。没有继续削减选路证据或修改窗口规则。正式 Q0 仍检查原 N-gap 字节、最终证据身份和定向遗漏竞争，并输出完整序列和报告；没有 provisional 路径则明确选择 `full`，其他错误仍抛出。
- 197 项定向测试（含发布、续跑合同和交付）：196 通过、1 跳过。bridge fixture 的规划坐标与完整构建一致；测试禁止规划调用最终 FASTA 重建和报告身份生成；原 N-gap 两侧端点保留。节省的是已确认存在的重复工作，暂不估小麦壁钟倍率。
- `43020552` 07:12:19 明确终态 `FAILED / 1`，诊断 hook 误指新版本才有的 `_links_for_path_graphs`，在读取/解析小组之前退出，无可用 timing。保留失败日志；对同一已冻结 package 的实际 Python import 和所有 hook 通过预检后，修正诊断 `43020641 / agent-X86-61` 07:15:24 起跑，1 CPU、只读原小组，不执行 mapper；目录 `q0-natural-frontier-3d-phase-profile-20261123-hookfix/`。07:16 `43020546` 仍在候选区域阶段；新版 `43017096` 同一 run 仍无新增成功窗口日志。不重提、不热改主任务，仍只做本地提交。

### 11/23 07:23 — Q0 参考一致性只检索实际相交的锚点

- 原 `reference_consistent()` 对每个真实配对块遍历左 placement 的全部参考块，再对相交左块遍历右侧全部参考块；此函数用于 placement 准入和路径图。按同一不可变 placement 缓存定向半开区间及参考坐标偏移，通过 start 和最大 end 的前缀做相交检索。只在确实对应的 source 区间比较两侧映射偏移；保留两端任何叠加/嵌套的矛盾参考证据、反向坐标、端点语义和独立的 pair 竞争检查。不改变选择阈值、搜索预算、选择结果或证据格式。
- 105 项定向测试通过；新测试含 2,048 个正反方向/嵌套等几何对照旧投影，加上边界和嵌套冲突用例。受控合成核：两端各 2,000 个稀疏锚点、2,000 个配对块，同一 Python 进程上旧实现 5.1399 s、首次建索引加查询 0.0059 s、复用索引查询 0.0028 s，接受数一致；不把微基准外推到整套小麦或当前生产任务。
- 07:22 实查 3D `43020641` 初始读取完成（加载约 4.50 s），尚待选路子阶段计时；`43020546` 仍在候选区域对照。`43017096` 和旧 `42523432` 仍运行且不热改。只本地提交，不 push。

### 11/23 07:29 — Q0 等价区间不再全扫，3D 对照已经准备完 full 证据

- Q0 覆盖模型原来每增加一个切点，就遍历同源全部配对块；关联时再次全扫该源原子区间。改为直接检索实际相交的配对块/原子区间。切点在两个相邻块的共同端点仍传播至两边，选中碱基区间仍按半开比较；保留正反向、重叠冲突、边界数限制和真实独立来源，不合并竞争关系、不改变搜索预算。评分也不再对完整覆盖或完全未覆盖的原子构造重复的差集。
- 定向 144 项：143 通过、1 跳过，含端点两侧传播、嵌套关系、源间缺口及随机逐碱基对照。9,000 个稀疏关系和 45,005 个边界的同进程合成基准：构建 13.8385→0.2635 s，10 次切片评分 1.0567→0.3340 s，边界、冲突集、评分和未覆盖坐标完全一致。这是覆盖内核压力测试，不是整套小麦倍率。
- 07:28 `43020546` 的 full arm 出现 `candidates=1776 supplementary_tasks=114 unplaced_segments=0`，已准备证据但还未完成选择与定向对照；不能据此推断省去多少。`43020641` 同时仍在跑，实际过去 13 分钟仅累计约 199 s 用户 CPU；壁钟包含分配/读文件等，尚未出可用阶段报告。新版主任务 `43017096` 不热改、不重提。代码只提本地，不 push。

- 07:32:45 独立 3D selector A/B `43020642 / agent-X86-18` 起跑，目录 `q0-natural-3d-selector-ab-20261123/`，源码全清单 SHA-256 `c192acee3dad4139f81894f676a10c54ced128bf6b88b091557c59c22d09220f`。直接冻结本地提交 `06777d80` / `c4640727` 两份 Server tools 闭包，两者只有 reference/coverage 两个内核源码差异；针对各自完整导入做了预检，未往较老的已运行 package 强行贴补丁。同一节点同一已验证的 3D 面板，两个 arm 都排除 self（同生产定向规划输入口径），不跑 mapper、不读整麦、不写生产目录。比较选路（含备选和诊断）、前沿坐标与源区间摘要；记录 CPU/壁钟和子阶段。先跑 candidate，随后跑 baseline，避免 baseline 单臂超时丢失候选阶段归因；单臂未完成不当成有效 A/B。与含 self 的早期 708.4 s 基线不是一组对照。

### 11/23 07:39 — 3D 实样选路等价；准入重复扫描是下一处主要成本

- `43020642 / agent-X86-18` 07:37:40 成功；两臂均为同一 97 条天然 contig、363 条基础跨组装链接，不含 self。提交 `06777d80`→`c4640727` 的选路、备选、诊断、使用的源坐标及定向结果摘要完全一致。壁钟 38.98→32.68 s、用户进程 CPU 27.65→25.33 s（单轮、未抵消调度和噪声，不外推整麦）。baseline.json SHA `ea8242fc121d8eaa2287b187b0a5dfb93bb955ebd9d05f23cedebaea196f930e`；candidate.json SHA `910b522e2caebe37c6562f4e04441c48c0e87a6c4bce0b249b455d09455ef140`。实样目前最贵的是准入（候选 25.29 CPU s/总 25.33）；图构造和搜索合计约 0.035 CPU s，不能套用此前两种合成压力倍率。
- 追查准入：给无独立参考定位的片段找根依据时，对同一个根 placement 的完整区间做复杂度和已有歧义筛选，原来每个合格配对块都重算。改为仅在有合格块时计算，按不可变 source part 和区间在同一次准入内复用，有界 LRU 128 项并在此阶段结束后释放。区间起点、复杂度抽窗、歧义/竞争、进入证据清单的顺序均不变。合成回归用两个 off-ref 片段、20 个配对块，保留两条定位且整段根区间只扫描一次；145 项定向测试（144 通过、1 跳过）。
- 此改仅本地提交，不 push、不热改运行。旧带 self 3D 分段计时 `43020641` 和真实 full/targeted 派发 `43020546` 仍继续，暂不把上述 3D 基础规划对照当成完整补比对 A/B 或生产生效证据。

### 11/23 07:48 — 实样准入加速确认，保留完整 3D 证据做零 mapper 重放

- 同节点实样 A/B `43020643 / agent-X86-18` 07:44:54 成功（目录 `q0-natural-3d-root-context-ab-20261123/`）；97 条 contig、363 条跨组装 link，唯一 Server tools 差异为 `c4640727`→`01646fb4` 根区间筛查复用。规划壁钟 **37.473→2.167 s**，进程 CPU **27.332→1.752 s**；复杂度筛查 CPU **26.069→0.678 s**。选路（含备选及搜索诊断）、选中源区间、前沿坐标的摘要逐项一致。baseline SHA `0ec069c899ba2e8f6a05a8b347101656e3766c0f9b78a9e1e3efd25871860cc5`；candidate SHA `63b083c3ae7dfced6b7f3fa598190da6e7f6613d8db5396289e951a9e6899461`；代码清单 SHA `b8f46a5b6af7c16ebe96e9f915b9054112d6c5d52fd03e409f7b665b97151b67`。这证明实样基础规划去重效果，不是完整 Q0 或当前作业的倍率。
- 现场旧代码 `43020546` 已记录 `completed full`（114 个已准备补充任务）、进入 targeted partial；后于 07:46:28 **诊断脚本超时 124**，无新 full/targeted 冷 A/B。`43020641` 旧带 self 计时同样终态 124，无完整 phase report；两者均不是生产故障。原缓存和日志留存，没重提同一实验。
- 07:48:01 同原节点 `43020644` 起跑，1 CPU，只读 `43020546` 已终态节点本地 full arm（仅当普通 `load_verified_evidence` 重新完整通过才可使用），完全不跑 mapper、不写两个主任务。用原 builder `q0-evidence-builder-68eab3b311a9df3157fc13ba` 和隔离优化过的消费代码 `q0-selector-256fd5bbfe4dc8593960b36d`，前置验证没有改 builder；固定已有 task graph 测实际可省的投影/独立 raw、成品路径和已知遗漏竞争守卫，不把重放当成动态路由/冷吞吐。目录 `q0-natural-3d-verified-full-replay-20261123/`，清单 SHA `5e6f8b93dd8724211711742e7bb8c55b4bc1f4e025cb4b85e2876f37db12d30b`，前诊断终态 SHA `78f5cb266a46feab58f6d711b64d5a571b6b49a4b85c8b37a3e0f1e04639e0ec`。生产 `43017096` 同一 run 仍在进行，未安装新优化，不重提、不 push。

### 11/23 07:53 — 3D 固定任务图重放：筛选有收益，但当前守卫拒绝直接采用

- `43020644 / agent-X86-18` SUCCEEDED/0；完整旧 full ready `q0-ready-evidence-78de8507df9dc63fdfb5b219` 的文件身份再次核验通过，含 32,752 条基础＋补充 pair links。输出 `q0-natural-3d-verified-full-replay-20261123/result.json` SHA `a121e9db205f47eb6fa8aa111e4e8b867b4f2e9e5b88b58725d0b443d01d0d99`。无 mapper、无对原目录写入。
- 3D 固定 full 任务图按当前基础前沿保留 **113→54 个区域 raw/project**，另外 1 个原生任务原样保留。54 个保留窗口中 45 个仅 target 触及前沿；若只看 query 会把这些窗口误删。省掉 63.7% query bp、只省 3.46% target bp；数量或碱基数不能替代测到的冷 mapper 与整段墙时。基础定向规划 2.52 s，已有证据下 full/targeted 构建 51.79/45.33 s，不含补比对执行。
- 此面板 10 条构建路径的 FASTA、来源和切换均一致，保留全部 3 个精确 overlap；但是**当前省略守卫拒绝**，因为选中的 pairwise 定位仍碰到未查过的源范围。重放中未观察到结果差异不等于竞争已证伪；不启用、不降级守卫、不重提生产。下一步对这些具体定位反查 59 个 deferred 上下文，在固定任务图上计量需补回多少、重选后有无新的未查竞争，而不是直接补回所有任务；该过程仍需独立验证动态路由及真实总耗时。

### 11/23 07:59 — 只补已选证据可能受影响的原窗口

- 新增 `selected_proof_frontier`，复用发布守卫原来的三类坐标：选中 pairwise placement 的完整源范围、其成对证据两轴、精确拼接证据两轴。结果只是下一轮补查的候选范围；不会授权当前选路，也不会因换了函数而把原有遗漏判成已搜索。完整保留目标侧命中、源 part 偏移和在新一轮重选后再次审计；不拆或改已规划窗口。整组 Q0 130 项通过，另补的偏移/成对定位测试所在 frontier 模块 11 项通过。版本仍仅本地，不部署生产或 push。
- 已终态 full graph 的独立只读 `43020647 / agent-X86-18` 已 RUNNING，目录 `q0-natural-3d-proof-repair-replay-20261123/`，代码清单 SHA `e4677ba165944f1e449253e1dcdfd9a5fc9a9043a36c4524ca5d1a21d64a73f3`，绑定上一轮已成功报告且再次验证原 ready。初始保留 54 个，最多补回 3 轮，每轮只选与当前正证据相交的 deferred 原上下文，并按原证据重新选路且重过校验。没有重新运行 mapper，不接触生产工作区；要看的是允许保留多少省略而能通过原守卫，以及最后序列/来源/切换风险，不把固定任务图估算当生产墙钟。

- 08:03:36 `43020647` SUCCESS/0；报告 SHA-256 `e36927ebeba266a963c8814ca7654c2f4b414cb7dfa71996c851381aff72f7e7`。**一轮补回 32 个完整 raw/project，区域工作 113→54→86，仍省 27 个（23.9%）**。原守卫通过；10 条构建序列、来源及方向、3 个精确连接均与 full 不变；原生补充任务保留。已验证输入的构建墙时 full 43.28 s、初次定向 42.98 s、补查后重选 46.72 s，基础规划 2.32 s。即固定任务图的一次二阶段策略要拿约 **49 s 额外选择成本**与 27 个省下的 mapper（以及出入文件）比较，不能只按窗口数转成净提速。下一步同时量加权成本和是否能用 provisional 的正证据范围预先纳入部分竞争窗口，避免第二次选择；均须保留最终守卫。08:03 新旧生产仍 RUNNING，现行尚未部署此模式，不重提。

### 11/23 08:12 — 首轮正证据预判不足；跳过的窗口不能按数量估值

- `43020721 / agent-X86-18` 08:11:46 SUCCESS/0（固定任务图诊断）。将基础 provisional 已选正证据两轴纳入首轮，**没有新增任何窗口**，仍保留 54/113，最终序列不变但原守卫仍因已选 pairwise 定位范围未搜索而拒绝。说明这个案例仅用基础正证据无法替代补比对后的复判，不作为一阶段上线依据。隔离实验 `q0-natural-3d-one-pass-proof-replay-20261123/`，源码清单 SHA `4148bc88d9a8b3342663df4cf8cafea78af74f88d2bfc254526ce7b00dd3b588`，报告 SHA `9b54883b2de4262fd10816c0c958413c0b25bbc72758688849d0445ecbb72bdc`。
- 初始被跳过的 59 个精确 raw 中，57 份留存日志合计报告 minimap2 `Real time` **542.73 s**；初始保留的 54 个中只有 32 份留存（其他来自复用或无日志），这 32 份合计 **6.17 s**。每个原 raw 和粗链回执都由 ready 绑定，stderr 计时本身不在科学回执内，只作历史服务时间诊断；缺的日志不填 0，不比较覆盖不全的两组总量，不折算生产并发墙时。该对照重点是明确少算的可能是重窗口，但其中多少在补查时被加回，尚需分组。
- `43020722` 已在同一节点起跑（`q0-natural-3d-weighted-proof-repair-20261123/`，清单 SHA `ad0fcfd102ba5389594fa1d25348e4cef87faa409a3d97be84bdf712e51ce0f0`），按已通过的 86/113 方案重新核准最终仍省的 27 个 raw，再绑定到已有 mapper 日志，零 mapper、不写原图。若剩余重量不足抵消额外约 49 s 选择成本，优先止损不接该策略；有余量才做同节点冷派发/最终报告和真实总墙钟。至 08:12 新版 `43017096` 保持原 owner/reader、内存约 31 GiB，有 CPU 进展但仍无同 run 新区域成功日志；旧版无改，不重提、不 push。

- 08:15:41 `43020722` SUCCESS/0，报告 SHA `f3b97788ed375c2ceff2bc5513ff4c466d63cf18b362f1e615f1d70427978e16`；86 区域＋1 原生的补查结果再次通过原守卫并逐条复现 full FASTA。最终仍省的 **27/27 个精比对**均有日志，历次归档自报 `Real time` 合计 **541.777 s**、CPU **536.013 s**，另 27 个粗链合计 **2.693 s**；相比原先 59 个省略上下文里能看到的约 543 秒，这些重任务几乎都仍可省。补查加回的 32 个里 30 个有精比对日志，合计只增加 0.948 s；2 个缺失不能当零。按这份实样选择验证，值得下一步做真实冷派发和完整壁钟，但时间是各次 mapper 自报服务时间之和（含可能单个重长尾），不是整段 SLO 或生产恢复后的剩余时间。以同节点同工具/资源做前瞻实测，问的是“完整原上下文先定向派发、发现正证据后仅补查并重选，包含规划/I/O/最终审计是否净快”。选中上下文完整复用，不再尝试已证否的基础正证据一阶段预测。08:15 新版仍在原 run `q0_evidence`，未改远端运行或默认、只提交本地。

### 11/23 08:24 — 同节点冷跑全量与真实按需补查

- `9e92a94f` 增加隔离工具 `run_wheat_proof_repair_cold.py`：两组使用同一冻结天然 3D 输入和 minimap2、各自空缓存。实际 Server planner 与派发/回执不打桩；实验仅适配已冻结初始矩阵输入和范围身份，不读生产工作区。定向先跑，若原发布守卫报告已选证据有未搜索范围，只扩张相交范围，使用同组原回执可精确复用的窗口；如果动态路由改变则实际重做所需窗口，最多两次补查。重新读取并校验真实 ready、完整选路报告而非只比较 PAF。两组计规划、派发准备、回执验证、完整读回、选路/核验墙时；另计每轮实际 regional mapper 启动与累计服务。私有定向身份不被普通 loader 接纳，不能迁入生产。
- 本地后端 60 项、附加事故测试 5 项及临时小型冷准备/选路冒烟通过；受控冒烟仅验证接线（没有实际区域 mapper）。`43020726 / agent-X86-06` 已运行，实际 6 CPU、调度硬内存 60 GiB（脚本申请 16 GiB，不能把申请当硬限）；独立目录 `q0-natural-3d-cold-repair-ab-20261123/`，清单 SHA `d534673fac1c563f88a7a96f417f21d5929f436a70d557255f3f8e82a06d6388`。08:24 实际首轮定向派发已产生 55 个补充任务的 ready（包含 1 个原生），尚未公布穿过最终校验或完整 A/B；不把首轮 ready 当成成品。新版 `43017096` 同一 reader 仍运行，约 32 GiB，日志尚未记录本 run 新窗口，不重提、不部署此实验、不 push。

- 08:26 实查真实冷定向组已完成两轮并通过原守卫。首轮实际启动 54 个精比对（22 个粗链）、约 14.47 s 准备，首次选路 33.32 s 后如预期要求补查；第二轮实际仅启动 **32** 个新精比对（26 个新增粗链），准备 7.42 s、读回校验 4.32 s、重选含守卫 33.27 s，剩余 27 个未搜索窗口。以实际分段计时为准：两轮分别约 **51.21 s** 和 **45.01 s**，合计约 **96.22 s**（实验的最终 arm_wall 与报告为准）。全量冷组同节点已进入 partial，尚未完成，不能报净收益/成品等价。后续若考虑接入，必须在 `lgz_prepare_inputs` **实际 reads/QC 过滤后的选路**重作原守卫；诊断不含 reads 质量决策，也不覆盖 donor/Step1。不能在下游已捕获输入指纹及复制 ready 的事务内无声明改写 manifest 后继续使用旧指纹。

### 11/23 08:35 — 3D 冷对照完成，开始验证真实 Server 入口

- `43020726 / agent-X86-06` 08:31:06 SUCCESS；报告 SHA-256 `9abba70ff410486d4026a7d613f7d3b49009e2da1f7aa24238285b00458ede17`。同一节点、6 CPU、每臂新工作区冷启动真实 planner/mapper/回执，定向＋一轮补查 **96.239 s**，full **333.247 s**（**减少 71.12%**，3.46 倍），两臂共用的已冻结初始证据加载不计。全量精比对 113（粗链 75），定向精比对 54＋32（粗链 22＋26）；实际原守卫通过。10 条构建 FASTA、来源区间、方向、3 个精确拼接及缺口类型计数相同；无来源坐标差集。此为单轮 97 条天然 contig 面板，不是全麦、reads 支持、供体或当前运行的实测倍率。
- 已核实新版 `prepare_lgz_inputs.sh` 无 `--reads` 且包 `reads_qc_enabled=false`。真实 Server 入口拟用显式 `decision_frontier_repair`：不把私有实验策略注入生产，不修改默认或初始检查点；正常准备可回读所有验证回执，临时选择失败按真正省略冲突扩大范围，最多 2 轮再全量。各轮只在内存传递 draft，唯一 canonical ready 在所需校验及签名栅栏之后发布；已冻结的下游输入不回写。试验档只接受已绑定的 no-reads-QC `package.tsv`；reads 模式另行设计下游证据依赖，不能直接套用。本地运行无变化、更没有用 3D 倍率证明整麦。仍只本地 commit，不 push。

- 正式入口实验档已本地提交 `a5be991e`；172 项定向测试全部通过，覆盖仅在最后发布、普通下游按同一格式读取、no-reads-QC 前置门和选择时输入漂移不写 ready。实际入口隔离作业 `43020729 / agent-X86-06` 08:39:58 起跑，清单 SHA `138d1ebea2422cb86ae38ccf78aac992d6e55587a4febc9c4f2f5533dcb633f6`，目录 `q0-natural-3d-native-repair-entry-20261123/`。与前一实验不同，此次不用私有范围/策略注入：真实 `prepare_evidence(..., supplement_scope=decision_frontier_repair)` 内置补查及发布，再走普通 `load_evidence_input` 和最终构建，核对同一份全量冷对照的所有最终 FASTA 哈希；还保留输入小组适配，非整麦。08:40 已产生首轮 55 个补充结果的**私有 draft**，不等于 canonical ready 成功。两个主作业不动。下一步用真实入口计明包含重复验证/真正消费者的净收益，再看全麦恢复/已缓存工作能否抵消接管成本；不能用这份面板结果直接切换主任务。

### 11/23 08:46 — 正式入口实样通过；补查不再重扫初始矩阵

- `43020729` 08:42:17 成功，报告 SHA-256 `2fb5128cb60cfc0ca3a893c0169260c4bf913258a800544a7ac28786bf6d23ee`。真实 Server profile 只补查一次，证据 ready **94.68 s**，包含此后的普通消费者独立读回/选路 **131.74 s**。仍是 86 区域＋1 原生，25 个候选与 2 个 partial 窗口未运行；普通消费者的 10 条 FASTA 哈希与完整冷对照一致。测的是自然 3D 小组＋已验证初始输入适配，不能用 131.74 / 333.25 s 当同轮、同代码入口 A/B 或生产接管预算。
- 整麦准备的前置输入重扫昂贵；本地补查现在同一进程只执行一次原 `_initial_inputs`（含普通外层检查点与分区/初始 PAF 验证），后续轮绑定同一批文件的 resolved target、dev/inode/size/mtime/ctime 以及已全量校验的 SHA。若基准有漂移就失败，不采用旧 snapshot 或暗自重算；不跨进程复用。重复轮只重读源 FASTA（避免持有重复全基因组 DNA），保留各轮已验证 byte identities、PAF 内容/闭包、原始完整输出和最终发布守卫。各轮从同一初始 `ObservedSourcePairs` 独立复制，可共享不可变合并区间但不共享新增观察。普通全量路径不变。
- 179 项定向测试通过，含原初始输入只验证一次、两轮观察隔离、结果正常发布、选择中漂移和两轮之间初始 PAF 漂移拒绝；只提交本地。新版生产截至本次检查仍 RUNNING/同一 reader，原有区域输出目录未见本轮新增，不能为补丁再次机械重提。

- `d9b80b64` 的隔离验证 `43020733 / agent-X86-06` 08:48:09 起跑（`q0-natural-proof-repair-bound-inputs-20261123/`，清单 SHA `195a576ea3339043f702099b1c14a7897b5f23c691fb247a8c3d95582bcdee58`）。3D 只重跑实际新试验档，逐条对照已封存 full FASTA，要求一次初始读取、一次真实补查；另 4B/5B 用同一套实际新代码各自独立 cold full/proof 对照，防止把 3D 重窗口结果外推到轻样本。08:48 已到 3D 首轮私有 draft（55 项），等待后续原守卫和真正消费者。此作业无生产读写，主运行仍在原阶段，暂不部署、不重提、不 push。

### 11/23 08:54 — 三个天然样本通过核验；轻任务不适合默认开启

- `43020733 / agent-X86-06` 08:51:27 SUCCESS/0；整份报告 SHA-256 `b0572aca559270d98ded446b4519c17e0ea79a6deeacd5e820f315694c5fd7a9`。真实 Server 入口 `d9b80b64` 的 3D 定向档只读取一次初始输入、一次补查；仍保留 86 区域＋1 原生，读回消费者后 **128.95 s**（到 ready 92.98 s），10 条 FASTA 与原全量冷对照一致。不是与 333.25 s 同轮的 A/B，不用于推出当前整麦 ETA。
- 同节点、同版本、各臂独立空缓存，4B 全量→定向 **8.52→29.41 s**（最后仍需要 4 个窗口），5B **8.49→14.81 s**（6→4 个窗口，另有 1 个原生）。两样本的全部序列、来源区间和切换审计一致。轻任务上少跑几窗不抵额外选路/验收，拒绝把定向档改为默认；也不以这两个小样本推导随意的 contig 数阈值。
- 新工作区可用 `run.sh` 或 `prepare.sh` 显式传 `--q0-supplement-scope decision_frontier_repair`；默认或显式 `full` 生成原命令。作用域仅生成的 `prepare_q0_evidence.sh`，不写 `prepare_options.tsv`，不修改参考/分组/初始染色体命令，也不是续跑资源参数。已有工作区不能用该选项热切换；正式接管仍需保全已有结果并复核当前全麦增益。20 项 runner/参数测试通过、Bash 语法通过；三个本地实际命令生成工作区逐项比较，只有 opt-in Q0 命令不同（本机 MUMmer 缺少新版 `--batch`，此生成冒烟仅替换工具 help、未运行比对；真实 mapper 见远端试验）。只本地 commit，不 push。

### 11/23 09:09 — 真实工作区切换预备包通过元数据校验，未安装

- 本地 `7997a38e` 为已有工作区的隔离 Q0 reader 增加显式 `decision_frontier_repair` 绑定，保留原 `clear_same_dependencies_v1` 子进程 loader 策略。按真实 builder/selector source inventory 和原 runtime 文件 SHA 校验；仅接受同一份 SHA 绑定且 `reads_qc_enabled=false` 的 `metadata/package.tsv`。外部冻结 reader 调用约定及默认全量不变。事故工具 98 项定向测试通过（迁移准备、reader、context、stage、resume 和 loader launch）。
- Donau 比较根下 `q0-proof-repair-candidate-20261123-0904/` 的实际预备包成功：`candidate-prepared.json` SHA-256 `49bdb323f0aa52b4a3cc2ca0e433340b712cba85fa6ccf99dcfa5fe3a8d2810e`，`transition.json` SHA-256 `6c975c673aa54c0c90ae9ef9352cc91507f533b5b2554896c9a36263f81f2582`。核对原安装回执 14 个 runtime 模块加 launcher/reader declaration 共 16 项；新候选闭包 18 模块（builder 15、selector 7、有交集），其中 12 项改变（含唯一新增 `q0_frontier_scope.py`）。四处原 builder 策略/参数与两处 admission/path 策略类均 AST 等同。范围选择本身有意变化，不由 AST 等同推导结果等同。
- 这是隔离目录内的 `q0_candidate_prepared_not_installed`，没有安装回执、没有实跑候选、没有证明现有缓存可完整接管。09:09 新版 `43017096` 与旧版 `42523432` 均仍 `RUNNING`，新版 owner/run 未换、`q0_evidence` 已运行约 2 小时 32 分，仍无本轮新区域窗口或 canonical evidence；最近一次实际子步骤日志仍是 07:00:35 的 loader 探针。未停作业、改生产工作区、重做整麦对照或 push。再次切换至少须有完整只读复用预检和现有剩余工作量证据；不要用 3D 小组倍率抵算约 5 小时已实测的重启到 Q0 开始成本。

### 11/23 10:25 — Q0 输入规划扫描省去不消费的逐行身份构造

- 新增 `2d4ed69`：`_initial_inputs` 用与正式 reader 共用严格 parser 的几何视图构建 observed source pairs 和跨组装覆盖。不再为这一遍生成每行 SHA、可引用 evidence ID 和 tag tuple；每个分区内复用 source key。仍检查 UTF-8、名称、长度、数值、方向、CIGAR 语法/双轴跨度、完整初始检查点及绑定整份 PAF 字节；真正消费证据时仍走带真实行号、行 SHA 和 tags 的 reader。未省略任何记录、候选或坐标。186 项定向测试通过，含 reverse、插删、X-only、gap-only、CRLF/CR、无用 ID 计算拒绝及坏行/长度漏读回归。
- Donau 隔离 `43021269 / agent-X86-06 / SUCCEEDED`，Python 3.10.12，1 CPU，目录 `q0-observation-scan-ab-20261123-1023/`，源码清单 SHA-256 `73abecdb52525333e82fa19d829694361d5d1c8747ff28adc4a3c638826c03b6`，报告 SHA-256 `2c9a37b8d459fd7c0fc4e59e1b6f1b2e81a5aebef7afedd5f44289347b3e7bfb`。同节点本地临时盘，ABBA 分别用逐行带身份路径和精简几何视图；合计 **72,467 行**，每组完整关系集合、合并覆盖区间摘要一致，6B cross 有 546 条 source 的合格覆盖。分组均值：1B flye self **1.764→1.083 s**（−38.6%），2A hifiasm self **1.675→1.073 s**（−36.0%），6B cross **2.128→1.813 s**（−14.8%）。这是原 PAF 的有界完整行切片、由切片建名长输入表；不含整文件 SHA、初始 checkpoint 校验、全麦内存/共享盘成本或 mapper。测试未写主工作区、未导入采纳产物。
- 10:25 的生产元数据：22 个 cross PAF 约 20.0 MB，44 个 self PAF 约 12.50 GB（文件长度，非有效用量）。输入扫描确实覆盖大矩阵，但不能用有界片比例推整麦节省的小时数。新版 `43017096` 和旧版 `42523432` 仍 RUNNING；同一 Q0 run 未出现新区域结果，`userCpuTimeTotal` 在 10:23:49→10:24:37 从 10113→10152 秒，不能据此定位确切输入。当前冻结 runtime 与 09:09 已封存候选均未替换；未停作业、不 push。

### 11/23 12:24 — 先筛整条父序列并没有额外省掉窗口规划

- 独立只读作业 `43022784 / agent-X86-06`（12:21:42–12:24:23，SUCCEEDED/0）。18 号节点无可分配核，06 上已有 `43020726` 的同一 3D 面板冷全量归档。复用其**自己的** builder、selector 和 ready `q0-ready-evidence-6588fa57f9c1a6b758a8278d`；不是 18 号节点的同一份 ready。提交前核对两份既有全量报告的构建 FASTA 哈希集合相同；回放前后重新校验输入与完整输出。没有执行 mapper、安装候选或重启主任务。
- 先用基础参考/跨组装比对给父分段列候选；再用已归档的窗口核对是否漏掉确实需要的查询。两轮的需求分别涉及 12 和 51 个来源，但参考坐标范围太宽，两轮都留下全部 **97/97 个父分段**；其中 80 个实际提供了归档区域查询。原有 113 个区域窗口中，按父分段**可提前排除 0 个**，漏掉必要窗口数也是 0。此整段筛法不接生产；若继续试，应在实际窗口的查询/目标区间和 CIGAR 块上衡量能否更早排除，不把参考重叠当正证据。
- 后续按决策所需再筛窗口，首轮保留 54，校验要求补回 32，最终 **86/113 个区域窗口（少 27，23.9%）**，另 1 个原生任务保留。原守卫通过，10 条构建序列、已选来源区间和方向、精确连接、参考未表示长度一致；按来源、区间、方向和连接类型去重的 46 个备选路径几何也无增减。27 个来自已有窗口筛法，不是父级筛法的新增收益；本次 161 秒是重放时间，不是 mapper 提速，不能外推全麦约 61,000 个计划窗口。
- 本地证据：`incident-tools/wheat-20261119/q0-reverse-parent-3d-cold06-20261123.json`，SHA-256 `e3470e1a70e67c143aaa025693668ed2a099c6b4e7935d16df1ced92a2a5a031`。远端 `q0-reverse-parent-replay-20261123-1210/cold06/` 保留提交/作业日志与绑定清单；回放代码 SHA-256 `85beac732ab1c9595dac5f3af9691aae2b34017fabe8ca0454316ea04d80a1b1`。

### 11/23 12:32 — Q0 真正引用了哪些区域补比对？移除后是否改变结果？

- 只读作业 `43022809 / agent-X86-06 / SUCCEEDED/0` 再次核验同一 3D 冷全量 ready `q0-ready-evidence-6588fa57f9c1a6b758a8278d`。按不同区域投影任务计数，不按 PAF 行数：113 个中 **5 个**在赢家路径的 placement 或 join 证据 ID 中被引用（其中 3 个见于 join）；**13 个**只在备选路径相应字段中出现而未被赢家引用；**10 个**只在其他决策证据登记中出现；**74 个**有投影行但没被前述三类字段直接引用；**11 个**没有投影行。分类按此顺序互斥。`projected_hits_not_cited` 仅指上述直接引用字段和 `decisions.evidence`，不是说其记录没参与竞争、覆盖评分或歧义检查；`no_projected_hits` 也不等于 mapper 原始输出为空。
- 将全部区域输出对 Q0 选择器屏蔽，仅保留原基础证据和 1 个非区域原生补充；另试事后只保留赢家引用的 5 个区域任务。两个实验均从各自可见证据重新准入和选路：10 条 FASTA、来源/方向、精确连接、未表示参考长度及备选路径几何集合与完整对照均无变化。**两组都未通过原未搜索竞争区校验**，不能发布，5 个也不是事前可知的最小集合。不删任何已完成证据，不关守卫，不跑新 mapper。相比之下，同面板已有修补方案保留 86/113，原守卫通过。
- 下一步可将重点从“先列全量窗口再过筛”改为“先用基础证据和已完成的原生结果生成 Q0 草案，找到可能改变定位、精确切点、竞争路径或供体占用的具体区间，再发起必要的双侧验证”。对不能排除的竞争保留原范围补查或全量回退，须以前瞻而非事后赢家列表对照验证，包括已知需要补证的反例。此 3D 观察不授权整麦零区域补比对。
- 原报告：`incident-tools/wheat-20261119/q0-window-use-3d-cold06-20261123.json`，SHA-256 `6ef380b44e9b4dc0cd5039a50b11daceadbd6920fd19ea9dd13793bec0090af7`；远端 `q0-3d-window-usage-20261123/`。本地只读诊断和相关 18 项测试在隔离的 master 代码上通过。

### 11/23 12:44 — 先选草案再请求比对：三个归档面板与内部竞争片段反例

- 两个单核只读对照 `43022884`（切点/同分备选/现有正证据）和 `43022888`（再查可能新定位的片段），均在 `agent-X86-06` SUCCEEDED/0。第一次草案仅使用基础对照（含 self），不看任何区域或原生补比对输出。根据两轴窗口输入几何冻结所请求的 ID 集，再向算法提供这些窗口的证据和完整保留的非区域原生任务；重选后重新提问，最后才查看全量答案。无草案、未排除竞争或请求预算耗尽回全量。两组均保持生产原有遗漏守卫。这是已知任务图上的盲选，而不是动态生产规划或冷 mapper 实验。
- 原始区域窗口 **3D 113、4B 4、5B 6**。只查草案切点和正证据，实际请求 **86、4、4**；额外查“某个未定位源区间可以通过对应查询/目标的已定位一侧取得定位”后，请求 **102、4、4**。3D 因新定位多要 16 个，净少 11 个（9.7%）；4B 不减，5B 少 2 个。三个面板两组均一次提出所有需要的区域窗口，未触发全量回退；成品序列、已选来源和方向、精确连接、参考未表示长度以及备选路径几何在对照中没有差异。不表示所有决策记录相同。
- 不能只选请求更少的一组：一个有真实序列对应的受控反例中，500 bp 未定位序列确实匹配已定位源的内部，两侧都不碰赢家的切点。切点版本保住了赢家序列并通过原守卫，却丢掉全量对照的一条备选路径；加入定位询问才发现它。反过来不能把“可能新定位”不加区分地扩成大规模精比对。
- 事后仅用于诊断：在重现**全量那套正证据坐标**的条件下，3D 有 **82/113** 个窗口的一侧碰到原守卫保护区（4B 为 4/4，5B 为 4/6）。这不是说 82 个都贡献正证据，也不是所有可能算法的数学下限；它解释了为何仅缩小切点范围仍很难大减窗口。下一步应在请求精比对前区分真正可能改变定位/方向/接头的**来源对和区间**与单轴重叠；验证必须包括这个反例，不直接削弱发布守卫。
- 本地 `incident-tools/wheat-20261119/q0-blind-draft-three-panels-20261123.json` 包含各臂原始报告哈希、请求集摘要、计数和逐染色体差异；远端 `q0-blind-draft-requests-20261123/{,with-localization/}` 保存六份原报告与作业日志。独立 master 工作目录通过 25 项诊断测试及 55 项既有范围/路径测试。不改生产、不重启，不将面板结果乘到整麦计划数。

### 11/23 12:59 — 双轴序列筛选能排除目标对，但不足以跳过昂贵的整个补比对窗口

- 已冻结 3D/4B/5B 面板上，先从草案提出定位/连接问题，再用查询和目标的实际窗口序列筛掉不能满足“≥100 个配对碱基、列一致率 ≥95%”必要条件的目标对。不看已完成的 PAF 来挑选任务，不拆保留窗口原目标组。筛选利用任一合格比对必有 100–199 列的局部块仍达到该一致率；该块在同一方向的对应区间至少共享 5 个 16-mer 和 53 个 8-mer（计出现次数），不是随机 sketch。模糊碱基或过多重复工作保守保留。这个界只针对该门槛，不是假定 mapper 不会产生弱命中，也不证明这些配对一定改变 Q0。
- `43022901 / agent-X86-06 / SUCCEEDED`：3D 2299 对排除 223，对应草案请求从上一版 **102/113 → 96/113**；4B **4/4 → 2/4**；5B 仍为 **4/6**。已达到上述门槛的归档投影行分别 11859、8、62，实查三组均无误排。已选序列、来源方向、连接、参考未表示长度及备选路径几何未见差异，但**3D 和 4B 均拒于原遗漏守卫，仅 5B 通过**。因此没有把不可能提供强匹配的 pair 冒写成完整搜索，没有发布这个结果。弱命中仍可能影响上游候选/后续路由。
- `43022903 / SUCCEEDED`：在全麦真实运行归档中，从已有 64 窗原生对照固定取序号 0,8,…,56；完整输入 FASTA 共 199875514 字节，与原回执逐一核验。7411 个查询—目标对中 1684 个可排除（22.7%，占目标碱基 19.4%），覆盖 813 个实际有门槛命中的对，无误排；但 **8/8 个窗口都仍有可比目标，整窗调用一个也省不了**。没有实跑缩短目标表的 mapper，不据此换算墙钟。
- `43022906 / SUCCEEDED`：对 1189 个已经完成、每个都有唯一 raw/project 关联的全麦区域窗口，绑定原始成功回执、窗口几何、源 part、完整 raw PAF SHA，按原投影规则读取真正落在 core 的命中。单独只读 229443617 字节的 raw PAF。**1177 个至少有一个上述门槛命中、4 个仅弱投影、8 个无投影。** 只凭“所有目标均不可能有强匹配”排整窗，即使用事后答案，在这个批次也最多排 **12/1189（1.0%）**；这 12 个原 mapper 服务时间合计 **23.223 s**，相对全部 8280.383 s 约 0.28%，不是净墙时。1177 是“确实存在符合门槛的匹配”，绝不是“1177 个决定都需要”。此批次并非对剩余 61k 任务随机抽样。下一步应检验已有证据能否确定同一源对/方向/位置的决策、哪些新关系可能翻转定位或路径，而不要继续仅按“是否能比上”加码。不得按此比例外推全麦。
- 三个作业均未新跑 mapper、改写已准备的证据或重启主任务。远端 `q0-pair-capacity-20261123/` 的清单、各作业和原报告 SHA 记录于 `incident-tools/wheat-20261119/q0-pair-capacity-wheat-20261123.json`；本地隔离 master 上相关 87 项测试通过。

### 11/23 13:16 — 新位置不等于新决策；按已知位置过滤没有进一步减少整窗

- `43022961 / agent-X86-06 / SUCCEEDED`：冻结 22 个初始染色体检查点和相应组装间 PAF（20,024,243 字节），只读复核前一轮的 1189 个已完成区域窗口。把区域查询、目标都投回**同一来源对、方向、偏移和实际配对块**；同一映射可合并覆盖，不能拿另一位置、相反方向或中间的缺口来补齐。基础 PAF 不设质量下限，区域命中须达 ≥95% 且有 ≥100 个 M/= 配对碱基。1164/1189 个窗口在查询 core 中确有连续 ≥100 bp 不在任何相同的初始跨组装映射内；其中首个见证为 1143 个新源对、15 个已知源对同方向的新偏移、6 个已知映射的延伸。这只测跨组装关系，不读取 12.5 GB 自比对，不是全麦随机样本，也**不说明 1164 个窗口都是构建 Q0 所必需**。
- `43022964 / agent-X86-06 / SUCCEEDED`：在不知道区域输出时，用已有同方向、同位置的单一连续坐标映射解释整对查询 core；若还已知第二个位置则不省略。额外约束没有比上一版“草案定位＋切点”再省任何整窗：3D **102/113**、4B **4/4**、5B **4/6**。三者均过当前遗漏守卫，逐一对照构建状态、序列、来源方向、拼接、参考缺失长度及备选几何均无差异。事后查出 3D 65/113 个窗口、5B 6/6 个窗口确有 ≥100 bp 新位置，但这些窗口没有被最后所选路径直接引用。5B 还发现 **3 个事前判为“可用原位置解释”的来源窗口对中有 1 个确有新位置**。该结果否定了“覆盖一个已知位置等于没有别的位置”，没有否定“新位置可能不改变本次决定”。面板基础索引只纳入达门槛记录，与上一条全麦基础索引口径不同。原始命令和报告在 `q0-cross-locus-20261123/`；仓库计数、原始 SHA 和检查点清单身份见 `incident-tools/wheat-20261119/q0-signed-locus-wheat-20261123.json`。
- 检查新版作业的**本轮**原始日志：`43017096` 从 10:56:38 的 100 个进展至 13:11:35 的 **15000/61000**（`fallback_sources=0`），`q0_evidence` 第 5 次执行尚无最终 ready；这是 `consume()` 收到的任务结果数，不是新启动 mapper 的数量，也不是上述实验已部署。旧版 `42523432` 仍在运行，未改动任何生产输入、缓存或进程。
- 新的只读对照 `43022980` 于 13:16:06 在 06 节点实际起跑；在看全量答案之前分别使用“只有基础证据”“基础＋原生、零区域”构建草案。除了 FASTA/已选路径，它还用真实 `available_intervals()` 检查可作供体的来源区间，分开比较未知区、未放置来源和备选定位，避免把“FASTA 没变”误作“下游全没变”。不把任何草案发布成最终证据。封存 `q0-draft-consumer-fields-20261123/consumers.sha256` 的 SHA 为 `f8fd46c70e6a258d7cd21aa868b7c990cec435c34e0e5443f9374eb184c9df0c`。
- `43022980` 13:18:33 `SUCCEEDED/0`。**3D、4B、5B 分别不使用 113、4、6 个区域补比对窗口，甚至连 1、0、1 份原生补充也不使用，仍分别复现全量的 10、1、1 条 Q0 序列**。逐臂核对九类对象：FASTA；按顺序的来源/方向/切点/接头；参考缺口精确坐标；已占用来源坐标；通过发布代码得到的可作供体区间；未放置片段；已知候选定位几何；备选路径几何；已知歧义区间。三个面板两种草案的这九项均无差异，包括逐来源坐标而非仅长度相同。原始报告和字段哈希见 `incident-tools/wheat-20261119/q0-zero-regional-consumers-20261123.json`。没有据此推断证据引用、搜索完整度或真实全麦输出相同，也不是新的冷运行计时。
- 用正反两个方向的桥接夹具检验这个对照能否发现“确实不能省”的结果：三个来源都有参考定位，但去掉真正支持两个接头的配对比对，定位清单仍相同，Q0 序列、已选路径、三个来源可作供体的范围均发生变化。另一个内部重复片段夹具只改变备选定位，不改变所选路径及供体。故后续验证要让程序只看构建草案时的证据，**区别能定位来源与能证明具体接头**，在新材料上验证强证据停止、弱接头补查；不按三个冻结面板的零窗口直接切换主任务。隔离 master 基线及本次诊断代码定向回归 133 项通过。

### 11/23 13:30 — 首个按“已有点过线，不为竞争额外搜索”运行的盲测（实验，不是生产选路）

- 在只看到基础证据时先构建草案。对每个选中来源片段，用现有 admission 合格锚点检查两端分开的窗口是否各有至少 100 个连续支持碱基；不因已有备选或理论上还有备选而发起请求。已由 selector 证明的精确接头或已知输入缺口不追加比对；未知接头如果已有达到原配对阈值、方向相符且接近两端的配对证据但仍不能安全选择切点，则保留缺口；没有足够接头证据才请求两侧。没有可信草案保留全量回退。初版对有归属但没构建出骨架的染色体保守请求有关来源片段。这个实验不声称无未见竞争者，也不改变 `construct_q0` 的许可条件。
- 不以已看过的 3D/4B/5B 作验证集。用固定算法只读同一批 assignment 元数据，按目标 8、16、32 条 contig 和两个组装的平衡度选取从未用于上述面板的来源与其他染色体，不看补充比对、选路结果或耗时。`43023026` 成功冻结 **2B-8Mb / 3B-792Mb / 1B-689Mb**，原始参考和成员间基础 PAF 均保留并核对原回执，冻结库存 SHA `74a9002ea542d188702251bf57543115790822774f918003da0b34980d67f21b`。
- `43023038` 在 `agent-X86-06` 于 13:27:53 实际启动。四核、同一 minimap2；每个面板先盲测再全量，各臂独立空目录，真实派发，分别数新精比对、粗链、原生调用，核结果时另对照九类几何字段。只有私有 in-memory manifest，绝不写入生产 workspace 或给草案写 canonical ready。冻结程序清单 SHA `5ef2a91b87b5ad5764656f71f11d48ce89930d1c4e45bc2e8eb72cc92f6cb40d`，远端目录 `q0-heldout-draft-threshold-20261123/`。2B 无可信初始草案，已按原样回退，两个臂分别跑 14 个区域精比对、11 个粗链，最终两边均没有可信路径；不是成果等价的阳性样本。隔离 master 基线 136 项定向测试通过，包含真实竞争命中不触发新请求且不授权精确接头的正反方向测试。
- 13:33 核过两个首轮盲测回执。3B 的草案有一个过线的定位，但另一个未构建染色体的 assignment 把 16 个来源都加入请求，结果 **36→36** 个新精比对、**26→26** 个粗链，九类字段都与 full 相同。不能拿旧面板“全删也不变”当作算法已前瞻省下。发现一条可泛化的重复请求：同一份来源在 A 已过线，又因为它在 B 有次要 assignment 而重查。修正只从“缺少染色体的请求”扣掉已选、双侧支持的**来源区间**；该 contig 的其他区间和独立的弱接头请求不扣。漂移或新材料须重新评估。`43023046` 依赖上述首轮完整成功，按源码清单 SHA `5897e39f71c8d8ba1b932ccfa6be7aa6ea9ae68da27de08e68ca16924ca3196f`，只看基础输入重算请求摘要，完全相同即沿用原冷测，不为验证补丁把全量 mapper 再跑一遍；仅不同的草案单独冷跑并与原 full 九项摘要核对。

### 11/23 13:39 — 只为有可能被补上的决策派发；有骨架与无骨架分开验收

- 首轮 `43023038` 和扣除已经支持子区间的 `43023046` 均 `SUCCEEDED`。在 2B/3B/1B，初版真实区域精比对 **14/36/59**，与全量相同；第二版在 3B/1B 确实扣掉了 79,980/2,743 bp，但仍没有减少整个调用。在这三组上“只是缩短已选片段的询问区间”不解决问题，未用回放窗口数冒充实跑。
- 从 admission 的实际来源检查发现：每条染色体先要有至少一个通过原参考筛选的种子定位。后续组装间配对只继承既有染色体位置；跨染色体尾部拆分仍保留其原参考种子，另一侧要有另一染色体的独立种子；输入 N 间隔的邻接也只继承已有位置。**assignment 标签本身不是参考定位。** 在固定来源、参考证据和既有 admission 策略下，若 B 缺少这样的种子，就不为“找到 B 骨架”发起补比对。与 A 的弱接头、弱定位有关的询问仍保留；若有参考种子但没有可信骨架则回退。若一个参考种子也没有，返回“没有可信路径”，不制造空的成功组装。该推论不适用于添加新参考、reads、来源数据或更换 admission 策略。
- `43023050` SUCCESS/0。在只看基础输入重新生成请求后，3B、1B 均选到一个两端过阈值的定位，额外 assignment 所指的 1、2 条染色体没有参考种子。算法实际跳过 planner/mapper：**3B 区域精比对 36→0、粗链 26→0；1B 区域精比对 59→0、粗链 54→0**。各有一条 Q0，FASTA、顺序与切点、参考缺口、来源占用、可用供体、未定位片段、候选定位、备选路径及歧义区间均与同面板实跑全量的逐项摘要一致。2B 从 14 次精比对和 11 次粗链变为 0，两边都没有 Q0，另作阴性报告，不混作正确构建。此验证允许实际执行零派发的决策，但若请求仍非空则只报告、绝不强制改为空。本次三组都确实判为空。旧 full 与改进后草案来自不同作业，不用它们宣称生产墙钟倍率。
- 上述三组是相对 3D/4B/5B 的新材料，但最后一步规则是在分析这三组的初版后形成，不能当作独立验收。将规则源码先冻结（`q0-multisource-threshold-20261123/freeze.sha256` 的 SHA `cc60f75a78e516b5ba310782449366abb926670c07381c0d2694bd404b27d413`），只按既有 assignment 选择两个与前六组无来源交集、两个组装各有至少两个单染色体且高支持的来源、起点间隔足够的材料：7A-734Mb 和 6A-16Mb。`43023053` 成功，面板库存 SHA `040ff1714ff59079411063b782c31d70fae409625b57c8595ae7ee8a6f753d54`。四核同节点 `43023055` 已于 13:38:38 RUNNING，锁定规则，仍先跑算法再跑全量，实际比较新 mapper 调用和下游字段。清单 SHA `33bb26ca1ecc871fb79c5f163eb1257acca12ecbae31c9bfda20cc67fc28e3d7`。原三组证据 `incident-tools/wheat-20261119/q0-threshold-three-holdouts-20261123.json`；不改正式默认、不重启整麦。定向回归 140 项通过。
- `43023055` 13:39:08 SUCCESS/0，两份原报告 SHA 已与作业日志核对。**独立 7A 样本**：草案有 3 个两侧参考/定位支持已过线的片段、2 个缺实际配对证明的接头；算法仍为这 2 个接头请求比对。原生比对 1→1，区域精比对 **10→4**、粗链 **10→4**；同节点独立空目录从草案/准备到读回选择耗时 full **13.735 s**、定向 **10.912 s**（不含共同输入读入、比较或下游发布）。两边均产出 1 条 Q0，9 类字段摘要一致。**当前发布守卫以“仍有未搜索的竞争范围”为由拒绝定向结果**；本次只验证草案，未通过科学成果发布验收，不能部署时把失败当成功。6A 没有可信参考种子，区域精比对 5→0、粗链 2→0，全量也不产出 Q0。两个样本不得合并当作两个阳性，也不得用 7A 一次试验推整麦耗时。详见 `incident-tools/wheat-20261119/q0-threshold-postrule-cold-20261123.json`。后续科学接口需区分“现有证据支持、已知冲突可留缺口但未穷举竞争”的草案语义与现行最终证据守卫，继续验证真正多接头案例及全麦范围，不原地替换现运行作业。

### 11/23 14:06 — 已支持的骨架可通过正式 Q0；尚未切换运行中的整麦

- 独立 `positive_threshold` 策略先从全部基础矩阵（包含 self）构建草案，再由定位和接头的具体缺证决定是否补查。使用现有准入与精确切点规则；已知竞争证据保留，不保证排尽未搜索的备选。正常写入 `metadata/grt_q0_evidence.json`，经 `build_q0` 重读及 `stage_selection` 生成路径和来源证据；全量与旧的修补模式仍按其自身的遗漏守卫验收。
- 同节点四核 `43023085` 成功，报告逐项 SHA 与日志一致。7A 从 10 次区域精比对降至 4 次，粗链 10→4，原生 1→1，一条 Q0；正式冷计时 full 11.62s、新策略 12.75s，调用减少但这组并未提速。3B 区域 36→0、粗链 26→0，一条 Q0，62.51→6.24s。3D 归档 full 有 113 个不同区域任务；独立冷测 `43023075` 新策略实际执行 53（另有粗链 19、原生 1），10 条 Q0。`43023085` 在 3D 只恢复上述终态可验证产物；53 个区域回执和 1 个原生回执命中，新启动数为 0，不是冷启动零计算。三组序列、路径顺序/连接、参考缺口、来源占用、可用供体、未定位部分、已知定位、备选与歧义九项均与各自的 full 摘要一致；没有 3D 同轮 full 耗时，不估其净提速。
- 独立统计及来源见 `incident-tools/wheat-20261119/q0-formal-threshold-20261123.json`。首个诊断 `43023074` 在装载输入前因诊断文件名错误退出，不视为科学结果。Server 回归 382 项（跳过 1），专项 31 项通过。14:05:23 `43017096` 仍按原策略处理到 19,000/61,000；旧 `42523432` 未动。策略属于科学配置，非资源覆盖；普通 resume 不允许改变，不能用该参数原地重提。切换前仍需量化整麦剩余工作、已提交回执在新策略下的可复用集合，以及切换时间/内存开销；不覆盖原 ready 或用旧成功标记冒充新策略。

### 11/23 14:27 — 跨旧缓存实测、整麦规划内存与分染色体限制

- 旧工作区的投影校验器 SHA 与 `6334b153` 不同；不能把当前 20,800 个已处理窗口直接记为新策略缓存命中。`43023106` 从已冻结的完整真实小麦运行记录取 8 个中/大输出窗口，把校验过的闭包复制到节点临时目录，按独立来源清单重建上下文身份（3,288 个不同成员）；不重新读取全部 DNA，不准重建 FASTA 或启动 mapper。8 个旧投影均被新校验器拒绝直接接收，但链决策和 exact raw 回执全部复用，重新生成并正式校验的投影 PAF 逐字节相同，**新 mapper 0 次**。该结论以窗口及完整目标集合仍被请求为前提，不是 61,000 全部可复用。
- `43023101` 及配对 `43023121` 在独立进程中，从整麦 2 份参考、44 份 self、22 份 cross 初始 PAF 每份取至多 1 MiB、比对相同字节片段；共 207,601 条完整记录。不加载整份基因组。原策略一次保留大量 Python CIGAR 元组；新表示逐行通过原解析器后紧凑保存，而不删任何已观察的命中、操作或可选标签，超宽长度不截断。配对任务中 self 保留对象的私有内存增量 **842.65→255.26 MiB**，参考 **32.21→12.58 MiB**，cross **244.70→71.97 MiB**。所有采样记录核对 CIGAR、完整标签、证据 ID 与原行 SHA；不宣称整麦峰值或时间。第一份目录 `43023100` 因系统默认 Python 不支持现有代码，在装载输入前退出，后续显式使用既有 x86 运行环境。
- `43023121` 同节点另做正式 Q0 冷对照（先定向再 full）：7A 区域调用 10→4、full 10.31s / 定向 11.92s；3B 36→0、50.93s / 6.07s。各生成一条 Q0，九项下游字段相同。未重复 3D 冷比对。`43023128` 只查原小麦 assignment 和已封存的**历史**残余窗口：31,186 个有归组来源中 10,999 个涉及多个染色体分组，22 组经共享来源全连通；仅凭染色体分别选路再相加不能证明全局一致。历史 61,087 个查询窗中 24,926 个没有归组标签，不能据此跳过它们的双侧窗口。没有运行全麦新策略、未停止或安装到作业中。14:27:16 新版 `43017096` 当前运行已处理 20,800/61,000，未有 Q0 ready；旧版照常。
- 证据及远端报告 SHA：`incident-tools/wheat-20261119/q0-threshold-cutover-evidence-20261123.json`。隔离 Q0 专项 364 项（跳过 1），事故专项 33 项通过；另外核对了完整桥接路径/证据及两种模块导入身份。全 Server 混合发现并非全绿：按相同环境与 `6334b153` 基线对照，4 个失败相同，14 个错误降至 11，未新增失败用例；剩余涉及既有旧命名空间缺项、冻结交接清单和测试混用两种模块导入。没有修改既有交接白名单或降低校验来令套件通过。

- 14:31，`43023190` SUCCESS/0。对整麦两份初始参考 PAF 逐字节核对已封存 SHA（共 1,745,286,139 字节，6,733,022 行），只取严格准入的必要条件：不在任何初始染色体分组、且无任何 identity ≥0.90、有效 MAPQ ≥20 的参考记录。这样的来源不能在**首次仅基础证据草案**里由自身请求定位或接头比对，但目标一侧仍可能要求整个窗口；不是排除后续补证/修补/回退。38,267 个完整来源中仅 255 个满足该条件；历史 61,087 个查询窗只排除自身轴 260 个。已冻结的 128 个真实完整上下文中，其中 5 个查询自身符合排除条件，**128 个的目标都含至少 8 个仍可能被请求的来源，按这个便宜判据可证明跳过的整窗为 0**。不等于实际阈值算法省 0：要判断大幅精简，仍须得到全局草案实际选中的弱端与接头，再做查询/目标双侧相交。未读 12.5 GB self、未读整套 DNA、未运行 mapper 或改工作区。14:30:52 新版 21,100/61,000；前约一小时 16,400→21,100，不能把此速率当新策略的速度或 Q0 完成 ETA。报告已追加到上述证据 JSON。

### 11/23 14:46–14:53 — 阈值草案独立运行；按用户要求退役最老对照

- 在 `agent-X86-21` 单独提交 `43023751`（14:41:30 开始，32 核、320 GiB）。不重启、不写入原主任务 `43017096`。代码取自 `665d2ec0`，控制目录 `jm19-compare-614589f-20261118/q0-latest-fork-20261123-1435/control/`；`snapshot.json` SHA-256 `2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d`。从原主任务同代日志确认 25 项通过检查点校验，将首轮草案用到的 104 个有内容哈希的文件（61,058,636,573 字节）复制到新节点本地 `/tmp`，不在共享 home 再存一整套，也不硬链接运行中输入。
- 这个作业用全麦实际参考/组装间/组装内比对，生成 `global-first-request.json`（阈值草案首轮需补证的来源区间）。它自身不运行新 mapper，不发布正式 Q0，不跑 Q1–Q4。衡量是否可以替代正式路线，应比较下游需要的定位、方向和连接等效果，而非要求复现所有假设竞争态；本次启动不是已通过验收，也不是已经获得整麦窗口节省比例。
- 用户明确最早的 `v2.0.20` 无需再运行。正常停止 **`42523432`**，调度器终态 `FAILED / Job was terminated by xbzhang26`，结束时间 `2026-11-23 14:46:19 +08:00`。保留终态、原 owner、日志尾部和输入来源；**不应续跑此基线**。`43017096` 与阈值草案 `43023751` 是另外两个作业，不在退役范围。
- 清理边界：`jm19-full-v2.0.20-20261117/gpm_server` 不能整目录删除。新版启动记录及两个参考检查点仍指向其中的两份组装、参考和既有参考结果。只处理 `grt/failed/`、`grt/cache/step23/` 的已核实独占中间文件；保留原始输入、参考比对、已有 Q 结果和复用凭据。审计与回执位于 `$HOME/cgat-reads-debug/logs/retire-42523432-20261123/`。`diskquota` 应在 ARM 登录入口查询个人配额；x86 的 `df` 不是个人余量。
- 14:53:40，`staged.json` 确认全部 104 个输入均已在 `agent-X86-21` 经 SHA-256 校验；草案进入整麦计算。原任务未重启。清理前个人配额：2,444,703,485,952 / 10,995,116,277,760 字节；退役审计 `43023768` 成功后才允许 `43023776` 执行清理。
- `43023768` 在原节点核对旧 owner 已不在、锁已释放、无同用户进程打开候选目录中的文件，且新版启动/检查点和 fork 清单都未引用候选路径。清单 SHA-256 `5401fafbb9ce07c543c83fdcc4b1c0abde28946dde0d07f608b2ffdc11349e60`：188,833 个普通文件，均为单链接，分配块合计 36,469,198,848 字节；其中失败目录 174 个，缓存 188,659 个。`43023776` 按清单逐项复核设备、inode、大小、时间、链接数再 unlink。核对实际完成以 `cleanup-receipt.json`、两个候选目录为空及 ARM 的 `quota-after.txt` 为准，不以计划量代替已释放量。

### 11/23 15:06 — 先冻结真实窗口，再按整麦首轮请求逐个计数

- 独立核对旧版清理：`43023776` 于 15:00:44 成功退出；两个指定目录均已空，188,833 个文件的分配块合计 **33.96 GiB**。两个组装、参考和两份参考 PAF 仍存在，未改新版主任务。`cleanup-receipt.json` SHA-256 `75a1ab33d310fcfe763cf84e121c12af89043545d6a02d612fc7d058ac9b7679`。ARM 清理后 `diskquota` 已用 2,436,520,247,296 / 10,995,116,277,760 字节，余约 7.78 TiB；账户级前后差值不是本次文件的分配块总量。
- 草案 `43023751` 已开始读取整麦首份参考 PAF，还没有首轮补证请求。为避免只统计查询端，或等草案出来后再挑窗口，`43024353 / agent-X86-04` 先冻结了原工作区下 **23,845 个**已命名窗口上下文目录（`listed.json` SHA-256 `3279c08db5c27934d8754144acdf4f10e166faef95649f5f0cc6b96682fd903d`）。这不是 61,000 个计划窗的随机样本；同一个查询可以有不同目标，一些目录在枚举时仍可能没有发出完整 spec。程序逐一绑定完整 context ID、成员序列哈希、双侧区间和原组装 FAI；只读取元数据，不启动 mapper，不写原工作区。
- 后继 `43024354` 已由调度器确认依赖 `43023751=SUCCEEDED && 43024353=SUCCEEDED`。使用真实 `global-first-request.json` 的参数契约、源码版本和快照 SHA，报告精确保留/可跳过的已观察上下文，分开仅查询、仅目标和两侧命中；对有多个目标集合的同一查询另报去重数。结果目录 `q0-fork-window-census-20261123-1505/census/`。该数是**首轮、已出现的上下文**，不是对整麦最终候选阶段、修补、回退或耗时的外推。无可信路径也不能报“成功零比对”。

### 11/23 15:17 — 正式接续前，验证原生结果跨工作区复用

- 独立 `43024411 / agent-X86-60 / SUCCEEDED`，从原生产绑定的 4 个完整原生矩阵中选最小的原档 `q0-map-b30137a13323db8a99874448`；在节点私有临时目录物理复制其 4 个输出（29,671,759 字节）及原始成功凭据，无源硬链接。使用与草案相同的 `665d2ec0`、实际 minimap2 身份和普通 `asm10` 参数，运行正式 `_supplement(cache_only=True)`，实际校验所有输出并从头到尾消费 12,774 条 PAF 记录，涉及 1,418 个查询分段和 52 个目标分段。没有启动 mapper，也没有修改现有作业。说明这个真实矩阵可跨工作区直接复用，并非其他矩阵或正式 Q0 已验收。
- 4 个原生矩阵成功凭据列出的输出合计 **92.26 GiB**。其中 3 个任务列的是同一组 32,088,868,779 字节的目标 FASTA，且 SHA 相同；如果后续确实需要全部 4 个，按内容只从共享存储读取一次，每种输出只需传一份，合计 **32.49 GiB**。差额 **59.77 GiB** 是潜在传输节省，不是本次回收的磁盘空间、减少的窗口或已获得的提速。不可把 `-m 2000` 弱种子当作全范围普通比对，不为复用而改写任务身份。报告 `incident-tools/wheat-20261119/q0-fork-native-check-20261123.json`，SHA-256 `b453dfd885dd6dd1a3e16adc2a7632863fc3e774203ba1f98a53d0fa394d45a1`。

### 11/23 15:27 — 全局草案读取 PAF：不丢行的解析提速候选

- 现行草案对 2 份参考、44 份组装内、22 份跨组装 PAF 各顺序读一次；在这一个作业内，不是把 68 份文件从头反复扫。现行逐行路径先构造完整 `PafAlignment` 和 CIGAR 元组，再转成 `RetainedHit` 并打包；证据 ID 每次还会重新对固定 artifact 名做 JSON 编码。普通正式准备的 `_initial_inputs` 为初始匹配覆盖另扫染色体 PAF，与草案持有命中的用途不同，不能只删调用；可考虑同一已校验的数据流向两类消费者输出。
- 独立只读 `43024445 / agent-X86-04 / SUCCEEDED`，固定与在跑草案相同的快照与运行库。每份取开头最多 512 KiB 中的完整行，按原文件名、真实行号、原顺序比较 **103,612** 行；参考 3,972、组装内 69,203、跨组装 30,437。候选在读行时直接生成现有紧凑对象；先验证名字表，每行仍匹配来源与长度；短 CIGAR 缓存有限，命中时仍逐行核对双侧跨度；证据 ID 只复用 JSON 固定前缀，原行 SHA、行号、方向、坐标、标签顺序、CIGAR 均保留。每条结果与原 `RetainedHit` 全字段相同。有界测试覆盖非 ASCII 路径、反向、非法/重复 CIGAR、超宽操作和缓存命中时的错误跨度。
- 同节点单核、相同已加载行、原/候选/候选/原计时：**6.282 / 4.192 / 4.190 / 6.225 秒**，中位耗时比 1.49，解析环节少约 33%。不包含文件 I/O、全量留存、选路、补充 mapper；不是全套草案或整麦 Q0 加速比。候选在 `incident-tools/wheat-20261119/`，没有改动在跑进程或生产解析器。下一步可先把候选与统一解析语义对齐，补独立保留验证（长行、坏输入与 gzip）及真实首轮请求一致性，再考虑替换。不要为了这段提速重启正在产出首轮需求的作业。

### 11/23 15:37 — 正式代码启用草案快速读取；六个真实面板逐区间一致

- 用户确认直接推进代码。`positive_threshold` 的首次选路现由 `q0_threshold_prepare.initial_questions` 直接读取保留型记录；仅有效行走一次快路径，异常行交回普通严格解析器定性，保留原诊断、长度/双侧跨度校验、顺序/标签、原行摘要和证据 ID。一个草案共享有界短 CIGAR 缓存，不在任务间共享。普通 full 读取、已完成的比对、最终独立守卫均未替换。旧版和正在运行的整麦运行包均未改动。
- 实际生产函数 A/B `43024546 / agent-X86-04 / SUCCEEDED`：68 份原数据的 103,612 条完整记录全字段一致；单核解析四轮为原 6.235、快 4.123、快 4.124、原 6.186 秒，解析中位数约 **1.51×**。同时核对了新 fork 草案的搬运计划：绑定同一个 104 文件快照，首轮搬运 **103 个、46,268,919,384 字节**；14,789,717,189 字节的参考 FASTA 保留在原处，身份写入 `deferred_for_formal_q0`，不是已在草案节点重新验过。正式 Q0 需要时再按哈希复制。未改现有 fork 的文件或回执。
- `43024535 / agent-X86-60 / SUCCEEDED`：同一冻结输入，两套独立 Python 解释器分别调用旧/新真实 `initial_questions`，不打补丁替代选路、也不运行 mapper。六个面板 (`1B/2B/3B/3D/6A/7A`) 的 `has_path` 和**完整有序的来源、区间清单**一致。3D 是 9 个来源 9 个区间，7A 是 3 个来源 4 个区间；1B、3B 有路径无请求；2B、6A 无路径，不算成功构建。局部 367 项 Q0 回归（366 通过、1 跳过）。证据见 `incident-tools/wheat-20261119/q0-fused-first-request-verified-20261123.json`。该准入不等价于整麦减少多少补比对，`43023751 → 43024354` 继续验证。

### 11/23 15:51 — 正式阈值准备：覆盖统计与首轮选路共用一次染色体 PAF 解析

- 从原生输入冷启动 `positive_threshold` 时，分区与检查点按原样验证。每条染色体命中只严格解析一次：先送入覆盖统计，按原顺序留给首轮选路。领取时校对文件代次、矩阵清单及查询/目标方向。已有 ready、旧版自定义读取器不预留整套矩阵，仍按原路径校验。没有取消内容哈希或最终独立验收，没有更改要求补证的阈值。
- 先试的按矩阵预检整个名字表虽然把解析次数减半，但在小麦实际输入上反而变慢（11.13 → 12.51 秒），没有采用。改为只检查遇到的名字，仍按当前分区逐条核对来源和长度。最终代码 `43024598 / agent-X86-60 / SUCCEEDED`：44 个组装内和 22 个跨组装 PAF，每份取开头最多 512 KiB 的完整行，共 99,640 条。原/新/新/原分别为 11.153 / 8.645 / 8.629 / 11.155 秒；这段的解析次数 132 → 66，中位耗时少 **22.6%**。覆盖区间和有序证据 ID 一致。计数不含内容哈希，也不含原本不重复的两个参考 PAF；不是整麦提速。
- 六个冻结的完整真实面板，原/新首轮路径状态、所需来源、具体区间及覆盖摘要均一致。真实准备入口的本地回归还对比了带非空跨组装证据的 ready、构建记录和 Q0 决策。372 个 Q0 测试，371 通过、1 跳过。诊断及结果：`incident-tools/wheat-20261119/verify_q0_shared_scan.py`、`incident-tools/wheat-20261119/q0-shared-matrix-scan-verified-20261123.json`。既有运行包未改；15:51 的整麦草案 `43023751` 已完成 54/68 个 PAF，首轮补证清单未出，`43024354` 等待其成功。这一优化消除的是重复读取，不是补充比对本身。

### 11/23 16:01 — 从本轮实际种子覆盖重建首阶段 61,000 个查询窗口

- 不把 23,845 个已有上下文外推成 61,000 个。独立作业 `43024697 / agent-X86-60 / SUCCEEDED` 从已冻结的 61,087 窗查询几何起步；将两个参考 PAF、22 个跨组装 PAF、第一份原生矩阵的来源摘要与草案快照/成功凭据逐项对齐。再按当前主任务日志列明的三个补充种子矩阵顺序无关地并入覆盖：分别严格读取 85,774、26,848、12,774 行，保留各自原参数和来源；只有正式规则承认的跨组装成对块才扣除残余覆盖。未重跑 mapper、未把 `-m 2000` 结果当作普通范围负证据。
- 用生产 `plan_query_windows` 重建 **61,000 个不同查询窗**，与主任务同代日志分母相同。冻结的 **23,845 个上下文全部**命中重建计划中 **23,845 个不同查询**，逐一核对了窗口 ID、来源、起止坐标；没有其他查询、重复的目标版本或边界冲突。另 **37,155** 个查询有已重建坐标，但不在这批冻结的目标清单中。这个验证不等于逐一读出了主进程私有的未来目标集合，更不等于还需启动 37,155 次比对。重建报告原件 SHA `9b7e12988d8fabe2fd360910d517a3e112e99da4b03578fe1ed9fdcff4d2a682`，归档于 `incident-tools/wheat-20261119/q0-partial-query-replay-20261123.json`。
- `43024709` 依赖 `43024354=SUCCEEDED`。真实首轮需求和已有上下文的双侧统计都封存后，它读取仅约 1.4 MiB 的冻结查询表，核对全部 61,000 个窗口 ID，然后分开报告已观察的两侧、未观察目标但查询已相交、未观察目标且仍需查目标的数量；不把后者报作可跳过。无路径、无补证请求、全范围回退分开处理。程序及定向测试：`replay_wheat_partial_queries.py`、`measure_replayed_wheat_demand.py`。当前只证明查询分母及其与已观测窗口的关系；整麦策略是否大幅减少补比对，仍等真实请求和后续正式阶段。

### 11/23 16:13 — 不重建整个目标列表也能核对双侧；68 份输入已读完

- 对 37,155 个尚无冻结目标表的查询，不能把“查询端不碰需求”当作“无需比对”。诊断实现了与现行区域规则等价的**目标侧相交判据**：在来源分段内将所需区间向两侧扩目标 padding，沿实际成对 CIGAR 块（含反向，不跨缺口，不纳入 X）投回参考。查询的参考范围仍由原 `ReferenceIndex.regions` 给出；相交时排除查询分段自身。每个参考区间前缀记录两个不同分段的最远终点，防止把自身当目标，也不会漏掉第二个真实目标。不改 Q0 阈值，不用这个判据绕过父查询回退或遗漏审计。
- 实机 `43024729 / agent-X86-60 / SUCCEEDED`：只在节点私有目录使用经 SHA 核对的索引和两份参考 PAF。在预先指定的 34 个真实上下文上，原规划器完整算出的目标列表与冻结列表逐坐标一致；选取 10 个真实来源作为**探针**而非全麦需求，目标侧 5 个命中、29 个不命中，新旧判定逐一相同。完整枚举目标 33.43 秒；反向索引构建 0.087 秒，34 次查询合计 0.0015 秒。两路仍需取得查询参考范围（此样本 1.16 秒）；这些时间不代表整麦速度或补比对降幅。回执 `incident-tools/wheat-20261119/q0-inverse-target-calibration-20261123.json`，SHA `c12172a1bc148ea6d873a92f0e3322f5114cb7b7779c18ce59b69fc6ede51d3f`。定向回归 15 项通过，包括反向 CIGAR、拆分分段边界和真实 spawn 读索引。
- 全麦条件核算 `43024732` 已确认依赖 `43024709=SUCCEEDED`；仅当真实首轮清单是局部区间时才读取私有索引，补查未观察目标、且查询端未相交的窗口；同时用真实需求在已冻结的原始目标上交叉检查。没有请求、有路径/无路径以及全范围回退分别记账，不做无用投影。结果目录 `q0-inverse-partial-20261123-1608/first.json`。这是**区域任务被分配和实际启动前**的双侧几何判据，后续原生覆盖、全父回退、候选及修补仍须单列。
- 16:03 `43023751` 完成 68/68 份 PAF，首轮需求尚未发出。16:12:27 至 16:13:03，在同节点用已验工具对本作业绑定到的 PID 做 4 次不暂停、不读 locals 的栈采样：4 次都在 `_reference_groups`，其中 3 次正在把重叠区间投回参考位置比较竞争命中，1 次正在筛锚点序列复杂度。不是继续读矩阵，也不足以从 4 个采样点估算剩余时间。原件 `observer-v2/selector.json`（`43024746 / SUCCEEDED`），SHA `25c4f22634c2581e129d492f8332bb45747b12a7e57edd03ded786af33d170de`。首次观测作业 `43024733` 因系统 Python 3.6 不支持 `capture_output` 在采样前退出；没有把它当主任务故障，也没有重启主任务。

### 11/23 16:23 — 参考锚点竞争判定的等价优化，未重启整麦草案

- `_reference_groups` 仍逐条保留原证据，只去掉为同一重叠区间重复投影的工作。成对块的映射由参考名、方向和固定坐标偏移确定。稀疏命中直接比较；对密集重叠，按身份阈值从高到低纳入符合原 `other.identity + margin >= current.identity` 的块，分别得到每条证据仍可独立支持的区间以及所有歧义坐标。先合并连续区间再做复杂度分块，保留原锚点、证据 ID、MAPQ 及顺序。新的实现文件纳入 selector 身份，不把旧成功凭据改签成新结果。
- `43024778 / agent-X86-04 / SUCCEEDED`：两份 SHA 核对的真实小麦参考 PAF，各取开头最多 1 MiB 完整行，在 18 个不同重叠密度的有界区块（7,287 个真实成对块）上逐条核对。四轮原/新/新/原的竞争判定为 2.151 / 0.066 / 0.065 / 2.225 秒。六个完整冻结面板同时对照原、新正式 `initial_questions`：170 个来源分段的参考锚点、证据 ID、高质量组和歧义坐标摘要一致，每个面板的路径状态与完整首轮需求一致。参考筛选合计 **7.11 → 3.39 秒**；同一组观测中整个面板草案合计 **38.27 → 34.50 秒**，3D 主要耗时不在这个环节。不能以局部 33 倍作为整麦加速比，也不是补比对数量降幅。
- 复现：以 `d270348f` 的 `server/tools` 为基线，将其原 `q0_admission.py` 复制为隔离运行包中的 `lgz_core/q0_admission_old.py`，仅替换新的 `q0_admission.py` 并添加 `q0_reference_competition.py`，执行 `incident-tools/wheat-20261119/verify_reference_competition.py` 的 natural 和 panel 对照。逐臂计时、输入/输出/代码哈希见 `q0-reference-mask-comparison-20261123.json`。补全隔离工作区的历史 fixture 后，375 个 Q0 回归项中 374 通过，1 跳过。16:23 在跑草案 `43023751` 仍为原冻结版本，尚无首轮清单；常规主任务 `43017096` 本轮日志为 29,400/61,000。

### 11/23 16:30 — 当前 master 从空目录运行正式 Q0，分别实数补比对和核对输出

- `43024855 / agent-X86-04 / SUCCEEDED`，正式实现为 `e7307a7c`。选了两个已知首轮行为不同的真实面板，不当作全麦抽样。每个面板的阈值和全量两臂均用独立空目录、同一已验 minimap2、4 核，没有恢复已完成的任务。冻结子集适配外层初始检查点读取及参考长度；沿用真实证据准备、ready 复验、`build_q0` 和路径/证据行生成。以下是已完成的补充 mapper 调用，不是计划窗数。
- 1B-689Mb：全量 **54 次粗链、59 次区域精比对**；阈值路线无需补证，二者均为 **0**。两臂均有一条 Q0。7A-734Mb：全量 **10 次粗链、10 次区域精比对、1 次原生比对**；阈值路线 **4、4、1**，没有把仍需进行的原生比对省略。两臂同样均有一条 Q0。
- 两个面板各自的 FASTA、来源与方向/接头、参考缺口、占用及可作供体的区间、未放置来源、已知定位、备选路径几何、已知歧义区间九项均逐字段一致。1B 全量/阈值耗时 107.98/5.13 秒，7A 为 11.76/10.90 秒；顺序固定、未计共同输入搬运，不按面板耗时或比例外推整麦。原回执 SHA、正式运行身份及九项字段摘要见 `incident-tools/wheat-20261119/q0-formal-master-1b-7a-20261123.json`。整麦在跑草案仍独立等待真实首轮请求。

### 11/23 16:40 — 正式 fork 不能把原事故调度检查点当成普通染色体检查点

- 为避免首轮需求出来后误重跑已完成的染色体比对，先核对冻结快照及其 25 个原始生产凭据。22 个染色体的凭据全部保留 `incident_self_execution`，其中 4 个还保留 `incident_execution_overrides`。它们列出的输入与输出共 4,851 个不同路径；与当前草案的 104 个路径取并集是 4,864 个。若按文件完整复制，较草案还需 4,760 个路径、按内容去重额外 **113.17 GiB**。这是完整复制方案的预算，不是额外比对，也不是所有可信复用方案的最低空间要求。
- `43024877 / agent-X86-04 / SUCCEEDED`：选实际内容最小的 `q0_chr:Un`，在独立的节点临时目录逐文件校验并物理复制 118 项（2.34 GiB），不链接原缓存。把原封不动的父检查点交给 `18c07c4b` 的标准 `OuterCheckpointManager`。标准输入字段全部相同、3 份 PAF 的独立几何及输出身份检查均匹配，但普通 reader **正确拒绝**，因为它不会生成原来的自比对执行身份。父检查点另有 2 个批次结果和 30 个原生资源回执，32 个均与冻结的原 reader 声明相符。未执行 mapper，未编辑/签发检查点，临时数据已由程序退出时回收。
- 结论：不能靠复制造成“新主任务已完成原生步骤”，也不因 stock reader 拒绝就重新比对。正式切换仍须使用保留原执行身份的只读父结果校验及显式导入；在通过之前保持原作业不变。仅一条染色体做了实物试验，其余 21 条仅查封存凭据。诊断 `check_wheat_fork_parent_closure.py`；原报表 `q0-parent-checkpoint-fork-closure-20261123.json`，SHA `f561fa7bb59885996042dfbd8504b7736e7e4e8019da0a42433729be76c26110`。这不影响首轮需求和精简数量的三项后继核算，也不是整麦数量结论。

### 11/23 17:55 — 跟踪分支修复自动选路；不改变在跑的整麦对照

- 同一份小麦快照（SHA-256 `2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d`），布局 1 原能识别 66 份基础矩阵，布局 2 却把比对文件读成 0 并走全量。原因是扫描了字面目录 `runs`，未使用布局解析。现在从参考索引和每条染色体的声明定位对应文件，只读文件大小，不遍历工作区，也不计临时/历史 PAF。正式 Q0 的内容验证不变。
- 元数据重放：校验 29 份真实元数据；另用相同大小的 68 个稀疏占位文件测试 `stat`，没有读取序列或执行 mapper。旧布局、新布局（逻辑路径和编号路径两种描述）均计得 **66 个矩阵、2 个参考比对，14,267,662,561 字节**，得到完全相同的自动选择 `decision_frontier_repair`。旧脚本未指定范围时仍为 `full`；新建工作区在此跟踪分支显式记录 `auto`。显式 `full` 与自动选择 `full` 也不再混用决策回执。
- 这验证的是目录识别与选路，不是补比对降幅。作业 `43023751` 仍使用冻结的显式 `positive_threshold`，不是上述自动模式；整麦首轮保留窗口和正式 mapper 次数分别以首轮清单核算和实际完成任务为准。没有改动远端工作区、重启作业或更新 `master`。

### 小麦 Q0 接续：不对派生 FASTA 额外做 SHA-256 对齐

原作业的输入、结果和检查点保留。后续不为与父工作区逐件比哈希而重建或扫描派生 FASTA；这不是首轮清单、补比对计数或正式接续的前置步骤。单组试验已结束，不扩到其余 43 组。

### 11/23 18:34 — 首轮用多核筛参考锚点：小面板不宜无条件开进程池

- `43027053` 在 `agent-X86-04` 的独立 8 核作业内测试。试验代码 `incident-tools/wheat-20261119/bench_q0_source_screen_pool.py`；Server 基线 `b1a9b6b5`。每个真实面板只加载一次，按 1、2、4、8、8、4、2、1 核测试同一份内存证据。多核时父进程计算一条来源，其余进程采用 `spawn`，只接收自己负责的来源序列、参考命中和片段，不复制整麦证据图；全局竞争与路径选择按原顺序执行。计时含建池、通信、选路和首轮问题，不含共同的输入读取/预热。直接比较完整准入结果、路径及备选、占用区间、请求和统计，6 个面板的 48 次结果均与各自串行结果一致。
- 每面板每档取两次平均再相加：**1 核 23.62 s，2 核 25.05 s，4 核 24.77 s，8 核 25.00 s**。1B 的确由 0.87 s 降到 0.53 s；6A 由 0.08 s 增到 0.31 s。3D 的串行总耗时 21.02 s，参考筛选只占约 2%，多核只加速这一步并不能显著缩短总耗时。进程树按 100 ms 采样，8 核单项最大额外 RSS 约 192 MiB，含共享页重复计入，不是整麦内存预算。
- 这只验证按来源拆分可以不改变判定；不能据此把 8 核作为默认，也不能推出整麦降幅。后续大任务决策需要独立测足够重且可并行的来源工作量、进程启动/序列传输成本，以及其余串行步骤。现有整麦作业、发布代码和生产默认均未修改。逐面板原始计时及附加 RSS 见 `incident-tools/wheat-20261119/q0-source-screen-cores-20261123.json`。

### 11/23 18:45 — 参考筛选占主导的工作负载可按来源并行

- 独立作业 43027061：两套小麦组装各按名称分位预选 16 条来源（合计 52.04 Mb），通过已有参考索引仅读取这些来源的 8,643 条命中。对同一内存输入正反顺序各测一遍；1、2、4、8 核平均为 **8.46、5.68、3.62、2.38 秒**。八次判定与请求完全一致。计时不含共同的输入读取。逐次数据见 `incident-tools/wheat-20261119/q0-indexed-screen-cores-20261123.json`。
- 8 核在这组参考筛选负载上约为串行的 3.55 倍；样本不含组装间比对及后续分配需求，并非整麦首轮清单的端到端加速。结合前一组小面板，只支持对工作量足够大的参考筛选有条件启用多核；未修改生产默认或在跑作业。

### 11/23 18:57 — 阈值首轮按工作量使用用户的线程预算；没有重启整麦

- 跟踪分支把 `positive_threshold` 首轮的运行线程数传到参考筛选。小批次、超大单条来源、未确认作业内存上限时不强开并行；有足够独立的大区间和内存余量时，单节点最多使用已测的 8 核（含主进程）。只传一条来源的局部工作，不复制全基因组证据；竞争命中仍按同一规则处理，按原片段顺序归并，再做全局路径选择。单包超限、子进程资源故障均回到主进程算原问题，不当成无证据。日志记录实际完成片段数，不由此估算后续补比对次数。
- `43027152 / agent-X86-04 / SUCCEEDED`：同一批 32 条真实小麦来源、8,643 条参考命中，直接调用接入后的选路函数而非原型替身。按 1/8/8/1 核执行；串行均值 **8.28 秒**，8 核均值 **2.44 秒（3.40 倍）**，每次多核有 28/32 个片段由子进程处理。完整准入、路径、占用和首轮需求相等。该批不含组装间连接，计时不含共同输入读取，不能据此外推整麦。远端原始报表 `incident-tools/wheat-20261119/q0-first-screen-runtime-20261123.json`。另用实际 CLI 验证传入 4 核的小型混合证据工作区保留 1 条计算通道；本地 400 项 Q0 回归中 399 通过、1 跳过，生成的 Server 运行时清单已同步并只读复核。
- `43023751` 仍使用原冻结实现，18:57 未产生 `global-first-request.json`；原全量对照 `43017096` 实际记录 40,700/61,000。此次没有修改两个作业、工作区或 `master`。仍待真实的首轮双侧窗口数及后续实际启动的补比对次数。

### 11/23 19:14 — 确需修补时，直接把本轮查出的区间交给下一轮

原阈值流程在验证一次选路时已经算出了完整补证需求，若验证要求修补，调用方却又对**同一份未变证据、同一条路径**重算一次。现在只传递这次验证得到的来源区间（`None` 仍明确表示全量回退），不复用跨轮判定。新增证据后仍独立选路、验证，不能提前发布。配对回归中，弱接头随后得到新证据的两轮从 3 次需求计算减至 2 次；全量回退分支在派发前从 2 次减至 1 次，派发区间与回退标记不变。402 项 Q0 测试中 401 通过、1 跳过，运行时清单已同步、复核。这不提速冻结草案的第一次选路，也不是整麦补比对降幅。

### 11/23 20:23 — 同一组 4D，只重提候选版

作业 `43029868`（`8b1482f9`，8 CPU、64 GiB）在 `agent-X86-52` 复用 `43028326` 已准备的 4D 输入；启动日志已记录 `REUSED_COMPLETE_4D_INPUT`。不重跑 mapper 或旧版对照。旧作业的 766/766 指参考筛选已完成，不是可移植的筛选结果；新进程须重新读取和选路。先按既有染色体/方向约束排除不可能的放置，再在相交锚区内计算原有投影；未放宽阈值或竞争证据规则。实际等价性及耗时以单组完成后的比对为准。

- `q0-4d-placement-resume.nzBAGt/`（与原 `gpm_server/` 同级）：`job_43029868.out` 记录各放置阶段、轮次、完成数和耗时；单项耗时过长时看 `placement-stacks.log` 的定时调用栈。`candidate.json` 是完整的候选摘要，`4d-first-request.json` 仅是本组请求，不能作为整麦清单。
- 轻量观察脚本将候选与原 `q0-4d-gate-whole-NDdyyY/old.json` 的完整科学摘要比较，结果写入 `comparison.json`；作业提交、运行或单侧成功均不是等价结论。冻结整麦 `43028666` 仍依赖原 `43028326`，不会自动切换到此提交。此轮没有启动其他测试。

### 11/23 20:33 — 第二轮片段定位的区间求交

`43029868` 的第一轮定位（509 段）历时 17 秒；第二轮在 `20:29:43` 和 `20:32:43` 两次主线程采样均落在 `q0_admission.py` 的直接参考锚逐对求交处。作业仍在计算，不是清单写入失败。`f34eb960` 只给该片段及该染色体/方向的直接参考覆盖建区间索引，不合并原始参考证据，不改变准入阈值。

4D 验证 `43029895` 位于 `q0-4d-indexed-support.cOzHej/`，依赖 `43029868=SUCCEEDED`；父作业的两个冻结对照不重跑，不更换整麦依赖。成功后先看 `predecessor-comparison.json`（对上一候选），再看 `comparison.json`（对冻结旧版），并核对 `4d-first-request.json`。仅有提交凭据、栈采样或单侧完成不能证明结果等价或加速。

### 11/23 20:41 — 4D 进程退出 139；不依赖失败的候选重提

`43029868` 第二轮完成 485/485（567 秒）；第三轮最近心跳为 34/444。20:38:38 进程发生 SIGSEGV，Donau `jobExitCode=139`，峰值 4,058 MiB（申请 65,536 MiB）、无 swap。没有完整候选文件。周期性栈转储恰在同一秒截断，不能据此确定是采样器、解释器还是计算路径造成崩溃。原日志和退出证据保留在原目录。`43029895` 无启动时间，Donau `exitCode=21004` 表示成功依赖不再可能，不是第二次科学计算崩溃。

替代作业 `43029926`（`q0-4d-fatalonly.tgV9Ax/`，仍是 `f34eb960`、同节点 8 核）已在 20:40:35 运行；日志已确认复用原 `43028326` 的 4D 硬链接输入、未启动 mapper。只从独立测试驱动移除周期性异步抓栈，保留应用阶段心跳，致命错误时写当前线程 `fatal-stack.log`。普通作业无权限读取此前的系统 core 日志，未改权限、内核或调度设置。不存在可恢复的轮次检查点，也不存在可供比较的 `43029868` 完整结果；不得补造。现以冻结 `43028326` 的完整 `old.json` 核对路径、序列、放置、证据和首轮需求，实际结论看 `comparison.json`，不能认作已通过。整麦依赖不变。

### 11/23 21:08 — 修复候选已实际生成 4D 草路径和首轮补证清单

Donau 作业 `43029926` 于 21:07:29 正常结束（退出码 0；总墙钟 26 分 54 秒），草路径与首轮需求计算用时 1,578 秒。四轮未放置片段的定位分别用时 16、337、362、360 秒，之后以 324 个已放置片段进入选路。已确认 4D 路径和重建序列均有摘要，诊断文件无致命错误。本次未复现此前的段错误，尚无证据断定根因。

只读核对 `q0-4d-fatalonly.tgV9Ax/4d-first-request.json`：181 个来源、300 个区间，来源坐标合计 657,484 bp；规范化内容摘要与 `candidate.json` 一致。原始清单文件 SHA-256 为 `1a51ebcfef103cb8c986ca7e98cb11eb7e86f6d68f9100d057fc3446e9698ec5`，候选收据为 `918685bd5c807fd863ddc066e65a0317a5fb9bf5c68cebe688285f8659230873`。这些是单组在**补充比对之前**产生的请求，不是 mapper 窗口数、全麦节省量或全麦清单。截至 21:08 冻结对照 `43028326` 仍运行、尚无 `old.json`；独立比较继续，未宣布新旧一致或切换整麦作业。

### 11/23 21:54 — 与上一个完整候选核对一致；冻结旧版仍待完成

`43028326` 中的 `af30a204` 已独立完成 `latest.json`（SHA-256 `656437c98ff4c68894f7d87313f8ee4a7297976964b939ec2d515ca3bc54f706`）。在同一组冻结 4D 输入上，它与 `43029926` 的 `f34eb960` 在草路径、重建序列、准入记录、放置、未放置片段、已占区间、歧义区间、是否有路径、首轮请求共九项上全部相同。两者均有 4D 路径且请求 181 个来源、300 个区间。相同口径的 `draft_s` 分别为 7,529.94 和 1,578.10 秒，约 4.77 倍，仅指该组草 Q0 至首轮请求，不是整麦耗时。另核对原始 300 个区间都在冻结的 4D 来源边界内，同一来源内互不重叠。`latest.json` 不是同作业的 `old.json`；截至本次采样，旧版 `665d2ec0` 尚未完成，不用前者替代最终独立核对。

### 11/23 22:39 — 整麦修复版启动，旧全量草案分支按授权退场

`43032833`（`q0-whole-repaired.ewp15v/`，`f34eb960`，`agent-X86-52`，32 CPU、320 GiB）22:18:21 启动，不依赖尚在运行的最早 4D 对照。启动凭据绑定已完整完成的 `af30a204` 与 `f34eb960` 的九项 4D 科学结果，并核对了新旧整麦输入声明除代码版本外完全相同。本次只计算整麦草 Q0 与首轮补证清单，不启动 mapper、不发布正式 Q0。新控制快照 SHA-256 `31748ea3db1906eddffea6a2096d99e454946f8fa4af9a24efb7b6982d4af02e`。25 个原生产单元的完成凭据已复用；103 个本阶段所需文件共 46,268,919,384 字节已校验并复制至独立节点暂存区，参考 FASTA 本体仍留待正式 Q0。22:38:27 已观测到首份参考比对 `DRAFT_PAF_START runs/JM19_hifiasm_vs_ref/result.paf`。

依用户确认的顺序，新提交受理后先撤等待的 `43028666`；确认新进程实际读取 PAF 后，依次终止原 fork 的下游 `43024732`、`43024709`、`43024354` 和原 fork `43023751`。22:39 已复查五个作业均为操作者终止（Donau 显示 `FAILED`，不是计算故障）。未删除输入、快照或比对结果。原独立 4D 对照 `43028326` 和整麦全窗口对照 `43017096` 均仍运行；后者 22:38 报 58,000/61,000，仅是窗口进度，不是整麦修复版进度。

### 11/24 — 达标即停：补证与多轮定位分开处理（跟踪分支，未部署）

- 草路径上的区间按原阈值判断；已达标不为竞争态另开比对。对仍为 `reference_unknown` 的连接，按实际左右放置分别检查，遇到第一条足以保留 gap 的证据就停止查看这个连接的后续命中。相同来源对上的另一处连接仍独立判断；所有待判连接都达标时停止扫描。未证明精确重叠的 gap 不闭合，也不把旁证或竞争记录删除。
- 草 Q0 进入选路前，多轮定位只把新增的锚点与仍未放置的片段比较；旧区间支持、证据和父节点累积使用，同一轮仍按原顺序统一判定。已放置的片段不再作为待验证对象，但可以帮助定位别的片段。日志分别给出每轮新增锚点、仍待放置、与新增锚点有联系的片段数，以及草路径达标/待补的计数。
- 仅作源码与差异检查；本修订没有新的 4D 或整麦测量。已有作业与冻结输入不变，不用上一修订的 4D 对照代替本次验收。

### 11/24 02:35 — 轮内候选并行已入分支；仅在本轮 4D 回执通过后提交新版全麦

- `612cbce9` 在增量定位上按候选分工；最多使用用户预算中的 8 路，子进程只接收有界片段数据，不能发给子进程的候选由主进程完整计算。每轮日志区分工作进程和主进程的片段数、实际新增关系、免于重算的旧关系、几何计算和复杂度筛选的累计任务秒数（不是墙钟提速）。没有改阈值；达标的连接仍不追竞争态。
- 冻结 `43028326` 已成功完成。`q0-4d-fatalonly.tgV9Ax/comparison.json` 对最早 `665d2ec0` 和上版 `f34eb960` 的九项科学结果给出 `equal`，同组草案耗时 24,151 和 1,578 秒；这不是本次新并行代码的验收。新 4D 作业 `43040585` 在 `agent-X86-52`（8 核，64 GiB）运行，父作业已结束，故从同一套冻结比对重新暂存 766 个成员，未重跑 mapper。已进入 selector。
- 全麦控制目录 `q0-whole-pair-lanes.xzqe7b`；登录节点观察器 PID `3740485`。它只在 `43040585` 调度成功、9 项和实际 300 个请求区间均与上版相同、确有候选交给工作进程且同口径耗时低于上版时，提交一次全麦草 Q0 / 首轮清单作业。32 核、320 GiB，指定 `agent-X86-05`，与现有 `43032833` 隔离；沿用全部冻结输入和 25 个原生产凭据。任一验收条件不满足则不提交；旧全麦若已产出清单也先停下复核。不要因没有 `whole.jobid` 重复提交：先查 `gate.log`、`submit.intent`、`submit.output` 和调度器。未授权取消现存运行中的比较作业。

### 11/24 02:45 — 新 4D 验收通过，全麦已在独立节点启动

- `43040585` 成功。`q0-4d-pair-lanes.Nf85nm/comparison.json`（SHA-256 `09799f9bf253d11c0577a1db526558772dee72d368a1bc3a33a1c42b7d1e7f13`）显示相对于上版 `f34eb960` 九项科学结果无差异，原始清单字节亦一致（181 个来源、300 个区间、657,484 bp）。从草 Q0 到首轮请求耗时 1,578.10 → 630.28 秒，约 2.50 倍；其中定位第二轮 337 → 78 秒，第三轮 362 → 35 秒。第一轮 260 个候选由工作进程完成；第二轮只有 12 个（其余 343 个由主进程完成），因此不能把提速都归因于并行。第二轮免于重算 8,343 个旧关系。该 4D 本次有 161 个放置达标、24 个偏弱；155 个未知连接仍需证据，没有因“保留 gap 所需证据已够”而提前结束的未知连接。保持审慎，不把这一组的时间外推整麦。
- 新全麦 `43040669` 于 02:44:16 在 `agent-X86-05` 启动，32 核 / 320 GiB。`control/started.json` 核实实际进程加载 `612cbce9`、`positive_threshold` 与新快照 `1d66bcfce3d1cf96cfcb10984540a300678b3e1fd683ba9a84581be64a98b74d`，当前为冻结输入暂存阶段。独立运行，不覆盖先前的全麦草案 `43032833`。该作业产物仅为整麦首轮补证清单，不是正式 Q0。
- 全窗口对照 `43017096` 在 60,900 条的整百日志之后，已经新建原生回退 `q0-map-bbb71092f55e5db234479331`：2 个查询、38,267 个目标，输入 FASTA 分别约 101 MB、32.1 GB。原生命令和索引日志已出现，02:36 未产生成功回执；不要凭区域进度末行判断仍欠 100 个窗口，也不要为此中止对照。

### 11/24 02:54 — 全麦草案输入已就绪，重接首轮窗口核算

- `43040669` 的 `control/staged.json` 确认在 `agent-X86-05` 核验并暂存全部 103 个草案输入（46,268,919,384 字节），从启动记录到暂存回执约 9 分 12 秒。已进入全局草 Q0 构建；参考 FASTA 本体只为正式 Q0 保留，尚无整麦请求。
- 原窗口核算链依赖已终止的旧 fork，新清单不会触发它。新提交 `43040673`（`q0-bound-first-demand.8xpsAJ`，条件 `43040669=SUCCEEDED` 已由调度器确认，等待时未分配计算节点）。核算脚本 `account_repaired_wheat_request.py`：用本次运行的代码绑定实际首轮清单；核对历史和当前快照仅代码版本不同后，在原规划器上复用经封存的 61,000 个查询、23,845 个双侧上下文。仅对查询侧未命中且无实际目标记录的窗口补查目标侧，另用已知上下文交叉核对。未启动 mapper、未重复提交草 Q0，未触碰对照。`result/first-demand.json` 是成功后才会产生的几何核算报告，不能当作新启动 mapper 数或 Q0 完成凭据。

### 11/24 03:09 — 全窗口对照的长尾是整段原生回退，不是剩余窗口数

对照作业 `43017096` 正在执行的原生任务 `q0-map-bbb71092f55e5db234479331` 已取到两条完整查询和 38,267 个目标（31,706,122,489 bp）。将其实际命令与封存的 61,000 个查询窗和来源表逐一核对，仅这两条查询所属的 **13 个**窗口对应本次原生全段：Flye 的 5 个窗合并覆盖整段 422,383 bp；Hifiasm `ptg000010l` 的 8 个窗合并仅 656,959 bp，而原生查询取整段 99,097,964 bp。这里按窗口坐标取并集，含窗口上下文，不是补证清单。规则是同一父查询有一个窗口无法在原预算内取得可靠目标，即整段回退；现有文件没有说明这两个来源各自具体触发哪个条件，不能把 13 个窗都说成失败或把长度倍数当成可节省耗时。03:09 未有本次原生成功回执。已留证 `incident-tools/wheat-20261119/q0-native-fallback-query-geometry-20261124.json`；今后比较全麦补证成本时将这两条的实际原生调用和区域窗口分列，不跳过目标侧证据，不修改或中断对照。新版 `43040669` 此时已读过两份参考，正在读取 1B 组已有比对。

### 11/24 12:20 — 第二轮重新筛整锚点已获现场证据；混合筛选全麦作业启动

- `43040669` 的 68 份 PAF 共 49,431,155 行，顺序和各文件计数与上一全麦相同。第二轮确实从 32,878 个未放置片段缩到 23,195 个有关候选，省去 463,993 个旧关系。但 12:13 的累计工作日志仍是几何 245.5 任务秒、复杂度 24,660.4 任务秒。独立同节点只读作业 `43048972` 在 12:16–12:18 对已绑定的所有者主线程作 12 次非暂停采样，12 次都在 `_candidate_delta → rooted_context → _clean_source_intervals`，不是读取输入或几何计算。`q0-live-complexity.Zn80Bp/selector.json` SHA `e9c14890db98e6b95e66581b6478ff7b320a8392e408d0e65e7c821712532595`。原旧诊断目录的 profiler 字节与历史约束不同，未执行或覆盖它；仅在隔离目录使用原 SHA 匹配的副本。样本不声称覆盖全部候选或整轮。
- 4D 同输入、同节点、同 8 核，直接对 `612cbce9` 的 630.28 秒：全按局部分块 `39135a9b`（`43042911`）635.07 秒、第二轮 96.1 秒，未采用。混合策略 `5f2e505c`（`43042918`）627.29 秒；第二轮 82.6 秒仍慢于 78.5 秒，第三轮约 22 秒而非 35 秒。两版各九项输出相同，300 个区间清单字节均相同；约 3 秒总差不是整麦提速证据。短/密集段保留有界整段筛选摘要，长且稀疏段仅筛实际配对块所触及的原网格，屏蔽区边缘重新起算、反向坐标和片段末端均按原规则。
- 已提交独立全麦 `43049105`（`q0-whole-hybrid.u1ylvM`），12:19:43 在 `agent-X86-14` 开始，32 核/320 GiB；`control/started.json` 确认新修订、阈值路线、原生产代次。快照 `1ac0f77f60dce3398fa10372f641baa19bc2dbb2ce80c31f28281258a9a5cfc5` 除修订外与前一全麦一致。未中断 `43040669` 或对照。下一判据：先核实同一轮 23,195 个候选和锚点数量，再比较跨过第 1,000 个候选的心跳时间区间；`612cbce9` 为 4,164–4,224 秒，不把 4D 比例当作全麦比例。`43040673` 仍只依赖 `43040669`；新核算脚本已登记两个独立快照，要以胜出作业的真实请求核算，不混用回执也不预报节省量。

### 11/24 — 把草 Q0 的线程预算用于读取已有 PAF（未实测，不切换运行中的作业）

- 现场 `43049105` 使用 `-t 32`，13:09 已读完 45/68 份 PAF；该版此阶段串行，Donau 最近 CPU 为 99%。此前的 4D 选路计时不能证明读取提速。
- 新准备器和首轮清单入口都把同一预算传给 PAF 解码。每次仍只打开一个输入，按原顺序读一次；大的 PAF 拆为有界行块，由独立进程解析，主进程按原始行号收回、核对双方名称与长度。不复制整麦 DNA，不写持久暂存，不并发争读 68 份文件。小文件、无可信内存额度或单核沿用串行。单个超大行及未成功交付的块用原解析器处理，不把异常当作无命中。
- 新日志 `DRAFT_PAF_TIME` 给出文件数、行数、逐文件及累计墙钟秒数（含调用方接收该文件的命中）；`LGZ q0 PAF decoded` 区分工作进程和主进程实际完成的行数。后续统一验收时，在相同冻结输入上分别核对记录身份与次序、首轮清单字节、读取总耗时及峰值内存，另计选路时间。开发时未运行测试，未部署、未重提；不能把候选进程数折算成加速倍数。
- 北京时间 13:22:22 复查：`43049105` 仍为 `5f2e505c`，68 份 PAF 已全部读完；草案进入 38,267 个片段的参考筛选，日志为 32 核预算、8 路。此进度不是新解析器的实测。

### 11/24 15:21 — 整麦定位第二轮前 2,000 个候选的实测对照

- `43049105`（`5f2e505c`，X86-14）与 `43040669`（`612cbce9`，X86-05）：冻结输入相同，68 份 PAF 的路径顺序与逐文件记录数相同，合计 49,431,155 行。两边均筛过 38,267 个片段；第一轮完成 21,983 个候选，新版 534 秒、上一版 628 秒。第二轮两边均新增 1,745 个锚点、需处理 23,195 个候选，都不重复计算 463,993 个旧关系。
- 从两个运行目录的 `whole_<jobid>.out` 读取第二轮 `placement anchor unplaced segments` 进度。跨过第 1,000 个时，新版的相邻记录是 790@99 秒、1,297@364 秒；上一版是 995@4,164 秒、1,005@4,224 秒。跨过第 2,000 个时分别为 1,889@424 秒、2,378@485 秒；1,989@8,065 秒、2,002@8,125 秒。未插值：即使取对新版最不利的两个时间端点，两个里程碑的实际墙钟耗时比分别大于 11 倍、16 倍。
- 15:21:21 最新记录为新版 3,227/23,195（605 秒），上一版 8,977/23,195（36,179 秒）。这是不同计算节点上的第二轮前段对照，不外推整轮，也不证明最终清单相同；新版没有使用 `b931305f` 的 PAF 解码器。此时新版仍未产出 `control/global-first-request.json`，未中断任何作业。

### 11/24 16:17 — 新版完成第二轮，已进入第三轮

- `43049105` 的 `whole_43049105.out` 明确记录第二轮 `finished completed=23195/23195 elapsed_s=3795`（1 小时 3 分 15 秒）。16:17:45 对读上一版 `43040669` 的同轮日志：已用 39,540 秒，仅到 9,736/23,195。因此就两次实际运行而言，第二轮耗时比的下界已经超过 10.4 倍；旧轮未结束，不能写成最终倍数，也不能当作整麦总提速。
- 第三轮新增锚点 2,584 个，剩余 30,355 个未放置片段中有 20,091 个与新锚点有关；942,523 个旧关系不再重算。16:17:45 最近一条完成数为 3,322/20,091（168 秒）。此时仍无首轮补证清单；旧的 `43040673` 继续绑定 `43040669`，不能当成新版清单的自动核算。

### 11/24 17:02 — 草 Q0 已进入逐染色体选路；1B 现场热点是候选覆盖计分

- `43049105` 的第 4/5/6 轮分别完成 13,513/4,517/406 个候选，用时 110/18/2 秒。随后扩展 8,985 个已定位锚点用时 415 秒，记录 29,526 个未定位片段用时 13 秒。16:42:58 的监控仍见锚点扩展，16:45:59 已见 `chromosome path 1/22: 1A`；当 1B 起始行仍是文件末行时，日志 mtime 为 16:53:17.817。据此 1A 经历约 7–11 分钟（采样界限，非精确计时），17:02:37 时 1B 已超过 9 分钟，未见首轮清单。
- 在同一节点用独立只读诊断 `43050915` 对绑定到该快照的主进程作非暂停采样：17:00:29 至 17:02:30，12/12 次均位于 `search_paths → evaluate → materialize → CoverageModel.assess`。其中 7 次在所选片段的覆盖/重复检查，1 次在汇总覆盖长度，4 次在遍历或合并未覆盖区间。`q0-live-path.HyUOMQ/selector.json` SHA-256 `4563f6a7d560af98f05ddd256f5c430f59447569af57368e076918c26e9a9e06`。这是 1B 某个时间段的栈分布，不是各函数的累计秒数，也不能按 22 条线性外推。
- 候选打分既计算覆盖与重复，又立即构建详细缺失区间，之后才判断是否丢弃重复候选。应优先研究保留完全相同的分数、重复判定和排序，延迟为胜出及需输出的备选路径构建缺失明细；未改变阈值、代码或运行中的主作业。

### 11/24 — 选路候选延迟生成缺失区间（跟踪分支，未切换作业）

- 针对 `43050915` 捕捉到的 `CoverageModel.assess` 热点，搜索中的候选只保留原有节点、连接、切片和评分。每个来源区间仍投影到原方向的等价单元，照旧检查范围和重复；对通过检查的路径，等长投影且无相交，切片长度之和就是被代表的唯一碱基数。拒绝与排名规则、访问顺序、评估上限均未改动。
- 胜出路径与最终返回的每条备选仍通过完整覆盖评估，复核分数与重复状态，生成所有来源的原坐标缺失区间。公共 `materialize` 与 `SearchResult.record()` 仍提供完整明细；并列时不把排在首位的备选冒充原胜出路径。计时只写日志：公共索引、每条染色体的建图/排名/明细分别记录；不把耗时写进科学结果。
- 本修订仅做静态差异及调用关系检查，无运行测试和提速实测。统一验收时应在相同冻结输入上对照胜出与备选的完整记录、各来源缺失区间、非入选原因及首轮补证清单，再比较同条染色体的耗时。`43049105` 继续使用原来的 `5f2e505c`，无需为本次改动重提。

### 11/24 18:40 — 3B 坐标边界传播触及上限，首轮清单未发布

- `43049105`（`5f2e505c`）走完前 7 个参考条目的选路，进入第 8/22 个 `3B`。18:36:58 在 `PathGraph.__init__ → CoverageModel.__init__` 抛出 `q0 coordinate-equivalence boundary limit exceeded`；18:40:55 调度器确认 `FAILED`，命令退出 1。终态日志 `q0-whole-hybrid.u1ylvM/whole_43049105.out` SHA-256 `74624ae03318afd31f90b1e6ba06fa4bfbc579408b5235a310533771ac1ab3c2`。这是显式算法保护，不是调度 OOM，也不是路径评分超时。
- 堆栈指向作业版本 `q0_coverage.py:86` 而非第 75 行：初始端点已通过检查，沿同源关系传播产生新的来源坐标时，去重计数从 200,000 升到 200,001。日志没有给出触发的关系/连通分量或最终所需边界数。`8faa5f78` 延后的是建图之后的候选缺失明细，并未修改这里的传播或限额；单换该版不构成修复。
- `control/global-first-request.json` 不存在。共享控制目录仅有启动、暂存、冻结快照和原生产回执。冻结快照仍绑定 25 个生产单元，可复用 2 份参考及 66 份矩阵 PAF，不需重跑初始比对；7 个已处理条目的草路径没有单独的可验证续跑回执。不能把失败解释为空补证清单，不能跳过 3B 或直接抬高/关闭保护再全麦重跑。
- 18:42 三个既有计算作业 `43040669`、`43032833`、`43017096` 仍 RUNNING，独立核算 `43040673` 仍只等 `43040669`。已转为只读跟踪这些作业；未测试、重提、取消或修改现场运行时。下一步应隔离 3B 的关系传播，区分多个独立分量合计超限与单个分量内部扩张，再决定保留精确坐标映射与资源上限的处置方式。

### 11/24 — 3B 建图：精确合并重复坐标映射（跟踪分支，未部署）

- 普通路径保留所有原始端点，但相同来源、方向和两端坐标的映射只传播、合并一次。不再为每个“原始证据 × 覆盖小段”保留一条临时记录；若发现歧义，按原始证据与歧义小段的实际交集找回证据 ID。不会因压缩而把相邻的其他证据一并剔除。
- 仅在原分段超过原有 200,000 个边界上限后，才尝试合并来源对、方向和坐标变换均相同，且相接或重叠的连续映射。哪怕只隔一个碱基也不跨过；不同方向或偏移不合并。必需区间端点始终保留。只有起始切点确实减少才再传播，至多一次，仍用同一上限。若必要映射本身太复杂，明确失败，不跳过该组、不出空清单。
- 日志分别给出边界分段和覆盖单元构建的墙钟耗时。越限时报告起始切点、当前切点、最大来源连通组占多少、触发坐标及其所在组的切点数；这里按**来源序列**分组，不能推论组内所有坐标彼此相连，也不能从越限瞬间反推最终切点总数。
- 仅静态审阅，未运行测试、未改远端运行时或作业。统一验收时应对照旧版可完成输入的完整输出；对正反向相接、断开、不同偏移及部分歧义的关系核对原始证据 ID、覆盖长度和缺失坐标；最后再用整条 3B 的实际关系核对是否能在原上限内完成，不能拿局部面板代替。没有整麦提速或 3B 已修复的结论。

### 11/24 — 按“同一决策达标即停”审视首轮清单（仅跟踪分支）

- `initial_questions → select_request_paths → questions`：首轮要的是获选片段、连接和实际薄弱区间，而非备选的缺失明细或落选理由。保留同一候选搜索、评分、并列处理、精确连接与跨染色体占用检查；获选后直接交给清单决策。全局参考筛选后没有任何种子则不再建配对索引；单组没有可用起点则不建该组的图。两者都不把“没有路径”当作 Q0 成功。
- 找到一个实际的竞争态重复环节：初始放置已被参考锚定时，原实现仍查其他染色体尾部，并会在已有链足以证明主段连续后继续收集见证。草案现在按原拆分条件先判断：主锚点范围两端都容不下最小独立尾部，就不查；只要任一端仍有足够空间就按原规则评估。一条合格链同时支持主段和备选尾部就停止查找更多连续性见证，此处仅作保留原放置的决策。未知接头的任何一侧没有锚点时，不再为不可能成立的两侧见证扫描比对；它仍会请求补证。
- 针对 3B 的第一次建图，草案在传播**之前**按同一来源对、方向和偏移合并相接或重叠的映射；不跨越正长度缺口，同一决策不再先耗尽 20 万上限再试一次。若精确合并后仍超限就报告错误，不发布空清单。正式选路、验收与输出仍走完整路线，验收器拒绝首轮轻量对象；不承诺复用不同代码身份的清单。
- 只做源码、消费路径及差异审阅。未运行测试，未部署或提交作业。统一验收应核对同一冻结输入的获选片段/方向/切点、原 gap、歧义证据 ID 和完整有序首轮清单，含无种子、刚好容得下最小尾部、未知接头和正反向片段；另以整条 3B 的实际映射数、切点数、耗时及有无清单判断收益。

### 11/24 21:29 — 新版全麦重提准备完毕，尚无同版 4D 放行回执

- Donau `43049105` 仍为 `FAILED`。已查调度和三个草案控制目录，未发现已产生的全麦首轮清单或正在运行 `f9ed324f` 的草案。21:29，`43040669`、`43032833` 均在定位第 2 轮（14,295/23,195；23,873/32,878），`43017096` 运行中，`43040673` 等待。未停止、修改或再提交这些作业。
- 已在 `jm19-compare-614589f-20261118/q0-request-ready.f9ed324f` 新建隔离控制目录。运行修订 `f9ed324f3984efc41eb780159f8294b5f4db2545`，Git 归档 `latest.tgz` SHA-256 `e6456b2f31aba63d60149e33e21790ea4aa178d6f948acdc1dcef04c7b976aef`；只读绑定旧快照，核对除 revision 之外所有字段相等，新快照 `451a42a602e5359a3783e1fc139620ba3a1b47d74bfe55b46e1d8c94e66e9512`。25 个原生产回执和两份声明逐份核对。只暂存程序和小型元数据，目录实占 4.4 MiB，未复制整套输入、启动 mapper 或发布正式 Q0。
- 旧全麦 `verify.py` 绑定 `5f2e505c` 的 4D 对照与运行包，不能用于新版放行。旧 4D `group.arm` 只捕获 `select_q0_paths`，新版首轮不会调用它；直接重提原脚本不能获得正确比较。新增 `incident-tools/wheat-20261119/capture_request_only_4d.py`，同字节暂存到 `qualification/candidate.py`。它观察真实首轮入口，计时结束后才独立生成完整记录，比较获选片段/方向/接头/评分、实际请求，并交由原比较器核对历史九项结果。未执行候选或比较器。`qualification/inputs.sha256` 为 `5e4dea497d50798b9f25b9bf3085b3b07a70ca6ab758f474a39d7e56cdc77c67`；保留 766 个成员的冻结取数规则、原基准和 300 个请求区间，不复跑比对。
- `prepared.json` 表示已暂存，**不是准入成功或已提交**。依当前不运行测试的要求，未单独重跑 4D，也没有用旧回执代签或排一个依赖永远无法满足的全麦作业。若获准执行这一轮 4D，再检查 x86 节点空位和该修订是否已有作业/回执；先核实结果、运行身份和同口径计时达到既有条件后，才向独立节点提交一次 32 核/320 GiB 全麦首轮清单作业，不触动正式工作区。

### 11/24 21:35 — 用户准许运行一次新版 4D，达标后自动提交一份全麦

- 4D 作业 `43054355`，21:35:23 在 `agent-X86-52` 启动，独立目录 `q0-request-ready.f9ed324f/qualification`。Donau 运行态资源回执已发布，8 核/64 GiB；日志已确认从冻结输入重暂存 766 个成员和三份组内矩阵，未启动 mapper，真实的 `select_request_paths` 已进入选择器。既有旧全麦仍用各自进程和工作区。
- 同级 `gate_f9ed_wheat_resubmit.py watch` 已在登录节点启动（见 `gate.pid` 和 `gate.log`），不会再提交 4D。它要求本次作业在正确目录和节点成功、同修订、九项科学结果相同、原始请求字节摘要一致（181 个来源、300 个区间），且真实草案耗时严格低于同机冻结基准 `612cbce9` 的 630.2768 秒。缺证或任一不符不提交。满足后选择有 32 核/320 GiB 可用且独立的 x86 节点，先写一次性提交意向，再提交一次新版全麦首轮清单。全麦自身也要复核这份准入回执，不接管原生产目录。
- 窗口核算器已登记新快照：直接与最初 `2c8bd6a2…` 的冻结快照逐字段比对，唯一差异是修订；另在新目录 `accounting/` 留存对应脚本。仍须先取得真实 `control/global-first-request.json`、匹配修订和阈值合同才可核算；本次没有触发核算作业，也没有重接 `43040673` 的依赖。

### 11/24 21:56 — 清理旧作业副本；新版 4D 达标，全麦尚未获调度器接收

- `43049105` 已失败，`agent-X86-14` 上的私有暂存不含独立的染色体检查点。维护作业 `43054639 / SUCCEEDED` 将暂存清单与原生产输入、父凭据、暂存时间和文件身份核对，确认没有进程占用、没有未知产物后，删除 131 个节点文件，释放已分配文件块 46,272,180,224 字节（43.09 GiB）。未删除共享的失败日志、快照、代码包或生产输入。这 **不是共享配额回收量**。
- 共享盘：历史 `42675569`、`42677292` 均已成功，两次试验的同染色体 `target.mmi` 确实逐字节相同。`43054665 / SUCCEEDED` 仅删除长窗试验重复的 1A、3D 索引及一次性预检的两个占位文件；保留短窗试验两份索引、两套 PAF、结果、日志及复现脚本。共删除 4 个文件，已分配文件块 2,220,175,360 字节（2.07 GiB）。两次清理回执分别在 `~/cgat-reads-debug/logs/retire-43049105-20261124/cleanup-receipt.json` 及其 `shared/shared-receipt.json`，后者逐项列出保留位置与摘要。21:54 的 `diskquota` 读数约 2.41 / 10 TiB；不能用瞬时账户读数之差代替删除回执。
- `43023751` 此前已人为终止；旧暂存记录在 `agent-X86-21`，当时复制的输入为 61,058,636,573 字节。只提交一份绑定该节点、该清单和该作业的 1 核清理任务 `43054667`。21:56 仍为 `PENDING`，**不计入已释放空间**。后续查 `~/cgat-reads-debug/logs/retire-43023751-20261124/cleanup-receipt.json`；若暂存已不存在，按零回收记，不重复启动。
- 新版 `43054355 / SUCCEEDED`：4D 九项结果及 181 个来源、300 个区间的原始请求一致；同机同口径草案 `630.28 → 556.76 秒`（减少 11.7%，不是全麦提速）。21:54 自动门控尝试向 `x86` 指定 `agent-X86-63`，Donau 明确拒绝创建作业：该节点不属于队列的资源组。按任务名查询无匹配，没有 `whole.jobid`，也没有新版全麦在排队。保留原 `whole-submit.intent`、`whole-submit.output` 和 `gate.log`，未绕过意向锁重提；如后续重提，应从 `dqueue -l x86` 的 `nodeList`（`X86`）及 `dnode -rp X86` 的交集中选节点，而非全局空闲节点，不重跑 4D。旧版对照 `43017096`、草案 `43032833`、`43040669` 及其依赖 `43040673` 均未取消。

### 11/24 21:58 — 修正节点池，复用 4D，单份新版全麦实际启动

- `x86` 队列的 `nodeList` 是 `X86`。选节点改为读取该队列状态并从 `dnode -rp X86` 内筛满足 32 核/320 GiB 的独立节点，不再从全局 `dnode` 表挑选。拒单恢复仅接受已封存的“该节点不在队列”回执；先复核 4D、任务名及清单、已有运行/提交记录，再在原锁下写独立的 `retry-x86-pool/` 意向和提交结果。21:54 的拒单证据保持原样，没有重跑 4D 或初始比对。
- 新版全麦首轮清单作业 **`43054692`** 于 21:58:58 在 `agent-X86-64` 启动。Donau `RUNNING` 分配回执为 32 CPU / 327680 MiB，`whole-allocation.log` 已确认发布。21:59:27 `control/started.json` 确认实际加载 `f9ed324f`、`positive_threshold`、32 线程、冻结快照 `451a42a6…`，在其独立节点暂存目录运行。此时正在暂存输入，尚无 `control/staged.json` 或 `control/global-first-request.json`；不能将 4D 的 300 个区间冒称为整麦结果。后续核查暂存完成、68 份初始 PAF 的读取以及 3B 是否越过旧失败点。不要因 `gate.log` 仍保留上次的报错而重提；本次以 `retry-x86-pool/gate.log`、`whole.jobid` 及实际 Donau 状态为准。

### 11/24 22:08 — 新版全麦已完成输入暂存；窗口核算只做准备

- `43054692` 的 `control/staged.json` 记录 22:08:39，103 个冻结文件、46,268,919,384 字节，距真实启动回执 552.16 秒。`VERIFIED_DRAFT_INPUTS` 已输出；已转入草 Q0，尚未产生整麦首轮清单。已复用 2 份参考与 66 份组内 PAF（44 份自比对、22 份组装间比对），这里是暂存完成，不代表 68 份都已被选择器解码。
- 原窗口核算作业 `43040673` 仍只依赖 `43040669`，不能代算 `43054692`。为新版在其 `accounting/` 准备 `account_f9ed_whole_request.dsub`（SHA `0d0b9937b31936dd586294c4f8f1f457848c43d5da2164644ad221361c5f2dcf`），**未提交、未执行**。待 `43054692=SUCCEEDED` 且真实 `control/global-first-request.json` 存在后才提交一次；无需重跑 4D、原规划或 mapper。该脚本使用本次修订解释阈值合同，复用冻结的旧规划器及其辅助脚本，输出为 `accounting/result/first-demand.json`。该报告只回答原先 61,000 个规划窗口有多少与本轮需求相交，不是实际比对数或正式 Q0。

### 11/24 22:27 — 首份 PAF 前的静默来自准备区间；读数按同一冻结文件核对

- `43054692` 在 22:08:39 已暂存完成，22:20:56 尚未记录首份 `DRAFT_PAF_START`，22:21:55 已开始解码。这约 12–13 分钟包含加载两套组装 FASTA、原序列拆分与构建输入索引，现有日志不能进一步拆分耗时；不是重跑比对。两份参考 PAF 实际耗时 48.93、76.37 秒，第一份 2,627,833 行均由解码工作进程处理。截至 22:27，15/68 份已完成，逐份记录条数与同输入旧日志一致，共 13,872,511 / 49,431,155 行（28.1%）；这是读文件进度，不是草 Q0 总进度。
- 后续版本仅补日志：fork 记录组装 FASTA 加载的起止，`initial_questions` 独立记录源序列索引耗时，并在序列边界每隔至少 60 秒报告已处理条数。条数包含按既有规则跳过的无效序列，不表示全部获采纳。没有新增遍历、重读或比对；没有运行测试，也没有热改或为日志重启本次作业。

### 11/24 22:40 — 全麦 68 份旧比对读取完毕，进入草案候选定位

- `43054692` 读完 14,267,662,561 字节的 68 份 PAF。与同输入 `43049105` 的 `DRAFT_PAF_COMPLETE` 逐文件核对，文件名和记录数全部相同，合计 **49,431,155 条**；总数一致不代替最终路径或请求比对。当前日志从首字节至最后一条 `DRAFT_PAF_TIME`（含换行）共 24,939 字节，SHA `1dd21128a3e76b1a8e38934c25c89b45849a5fb7b00bede0853e2686445b537f`。
- 逐文件读取及调用方接收记录的累计墙钟 **1,120.16 秒（18 分 40 秒）**。按类别：2 份参考 125.30 秒；44 份自比对约 991.96 秒；22 份跨组装约 2.92 秒（分项由逐文件两位小数累加）。45 份实际使用 2–7 个工作进程、解码 49,356,628 条；23 份未启用进程池、74,527 条。此数不含此前暂存、FASTA 加载和索引，也不等于全流程用时。22:40 已进入候选定位：42,698,133 条组内关系，38,267 个源片段，`cpu_budget=32 lanes=8`。仍无整麦首轮清单；未重提、未中止对照。

### 11/24 — 参考筛选：整段对整段不再重复裁剪、投影（候选，未在当前作业部署）

- `43054692` 已进入 38,267 个片段的参考筛选。对冻结来源表的 38,267 个 ID，按原 `dataset/contig/0/length/sequence_sha256` 逐项复核；每条源序列恰对应一个完整片段，长度与两份冻结 FAI 一一相同。因此，为同一来源的多个片段再建一次索引在这份输入上没有收益。按当前整条序列传递的尺寸门槛，只有 2,239 条处于 750,000 bp 至 8 MiB；902 条更长的来源占 22,473,346,385 / 31,706,122,489 bp。该比例不是 CPU 时间占比，也不是增加并发的内存安全依据。
- 以前同阶段的栈采样定位过参考坐标投影。现在参考块若已完整落在源片段内，复用原不可变区间，不再构造同坐标的交集；完整等长块在正、反向都映射到原目标区间，直接复用它。部分覆盖仍按原方向投影，越界和非等长证据仍拒绝，未跳过竞争掩码、阈值判断或证据 ID。只做源码与冻结元数据审阅，未运行测试、未部署、未重提；不能由此宣称量化提速。
