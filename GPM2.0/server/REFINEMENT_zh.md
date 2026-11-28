# LGZ 后精修与编号工作区

[English](REFINEMENT.md) | **中文** · [Server 手册](README_zh.md)

本指南对应当前源码实现，不会追溯改变已发布的 v2.0.21 压缩包。此前在原生 Linux x86_64 和 ARM64 上，用同一套环境和合成数据实跑了四个固定版本工具。那次验证不包含本次目录调整和空间回收；具体范围及证据见仓库中的 `GPM2.0/docs/server-refinement-final-acceptance-20261122.md`。请使用同一版源码构建的安装器与 App；不要覆盖正在使用的安装目录，也不要在作业运行时更新环境。

## 1. 环境与首次运行

四工具全部使用同一个 **cgat-server** 环境，不另建 DEGAP、quarTeT 或 LR 环境。在对应源码或 Server 包中执行：

```bash
SERVER=/path/to/GPM2.0/server
bash "$SERVER/install.sh"
# 按安装器末尾提示激活 cgat-server。
bash "$SERVER/install.sh" --check
```

安装会改变依赖，`--check` 只做检查。更新环境前停止受影响的作业。安装器核对固定源码/分发包的 hash 和已声明的兼容补丁；普通分析运行不下载工具。上游 shell 驱动有限制，工作区和环境路径不要包含空格或 shell 特殊字符。

```bash
# LGZ 完成后直接运行默认工具 DEGAP。
bash "$SERVER/run.sh" --ref /data/reference.fa --ds /data/assembly.fa \
  --out /work/cgat_server --threads 32 \
  --hifi /reads/hifi_1.fq.gz /reads/hifi_2.fq.gz --ont /reads/ont.fq.gz

# 不提供 typed reads：只运行 LGZ，基线明确标为未精修。
bash "$SERVER/run.sh" --ref /data/reference.fa --ds /data/assembly.fa \
  --out /work/lgz_only --threads 32
```

`--hifi`、`--ont` 各自可以接多个文件，也能重复提供。直接提供原始 reads，不会因此开启 LGZ 前的旧 Meryl/Merqury/CRAQ QC 流程。工具需要的 FASTA 转换按内容绑定，不校正、裁剪或过滤 reads。同一文件不能重复提供，也不能同时标为两种技术。工具本身仍可按其固定配方处理数据，例如 TGS-GapCloser 的 ONT Racon 轮次。

## 2. 在已完成 LGZ 后追加或选择工具

已经完成的**编号布局** LGZ-only 工作区可以原地追加：

```bash
bash /work/lgz_only/run_all.sh --hifi /reads/hifi.fq.gz --ont /reads/ont.fq.gz
# 也可以从已安装 Server 指定同一个输出根目录。
bash "$SERVER/run.sh" --out /work/lgz_only --hifi /reads/hifi.fq.gz
```

通过校验的 LGZ/参考比对结果会复用，改变下游 reads/工具不会重新 prepare。两个入口都保存 typed reads 与工具选择。两种 reads 参数都省略时，沿用已保存的 reads；**只要提供任意一种 reads 参数，就整体替换已保存的选择**：`--hifi new.fq.gz` 也会清空此前的 ONT 组。需要保留两组时，本次同时提供两种参数。各文件顺序会保留。

```bash
# 每种工具均从同一 LGZ 结果出发，按下表固定顺序独立运行。
bash /work/lgz_only/run_all.sh --gapfill-tools degap,tgsgapcloser,quartet,lrgapcloser
# 也可以只选一部分，不要求包含 DEGAP。
bash /work/lgz_only/run_all.sh --gapfill-tools quartet,lrgapcloser
# 仅本次关闭精修，保留已保存的设置和历史结果。
bash /work/lgz_only/run_all.sh --gapfill-tools none
```

工具名使用上面的小写标识，以逗号分隔且不重复；`none` 只能单独使用。没有可用 typed reads 却选择工具会报错。省略工具参数时沿用保存的选择；新的有 reads 任务默认 `degap`。仅准备而不执行的 `prepare.sh --gapfill-tools none` 则初始化为关闭精修。**不提供 `--final-tool` 参数**：每个成功工具各保留一份独立 FASTA，App 则将所有工具结果读入同一项目。

| 顺序 / 参数标识 | 同时提供两种技术时 | 固定源码/分发版本 |
| --- | --- | --- |
| `01_degap` / `degap` | 一次原生混合输入运行 | DEGAP 2.0，revision `ec26a174c0bbb84f2a48affa6e4f50ad14adf465` |
| `02_tgsgapcloser` / `tgsgapcloser` | 仅用 HiFi；没有 HiFi 时使用 ONT | TGS-GapCloser `1.2.1`，分发变体 `1.2.1_ml`、build 4；revision `52818b3e464209477baec506ade3240be43b4fa8` |
| `03_quartet` / `quartet` | 一次 GapFiller 运行消费两组输入 | quarTeT `1.3.1`，revision `a44d8c87e3f4bcefaf43dc4134e88b6a21890265` |
| `04_lrgapcloser` / `lrgapcloser` | 仅用 HiFi；没有 HiFi 时使用 ONT | LR_Gapcloser `1.0`、build `pl5321hdfd78af_0`；revision `156381adec01a5c664edbf5df1d866b5c70e82a1` |

仅提供一种技术时，各所选工具使用该组数据。TGS/LR 不会悄悄各跑一遍 HiFi、ONT；报告记录提供、实际消费和未使用的输入。[`contracts/refinement-tools.lock.json`](contracts/refinement-tools.lock.json) 才是各平台包 hash、依赖 build、固定参数和公开 wrapper 补丁的权威清单，仅有版本号不算固定完整版本。环境定义覆盖 `linux-64`、`linux-aarch64`，不表示两种架构都已真实跑通。工具串行运行，共享已保存的线程预算，不为四工具分别同时申请整份预算。

CGAT 锁定了 DEGAP 版本，并显式传入与上游 GapFiller 默认一致的参数：开启 k-mer 过滤、每个缺口左右合计最多 10 次延伸尝试，以及 500,000 bp 的累计延伸预算（最后一次完整尝试可超出该上限）。除已列出的覆盖项外，其他工具均沿用各自锁定的上游默认设置。高级用户可直接编辑已安装 Server 中的 `tools/gapfill.toml`，工作区副本会自动同步，无需新增 CLI 选项，详细说明见配置文件注释。

四个工具的线程预算和输入输出由 CGAT 指定。TGS HiFi 额外使用 `--ne` 与 `-x asm20`；LR 使用 `-n 1`（上游为 `-n 5`）；quarTeT 使用 `--noplot`。

## 3. 最终结果究竟在哪

`--out` 是包含交付包的整个工作区根目录：

```text
cgat_server/                         # 当前项目级交付布局
  01_inputs/  02_alignments/  03_lgz/
  04_refinement/
    automatic/<工具>/                # 输入、原生尝试和接纳证据
    manual/<批次完整摘要>/03_report/  # 批次 summary.json、report.html
  05_final/
    cgat_server.lgz.fa               # 可直接使用的未精修基线
    cgat_server.<工具>.fa            # 各工具独立发布的基因组
    cgat_server.manual-<批次前16位>.fa # 有完整快照的手动批次全基因组
    results.tsv                      # 本次尝试、接纳数、当前可用 FASTA
    details/                         # 详细路径、来源及批次选择清单
  06_report/report.html              # 总览与报告、比较入口
  07_delivery/
    cgat_server.full.tar.gz          # 全项目唯一一对，不按工具重复打包
    cgat_server.light.tar.gz
    cgat_server.auto.patch.zip       # 有自动结果时才发布的累计补丁
    manual/cgat_server.manual-<批次前16位>.patch.zip
  .lib/                              # 工作区运行库
  .runtime/                          # 状态、checkpoint 与发布回执，不可整删
```

FASTA 前缀取创建时的输出目录名。补跑失败不会替换上次成功的基因组；从 `results.tsv` 可查到现有 FASTA 对应哪次发布。若工具没有接纳补丁，清单标明零接纳。已有编号工作区继续使用 `05_final/00_lgz/` 和 `05_final/<工具编号>/`，不搬迁、不改名。

补跑自动精修时，有新发布结果才更新同一对 Full/Light 和累计自动补丁。手动批次只追加自己的交付补丁和 FASTA，不更新项目包。`--archive-format zip` 将 Full/Light 的后缀改为 `.zip`，补丁始终为 ZIP。旧作业按其创建时的布局读取，不会自动移动数据。

仅存在工具目录不能证明本次成功，应以当前总览和内容绑定的 committed 发布回执为准。新尝试失败会留存诊断，不删除旧的成功发布，也不把旧发布标成新结果。一个工具失败不妨碍其他成功工具或 LGZ 基线交付，但本次流程总退出码非零。

最终组装由已接纳、可追溯来源的改动重建，不直接复制原生整条染色体，也不把 LGZ FASTA 改名冒充精修。接纳的联合缺口修复、负链和重叠连接保留来源关系；歧义或越界候选不接纳并记录原因。可能出现零接纳，必须与原生失败区分。结构/来源检查**不等于生物学正确性验证**。未变来源坐标上的证据会保留。新接纳的 patch 来源现会对原准备参考独立比对，并使用冻结库执行 tel/cen 扫描，不重跑 LGZ 或补洞工具。测量保存在 `04_accepted/<run>/01_source_evidence/<generation>/`，报告及两类 App 包携带同一证据；`no_hit`（测量无命中）、`disabled`（未启用）、`no_rules`（无规则）和 `no_chr_library`（无该染色体库）分开记录。包内 `metadata/refinement/source_intervals.tsv`、`final_annotations.tsv` 按真实切片、反向及截断关系映射到新坐标。这是来源扫描和坐标映射，不冒充完整终版基因组重扫描或准确性验证。

所有补洞工具均按原始 LGZ 缺口判定：只有完全闭合才采纳。部分填补仍可在诊断中查看，但最终 FASTA 和 Final Path 保留该处的原序列。如果一个修改横跨多个缺口，又没有证据能把它拆开，只有所涉缺口全部闭合才会一并采纳。

缺口闭合和已有侧翼的变化分开判定。唯一的缺口边界锚能区分两者时，CGAT 可以接纳补丁，
同时保留缺乏独立证据的 LGZ 原侧翼，缺口详情会列出保留区间及原生长度差。边界不确定时不猜切点，
保留原生证据但不接纳不可分离的候选。与参考不同本身不是拒收理由。

新版 DEGAP 对每个原生缺口尝试运行一个双向任务。CGAT 校验已封存的 `family-result.json`，用原始侧翼核对候选，且只接纳有证据的接点区间，而不是整段候选。未补上的任务保留原因，不当成执行异常或 App 候选。升级时用新版 Server 的 `install.sh` 刷新同一个受管环境的工具锁，不必单建 DEGAP 环境；旧运行保留为历史，不当作新版任务复用。

## 4. 报告、App 导入与恢复

先打开 `06_report/report.html` 看流程总览。`01_lgz/` 是 LGZ 基线报告，`02_refinement/` 按固定编号分工具，`03_comparison/` 保留每批的 TSV/JSON。从总览进入工具或缺口详情，可查看实际使用的 reads、原生任务是运行还是复用、CGAT 接纳了哪些改动、最终结果是否发布。失败会列出已记录的失败阶段和原因，并链接诊断；零接纳则表示保留 LGZ 序列，并不等于失败。复制整个 `06_report/` 可保留 LGZ、当前已发布的精修报告及比较表之间的链接；也可解压 App 包后打开 `report/report.html`。未发布或失败的尝试详情可能在 `04_refinement/`，最终结果和交付包则位于同级的 `05_final/`、`07_delivery/`；如需保留这些链接，请连同工作区布局一起复制。

在工具报告中进入 **原生 job 报告与日志 → 离线原生可视化**（`native_visualization/index.html`）。新版 DEGAP 的 `Global.report.html` 总览和各双向任务的 `family-report.html` 有独立的离线浏览副本；原始 HTML 作为带哈希的静态文本附件保留。离线副本保留上游内嵌 JS/SVG，与 CGAT 接纳页面隔离，不依赖 CDN；原生页中指向工作目录的文件链接改由 CGAT 诊断区提供。旧 LEFT/RIGHT 历史报告使用其对应的可移植规则。来源绑定会明确显示：`observed_diagnostic` 是「报告时观察」，**不是原生完成回执证明**。缺失、未知依赖或过大的详情有明确状态，不提供悬空链接；总览内嵌 gap 数据也会与可用的原生 gap 诊断核对。

TGS-GapCloser、quarTeT GapFiller、LR_Gapcloser 的固定入口不生成原生 HTML，保留它们实际的日志、填补明细、AGP 等诊断，不伪造上游可视化。Full 与 Light 携带相同报告文件。已用 Windows 浏览器离线检查批次导航、原生图形，以及 Full/Light 报告解压后的相对链接。报告可正常浏览不代表生物学准确性。

新建项目时导入项目 Full 或 Light，全工具结果一起进入，不选版本。向已有匹配项目追加自动结果，在项目页「精修」右上角导入累计自动补丁。卡片区分各工具结果与项目实际采用；每个 Gap 先看是否完整闭合，多个合格闭合再按 DEGAP → LR_Gapcloser → TGS-GapCloser → quarTeT 采用一个。只读查看不改变导出路径；已有人工决定或边界冲突不覆盖。Light 不附带完整序列，不能替代 Full 的离线 FASTA 导出。

手动 App `DEGAP-JOBS` 是独立入口。当前源码收集器将人工候选目录分版本保存在 `04_refinement/automatic/degap/06_manual/01_catalog/`，以 `.runtime/manual_degap/current.json` 为准，不修改原 LGZ 表。匹配源码构建的 App 已解析实际 Server 运行库，并按内容绑定原始/精修/人工候选种子来源；Full/Light 交付均携带 `metadata/server_sources.json` 身份。受控导出 → Server → 原 App 导入检查保留了手动编辑的 Final Path。已提交迁移清单绑定的旧人工包现可纳入不可变 registry，不重跑原生任务或其比对。未知旧结果 ZIP 仍保护：保留原 ZIP，复制未改动的原 `jobs.tsv` 和 `degap_jobs/` receipt 到新的空目录收集，不重新导出 token。不能把这些协议检查等同于手动全链路验收。

### 项目级手动精修（`refine.py`，当前源码）

除旧版脚本包入口（App 中明确标为「旧版 DEGAP-JOBS（脚本包）」）外，当前源码源码在配套桌面端 App 与 Server 工作区之间新增项目级 **精修任务** 流程：

1. **在 App 登记并导出任务。** 在装配页勾选 Gap；每个 Gap 默认 DEGAP，也可以加选多个工具。左右端粒用 DEGAP TelSeeker，并指定 motif。「参数设置」可调整工具参数或覆盖项目 reads。从装配页可导出当前染色体的任务；在项目页顶部选「导出 → 精修任务」，可按染色体预览后导出全项目已选位点。任务包保存所选工具及参数；新项目包还保存整套工作路径快照。只有通过校验且完全闭合的候选参与同一 Gap 的择优，优先级为 DEGAP → LR_Gapcloser → TGS-GapCloser → quarTeT。部分填补不计作闭合。
2. **Server 运行：** 在匹配工作区执行 `python .lib/tools/refine.py refinement_tasks.zip`，需要覆盖 reads 时可重复使用 `--hifi` / `--ont`。详见第 3 节的批次报告、直接 FASTA 和补丁路径。整基因组从导出时的项目快照重建，保留其他染色体上的编辑；旧任务缺少快照时只交付局部补丁。
3. **报告边界与隐私：** 可分享 HTML 报告不公开服务器私有 reads 路径（仅保留测序类型与 SHA-256 摘要），明确区分「等待导回 App」（`pending_app_import`）与「无可导回补丁」（`no_patch`）；无 App 回执前绝不标记为已导回。
4. **导回原项目：** 在项目页「精修」卡片右上角导入本批 `.patch.zip`。App 按包内清单识别手动或自动补丁，先保存待提交编辑，核对原项目、批次和位点，不新建工具项目。已采用片段在 Final Path 中保留工具与批次来源；各工具详情只读，可定位或撤销已采用的位点，不提供换工具入口。

新版 App 为捆绑的双向 DEGAP 单独使用 `shared_prepare.family-v1/`，按哈希记录原始 reads 和转换程序，不接用旧的未校验 FASTA/索引缓存。若旧导出脚本指向旧缓存，请保留旧结果；需要重跑时，用新版 App 重新导出并选择新的 job 输出目录。已有候选包仍按原规则收集或导入。

停止或失败后重复同一入口命令；完整且通过校验的结果会复用。已封存完成的原生运行，在接纳、报告或发布失败后可以重新接纳，不重跑工具。只有报告或打包器变化时刷新报告和包，未变化的最终序列文件不替换。

原生内部恢复边界：

- **DEGAP：**由新版原生调度器恢复已封存的终止双向任务，校验缺口定义、输入、结果清单及其明细。预处理与缺口检测重新执行，不接续未完成的延伸轮次。
- **quarTeT：**恢复通过校验的逐输入 PAF，包括明确的空比对结果；后续输入仍进入原生处理。
- **TGS：**按原生分块/轮次复用已完成的 minimap2/Racon 命令输出。scaffold/候选准备与整合仍执行，不恢复原生 done 标记。
- **LR：**同时恢复完整迭代处理 FASTA **和** `info_filter2` 证据。预处理和首个索引重新执行，仍由原缺口检测判断是否提前结束；仅有一个 FASTA 或后台子进程失败，不能算完成。

每次重试使用新原生目录，在 `02_jobs/<run>/native_units/`、`native_substeps.json` 记录原生产者和本次恢复，不是直接接着运行任意旧目录。保留的部分文件不能直接作为完成回执。不要通过删除 checkpoint 或移除锁强制复用。

```bash
# 只读查看，不取消正在运行的分析。
tail -F /work/cgat_server/.runtime/logs/progress.log
python3 "$SERVER/tools/view_run_log.py" --server-dir /work/cgat_server --detailed --follow
# 旧作业停止后，用 run.sh 调整预算，不给 run_all.sh 新增资源参数。
bash "$SERVER/run.sh" --out /work/cgat_server --threads 64
```

## 5. 旧工作区的显式续跑与迁移

未标记的旧布局必须先显式迁移再追加；不要覆盖运行 `prepare.sh`，也不要用 symlink 假装已经编号。物理迁移要求原 LGZ 基线**已经完成且可验证**。未完成任务先走下方独立的原引擎续跑入口，只接纳经过内容审核的历史引擎；完成后再单独审批迁移，不直接换新引擎重算。

先备份工作区，确认各节点均无活动或**排队**任务可能写入。使用**新版已安装 Server** 的入口，不使用旧工作区内嵌运行库：

```bash
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server --preview
# 检查 approval_sha256、目录移动、命令替换和运行库增补。
# APPROVAL 必须填入你刚核对的 preview 所打印的完整 approval_sha256。
APPROVAL=replace_with_reviewed_approval_sha256
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server \
  --apply --approve "$APPROVAL" --confirm-idle
bash /work/old_server/run_all.sh --hifi /reads/hifi.fq.gz --ont /reads/ont.fq.gz
```

Preview 只读；`--confirm-idle` 记录你已经完成的调度器/所有节点检查，不替你执行检查。文件清单变化会使批准摘要失效。迁移保留原科学证明，并冻结已完成 LGZ 的原引擎边界，不制造新版引擎 checkpoint。迁移后修改 LGZ 科学参数需新建工作区；reads/工具设置仍可调整。

迁移中断会阻止普通入口运行。使用同一源码版本恢复已记录事务，以下操作**二选一**：

```bash
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server --resume --confirm-idle
# 或：仅回滚仍归事务所有且未变化的迁移产物。
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server --rollback --confirm-idle
```

不会覆盖被修改的用户数据，也不会抢占未知/活跃 owner 的锁。遇到拒绝时保留 journal/备份并排查，不删除工作区 metadata。已在 x86_64 验证受支持的历史工作区续跑、迁移中断恢复和精修追加；ARM64 实跑验收针对当前固定工具，不覆盖未经核验的旧引擎。

### 原 LGZ 尚未完成

先保留原物理布局和已安装引擎继续原流程。目前审核清单覆盖编号目录改造前的
`f2ceafb0` 源码；按整套已安装运行库的实际内容匹配，**不只看版本号**。
未知或已修改的引擎会拒绝处理，不自动升级。保存的启动目录和生成脚本中的根路径也必须
仍指向本工作区；搬移后指向其他目录的旧脚本会拒绝执行，不静默改写或到另一项目写入。

```bash
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server \
  --preview-lgz-continuation
# 审阅原引擎、科学步骤前缀、有效 checkpoint 和审批摘要；确认所有节点无活动/排队写入任务。
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server \
  --continue-lgz --approve <continuation_approval_sha256> --confirm-idle
# 成功后返回新的「已完成工作区迁移」预览及独立审批摘要。
python3 -B "$SERVER/tools/migrate_workspace.py" --server-dir /work/old_server \
  --apply --approve <new_migration_approval_sha256> --confirm-idle
```

仅运行原计划到证据汇总的前缀，不运行旧 DEGAP/打包尾部；续跑期间不替换持久化计划、
科学脚本、原运行库或环境。已完成外层步骤使用原校验器复核；已有 q0/供体/q 阶段的
缓存不匹配时，在失效和重算之前停止，不伪造缓存命中。每次审批、缓存事件和状态保存在
`.run_all/legacy_continuation/`。失败后先看原日志，重试前重新预览，不删除 checkpoint
或绕过缓存保护。目前是受控脚本边界检查，真实原生 LGZ 和调度器终止仍待统一验收。

### 回收已发布工具的原生临时文件（可选）

在新项目工作区根目录执行。第一条只列清单，不删除、不重跑。检查 `files` 中每一项及影响后，沿用相同的工具范围，传入输出的完整 `plan_sha256`：

```bash
python -B .lib/tools/compact_refinement.py --tool lrgapcloser
read -r -p '粘贴审阅过的 plan_sha256：' plan_sha256
python -B .lib/tools/compact_refinement.py --tool lrgapcloser --apply "$plan_sha256"
```

省略 `--tool` 检查所有工具。`unlink` 只针对原生成功时登记、现在仍可重建且无引用的 reads 副本、分片或索引；手动重放原生流程可能要重新预处理。`share` 只让支持的文件系统共享两个已核对文件的相同数据块，保留两条路径及写时复制语义；不支持时跳过，不改用硬链接或强删。清单为空也是正常结果。逻辑大小、文件占块和共享范围并不等于磁盘实际释放量。

若操作被中断，按提示运行 `python -B .lib/tools/compact_refinement.py --recover "$plan_sha256"`：提交前恢复暂存文件，提交后只清掉已获授权的暂存副本。操作回执在 `.runtime/refinement/compaction/`。不要手动删除 `.runtime`、失败现场或 `04_accepted/`。旧布局不支持这个入口；没有登记清单的原生尝试不允许按文件名补猜删除。
