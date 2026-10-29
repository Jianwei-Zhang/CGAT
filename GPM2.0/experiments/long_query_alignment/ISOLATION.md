# Standalone query localization / 独立 query 定位

This opt-in diagnostic runs **unmodified minimap2**, not the CGAT pipeline.
It is not a production fallback or a validated parameter workaround. Keep the
original workspace and its partial PAF untouched. Do not import diagnostic PAFs.

## What it does

- Without `--execute`: validates paths/options and prints argv; creates no file,
  launches no minimap2 and submits no job.
- With `--execute`: requires a new output directory **outside** prepared Server
  workspaces, scans plain FASTA using bounded reads, validates IDs/IUPAC DNA,
  hashes input bytes, checks version and records executable SHA256.
- Runs exactly one `-c -x asm10 -t 1 --print-qname` diagnostic against the original
  target FASTA, retaining its order/default index partitioning. The single mapping
  thread is intentional for query attribution; it is not a speed/memory fix.
- Records QR/QT pairing, index-part number, exit status, limits, stderr and command.
  Only a well-formed active QR at the exact assertion can identify a candidate;
  the last completed query or the last partial PAF row never identifies it.
- Optional `--query-id ID`: scans the full original query file to detect duplicates
  and hash content, but copies **only that whole record** into the private output.
  Does not split/truncate the record or touch original `.fai` files. The reference
  is unchanged. A successful isolated replay cannot prove the full job succeeds.
- `--case eqx` / `--case no-long-join` require `--query-id` and a separate explicit
  invocation/new output. They are controlled contrasts, not auto retries. Both
  already fail on our 270 Mb synthetic CIGAR case; no benefit is promised.
- Overall timeout includes input scans. Child address-space and per-file limits,
  free-disk guard, disabled core dumps and process-group termination bound work.
  SIGTERM/KeyboardInterrupt preserve a report where possible; SIGKILL/node loss
  cannot guarantee final packaging. Failed/partial artifacts are retained.
- `diagnostics.tar.gz` uses an allowlist: command, report, input identities/lengths
  and logs only. **No FASTA, PAF, binary or core dump is included.** Paths and IDs
  remain in logs; review before sending. No upload occurs automatically.

Python 3.10+ on Linux; standard library only. `--memory-gib` is an address-space
cap, **not** a Slurm request or an RSS prediction. It can itself cause allocation
failure: distinguish that from the original assertion. Reserve scheduler memory
separately and leave headroom. Inputs and binaries must not change during a run.
Pre-run content hashes and before/after stat checks are recorded; an after-run
full content rehash is not performed. Source fingerprints do not replace a snapshot.

## Operator commands

First activate the same trusted Server environment used by the failed job. Set
absolute paths; `OUT` must be a new sibling diagnostic directory, not inside the
prepared workspace. The following only **previews**, even on a login node:

```bash
python3 isolate_minimap2.py \
  --minimap2 /absolute/path/to/cgat/bin/minimap2 \
  --ref /absolute/path/to/workspace/data/reference/genome.filled.fa \
  --query /absolute/path/to/workspace/data/datasets/assembly.fa \
  --out /absolute/path/to/new-isolation-directory \
  --timeout-seconds 21600 --memory-gib 400
```

Review the plan and resource budget. **Only in an explicitly submitted compute
job**, append `--execute`. For a 500 GB allocation, 400 GiB address-space cap is an
initial diagnostic bound, not a guarantee of fit or completion. No job is submitted
by this tool. Input scanning reads both complete FASTAs; for a wheat pair that can
mean roughly 30 GB of I/O before mapping. A single mapping thread may take hours.
The default version check is exactly `2.31-r1302`; do not bypass a mismatch blindly.

After completion, send `diagnostics.tar.gz` plus the printed archive SHA256.
Tool exit zero means **diagnostic collection completed**, including captured
assertions/timeouts; examine `outcome`, `execution` and `trace`. It never means a
workaround or biological result passed. Setup/input errors exit 2 where recorded.

If a candidate was identified, independently replay it in another new directory:

```bash
# Same options/target as above; new OUT; explicit compute job, not login node.
python3 isolate_minimap2.py ... --query-id EXACT_ID --case locate --execute
```

If the assertion does not recur, retain that result; do not declare a fix or delete
other records from production. If it recurs, evaluate selected contrasts separately
and validate PAF/candidate/downstream equivalence before considering integration.
Do not reduce `-I`, increase `-I` to a full wheat index, add `--split-prefix`, remove
`-c`, or skip queries as an automatic reaction. Index/MAPQ correctness and the
assertion are separate questions. Full-target changes need their own resource and
scientific validation. No customer sequence is included in this repository.

## 中文操作说明

这是**独立定位工具，不是修复版 Server**。默认只显示命令；加 `--execute`
才会读完整 FASTA 并启动一次受限诊断。不要在登录节点执行比对。

1. 原工作区、原 FASTA、失败日志和不完整 PAF 全部保留。
2. 先检查预览，再在学校计算作业中运行；输出必须是工作区外的新目录。
3. 单线程配合 query 开始/完成标记定位，不从“mapped 6”或最后一条 PAF 猜测。
4. 发回 `diagnostics.tar.gz` 和打印的 SHA256，不需要发 FASTA/PAF/core。
5. 定位到 ID 后，另开新诊断目录，仅提取该整条 query、保持原参考不变重放。
6. 超时、内存上限退出、未复现都不是修复成功；参数对照不自动连续运行。

脚本返回 0 仅表示诊断收集完成；判断结果看 `outcome` 与子进程退出码。
工具不下载/安装依赖、不提交作业、不上传数据、不修改 minimap2，也不产生可导入的
正式结果。已有参数审计显示，`--eqx`、缩小批次、调整 long-join/带宽等没有解决
受控长 CIGAR 反例；`--max-qlen` 跳过数据更不能当作修复。
