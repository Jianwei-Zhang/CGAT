# Pinned post-LGZ tool recipes / 精修工具固定配方

The fixed recipe is summarized here; the lock is authoritative. The [consolidated validation](server-refinement-final-acceptance-20261122.md) records actual x86_64 and ARM64 installation, native runs, delivery and branch acceptance. These are synthetic workflow checks, not a tool ranking or biological benchmark.

## Installation and reproducibility

The machine-readable authority is `server/contracts/refinement-tools.lock.json`. All tools share `cgat-server`; there is no second refinement environment and no runtime download. `env.sh` installs the conda dependencies, installs the SHA-256-locked quarTeT source into that same prefix, and writes a verified runtime receipt. `install.sh --check` is read-only. A different executable found on PATH is not an accepted substitute.

| Tool | Fixed version/source | Distribution |
| --- | --- | --- |
| DEGAP | 2.0, commit `6cd01f1b983c43648e51389c129dfbd8b5926284` | Bundled source; original manifest and every source file checked |
| TGS-GapCloser | 1.2.1, upstream tag commit `52818b3e464209477baec506ade3240be43b4fa8` | Bioconda build 4 from the `1.2.1_ml` release variant, exact build and archive SHA-256 per architecture |
| quarTeT GapFiller | 1.3.1, commit `a44d8c87e3f4bcefaf43dc4134e88b6a21890265` | Pinned source archive plus the explicitly recorded Python 3.11 packaging patch below |
| LR_Gapcloser | 1.0, commit `156381adec01a5c664edbf5df1d866b5c70e82a1` | Exact noarch Bioconda package; uses the separately pinned native BWA for the current architecture |

The environment specifications additionally pin BWA 0.7.19, Racon 1.5.0, and the versions of DEGAP's Python/native dependencies. Exact conda builds and archive hashes are locked for TGS-GapCloser, LR_Gapcloser, BWA and Racon. Installed file hashes, resolved versions and builds are recorded and verified; they are not replaced by a version banner alone. Python 3.11 is retained. Available license files stay with the installed source distribution. The pinned DEGAP tree does not declare a LICENSE file; its lock entry explicitly records `NOASSERTION` rather than inventing a license grant.

For quarTeT, the upstream 1.3.1 gap-detail f-string uses quote reuse that Python 3.11 cannot parse. The lock declares one exact, before/after-SHA-bound quote substitution, `python311-fstring-quotes-v1`. It only changes quote spelling; it does not modify sequence processing, selection, thresholds or parameters. The patched source is **not described as byte-identical to upstream**. The actual Python 3.11 interpreter has loaded its GapFiller `--help` successfully in a temporary installation.

## Input and invocation recipes

- DEGAP receives the original typed HiFi/ONT inputs in one native mixed invocation. The pinned family recipe runs one bidirectional job per native gap, with one worker receiving the total thread budget. Its sealed junction and exterior flanks are checked before admission.
- TGS-GapCloser receives HiFi when both technologies are supplied, otherwise the supplied technology. HiFi uses `--ne`, `--tgstype pb` and the explicit `-x asm20` minimap2 preset. ONT uses the tool's own one-round Racon stage and `-x ava-ont`; this is recorded native processing, not an additional hidden correction pipeline.
- quarTeT receives both selected FASTA inputs in one GapFiller invocation, using minimap2 with the explicit upstream `-x asm5` preset. Experimental join mode stays off. `--noplot` avoids installing the unrelated plotting stack; native detail and modified AGP outputs remain required and available to the CGAT report.
- LR_Gapcloser receives HiFi when both are supplied, otherwise the supplied technology; it uses the native PacBio/ONT switch. Three iterations and one tag partition are explicit recipe settings. One partition prevents its background coverage jobs from exceeding a one-thread allocation. The upstream documentation's corrected-read recommendation does not become an extra CGAT input gate; no external correction step is inserted.

For FASTA-only recipes, FASTA/FASTQ, plain/gzip and wrapped records are detected from file content. The conversion does not trim, filter or correct bases. Stable converted IDs have a compressed mapping back to original input order and read IDs. Input files are never rewritten. Converted data are reused only with matching input bytes, conversion code/recipe and output hashes.

quarTeT keys some temporary alignment files by input **basename**, not full path. The conversion therefore creates distinct content-bound basenames; the command builder rejects colliding basenames instead of silently reusing the first technology's alignments for the second.

## Native output rules that adapters must retain

- DEGAP must provide both its gap-result JSON and its native integrated assembly. The assembly must contain the original chromosome set; it is indexed and summarized, but is not unconditionally adopted as CGAT's final result. A native exit code alone is insufficient.
- The exact locked TGS-GapCloser package was downloaded and hash-checked separately from the source tag. Its `1.2.1_ml` wrapper filters PAF rows using `qstart < 1000000 OR qlen - qstart < 1000000`. This is a native distribution behavior, not a CGAT-added filter. Some fatal argument checks in this wrapper return **0**: artifact validation is therefore mandatory even when the shell exits successfully. These distinctions are in the machine-readable recipe; the distribution is not presented as byte-identical to vanilla upstream 1.2.1.
- TGS-GapCloser provides `*.scaff_seqs`, `*.updated_scaff_infos`, `*.orignial_scaff_infos` (upstream spelling) , `*.name_map` and `*.gap_fill_detail` (singular, verified against the pinned writer). The adapter must use these real artifacts, not an assumed `gap_fill_details` filename.
- LR_Gapcloser can stop before iteration 3 when no gaps remain. An adapter must validate the last complete iteration and the early-stop condition; merely selecting the largest directory number is insufficient.
- quarTeT explicitly returns nonzero for “no gap can be closed” or no eligible gaps. These cases require a specific, evidence-backed native no-result classification. They must not be conflated with arbitrary process failure, nor turned into successful final results merely by copying LGZ.

The common private staging layer now classifies these special cases using native artifacts and sequence checks. Public `run_all.sh` uses the same classifications before publishing numbered Final Path, reports and App deliveries. Fixed recipes and format fixtures alone do not establish native acceptance.

## Initial investigation (historical)

This batch used small local installer/recipe/conversion checks and a controlled DEGAP adapter with real FASTA indexing. The source archive was downloaded and hash-checked; the temporary patched quarTeT entrypoint was checked with actual Python 3.11. No existing conda environment was upgraded during development.

Bioconda package records exist for the selected Linux x86_64/aarch64 native distributions, and the selected Python library versions have matching platform distributions (GNU parallel is noarch). That is **package availability**, not environment solve, native smoke, accuracy, performance or ARM64 acceptance. These were only the initial findings. The later consolidated validation supersedes this evidence with separate native install and tool receipts on both architectures.

Primary audit sources (immutable tool revisions or distribution archive hashes are in the lock):

- `https://github.com/Jianwei-Zhang/DEGAP`
- `https://github.com/BGI-Qingdao/TGS-GapCloser`
- `https://github.com/aaranyue/quarTeT`
- `https://github.com/CAFS-bioinformatics/LR_Gapcloser`
- `https://github.com/bioconda/bioconda-recipes/tree/master/recipes/tgsgapcloser`
- `https://github.com/bioconda/bioconda-recipes/tree/master/recipes/lr_gapcloser`
- Anaconda distribution records for the pinned Bioconda/conda-forge versions; exact native package URLs and SHA-256 values are in the lock.

---

## 中文摘要与边界

四工具已确定本轮固定配方，机器可读依据为 `server/contracts/refinement-tools.lock.json`。工具都进入同一 `cgat-server` 环境：TGS-GapCloser 与 LR_Gapcloser 使用锁定的 Bioconda 分发件，quarTeT 使用锁定源码加明确的 Python 3.11 引号兼容补丁，DEGAP 校验 bundled 源码。运行时不联网安装、不取 latest，也不接受 PATH 上另一版本静默替代。

HiFi/ONT 选择沿用设计：DEGAP 与 quarTeT 单次使用两类输入；TGS、LR 同时有两类时只用 HiFi。TGS 的 ONT 配方明确保留其原生 Racon 步骤，其他工具不额外插入纠错流水线。FASTA 派生转换保留原 reads 和可逆 ID 对照，quarTeT 的两个输入不得同 basename。

本轮还发现并记录了实际原生边界：LR 可能提前结束迭代；quarTeT 在无候选时会返回非零；TGS 的真实文件名不是假定的通用 gap-detail 名。后续公共执行/接纳层必须按这些证据处理，不能把失败统一包装成“成功但零填补”。

当前固定配方已接入公共入口、报告和 App 交付。两架构的环境、真实原生命令、路径来源和验收证据以统一验收文档为准。这里保留早期的原生边界调查，不用于判断工具优劣。

## Native adapters and explicit packaging patches (2026-11-21 update)

The three additional adapters now reconstruct native output from actual trace formats: TGS scaffold records plus singular `gap_fill_detail`; quarTeT modified AGP plus fill detail and selected input slices; LR per-iteration `info_filter2` plus the original converted read order. Each intermediate/native FASTA is checked against its trace. Edits are then projected onto the original LGZ Final Path, retaining uniquely unchanged internal islands and rejecting ambiguous provenance. These are private staged results, not public final deliveries yet.

Additional exact patches are part of the lock and recipe identity:

- **quarTeT `cgat.quartet.v2`:** besides the Python 3.11 f-string quote patch, GapFiller alone passes an explicit `allow_empty=True` to the minimap helper. A successful empty PAF now reaches the existing no-alignment branch, allowing the next selected input to be tried. A failed aligner is still an error. Other quarTeT callers keep the previous empty-PAF behavior. No nonempty alignment thresholds or candidate ranking are changed. All patch input/output hashes are locked.
- **LR `cgat.lrgapcloser.v3`:** CGAT copies the verified installed driver into the attempt's `02_jobs/native_driver.sh`, changing only helper-directory discovery to an explicit verified runtime directory. Upstream `/proc` matching can accidentally select any fd line whose log/workspace path contains `255`; the copied driver avoids that ambiguity. The original conda file is unchanged. Both driver hashes, the patch and its environment are recorded. The copied driver runs with shell `-e -o pipefail`; swallowed native command failures are not accepted as completion.

Known pinned behavior is not silently corrected: quarTeT numbers short N runs differently between gap detection and the final AGP writer. If this produces contradictory gap identities, admission rejects it instead of relocating a candidate. LR's reverse-strand partial-fill branch does not add the same synthetic 100-N prefix as its forward branch; the adapter reproduces and validates the actual native output rather than inventing a symmetric algorithm.

The read conversion recipe now writes a content-bound FASTA index and keeps UTF-8 original identifiers in the reversible map. Native lookup retains only requested IDs/ordinals, not every read sequence in memory. Each selected engine validates only its own pinned dependencies at execution time; environment install/check still validates all four engines.

At this historical implementation checkpoint, evidence remained deliberately lightweight: controlled format/sequence fixtures; the actual pinned TGS splitter/writer on a tiny supplied-fill example; the pinned LR sequence writer with tiny partial-fill rows; and Python 3.11 quarTeT with a controlled successful-empty aligner, confirming both inputs are attempted. The last example is **not** a real alignment test. A separate tiny driver test covers `255` in paths and altered-source rejection. None of these replaces end-to-end native runs, both-architecture environment checks or final Server/App acceptance.

中文补充（2026-11-21 当时状态）：新增三工具已接入内部原生执行、来源解析和待发布 Final Path；每工具依次执行、失败隔离，以及内容绑定的完整结果复用也已实现。尚未接入公共运行入口、最终报告和 App 交付。quarTeT 空 PAF 补丁、LR helper 路径补丁均明确锁定，不冒称原版字节不变。只复用已经验证的完整结果；原生子任务中断后的部分复用仍待实现。
