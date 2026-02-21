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
    """
    findings: list[DiagnoseFinding] = []

    # 1. 钒渣品位评估 (Source 106 4)
    if slag.V2O5 is not None and slag.V2O5 < 12.5:
        findings.append(
            DiagnoseFinding(
                title="钒渣品位偏低 (V2O5 < 12.5%)",
                severity="high",
                evidence=[f"实测 V2O5 = {slag.V2O5}%"],
                recommendation=[
                    "检查来料铁水 V 含量是否发生趋势性下降。",
                    "核实吹炼过程是否过吹，导致氧化铁大量进入渣中稀释品位。",
                ],
            )
        )

    # 2. 硅稀释效应 (Si Dilution Effect)
    if iron_analysis and iron_analysis.Si > 0.25:
        findings.append(
            DiagnoseFinding(
                title="高硅稀释效应 (Si Dilution)",
                severity="medium",
                evidence=[f"入炉铁水 Si = {iron_analysis.Si}% > 0.25%"],
                recommendation=[
                    "高硅铁水会产生大量 SiO2 稀释钒渣。建议分流高硅铁水，或在前期强化撇渣操作。",
                    "后续炉次建议增加生铁块比例，减少氧化物冷却剂带来的额外造渣量。",
                ],
            )
        )

    # 3. 原料结构缺陷 (Raw Material Deficit)
    if iron_analysis:
        si_ti_sum = iron_analysis.Si + iron_analysis.Ti
        ratio = iron_analysis.V / si_ti_sum if si_ti_sum > 0 else 99.0
        if ratio < 1.01:
            findings.append(
                DiagnoseFinding(
                    title="原料结构比值失衡 (Raw Material Deficit)",
                    severity="high",
                    evidence=[f"铁水 V/(Si+Ti) = {ratio:.2f} < 1.01"],
                    recommendation=[
                        "该原料结构属于“极难富集”范畴。建议强制使用氧化铁皮或高钒块矿作为补钒手段。",
                        "严禁在此类工况下使用 SiO2 含量较高的弃渣球作为冷却剂。",
                    ],
                )
            )

    # 4. 高炉渣混入污染 (Blast Furnace Slag Contamination)
    if process.is_one_can and slag.CaO is not None and slag.CaO > 2.0:
        findings.append(
            DiagnoseFinding(
                title="高炉渣混入污染 (Slag Contamination)",
                severity="high",
                evidence=[f"工艺: 一罐到底", f"渣中 CaO = {slag.CaO}% > 2.0%"],
                recommendation=[
                    "检测到显著的高炉渣混入迹象（CaO 偏高）。高炉渣中的 CaO 会恶化钒渣流动性并降低品位。",
                    "建议核查撇渣器运行状态，或增加扒渣工序。一罐到底流程需特别注意捞渣质量。",
                ],
            )
        )

    # 5. 过程操作异常
    if process.tap_time_min is not None and process.tap_time_min < 3.5:
        findings.append(
            DiagnoseFinding(
                title="出钢时间过短，富钒渣流失风险",
                severity="medium",
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
                evidence=["各项关键指标均在 v6.0 标准区间内"],
                recommendation=["继续保持当前标准化操作流程。"],
            )
        )

    return DiagnoseLowYieldResult(
        findings=findings,
        notes=["诊断逻辑已升级至 v6.0 深度融合版。"],
    )
