# SSH 180：post-LGZ 真实数据合并前验证

2026-11-22（Asia/Shanghai），在 Donau `arm` 队列验证 feat 源码
`30dafa1cee9d4cdb03e7b0513dbe1246c3025799`。采用独立任务目录和此前验证过的私有
ARM 环境；重新核验工具锁和执行环境。本次未修改 `master`、客户任务、共享环境或发布产物。

**合并前仍需修复一个启动问题。** `micromamba run -n cgat-server bash <out>/run_all.sh …`
会被 reference handoff 误判为另一个活跃的工作区进程。最小复现记录了被命中的真实
父进程命令行；激活相同环境后直接执行 `bash <out>/run_all.sh …` 不触发误判。
此处应修正对当前启动链的识别，同时保持对无关工作区并发写入的拦截。不要通过删除锁、
取消进程防护或重建工作区来绕过。激活环境的成功路径不代表 wrapper 已修复。

## 输入与结果

- **拟南芥 Col-0（自然缺口）**：从公开组装 `GCA_964341225.1` 的
  `OZ204932.1` 原样截取 200,463 bp，缺口为原组装 0-based 半开区间
  `[203829, 204292)` 的 463 个 N，未人工遮盖。`ERR13987671` 与 draft
  记录关联到同一个 BioSample `SAMEA117327409`。预先用 TAIR12 `GCA_978657495.1`
  对上两侧锚点，从全参考比对中选择 157 条原始 PacBio HiFi 记录（保留原始 `/ccs` 名称和完整记录；全部均值 Q≥20）。
  TAIR12 在本次用作 `--ref` 和区间对照，不作为供体 `--ds` 或 reads。LGZ-only
  保留原缺口，随后在同一工作区通过 `run_all.sh --hifi … --gapfill-tools …` 跑四个固定版本。
- **酵母 ONT（遮盖对照）**：`ERR13375554`，来源为 `PRJEB77686` 的酿酒酵母
  RIB1005。reads 为真实 PromethION 数据，2,000 bp 缺口是人工遮盖，不计作自然缺口。
  直接用 `run.sh --ont …`，不显式选工具。默认 DEGAP 原生尝试四轮后耗尽，
  零接纳、终版序列不变；保留了对应原因、工具报告和 Full/Light 包。

| 拟南芥工具 | CGAT 接纳 | 终版剩余 N | 区间对照 |
| --- | ---: | ---: | --- |
| DEGAP `6cd01f1` | 1 | 0 | 三轮闭合。独立 patch 来源重建了 463 bp，与 TAIR12 同源区间逐碱基一致。 |
| TGS-GapCloser `1.2.1` | 0 | 463 | 原生完成，无接纳改动。 |
| quarTeT GapFiller `1.3.1` | 0 | 463 | 原生报告无候选，区别于运行失败。 |
| LR_Gapcloser `1.0` | 1 | 0 | 接纳 629 bp patch，与 463 bp 对照区间不完全相同，不能仅凭缺口消失判定正确。 |

单个真实缺口仅用于验证接入和结果溯源，不用于工具准确率、吞吐量或两种测序技术的比较。

## 复核入口

远端根目录：`~/cgat-reads-debug/post-lgz-refinement-real-30dafa1c.8gngb5wS/`。
分别打开 `runs/col0-append/06_report/report.html` 和 `runs/ont-default/06_report/report.html`。
各工具的终版及来源文件在 `05_final/<编号_工具>/`，Full/Light 在 `07_delivery/<编号_工具>/`。

- `43016014`：ONT 默认入口及终版/交付复核通过。
- `43016016`：首次拟南芥启动未初始化 Donau `appdir`，在模块加载阶段退出，未开跑。
- `43016020`：真实输入及 LGZ-only 完成；追加参数触发 wrapper 启动误判。
- `43016140`：激活同一环境后，原工作区四工具均运行并发布。作业随后被临时验收脚本判失败：
  脚本把所有零接纳都限定为 `completed_zero_accepted`，实际 quarTeT 正确使用 `native_no_candidates`。
  两者分别记录，未改动生产代码或原始日志。
- `43016146`：复核各自状态、来源、双包及无改动重跑。通过。四项原生完成回执、Final Path 和 FASTA 的
  SHA-256 前后不变；LGZ q0–q3、原始 PAF 和 5 个 LGZ 基线终版文件的字节及 mtime 均不变。

两套报告的本地链接检查通过（拟南芥 24 页、222 条；酵母 10 页、81 条）。
Full/Light 含真正的报告和来源产物，未把交付校验冒称为本次桌面 App 导入。

`evidence/` 保留输入哈希及公开归档元数据、工具锁探测、基线与终版核验回执、
`col0-append-junction-comparison.json`、`standalone-guard-probe.PeEayuGY/` 与调度器状态。
