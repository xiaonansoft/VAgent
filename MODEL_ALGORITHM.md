# Model Algorithm Documentation / 模型算法文档

This document details the mathematical models and algorithms used in the Vanadium Smelting Agent.
本文档详细介绍了钒冶炼智能体中使用的数学模型和算法。

## 1. L1 Static Model (SDM) / L1 静态模型 (SDM)
**File**: `backend/app/tools/initial_charge.py`

The Static Data Model (SDM) calculates the initial charge (coolants/additives) and total oxygen requirement based on the "Four Balances" of metallurgy.
静态数据模型 (SDM) 基于冶金学的“四大平衡”计算初始配料（冷却剂/添加剂）和总氧气需求量。

### Key Algorithms / 关键算法:
1.  **Heat Balance (Enthalpy) / 热平衡 (焓)**:
    -   **Input Heat ($Q_{in}$) / 输入热量**: Physical heat of molten iron ($C_p \approx 0.8 kJ/kg\cdot K$). "One-Can" process adds an effective +30°C.
        铁水物理热 ($C_p \approx 0.8 kJ/kg\cdot K$)。“一罐到底”工艺增加有效温度 +30°C。
    -   **Reaction Heat ($Q_{react}$) / 反应热**: Exothermic heat from oxidation of Si, V, C, Ti, Mn.
        Si, V, C, Ti, Mn 氧化的放热反应热。
        -   Si -> SiO2: 27620 kJ/kg
        -   V -> V2O3: ~15200 kJ/kg
        -   C -> CO: 9280 kJ/kg
    -   **Output Heat ($Q_{out}$) / 输出热量**: Target physical heat at end-point + Heat Loss (~5%).
        终点目标物理热 + 热损失 (~5%)。
    -   **Coolant Demand / 冷却剂需求**: Derived from Excess Heat ($Q_{excess} = Q_{in} + Q_{react} - Q_{out}$).
        源自富余热量 ($Q_{excess} = Q_{in} + Q_{react} - Q_{out}$)。

2.  **Material Balance / 物料平衡**:
    -   **Slag Weight / 渣量**: Estimated as $2.14 \times \Delta Si + 1.79 \times \Delta V$. "One-Can" adds 10% for blast furnace slag carryover.
        估算为 $2.14 \times \Delta Si + 1.79 \times \Delta V$。“一罐到底”工艺因高炉渣带入增加 10%。
    -   **Oxygen Volume / 氧气体积**: Stoichiometric calculation based on oxidized elements (Si: 0.8, V: 0.5, C: 0.93 $Nm^3/kg$).
        基于被氧化元素的化学计量计算 (Si: 0.8, V: 0.5, C: 0.93 $Nm^3/kg$)。

3.  **Strategy Rules / 策略规则**:
    -   **V/(Si+Ti) Ratio / V/(Si+Ti) 比值**: If < 1.05, mandates Oxide Scale (exothermic) instead of Coolant Scrap to promote enrichment.
        如果 < 1.05，强制使用氧化铁皮（放热）代替冷钢，以促进富集。
    -   **High Si / 高硅**: If Si > 0.25%, mandates Pig Iron to prevent splashing.
        如果 Si > 0.25%，强制使用生铁块以防止喷溅。

---

## 2. L2 Dynamic Model (ODE Simulation) / L2 动态模型 (ODE 仿真)
**File**: `backend/app/tools/kinetics_simulator.py`

The L2 model simulates the time-evolution of the molten bath using a system of Ordinary Differential Equations (ODEs).
L2 模型使用常微分方程组 (ODEs) 模拟熔池随时间的演变。

### State Variables / 状态变量:
-   $[C], [Si], [V], [Ti]$ (Concentrations in % / 浓度百分比)
-   $T$ (Temperature in °C / 温度 °C)

### Differential Equations / 微分方程:
The model solves $dy/dt = f(y, t)$ where:
模型求解 $dy/dt = f(y, t)$，其中：

1.  **Oxidation Rates ($dX/dt$) / 氧化速率**:
    -   **Silicon (Si) / 硅**: Fast initial oxidation ($k_{Si} \approx -0.0018$), slows down later.
        初始氧化快 ($k_{Si} \approx -0.0018$)，随后减慢。
    -   **Titanium (Ti) / 钛**: Similar fast kinetics to Si.
        动力学特性与硅相似，氧化快。
    -   **Vanadium (V) / 钒**: Modeled as quasi-first-order reaction, dependent on concentration.
        建模为准一级反应，取决于浓度。
    -   **Carbon (C) / 碳**: Temperature dependent. Suppressed at low T (< 1361°C), accelerates at high T.
        温度相关。低温 (< 1361°C) 时受抑制，高温时加速。

2.  **Temperature Change ($dT/dt$) / 温度变化**:
    -   $dT/dt = Heating - Cooling - Loss$
        $dT/dt = 加热 - 冷却 - 损失$
    -   **Heating / 加热**: Weighted sum of oxidation rates ($\Delta H_{reaction}$).
        氧化速率的加权和 ($\Delta H_{reaction}$)。
    -   **Cooling / 冷却**: Endothermic melting of added coolants (modeled over first 150s).
        添加冷却剂的吸热熔化（在前 150 秒内建模）。

### Critical Temperature (Tc) Prediction / 临界温度 (Tc) 预测:
-   The model identifies the crossover point where Carbon oxidation becomes thermodynamically more favorable than Vanadium oxidation (~1361°C).
    模型识别碳氧化在热力学上比钒氧化更有利的交叉点 (~1361°C)。
-   **Proactive Advice / 前瞻性建议**: If Tc occurs too early (< 200s), suggests immediate coolant addition.
    如果 Tc 出现过早 (< 200s)，建议立即添加冷却剂。

---

## 3. Process Simulator (Digital Twin) / 过程仿真器 (数字孪生)
**File**: `backend/app/data/simulator.py`

A real-time "Digital Twin" that generates streaming data for the frontend, acting as a virtual furnace.
一个为前端生成流数据的实时“数字孪生”，充当虚拟转炉。

### Features / 特性:
-   **Physics Engine / 物理引擎**: Simplified kinetic steps running at 1Hz.
    以 1Hz 运行的简化动力学步骤。
-   **Thermodynamics / 热力学**:
    -   Temperature drives reaction preference (V vs C).
        温度驱动反应偏好（钒 vs 碳）。
    -   Critical Temp (~1360°C) acts as a switch for reaction dominance.
        临界温度 (~1360°C) 充当反应主导地位的开关。
-   **Self-Learning Parameters / 自学习参数**:
    -   `heat_efficiency_factor`: Adjusts effective heat generation.
        调整有效热生成。
    -   `reaction_rate_modifier`: Global multiplier for reaction speeds.
        反应速度的全局乘数。
    -   These evolve between heats based on simulated feedback.
        这些参数根据模拟反馈在炉次之间演变。

---

## 4. Soft Sensor (Mechanism Inference) / 软测量 (机理推断)
**File**: `backend/app/data/soft_sensor.py`

Provides data reliability by validating sensors and reconstructing missing values.
通过验证传感器和重构缺失值来提供数据可靠性。

### Logic / 逻辑:
1.  **Validation / 验证**:
    -   Checks Range ($1200 < T < 1550$).
        检查范围 ($1200 < T < 1550$)。
    -   Checks Rate of Change ($< 50^\circ C/min$).
        检查变化率 ($< 50^\circ C/min$)。
2.  **Reconstruction (Mechanism Inference) / 重构 (机理推断)**:
    -   If the physical sensor fails (e.g., returns 0 or noise), the Soft Sensor takes over.
        如果物理传感器失效（例如返回 0 或噪声），软测量将接管。
    -   Uses a simplified **Heat Balance Model**:
        使用简化的**热平衡模型**：
        $$T_{next} = T_{prev} + (Heat_{Si} + Heat_{C} - Heat_{Loss}) \times dt$$
    -   Input: Reaction rates ($dSi/dt, dC/dt$) derived from gas analysis or model estimates.
        输入：源自气体分析或模型估计的反应速率 ($dSi/dt, dC/dt$)。

---

## 5. Control Strategies / 控制策略

### Lance Profile Strategy / 枪位曲线策略
**File**: `backend/app/tools/lance_profile.py`
-   **Low Si (< 0.20%)**: "Low-High-Low" pattern. Raise lance in middle phase to soften blow and protect furnace lining/promote V oxidation.
    **低硅 (< 0.20%)**: “低-高-低”模式。在中期提枪以柔和吹炼，保护炉衬并促进钒氧化。
-   **High Si (> 0.20%)**: "Constant Low" pattern. Hard blow to remove Si quickly.
    **高硅 (> 0.20%)**: “恒定低”模式。硬吹以快速脱硅。

### Thermal Balance Strategy / 热平衡策略
**File**: `backend/app/tools/thermal_balance.py`
-   Calculates specific coolant weight ($kg/t$) based on overheating degree ($\Delta T = T_{iron} - 1280$).
    根据过热度 ($\Delta T = T_{iron} - 1280$) 计算比冷却剂重量 ($kg/t$)。
-   Selects coolant type: "Ball Scrap" (Qiufan) for High Si (strong cooling), "Slag Ball" (Qizhaqiu) for Low Si (cost effective).
    选择冷却剂类型：高硅时选“球返”（强冷却），低硅时选“弃渣球”（成本效益高）。
