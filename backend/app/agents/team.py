from __future__ import annotations

from typing import Any, List
from pydantic import ValidationError

from ..schemas import (
    InitialChargeInputs, 
    IronInitialAnalysis, 
    SimulationInputs,
    SaveHeatResultsInputs
)
from ..tools.initial_charge import calculate_initial_charge
from ..tools.kinetics_simulator import simulate_blow_path
from ..tools.equilibrium_model import calculate_equilibrium_state
from ..tools.lance_profile import recommend_lance_profile
from ..tools.critical_temp import predict_critical_temp
from ..knowledge_base import query_knowledge
from .core import BaseAgent, AgentResult

class ChargingAgent(BaseAgent):
    def __init__(self):
        super().__init__("配料专家", "L1 静态配料 (SDM)")

    async def _execute(self, context: dict) -> AgentResult:
        si = context.get("si")
        temp = context.get("temp")
        is_one_can = context.get("is_one_can")
        
        iron_analysis = IronInitialAnalysis(C=4.2, Si=si, V=0.28, Ti=0.1, P=0.08, S=0.03)
        l1_inp = InitialChargeInputs(
            iron_weight_t=80.0,
            iron_temp_c=temp,
            iron_analysis=iron_analysis,
            is_one_can=is_one_can
        )
        l1_res = calculate_initial_charge(l1_inp)
        
        lines = []
        lines.append(f"推荐配方：")
        for item, weight in l1_res.recipe.items():
            lines.append(f"   - {item}：{weight} 吨")
        lines.append(f"   - 预计总氧量：{l1_res.oxygen_total_m3} m³")
        lines.append(f"   - 预计渣量：{l1_res.slag_weight_t} 吨")
        for warning in l1_res.warnings:
            lines.append(f"   - 提示：{warning}")
            
        return AgentResult(
            agent_name=self.name,
            role=self.role,
            content="\n".join(lines),
            data={"l1_res": l1_res, "recipe": l1_res.recipe, "iron_analysis": iron_analysis},
            tool_calls=[{"name": "calculate_initial_charge", "arguments": l1_inp.model_dump(mode="json")}]
        )

class SimulationAgent(BaseAgent):
    def __init__(self):
        super().__init__("仿真专家", "L2 动态过程推演 (ODE)")

    async def _execute(self, context: dict) -> AgentResult:
        temp = context.get("temp")
        iron_analysis = context.get("iron_analysis")
        recipe = context.get("recipe")
        
        if not all([temp, iron_analysis, recipe]):
            return AgentResult(agent_name=self.name, role=self.role, content="缺少必要参数，无法进行仿真。")

        l2_inp = SimulationInputs(
            initial_temp_c=temp,
            initial_analysis=iron_analysis,
            recipe=recipe
        )
        
        # Offload ODE solver to thread to avoid blocking asyncio loop
        import asyncio
        l2_res = await asyncio.to_thread(simulate_blow_path, l2_inp)
        
        # Run Equilibrium Model (Cross-Validation)
        l2_eq_res = calculate_equilibrium_state(l2_inp)
        l2_res.equilibrium_result = l2_eq_res
        
        lines = []
        lines.append(f"预计终点温度：{l2_res.final_temp_c}℃ (动力学)")
        lines.append(f"理论极限温度：{l2_eq_res['final_temp_c']}℃ (热力学平衡)")
        lines.append(f"预计终点残 V：{l2_res.final_analysis['V']}%")
        
        if l2_res.tc_crossover_s:
            lines.append(f"关键预警：碳钒转化点 (Tc) 预计在 {l2_res.tc_crossover_s}秒 处发生。")
        
        # Compare Kinetic vs Equilibrium
        temp_diff = abs(l2_res.final_temp_c - l2_eq_res['final_temp_c'])
        if temp_diff > 50:
             lines.append(f"【模型偏差警告】动力学与平衡态温度偏差 {temp_diff:.1f}℃，建议检查反应速率系数或热效率。")
            
        return AgentResult(
            agent_name=self.name,
            role=self.role,
            content="\n".join(lines),
            data={"l2_res": l2_res, "l2_eq_res": l2_eq_res},
            tool_calls=[{"name": "simulate_blow_path", "arguments": l2_inp.model_dump(mode="json")}]
        )

class LanceAgent(BaseAgent):
    def __init__(self):
        super().__init__("枪位专家", "枪位推荐与操作指令")

    async def _execute(self, context: dict) -> AgentResult:
        si = context.get("si")
        lp = recommend_lance_profile(si_content_pct=si)
        
        lines = []
        lines.append(f"吹炼模式：{lp.mode.value}")
        steps_str = " -> ".join([f"{s.lance_height_mm}mm({s.start_min}-{s.end_min}min)" for s in lp.steps])
        lines.append(f"枪位路径：{steps_str}")
        lines.append(f"终点提示：{lp.endgame_action}")
        
        return AgentResult(
            agent_name=self.name,
            role=self.role,
            content="\n".join(lines),
            data={"lance_profile": lp},
            tool_calls=[]
        )

class SafetyAgent(BaseAgent):
    def __init__(self):
        super().__init__("安全专家", "热力学实时评估")

    async def _execute(self, context: dict) -> AgentResult:
        simulator = context.get("simulator")
        if not simulator:
            return AgentResult(agent_name=self.name, role=self.role, content="无法连接模拟器")
            
        crit = predict_critical_temp(v_content_pct=None, current_temp_c=simulator.state.temp_c)
        
        lines = []
        lines.append(f"当前熔池温度：{simulator.state.temp_c:.1f}℃")
        lines.append(f"临界转化点 (Tc)：{crit.t_critical_c:.1f}℃")
        lines.append(f"温度裕度 (T-Tc)：{crit.margin_c:.1f}℃")
        
        if crit.margin_c is not None:
            if crit.margin_c >= -3:
                status_msg = "【警告】温度已逼近临界点" if crit.margin_c < 0 else "【严正警告】温度已超临界"
                lines.append(f"状态评估：{status_msg}")
                lines.append("应急预案：立即停止提枪，投加压温料（生铁块/氧化铁皮），强化底吹搅拌。")
        
        # 工艺窗口智能监控 (Process Window Monitoring)
        # 黄金区间: 1340 ~ 1400°C (Ref: 铁水预处理提钒讲课稿)
        curr_temp = simulator.state.temp_c
        if curr_temp < 1340:
            lines.append("【工艺偏差】温度偏低 (<1340℃)。建议：提高供氧强度或减少冷却剂，防止钒氧化率降低。")
        elif curr_temp > 1400:
            lines.append("【工艺偏差】温度偏高 (>1400℃)。建议：投入生铁块/氧化铁皮压温，防止碳大量氧化。")
        else:
            lines.append("【工艺达标】温度处于 1340~1400℃ 黄金提钒区间。")
        
        return AgentResult(
            agent_name=self.name,
            role=self.role,
            content="\n".join(lines),
            data={"critical_temp": crit},
            tool_calls=[{"name": "predict_critical_temp", "arguments": {"current_temp_c": simulator.state.temp_c}}]
        )

class KnowledgeAgent(BaseAgent):
    def __init__(self):
        super().__init__("知识库专家", "专家经验引用 (RAG)")

    async def _execute(self, context: dict) -> AgentResult:
        message = context.get("message", "")
        si = context.get("si")
        temp = context.get("temp")
        
        knowledge_hits = query_knowledge(message)
        if not knowledge_hits and si is not None:
            if si < 0.20: knowledge_hits += query_knowledge("低硅")
            if temp and temp > 1350: knowledge_hits += query_knowledge("1361")
            
        lines = []
        if knowledge_hits:
            for hit in knowledge_hits[:2]:
                lines.append(f"【{hit['topic']}】依据 {hit['id']}：{hit['content']}")
        
        return AgentResult(
            agent_name=self.name,
            role=self.role,
            content="\n".join(lines) if lines else "",
            data={"hits": knowledge_hits},
            tool_calls=[]
        )

class CoordinatorAgent(BaseAgent):
    def __init__(self):
        super().__init__("指挥官", "任务调度与整合")
        self.charging_agent = ChargingAgent()
        self.simulation_agent = SimulationAgent()
        self.lance_agent = LanceAgent()
        self.safety_agent = SafetyAgent()
        self.knowledge_agent = KnowledgeAgent()

    async def run(self, context: dict) -> dict:
        # Initialize Trace ID
        from app.core.logger import generate_trace_id, get_trace_id
        tid = get_trace_id()
        if not tid:
            tid = generate_trace_id()
            
        self.logger.info("CoordinatorAgent starting execution", extra={"trace_id": tid})

        # Check required inputs
        si = context.get("si_content_pct")
        temp = context.get("iron_temp_c")
        is_one_can = context.get("is_one_can")
        simulator = context.get("simulator")
        message = context.get("message")
        
        results = []
        tool_calls = []

        # 0. Safety Check (Always runs if simulator is available)
        res_safety = None
        if simulator:
            res_safety = await self.safety_agent.run(context)
        
        # 1. Parameter Check
        if si is None or temp is None or is_one_can is None:
            reply_lines = []
            reply_lines.append("提钒专家团队已就绪。为了提供精确的冶炼计算建议，请提供以下核心参数：")
            reply_lines.append("- [Si] 含量 (si_content_pct)")
            reply_lines.append("- 入炉铁水温度 (iron_temp_c)")
            reply_lines.append("- 工艺类型 (is_one_can)")
            reply_lines.append("\n示例输入：{\"iron_temp_c\": 1340, \"si_content_pct\": 0.28, \"is_one_can\": true}")
            
            if res_safety and res_safety.content:
                 reply_lines.append(f"\n### {res_safety.agent_name} ({res_safety.role})")
                 for line in res_safety.content.split('\n'):
                     reply_lines.append(f"   {line}")
            
            return {
                "reply": "\n".join(reply_lines),
                "tool_calls": res_safety.tool_calls if res_safety else [],
                "trace_id": tid
            }
            
        agent_context = {
            "si": si,
            "temp": temp,
            "is_one_can": is_one_can,
            "simulator": simulator,
            "message": message
        }

        safe_mode_active = False
        safe_mode_reasons = []

        # 2. Run Agents
        # L1 Charging
        try:
            res_l1 = await self.charging_agent.run(agent_context)
            results.append(res_l1)
            tool_calls.extend(res_l1.tool_calls)
            
            # Update context for L2
            agent_context.update(res_l1.data)
        except (ValidationError, Exception) as e:
            safe_mode_active = True
            safe_mode_reasons.append(f"配料计算失败: {str(e)}")
            # Fallback Recipe
            fallback_recipe = {"生铁块": 5.0, "氧化铁皮": 1.0}
            fallback_res = AgentResult(
                agent_name=self.charging_agent.name,
                role=self.charging_agent.role,
                content="【安全模式】模型计算异常，启用应急配方：\n   - 生铁块：5.0 吨\n   - 氧化铁皮：1.0 吨",
                data={"l1_res": None, "recipe": fallback_recipe, "iron_analysis": None},
                tool_calls=[]
            )
            results.append(fallback_res)
            agent_context["recipe"] = fallback_recipe
            # Provide dummy analysis if missing - Use safe hardcoded values to prevent secondary validation errors
            if "iron_analysis" not in agent_context:
                agent_context["iron_analysis"] = IronInitialAnalysis(C=4.2, Si=0.20, V=0.28, Ti=0.1, P=0.08, S=0.03)

        # L2 Simulation
        try:
            if safe_mode_active:
                raise Exception("由于上游配料异常，跳过动态仿真。")
                
            res_l2 = await self.simulation_agent.run(agent_context)
            results.append(res_l2)
            tool_calls.extend(res_l2.tool_calls)
        except (ValidationError, Exception) as e:
            if not safe_mode_active: # Only log if it wasn't skipped intentionally
                 safe_mode_reasons.append(f"仿真推演失败: {str(e)}")
            # Fallback (Skip)
            fallback_res = AgentResult(
                agent_name=self.simulation_agent.name,
                role=self.simulation_agent.role,
                content=f"【安全模式】仿真模块未启动 ({str(e)})",
                data={"l2_res": None},
                tool_calls=[]
            )
            results.append(fallback_res)

        # Lance Profile
        try:
            res_lance = await self.lance_agent.run(agent_context)
            results.append(res_lance)
        except (ValidationError, Exception) as e:
            safe_mode_active = True
            safe_mode_reasons.append(f"枪位推荐失败: {str(e)}")
            # Fallback Lance
            fallback_res = AgentResult(
                agent_name=self.lance_agent.name,
                role=self.lance_agent.role,
                content="【安全模式】枪位推荐异常，建议：\n   - 保持恒定枪位 1200mm",
                data={"lance_profile": None},
                tool_calls=[]
            )
            results.append(fallback_res)

        # Safety (Already ran, include it here)
        if res_safety:
            results.append(res_safety)
            tool_calls.extend(res_safety.tool_calls)
        
        # Knowledge
        res_know = await self.knowledge_agent.run(agent_context)
        if res_know.content:
            results.append(res_know)
            
        # 3. Format Output
        final_reply = [f"【冶炼决策建议 v7.0 - 多智能体协同模式】"]
        final_reply.append(f"当前工况：[Si] {si:.3f}%，铁水温度 {temp:.1f}℃，工艺：{'一罐到底' if is_one_can else '非一罐到底'}。")
        
        for res in results:
            if not res.content: continue
            final_reply.append(f"\n### {res.agent_name} ({res.role})")
            # Indent content slightly
            for line in res.content.split('\n'):
                final_reply.append(f"   {line}")
                
        self.logger.info("CoordinatorAgent completed successfully", extra={"trace_id": tid})
        
        return {
            "reply": "\n".join(final_reply),
            "tool_calls": tool_calls,
            "trace_id": tid
        }
