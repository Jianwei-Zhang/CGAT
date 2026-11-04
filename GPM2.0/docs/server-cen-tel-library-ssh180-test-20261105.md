# cen/tel 库：SSH 180 完整 Server 流程复核（2026-11-05）

## 1. 结论与测试基线

四组真实工具的完整 Server 流程及各自一次 resume 均通过；最终 ARM Server Python
全量回归 **446 tests、0 failures、0 skipped**，另有 **8 组 shell 回归通过**。
本轮没有修改业务代码、客户工作区、共享软件环境或正式发布资产。

- 被测 Git revision：`0571eba42f09bc7031466264e47c1e10e65dcbdc`。
- 源码来自该提交的 `git archive`，不是尚未包含本功能的旧发布包。
- 源码归档 SHA-256：`ad83477f086b60ddf76a076f503139dd9353f24324cadf4edb2c939f295fd3c5`。
- 传输后校验整个载荷 SHA-256；收尾再逐文件核对归档中所有源码，确认未改变。
- 远端根目录：`~/cgat-reads-debug/cen-tel-20261105-0571eba/`。
- 登录节点 `cli-ARM-01`；生物学流程及 Python/shell 回归通过 Donau `arm` 队列执行，
  每作业 2 CPU。维护用生成运行时校验单独使用 `x86` 队列、1 CPU，见第 5 节。
- 本文日期按 Asia/Shanghai；工作流 run ID 使用 UTC，可能以 `20261104T17...` 开头。

环境复用已安装的独立 ARM 依赖环境，缓存和 HOME 指向本轮专用目录，不重装、不修改旧环境：
Python 3.11.14、minimap2 2.31-r1302、MUMmer4 4.0.1、samtools 1.23.1、meryl 1.4.2、
Merqury 1.4.1、CRAQ 1.10、pigz 2.8。当前公共 module 的相关版本与项目锁定版本不一致，
因此用上述已核对的独立环境；最终回归另显式加载 `arm/git/2.47.1`。

## 2. 数据与完整流程结果

| 数据 / 控制 | 输入 | 已核对结果 |
| --- | --- | --- |
| `synthetic` | 与真实工具集成测试相同的 seed=912 合成序列，20,820 bp；ref 与 assembly 序列相同 | 两端各 210 bp tel 重复，产生 2 条双链 tel 标记；CentO 候选 4,211–16,610，覆盖 12,400 bp，identity 100% |
| `public_rice` | 缓存的公开 ENA/INSDC 原始 EMBL `AY101510.1`，62,203 bp；分别作为 ref / assembly | CentO 候选 22,635–62,136，跨度 39,502 bp，命中覆盖 33,749 bp，identity 93.914%；无 tel 标记 |
| `synthetic_gap` | 合成序列派生：primary 的 1,001–1,500 替换为 500 个 N，support 为完整原序列 | q0/q1/q2 各有 500 N；Step3 接受 support/donor 的 1,001–1,500 回填；q3/q4 均无 N，最终序列与原始合成 reference 完全相同 |
| `library_contract` | 同一合成数据，使用独立 tools 副本添加本地库，并显式传入 tel/cen | 官方 + 本地 + 参数同时生效；重复内容去重后仍为 3 条 tel 规则、4 条 cen 序列，命中保留三类来源及 note；变更安装库、删除本地条目后，resume 仍保留原冻结数据和注释 |

公开水稻原序列 MD5：`9f6d944e997a731a9e37cb0b72e1562f`；原始 EMBL、转换后的 FASTA、
合成输入及其 SHA-256 均保留在任务目录。该片段的 3 个原始 N 在结果中原样保留，
没有将未提供 donor 的原始不确定碱基假称为已修复。

前三组不显式传 `--tel`/`--cen`，以检查官方库自动启用；四组均未传 `--skip-self`，
按默认 chr-partition 配置执行。ref alignment → assignment → LGZ prepare → Step1 →
Step2 → Step3 → telomere finalize → chromosome alignment / tel/cen scan →
evidence finalize → Full / Light staging → report → 最终归档全部完成。
单 assembly 场景为 11 个执行单元，primary+support 场景为 12 个，状态全部 success。

## 3. 来源、冻结、证据与交付检查

- 校验 `metadata/annotation_library_snapshot.json` 与 `tel/rules.tsv`、`cen/reference.tsv`、
  `cen/library.fa` 的 SHA-256；首次完成与 resume 后快照字节不变。
- 四组最终 q4 序列均逐碱基等于各自预期 reference；前三组 cen 命中在 resume 前后完全一致。
- 缺口回填不是仅靠 N 数推断：存在 accepted Step3 refill 事件
  `event-12ebdbd06f37b2b426d9e228`，明确指向 `support:donor:1001–1500`，
  且有 evidence ID 和 final-path segment ID；最终 bundle contract 校验通过。
- 叠加控制通过真实 `library.sh add-tel/add-cen/list/remove` 操作；本地 note 保留，
  显式参数的 note 为空；官方条目删除被拒绝。修改的只是专用 tools 副本中的官方 note，
  本地库文件哈希保持不变，随后删除本地条目也不改变项目已冻结结果。
- 该官方内容变化控制不是一次正式 updater 下载/发布。实际更新器的本地库保护另由全量回归中
  `test_official_library_updates_never_touch_local_or_project_snapshot`、
  `test_official_source_cannot_own_user_local_library_paths` 覆盖。
- 每组均生成 Full 与 Light，共 8 个包；逐包 `gzip -t`，检查成员路径/重复项、快照与报告内容。
  Full 保留 cen FASTA；Light 没有 `.fa/.fasta/.fna`。两个包都保留完整报告、来源和 note。

最终 resume 后的交付文件（均在远端 `runs/`）：

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| `library_contract.light.tar.gz` | 83,469 | `67fac1078557dfb0bbaff0b39874590211de995673b939ebbbca0e3c842abb4c` |
| `library_contract.tar.gz` | 95,343 | `1016be27f055d786642122160a95b32c2e633ad92004f3d64efc59f483d73fbe` |
| `public_rice.light.tar.gz` | 82,239 | `edc308531cf372b27ef1dfb753d78e9761ccaeb84f9d7f68475b8ec18a4f4868` |
| `public_rice.tar.gz` | 123,269 | `f7e8c2058e6548ca7ddec2b72534ea42e2e56d00658a380938648fb6b43fa9b3` |
| `synthetic.light.tar.gz` | 81,610 | `b1a4555126eec8d1d092e14f30b2160d6daff3f1006bc95e0cf15a298ed128bd` |
| `synthetic.tar.gz` | 93,393 | `18799f1d6aad9a0630e5574484c585280e8cd4250e7bdfd59df15331683d682d` |
| `synthetic_gap.light.tar.gz` | 95,351 | `b7504f1ab59aff77b073410ac26a18aed47046508e9f45d3cc535e73660f6148` |
| `synthetic_gap.tar.gz` | 108,791 | `15095a7edc3c94fb993ae8c02d7b63be9a9cd32bd68044e1a8ce243b59bf8fa1` |

## 4. 回归与作业证据

最终 ARM Python 回归：**446 tests，0 failures，0 skipped，609.037 s**；
其中包含 11 项 annotation-library 测试、4 项真正 nucmer/show-coords 的集成测试，
不是把 mock 或 skip 算作真实 MUMmer 通过。

8 组 shell：`fake_command_control`、`env`、`package_templates`、`prepare_metadata`、
`prepare_full`、`final_path`、`add_dataset`、`add_ctg`，全部退出 0。

| 作业 | 用途 | 最终状态 |
| --- | --- | --- |
| `40866525` | 合成默认库完整流程 + resume | SUCCEEDED |
| `40866526` | 公开水稻片段完整流程 + resume | SUCCEEDED |
| `40866527` | 缺口回填控制完整流程 + resume | SUCCEEDED |
| `40866535` | 官方/本地/参数叠加、note、冻结 resume | SUCCEEDED |
| `40866559` | 补齐 Git 后全量 Python + 8 组 shell | SUCCEEDED |
| `40866569` | x86 生成运行时只读一致性校验 | SUCCEEDED |

## 5. 初轮环境问题与修正记录

未删除失败记录，也未改动业务逻辑或弱化断言以得到通过：

1. 初轮 `40866528`：Python 为 445 passed + 1 skipped，原因是计算节点无 Git；
   之后维护校验器按 ARM 宿主架构寻找 companion，而仓库只携带 `linux-x86_64` bundle，
   因而作业失败。补载 ARM Git 后以 `40866559` 完整重跑所有 Python 测试及 shell 测试。
2. 维护校验改为架构匹配的 x86 作业；初次 `40866560` 发现集群 Python module 仅提供
   `python3.10`，无版本名 `python3` 仍落到系统 Python 3.6。改为 module 的显式
   `python3.10` 并检查版本后，`40866569` 通过；未在 ARM 执行 x86 二进制。
3. 最终原始 `sync_server_runtime.py` 只读校验结果为 `status=verified`、`changed=[]`，
   既核对生成源码，也核对已审核 x86 companion 的哈希/receipt；没有使用 `--write`。

初轮日志保存在 `logs/python-regression.initial.log`、`logs/runtime-integrity.initial-arm.log`、
`logs/runtime-integrity.initial-x86.log` 及对应 scheduler job 输出中。

## 6. 可复核位置与边界

根目录按 `source/inputs/scripts/runs/logs/reports` 分层；一次性 `.dsub`、环境加载脚本和验收脚本
全部保留在 `scripts/`。如需完整重跑，应使用新任务目录并更新脚本中的任务根路径，
不要覆盖本次证据；计算仍须通过 Donau 提交，不在登录节点跑生物学计算。

完整证据包为 `evidence/cen-tel-0571eba-evidence.tar.gz`，包含固定源码载荷、输入、脚本、
日志、机器报告及 8 个交付包，已下载至本地复核 SHA-256 和内部索引：

`8e98e6e3b6336cec696572ebd93d5a7c7d10f4c41c231f01d3e35c7786fd1e14`。

主要机器可读证据：

- `reports/summary.json`、`reports/environment.json`、`reports/inputs.json`。
- `reports/postflight.json`：逐碱基一致性、N 变化、accepted 事件与源码完整性。
- `reports/<case>.first.json`、`reports/<case>.resumed.json`：前三组首次/恢复后的注释与包验收。
- `reports/library_contract.json`、`reports/delivery-sha256.tsv`、`reports/scheduler-final.txt`。
- `logs/python-regression.log`、`logs/shell-*.log`、`logs/runtime-integrity.log`。
- 每组 `runs/<case>/report/report.html` 和该工作区完整日志、事件/证据及冻结库。

**本次通过声明仅覆盖上述小规模数据的真实完整 Server 流程和自动化回归。**
未提供 reads，`reads_qc_enabled=false`，不声称执行 Merqury/CRAQ 的 reads 质控；
不构成全基因组/全物种敏感度或误报率验收，单 contig 控制也不构成大规模 self 比对验收。
未做远端 App 导入/图形界面、浏览器或原生窗口验收，未在远端运行包含 App E2E 的标准全门禁；
其本地通过记录见 `server-cen-tel-library-review-20261104.md`。维护校验在 x86 通过
不代表长 CIGAR 异常恢复分支已在 ARM 验收。本轮不做正式发布或线上资产替换。
