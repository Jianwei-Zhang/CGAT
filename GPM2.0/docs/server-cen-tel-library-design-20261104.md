# Server cen / tel 官方库与本地库设计

日期：2026-11-04

状态：设计已确认，v1 官方库收录范围已确定，尚未实施。cen 条目的具体序列和 accession 需在生成数据前逐条核对；本文不授权修改 Server 代码、生成官方库数据、发布 Server 源码包或修改用户工作区。

## 1. 目标

- Server 提供 tel 和 cen 官方库，`prepare` 自动使用库中的检查信息。
- 用户可维护自己的本地库。
- 运行时可以显式传入 `--tel`、`--cen` 补充本次信息。
- 官方库更新不能修改用户本地库。
- 已准备的项目不能因为 Server 或官方库更新而悄悄改变检查依据。

## 2. 当前实现基线

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

现有 GRT 默认值为末端 5 个、供体 20 个；由于供体还要求至少 500 bp，7 bp 以内的 motif 在供体检查中实际由 500 bp 决定。因此官方条目采用 `min_repeat = 5` 时，GRT 现有默认行为不变。官方库生效后不再需要 GRT 内置的另一套默认 motif。

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
- 在每条染色体对应的 assembly 中搜索候选区域。
- 相同序列只计算一次，但保留全部来源和 `note`。

判定流程：

```text
cen 序列命中
→ 合并相邻命中
→ 按区域总长度筛选
→ 输出着丝粒候选区域
```

- `--cen-min-identity` 判断单个命中是否可信。
- `--cen-min-len` 判断合并后的区域是否足够长。
- 两个阈值统一作用于官方库、本地库和本次 `--cen`。
- 相邻命中的最大间隔第一版采用固定内部规则，不开放参数；数值需根据真实官方库样本和测试数据确定。

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
- 采用新库需要明确重新 prepare 或重新检查。

## 9. 兼容性

- `--tel` 用法不变，但改为追加到库规则上。
- `--cen` 仍传 FASTA，但语义改为“着丝粒相关序列”。
- 旧 `<chr>_centromere` FASTA 仍可读取，但染色体名不参与判定。
- 报告和 App 中的 cen 表述改为“着丝粒候选区域”，并显示命中条目及来源。

## 10. 官方库 v1

### 10.1 收录原则

- 只收录最常见、证据明确的条目；少见类群由用户放入本地库。
- 每个条目必须能追溯到可复核的数据库、论文或公开数据，依据写入 `note`。
- 区分实验证据与计算预测；v1 不收录仅由计算预测得到的条目。
- tel 只收录 motif 和阈值这类事实信息，引用原始文献，不复制 TeloBase 数据库内容。
- cen 序列来自 GenBank/ENA 等公开记录或论文补充材料，生成数据前逐条核对 accession、长度和序列。

### 10.2 tel

| id | motif | min_repeat | 适用范围 | 依据（生成前核对） |
| --- | --- | ---: | --- | --- |
| `tel_plant_TTTAGGG` | `TTTAGGG` | 5 | 多数陆地植物（拟南芥型） | Richards & Ausubel, Cell 1988 |
| `tel_vertebrate_TTAGGG` | `TTAGGG` | 5 | 脊椎动物及多种真核生物 | Moyzis et al., PNAS 1988 |
| `tel_arthropod_TTAGG` | `TTAGG` | 5 | 多数节肢动物/昆虫 | Okazaki et al., MCB 1993；Sahara et al., Chromosome Res 1999 |

不进入 v1：衣藻型 `TTTTAGGG`、葱属、茄科夜香树属等特殊类群，以及双翅目中由转座子维持端粒的物种。

### 10.3 cen

| id | 条目 | 单体长度 | 物种 | 依据（生成前核对） |
| --- | --- | ---: | --- | --- |
| `cen_arabidopsis_CEN180` | CEN180 | 约 178 bp | 拟南芥 | Naish et al., Science 2021 |
| `cen_rice_CentO` | CentO | 约 155 bp | 水稻 | Cheng et al., Plant Cell 2002 |
| `cen_maize_CentC` | CentC | 约 156 bp | 玉米 | Ananiev et al., PNAS 1998 |
| `cen_human_alpha` | α-satellite | 约 171 bp | 人 | Altemose et al., Science 2022 |

- 每个条目收录一条代表性单体序列，并在 `note` 中写明来源记录、长度和功能证据。
- 小麦等主要由着丝粒反转录转座子构成的类群不进入 v1。
- cen 卫星序列种属特异性强；未命中只表示官方库没有覆盖该物种，不表示没有着丝粒。

### 10.4 实施前需验证

- cen 单体在全基因组中有大量拷贝。当前 minimap2 方式可能因高频 minimizer 过滤而漏检，实施前需用真实数据确认检测方法。
- 现有 `prepare` 端粒扫描为逐字符 Python 实现。官方库默认启用后，每个项目都会扫描全部 assembly，实施前需评估耗时。
- `min_repeat = 5` 会标出更多染色体内部端粒样重复；需用测试数据确认显示密度是否可接受。

## 11. 实施验收

- 只用库时，tel 和 cen 自动生效。
- 库与显式参数正确合并。
- 官方库更新后，本地库字节不变。
- Server 更新后，已准备项目仍使用原快照。
- 不能删除官方条目。
- 短重复序列的相邻命中能正确合并为候选区域。
- 结果中显示命中条目及来源。
- 使用官方 tel 库时，GRT 末端和供体判定与现有默认行为一致。
