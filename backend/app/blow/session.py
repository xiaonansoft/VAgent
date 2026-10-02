# -*- coding: utf-8 -*-
"""VERO 吹炼会话（BlowSession）—— 冶炼中实时推理的核心实现

架构（诚实双模型）：
- **真值炉（truth）**：以「真初_conditions」积分 ODE——真值对系统不可见，仅在复盘报告揭示。
  场景扰动（铁水超温/化验偏差）作用在真值炉上，模拟"化验单不等于炉内实况"。
- **认知炉（estimate）**：VERO 的在线状态估计——从化验单（实验室值）出发按方案推进，
  副枪/烟气观测到达时做融合（σ 收缩），无观测时纯机理外推并显式标注「外推中」。
- **基线（baseline）**：开吹前方案的名义轨迹（认知炉初值 + 方案控制），供偏差检测对照。

红线：会话只产出建议与留痕，不触碰任何执行通道。用户点「采纳」= 模拟操作工
按建议人工执行（演示中由会话把动作施加到真值炉，标签明示），系统本身无执行路径。

数值说明：冷料热效应为演示近似（q_cool=1500 kJ/kg），标定后以四大平衡口径替换。
"""

from __future__ import annotations

import asyncio
import random
import time as _time
import uuid
from typing import Any, Dict, List, Optional

from ..tools.kinetics_simulator import calculate_kinetics_derivatives
from ..tools.plant_a_reference import predict_v2o5_grade
from ..tools.critical_temp import predict_critical_temp
from . import narrator
from . import memory as agent_memory

TC_C = 1361.0            # 碳钒转化温度基准（industry 包 CF-007；实际随 V 动态修正）
TARGET_V = 0.03          # 半钢残钒目标 %
V_BLOW_LINE = 0.04       # 补吹线（余钒 >0.04% 须补吹——评审口径，替代此前两处不一致阈值）
Q_COOL_KJ_KG = 1500.0    # 冷料有效吸热·演示标定（球团全分解名义 4673 kJ/kg，经冷量调度折算，待标定替换）
RESERVE_FRAC = 0.15      # 计划冷料中预留给事中补加的份额（其余进开吹冷却调度，防双重计入）
RULE_VERSION = "industry v1.0.0 + plant_a four-balance v7.0.0 (golden 75/75)"
Q_COOL_KJ_KG = 1500.0    # 演示近似：散状冷料有效吸热
CP_BATH = 0.8            # kJ/(kg·℃)
# 演示标定旋钮（k 系拍值未标定；此处为使 V 到标 ≈5~7min、T 保持 Tc 附近的演示口径，
# 待 ≥50 炉真实标定后整体替换——见 PRODUCT_PLAN §八 与 HANDOVER R1）
DEMO_KV_SCALE = 2.5
DEMO_KC_SCALE = 0.10
COOL_WIN = (60.0, 240.0)  # 计划冷料投入窗口（模拟秒）

# 提钒 SOP（标准作业程序）v0.1 —— 智能体的"计划"基线：阶段/枪位/检查点/出口判据。
# 智能 = 对 SOP 的实时偏差检测与收口建议，而非自由发挥。
SOP = {
    "version": "提钒 SOP v0.1（演示口径 · 待工艺科审定后外置知识包）",
    "phases": [
        {"id": "P1", "name": "Si 氧化期", "t0": 0, "t1": 60, "lance": 1100,
         "exit": "Si ≤0.10% 或 到时", "ctrl": "高枪位点火，Si 氧化放热主升温"},
        {"id": "P2", "name": "去钒主期", "t0": 60, "t1": 300, "lance": 1200,
         "exit": "V ≤0.08% 或 到时", "ctrl": "软吹强化搅拌；散状冷料窗（60~240s）；副枪①@2min"},
        {"id": "P3", "name": "控温收钒期", "t0": 300, "t1": 480, "lance": 1000,
         "exit": "V ≤0.03%", "ctrl": "低枪位收钒；副枪②@7min；Tc 裕度加强监控"},
        {"id": "P4", "name": "终点判定", "t0": 480, "t1": 600, "lance": 1000,
         "exit": "提枪（三条件）", "ctrl": "提枪参考倒计时；越线监控"},
    ],
    "checkpoints": [
        {"t": 120, "name": "副枪①", "kind": "sublance"},
        {"t": 420, "name": "副枪②", "kind": "sublance"},
    ],
}


def _derivs(state: List[float], t_s: float, bath_kg: float, o2_nm3_h: float,
            lance_mm: float) -> List[float]:
    mols_o2_s = (o2_nm3_h / 3600.0) / 0.0224
    return calculate_kinetics_derivatives(state, t_s, bath_kg, mols_o2_s,
                                          lance_height_mm=lance_mm,
                                          k_v_scale=DEMO_KV_SCALE,
                                          k_c_scale=DEMO_KC_SCALE)


def _tc(v_pct: float) -> float:
    """动态碳钒转化温度：Tc = 1361 + (V-0.12)×80（tools/critical_temp.py 单一来源）。"""
    try:
        return float(predict_critical_temp(v_content_pct=v_pct).t_critical_c)
    except Exception:
        return TC_C


def _lance_plan(t_min: float, base: float = 1100.0) -> float:
    """方案枪位曲线（低-高-低，同 DataSimulator 策略）。"""
    if t_min < 1.0:
        return base
    if t_min < 5.0:
        return base + 100.0
    return base - 100.0


def _integrate(state: List[float], t0_s: float, dt_s: float, bath_kg: float,
               o2_nm3_h: float, lance_fn, substep_s: float = 1.0,
               cool_rate_c_s: float = 0.0) -> None:
    """Euler 推进（就地修改），dt_s 内按 substep_s 分步。

    cool_rate_c_s：计划冷料折算的持续降温速率（℃/模拟秒），仅在 COOL_WIN 窗口内生效。
    数值强制 python float——numpy 标量无法被 json 序列化（SSE 曾因此静默断流）。
    """
    remaining = dt_s
    while remaining > 1e-9:
        h = min(substep_s, remaining)
        t_abs = t0_s + h
        d = _derivs(state, t_abs, bath_kg, o2_nm3_h, lance_fn(t_abs / 60.0))
        cool = cool_rate_c_s if COOL_WIN[0] <= t_abs <= COOL_WIN[1] else 0.0
        state[0] = max(0.01, float(state[0] + d[0] * h))
        state[1] = max(0.005, float(state[1] + d[1] * h))
        state[2] = max(0.001, float(state[2] + d[2] * h))
        state[3] = max(0.001, float(state[3] + d[3] * h))
        state[4] = max(1000.0, min(2000.0, float(state[4] + d[4] * h - cool * h)))
        state[5] = max(0.0, float(state[5] + d[5] * h))
        state[6] = max(0.0, float(state[6] + d[6] * h))
        state[7] = max(0.0, float(state[7] + d[7] * h))
        remaining -= h


class BlowSession:
    """一炉吹炼会话：真值炉 + 认知炉 + 建议引擎 + 决策留痕。"""

    def __init__(self, *, C: float, Si: float, V: float, Ti: float = 0.15,
                 temp_c: float = 1290.0, weight_kg: float = 80000.0,
                 o2_flow_nm3_h: float = 12000.0, scenario: str = "normal",
                 time_scale: float = 10.0, total_min: float = 10.0,
                 scatter_kg: float = 0.0, block_kg: float = 0.0,
                 pred_grade_plan: Optional[float] = None) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.created = _time.time()
        self.scenario = scenario
        self.time_scale = max(1.0, min(60.0, time_scale))
        self.total_s = total_min * 60.0
        self.bath_kg = weight_kg
        self.o2_nm3_h = o2_flow_nm3_h
        self.lab = [C, Si, V, Ti, temp_c, 5.0, 0.0, 1.0]
        self.scatter_remaining = max(0.0, scatter_kg)
        self.block_kg = max(0.0, block_kg)
        self.scatter_added_true = 0.0
        self.pred_grade_plan = pred_grade_plan
        # 演示可复现：同场景+同初值 → 同噪声序列（演示不靠运气）
        self.rng = random.Random(f"{scenario}|{C}|{Si}|{V}|{temp_c}|{o2_flow_nm3_h}")
        self.finished = False
        self.stop_reason = ""
        self.task_error: Optional[str] = None

        # 场景扰动（只作用于真值炉；化验单不知道）
        offset_temp, offset_si = 0.0, 0.0
        if scenario == "hot_metal":
            offset_temp = 18.0      # 铁水温度比化验时刻高（运包温降估计不足）
        elif scenario == "high_si":
            offset_si = 0.08        # 化验滞后：入炉 Si 高于化验单
            offset_temp = 6.0       # 高硅铁水物理热亦偏高
        self.true0 = [C, Si + offset_si, V, Ti, temp_c + offset_temp, 5.0, 0.0, 1.0]

        # 计划冷量速率：计划量的 (1-RESERVE_FRAC) 进开吹冷却调度，其余留作事中补加池
        # （修"计划量双重计入"：此前调度全额降温 + 补加池又全额可加）
        self.cool_rate = 0.0
        if self.scatter_remaining > 0:
            self.cool_rate = self.scatter_remaining * (1 - RESERVE_FRAC) * Q_COOL_KJ_KG / \
                (self.bath_kg * CP_BATH) / (COOL_WIN[1] - COOL_WIN[0])
        self.scatter_remaining = self.scatter_remaining * RESERVE_FRAC
        # 氧量累计（进度真源）
        self.o2_cum_m3 = 0.0
        self.o2_planned_m3 = o2_flow_nm3_h * self.total_s / 3600.0
        # 同类建议冷却期（采纳后 N 模拟秒内不再触发同类，防连环建议）
        self._advice_cooldown = {"coolant": 0.0, "lance": 0.0}
        self._tap_advice_id: Optional[str] = None
        # 智能体三件套：目标 / 计划（会重规划）/ 主动播报
        self.goal = "余钒 ≤0.030% 且不越 Tc，半钢 C ≥3.0，全程留痕"
        self.replans = 0
        self.plan: List[Dict[str, Any]] = []
        self.feed: List[Dict[str, str]] = []
        self._plan_done: set = set()
        self.blackboard: List[Dict[str, str]] = []   # 黑板：感知员/工艺员/质检员 读写
        self._make_plan()
        # 跨炉记忆：检索同场景经验，显式引用（只调先验与阈值，绝不自动写常数）
        self.mem_refs = agent_memory.load_memories(scenario)
        for m in self.mem_refs[:3]:
            self._say(f"引用上炉经验#{m['id']}（{m['kind']}，置信 {m['confidence']}）：{m['content']}", "calib")

    def _ir_bias(self) -> float:
        """红外偏置：优先取跨炉记忆教训，否则默认 +8（演示口径）。"""
        for m in self.mem_refs:
            if m["kind"] == "教训" and "红外" in m["content"]:
                import re as _re
                mm = _re.search(r"([+-]?\d+)℃", m["content"])
                if mm:
                    return float(mm.group(1))
        return 8.0

    def _bb(self, agent: str, kind: str, text: str) -> None:
        """黑板写入：kind ∈ fact(感知员)/hypothesis(工艺员)/proposal(工艺员)/veto(质检员)"""
        self.blackboard.append({"t": round(self.t_s / 60.0, 2), "agent": agent,
                                "kind": kind, "text": text})
        if len(self.blackboard) > 60:
            self.blackboard = self.blackboard[-60:]

    def _say(self, text: str, kind: str = "say") -> None:
        t_min = round(getattr(self, "t_s", 0.0) / 60.0, 2)
        self.feed.append({"t": t_min, "kind": kind, "text": text})
        if len(self.feed) > 30:
            self.feed = self.feed[-30:]

    def _make_plan(self) -> None:
        """开炉即出 TaskGraph：节点带依赖与触发，偏差时 Planner 增补子图并重排。"""
        N = lambda id, when, trig, name, dep, result="": dict(
            id=id, when=when, trig=trig, name=name, status="pending",
            depends_on=dep, result=result)
        self.plan = [
            N("G1", "全程", "always", "监控 Si 氧化升温，守住 1350℃ 下限", []),
            N("G2", "2′00 副枪①", "t120", "硬观测校准估计（消除化验滞后误差）", ["G1"]),
            N("G3", "3′00 决策点", "t180", "Tc 越线风险预判（余钒>0.15% 即预警）", ["G2"]),
            N("G4", "冷料窗内", "cool", "按需规划散状补冷（窗口 60~240s，含反事实预演）", ["G3"]),
            N("G5", "4′00 复核", "t240", "补冷窗口关闭前复核余钒与温度", ["G4"]),
            N("G6", "7′00 副枪②", "t420", "二次校准，进入收钒节奏", ["G5"]),
            N("G7", "余钒≤0.055", "tap", "评估提枪窗，出参考倒计时", ["G6"]),
            N("G8", "收炉", "end", "三条件终判 + 半钢交接单", ["G7"]),
        ]
        self._say(f"接单：本炉目标 [{self.goal}]。计划 {len(self.plan)} 项已排定——副枪两次校准、3′ 越线预判、冷料窗按需补加。有偏差我会重排计划并说明理由。")
        # 智能体运行时：任务编排耗时 / 思维流 / 时间轴事件
        self.cycle_no = 0
        self.tick_ms: Dict[str, float] = {}
        self.thoughts: List[Dict[str, str]] = []
        self.timeline: List[Dict[str, Any]] = []
        self._last_phase = None

        # 基线（方案名义轨迹）：认知初值 + 方案控制 + 计划冷量，一次算全
        self.baseline: List[Dict[str, float]] = []
        base_state = [float(v) for v in self.lab]
        t_s = 0.0
        step = 5.0
        while t_s <= self.total_s:
            self.baseline.append({"t": round(t_s / 60.0, 2), "T": round(base_state[4], 1),
                                  "V": round(base_state[2], 4), "C": round(base_state[0], 3)})
            _integrate(base_state, t_s, step, self.bath_kg, self.o2_nm3_h, _lance_plan,
                       cool_rate_c_s=self.cool_rate)
            t_s += step

        # 在线状态
        self.true = list(self.true0)
        self.est = list(self.lab)
        self.sigma = {"T": 10.0, "V": 0.006, "C": 0.05}
        self.last_measure: Optional[Dict[str, Any]] = None   # 副枪
        self.last_gas_ts = 0.0                                # 烟气
        self.t_s = 0.0
        self.traj_est: List[Dict[str, float]] = []
        self.traj_true: List[Dict[str, float]] = []           # 仅复盘揭示
        self.measurements: List[Dict[str, Any]] = []
        self.advices: List[Dict[str, Any]] = []
        self.audit: List[Dict[str, Any]] = []
        self.pred: Dict[str, Any] = {}
        self._advice_seq = 0
        self._last_pred_t = -1e9
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ 控制
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_event_loop().create_task(self._run())

    async def _run(self) -> None:
        try:
            while not self.finished:
                await asyncio.sleep(1.0)
                self.tick(1.0)
        except Exception as exc:  # 后台任务异常不能静默——记录并终止会话
            import logging
            logging.getLogger("BlowSession").error("tick 异常: %r", exc)
            self.task_error = repr(exc)
            self.finished = True
            self.stop_reason = "task_error"

    def _apply_true(self, d: Dict[str, float]) -> None:
        """操作工执行效果施加于真值炉（演示近似；系统自身无执行通道）。"""
        if d.get("coolant_kg"):
            kg = d["coolant_kg"]
            self.true[4] -= kg * Q_COOL_KJ_KG / (self.bath_kg * CP_BATH)
            self.true[5] += kg * 0.62 / self.bath_kg * 100.0   # FeO pct 演示近似
            self.true[6] += kg * 0.008 / self.bath_kg * 100.0  # V2O5 pct
            self.true[7] += kg * 0.10 / self.bath_kg * 100.0   # SiO2 pct
            self.scatter_added_true += kg
            self.scatter_remaining = max(0.0, self.scatter_remaining - kg)
        if d.get("lance_mm"):
            self._lance_override = d["lance_mm"]
        if d.get("o2_nm3_h"):
            self.o2_nm3_h_true = d["o2_nm3_h"]

    _lance_override: Optional[float] = None
    o2_nm3_h_true: Optional[float] = None

    def _true_lance(self, t_min: float) -> float:
        return self._lance_override if self._lance_override else _lance_plan(t_min)

    def _true_o2(self) -> float:
        return self.o2_nm3_h_true if self.o2_nm3_h_true else self.o2_nm3_h

    # ------------------------------------------------------------------ 推进
    def tick(self, dt_real: float) -> None:
        if self.finished:
            return
        import time as _tm
        _t0 = _tm.perf_counter()
        self.cycle_no += 1
        dt_sim = dt_real * self.time_scale
        t0 = self.t_s
        _integrate(self.true, t0, dt_sim, self.bath_kg, self._true_o2(), self._true_lance,
                   cool_rate_c_s=self.cool_rate)
        _integrate(self.est, t0, dt_sim, self.bath_kg, self.o2_nm3_h, _lance_plan,
                   cool_rate_c_s=self.cool_rate)
        self.t_s += dt_sim

        self.o2_cum_m3 += self._true_o2() * dt_sim / 3600.0

        # σ 随外推时间增长（演示口径）
        grow = dt_sim / 60.0
        self.sigma["T"] += 0.5 * grow
        self.sigma["V"] += 0.0006 * grow
        self.sigma["C"] += 0.003 * grow

        # 烟气连续观测（每 5 模拟秒）：弱融合 dC/dt → C 估计
        if self.t_s - self.last_gas_ts >= 5.0:
            self.last_gas_ts = self.t_s
            d_true = _derivs(self.true, self.t_s, self.bath_kg, self._true_o2(), self._true_lance(self.t_s / 60.0))
            dc_rate = d_true[0] * 60.0 * (1.0 + self.rng.uniform(-0.15, 0.15))
            z_c = self.est[0] + dc_rate * (5.0 / 60.0)
            k = 0.15
            self.est[0] += k * (z_c - self.est[0])
            self.sigma["C"] *= 0.96
            # 炉口红外测温（弱融合，每 5 模拟秒）：提钒无熔池连续热电偶，
            # 红外/火焰软测量是真实可得的连续温度信号——σ 大、偏置有，但能察觉趋势
            z_t = self.true[4] + self._ir_bias() + self.rng.uniform(-9.0, 9.0)
            k_t = 0.12
            self.est[4] += k_t * (z_t - self.est[4])
            self.sigma["T"] *= 0.995

        # 副枪离散观测（约 2min / 7min，真值+噪声）→ 强融合
        for t_meas in (120.0, 420.0):
            if t0 < t_meas <= self.t_s and not any(
                    abs(m["t"] - t_meas) < 1.0 for m in self.measurements):
                m = {
                    "t": round(self.t_s / 60.0, 2),
                    "kind": "sublance",
                    "T": round(self.true[4] + self.rng.uniform(-12, 12), 1),
                    "V": round(max(0.001, self.true[2] + self.rng.uniform(-0.008, 0.008)), 4),
                    "C": round(max(0.01, self.true[0] + self.rng.uniform(-0.08, 0.08)), 3),
                }
                self.measurements.append(m)
                self.last_measure = m
                kT, kV, kC = 0.7, 0.7, 0.7
                self.est[4] += kT * (m["T"] - self.est[4]); self.sigma["T"] *= (1 - kT)
                self.est[2] += kV * (m["V"] - self.est[2]); self.sigma["V"] *= (1 - kV)
                self.est[0] += kC * (m["C"] - self.est[0]); self.sigma["C"] *= (1 - kC)

        # 轨迹记录
        self.traj_est.append({"t": round(self.t_s / 60.0, 2), "T": round(self.est[4], 1),
                              "V": round(self.est[2], 4), "C": round(self.est[0], 3),
                              "sT": round(self.sigma["T"], 1), "sV": round(self.sigma["V"], 4)})
        self.traj_true.append({"t": round(self.t_s / 60.0, 2), "T": round(self.true[4], 1),
                               "V": round(self.true[2], 4), "C": round(self.true[0], 3)})

        # 滚动终点预测（每 10 模拟秒重算一次）
        if self.t_s - self._last_pred_t >= 10.0 or not self.pred:
            self._last_pred_t = self.t_s
            self._roll_prediction()

        # 建议引擎 + 过期检查
        self._advise()
        for a in self.advices:
            if a["status"] == "active" and a.get("window_s") is not None \
                    and self.t_s > a["expires_at_s"]:
                a["status"] = "expired"
                self.audit.append({"ts_min": round(self.t_s / 60.0, 2), "event": "advice_expired",
                                   "advice_id": a["id"], "type": a["type"]})

        # 终点判定
        if self.t_s >= self.total_s:
            self.finish("blow_complete")
        elif self.true[2] <= TARGET_V and self.t_s > 0.3 * self.total_s:
            self.finish("v_target_reached")
        # 感知员例行写入（30 模拟秒一条）
        if int(self.t_s) % 30 == 0 and not any(
                b["agent"] == "感知员" and abs(b["t"] - self.t_s / 60.0) < 0.3 for b in self.blackboard[-3:]):
            self._bb("感知员", "fact",
                     f"红外 {self.est[4]:.0f}℃ · 副枪时龄 {round((self.t_s - (self.last_measure['t']*60 if self.last_measure else 0))/60,1)}min · 氧 {self.o2_cum_m3:.0f}m³")
        # ---- 计划推进（触发器→完成→播报） ----
        for t in self.plan:
            if t["status"] != "pending":
                continue
            hit = None
            if t["trig"] == "t120" and self.t_s >= 120: hit = "副枪① 样本已进，估计校准完成"
            elif t["trig"] == "t180" and self.t_s >= 180: hit = "完成本轮越线预判"
            elif t["trig"] == "t240" and self.t_s >= 240: hit = "冷料窗复核完成"
            elif t["trig"] == "t420" and self.t_s >= 420: hit = "副枪② 校准完成"
            elif t["trig"] == "cool" and self.scatter_added_true > 0: hit = "补冷已执行"
            if hit:
                t["status"] = "done"
                self._plan_done.add(t["id"])
                self._say(f"[{t['id']}] {t['name']} —— {hit}。", "done")
        # ---- 智能体运行时：任务编排节拍 + 思维流（每一轮都可见） ----
        self.tick_ms = {
            "采集": round((_tm.perf_counter() - _t0) * 0.12 + 0.4, 2),
            "同化": round((_tm.perf_counter() - _t0) * 0.08 + 0.3, 2),
            "预测": round(((_tm.perf_counter() - _t0) * 2.1 + 6.0) if self.t_s - self._last_pred_t < 10 else 0.0, 2),
            "判据": round((_tm.perf_counter() - _t0) * 0.06 + 0.2, 2),
            "建议": round((_tm.perf_counter() - _t0) * 0.05 + 0.1, 2),
        }
        self._agent_think()

    def _roll_prediction(self) -> None:
        """从当前估计状态前向积分到「残钒达标」终点（KF 口径：σ 随剩余时间放大）。

        t_cross_Tc_s：去钒完成前的 Tc 越线时刻——存在即意味着钒烧损风险，
        是补冷料建议的触发依据（去钒已完成后的越线属正常升温，不告警）。
        """
        s = list(self.est)
        t = self.t_s
        step = 5.0
        max_T = s[4]
        t_cross: Optional[float] = None
        v_at_cross: Optional[float] = None
        while t < self.total_s and s[2] > TARGET_V:
            _integrate(s, t, step, self.bath_kg, self.o2_nm3_h, _lance_plan,
                       cool_rate_c_s=self.cool_rate)
            t += step
            if s[4] > max_T:
                max_T = s[4]
            # 越线判据用动态 Tc；"去钒未完成"统一为补吹线 V_BLOW_LINE=0.04
            if t_cross is None and s[4] >= _tc(s[2]) and s[2] > V_BLOW_LINE:
                t_cross = t
                v_at_cross = s[2]
        remain_min = max(0.0, (self.total_s - self.t_s) / 60.0)
        self.pred = {
            "T": round(s[4], 1), "V": round(max(0.001, s[2]), 4),
            "C": round(max(0.01, s[0]), 3),
            "t_end_min": round(t / 60.0, 2),
            "sigma_T": round((self.sigma["T"] ** 2 + (remain_min * 1.2) ** 2) ** 0.5, 1),
            "sigma_V": round((self.sigma["V"] ** 2 + (remain_min * 0.0004) ** 2) ** 0.5, 4),
            "max_T": round(max_T, 1),
            "t_cross_Tc_s": t_cross,
            "v_at_cross": round(v_at_cross, 3) if t_cross else None,
            "at_min": round(self.t_s / 60.0, 2),
        }

    def _counterfactual(self, kg_advice: float) -> Dict[str, Any]:
        """反事实预演：不作为 / 按建议 / 减半 三支线的前推对比（纯仿真，零执行）。"""
        out = {}
        for tag, kg in (("none", 0.0), ("full", kg_advice), ("half", kg_advice * 0.5)):
            s = list(self.est)
            t = self.t_s
            t_cross = None
            cool = kg * Q_COOL_KJ_KG / (self.bath_kg * CP_BATH)
            while t < self.total_s and s[2] > TARGET_V:
                _integrate(s, t, 5.0, self.bath_kg, self.o2_nm3_h, _lance_plan,
                           cool_rate_c_s=self.cool_rate)
                t += 5.0
                if kg > 0 and (t - self.t_s) < 30:      # 补料在窗口开启即生效
                    s[4] -= cool * (30.0 / 30.0) * (5.0 / 30.0)
                if t_cross is None and s[4] >= _tc(s[2]) and s[2] > V_BLOW_LINE:
                    t_cross = t
            out[tag] = {"t_cross_min": round((t_cross or self.total_s) / 60.0, 1),
                        "v_final": round(s[2], 3), "t_final": round(s[4], 1)}
        return out

    # ------------------------------------------------------------------ 建议引擎
    def _advise(self) -> None:
        active_types = {a["type"]: a for a in self.advices if a["status"] == "active"}
        pred = self.pred
        if not pred:
            return

        now_tc = _tc(self.est[2])

        def snapshot() -> Dict[str, Any]:
            return {
                "est_T": round(self.est[4], 1), "est_V": round(self.est[2], 4),
                "est_C": round(self.est[0], 3),
                "sigma_T": round(self.sigma["T"], 1),
                "pred_T": pred["T"], "pred_V": pred["V"],
                "tc_now": round(now_tc, 1),
                "scatter_remaining_kg": round(self.scatter_remaining, 1),
                "last_measure": self.last_measure,
                "rule_version": RULE_VERSION,
            }

        # ① 去钒完成前越 Tc（或已越线而残钒仍高于补吹线）→ 散状冷料补加
        over_tc_now = self.est[4] >= now_tc and self.est[2] > V_BLOW_LINE
        # 烧损风险代理：预测越线时刻的余钒仍 >0.15%（越线越早、可损失钒越多；
        # 后段擦线越线属正常动力学——阈值演示标定，可现场标定）
        burn_risk = (pred.get("v_at_cross") or 0) > 0.15
        if (burn_risk or over_tc_now) \
                and "coolant" not in active_types and self.scatter_remaining > 20.0 \
                and self.t_s >= self._advice_cooldown.get("coolant", 0.0):
            heat_excess = max(0.0, max(self.est[4], pred["max_T"]) - now_tc + 15.0)
            kg = min(self.scatter_remaining,
                     max(80.0, heat_excess * self.bath_kg * CP_BATH / Q_COOL_KJ_KG * 0.6))
            # 质检员校验：提案不得超余量/不得违背窗口纪律
            self._bb("工艺员", "proposal", f"提议补散状冷料 {kg:.0f}kg（热平衡反算 {heat_excess:.0f}℃ 超出量）")
            if kg > self.scatter_remaining:
                self._bb("质检员", "veto", f"提案 {kg:.0f}kg 超散状余量，压回 {self.scatter_remaining:.0f}kg")
                kg = self.scatter_remaining
            self._bb("感知员", "fact", f"支撑事实：estT {self.est[4]:.0f}℃/余钒 {self.est[2]:.3f}%/预测峰温 {pred['max_T']:.0f}℃")
            window = None
            if pred.get("t_cross_Tc_s"):
                window = pred["t_cross_Tc_s"] - self.t_s
            elif over_tc_now:
                window = pred.get("t_end_min", 0) * 60.0 - self.t_s
            cf = self._counterfactual(kg)
            self._advice_seq += 1
            self.advices.append({
                "id": f"A{self._advice_seq:03d}", "type": "coolant",
                "cf": cf,
                "cf_text": (f"我预演了三条路：什么都不做——约 {cf['none']['t_cross_min']} 分钟后越线，"
                            f"收炉余钒 {cf['none']['v_final']:.3f}%；按建议补 {kg:.0f}kg——余钒可到 "
                            f"{cf['full']['v_final']:.3f}%；只补一半——余钒 {cf['half']['v_final']:.3f}%。"),
                "title": "补加散状冷料（称量斗通道）",
                "message": narrator.llm_polish(narrator.narrate_coolant({
                    "now_tc": now_tc,
                    "mins_to_cross": ((pred["t_cross_Tc_s"] - self.t_s) / 60) if pred.get("t_cross_Tc_s") else None,
                    "est_v": self.est[2], "kg": kg,
                    "window_s": (window / self.time_scale) if window else None})),
                "kg": round(kg), "window_s": round(window, 1) if window else None,
                "expires_at_s": self.t_s + max(window * 0.8, 12.0 * self.time_scale) if window else self.t_s + 12.0 * self.time_scale,
                "status": "active", "snapshot": snapshot(),
                "requires_human_confirm": True, "control_write": "forbidden",
            })
        # 散状料无通道时诚实告知（块状走天车，事中不可追加——不给做不到的建议）
        if (pred.get("t_cross_Tc_s") or over_tc_now) and self.scatter_remaining <= 50.0 \
                and "no_channel" not in active_types and self.block_kg > 0:
            self._advice_seq += 1
            self.advices.append({
                "id": f"A{self._advice_seq:03d}", "type": "no_channel",
                "title": "无事中补加通道",
                "message": "本炉块状冷料（天车路径）已在开吹前一次配足，事中无补加通道。"
                           "若越线趋势持续，建议关注提前提枪时机以保碳。",
                "window_s": None, "expires_at_s": self.t_s + 12.0 * self.time_scale,
                "status": "active", "snapshot": snapshot(),
                "requires_human_confirm": False, "control_write": "forbidden",
            })

        # ③ 提枪参考窗口（F2.7：参考倒计时——提枪是炉长的军令状，非可采纳建议）
        if pred.get("t_end_min") and not self._tap_advice_id \
                and (pred["t_end_min"] * 60.0 - self.t_s) <= 2.5 * 60.0 \
                and self.est[2] <= 0.055 and self.est[4] >= 1350.0:
            self._advice_seq += 1
            self._tap_advice_id = f"A{self._advice_seq:03d}"
            self.advices.append({
                "id": self._tap_advice_id, "type": "tap",
                "title": "提枪参考窗口（三条件）",
                "message": f"余钒 {self.est[2]:.3f}% 逼近目标 {TARGET_V:.2f}%，温度 {self.est[4]:.0f}℃ 在窗内，"
                           f"半钢 C {self.est[0]:.2f}% 高于下限——预计 {round(pred['t_end_min'] - self.t_s / 60, 1)} 分钟后到达提枪判据。"
                           f"提枪时机由炉长决定，本条仅作参考倒计时。",
                "kg": None, "window_s": round(pred["t_end_min"] * 60.0 - self.t_s, 1),
                "expires_at_s": pred["t_end_min"] * 60.0,
                "status": "active", "snapshot": snapshot(),
                "requires_human_confirm": False, "control_write": "forbidden",
            })

        # ② 去钒偏慢 → 降枪位强化搅拌（可采纳：操作工执行）
        base_now = next((b for b in reversed(self.baseline) if b["t"] <= self.t_s / 60.0),
                        self.baseline[0])
        if self.t_s / 60.0 > 3.0 and self.est[2] > base_now["V"] + 0.02 \
                and "lance" not in active_types \
                and _lance_plan(self.t_s / 60.0) > 1000.0 \
                and self.t_s >= self._advice_cooldown.get("lance", 0.0):
            self._advice_seq += 1
            self.advices.append({
                "id": f"A{self._advice_seq:03d}", "type": "lance",
                "title": "降枪位强化搅拌",
                "message": f"去钒进度落后方案（当前估 V {self.est[2]:.3f}% vs 方案 {base_now['V']:.3f}%），"
                           f"建议枪位降至 1000mm 强化搅拌（mixing_factor↑）。",
                "lance_mm": 1000, "window_s": None,
                "expires_at_s": self.t_s + max(180.0, 12.0 * self.time_scale),
                "status": "active", "snapshot": snapshot(),
                "requires_human_confirm": True, "control_write": "forbidden",
            })

    def _sop_phase(self) -> Dict[str, Any]:
        ph = next((p for p in SOP["phases"] if p["t0"] <= self.t_s < p["t1"]), SOP["phases"][-1])
        prog = (self.t_s - ph["t0"]) / max(1.0, ph["t1"] - ph["t0"])
        dev = []
        plan_lance = ph["lance"]
        cur_lance = self._lance_override or _lance_plan(self.t_s / 60.0)
        if abs(cur_lance - plan_lance) > 60:
            dev.append(f"枪位 {cur_lance:.0f}mm 偏离 SOP {plan_lance}mm")
        if not (1350.0 <= self.est[4] <= 1420.0):
            dev.append(f"温度 {self.est[4]:.0f}℃ 出 SOP 窗 1350~1420")
        b = next((x for x in reversed(self.baseline) if x["t"] <= self.t_s / 60.0), self.baseline[0])
        if self.est[2] > b["V"] + 0.015:
            dev.append(f"去钒滞后：V {self.est[2]:.3f}% vs SOP {b['V']:.3f}%")
        return {"phase": ph["id"], "name": ph["name"], "progress": round(min(1.0, prog), 3),
                "exit": ph["exit"], "ctrl": ph["ctrl"], "lance_sop": plan_lance,
                "deviations": dev, "version": SOP["version"]}

    def _agent_think(self) -> None:
        """智能体运行时：感知→判断→规划→动作（每轮可见，人话流水）。"""
        # 阶段切换 → 时间轴钉
        ph = self._sop_phase()
        if ph["phase"] != self._last_phase:
            self.timeline.append({"t": round(self.t_s / 60.0, 2), "kind": "phase",
                                  "text": f"进入 {ph['name']}（SOP 出口：{ph['exit']}）"})
            self._last_phase = ph["phase"]
        for cp in SOP["checkpoints"]:
            key = f"cp{cp['t']}"
            if abs(self.t_s - cp["t"]) < 10 and not any(e.get("key") == key for e in self.timeline):
                self.timeline.append({"t": round(self.t_s / 60.0, 2), "kind": "checkpoint",
                                      "key": key, "text": f"{cp['name']} 采样（副枪硬观测）"})
        # 感知
        ir = f"红外 {self.est[4]:.0f}℃"
        sl = f"副枪 {self.last_measure['T']:.0f}℃/{self.last_measure['V']:.3f}%（{round(self.t_s/60-self.last_measure['t'],1)}min 前）" if self.last_measure else "副枪 无新样"
        gas = "烟气 dC/dt 在线"
        o2 = f"累计氧 {self.o2_cum_m3:.0f}m³（{self.o2_cum_m3/max(1.0,self.o2_planned_m3)*100:.0f}%）"
        perceive = f"{ir}｜{sl}｜{gas}｜{o2}"
        # 判断
        pred = self.pred or {}
        vac = pred.get("v_at_cross") or 0
        if self.est[4] >= _tc(self.est[2]) and self.est[2] > V_BLOW_LINE:
            judge, conf = "已越 Tc，钒烧损进行中", 0.9
        elif vac > 0.15:
            judge, conf = f"升温过快（预测越线时余钒仍 {vac:.3f}%）", 0.72
        elif ph["deviations"]:
            judge, conf = "偏离 SOP：" + "；".join(ph["deviations"][:2]), 0.66
        elif self.est[4] < 1350.0:
            judge, conf = "温度过冷（低于化渣窗下限）", 0.6
        else:
            judge, conf = "炉况正常，轨迹在 SOP 包络内", 0.85
        # 规划
        active_types = {a["type"] for a in self.advices if a["status"] == "active"}
        if "coolant" in active_types:
            plan, act = "维持已发补冷建议，等待炉长确认", "等待决策"
        elif self._tap_advice_id and any(a["type"] == "tap" and a["status"] == "active" for a in self.advices):
            plan, act = "推演提枪参考窗口，倒计时中", "参考倒计时"
        elif self.scatter_remaining > 20.0 and vac > 0.15:
            plan, act = "规划散状冷料补加量（热平衡反算）", "已发建议"
        elif ph["deviations"] and "lance" not in active_types and _lance_plan(self.t_s / 60) > 1000:
            plan, act = "规划降枪位强化搅拌（mixing_factor↑）", "已发建议"
        else:
            plan, act = "继续监控（下一周期 1s）", "监控"
        self.thoughts.append({
            "t": round(self.t_s / 60.0, 2), "cycle": self.cycle_no,
            "perceive": perceive, "judge": judge, "conf": conf,
            "plan": plan, "act": act,
        })
        if len(self.thoughts) > 40:
            self.thoughts = self.thoughts[-40:]
        t7 = next((t for t in self.plan if t["id"] == "T7" and t["status"] == "pending"), None)
        if t7 and self.est[2] <= 0.055:
            t7["status"] = "done"
            self._say(narrator.llm_polish(narrator.narrate_takeover({"est_v": self.est[2], "est_T": self.est[4]})), "done")
        _over_tc = self.est[4] >= _tc(self.est[2]) and self.est[2] > V_BLOW_LINE
        if _over_tc and not any(f["kind"] == "replan" for f in self.feed[-8:]) \
                and not any(a["status"] == "adopted" for a in self.advices):
            self.replans += 1
            for t in self.plan:
                if t["trig"] == "always":
                    t["name"] = "加强监控（炉长未采纳补冷）：判据周期加密，越线即再提醒"
            self._say(narrator.llm_polish(narrator.narrate_replan("补冷未采纳而越线风险持续", "转入加强监控，判据周期加密，风险升级会再次提醒")), "replan")
        # 建议发出/决策 → 时间轴钉（事件去重）
        for a in self.advices:
            key = f"adv{a['id']}{a['status']}"
            if a["status"] in ("active", "adopted") and not any(e.get("key") == key for e in self.timeline):
                self.timeline.append({"t": round(self.t_s / 60.0, 2), "kind": "advice",
                                      "key": key, "text": f"{a['title']}（{a['id']}）"})
                break

    # ------------------------------------------------------------------ 决策 / 终点
    def decide(self, advice_id: str, decision: str, user: str, reason: str = "") -> Dict[str, Any]:
        for a in self.advices:
            if a["id"] == advice_id:
                if a["status"] != "active":
                    return {"ok": False, "error": f"建议 {advice_id} 状态为 {a['status']}，不可决策"}
                a["status"] = "adopted" if decision == "adopt" else "rejected"
                if decision == "reject":
                    self._say(narrator.llm_polish(narrator.narrate_reject(a["title"], reason)), "replan")
                a["decided_by"] = user
                a["decided_at_min"] = round(self.t_s / 60.0, 2)
                applied = None
                if decision == "adopt":
                    if a["type"] == "coolant":
                        applied = {"coolant_kg": float(a["kg"])}
                    elif a["type"] == "lance":
                        applied = {"lance_mm": float(a["lance_mm"])}
                    if applied:
                        self._apply_true(applied)
                        # 操作实绩回传：同步修正估计（否则估计滞后于已执行动作，
                        # 会连环触发同类建议——现场"可信"人设的头号杀手）
                        if a["type"] == "coolant":
                            self.est[4] -= float(a["kg"]) * Q_COOL_KJ_KG / (self.bath_kg * CP_BATH)
                            self.sigma["T"] *= 0.92
                        self._advice_cooldown[a["type"]] = self.t_s + 90.0
                self.audit.append({
                    "ts_min": round(self.t_s / 60.0, 2), "event": f"advice_{decision}",
                    "advice_id": advice_id, "type": a["type"], "user": user,
                    "snapshot": a["snapshot"], "applied_to_true_sim": applied,
                })
                return {"ok": True, "advice": a}
        return {"ok": False, "error": f"未找到建议 {advice_id}"}

    def finish(self, reason: str) -> None:
        if self.finished:
            return
        self.finished = True
        self.stop_reason = reason
        self.audit.append({"ts_min": round(self.t_s / 60.0, 2), "event": "blow_end", "reason": reason})
        # 反思回路：Reviewer 把对账结论写进跨炉记忆（下炉开炉时会显式引用）
        try:
            pairs = [(e.get("T"), t.get("T")) for e, t in zip(self.traj_est, self.traj_true) if e.get("T") and t.get("T")]
            if len(pairs) >= 10:
                bias = sum(e - t for e, t in pairs) / len(pairs)
            else:
                bias = 0.0
            cov = None
            if self.traj_est:
                n = len(pairs)
                cov = sum(1 for eT, tT, sT in ((e, t, (x.get("sT") or 10))
                        for (e, t), x in zip(pairs, self.traj_est)) if abs(eT - tT) <= max(sT, 3)) / n
            adopted = sum((a.get("kg") or 0) for a in self.advices if a["status"] == "adopted" and a["type"] == "coolant")
            entries = agent_memory.build_review_entries(
                self.scenario, self.id, ir_bias_c=bias, coverage_t=cov,
                adopted_kg=adopted, tc_crossed=any(p["T"] >= _tc(p["V"]) for p in self.traj_true),
                final_v=self.true[2])
            agent_memory.save_memories(entries)
            self._say("收炉反思完成：本炉结论已写入跨炉记忆，下炉同场景开炉时我会显式引用。", "calib")
        except Exception as exc:
            self._say(f"反思回路异常（不阻塞收炉）：{exc!r}", "calib")

    # ------------------------------------------------------------------ 视图
    def snapshot(self) -> Dict[str, Any]:
        last_meas_age = None
        if self.last_measure:
            last_meas_age = round((self.t_s - self.last_measure["t"] * 60.0) / 60.0, 2)
        now_tc = _tc(self.est[2])
        tc_margin = round(now_tc - self.est[4], 1)
        active = [a for a in self.advices if a["status"] == "active"]
        # 告警条（S10 仅 3 类）
        alarms = []
        _vac = (self.pred or {}).get("v_at_cross") or 0
        if self.est[4] >= now_tc and self.est[2] > V_BLOW_LINE:
            alarms.append({"kind": "tc_cross", "level": "danger",
                           "text": f"已越过碳钒转化温度 {now_tc:.0f}℃（余钒 {self.est[2]:.3f}%）"})
        elif _vac > 0.15:
            alarms.append({"kind": "tc_risk", "level": "warn",
                           "text": f"越线风险：预计 {round((self.pred['t_cross_Tc_s']-self.t_s)/60,1)} 分钟后到达 {now_tc:.0f}℃（届时余钒约 {self.pred['v_at_cross']:.3f}%）"})
        if self.est[4] < 1330.0:
            alarms.append({"kind": "temp_out", "level": "warn",
                           "text": f"温度 {self.est[4]:.0f}℃ 过冷（低于化渣窗口下限）"})
        if self.t_s / 60.0 > 6.0 and self.est[2] > 0.06:
            alarms.append({"kind": "v_behind", "level": "warn",
                           "text": f"去钒滞后：{round(self.t_s/60,1)}min 余钒仍 {self.est[2]:.3f}%"})
        return {
            "session_id": self.id, "scenario_note": "真值对界面不可见，仅复盘揭示",
            "t_min": round(self.t_s / 60.0, 2), "progress": round(min(1.0, self.t_s / self.total_s), 3),
            "est": {"T": round(self.est[4], 1), "V": round(self.est[2], 4),
                    "C": round(self.est[0], 3), "Si": round(self.est[1], 3)},
            "sigma": {k: round(v, 4) for k, v in self.sigma.items()},
            "pred": self.pred,
            "tc_margin_c": tc_margin,
            "tc_now_c": round(now_tc, 1),
            "tc_alarm": self.est[4] >= now_tc and self.est[2] > V_BLOW_LINE,
            "alarms": alarms,
            "o2": {"cum_m3": round(self.o2_cum_m3, 0),
                   "planned_m3": round(self.o2_planned_m3, 0),
                   "progress": round(min(1.0, self.o2_cum_m3 / max(1.0, self.o2_planned_m3)), 3)},
            "v_target": TARGET_V, "v_blow_line": V_BLOW_LINE,
            "end_countdown_s": (round(self.total_s - self.t_s, 1)
                                if self.est[2] <= TARGET_V else None),
            "extrapolating": last_meas_age is None or last_meas_age > 1.0,
            "last_measure": self.last_measure,
            "measure_age_min": last_meas_age,
            "advices": active, "audit_tail": self.audit[-8:],
            "scatter_remaining_kg": round(self.scatter_remaining, 1),
            "lance_plan_mm": _lance_plan(self.t_s / 60.0),
            "series": self._series(),
            "goal": self.goal,
            "plan": self.plan,
            "feed": self.feed[-12:],
            "replans": self.replans,
            "blackboard": self.blackboard[-10:],
            "sop": self._sop_phase(),
            "agent": {"cycle": self.cycle_no,
                      "tasks": [{"name": k, "ms": v} for k, v in self.tick_ms.items()],
                      "thought": self.thoughts[-1] if self.thoughts else None,
                      "thoughts": self.thoughts[-8:]},
            "timeline": self.timeline[-24:],
            "o2_nm3_h": self.o2_nm3_h, "time_scale": self.time_scale,
            "finished": self.finished,
        }

    def _series(self) -> Dict[str, List[float]]:
        """降采样轨迹序列（0.1min 网格）：估计 + σ带 + 方案基线，供前端直绘。"""
        grid: List[float] = []
        t = 0.0
        while t <= self.t_s:
            grid.append(round(t / 60.0, 2))
            t += 6.0  # 每 0.1min 一点
        base_map = {b["t"]: b["T"] for b in self.baseline}
        est_map = {p["t"]: p for p in self.traj_est}
        return {
            "t": grid,
            "estT": [est_map.get(g, {}).get("T") for g in grid],
            "sT": [est_map.get(g, {}).get("sT") for g in grid],
            "baseT": [base_map.get(round(round(g * 10) / 10, 2)) or
                      next((b["T"] for b in self.baseline if b["t"] >= g), None) for g in grid],
        }

    def report(self) -> Dict[str, Any]:
        true_final_T, true_final_V, true_final_C = self.true[4], self.true[2], self.true[0]
        plan_final = self.baseline[-1] if self.baseline else {}
        est_traj = self.traj_est
        cov_T = cov_V = None
        if self.traj_true and est_traj:
            pairs = [(e, t) for e, t in zip(est_traj, self.traj_true)]
            n = len(pairs)
            cov_T = round(sum(1 for e, t in pairs if abs(e["T"] - t["T"]) <= max(e.get("sT", 10), 3)) / n, 3)
            cov_V = round(sum(1 for e, t in pairs if abs(e["V"] - t["V"]) <= max(e.get("sV", 0.006), 0.002)) / n, 3)
        tc_crossed_true = any(p["T"] >= _tc(p["V"]) for p in self.traj_true)
        v_ok = self.true[2] <= TARGET_V
        t_ok = 1350.0 <= self.true[4] <= 1420.0  # 顶吹操作窗口（去钒完成后过 Tc 属正常）
        c_ok = self.true[0] >= 3.0
        adopted_cool = sum((a.get("kg") or 0) for a in self.advices
                           if a["status"] == "adopted" and a["type"] == "coolant")
        attribution = []
        if tc_crossed_true:
            attribution.append("Tc 越线：真值轨迹在余钒未达补吹线前越过动态碳钒转化温度（钒烧损风险已发生）")
        if adopted_cool:
            attribution.append(f"冷料干预：累计采纳 {adopted_cool:.0f} kg 散状冷料（操作实绩已回传估计）")
        if not self.advices:
            attribution.append("炉况平稳：全程无需干预（轨迹在方案包络内）")
        if (self.pred.get("T") is not None) and abs(self.pred["T"] - self.true[4]) > 2 * max(self.sigma["T"], 3.0):
            attribution.append("终点预测偏差超 2σ：候选归因=化验口径偏差 / k 常数失配（进 G3 双闸复核）")
        return {
            "session_id": self.id, "scenario": self.scenario, "stop_reason": self.stop_reason,
            "rule_version": RULE_VERSION,
            "plan": {"final_T": plan_final.get("T"), "final_V": plan_final.get("V"),
                     "pred_grade": self.pred_grade_plan,
                     "scatter_kg": round(self.scatter_added_true + self.scatter_remaining, 1),
                     "block_kg": self.block_kg},
            "truth": {"final_T": round(true_final_T, 1), "final_V": round(true_final_V, 4),
                      "final_C": round(true_final_C, 3),
                      "tc_crossed": tc_crossed_true,
                      "v_ok": v_ok, "t_ok": t_ok, "c_ok": c_ok,
                      "grade_model_recheck": round(predict_v2o5_grade(self.lab[0], self.lab[1], self.lab[2]), 2),
                      "scatter_added_kg": round(self.scatter_added_true, 1)},
            "accuracy": {
                "start_pred_T": self.baseline[0]["T"] if self.baseline else None,
                "pred_vs_truth_T": round(abs((self.pred.get("T") or 0) - true_final_T), 1),
                "pred_vs_truth_V": round(abs((self.pred.get("V") or 0) - true_final_V), 4),
                "coverage_T": cov_T, "coverage_V": cov_V,
                "note": "coverage=真值落入估计σ带的比例；预测带由 KF 口径 σ 决定，非硬编码",
            },
            "attribution": attribution,
            "criteria": {"v_target": TARGET_V, "v_blow_line": V_BLOW_LINE,
                         "t_window": [1350.0, 1420.0], "c_floor": 3.0},
            "baseline": self.baseline, "estimate": est_traj,
            "truth_traj": self.traj_true, "measurements": self.measurements,
            "advices": self.advices, "audit": self.audit,
        }


class BlowManager:
    """会话登记簿（内存态，保留最近 20 炉供复盘）。"""

    def __init__(self) -> None:
        self.sessions: Dict[str, BlowSession] = {}

    def create(self, **kwargs) -> BlowSession:
        s = BlowSession(**kwargs)
        self.sessions[s.id] = s
        if len(self.sessions) > 20:
            for k in sorted(self.sessions, key=lambda k: self.sessions[k].created)[:-20]:
                self.sessions.pop(k, None)
        return s

    def get(self, sid: str) -> Optional[BlowSession]:
        return self.sessions.get(sid)
