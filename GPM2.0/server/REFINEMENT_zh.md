# LGZ 后精修与编号工作区

[English](REFINEMENT.md) | **中文** · [Server 手册](README_zh.md)

本指南对应功能分支中的源码实现，不会追溯改变已发布的 v2.0.21 压缩包。四工具真实小样例、Linux x86_64/ARM64 环境及完整验收矩阵仍待最后统一检查。请使用同一版源码构建的安装器与 App；不要覆盖正在使用的安装目录，也不要在作业运行时更新环境。

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
| `01_degap` / `degap` | 一次原生混合输入运行 | DEGAP 2.0，revision `0b3c9bc7acc5bd290ad2b23d53cc57815f1c7e75` |
| `02_tgsgapcloser` / `tgsgapcloser` | 仅用 HiFi；没有 HiFi 时使用 ONT | TGS-GapCloser `1.2.1`，分发变体 `1.2.1_ml`、build 4；revision `52818b3e464209477baec506ade3240be43b4fa8` |
| `03_quartet` / `quartet` | 一次 GapFiller 运行消费两组输入 | quarTeT `1.3.1`，revision `a44d8c87e3f4bcefaf43dc4134e88b6a21890265` |
| `04_lrgapcloser` / `lrgapcloser` | 仅用 HiFi；没有 HiFi 时使用 ONT | LR_Gapcloser `1.0`、build `pl5321hdfd78af_0`；revision `156381adec01a5c664edbf5df1d866b5c70e82a1` |

仅提供一种技术时，各所选工具使用该组数据。TGS/LR 不会悄悄各跑一遍 HiFi、ONT；报告记录提供、实际消费和未使用的输入。[`contracts/refinement-tools.lock.json`](contracts/refinement-tools.lock.json) 才是各平台包 hash、依赖 build、固定参数和公开 wrapper 补丁的权威清单，仅有版本号不算固定完整版本。环境定义覆盖 `linux-64`、`linux-aarch64`，不表示两种架构都已真实跑通。工具串行运行，共享已保存的线程预算，不为四工具分别同时申请整份预算。

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
  .runtime/                          锁、checkpoint、metadata、日志和历史
    refinement/<tool-dir>/<run>/final/  按来源重建的私有待发布结果
```

方括号表示两个实际文件，不是文件名的一部分；`--archive-format zip` 使用 `.zip`。每种工具在 `04_refinement`、`05_final`、`06_report/02_refinement`、`07_delivery` 下的目录编号固定，不因只选择一个工具而改号。编号工作区不再保留根目录 `data/`、`grt/`、`report/`、`logs/` 影子树。App 包内部仍使用协议约定的 `data/`、`metadata/` 等路径，不要手动改包内目录。

仅存在工具目录不能证明本次成功，应以当前总览和内容绑定的 committed 发布回执为准。新尝试失败会留存诊断，不删除旧的成功发布，也不把旧发布标成新结果。一个工具失败不妨碍其他成功工具或 LGZ 基线交付，但本次流程总退出码非零。

最终组装由已接纳、可追溯来源的改动重建，不直接复制原生整条染色体，也不把 LGZ FASTA 改名冒充精修。合法的部分修复、联合缺口、负链和重叠连接保留来源关系；歧义或越界候选不接纳并记录原因。可能出现零接纳，必须与原生失败区分。结构/来源检查**不等于生物学正确性验证**。未变来源坐标上的证据会保留。新接纳的 patch 来源现会对原准备参考独立比对，并使用冻结库执行 tel/cen 扫描，不重跑 LGZ 或补洞工具。测量保存在 `04_accepted/<run>/01_source_evidence/<generation>/`，报告及两类 App 包携带同一证据；`no_hit`（测量无命中）、`disabled`（未启用）、`no_rules`（无规则）和 `no_chr_library`（无该染色体库）分开记录。包内 `metadata/refinement/source_intervals.tsv`、`final_annotations.tsv` 按真实切片、反向及截断关系映射到新坐标。这是来源扫描和坐标映射，不冒充完整终版基因组重扫描或准确性验证。

## 4. 报告、App 导入与恢复

先打开 `06_report/report.html`，再进入每工具报告及其 job/原生诊断链接。报告区分所有原始 gap、原生候选、接纳改动、残余 N 和末端 gap，并说明实际消费的数据差异；不自动评选最佳工具，不编造准确率或峰值内存。复制报告时带上整个可搬移报告目录，保留相对链接。上游 HTML 当前以安全文本附件保留，不冒充已验收的离线交互原生可视化。

将某工具的 **Full** 包导入匹配新版 App 的新项目。其权威 Final Path 和导出染色体对应该工具的接纳结果，`00_lgz` 包则明确未精修。Full 包含来源 FASTA；Light 不含 FASTA，但保留索引、metadata、路径及来源关系，因此导出 FASTA 前需要真实序列来源就绪。不要覆盖已有人工编辑的项目。精修包协议为 schema 5 / App Final Path 4；旧 App 拒绝该协议，不静默显示 LGZ 路径。新 App 保留对旧包的兼容。

手动 App `DEGAP-JOBS` 是独立入口。当前源码收集器将人工候选目录分版本保存在 `04_refinement/01_degap/06_manual/01_catalog/`，以 `.runtime/manual_degap/current.json` 为准，不修改原 LGZ 表。匹配源码构建的 App 已解析实际 Server 运行库，并按内容绑定原始/精修/人工候选种子来源；Full/Light 交付均携带 `metadata/server_sources.json` 身份。受控导出 → Server → 原 App 导入检查保留了手动编辑的 Final Path。已提交迁移清单绑定的旧人工包现可纳入不可变 registry，不重跑原生任务或其比对。未知旧结果 ZIP 仍保护：保留原 ZIP，复制未改动的原 `jobs.tsv` 和 `degap_jobs/` receipt 到新的空目录收集，不重新导出 token。原生工具最终验收仍未完成，不能把协议检查等同于手动全链路验收。

停止或失败后重复同一入口命令；完整且通过校验的结果会复用。已封存完成的原生运行，在接纳、报告或发布失败后可以重新接纳，不重跑工具。只有报告或打包器变化时刷新报告和包，未变化的最终序列文件不替换。

原生内部恢复边界：

- **DEGAP：**由原 LEFT/RIGHT 调度器恢复已封存的终止子任务。LEFT 未补上时仍运行 RIGHT；预处理和缺口检测重新执行，不接续未完成的延伸轮次。
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

## 5. 显式迁移已完成的旧工作区

未标记的旧布局必须先显式迁移再追加；不要覆盖运行 `prepare.sh`，也不要用 symlink 假装已经编号。当前适配器要求原 LGZ 基线**已经完成且可验证**；尚未完成的旧 LGZ 阶段迁移/续跑仍待实现，会拒绝处理，不换用新引擎重算。

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

不会覆盖被修改的用户数据，也不会抢占未知/活跃 owner 的锁。遇到拒绝时保留 journal/备份并排查，不删除工作区 metadata。上述源码契约和受控检查仍需发布前真实工具、环境与 A01–A18 最后统一验收。
