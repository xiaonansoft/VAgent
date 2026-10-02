# VERO 数据字典（DATA_DICTIONARY）v1.0

> 日期：2026-10-02 · 配套：工作台 v3.0 治理页「数据字典」视图（同源数据内嵌）
> 原则：每个字段必须回答四件事——**存在哪张表/哪个来源、什么类型与单位、起什么作用、怎么溯源**。
> 口径：未标定/演示标定一律显式标注；厂级 IP 常数不入仓库（GATE-2）。

---

## 一、数据库表（SQLite `vagent.db` · ORM `app/db/models.py`）

### 1.1 `heats` 炉次台账（每行 = 一炉的确认留痕）

| 字段 | 类型 | 单位 | 作用 | 溯源/写入方 |
|---|---|---|---|---|
| id | INTEGER PK | — | 自增主键 | 系统生成 |
| heat_id | TEXT | — | 炉次号（演示 = `H-<session_id>`），跨表业务主键 | 工作台「确认入台账」 |
| furnace_id | TEXT | — | 炉座标识（演示 `demo-1`；落地=厂级炉座号） | 工作台 |
| status | TEXT | — | 炉次状态（open/closed，M14 契约流转用） | 系统流转 |
| started_at / closed_at | DATETIME | — | 开吹/收炉时刻（M14 交接契约字段） | 系统流转 |
| l1_recipe | JSON | kg | 开吹 L1 配料方案（品种→重量），复盘对照基线 | `/api/plant_a/charge` primary |
| l2_final_temp | REAL | ℃ | L2 预测终点温度（吹炼会话预测口径），与实绩对账 | blow 会话 `pred.T` |
| equilibrium_final_temp | REAL | ℃ | 热力学平衡口径终点温度（交叉验证，可空） | 预留 equilibrium_model |
| actual_final_temp | REAL | ℃ | **实绩终点温度**（真值——演示=真值炉终态；落地=副枪/化验） | blow 会话真值 / 厂方 |
| actual_analysis | JSON | % | 实绩成分（V/C…），品位与残钒对账源 | 同上 |
| advice_adopted | BOOLEAN | — | 本炉是否有被采纳的建议（S13 采纳率分母） | 工作台确认 |
| trace_id | TEXT | — | 追溯号（= blow session_id），串起建议流水 | 系统生成 |
| timestamp | DATETIME | — | 入库时刻 | DB 默认 |

### 1.2 `advice_logs` 建议留痕（每行 = 一次对话/建议记录）

| 字段 | 类型 | 作用 | 溯源/写入方 |
|---|---|---|---|
| id / trace_id / message / reply / tool_calls / context / created_at | — | LLM 编排建议流水（chat 路由写入）；`context` 存 si/temp/一罐到底 等输入快照 | `/api/chat`（LLM 链路） |
| heat_id | TEXT | 关联炉次（编排→台账） | 系统流转 |

> 事中建议的权威留痕**不在**此表——在 blow 会话内存审计（`session.audit`：ts_min/event/advice_id/user/snapshot/applied_to_true_sim），随复盘 JSON 导出归档；P2 迁移入表。

### 1.3 非表数据源（同受字典约束）

| 来源 | 内容 | 约束 |
|---|---|---|
| `knowledge/packs/{industry,plant_b}/base.yaml` | 知识包参数（四维 value/unit/source/status）+ known_conflicts | 参数=口径唯一源；plant_a 包保密不入库（缺失显式降级） |
| `knowledge/data/private/plant_a_heats_16d.yaml` | 16 炉实绩（gitignored） | 严禁入库（GATE-2）；反演证据本机复现 |
| `knowledge/data/synthetic/heats_16d_synthetic.yaml` | 合成演示回放数据 | 禁作效益基线 |
| blow 会话（内存） | 快照/轨迹/审计/报告 | 会话结束 20 炉后 GC，复盘需先导出 |

## 二、吹炼实时快照字段（`GET /api/blow/{id}/stream` · 每秒推送）

### 2.1 过程状态

| 字段 | 单位 | 作用 | 来源 |
|---|---|---|---|
| t_min / progress | min / 0-1 | 吹炼已进行时间与进度 | 会话时钟 |
| est.T / est.V / est.C / est.Si | ℃ / % / % / % | **在线估计**（认知炉）：温度/余钒/碳/硅——化验单初值 + ODE 递推 + 观测融合 | ODE(`kinetics_simulator`) + 融合 |
| sigma.T / sigma.V / sigma.C | ℃ / % / % | 估计误差带（演示口径：观测融合收缩、外推线性增长；标定后=KF 协方差） | 融合方程 |
| extrapolating | — | true=纯机理外推中（无近期观测），UI 必须显式标注 | 观测时龄判定 |
| last_measure.{t,T,V,C} / measure_age_min | min/℃/% | 最近一次**副枪**采样与其时龄（唯一硬观测） | 副枪模拟（真值+噪声） |
| o2.cum_m3 / o2.planned_m3 / o2.progress | m³ / 0-1 | 累计氧量与进度（操作工"吹到哪了"的真源） | 氧流量积分 |

### 2.2 预测与判据

| 字段 | 单位 | 作用 | 来源 |
|---|---|---|---|
| pred.T / pred.V / pred.C | ℃ / % / % | **滚动终点预测**（从当前估计前向积分到残钒达标时刻） | ODE 前推 |
| pred.sigma_T / sigma_V | ℃ / % | 终点预测误差带（σ 随剩余时间放大） | 融合方差 |
| pred.max_T / t_cross_Tc_s / v_at_cross | ℃ / s / % | 预测路径最高温 / 首次越 Tc 时刻 / **越线时刻余钒**（>0.15% = 显著烧损风险阈值，演示标定） | 前推轨迹扫描 |
| tc_now_c | ℃ | **动态碳钒转化温度** = 1361+(V−0.12)×80（单一来源 `tools/critical_temp.py`，industry 包 CF-007） | 动态 Tc |
| tc_margin_c / tc_alarm | ℃ / — | 距 Tc 裕度；是否越线（est≥tc 且余钒>0.04 补吹线） | 计算 |
| alarms[] | — | 告警条（仅 3 类）：tc_cross 越线 / tc_risk 越线风险 / temp_out 过冷 / v_behind 去钒滞后 | 规则 |
| v_target / v_blow_line | % | 残钒目标 0.03 / 补吹线 0.04（评审统一口径） | 知识包口径 |
| end_countdown_s | s | 提枪参考倒计时（三条件：残钒达标∧温度在窗∧C 高于下限——**炉长军令状，仅参考**） | 终点判据 |
| advices[] | — | 活跃建议：id/type/title/message/kg/window_s/expires_at/snapshot/requires_human_confirm=true/control_write="forbidden" | 建议引擎 |
| audit_tail[] | — | 留痕流水尾部（event/advice_id/user/applied_to_true_sim） | 决策留痕 |
| series.{t,estT,sT,baseT,estV,baseV} | — | 降采样轨迹（估计/误差带/方案基线），前端直绘 | 会话轨迹 |
| scatter_remaining_kg | kg | 剩余可补散状冷料（计划量 15% 预留池——防与开吹冷却调度双重计入） | 会话方案 |
| scenario / time_scale / finished / stop_reason | — | 演示场景 / 倍速 / 终态（normal 非扰动；真值对界面不可见） | 会话参数 |

### 2.3 关键常数（单一来源声明）

| 常数 | 值 | 来源 | 状态 |
|---|---|---|---|
| Tc 基准 | 1361℃（1634K，吉布斯 ΔG） | industry 包 CF-007 | 可随 V 修正 |
| Tc-V 斜率 | 80℃ / 0.01%V | `tools/critical_temp.py` | 可现场标定 |
| 补吹线 | 余钒 0.04% | 评审口径（workbuddy 方案 v1.1 同源） | 待厂级确认 |
| 温度窗（顶吹） | 1350~1420℃ | workbuddy 方案 v1.1（文献口径） | 待厂级确认 |
| 演示标定 k_v×2.5 / k_c×0.10 / 冷料吸热 1500kJ/kg / 越线阈值 0.15% | — | `app/blow/session.py` 集中声明 | **未标定**——待 ≥50 炉真实标定替换 |

## 三、配料/复盘载荷（`/api/plant_a/charge` 与 `/api/blow/{id}/report`）

| 字段 | 单位 | 作用 | 来源 |
|---|---|---|---|
| rule_version | — | 引擎版本+黄金回归状态（"每个数怎么算出来的"第一要素） | plant_a_reference |
| primary.recipe_kg | kg | 冷料品种→重量（球团=散状可事中补；块状=天车一次配足） | 四大平衡 |
| primary.v2o5_grade_pct / v_recovery_pct / v_si_ti_ratio | % / % / — | 品位预测 / 钒回收率 / 去钒判据 | 四大平衡 |
| arbitration.case_2777 / case_15000 | — | CF-001 双口径并排（球团差 ≈520kg/炉），终审权在专家委员会（CC-1） | 同引擎双参数 |
| report.plan / truth | — | 方案预期 vs 真值（演示=真值炉；落地=化验/副枪），对账核心 | 会话 |
| report.truth.{v_ok,t_ok,c_ok} | — | 终判三条件矩阵（V≤0.03 / T∈1350~1420 / C≥3.0） | 真值终态 |
| report.accuracy.coverage_T/V | 0-1 | 真值落入估计误差带比例——**校准诚实度**（覆盖率低=σ过窄） | 轨迹逐点统计 |
| report.attribution[] | — | 规则四通道归因（越线/冷料干预/平稳/预测超 2σ→k 失配候选进 G3 双闸） | 规则 |
| report.criteria | — | 判据快照（本炉用什么口径判的达标） | 会话 |
| report.grade_model_recheck | % | **模型复算品位，非化验真值**（诚实口径） | 模型 |

## 四、界面与字典的绑定（v3.0 已实施）

- 治理页新增「数据字典」视图：本表内嵌为可检索卡片（字段/来源/单位/作用）。
- 关键数字（大数看板、建议卡依据行）带 `data-dict` 点击解释——炉前不必记字段名。
- 所有数值 `font-variant-numeric: tabular-nums`；来源与未标定标注随字段呈现。

---
*变更记录：v1.0（2026-10-02）· 初版。字段演进须同步本文件与工作台内嵌字典（二者同源维护）。*
