# LGZ 后精修与编号工作区

[English](REFINEMENT.md) | **中文** · [Server 手册](README_zh.md)

本指南对应功能分支中的源码实现，不会追溯改变已发布的 v2.0.21 压缩包。已在原生 Linux x86_64 和 ARM64 上验证统一环境，并用合成数据实跑四个固定版本工具；具体范围及证据见仓库中的 `GPM2.0/docs/server-refinement-final-acceptance-20261122.md`。请使用同一版源码构建的安装器与 App；不要覆盖正在使用的安装目录，也不要在作业运行时更新环境。

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

工具名使用上面的小写标识，以逗号分隔且不重复；`none` 只能单独使用。没有可用 typed reads 却选择工具会报错。省略工具参数时沿用保存的选择；新的有 reads 任务默认 `degap`。仅准备而不执行的 `prepare.sh --gapfill-tools none` 则初始化为关闭精修。**不提供 `--final-tool` 参数**：每个成功工具都有独立最终结果和 App 项目，不暗中选择“获胜”结果。

| 顺序 / 参数标识 | 同时提供两种技术时 | 固定源码/分发版本 |
| --- | --- | --- |
| `01_degap` / `degap` | 一次原生混合输入运行 | DEGAP 2.0，revision `ff4d753511fc8556d77b9a578e064e69fe47ade9` |
| `02_tgsgapcloser` / `tgsgapcloser` | 仅用 HiFi；没有 HiFi 时使用 ONT | TGS-GapCloser `1.2.1`，分发变体 `1.2.1_ml`、build 4；revision `52818b3e464209477baec506ade3240be43b4fa8` |
| `03_quartet` / `quartet` | 一次 GapFiller 运行消费两组输入 | quarTeT `1.3.1`，revision `a44d8c87e3f4bcefaf43dc4134e88b6a21890265` |
| `04_lrgapcloser` / `lrgapcloser` | 仅用 HiFi；没有 HiFi 时使用 ONT | LR_Gapcloser `1.0`、build `pl5321hdfd78af_0`；revision `156381adec01a5c664edbf5df1d866b5c70e82a1` |

仅提供一种技术时，各所选工具使用该组数据。TGS/LR 不会悄悄各跑一遍 HiFi、ONT；报告记录提供、实际消费和未使用的输入。[`contracts/refinement-tools.lock.json`](contracts/refinement-tools.lock.json) 才是各平台包 hash、依赖 build、固定参数和公开 wrapper 补丁的权威清单，仅有版本号不算固定完整版本。环境定义覆盖 `linux-64`、`linux-aarch64`，不表示两种架构都已真实跑通。工具串行运行，共享已保存的线程预算，不为四工具分别同时申请整份预算。

CGAT 锁定了 DEGAP 版本，并显式传入与上游 GapFiller 默认一致的参数：开启 k-mer 过滤、每个缺口左右合计最多 10 次延伸尝试，以及 500,000 bp 的累计延伸预算（最后一次完整尝试可超出该上限）。除已列出的覆盖项外，其他工具均沿用各自锁定的上游默认设置。高级用户可直接编辑已安装 Server 中的 `tools/gapfill.toml`，工作区副本会自动同步，无需新增 CLI 选项，详细说明见配置文件注释。

四个工具的线程预算和输入输出由 CGAT 指定。TGS HiFi 额外使用 `--ne` 与 `-x asm20`；LR 使用 `-n 1`（上游为 `-n 5`）；quarTeT 使用 `--noplot`。

## 3. 最终结果究竟在哪

`--out` 是包含交付包的整个工作区根目录：

```text
cgat_server/
  run_all.sh
  01_inputs/                         参考、组装及派生输入
  02_alignments/                     原始比对
  03_lgz/                            原始 LGZ 各阶段、证据和注释
  04_refinement/
    01_degap/                        其他工具使用上表固定目录
      01_inputs/<run>/
      02_jobs/<run>/                 命令、状态和原生完成回执
      03_native/<run>/               原生输出留存，不是最终结果
      04_accepted/<run>/             被接纳的 patch 来源序列
        01_source_evidence/<generation>/  参考比对及注释测量证据
      05_report/<run>/<site>/        可搬移的尝试报告
  05_final/
    cgat_server.lgz.fa                可直接使用的 LGZ 基线
    cgat_server.degap.fa              可直接使用的已发布自动精修结果
    results.tsv                       区分本次尝试和当前可用发布
    details/
      00_lgz/                          LGZ 基线：refinement_applied=false
      01_degap/                        已校验并发布的精修结果
        assembly.fa
        final_path.json
        sources.tsv
        remaining_gaps.tsv
        provenance.json
  06_report/
    report.html                      从这里进入总览和本次比较
    01_lgz/report.html               原始 LGZ 过程
    02_refinement/01_degap/report.html
    03_comparison/<batch>/
  07_delivery/
    00_lgz/cgat_server[.light].tar.gz
    01_degap/cgat_server.degap[.light].tar.gz
  08_refinement_jobs/
    02_manual/
      <batch_sha256>/                项目级手动精修批次、结果包与 report.html
  .lib/                              工作区内嵌运行库副本（包含 .lib/tools/refine.py）
  .runtime/                          锁、checkpoint、metadata、日志和历史
    refinement/<tool-dir>/<run>/final/  按来源重建的私有待发布结果
```

FASTA 前缀取创建时的输出目录名。补跑失败不会替换上次成功的基因组；从 `results.tsv` 可查到现有 FASTA 对应哪次发布。若工具没有接纳补丁，清单标明零接纳。已有编号工作区继续使用 `05_final/00_lgz/` 和 `05_final/<工具编号>/`，不搬迁、不改名。

方括号表示两个实际文件，不是文件名的一部分；`--archive-format zip` 使用 `.zip`。每种工具在 `04_refinement`、`05_final/details`、`06_report/02_refinement`、`07_delivery` 下的目录编号固定，不因只选择一个工具而改号。编号工作区不再保留根目录 `data/`、`grt/`、`report/`、`logs/` 影子树。App 包内部仍使用协议约定的 `data/`、`metadata/` 等路径，不要手动改包内目录。

仅存在工具目录不能证明本次成功，应以当前总览和内容绑定的 committed 发布回执为准。新尝试失败会留存诊断，不删除旧的成功发布，也不把旧发布标成新结果。一个工具失败不妨碍其他成功工具或 LGZ 基线交付，但本次流程总退出码非零。

最终组装由已接纳、可追溯来源的改动重建，不直接复制原生整条染色体，也不把 LGZ FASTA 改名冒充精修。合法的部分修复、联合缺口、负链和重叠连接保留来源关系；歧义或越界候选不接纳并记录原因。可能出现零接纳，必须与原生失败区分。结构/来源检查**不等于生物学正确性验证**。未变来源坐标上的证据会保留。新接纳的 patch 来源现会对原准备参考独立比对，并使用冻结库执行 tel/cen 扫描，不重跑 LGZ 或补洞工具。测量保存在 `04_accepted/<run>/01_source_evidence/<generation>/`，报告及两类 App 包携带同一证据；`no_hit`（测量无命中）、`disabled`（未启用）、`no_rules`（无规则）和 `no_chr_library`（无该染色体库）分开记录。包内 `metadata/refinement/source_intervals.tsv`、`final_annotations.tsv` 按真实切片、反向及截断关系映射到新坐标。这是来源扫描和坐标映射，不冒充完整终版基因组重扫描或准确性验证。

LR_Gapcloser 按原始 LGZ 缺口判定：只有完全闭合才采纳。部分填补仍可在诊断中查看，但最终 FASTA 和 Final Path 保留该处的原序列。如果一个修改横跨多个缺口，又没有证据能把它拆开，只有所涉缺口全部闭合才会一并采纳。

缺口闭合和已有侧翼的变化分开判定。唯一的缺口边界锚能区分两者时，CGAT 可以接纳补丁，
同时保留缺乏独立证据的 LGZ 原侧翼，缺口详情会列出保留区间及原生长度差。边界不确定时不猜切点，
保留原生证据但不接纳不可分离的候选。与参考不同本身不是拒收理由。

新版 DEGAP 对每个原生缺口尝试运行一个双向任务。CGAT 校验已封存的 `family-result.json`，用原始侧翼核对候选，且只接纳有证据的接点区间，而不是整段候选。未补上的任务保留原因，不当成执行异常或 App 候选。升级时用新版 Server 的 `install.sh` 刷新同一个受管环境的工具锁，不必单建 DEGAP 环境；旧运行保留为历史，不当作新版任务复用。

## 4. 报告、App 导入与恢复

先打开 `06_report/report.html` 看流程总览。`01_lgz/` 是 LGZ 基线报告，`02_refinement/` 按固定编号分工具，`03_comparison/` 保留每批的 TSV/JSON。从总览进入工具或缺口详情，可查看实际使用的 reads、原生任务是运行还是复用、CGAT 接纳了哪些改动、最终结果是否发布。失败会列出已记录的失败阶段和原因，并链接诊断；零接纳则表示保留 LGZ 序列，并不等于失败。复制整个 `06_report/` 可保留 LGZ、当前已发布的精修报告及比较表之间的链接；也可解压 App 包后打开 `report/report.html`。未发布或失败的尝试详情可能在 `04_refinement/`，最终结果和交付包则位于同级的 `05_final/`、`07_delivery/`；如需保留这些链接，请连同工作区布局一起复制。

在工具报告中进入 **原生 job 报告与日志 → 离线原生可视化**（`native_visualization/index.html`）。新版 DEGAP 的 `Global.report.html` 总览和各双向任务的 `family-report.html` 有独立的离线浏览副本；原始 HTML 作为带哈希的静态文本附件保留。离线副本保留上游内嵌 JS/SVG，与 CGAT 接纳页面隔离，不依赖 CDN；原生页中指向工作目录的文件链接改由 CGAT 诊断区提供。旧 LEFT/RIGHT 历史报告使用其对应的可移植规则。来源绑定会明确显示：`observed_diagnostic` 是「报告时观察」，**不是原生完成回执证明**。缺失、未知依赖或过大的详情有明确状态，不提供悬空链接；总览内嵌 gap 数据也会与可用的原生 gap 诊断核对。

TGS-GapCloser、quarTeT GapFiller、LR_Gapcloser 的固定入口不生成原生 HTML，保留它们实际的日志、填补明细、AGP 等诊断，不伪造上游可视化。Full 与 Light 携带相同报告文件。已用 Windows 浏览器离线检查批次导航、原生图形，以及 Full/Light 报告解压后的相对链接。报告可正常浏览不代表生物学准确性。

将某工具的 **Full** 包导入匹配新版 App 的新项目。其权威 Final Path 和导出染色体对应该工具的接纳结果，`00_lgz` 包则明确未精修。Full 包含来源 FASTA；Light 不含 FASTA，但保留索引、metadata、路径及来源关系，因此导出 FASTA 前需要真实序列来源就绪。不要覆盖已有人工编辑的项目。精修包协议为 schema 5 / App Final Path 4；旧 App 拒绝该协议，不静默显示 LGZ 路径。新 App 保留对旧包的兼容。

手动 App `DEGAP-JOBS` 是独立入口。当前源码收集器将人工候选目录分版本保存在 `04_refinement/01_degap/06_manual/01_catalog/`，以 `.runtime/manual_degap/current.json` 为准，不修改原 LGZ 表。匹配源码构建的 App 已解析实际 Server 运行库，并按内容绑定原始/精修/人工候选种子来源；Full/Light 交付均携带 `metadata/server_sources.json` 身份。受控导出 → Server → 原 App 导入检查保留了手动编辑的 Final Path。已提交迁移清单绑定的旧人工包现可纳入不可变 registry，不重跑原生任务或其比对。未知旧结果 ZIP 仍保护：保留原 ZIP，复制未改动的原 `jobs.tsv` 和 `degap_jobs/` receipt 到新的空目录收集，不重新导出 token。不能把这些协议检查等同于手动全链路验收。

### 项目级手动精修（`refine.py`，当前源码）

除旧版脚本包入口（App 中明确标为「旧版 DEGAP-JOBS（脚本包）」）外，当前功能分支源码在配套桌面端 App 与 Server 工作区之间新增项目级 **精修任务** 流程：

1. **App 导出（装配页当前染色体 / 项目页染色体预览 → 导出）：** 在装配页按项目跨染色体登记 Final Path 的 **Gap**（每个 Gap 可多选工具：默认仅选 `degap`，也可选择 `lrgapcloser`、`tgsgapcloser`、`quartet`）及 **左/右端粒端点**（固定 `DEGAP TelSeeker (telseeker_ctg)` 并配置端粒 motif）。装配页仅保留「当前染色体已选」快捷导出（卡片顶部同时显示当前染色体与全项目已选计数）；全项目总导出收口在项目页右侧「染色体预览 → 导出 → 导出全部精修任务」（与路径文件「全部」分开，入口不在「精修」卡；点击后先打开按染色体分组的预览确认弹窗，确认后才弹出系统保存框写出 `refinement_tasks.zip`，仅汇总本项目已登记位点，不扫描未选位点、不跨项目）。同一 Gap 的工具随同一任务导出。仅通过校验且完全闭合的候选参与择优，优先级同上述工具顺序。默认沿用项目已校验的 reads（界面不展示私有路径），也可显式覆盖或清空；空 reads 同样允许导出。
2. **Server 运行：** 将 `refinement_tasks.zip` 传到对应 Server 工作区，运行 `python .lib/tools/refine.py refinement_tasks.zip`（或已安装的 `~/bin/refine.py`，内部统一委派工作区运行库）。如需在 Server 端指定或覆盖 reads，可追加 `--hifi <文件...>` / `--ont <文件...>`；参数说明见 `--help`。产物保存在 `08_refinement_jobs/02_manual/<batch_sha256>/`，包含 `refinement_results.zip`、`summary.json` 和 `report.html`，并在 `06_report/report.html` 合并手动精修区段，不会改动自动终版 `05_final/`。
3. **报告边界与隐私：** 可分享 HTML 报告不公开服务器私有 reads 路径（仅保留测序类型与 SHA-256 摘要），明确区分「等待导回 App」（`pending_app_import`）与「无可导回补丁」（`no_patch`）；无 App 回执前绝不标记为已导回。
4. **App 导回、来源标记与撤销/切换：** 项目页「精修」卡片（位于数据集表与假分子预览之间）通过 `list_manual_refinement_results` 展示真实导回批次，并通过 `import_manual_refinement_results` 直接导入 `refinement_results.zip`（导入前先保存当前项目待保存的 Final Path，导入成功后重新载入权威装配与预览数据，不新建也不指定轨道）。已采用的精修片段在 Final Path 图与表中统一显示轻量「精修」标记，详细来源见 Tooltip 与 Final Path 日志贡献表。位点级撤销与候选切换已按 `undo_manual_refinement_locus` / `switch_manual_refinement_locus` 协议接入（不做本地模拟，由后端校验版本与边界）。Server CLI 与报告测试位于 `GPM2.0/server/tests/test_refine.py`。

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
