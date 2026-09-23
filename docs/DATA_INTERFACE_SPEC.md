# VEES 数据接口规范（DATA_INTERFACE_SPEC）

> 版本 v0.1（草案）· 2026-09-23 · 对应 HANDOVER §6 未决项 #7「TSC/TSO/烟气/氧枪 数据接口规范（D6，决定 P3 一切成败）」
> 性质：**只读采集 + 证据回流**，不写回控制回路。所有字段基于 `backend/` 现有实现（`schemas.py` / `simulator.py` / `soft_sensor.py` / `data_server.py` / `models.py`）与 `config.py` 默认参数，未凭空新增。

---

## 1. 目的与范围

打通「机理引擎 ↔ 现场数据」的边界，为 P3 学习闭环（RLS/PINN 残差、TabPFN 试点、漂移检测）提供字段级约定。本规范覆盖五类数据源：

1. 化验室 / 铁水条件（炉前、炉后）
2. PLC 实时过程量（温度、氧枪、枪位）
3. 副枪 TSC / TSO（离散采样）
4. 烟气分析（off-gas）
5. 炉后台账与判例（历史炉次）

---

## 2. 网络边界与安全红线（不可越界）

| 条款 | 约定 |
|---|---|
| 方向 | **只读**：从 PLC/DCS/化验室**采集**，永不反向写控制回路（对齐 PRODUCT_DEFINITION「只决策不执行」） |
| 位置 | 内网部署，**数据不出厂**（对齐 MVP 验收 A6 离线条款） |
| IP 分级 | 攀钢 Excel 专家常数（`knowledge/packs/pangang/base.yaml`）与现场台账均为**机密 IP**，不入公网、不提交 |
| 采集模式 | 实时高频走 SSE/内网总线；化验室走批量导入；副枪走离散事件 |
| 降级 | 采集断链时软测量兜底（`soft_sensor.py`），界面标注 `correction_source` 与置信度 |

---

## 3. 数据源清单

### 3.1 化验室 / 铁水条件（炉前，每炉 1 次）

来源：化验单 / MES。字段对齐 `IronInitialAnalysis` + `InitialChargeInputs`：

| 字段 | 单位 | 精度 | 校验范围 | 说明 |
|---|---|---|---|---|
| `iron_weight` | t | 0.1 | 40–140 | 铁水装入量 |
| `iron_temp` | ℃ | 1 | 1250–1380 | 兑铁温度 |
| `C` | % | 0.01 | 3.0–4.8 | 碳 |
| `Si` | % | 0.001 | 0.05–0.35 | 硅（配吃核心） |
| `V` | % | 0.001 | 0.15–0.40 | 钒 |
| `Ti` | % | 0.001 | 0.05–0.25 | 钛（V/(Si+Ti) 判据） |
| `Mn` / `P` / `S` | % | 0.001 | — | 锰/磷/硫 |
| `is_one_can` | bool | — | — | 一罐到底工艺 |
| `prev_lining_heat` | — | 0.1 | 可选 | 上一炉留渣/蓄热（L1 记忆修正） |

### 3.2 PLC 实时过程量（高频，SSE 1s tick）

来源：`simulator.py::_build_payload` 已定义的 payload 结构：

| 字段 | 单位 | 频率 | 说明 |
|---|---|---|---|
| `process_time` | min | 1s | 吹炼进程时间 |
| `temperature.value` | ℃ | 1s | 温度（经软测量后的值） |
| `temperature.status.is_valid / raw_value / estimated_value / confidence / correction_source` | — | 1s | 传感器健康 + 机理推断溯源 |
| `chemistry.si / v / c` | % | 1s | 熔池成分（模型推演值） |
| `lance_height.value` | mm | 1s | 枪位（急停=2000，正常 900–1200） |
| `oxygen_flow` | Nm³/h | 1s | 供氧流量（默认 22000） |
| `model_params.heat_efficiency / reaction_rate_mod` | — | 1s | 自学习参数（默认 0.92 / 1.05） |
| `is_emergency_stop` | bool | 1s | 急停标志 |

### 3.3 副枪 TSC / TSO（离散事件，每炉 1–2 次）

来源：`simulator.py` 中 `latest_sample`（TSC ≈ 2.0 min，TSO ≈ 7.0 min）：

| 字段 | 单位 | 说明 |
|---|---|---|
| `sample.time` | min | 采样时刻 |
| `sample.temp` | ℃ | 副枪测温 |
| `sample.C` | % | 副枪定碳 |
| `sample.V` | % | 副枪测钒 |

> 命名约定：TSC（测温·取样·定碳）与 TSO（测温·定氧·定碳）在提钒场景需确认副枪是否含 **V 测定**；若现场副枪不含 V，则以烟气反算 + 软测量估计，并标注 `estimated`。

### 3.4 烟气分析（off-gas，连续 1–5s）

来源：`soft_sensor.py::derive_decarburization_rate` 的直接输入：

| 字段 | 单位 | 频率 | 说明 |
|---|---|---|---|
| `off_gas.flow` | Nm³/h | 1–5s | 烟气流量 |
| `off_gas.CO` | % | 1–5s | CO 含量 |
| `off_gas.CO2` | % | 1–5s | CO₂ 含量 |
| `bath_weight` | t | 炉次 | 熔池重量（反算脱碳率用） |

> 烟气是**软测量反算脱碳率 dC/dt 的唯一硬数据源**，其缺失直接削弱 L2 碳含量估计与卡尔曼滤波修正（`MODEL_ALGORITHM.md` §2.4/§5.2）。

### 3.5 炉后台账与判例（批量）

来源：`models.py` 的 `Heat` / `AdviceLog` 表：

| 字段 | 说明 |
|---|---|
| `heat_id / furnace_id / timestamp` | 炉次标识 |
| `actual_final_temp` | 实际终点温度（对标 `l2_final_temp` 算误差） |
| `actual_analysis` | 实际成分（含**精渣 V₂O₅ 品位**、粗渣品位） |
| `advice_adopted` | 建议是否被采纳（P4 例外率看板输入） |
| `trace_id / message / reply / tool_calls / context` | 判例与留痕（AdviceLog） |

---

## 4. 传输协议

| 通道 | 协议 | 端点（现有） | 用途 |
|---|---|---|---|
| 实时流 | SSE | `GET /api/stream` | 1s 过程数据 |
| MCP 资源 | JSON-RPC | `POST /mcp/data`（`resources/list` / `resources/read` / `resources/subscribe`） | 点查询 + 订阅 |
| 控制（急停） | JSON-RPC | `POST /mcp/data`（`control/stop` / `control/resume`） | 仅仿真演示用，**不接真实控制回路** |
| 工具调用 | JSON-RPC | `POST /mcp/tools` | 配料/仿真/诊断等 |

> 资源 URI 约定（`data_server.py` 已用）：`resource://plc/iron_ladle/temperature`、`resource://plc/converter/lance_height`。建议扩展为统一命名空间：`resource://plc/converter/oxygen_flow`、`resource://offgas/analyzer/co`、`resource://sublance/tsc/latest` 等。

---

## 5. 软测量依赖矩阵

| 软测量输出 | 依赖字段 | 缺失降级 |
|---|---|---|
| 温度校验/推断 | `temperature` + `chemistry.si/v/c` 速率 | `default_fallback` 1300℃（confidence 0.1） |
| 脱碳率 dC/dt | `off_gas.flow/CO/CO2` + `bath_weight` | 无硬数据，仅模型先验 |
| 碳含量卡尔曼修正 | `sublance.C` + 烟气反算 | 仅模型预测 |

---

## 6. 与 P3 学习闭环对接（误差回流）

`RLS/梯度下降`（`MODEL_ALGORITHM.md` §6.1）每炉需回流的最小字段集：

```
{ heat_id, iron.{Si,V,Ti,C,temp,is_one_can},
  l2_predicted.{final_temp, grade_v2o5},
  actual.{final_temp, grade_v2o5, grade_rough},
  advice_adopted }
```

漂移检测（§6.3）需连续 N 炉的 `pred_err = actual_final_temp - l2_final_temp`，阈值 `3σ`。

---

## 7. 开放问题（挂责任人，对齐 HANDOVER §6）

| # | 问题 | 责任 |
|---|---|---|
| D6-1 | 副枪 TSC/TSO 是否含 **V 测定**？若无，V 终点如何闭环 | 【数据】 |
| D6-2 | 烟气分析仪的采样周期与量程（CO 上限、响应延迟） | 【数据】 |
| D6-3 | 化验室 Si/V 结果的**送样到出数时延**（影响炉前实时性） | 【工艺】 |
| D6-4 | 现场 PLC 点表与 `resource://` URI 的一一映射确认 | 【数据】 |
| D6-5 | shadow mode 并行炉数与真实接口切换标准（对齐 HANDOVER #8） | 【安全】 |

---

*对齐：`API_DOCUMENTATION.md`（现有端点与数据模型）；`MODEL_ALGORITHM.md`（软测量/卡尔曼/自学习输入）；`HANDOVER.md` §6 #7。*
