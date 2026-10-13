# Skill v3: WSL, SSH 140-1 and SSH 180 test record

Date: 2026-10-13. Tested skill source: `fdf195a4df35d34f5f60ceb6457a3bbe8c2d4157`.
This is **the current main agent following the skill**, not a fresh Pi/subagent
behavior test. Pi was not installed on remote hosts; no additional agent/software
was installed. Raw local notes were not uploaded or copied into this repository.

## Results and boundaries

| Target | Official online update | Verified offline update | Tiny fresh/resume pipeline | Local experience preserved |
| --- | --- | --- | --- | --- |
| WSL x86_64 | Check/download/stage passed; test-only activation | Not needed | Both exit 0, 12/12 stages | Byte-identical retired synthetic fixture; no new routine-success lesson |
| 140-1 x86_64 | Direct official HTTPS read timed out; helper exit 2, no activation | Exact WSL-verified official archive transferred by SSH and SHA-256 checked; test-only activation | LSF `75780718` / `75781263`, both DONE; runner exit 0, 12/12 stages | Verified missing-Python-PATH lesson retained; no duplicate |
| 180 aarch64 | Direct official HTTPS read timed out; helper exit 2, no activation | Same verified transfer and offline preparation; test-only activation | Donau `40531309` / `40531317`, both SUCCEEDED; runner exit 0, 12/12 stages | Controlled module/appdir failure lesson retained; no duplicate |

Online failure on either remote is **not** counted as online success. No proxy,
routing, authentication or shell-startup configuration was changed to force access.
Offline testing was an explicit transfer inside the agreed three-host test scope,
not an automatic fallback inside the updater. The remote network root cause was
not established or repaired, so no “network fixed” lesson was recorded.

The 140-1 resume interactive `bsub -Is` client returned **255**, while scheduler
status was DONE and the runner's recorded exit was 0. Current report/run identity,
all 12 stage results and both archives were independently checked. No duplicate
job was submitted to get a green client status. The underlying interactive-client
exit discrepancy remains uncorrected and is not treated as a verified repair.

## Data, resources and evidence

Each generated FASTA has two 60,000-base sequences. Reference + primary + support
use under 400 KB in total, no reads, deterministic seed 20261013. All three hosts'
input SHA-256 values match. No production genomes were used. WSL used 4 threads;
remote jobs requested 2 CPU cores with 900-second process caps. On 140-1, compute
ran on gpu02 CPU resources in the interactive queue; on 180, agent-ARM-11 in arm
with `-aa`. Preparation and computation were not run on login nodes. Networked
retrieval/staging and lightweight metadata validation used login nodes.

Existing environments were reused: WSL `cgat-server` (managed check passed),
140-1 `GRT` (runtime evidence, not managed-installer READY), 180 site ARM modules
(runtime evidence, not installer-spec parity). No environment installation/update.

All resumes show five `SKIP_VALID` and four `CACHE_HIT` log events. Both final
archives were read through gzip EOF/CRC, SHA-256 compared with recorded delivery
summaries, paths inspected, and embedded reports checked against the latest run.
Full has 10 FASTA files; Light has none. The companion tools are the same official
stable v2.0.10 asset ID `636332952`, SHA-256
`28cf865759cf62928967390ea41048d321334deca6021ff2942d12ef7227c677`;
skill v3 is separately pinned to the official repository commit above.

Machine-readable run IDs, hashes, archive sizes and source identities are in
`agent-skill-v3-three-hosts.json`. No scientific-quality, reads-QC, native App
visual/import, or independent fresh-agent adherence claim is made.

## Retained test roots

- WSL: `/home/xbzhang/projects/gpm-server-skill-v3-test-20261013-fdf195a/`
- 140-1: `~/gpm-skill-smoke/20261013-v3-fdf195a/`
- 180: `~/cgat-reads-debug/skill-v3-20261013-fdf195a/`

Each retains source, active project-only/standalone test skill, old skill outside
discovery, local notes, verified downloads, jobs, logs, reports and synthetic runs.
Historical v1/Pi test roots remain untouched. No global skill, existing run,
production installation, key or Release asset was modified by this revision.
