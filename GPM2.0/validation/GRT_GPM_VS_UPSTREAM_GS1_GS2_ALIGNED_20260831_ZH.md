# GPM-GRT 与原版 GRT 对齐验证：gs1/gs2（2026-08-31）

## 结论

本次修改已把 GPM-GRT 的 Stage1–3 主要执行语义对齐到原版 `Genome-Repair-Tools`，同时保留一条必要的自动结构编辑安全边界。

| 项目 | 对照范围 | 最终结果 |
| --- | --- | --- |
| gs1 | q0 的 12 个 gap；原版最终保留下来的 12 条染色体 | 12/12 个 gap 终态一致，12/12 条染色体逐碱基一致 |
| gs2 | q0 的 1 个 gap；5 条染色体 | 4/5 条染色体逐碱基一致；唯一 gap 均未填补，但 GPM 有意拒绝原版的大范围删除 |

因此，13 个测试 gap 中：

- 12 个达到严格的最终序列一致，全部来自 gs1；
- 1 个是明确、可审计的安全差异，来自 gs2；
- 不再存在旧基线中的 4 个 `result_mismatch` 和 5 个“终态相同但序列不同”的 gs1 gap。

完整逐 gap 结果见 [grt_gap_comparison_gs1_gs2_aligned_20260831.tsv](grt_gap_comparison_gs1_gs2_aligned_20260831.tsv)。旧的未对齐报告和 TSV 保留不变，作为修改前基线。

## 对齐边界

输入及公平比较边界沿用修改前测试：

- `D:\Desktop\gs1_lvzao .zip`，SHA-256 `c029cc26ee398318a8e9b055e6d2b42fe6a563e7984019fc6426a35d9d5bc61f`；
- `D:\Desktop\gs2_ara.zip`，SHA-256 `dafe14cfcc4c8713dbeb2bbd3728af2a0766765b89d87d1f479168df0b13bb91`；
- gs1 D0：111 个成员，FASTA SHA-256 `9f72de7f2e99cfbb480ab9a92189c9496c6031dfaf010008484f9711ecd8ef05`；
- gs2 D0：69 个成员，FASTA SHA-256 `baba8cfcd51f328d4397f103523d0b2001e262873653542075c08591cf1e05e1`；
- 原版 GRT commit：`975848d08b629ab3ce8d8ef5d0006e0479dfd75a`；
- GPM Step2/3 engine version：`9`，本次运行脚本 SHA-256 `44645c3fb774c4dc65f4c320d7457257fec4b18dff467704d3867c3123a135ee`；
- Python 3.11、samtools 1.23.1、minimap2 2.31-r1302、MUMmer/nucmer 4.0.1，10 threads。

原版使用同一份 GPM q0 和冻结 D0，执行 Stage1–4 aggressive 流程。比较最终序列时，对原版 fragment filter 添加的 `_filtered_...` FASTA header 后缀做名称归一化，不改变序列。

## 已对齐的执行语义

1. 外部 contig、无 reads 时，Stage1 仍显式产生 q0→q0r1→q0f→q1 的 identity 事件，而不是调用 GPM 自己的填补器。
2. Stage2 按原版 PatchRepair controller 处理：首个直接 patch 不可用时，对整条染色体运行结构 fixer；结构修正发生在后续 refill/filter 之前。
3. MUMmer 目标按原版拆分：`>=1 Mb` 记录逐条比对，较小记录按长度降序组成 `<=10 Mb` 分区。
4. 原版命令 `delta-filter -i -r -l 10000` 的实际效果是不启用 reference-best 过滤；GPM 用明确的 `delta-filter -l 10000` 表达同一效果，保留所有 `>=10 kb` repeat hit。
5. 可执行左右 anchor 必须来自同一 D0 record；直接 patch 优先最短的已验证 target span，结构候选优先更大的 `ref_overlap_N`。
6. Stage3 以普通 D0 为结构比对目标，按“结构修正→refill round1→component filter→refill round2”的原版顺序执行。
7. Type5 投影、100 kb 递增搜索窗、500 kb 上限、gap midpoint 和负链边界行为均按原版实际代码校准。

## gs1：严格最终一致

### 分阶段结果

| q 版本 | 染色体数 | 总长度 (bp) | `N{100,}` gap 数 | FASTA SHA-256 |
| --- | ---: | ---: | ---: | --- |
| q0 / q0r1 / q0f / q1 | 22 | 51,700,178 | 12 | `f887e50f4771df58aea9c1bb5f8f1143a6963a0461b040838438766523bae674` |
| q2 | 22 | 51,437,991 | 10 | `68333b73aeec9a57ae9c6ee1ccf3d14cf34c6aa78c782bad9ca1bc77f27ec85a` |
| q3 / q4 | 22 | 51,176,466 | 2 | `15c9e653f2e13ffe679f3bbecaaac95b820515d4264d6ed5f19284cc71926b22` |

原版 Stage2 的 12 条染色体中，GPM q2 有 10 条逐碱基一致；Chr8 和 Chr18 的中间选择不同。经过原版顺序的 Step3 refill/filter 后，12 条全部收敛为逐碱基一致：

| 最终 gap | GPM / 原版共同坐标 |
| --- | --- |
| Chr2 | `1417647-1417746` |
| Chr16 | `2094265-2094364` |

原版 Stage2 合并仍有既有的染色体名前缀误判，只输出 12 条染色体；GPM 正确保留 22 条。因此全文件 FASTA hash 不应直接比较。对原版实际输出的 12 条逐记录比较，长度、gap 坐标和 sequence SHA-256 全部一致。

### 完整工作流与契约

- run ID：`20260831T120533Z-1506563-42cda35e`；32/32 单元成功；
- Step2：12 gaps、89 candidates；1 个直接 patch，9 个结构删除被接受；
- Step3：8 个结构修正、3 个 refill，之后保留 2 个 gap；
- Final Path：34 segments（28 source、4 patch、2 gap）；
- contract：146 events、285 evidence、34 segments，q4 重建通过。

## gs2：保留一条安全差异

gs2 的 q0、q0r1、q0f、q1、q2、q3、q4 均为：

- 5 条染色体；
- 134,184,023 bp；
- 1 个 gap；
- FASTA SHA-256 `f6bd0ae940e12e79440377856912dcd5ef50e21ccdfacd7fd98f509218291029`。

原版对 `GWHBDNP00000004.1:371442-371541` 执行：

- Stage2 Type5 删除 101,382 bp；
- Stage3 Type1 再替换 4,687 bp；
- 最终仍保留 100N，但坐标移至 `366855-366954`；
- 最终 Chr4 净减少 105,918 bp。

GPM 检测到同一 Type5 候选及 `ref_overlap_10576`，但 101,382 bp 编辑超过 100 kb，且大于证据长度的 5 倍，因此以 `automatic_edit_exceeds_overlap_evidence` 拒绝。事件状态为 `unresolved`，q2→q3 没有 edit；Final Path 保留原始 100N。

这不是未对齐遗漏，而是有意安全边界：不能让约 10.6 kb 的 overlap 证据自动授权约 101.4 kb 的结构删除。其余 4 条 gs2 染色体与原版逐碱基一致。

### 完整工作流与契约

- run ID：`20260831T122925Z-1515099-143f1310`；15/15 单元成功；
- Step2：1 gap、7 candidates、0 accepted；
- Step3：1 个 Type5 候选因 edit/evidence 比例拒绝，0 correction、0 refill；
- Final Path：7 segments（6 source、1 gap）；
- contract：18 events、35 evidence、7 segments，q4 重建通过。

## 新交付包

未覆盖用户原 ZIP。4 个新包均通过 `unzip -tq`：

| 包 | 大小 | SHA-256 |
| --- | ---: | --- |
| `D:\Desktop\gs1_lvzao_gpm_server_aligned_20260831.zip` | 102.5 MB | `f69270eabd51f447ea21aa1ea8da7eb600c956325fb8373a9695d735f50f6cf9` |
| `D:\Desktop\gs1_lvzao_gpm_server_aligned_20260831.no_fasta.zip` | 4.5 MB | `f1b8c3e8dcb065da63a97c9ef3f704afd98f34903cd9c0431cee1f77f5b9aa06` |
| `D:\Desktop\gs2_ara_gpm_server_aligned_20260831.zip` | 266.9 MB | `3e8b3a44c45444c7c24c69ff3786c663c0841af40991e2d4b527c643a71474dd` |
| `D:\Desktop\gs2_ara_gpm_server_aligned_20260831.no_fasta.zip` | 28.6 MB | `e0cdce68a1d8a8b8c54653bca20d27306d2c83b6b98e5f729150a0a788598ef1` |

## 最终判断

GPM-GRT 现在可以把原版的正常 gap 修复语义作为兼容基线：gs1 的所有测试 gap 和原版最终序列严格一致；同类行为已有单元测试覆盖。对于原版可能由局部 overlap 触发的大范围结构删除，GPM 不盲目复刻，而是保留可解释、可回归、可审计的 100 kb / 5× evidence 安全护栏。
