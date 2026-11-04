# Server cen / tel 官方库与本地库设计

日期：2026-11-04

状态：已按用户授权推进源码实施和 v1 数据整理；测试与统一 review 由用户后续安排，尚未发布。本文不授权替换官方 Release 资产或修改已有用户工作区。具体来源和静态检查边界见第 12 节。

## 1. 目标

- Server 提供 tel 和 cen 官方库，`prepare` 自动使用库中的检查信息。
- 用户可维护自己的本地库。
- 运行时可以显式传入 `--tel`、`--cen` 补充本次信息。
- 官方库更新不能修改用户本地库。
- 已准备的项目不能因为 Server 或官方库更新而悄悄改变检查依据。

## 2. 实施前基线（兼容性对照）

- `--tel <motif> <min_repeat>` 可重复传入，`prepare.sh` 将其写入 `tel/rules.tsv`。
- `--cen` 只能传入一次 FASTA。当前实现要求序列名为 `<chr>_centromere`，染色体名必须存在于本次参考中，并按染色体使用对应序列扫描 assembly。
- `--cen-min-len` 和 `--cen-min-identity` 用于过滤 cen 比对。
- 当前 `--cen` 语义接近“与参考染色体对应的完整着丝粒序列”，新方案将改变这一语义。

## 3. 核心规则

本次实际使用的信息为：

```text
官方库 + 用户本地库 + 本次显式参数
```

- 未传 `--tel` / `--cen`：使用官方库和本地库。
- 显式传 `--tel` / `--cen`：追加到库信息上，不覆盖库。
- 本次参数只用于本次运行，不自动写入本地库。
- 第一版不支持停用官方条目；官方条目错误通过官方更新修正。

## 4. 库结构

```text
<Server tools>/
├── library/                 # 官方库，随 update.sh 更新
│   ├── tel.tsv
│   └── cen/
│       ├── cen.tsv
│       └── <id>.fa
└── local/library/           # 用户本地库，Server 更新不触碰
    ├── tel.tsv
    └── cen/
        ├── cen.tsv
        └── <id>.fa
```

- 官方库与本地库使用相同格式。
- 官方更新只修改 `library/`。
- 用户管理命令只修改 `local/library/`。

## 5. tel

### 5.1 库格式

```text
id    motif    min_repeat    note
```

- `note` 用于记录依据或说明，允许为空。
- `note` 不参与检测、去重或判定。

### 5.2 合并规则

```text
有效 tel 规则 = 官方 tel + 本地 tel + 本次 --tel
```

- `motif` 和 `min_repeat` 相同的规则只计算一次。
- 合并时保留全部条目的来源和 `note`。
- 结果保留命中所依据的规则和来源。
- 每条规则自动扫描正反两条链，库中不需要单独写反向互补 motif。

### 5.3 阈值含义

每条规则只保留一个 `min_repeat`，表示“至少连续多少个 motif 才算端粒样命中”。

- `prepare` 端粒标记：直接使用 `min_repeat`。
- GRT 末端检查：使用 `min_repeat`，范围仍为染色体两端 2,000 bp。
- GRT 供体检查：使用 `min_repeat`，同时保留现有总长度至少 500 bp 的要求。

现有 GRT 默认值为末端 5 个、供体 20 个；由于供体还要求至少 500 bp，7 bp 以内的 motif 在供体检查中实际由 500 bp 决定。因此官方条目采用 `min_repeat = 5` 时，原有 TTTAGGG / TTAGGG 规则的阈值语义不变；新增 TTAGG 会有意扩大默认识别范围，不能称为所有判定结果完全不变。新项目由库生成规则，GRT 内置默认值仅为无快照的旧项目保留。

## 6. cen

### 6.1 生物学语义

着丝粒的功能位置通常在单着丝粒染色体上是唯一的，但其序列组成常为多条染色体共享的卫星重复或转座子。因此，cen 库不用于证明某段序列属于哪条参考染色体。

第一版将 cen 库定义为“着丝粒相关重复序列”，检测结果统一称为“着丝粒候选区域”，不称为“完整参考着丝粒”或“确定的功能着丝粒”。

### 6.2 库格式

```text
cen.tsv: id    note
<id>.fa: cen 序列
```

- `note` 用于记录依据或说明，允许为空。
- `note` 不参与检测、去重或判定。
- FASTA 序列名不再承载染色体归属语义。

### 6.3 合并与检测

```text
有效 cen 序列 = 官方 cen + 本地 cen + 本次 --cen
```

- 不需要 `ref.fa`。
- 不要求序列名为 `<chr>_centromere`。
- 不通过染色体名、序列指纹或相似度推断 cen 条目归属。
- 将全部有效 cen 序列在每条染色体对应的 assembly 中搜索，不按物种或参考染色体推断归属。
- 相同序列只计算一次，但保留全部来源和 `note`。

判定流程：

```text
cen 序列命中
→ 合并相邻命中
→ 按区域总长度筛选
→ 输出着丝粒候选区域
```

- `--cen-min-identity` 判断单个命中是否可信。
- `--cen-min-len` 判断合并后实际命中覆盖的总长度是否足够长；重叠只计一次，间隔不计为支持长度。
- 两个阈值统一作用于官方库、本地库和本次 `--cen`。
- 相邻命中的最大间隔第一版采用固定内部值 200 bp，不开放参数；该值为待统一真实数据验收的暂定策略，不能视为已验证的生物学边界。

## 7. 用户管理命令

```bash
bash "$SERVER/library.sh" list
bash "$SERVER/library.sh" list tel
bash "$SERVER/library.sh" list cen

bash "$SERVER/library.sh" add-tel <motif> <min_repeat> [--note <text>]
bash "$SERVER/library.sh" add-cen <cen.fa> [--note <text>]

bash "$SERVER/library.sh" remove <id>
```

- `list` 显示条目、类型、来源和 `note`。
- `add-*` 只写入本地库，并在写入前校验。
- `remove` 只能删除本地条目；删除官方条目时报错。
- 修改本地条目时先 `remove`，再重新 `add`。

## 8. 项目快照

`prepare` 将本次实际使用的库条目和参数复制到项目内，并记录：

```text
来源：官方 / 本地 / 本次参数
条目 ID
内容 SHA-256
note
```

- 后续运行和续跑只使用项目内快照。
- Server 或官方库更新后，已准备项目保持原检查依据。
- 采用新库需要明确重新 prepare（也可使用新输出目录）；直接恢复运行不重新读取安装库。
- 新项目同时保存三个检测输入文件的 SHA-256；加载前校验，拒绝被改写或部分生成的快照。旧项目无快照时继续使用原项目已有输入，不自动补入当前官方库。

## 9. 兼容性

- `--tel` 用法不变，但改为追加到库规则上。
- `--cen` 仍传 FASTA，但语义改为“着丝粒相关序列”。
- 旧 `<chr>_centromere` FASTA 仍可读取，但染色体名不参与判定。
- 报告和 App 中的 cen 表述改为“着丝粒候选区域”，并显示命中条目及来源。

## 10. 官方库 v1

### 10.1 收录原则

- 只收录最常见、证据明确的条目；少见类群由用户放入本地库。
- 每个条目必须能追溯到可复核的数据库、论文或公开数据，依据写入 `note`。
- 区分实验证据与计算预测；v1 不收录仅由计算预测得到的重复家族；序列来源与重复家族的功能证据分开记录，不将家族级证据误称为每个拷贝的实验认证。
- tel 只收录 motif 和阈值这类事实信息，引用原始文献，不复制 TeloBase 数据库内容。
- cen 序列来自 GenBank/ENA 等公开记录或论文补充材料，使用固定 accession.version 与提取坐标，核对原记录序列长度和 MD5；分发文件及提取序列另记 SHA-256。已选记录见 `server/library/cen/sources.json`。

### 10.2 tel

| id | motif | min_repeat | 适用范围 | 依据（已核对记录） |
| --- | --- | ---: | --- | --- |
| `tel_plant_TTTAGGG` | `TTTAGGG` | 5 | 多数陆地植物（拟南芥型） | Richards & Ausubel, Cell 1988 |
| `tel_vertebrate_TTAGGG` | `TTAGGG` | 5 | 脊椎动物及多种真核生物 | Moyzis et al., PNAS 1988 |
| `tel_arthropod_TTAGG` | `TTAGG` | 5 | 多数节肢动物/昆虫 | Okazaki et al., MCB 1993；Sahara et al., Chromosome Res 1999 |

不进入 v1：衣藻型 `TTTTAGGG`、葱属、茄科夜香树属等特殊类群，以及双翅目中由转座子维持端粒的物种。

### 10.3 cen

| id | 条目 | 单体长度 | 物种 | 依据（已核对记录） |
| --- | --- | ---: | --- | --- |
| `cen_arabidopsis_CEN180` | CEN180 | 约 178 bp | 拟南芥 | Naish et al., Science 2021 |
| `cen_rice_CentO` | CentO | 约 155 bp | 水稻 | Cheng et al., Plant Cell 2002 |
| `cen_maize_CentC` | CentC-154b | 154 bp | 玉米 | AF078919.1；Ananiev et al., PNAS 1998 |
| `cen_human_alpha` | α-satellite | 约 171 bp | 人 | Altemose et al., Science 2022 |

- 每个条目收录一个代表性重复单位或重复单位长度窗口，并在 `note` 中写明来源记录、长度和家族级功能证据；不冒称共识序列或已准确注释的单体边界。
- v1 暂不覆盖小麦等其他类群；这只是本次数据范围，不表示这些物种不存在卫星重复或其他着丝粒序列。
- cen 卫星序列种属特异性强；未命中可能来自库覆盖不足、序列分化、组装缺失或检测灵敏度限制，不表示没有着丝粒。

### 10.4 实施前需验证

- cen 单体在全基因组中有大量拷贝。源码改为 MUMmer4 `nucmer --maxmatch --nosimplify`，以短重复库为 reference、assembly 为 query，保留重复种子和多重命中；真实数据灵敏度与资源用量待验收。
- 端粒扫描已从逐字符 Python 循环改为正则迭代。官方库默认启用后，整体扫描耗时与标记数量仍需统一真实数据验收。
- `min_repeat = 5` 会标出更多染色体内部端粒样重复；需用测试数据确认显示密度是否可接受。

## 11. 实施验收

- 只用库时，tel 和 cen 自动生效。
- 库与显式参数正确合并。
- 官方库更新后，本地库字节不变。
- Server 更新后，已准备项目仍使用原快照。
- 不能删除官方条目。
- 短重复序列的相邻命中能正确合并为候选区域。
- 结果中显示命中条目及来源。
- 对原有 TTTAGGG / TTAGGG 规则，GRT 末端和供体阈值语义不退化；TTAGG 扩展范围符合设计。

## 12. 源码实施与验收交接

本轮已获得用户“推进实施，可以跳过测试，最后统一 review 与测试”的授权。

- `server/library.sh`：列出库条目、添加本地 tel/cen、移除本地条目；note 可空。管理命令不会修改官方库。
- `tools/annotation_library.py`：输入校验、相同规则/序列去重、全部来源保留、项目内容快照与校验。本次参数不写回本地库。
- `prepare.sh`：默认启用两层库并叠加参数；cen 不依赖 `ref.fa` 的染色体命名。
- `tools/cen_scan.py`：全库扫描、按 identity 过滤单个命中、跨条目/双链合并；覆盖长度去重后与 min-len 比较。`region_length` 是区域跨度，`align_length` 是实际命中覆盖；identity 为命中比对长度的加权均值，不是含间隔整段的一致性；混合链区域的 strand 为命中比对长度加权支持更多的一侧，MUMmer 无 MAPQ 因而写 0。
- 续跑依赖包含项目快照、cen FASTA、扫描模块与使用的 MUMmer 工具；代码更新不写项目库输入，旧项目不会自动加入新库。
- 更新器显式拒绝拥有 `local/` 文件的官方源 manifest，保留安装目录的本地内容。
- App 导入保留标记来源 JSON，工作区 schema 6→7 添加默认空来源列；老包缺失来源列时按空列表读取。该 schema 升级后应使用支持 schema 7 的 App，不承诺旧版 App 能重新打开。
- 报告和 App 使用“着丝粒候选区域”表述，标记详情可追溯来源和 note；两种交付均带来源快照；完整交付含 cen 库 FASTA，轻量交付继续排除所有 FASTA，避免夹带本地私有序列。

### 12.1 v1 实际 cen 来源

| 条目 | 记录和 1-based inclusive 范围 | 实际长度 | 说明 |
| --- | --- | ---: | --- |
| CEN180 / At178 | EU359509.1:181–358 | 178 bp | Zhang 2008 串联重复记录中的代表窗口 |
| CentO / RCS2 | AF058902.1:160–314 | 155 bp | Dong 1998 串联重复记录中的代表窗口；Cheng 2002 提供家族定位证据 |
| CentC-154b | AF078919.1:1–154 | 154 bp | 已核对原记录，修正早期概述中约 156 bp 的泛称 |
| human alpha-R1-9 | X13647.1:1–171 | 171 bp | 一个 α-satellite 亚家族单体，不代表所有人类染色体 |

`server/library/SOURCES.md` 记录来源、公共数据使用政策及证据边界；没有打包论文正文或 TeloBase 数据库。

### 12.2 本轮验证边界

按用户要求，不运行单元/集成测试、真实基因组计算、App 构建或浏览器测试。
已执行的静态检查：14 个 Python 文件及嵌入扫描脚本 AST、3 个 shell 文件语法、8 个 Rust 文件格式/解析、Windows Node 对 3 个 JS/MJS 文件的语法检查、Git diff 检查。库数据生成时已核对来源序列长度/MD5，并复核 4 个 cen FASTA 与来源 manifest 的 SHA-256。以上不包含 Rust 类型编译或任何运行测试。
新增和调整的测试源文件供之后统一执行，不宣称已通过。

统一 review 与测试应覆盖第 11 节全部条目，以及 MUMmer 高频短单体敏感度、200-bp 合并间隔、跨物种误报/漏报、tel 扫描耗时与标记密度、旧项目恢复、App schema 迁移和来源显示。
正式 Server 源码资产刷新仍需通过 `RELEASING.md` 的质量、备份、发布和公共下载核验门槛；本轮不发布、不升级现有用户安装。

### 12.3 源码实施收尾核对（2026-11-04）

以下核对针对已实现的代码路径，不是第 11 节运行验收的通过记录。
用户已明确把统一 review 与测试留到后续安排；本次不执行测试、不发布正式资产。

| 要求 | 已核对的源码依据 |
| --- | --- |
| 默认官方库 + 本地库，参数仅作追加 | `prepare.sh` 调用 `annotation_library.py snapshot`；`snapshot()` 先读取两层库，再追加本次 tel/cen 参数，没有替换已有条目的分支。 |
| 本次参数不写回本地库 | `snapshot()` 的输出仅为项目内 `tel/`、`cen/` 和 `metadata/`；管理命令的本地写入与 prepare 分离。 |
| 管理最简、官方只读、note 可空 | `library.sh` 公开 list/add-tel/add-cen/remove；`manage()` 只向 `local/library/` 写入，拒绝删除官方 ID；note 默认空串并校验为单行文本。 |
| 去重不丢来源与 note | tel 按规范化 motif + min_repeat 的内容哈希合并；cen 按大写序列内容哈希合并；每组保留全部 entries，标记输出保留 provenance。 |
| 官方更新不影响本地库或项目依据 | `update_server.prepare()` 拒绝官方 manifest 拥有 `local/`；`runtime_file()` 不将安装库分发为项目 runtime；快照位于项目运行数据目录，不在代码更新目标中。 |
| 续跑只使用项目快照 | assignment、GRT 输入构建/端粒收尾、cen 扫描接入 `verify_snapshot()`；outer checkpoint 输入包含快照、cen FASTA 和扫描模块；未接入运行时读取安装库的路径。 |
| cen 不按参考染色体命名或相似度推断归属 | 新快照统一记录 `chr_name=*`，序列名称仅用于追溯；各 chromosome 的任务均使用全部有效条目；新 prepare 不调用旧 `cen_reference_metadata.py` 的染色体绑定校验。 |
| 短重复合并后再按长度判断 | `cen_scan.parse_coords()` 先过滤单次 identity；`merge_hits()` 按 contig 合并近邻，计算命中覆盖并排除重叠/间隔，再应用 min-len。 |
| 保留原有 tel 阈值语义并扩展常见范围 | 原有两类 motif 的末端阈值仍为 5，供体仍要求 >=500 bp；TTAGG 是明确新增的默认覆盖，不将其描述为全部结果与旧版一致。 |
| 新增 dataset 不偷偷采用当前安装库 | `templates/add_dataset.sh` 复制原项目到 stage 并调用其 assignment/runtime，stage 内快照相对路径不变；没有重新调用安装库 snapshot 的步骤。 |
| 标记来源进入 App 与报告 | TSV provenance 经过兼容旧包的解析，写入标记表、经 main_view 返回，再由标记详情显示；报告收集 cen provenance 与锁定 tel 规则；schema 7 仅新增默认空来源列。 |
| Light 不夹带本地 FASTA | `lgz_app_package.build()` 仅在 include_fasta 时复制 cen/library.fa，Light 仍保留来源 JSON/校验值，不复制注释 FASTA。 |
| v1 数据有固定来源 | `library/cen/sources.json` 固定四个 accession.version、坐标、长度与校验值；`library/tel.tsv` 包含三条带引用的规则；来源范围与限制见 SOURCES.md。 |

此外，对照项目依赖锁定版本 MUMmer4 4.0.1 的上游源码，确认当前使用的
`--maxmatch`、`--nosimplify`、`-l`、`-c`、`-t`、`-p` 均存在；
`show-coords -THrcl` 的 NUCMER 表格输出顺序与当前 13 列解析一致。
此核对只确认接口定义，不证明检测灵敏度、误报率或资源用量：

- https://github.com/mummer4/mummer/blob/v4.0.1/src/umd/nucmer_cmdline.yaggo
- https://github.com/mummer4/mummer/blob/v4.0.1/src/tigr/show-coords.cc

源码实施交接已齐备；真实数据校准、单元/集成测试、Rust 类型编译、App 构建/原生验收及正式发布仍保持待办，不能从上述静态核对推导为已通过。
