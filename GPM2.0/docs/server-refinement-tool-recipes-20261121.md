# Pinned post-LGZ tool recipes / 精修工具固定配方

This is an implementation record, not a claim that the four-tool workflow or either architecture has passed acceptance. The complete acceptance criteria remain in `server-post-lgz-refinement-design-20261121.md`.

## Installation and reproducibility

The machine-readable authority is `server/contracts/refinement-tools.lock.json`. All tools share `cgat-server`; there is no second refinement environment and no runtime download. `env.sh` installs the conda dependencies, installs the SHA-256-locked quarTeT source into that same prefix, and writes a verified runtime receipt. `install.sh --check` is read-only. A different executable found on PATH is not an accepted substitute.

| Tool | Fixed version/source | Distribution |
| --- | --- | --- |
| DEGAP | 2.0, commit `0b3c9bc7acc5bd290ad2b23d53cc57815f1c7e75` | Bundled source; original manifest and every source file checked |
| TGS-GapCloser | 1.2.1, upstream tag commit `52818b3e464209477baec506ade3240be43b4fa8` | Bioconda build 4, exact build and archive SHA-256 per architecture; includes distribution patches |
| quarTeT GapFiller | 1.3.1, commit `a44d8c87e3f4bcefaf43dc4134e88b6a21890265` | Pinned source archive plus the explicitly recorded Python 3.11 packaging patch below |
| LR_Gapcloser | 1.0, commit `156381adec01a5c664edbf5df1d866b5c70e82a1` | Exact noarch Bioconda package; uses the separately pinned native BWA for the current architecture |

The environment specifications additionally pin BWA 0.7.19, Racon 1.5.0, and the versions of DEGAP's Python/native dependencies. Exact conda builds and archive hashes are locked for TGS-GapCloser, LR_Gapcloser, BWA and Racon. Installed file hashes, resolved versions and builds are recorded and verified; they are not replaced by a version banner alone. Python 3.11 is retained. Available license files stay with the installed source distribution. The pinned DEGAP tree does not declare a LICENSE file; its lock entry explicitly records `NOASSERTION` rather than inventing a license grant.

For quarTeT, the upstream 1.3.1 gap-detail f-string uses quote reuse that Python 3.11 cannot parse. The lock declares one exact, before/after-SHA-bound quote substitution, `python311-fstring-quotes-v1`. It only changes quote spelling; it does not modify sequence processing, selection, thresholds or parameters. The patched source is **not described as byte-identical to upstream**. The actual Python 3.11 interpreter has loaded its GapFiller `--help` successfully in a temporary installation.

## Input and invocation recipes

- DEGAP receives the original typed HiFi/ONT inputs in one native mixed invocation. Its native per-gap worker count is 1; that worker receives the total thread budget.
- TGS-GapCloser receives HiFi when both technologies are supplied, otherwise the supplied technology. HiFi uses `--ne`, `--tgstype pb` and the explicit `-x asm20` minimap2 preset. ONT uses the tool's own one-round Racon stage and `-x ava-ont`; this is recorded native processing, not an additional hidden correction pipeline.
- quarTeT receives both selected FASTA inputs in one GapFiller invocation, using minimap2 with the explicit upstream `-x asm5` preset. Experimental join mode stays off. `--noplot` avoids installing the unrelated plotting stack; native detail and modified AGP outputs remain required and available to the CGAT report.
- LR_Gapcloser receives HiFi when both are supplied, otherwise the supplied technology; it uses the native PacBio/ONT switch. Three iterations and one tag partition are explicit recipe settings. One partition prevents its background coverage jobs from exceeding a one-thread allocation. The upstream documentation's corrected-read recommendation does not become an extra CGAT input gate; no external correction step is inserted.

For FASTA-only recipes, FASTA/FASTQ, plain/gzip and wrapped records are detected from file content. The conversion does not trim, filter or correct bases. Stable converted IDs have a compressed mapping back to original input order and read IDs. Input files are never rewritten. Converted data are reused only with matching input bytes, conversion code/recipe and output hashes.

quarTeT keys some temporary alignment files by input **basename**, not full path. The conversion therefore creates distinct content-bound basenames; the command builder rejects colliding basenames instead of silently reusing the first technology's alignments for the second.

## Native output rules that adapters must retain

- DEGAP must provide both its gap-result JSON and its native integrated assembly. The assembly must contain the original chromosome set; it is indexed and summarized, but is not unconditionally adopted as CGAT's final result. A native exit code alone is insufficient.
- TGS-GapCloser provides `*.scaff_seqs`, `*.updated_scaff_infos`, `*.orignial_scaff_infos` (upstream spelling) and `*.name_map`. The adapter must use these real artifacts, not an assumed `gap_fill_details` filename.
- LR_Gapcloser can stop before iteration 3 when no gaps remain. An adapter must validate the last complete iteration and the early-stop condition; merely selecting the largest directory number is insufficient.
- quarTeT explicitly returns nonzero for “no gap can be closed” or no eligible gaps. These cases require a specific, evidence-backed native no-result classification. They must not be conflated with arbitrary process failure, nor turned into successful final results merely by copying LGZ.

The latter two special cases still need integration in the common native execution/admission layer. The fixed command recipes alone do not establish successful native execution or accepted refinement.

## Evidence and remaining gates

This batch used small local installer/recipe/conversion checks and a controlled DEGAP adapter with real FASTA indexing. The source archive was downloaded and hash-checked; the temporary patched quarTeT entrypoint was checked with actual Python 3.11. No existing conda environment was upgraded during development.

Bioconda package records exist for the selected Linux x86_64/aarch64 native distributions, and the selected Python library versions have matching platform distributions (GNU parallel is noarch). That is **package availability**, not environment solve, native smoke, accuracy, performance or ARM64 acceptance. Both lock-file platform validation fields remain pending. Complete shared-environment resolution and native small examples are deferred to the final consolidated validation.

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

当前完成的是固定环境定义、安装/校验代码、命令与输入配方，以及 DEGAP 原生输出的进一步完整性检查。没有在开发中升级真实环境，也未宣称四工具真实 reads、完整共同入口或 ARM64 已验收。最终仍须统一进行环境求解、原生小样例、路径来源、报告与 App 的完整验收。
