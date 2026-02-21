from __future__ import annotations

from ..schemas import DiagnoseFinding, DiagnoseLowYieldResult, IronInitialAnalysis, ProcessData, SlagAnalysis


def diagnose_process_quality(
    *, 
    slag: SlagAnalysis, 
    process: ProcessData, 
    iron_analysis: IronInitialAnalysis | None = None
) -> DiagnoseLowYieldResult:
    """
    炉后诊断 (Skill 3): 基于 v6.0 PRD 逻辑对提钒过程质量进行评估。
    
    Ref: 
    1. 黑龙江建龙转炉提钒技术材料--修改--2020.6.13(1).pdf
    2. 铁水预处理提钒讲课稿[整理版](1).pdf
    """
    findings: list[DiagnoseFinding] = []

    # 1. 钒渣品位偏低 (Low V2O5)
    # Ref: 建龙技术材料 P22 "铁水Si含量在0.18%左右时，钒渣理论品位只能达到13%左右"
    if slag.V2O5 is not None and slag.V2O5 < 12.5:
        findings.append(
            DiagnoseFinding(
                title="钒渣品位偏低 (V2O5 < 12.5%)",
                severity="high",
                root_cause="V2O5被SiO2或FeO大量稀释。通常源于铁水Si过高或冷却剂（氧化铁皮/球团）加入过量导致造渣量过大。",
                evidence=[f"实测 V2O5 = {slag.V2O5}%"],
                recommendation=[
                    "检查来料铁水 V 含量是否发生趋势性下降。",
                    "核实吹炼过程是否过吹，导致氧化铁大量进入渣中稀释品位。",
                    "建议减少低品位冷却剂（如球返）使用，增加高品位氧化铁皮。",
                ],
            )
        )

    # 2. 严重碳氧化 (Severe Carbon Oxidation) -> 钒收得率下降
    # Ref: 讲课稿 P4 "低于此温度(Tc)，钒优先于碳氧化...实际吹钒温度控制在1340～1400℃"
    # Rule: Temp > 1400 and FeO < 15% (Indicates C reduction of FeO)
    if process.final_temp_c is not None and slag.TFe is not None:
        if process.final_temp_c > 1400.0 and slag.TFe < 15.0:
             findings.append(
                DiagnoseFinding(
                    title="严重碳氧化导致钒收得率下降",
                    severity="high",
                    root_cause="熔池温度超过碳钒转化温度 (Tc ~ 1360-1380℃)。\n根据 ΔG-T 图，高温下 C 与 O 亲和力超过 V，导致 C 抢夺 V2O3 中的 O，发生还原反应: 2/3 V2O3 + 2C -> 4/3 V + 2CO。",
                    evidence=[
                        f"终点温度 = {process.final_temp_c}℃ > 1400℃",
                        f"渣中 TFe = {slag.TFe}% (偏低，表明 C 还原了 FeO)"
                    ],
                    recommendation=[
                        "必须严格控制终点温度在 1380℃ 以下。",
                        "建议增加冷却剂投入量或推迟冷却剂加入时间。",
                        "缩短吹炼时间，防止后期返干。",
                    ],
                )
            )

    # 3. 喷溅预警 (Splashing)
    # Ref: 讲课稿 P13 "供氧强度...过大时喷溅严重...当氧压一定时，低枪位...易喷溅"
    # Rule: Lance < 1.0m (Too low) OR (Scale added > 500kg in one batch implied by rapid cooling needs)
    # Assuming we can detect 'rapid scale addition' via events or coolant notes.
    # Here we use Lance Height + High C oxidation potential (Temp > 1350)
    if process.lance_height_min is not None and process.final_temp_c is not None:
        if process.lance_height_min < 1100 and process.final_temp_c > 1350:
             findings.append(
                DiagnoseFinding(
                    title="喷溅风险极高",
                    severity="high",
                    root_cause="高温 (>{1350}℃) 叠加低枪位 (<1.1m) 导致碳氧反应极其剧烈 (C + O -> CO 气体)。\n大量 CO 气泡短时间内生成，造成炉渣及金属液大喷发。",
                    evidence=[
                        f"最低枪位 = {process.lance_height_min} mm",
                        f"熔池温度 = {process.final_temp_c}℃"
                    ],
                    recommendation=[
                        "立即提升枪位至 1.4m 以上，进行软吹抑制碳反应。",
                        "严禁在高温阶段集中加入氧化铁皮（会瞬间分解释放氧原子引发爆发性反应）。",
                        "适当降低供氧强度。",
                    ],
                )
            )

    # 4. 返干 (Dry Slag / Reversion)
    # Ref: 建龙 P22 "渣中低熔点相过高，渣态过稀...但在铁水Si偏高时..." 
    # Actually 'Dry Slag' usually happens with Low FeO + High Melting Point components.
    # In V-extraction, V-spinel has high melting point. If FeO is reduced by C, slag becomes dry (thick).
    # Rule: FeO < 10% and Temp > 1380 (C reduces FeO)
    if slag.TFe is not None and process.final_temp_c is not None:
        if slag.TFe < 10.0 and process.final_temp_c > 1380:
            findings.append(
                DiagnoseFinding(
                    title="炉渣返干 (Slag Reversion)",
                    severity="medium",
                    root_cause="高温促进碳还原反应，渣中 FeO 被大量消耗 (FeO + C -> Fe + CO)。\nFeO 降低导致钒尖晶石 (V2O3-FeO) 熔点升高，炉渣变稠甚至结块，包裹金属液滴阻碍反应。",
                    evidence=[
                        f"渣中 TFe = {slag.TFe}% < 10%",
                        f"温度 = {process.final_temp_c}℃ (偏高)"
                    ],
                    recommendation=[
                        "适量补加氧化铁皮提渣中 FeO。",
                        "提升枪位化渣。",
                        "避免过度追求高温出钢。",
                    ],
                )
            )

    # 5. 硅稀释效应 (Si Dilution Effect)
    if iron_analysis and iron_analysis.Si > 0.25:
        findings.append(
            DiagnoseFinding(
                title="高硅稀释效应 (Si Dilution)",
                severity="medium",
                root_cause="Si + O2 -> SiO2. 高 Si 产生大量 SiO2，显著增加渣量，按质量守恒定律稀释 V2O5 品位。",
                evidence=[f"入炉铁水 Si = {iron_analysis.Si}% > 0.25%"],
                recommendation=[
                    "高硅铁水会产生大量 SiO2 稀释钒渣。建议分流高硅铁水，或在前期强化撇渣操作。",
                    "后续炉次建议增加生铁块比例，减少氧化物冷却剂带来的额外造渣量。",
                ],
            )
        )

    # 6. 原料结构缺陷 (Raw Material Deficit)
    if iron_analysis:
        si_ti_sum = iron_analysis.Si + iron_analysis.Ti
        ratio = iron_analysis.V / si_ti_sum if si_ti_sum > 0 else 99.0
        if ratio < 1.01:
            findings.append(
                DiagnoseFinding(
                    title="原料结构比值失衡 (Raw Material Deficit)",
                    severity="high",
                    root_cause="铁水 V/(Si+Ti) 比值决定了最终渣中 V2O5 的理论极限。Si/Ti 氧化物是主要脉石成分。",
                    evidence=[f"铁水 V/(Si+Ti) = {ratio:.2f} < 1.01"],
                    recommendation=[
                        "该原料结构属于“极难富集”范畴。建议强制使用氧化铁皮或高钒块矿作为补钒手段。",
                        "严禁在此类工况下使用 SiO2 含量较高的弃渣球作为冷却剂。",
                    ],
                )
            )

    # 7. 高炉渣混入污染 (Slag Contamination)
    if process.is_one_can and slag.CaO is not None and slag.CaO > 2.0:
        findings.append(
            DiagnoseFinding(
                title="高炉渣混入污染 (Slag Contamination)",
                severity="high",
                root_cause="CaO 来源于高炉渣或石灰混入。CaO 与 V2O5 形成高熔点钒酸钙，且恶化动力学条件。",
                evidence=[f"工艺: 一罐到底", f"渣中 CaO = {slag.CaO}% > 2.0%"],
                recommendation=[
                    "检测到显著的高炉渣混入迹象（CaO 偏高）。",
                    "建议核查撇渣器运行状态，或增加扒渣工序。一罐到底流程需特别注意捞渣质量。",
                ],
            )
        )

    # 8. 过程操作异常
    if process.tap_time_min is not None and process.tap_time_min < 3.5:
        findings.append(
            DiagnoseFinding(
                title="出钢时间过短，富钒渣流失风险",
                severity="medium",
                root_cause="物理分离不充分。短时间内渣铁界面未稳定，倾动出钢时钢水易卷吸富钒渣。",
                evidence=[f"出钢时间 = {process.tap_time_min} min < 3.5 min"],
                recommendation=[
                    "出钢过快可能导致富钒渣未能有效分离而随钢水流失。",
                    "建议检查出钢口直径，并严格执行抬炉操作。",
                ],
            )
        )

    if not findings:
        findings.append(
            DiagnoseFinding(
                title="提钒过程质量受控",
                severity="low",
                root_cause="各项参数匹配良好，热力学与动力学条件适宜。",
                evidence=["各项关键指标均在 v6.0 标准区间内"],
                recommendation=["继续保持当前标准化操作流程。"],
            )
        )

    return DiagnoseLowYieldResult(findings=findings)
