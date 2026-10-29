# 长查询分窗比对实验（不修改 minimap2）

这是**隔离的研究原型，不是 Server 的新默认算法或客户修复包**。不集成到
`run.sh`，不自动重试失败任务，也不向已有工作区替换 `result.paf`。

目标：在不修改 minimap2 本体、不丢弃查询、不删除 `-c` 的前提下，验证是否可以
绕过已复现的 270 Mb 单条比对 CIGAR 断言，同时恢复原序列坐标。

## 原型做什么

1. 校验并只读扫描原始纯文本 FASTA；在**新的实验目录**中生成私有序列副本。
   支持普通换行、CRLF 和不等长换行；拒绝重复 ID、空序列、非法字符及单条
   超过有符号 32 位坐标范围的记录。不更改原始 FASTA 或其 `.fai`。
2. 查询按默认 50 Mb core 分窗，每侧附加 100 kb 上下文。core 覆盖每个原查询
   碱基恰好一次；窗口总长度（core + 两侧上下文）严格受 28 位长度上限限制。
   参考不切窗，使用完整参考新建单段索引；不使用不明来源的缓存。
3. 调用现有 minimap2：`-c --eqx -x asm10`。`--eqx` 只是让原型逐碱基核对和
   重算裁剪后统计；不是单独解决原版溢出的参数。默认不添加 `-X` 或跳过长查询。
4. 还原原查询 ID、全长和坐标。按 CIGAR 在正反链上裁剪到窗口 core，分别推进
   query/target 坐标；边界上的 deletion 统一归属于查询正向坐标较高一侧的 core。
   在两个端点外不虚构比对、不填补缺失覆盖。
5. 对整条原始比对及裁剪片段，依据原始碱基核对 `=`/`X`、重算匹配/歧义统计；
   只有完全相同的 owned 关系才去重，不丢弃不同目标或不同位置的候选。
6. 额外生成严格连续的 stitched 候选：只连接相邻 core 中 query 和 target
   端点都完全相同、前后连接关系互相唯一的同链片段。分叉、缺口、倒位和
   同一窗口内 minimap2 自身切开的行不强行拼接。每条 stitched 行保留来源。
   超长逻辑操作仍写成各自不超过 `268435455` 的相邻 CIGAR 项，不重新编码
   到 minimap2 内部结构，也不输出 BAM。
7. 保留原始 PAF、命令、stderr、窗口映射、逐行 provenance、覆盖区间、输入与
   二进制 SHA-256。原输入/工具发生变化、子进程失败或校验失败时停止，保留证据。

## 为什么不能直接拿分窗 PAF 替换正式结果

分窗会改变整条 contig 的竞争、主次比对和评分。恢复坐标**不等于**恢复这些语义。
原型把 MAPQ 标成缺失值 `255`，不冒用窗口级 `AS`、`ms` 或 `tp` 标签。
这不能被视为更高置信度；正式消费者需要明确支持“缺失”，不能直接拿去排序。

实际对照发现：未拼接的 owned PAF 虽然碱基路径相同，现有 CGAT 归属逻辑按行
加权会使 indel 案例的 `anchor_start` 发生变化。严格连续拼接在当前合成对照中
消除了该差异，但不能据此承诺在复杂多倍体/重复序列中完全等价。

当前不支持或未验收：

- 主原型入口仍不支持自比对。独立 `compare_self.py` 已对 canonical alias、去对角线和去双向重复做了有限合成验证，
  不是生产自比对适配器。
- 全 contig 主次比对/评分/MAPQ 重建，以及复杂重复、多倍体中的候选竞争。
- 没有输出映射的窗口不会被假装覆盖；它们会出现在覆盖报告中。完整覆盖只适用于
  明确要求该条件的合成验收，不是生物数据总应对齐的假设。
- 窗口只限制 query 消耗，**不保证**异常超长 target deletion 或其他 minimap2
  缺陷不会触发；失败仍应保留，而不是继续缩窗直到“跑过”。
- 插入-only owned 片段目前明确拒绝，不静默删除。
- 多段 target 索引不接受。大参考的单段索引可能需要很多内存；`--memory-gib`
  是地址空间上限，默认 10 GiB，不能据此假定小麦全参考可在该限制内运行。
- 全流程等价性仍未成立。`compare_grt.py` 已对初始参考 PAF 替换做真实 GRT Step1–Step4 / Final Path 对照，但发现重复候选差异；
  自比对仍跳过，GRT 内部独立比对未分窗，原生 App 和客户小麦未验收。

因此产物始终标记 `experimental_only: true`、`production_ready: false`。
本目录不进入正式 Server 源码包，不更改既有 Release 或生产参数。

## 运行（仅限实验数据）

从仓库根目录执行；输出目录必须尚不存在，所有路径均可包含空格：

```bash
python3 GPM2.0/experiments/long_query_alignment/windowed_alignment.py \
  --minimap2 /absolute/path/to/minimap2 \
  --target /path/to/synthetic-reference.fa \
  --query /path/to/synthetic-query.fa \
  --out /tmp/new-long-query-experiment \
  --core-bases 50000000 --context-bases 100000 \
  --threads 2 --memory-gib 10 --timeout 600
```

Linux / Python 3.10+，无额外 Python 包。需要明确合成案例的全查询覆盖时，加
`--require-full-query-coverage`；无映射或覆盖不达标不会发布 final candidate。
默认 core/context 是**实验设置**，不是已验证的生物分析推荐值。

主要输出：

- `experiment.json`：真实状态、限制、工具/输入身份、覆盖及拼接统计。
- `raw.windows.paf`、`map.command.json`、`map.stderr`：未处理的真实比对证据。
- `windows.json`、`provenance.jsonl`：窗口坐标与每一行的保留/去重/上下文裁剪原因。
- `owned.experimental.paf`：core 内比对，保留窗口行结构。
- `stitched.experimental.paf`、`stitch-provenance.jsonl`：严格连续拼接及其来源。
- `*.pending.paf` / `*.partial`：失败过程中保留的中间结果，**不是成功结果**。

## 可复现验证

轻量单测与 120 kb 正反向真实比对（已接入 Linux Quality）：

```bash
python3 -m unittest discover -s GPM2.0/experiments/long_query_alignment -v
```

2 Mb 级 11 类对照；同时运行当前 Server 的**准备和染色体归属**（不执行完整 GRT）
时，需激活正常 Server 环境并传入 `--server-dir`：

```bash
python3 GPM2.0/experiments/long_query_alignment/compare_small_fixtures.py \
  --minimap2 /absolute/path/to/minimap2 \
  --server-dir GPM2.0/server \
  --out /tmp/new-small-window-comparison
```

270 Mb 原版失败及正反向分窗验证，默认不在 CI 中运行（需 C 编译器、数 GiB
内存/磁盘和数分钟计算时间）：

```bash
python3 GPM2.0/experiments/long_query_alignment/reproduce_large.py \
  --minimap2 /absolute/path/to/minimap2 \
  --out /tmp/new-270m-window-reproduction
```

对照中保留原始差异：`path_relation_equal` 比较 aligned-base/indel 坐标关系，
不把不同分段行数当作错误，也不吞掉真实位置/链向/indel 差异；
`assignment_equal` 是未拼接结果，`stitched_assignment_equal` 是拼接后结果。
即使这些检查通过，`ranking_equivalence` 和 `full_grt_tested` 仍不标为已通过。

本次实测见 `VALIDATION_20261029.md` 和 `evidence/` 中的小型 JSON 回执。

## 后续下游、自比对和重复候选审计

完整记录见 `VALIDATION_DOWNSTREAM_20261029.md`。这些脚本仍只接受**新建实验目录**，
不得指定客户工作区；对照有差异仍保存报告，不把退出码 0 当作等价性验收。
需要检查 `relation_equal`、各项 `checks` 和独立的原始 metadata 差异。

```bash
# 在正常 Server 环境中运行，PATH minimap2 必须与显式二进制完全一致。
# 真实执行准备、GRT Step1–Step4、染色体内数据集比对、证据汇总与 Final Path 导出；
# 仅替换 primary dataset 的初始 ref PAF，其他比对和生产代码不改。
python3 GPM2.0/experiments/long_query_alignment/compare_grt.py \
  --minimap2 /absolute/path/to/minimap2 \
  --server-dir GPM2.0/server --out /tmp/new-window-grt-audit

# 独立检查 -X 下原始无序 contig 对和窗口别名；不是上面流程的自比对集成。
python3 GPM2.0/experiments/long_query_alignment/compare_self.py \
  --minimap2 /absolute/path/to/minimap2 \
  --server-dir GPM2.0/server --out /tmp/new-window-self-audit
```

注意：即使 `scientific_projection_equal` 为真，初始 PAF 仍可能新增候选位置；
`coordinate_and_downstream_equal` 还要求关系对照与所有 downstream checks 相同，
但仍**不包含**整条 MAPQ/主次评分等价性，更不是生产放行字段。所有运行始终
`production_ready: false`。不能为了让测试通过删除重复候选、覆盖原始差异或把
MAPQ=255 改成一个任意“安全分数”。当前 FASTA 存储器只接受 ASCII 序列 ID。


## 整条候选约束分窗（第二阶段，仍为实验）

`guided_alignment.py` 增加独立的整条 query 链预比对，用作候选位置约束；
**最终输出仍必须具有逐碱基验证的 CIGAR**，不是去掉 `-c` 的替代方案。
原始分窗输出不删除，新增候选的排除原因、候选归属及恢复覆盖都单独留档。
所有选中的主/次级候选都必须恢复；候选丢失、路径超出已支持的几何范围或归属
不唯一会停止，不会不断放宽参数。MAPQ 仍未知，不冒用预比对的评分。

```bash
python3 GPM2.0/experiments/long_query_alignment/guided_alignment.py \
  --minimap2 /absolute/path/to/minimap2 \
  --target /path/to/synthetic-reference.fa --query /path/to/synthetic-query.fa \
  --out /tmp/new-guided-window-experiment
```

新的 9 组 GRT 对照中，先前两个重复候选反例已纠正；2.7 亿碱基的正反向恢复
也通过。但新增的真实 decoy 反例证明链预比对与最终 DP 候选/MAPQ 并不等价，
当前实现会明确拒绝该案例。因此**仍不进入正式 Server 或原生 App**。

详见 `VALIDATION_GUIDED_20261029.md`。在上述 `compare_grt.py` 或
`reproduce_large.py` 命令中增加 `--guide-chains` 才启用新实验路径；默认仍是
未约束的原对照。成功结果为顶层 `guided.experimental.paf`，预比对
`whole-query.chains.paf` 以及子目录中的原始分窗结果均不得当成已验收结果导入。


## 原始链得分来源与未知 MAPQ 消费修复

后续记录见 `VALIDATION_POST_DP_20261029.md`：

- App 拆分预览已单独修复 MAPQ=255 被误计为高质量的问题，保留原始未知值和
  普通覆盖证据。这不等于接受实验 PAF，也没有发布新安装包或改动 Server。
- 真实反例证明仅使用 AS 会保留错误候选。受限诊断已通过原版 minimap2 的
  seed/chain 记录，为分窗恢复的片段复算出正确链得分；完整候选选择与 MAPQ
  尚未恢复，原 guided 模式的拒绝条件不变。
- `audit_post_dp.py` 只生成 200 kb 合成输入，诊断 `-P`/seed trace 不作为正式
  参数建议或输出。不要将当前内存型 trace 解析器直接用于小麦规模数据。

## 客户侧隔离定位（非生产修复）

`isolate_minimap2.py` 是独立、标准库实现的显式诊断入口，见 `ISOLATION.md`。
默认仅预览；只有 `--execute` 才启动一次有时间/内存/文件上限的比对。
单线程 QR/QT 配对定位活动 query，不能用最后一条 PAF 猜测触发序列。
可在新目录提取指定整条 query 独立重放，原参考、原 FASTA 和工作区不改。
回传包只含日志/身份/命令，不含序列、PAF 或 core；没有自动提交、上传或参数重试。
270 Mb 真实断言定位与独立重放验收见 `VALIDATION_ISOLATION_20261029.md`。
该工具不进入正式 Server 包，也不代表客户已跑通。

## 流式 seed/chain 证据（仍为受限实验）

`stream_seed_trace.py` 已替换 score witness 中整份 trace/全部 seed 的内存缓存。
逐行校验并计算 SHA256，只保留当前 chain 的摘要和一个匹配结果；总字节数、
行数、行长和时间均有限制。只支持现有单 query、单线程、同链向两片段的 witness，
不恢复通用候选排序/MAPQ，不改变生产参数或客户隔离诊断包。

同一百万 seed trace 的旧/新完整 witness 一致；512 MiB 地址空间上限下峰值 RSS
约 234 MiB / 21 MiB。解析略慢，不宣称提速；这不是完整小麦流程的内存测量。
复现实验、协议拒绝项及剩余边界见 `VALIDATION_STREAMING_20261029.md`。

## 反向两片段与不同内存预算

反向 seed/片段关联已加入受限 witness：转换 query 坐标系，并按原 chain/target
顺序分配切分得分，不能按正向 query 坐标排序。真实反向 DP 和窗口证据对照通过；
不完整候选仍拒绝，通用候选筛选/MAPQ 仍未完成。

`trace_memory.py` 实现解析进程级预算适配：显式预算和 `RLIMIT_AS` 取较小值，
扣除当前虚拟内存及余量，再自动选择有界缓冲；预算不足不丢数据而是明确停止。
未知进程上限采用标明来源的保守规划值，不冒称已识别 Slurm/cgroup 的共享可用内存。
这不是整套 CGAT 的内存调度器，也不保证整个小麦比对能在任意内存下运行。
实测、模拟预算的区别与复现命令见 `VALIDATION_REVERSE_ADAPTIVE_20261029.md`。

## 作业内存预算与排队规划（实验层）

`job_memory.py` 增加只读 Slurm/cgroup v2 预算发现：检查可见祖先限制及当前占用，
不拿整机 RAM 代替作业额度。纯函数规划器结合显式 CPU、基线、余量和任务峰值预算，
预算小时暂缓新任务，预算大时允许更多拟并发；不跳过数据，也不自动启动任务。
当前没有接入生产调度器，未知峰值、cgroup v1、未确认的 Slurm per-CPU 额度等明确拒绝。

用户已要求将后续测试统一留到收尾；此前完成的结果与尚未运行的验收项分开记录于
`VALIDATION_JOB_MEMORY_20261030.md`。客户正在跑的诊断包及原流程不受影响。
