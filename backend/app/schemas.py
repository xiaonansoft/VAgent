from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class UnitValue(BaseModel):
    value: float
    unit: str
    ts: datetime = Field(default_factory=lambda: datetime.now(datetime.UTC))
    source: str | None = None


class IronInitialAnalysis(BaseModel):
    C: float = Field(..., ge=0, le=10.0, description="质量分数，%")
    Si: float = Field(..., ge=0, le=5.0, description="质量分数，%")
    V: float = Field(..., ge=0, le=5.0, description="质量分数，%")
    Ti: float = Field(..., ge=0, le=5.0, description="质量分数，%")
    P: float = Field(..., ge=0, le=2.0, description="质量分数，%")
    S: float = Field(..., ge=0, le=2.0, description="质量分数，%")


class SlagAnalysis(BaseModel):
    V2O5: float | None = Field(default=None, ge=0, description="质量分数，%")
    SiO2: float | None = Field(default=None, ge=0, description="质量分数，%")
    TiO2: float | None = Field(default=None, ge=0, description="质量分数，%")
    CaO: float | None = Field(default=None, ge=0, description="质量分数，%")
    TFe: float | None = Field(default=None, ge=0, description="质量分数，%")


class CoolantType(str, Enum):
    qizhaqiu = "弃渣球"
    qiufan = "球返"
    shengtie = "生铁块"
    yanghuatiepi = "氧化铁皮"


class CoolantRecommendation(BaseModel):
    coolant_type: CoolantType
    kg_per_t: float = Field(..., ge=0)
    add_within_minutes: float = Field(default=2.5, ge=0)
    notes: list[str] = Field(default_factory=list)


class LanceMode(str, Enum):
    constant_low = "恒定低枪位模式"
    low_high_low = "低-高-低模式"


class LanceStep(BaseModel):
    start_min: float = Field(..., ge=0)
    end_min: float = Field(..., ge=0)
    lance_height_mm: int = Field(..., ge=0)


class LanceProfile(BaseModel):
    mode: LanceMode
    steps: list[LanceStep]
    endgame_action: str


class CriticalTempResult(BaseModel):
    t_critical_c: float
    current_temp_c: float | None = None
    margin_c: float | None = None
    notes: list[str] = Field(default_factory=list)


class DiagnoseFinding(BaseModel):
    title: str
    severity: Literal["high", "medium", "low"]
    root_cause: str = Field(..., description="化学反应机理或热力学原因分析")
    evidence: list[str] = Field(default_factory=list)
    recommendation: list[str] = Field(default_factory=list)


class DiagnoseLowYieldResult(BaseModel):
    findings: list[DiagnoseFinding]
    notes: list[str] = Field(default_factory=list)


class ProcessData(BaseModel):
    is_one_can: bool | None = None
    tap_time_min: float | None = Field(default=None, ge=0)
    coolant_type_used: str | None = None
    coolant_structure_notes: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    # Added for Splashing Prediction
    lance_height_min: float | None = None
    final_temp_c: float | None = None
    oxygen_pressure_mpa: float | None = None


class ChatRequest(BaseModel):
    message: str
    iron_temp_c: float | None = None
    si_content_pct: float | None = None
    is_one_can: bool | None = None


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: str | None = None


class InitialChargeInputs(BaseModel):
    iron_weight_t: float = Field(..., ge=50.0, le=350.0, description="铁水重量，吨")
    iron_temp_c: float = Field(..., ge=1100.0, le=1600.0, description="铁水温度，℃")
    iron_analysis: IronInitialAnalysis
    is_one_can: bool = Field(default=True, description="是否一罐到底")
    target_temp_c: float = Field(default=1360.0, ge=1250.0, le=1600.0, description="目标终点温度，℃")
    # L1 Heat Loss Model Inputs
    ladle_transport_time_min: float = Field(default=15.0, ge=0, description="铁水包重包运输时间 (min)")
    ladle_empty_time_min: float = Field(default=30.0, ge=0, description="铁水包空包时间 (min)")
    
    # Memory / Context Correction
    prev_lining_heat: float | None = Field(default=None, description="上一炉次炉衬蓄热量")
    prev_slag_status: dict[str, float] | None = Field(default=None, description="上一炉次留渣状态")


class InitialChargeResult(BaseModel):
    recipe: dict[str, float] = Field(..., description="配料建议，单位：吨")
    oxygen_total_m3: float = Field(..., description="预计总氧量，m³")
    slag_weight_t: float = Field(..., description="预计渣量，吨")
    v_si_ti_ratio: float = Field(..., description="V/(Si+Ti) 比例")
    warnings: list[str] = Field(default_factory=list)


class SimulationInputs(BaseModel):
    initial_temp_c: float = Field(..., ge=1100.0, le=1600.0)
    initial_analysis: IronInitialAnalysis
    recipe: dict[str, float]
    oxygen_flow_rate_m3h: float = Field(default=22000.0, ge=1000.0, le=60000.0)
    duration_s: int = Field(default=360, ge=60, le=3600, description="仿真时长，秒")


class SimulationPoint(BaseModel):
    time_s: int
    temp_c: float
    C_pct: float
    Si_pct: float
    V_pct: float
    Ti_pct: float
    # Slag composition
    FeO_pct: float | None = None
    V2O5_pct: float | None = None
    SiO2_pct: float | None = None


class SimulationResult(BaseModel):
    points: list[SimulationPoint]
    tc_crossover_s: int | None = Field(default=None, description="碳钒转化点发生时间（秒）")
    final_temp_c: float
    final_analysis: dict[str, float]
    proactive_advice: str | None = Field(default=None, description="基于仿真的前瞻性操作建议")
    mode: Literal["real-data", "soft-sensing"] = Field(default="real-data")
    equilibrium_result: dict[str, Any] | None = Field(default=None, description="热力学平衡模型结果（用于交叉验证）")


class SaveHeatResultsInputs(BaseModel):
    furnace_id: str
    heat_id: str
    l1_recipe: dict[str, float]
    l2_final_temp: float
    equilibrium_final_temp: float | None = None
    actual_final_temp: float
    actual_analysis: dict[str, float]
    advice_adopted: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(datetime.UTC))


class CloudBrainState(BaseModel):
    current_step: str
    l1_result: InitialChargeResult | None = None
    l2_result: SimulationResult | None = None
    diagnosis_result: DiagnoseLowYieldResult | None = None
    timestamp: str

