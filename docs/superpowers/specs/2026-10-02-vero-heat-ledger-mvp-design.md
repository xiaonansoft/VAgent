# VERO 炉次账本 MVP 设计（工艺师副驾驶）

> 日期：2026-10-02 · 状态：设计已获批，待规格评审
> 定位来源：2026-10-02 第一性原理头脑风暴（价值链 / 决策盘点 / 本体 / 产品反方四角色），用户认可新定位：
> **提钒智能体 = 钒的账本 + 工艺师的副驾驶**。离线归因先行，吹炼中实时推荐不在本期。
> 命名纪律：A 厂 = plant_a（机理派，四大平衡模型），B 厂 = plant_b（查表派，规程）。文中不出现真实厂名。

---

## 1. 目标与成功标准

**用户**：工艺工程师 / 技术科（主），车间主任（看日报），炉长（看自己班组的对账，不排名）。

**一句话**：工艺师导入一段时间的逐炉台账，系统逐炉、逐渣批把钒和热量算清，指出"钒丢在哪、哪几炉/哪几批异常、为什么"，并审计规程查表与机理是否打架。

**MVP 验收（合成数据上，全部自动化测试）**：

| # | 判据 | 门槛 |
|---|---|---|
| AC-1 | 合成数据中埋入的四类异常（见 §4.3），归因主因命中 | 召回 ≥ 80% |
| AC-2 | 账本自洽：分摊到炉次的流失之和 = 渣批差额；炉次→渣批→日→数据集四级漏斗逐级加总一致（引擎内烟尘钒为差额项，逐炉守恒是恒等式，不作为验收） | 相对误差 ≤ 1e-6 |
| AC-3 | 规程审计自动报出 B 厂查表在 Si 0.20%→0.22% 处的折算跳变 | 必报 |
| AC-4 | 合成数据导出为模板 CSV/XLSX 再导入，分析结果与直接分析一致 | 逐字段一致 |
| AC-5 | A 厂引擎黄金用例零漂移；安全扫描四项通过 | 75/75、4/4 |

**真实数据前提（不在本期软件范围，但决定下一步）**：B 厂 3~6 个月逐炉台账。拿到后只换文件，不改代码。

## 2. 范围

**在**：台账导入（模板 + 校验 + 适用范围检查）、合成逐炉数据生成器、逐炉/渣批钒账本核算、异常归因卡、规程审计（A 机理 × B 查表）、日报导出、工艺师单页工作台。

**不在**：吹炼中实时推荐、半钢炼钢段模型、多智能体编排、图数据库/OWL、任何控制写入、个人/班组排名与考核打分、修改现有 `blow` 会话与 `initial_charge` 引擎。

## 3. 架构

```
backend/app/ledger/
  schema.py        # 数据类：Heat / SlagBatch / Dataset / 字段字典（单位、必填、取值范围）
  claims.py        # 读取知识主张 YAML，提供阈值/查表/当量查询
  io.py            # 模板生成；CSV / XLSX 导入导出；字段校验与适用范围检查
  synth.py         # 合成逐炉数据生成器（确定性种子 + 埋入异常 + ground truth）
  engine.py        # 逐炉核算（调用 plant_a_reference）+ 渣批汇总 + 钒漏斗
  attribution.py   # 规则标记 + 统计效应估计 → 归因卡
  audit.py         # A 机理 × B 查表网格审计 → 冲突清单
  report.py        # 日报 / 交接班单（Markdown + HTML）
  narrate.py       # 叙述：模板组句；可选内网 LLM 润色（零数值权，失败回退模板）
  store.py         # SQLite（backend/ledger.db，已被 .gitignore 覆盖）
  routes.py        # FastAPI /api/ledger/*
knowledge/claims/
  industry.yaml    # 行业层主张（物理不变量、方向性规律）
  plant_b.yaml     # B 厂规程主张（按 p21/p22 原文，带页码与适用范围）
webapp/VERO_LEDGER.html   # 工艺师工作台（后端 /ui 同源托管，/ledger 重定向）
backend/tests/test_ledger_*.py
```

**依赖**：只用已安装的 numpy / fastapi / openpyxl / 标准库；Python 3.9 可跑。`plant_a_reference.py` 只读调用，不改。

## 4. 数据

### 4.1 炉次表（模板 `heats`）

| 字段 | 单位 | 必填 | 说明 |
|---|---|---|---|
| heat_id | — | ✓ | 炉号，数据集内唯一 |
| ts | ISO 时间 | ✓ | 开吹时刻 |
| shift / crew | — | ✓ | 班次 / 班组 |
| iron_t | t | ✓ | 铁水装入量 |
| iron_C / Si / Mn / P / S / V / Ti / Cr | % | C/Si/V/Ti ✓ | 铁水化验；缺省项用行业默认值并标注 |
| iron_T | ℃ | ✓ | 入炉铁水温度 |
| one_ladle | bool | | 是否一罐到底 |
| pellet_kg / waste_ball_kg / pig_iron_kg / vslag_steel_kg | kg | ✓（可 0） | 球返/球团、弃渣球、铁块、钒渣钢实加 |
| coolant_lot | — | | 冷料批号（关联冷料 CaO 抽检） |
| oxygen_s | s | ✓ | 纯供氧时间 |
| end_T | ℃ | ✓ | 终点温度 |
| semi_C / semi_V | % | ✓ | 半钢化验 |
| is_slag_heat | bool | ✓ | 是否出渣炉次 |
| tap_s | s | | 出钢时间 |
| slag_batch_id | — | ✓ | 所属渣批 |

### 4.2 渣批表（模板 `batches`）

`batch_id, slag_t, V2O5, TFe, CaO, SiO2, MFe`（% 口径为粗渣装车样）；可选冷料批表 `coolant_lots: lot_id, CaO`。

校验：必填、单位范围（如 Si 0~1、iron_T 1150~1450）、炉号唯一、渣批引用完整。**适用范围检查**：每炉对照主张库中的 envelope（Si/温度/冷料品种），越界炉次照常核算但标 `out_of_envelope`，不进入统计效应估计。

### 4.3 合成数据生成器

- 规模可配（默认 90 天 × 24 炉/天 ≈ 2160 炉），种子确定性；渣批按 2~3 炉一批。
- 输入分布按 B 厂规程统计特征：Si 主体 0.10~0.40（含 Si>0.25 段）、V 0.26~0.31、iron_T 1250~1340。
- 冷料按 B 厂 p21 查表 + 操作噪声给定；半钢温度用 A 厂引擎对 `semi_steel.temp` 二分求解使热平衡余量为 0，再加测量噪声 → 热量自洽。
- 渣批实收 = 预测入渣 V₂O₅ × (1 − 流失率)，基础流失率 + 噪声。
- **埋入四类异常**（标签只写入 ground truth，分析代码不可读）：
  1. **下渣流失**：某段时期出钢口老化，`tap_s` 逐步缩短到 < 210 s，流失率上升；
  2. **一罐到底**：某段 `one_ladle=true`，iron_T +20~30℃，渣 CaO 上升（高炉渣带入）；
  3. **冷料 CaO 超标**：某冷料批 CaO 高，引用该批的渣批 CaO 上升、品位下降；
  4. **供氧不足**：某段 `oxygen_s` 低于规程下限，semi_V 偏高（提钒不彻底）。
- 输出带 `source: synthetic`，界面与报告全程显示"合成数据"水印。

## 5. 核算（engine.py）

**逐炉**：用实测铁水成分/温度、实加冷料（映射：球返→pellet、弃渣球→waste_slag_ball、铁块→pig_iron_weight、钒渣钢→metal_fe 口径——**近似映射，登记为假设 H-1**）、实测半钢 C/V/终点温度，`corrected=True` 运行 A 厂引擎，取：

- `heat_residual_kJ`：热平衡余量（正 = 模型认为应更热 → 冷料偏少或测温偏低；负反之），换算等效温差 ℃；
- `v_in`、`v_oxidized = v_in_iron − v_out_semi`、`v2o5_to_slag_pred`（kg）、`slag_mass_pred`；
- 钒平衡各项（原样保留供明细展示）。

**渣批**：`v2o5_pred = Σ 成员炉 v2o5_to_slag_pred`；`v2o5_actual = slag_t × V2O5%`；`recovery_gap = 1 − actual/pred`；`grade_pred = Σv2o5_pred / Σslag_mass_pred`，与实测品位对比。

**钒漏斗（数据集/日/班）**：铁水带入 → 已氧化 → 预测入渣 → 渣批实收；差额 = 流失，按成员炉预测贡献比例分摊到炉次。

**指标口径**：钒氧化率 = v_oxidized / v_in_iron；钒回收率 = v2o5_actual 折 V / v_in_total。口径写入字段字典，界面可查。

## 6. 归因（attribution.py）

**两层**：

1. **规则标记**（确定性，每条规则引用主张 ID 与页码）：
   - `tap_s < 210`（3.5 min）→ 下渣风险；
   - `one_ladle` 或 iron_T 显著高于批次均值 → 一罐到底/热量偏高；
   - 冷料批 CaO > 主张阈值（1.2% 口径待厂确认，登记 H-2）→ 冷料杂质；
   - `oxygen_s` < 规程下限（一般 >310 s、出渣炉次 >320 s、Si≥0.22% >330 s）→ 供氧不足；
   - Si > 0.25 → 高硅；实加冷料偏离查表推荐 > 阈值 → 配料偏差；`|heat_residual| ` 等效 > 15℃ → 热量不自洽（测温/冷料实吊量可疑）。
2. **效应估计**：对渣批层 `recovery_gap`、品位残差、CaO，对炉次层 semi_V，用最小二乘回归到上述因素的批次均值/占比上，得到每个因素的效应量与置信区间；对每个异常对象，按"规则命中 × 效应量"排序出主因、次因。

**异常判定**：残差超过数据集稳健 σ（MAD）2.5 倍的渣批/炉次进入异常列表。

**归因卡**：对象（渣批/炉次）、现象（数字 vs 基线）、主因与次因（效应量、命中规则、主张出处）、证据炉次清单、建议核查项（只建议核查，不下结论定责）、数据质量标注（越界、缺省、热量不自洽）。

## 7. 规程审计（audit.py）

- 网格：Si ∈ B 厂 p21 表各行 × iron_T ∈ {1260, 1280, 1300, 1320, 1340}，装入 80 t。
- B 口径：查表球返 kg/t + 温度修正 1.5 kg/t/10℃ + 铁块、钒渣钢按当量（1 t 球返 = 6 t 铁块 = 1.7 t 钒渣钢）折算为球返当量 kg/t。
- A 口径：A 厂引擎 `pellet=None` 自动求解所需球团 kg/t（其余冷料 0），半钢目标取主张中的终点温度中值。
- 输出：两口径的 ∂/∂Si、∂/∂T 斜率与截距差；B 当量序列单调性检查与跳变点；表注规则与当量的自洽检查（如"无铁块多加球返 0.5 t"vs 当量折算）；每项生成冲突条目 `{id, claim_a, claim_b, 差值, 说明, status=open}`。
- 审计结论只陈述差异与证据，**不改任何参数**。

## 8. 知识主张（knowledge/claims/*.yaml）

```yaml
- id: B-P21-COOL-TABLE
  kind: lookup            # lookup | threshold | equivalence | procedure | physical
  plant: plant_b
  statement: "1280℃ 基准下按铁水 Si 分档的球返加入量"
  data: {base_T: 1280, unit: kg/t, rows: [[0.10, 0, 0, 18], ...]}  # Si, 铁块t, 钒渣钢t, 球返kg/t
  envelope: {iron_T_min: 1260, si_min: 0.10, si_max: 0.40, iron_t: 80}
  source: {doc: "B厂转炉提钒技术材料(2020)", page: 21}
  status: draft           # draft | approved | disputed | superseded
```

MVP 收录：p21 查表、温度/Si 修正、冷却当量、冷料加入方式、出渣炉次温度、供氧时间下限、出钢时间 3.5 min、行业层 Tc 1361℃ 与 Si↑→冷料↑/品位↓方向性规律。已知问题：现有 `knowledge/packs/plant_b/base.yaml` 的 `coolant_lookup` 实为同集团另一基地口径（1300℃ 基准），本期**不改该包**（blow 会话在用），在审计报告"数据来源问题"一节显式列出，另立待办。

## 9. 接口（/api/ledger）

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/template.xlsx`、`/template/{heats,batches}.csv` | 下载模板 |
| POST | `/datasets/synthetic` `{days, heats_per_day, seed}` | 生成合成数据集 |
| POST | `/datasets/import`（multipart，xlsx 或两份 csv） | 导入，返回校验报告 |
| GET | `/datasets` | 列表 |
| POST | `/datasets/{id}/analyze` | 运行核算 + 归因，结果缓存 |
| GET | `/datasets/{id}/summary` | KPI、漏斗、损失瀑布、按日序列 |
| GET | `/datasets/{id}/findings` | 异常列表 + 归因卡 |
| GET | `/datasets/{id}/heats/{heat_id}`、`/batches/{batch_id}` | 明细 |
| GET | `/datasets/{id}/export.xlsx` | 导出（AC-4） |
| GET | `/datasets/{id}/report/daily?date=` | 日报 HTML/Markdown |
| GET | `/audit` | 规程审计报告 |
| GET | `/datasets/{id}/groundtruth` | 仅合成数据集，供"验证"视图对比 |

全部只读或写本地 SQLite；无任何控制端点（安全扫描路由断言覆盖）。

## 10. 工作台（webapp/VERO_LEDGER.html）

单页，无构建，原生 JS + SVG，沿用 `design-system/design-tokens.css`；浅色工程文档风（工艺师桌面场景）。五个视图：

1. **账本总览**：数据集选择/生成/导入；KPI（氧化率、回收率、平均品位、流失 V₂O₅ t）；钒漏斗；损失瀑布（按归因因素）；按日趋势。
2. **异常**：异常渣批/炉次列表（按损失量排序）→ 归因卡。
3. **渣批**：渣批表 + 成员炉次 + 预测 vs 实测。
4. **规程审计**：斜率/截距对比表、跳变点、冲突清单、数据来源问题。
5. **日报**：选日期 → 预览 → 导出。

合成数据集额外有"验证"页签：埋入异常 vs 归因结果的对照（即 AC-1 的可视化）。

## 11. 叙述（narrate.py）

模板组句为默认；若配置 `VERO_LLM_BASE_URL`，对归因卡和日报做润色，润色后校验数字集合与原文一致，不一致则丢弃回退模板。LLM 不参与任何计算与判定。

## 12. 测试

- `test_ledger_engine.py`：账本四级加总与流失分摊一致（AC-2）；热余量在合成"无异常"炉次上 ≈ 0。
- `test_ledger_synth.py`：同种子输出完全一致；四类异常均被埋入。
- `test_ledger_attribution.py`：AC-1 召回 ≥ 80%（默认种子 + 另两个种子）。
- `test_ledger_audit.py`：AC-3 跳变必报；单调性检查。
- `test_ledger_io.py`：AC-4 往返一致；校验报错路径。
- `test_ledger_api.py`：TestClient 冒烟全部端点。
- 既有：`tests/test_plant_a_reference.py` 75/75、`scripts/security_scan.py` 4/4（AC-5）。

## 13. 假设与风险

| # | 内容 | 处置 |
|---|---|---|
| H-1 | 钒渣钢按 A 引擎"金属铁"口径近似 | 界面与报告标注；真实数据后按成分修正 |
| H-2 | 冷料 CaO 阈值 1.2% 口径 | 主张 status=draft，待厂确认 |
| H-3 | A 引擎为 A 厂常数，直接用于 B 厂截距必有偏差 | 归因用残差的**相对**偏离（对数据集基线），不用绝对值；审计中"截距差"即此证据 |
| R-1 | 合成数据验证 ≠ 真实有效 | 全程水印；真实台账到位后按同一 AC 重跑 |
| R-2 | 渣批粗渣样代表性 | 渣批层统计，单批结论标置信度 |
