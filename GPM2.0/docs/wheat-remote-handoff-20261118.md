# 小麦远端对照任务：恢复入口（2026-11-18）

先读 `remote-server-targeted-repair.md`。本页是 **2026-11-18 20:19（Asia/Shanghai）核实的快照**，不是实时状态，也不是自动部署脚本。不得不核实就照抄旧 job ID 取消/重提任务。

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
