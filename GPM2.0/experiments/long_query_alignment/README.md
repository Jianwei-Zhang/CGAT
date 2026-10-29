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

- CGAT 的同数据集自比对、canonical alias 与去对角线语义。
- 全 contig 主次比对/评分/MAPQ 重建，以及复杂重复、多倍体中的候选竞争。
- 没有输出映射的窗口不会被假装覆盖；它们会出现在覆盖报告中。完整覆盖只适用于
  明确要求该条件的合成验收，不是生物数据总应对齐的假设。
- 窗口只限制 query 消耗，**不保证**异常超长 target deletion 或其他 minimap2
  缺陷不会触发；失败仍应保留，而不是继续缩窗直到“跑过”。
- 插入-only owned 片段目前明确拒绝，不静默删除。
- 多段 target 索引不接受。大参考的单段索引可能需要很多内存；`--memory-gib`
  是地址空间上限，默认 10 GiB，不能据此假定小麦全参考可在该限制内运行。
- GRT Step1–Step4、Final Path 和原生 App 的最终等价性；客户小麦数据也尚未验证。

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
