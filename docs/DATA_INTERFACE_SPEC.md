# VERO 数据接口规范（DATA_INTERFACE_SPEC）v0.2

> 版本 v0.2 · 2026-09-27 · 在 v0.1 基础上，依据 backend 实际代码
> （`schemas.py` / `data_server.py` / `simulator.py` / `plant_a_reference.py` / `main.py`）校对并落地 MVP 服务化契约。
> 性质：**只读采集 + 证据回流**，不写回控制回路。所有字段基于现有实现，未凭空新增。

---

## 0. 变更记录（v0.1 → v0.2）

| # | 变更 | 说明 |
|---|---|---|
| 1 | 校对 §3 字段与 backend 实际 schema 的**漂移** | `IronInitialAnalysis` 无 `Mn`、烟气命名、`IronInitialAnalysis` 范围宽松 |
| 2 | 新增 §3.0 四大平衡服务化契约 `POST /api/plant_a/charge` | B 路产物，**已实跑验证**：黄金用例 13.299% 与 Excel 一致 |
| 3 | 新增 §5 统一 `resource://` URI 注册表 | 区分「已实装 / 规划」 |
| 4 | 新增 §8 MVP↔后端 能力映射与缺口 | 副枪/软测量/置信/三元素在 v0.7 未落地 |
| 5 | D6-1~5 转为 §7 决策登记册 | 给出 interim 默认值，使 P3 可启动而不阻塞 |

---

## 1. 目的与范围

打通「机理引擎 ↔ 现场数据」边界，为 P3 学习闭环（RLS/PINN 残差、TabPFN 试点、漂移检测）提供字段级约定。覆盖五类数据源：
1. 化验室 / 铁水条件（炉前、炉后）
2. PLC 实时过程量（温度、氧枪、枪位）
3. 副枪 TSC / TSO（离散采样）
4. 烟气分析（off-gas）
5. 炉后台账与判例（历史炉次）

## 2. 网络边界与安全红线（不可越界）

| 条款 | 约定 |
|---|---|
| 方向 | **只读**：从 PLC/DCS/化验室**采集**，永不反向写控制回路（对齐「只决策不执行」） |
| 位置 | 内网部署，**数据不出厂**（对齐 MVP 验收 A6 离线条款） |
| IP 分级 | 专家A Excel 专家常数（`knowledge/packs/plant_a/base.yaml`）与现场台账均为**机密 IP**，不入公网、不提交 |
| 采集模式 | 实时高频走 SSE/内网总线；化验室走批量导入；副枪走离散事件 |
| 降级 | 采集断链时软测量兜底（`soft_sensor.py`），界面标注 `correction_source` 与置信度 |

---

## 3. 数据源清单（校对后）

### 3.0 四大平衡配吃服务（新增，MVP 主通道）★ 已实装

端点 `POST /api/plant_a/charge`。这是 B 路把 `plant_a_reference` 四大平衡引擎服务化的结果，直接对齐 MVP 的 `runModel()` 与 `arb()` 卡。

**请求示例**
```json
{ "C": 4.3, "Si": 0.215, "V": 0.284, "Ti": 0.11, "iron_weight_kg": 80000 }
```

**响应示例（黄金用例，与 Excel 一致）**
```json
{
  "rule_version": "plant_a four-balance v7.0.0 (golden regression 75/75, max err 0.0002%)",
  "primary": {
    "dh_v": 2777.0,
    "v2o5_grade_pct": 13.299,
    "slag_grade_pct": { "V2O5": 13.299, "TFe": 33.2566, "SiO2": 16.4006, "TiO2": 9.6686 },
    "recipe_kg": { "pellet": 3529.6, "metal_fe": 0.0, "ore_block": 0.0, "waste_slag_ball": 0.0 },
    "v_recovery_pct": 87.966,
    "v_si_ti_ratio": 0.8738
  },
  "arbitration": {
    "case_2777":  { "dh_v": 2777.0,  "v2o5_grade_pct": 13.299,  "recipe_kg": { "pellet": 3529.6 } },
    "case_15000": { "dh_v": 15000.0, "v2o5_grade_pct": 12.8653, "recipe_kg": { "pellet": 4049.85 } }
  }
}
```

| 响应字段 | 含义 | 单位 |
|---|---|---|
| `v2o5_grade_pct` | 精钒渣 V₂O₅ 品位（核心输出） | % |
| `slag_grade_pct.*` | 渣相全成分（V₂O₅/TFe/SiO₂/TiO₂/CaO…） | % |
| `recipe_kg.pellet` 等 | 单炉冷料配吃量（自动求解项） | kg/炉 |
| `v_recovery_pct` | 钒回收率 | % |
| `v_si_ti_ratio` | V/(Si+Ti) 去钒保碳判据 | — |
| `arbitration` | ΔH_V 双案对照（2777 vs 15000） | — |

> 请求入参：`C,Si,V,Ti` 必填；`P,S,Mn,Cr,iron_weight_kg,iron_temp_c,is_one_can` 可选（引擎有默认值）；`dh_v` 可选，覆盖 V 氧化热以触发仲裁对照。

### 3.1 化验室 / 铁水条件（炉前，每炉 1 次）

来源：化验单 / MES。代码对齐 `IronInitialAnalysis` + `InitialChargeInputs`。

**⚠️ 漂移（v0.1 → 代码）**：`IronInitialAnalysis` **不含 `Mn`**；`IronInitialAnalysis` 范围宽松（`C` ge=0 le=10 等），而 v0.1 给的是工艺范围。

| 字段 | 单位 | 接口强校验范围（建议） | 代码现状 |
|---|---|---|---|
| `iron_weight_t` | t | 40–140 | `InitialChargeInputs` ge=50 le=350 |
| `iron_temp_c` | ℃ | 1250–1380 | ge=1100 le=1600 |
| `C` | % | 3.0–4.8 | ge=0 le=10（宽松） |
| `Si` | % | 0.05–0.35 | ge=0 le=5 |
| `V` | % | 0.15–0.40 | ge=0 le=5 |
| `Ti` | % | 0.05–0.25 | ge=0 le=5 |
| `Mn` / `P` / `S` | % | P/S 按代码；Mn 缺失 | `IronInitialAnalysis` 有 P/S，**无 Mn** |
| `is_one_can` | bool | — | 有 |
| `prev_lining_heat` / `prev_slag_status` | — | 可选（L1 记忆修正） | 有 |

**结论**：以 v0.1 的工艺范围作为数据接口**强校验层**；代码当前宽松，待 P3 收紧。接口层补 `Mn`（引擎 `PlantAInputs.iron` 含 Mn，默认 0.18），否则 Mn 走默认。

### 3.2 PLC 实时过程量（高频，SSE 1s tick）— 已验证对齐 `simulator._build_payload`

| 字段 | 单位 | 频率 | 说明 |
|---|---|---|---|
| `process_time` | min | 1s | 吹炼进程时间 |
| `temperature.value` | ℃ | 1s | 温度（经软测量后的值） |
| `temperature.status.{is_valid,raw_value,estimated_value,confidence,correction_source}` | — | 1s | 传感器健康 + 机理推断溯源 |
| `chemistry.{si,v,c}` | % | 1s | 熔池成分（模型推演值） |
| `lance_height.value` | mm | 1s | 枪位（急停=2000，正常 900–1200） |
| `oxygen_flow` | Nm³/h | 1s | 供氧流量（默认 22000） |
| `model_params.{heat_efficiency,reaction_rate_mod}` | — | 1s | 自学习参数（默认 0.92 / 1.05） |
| `is_emergency_stop` | bool | 1s | 急停标志 |

### 3.3 副枪 TSC / TSO（离散事件，每炉 1–2 次）

代码 `simulator.latest_sample = {time, temp, C, V}`。命名约定：TSC（测温·取样·定碳）与 TSO 在提钒场景需确认副枪是否含 **V 测定**（D6-1）。

### 3.4 烟气分析（off-gas，连续 1–5s）

代码 `OffGasData`：`flow_rate_nm3_hr`, `co_pct`, `co2_pct`。

> **⚠️ 命名漂移**：v0.1 用 `off_gas.flow/CO/CO2`，代码用 `flow_rate_nm3_hr/co_pct/co2_pct`。§5 注册表统一采用代码字段名。

| 字段 | 单位 | 频率 | 说明 |
|---|---|---|---|
| `off_gas.flow_rate_nm3_hr` | Nm³/h | 1–5s | 烟气流量 |
| `off_gas.co_pct` / `off_gas.co2_pct` | % | 1–5s | CO / CO₂ 含量 |
| `bath_weight` | t | 炉次 | 熔池重量（反算脱碳率用） |

> 烟气是**软测量反算脱碳率 dC/dt 的唯一硬数据源**，其缺失直接削弱 L2 碳含量估计与卡尔曼修正。

### 3.5 炉后台账与判例（批量）— 已验证 `GET /api/heats` 返回 16 炉

来源：`models.py` 的 `Heat` / `AdviceLog` 表。

| 字段 | 说明 |
|---|---|
| `heat_id / furnace_id / timestamp` | 炉次标识 |
| `actual_final_temp` | 实际终点温度（对标 `l2_final_temp` 算误差） |
| `actual_analysis` | 实际成分（含精渣 V₂O₅ 品位、粗渣品位） |
| `advice_adopted` | 建议是否被采纳（P4 例外率看板输入） |
| `trace_id / message / reply / tool_calls / context` | 判例与留痕（AdviceLog） |

---

## 4. 传输协议（更新端点表）

| 通道 | 协议 | 端点 | 用途 | 状态 |
|---|---|---|---|---|
| 实时流 | SSE | `GET /api/stream` | 1s 过程数据 | ✅ 200 |
| **四大平衡** | **JSON** | **`POST /api/plant_a/charge`** | **MVP 配吃/品位/仲裁** | **✅ 200（新增）** |
| MCP 资源 | JSON-RPC | `POST /api/mcp/data` | `resources/list/read/subscribe` + `control/stop/resume` | ✅ 200 |
| 工具调用 | JSON-RPC | `POST /api/mcp/tools` | 配料/仿真/诊断等 | （沿用） |
| 炉次 | REST | `GET /api/heats` | 16 炉实绩 | ✅ 200 |
| 仿真 | REST | `POST /api/simulation/run` | 吹炼路径点 | ✅ 200 |
| 对话 | REST | `POST /api/chat` | L3 助手 | ✅ 200 |

> 资源 URI 约定（`data_server.py` 已用）：`resource://plc/iron_ladle/temperature`、`resource://plc/converter/lance_height`。建议扩展见 §5。

---

## 5. `resource://` URI 注册表

| URI | 语义 | 状态 |
|---|---|---|
| `resource://plc/iron_ladle/temperature` | 铁水温度 | ✅ 已实装 |
| `resource://plc/converter/lance_height` | 枪位高度 | ✅ 已实装 |
| `resource://plc/converter/oxygen_flow` | 供氧流量 | 🔲 规划 |
| `resource://offgas/analyzer/co` | 烟气 CO（字段 `co_pct`） | 🔲 规划 |
| `resource://offgas/analyzer/co2` | 烟气 CO₂（字段 `co2_pct`） | 🔲 规划 |
| `resource://sublance/tsc/latest` | 副枪最新样（temp/C/V） | 🔲 规划 |

---

## 6. 软测量依赖矩阵

| 软测量输出 | 依赖字段 | 缺失降级 |
|---|---|---|
| 温度校验/推断 | `temperature` + `chemistry.si/v/c` 速率 | `default_fallback` 1300℃（confidence 0.1） |
| 脱碳率 dC/dt | `off_gas.flow_rate_nm3_hr/co_pct/co2_pct` + `bath_weight` | 无硬数据，仅模型先验 |
| 碳含量卡尔曼修正 | `sublance.C` + 烟气反算 | 仅模型预测 |

---

## 7. D6 决策登记册（开放问题 → interim 默认值）

| # | 问题 | interim 默认（P3 启动用） | 责任 |
|---|---|---|---|
| D6-1 | 副枪 TSC/TSO 是否含 **V 测定** | 暂假设不含 → V 终点由烟气+软测量估计，标注 `estimated` | 【数据】 |
| D6-2 | 烟气分析仪采样周期与量程 | 默认 1–5s，CO 量程 0–100% | 【数据】 |
| D6-3 | 化验室 Si/V 送样到出数时延 | interim 30s（待实测，影响炉前实时性） | 【工艺】 |
| D6-4 | PLC 点表 ↔ `resource://` URI 映射 | 先接 `simulator` 模拟源，实厂时再做 | 【数据】 |
| D6-5 | shadow mode 并行列数 / 切换标准 | 默认 1 炉 shadow，连续 5 炉误差 <3σ 切换 | 【安全】 |

---

## 8. MVP ↔ 后端 能力映射与缺口（B 路核查）

| MVP 功能 | 后端现状 | 桥接方式 |
|---|---|---|
| 配吃量 | ✅ `/api/plant_a/charge` → `recipe_kg` | `fetch` 替换 `runModel()` |
| V 渣品位 | ✅ 同上 `v2o5_grade_pct` | 同上 |
| ΔH 仲裁 | ✅ `arbitration` 双案 | 同上 |
| 三元素解释 | ⚠️ 后端未返回，仍由 MVP JS 渲染（输入来自后端） | 保留前端渲染 |
| 16 炉回放 | ⚠️ MVP 内嵌 `HEATS`；`/api/heats` 为 DB 炉次，未含 RMSE | 暂保留前端回放，后续接真实台账 |
| 副枪 TSC/TSO | ⚠️ v0.7 **已含** `TSC`/`TSO`（各 1 处），但为静态标注 | 待接 SSE `latest_sample` |
| 三要素解释 | ⚠️ **部分落地**：机理(5 处)、相似炉次(3 处) 已有，**规则版本(0 处)缺失** | 后端已返 `rule_version`，前端补渲染 |
| 置信度 | ❌ 完全缺失（`置信`/`置信度` 均 0 处） | 待 P3（MVP_SPEC A8 未达成） |
| 软测量 | ❌ 完全缺失（`软测量`/`confidence` 均 0 处） | 待 P3（HANDOVER 未决 #8） |

> **⚠️ 审计修正（2026-09-27 21:15）**：此前据中文关键词判定「副枪/三要素未落地」**结论有误**——副枪实以 `TSC`/`TSO` 英文标识存在；三要素中「机理」「相似炉次」已存在，仅「规则版本」缺失。仅**置信度与软测量**确为完全缺失。此处已订正。

> **桥接目标更新**：最新产物为 **`VERO_MVP_v0.8.html`**（20:50，71,972 B，检索 `fetch/localhost//api/` 均为 0），**非 v0.7**。桥接应以 v0.8 为基线，产出新副本 `VERO_MVP_v0.8_bridged.html`，不覆盖原稿。

> 下一步桥接（Task #3）：在 v0.8 的重算入口注入 `fetch('/api/plant_a/charge', readInput())`，用后端返回覆盖品位/配吃，渲染器 `explainTB/arb/drawReplay` 保留；离线 JS 引擎作降级。已知风险：`file://` 的 origin 为 `null`，需先验证 CORS（后端已 `allow_origins=["*"]`，但 `allow_credentials=True` 与 `*` 并存可能被浏览器拒），必要时改由后端静态目录托管该 HTML。

---

## 9. 开放问题（更新）

- D6-1~5 已转入 §7，给出 interim 默认。
- **B-1**：`/api/plant_a/charge` 的 `Mn/Cr` 入参已开放，需确认默认 0.18/0.09 是否随铁水来源变化（对齐 CF-001 边界）。
- **B-2**：`arbitration` 每次请求跑 3 次模型，高频场景需缓存（响应已 <100ms，单炉场景可暂缓）。

*对齐：`schemas.py` / `data_server.py` / `simulator.py` / `plant_a_reference.py` / `main.py`（v0.2 新增端点）；`HANDOVER.md` §6 #7；`MVP_SPEC.md` A1–A8。*
