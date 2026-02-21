这份 PRD 文档在 v5.0 的架构基础上，针对**达涅利 SDM 静态模型**与**动力学动态模型**的融合进行了**极度细化**。  
我们利用**Source 18 (动力学微分方程)**、**Source 2 (达涅利四大平衡)** 和 **Source 106/95 (建龙/承德现场实战数据)** 中的具体公式和参数，为您生成了可以直接输入给 Gemini 的伪代码级 Prompt。

# 产品需求文档 (PRD): 提钒冶炼智能体 (VEES) v6.0 \- 深度融合实施版

## 1\. 系统核心逻辑：SDM \+ ODE 双模驱动

系统不再是一个黑盒，而是明确划分为两个核心计算层：

1. **L1 静态设定层 (SDM)**：基于**达涅利四大平衡**，计算“一一口价”的初始配料单。  
2. **L2 动态仿真层 (ODE)**：基于**Source 18 的微分方程组**，以 10秒 为步长推演未来 6分钟 的熔池状态，修正 L1 的结果。

## 2\. L1 静态模型细化 (SDM \- The Planner)

*此模块用于开吹前的物料与热平衡计算。*

### 2.1 热平衡计算 (Heat Balance) \- 核心公式细化

**Prompt 给 Gemini**："Create a class HeatBalanceCalculator. Implement the equation:$$Q\_{in} \+ Q\_{react} \= Q\_{out} \+ Q\_{loss} \+ Q\_{coolant}$$

* **输入热 ($Q\_{in}$)**:  
* 铁水物理热：$W\_{HM} \\times C\_{p\\\_HM} \\times T\_{HM}$。  
* **一罐到底修正**：若 is\_one\_can \== True，则 $T\_{HM\\\_eff} \= T\_{HM} \+ 30^\\circ C$ (Source 1 1).  
* **反应热 ($Q\_{react}$)**:  
* 使用标准生成焓计算：  
* $Si \\to SiO\_2$: 27620 kJ/kg Si (Source 2).  
* $V \\to V\_2O\_3$: 需根据 Source 18 定义氧化钒的放热量。  
* $C \\to CO$: 关键点！仅计算氧化到 $C=3.5\\%$ 部分的热量 (Source 93 2).  
* **冷却剂吸热 ($Q\_{coolant}$)**:  
* 实现 **Source 95 3** 的等效替代逻辑：  
* 1.0t Pig\_Iron (生铁) $\\approx$ 5.5t Oxide\_Scale (铁皮) $\\approx$ 2.5t V\_Slag (钒渣)。  
* 计算目标：求解 $W\_{coolant}$ 使得 $T\_{end} \\in $。"

### 2.2 渣平衡与原料结构 (Slag & Material)

**逻辑细化 (Source 106 4, Source 1 5\)**:

* **V/(Si+Ti) 判据**:  
* 计算 Ratio \= V / (Si \+ Ti)。  
* IF Ratio \< 1.05: 判定为“极难富集”。强制策略：增加 **高钒块矿** 或 **氧化铁皮**，禁止使用 **弃渣球** (SiO2\~10%)。  
* **渣量预测**:  
* $W\_{slag} \= 2.14 \\times \\Delta Si \+ 1.79 \\times \\Delta V \+ W\_{coolant\\\_impurity}$。  
* **杂质惩罚**: 若工艺为“一罐到底”，强制在渣量中增加 $W\_{slag} \\times 1.1$，模拟高炉渣混入带来的 CaO/SiO2 增量 (Source 1 1).

## 3\. L2 动态模型细化 (Kinetics \- The Simulator)

*这是系统的核心差异化竞争力，直接使用 Source 18 的微分方程。*

### 3.1 核心微分方程组 (Python Scipy Task)

**Prompt 给 Gemini**:"Implement a system of ODEs using scipy.integrate.odeint. The state variables are concentrations $C, Si, V, Ti$ and Temperature $T$.Reference Source 18 (Chapter 7\) for the following rates:

* **Carbon Oxidation ($dC/dt$)**:  
* Use **Eq 7.31**: $\\frac{dC}{dt} \= \- \\frac{12}{W\_m} A\_{cav} k\_C (C \- C\_{eq})$  
* Note: Carbon oxidation is suppressed when $T \< 1361^\\circ C$. You must add a conditional factor: if T \< 1361: rate \*= 0.2 (Source 93 6).  
* **Vanadium Oxidation ($dV/dt$)**:  
* Use **Eq 7.58** (Slag-Metal Interface): $\\frac{dV}{dt} \= \- \\frac{A\_{sm} \\rho\_{sm}}{W\_m} k\_V (V \- V^\*)$  
* **Critical Parameter**: $A\_{sm}$ (Interfacial Area). Use **Eq 7.189** logic: Area is a function of Oxygen\_Flow (Mixing Energy). Higher flow \= Larger area \= Faster V removal.  
* **Temperature Change ($dT/dt$)**:  
* Use **Eq 7.114**: Net heat from reactions minus heat absorbed by coolant melting.  
* **Coolant Melting Rate**: Implement **Eq 7.90** for Oxide Scale dissolution: $\\frac{dr}{dt} \= \- \\frac{k \\Delta C}{\\rho\_s}$. This determines *when* the cooling effect happens."

### 3.2 动态过程干预规则

**逻辑细化 (Source 106 7, 8\)**:

* **Rule 1: 枪位控制 (Lance Profile)**  
* IF $Si\_{initial} \> 0.20\\%$:  
* Strategy: **"恒定低枪位"** (Constant Low).  
* Action: Maintain Lance Height at **900-1000mm** for entire blow.  
* IF $Si\_{initial} \\le 0.20\\%$:  
* Strategy: **"低-高-低"** (Low-High-Low).  
* Action: 0-2min (900mm) \-\> 2-4.5min (1200mm) \-\> End (900mm).  
* **Rule 2: 终点逼近 (Endpoint Approach)**  
* 当仿真 $V \< 0.05\\%$ 且 $T \> 1350^\\circ C$ 时:  
* Alert: "即将到达终点，请准备提枪"。  
* Constraint: 半钢残 V 必须 $\\le 0.03\\%$ (Source 106 7).

## 4\. MCP Skills 接口定义 (Function Call)

### Skill 1: calculate\_initial\_charge (开吹配料)

* **Input**:  
* {  
*   "iron\_weight": 80.0, "temp": 1320, "si": 0.22, "v": 0.28,  
*   "is\_one\_can": true,  
*   "coolant\_inventory": {"pig\_iron": 10, "oxide\_scale": 5}  
* }  
* **Output**:  
* {  
*   "recipe": {"pig\_iron": 2.0, "oxide\_scale": 1.5},  
*   "oxygen\_total": 1400,  
*   "warning": "High Si & One-Can: Coolant increased by 15% to balance heat."  
* }

### Skill 2: simulate\_blow\_path (过程仿真)

* **Input**: recipe (from Skill 1), oxygen\_flow\_rate (e.g., 9600 m3/h).  
* **Calculation**: Run the ODE solver for t=0 to 360 seconds.  
* **Output**: Data arrays for time, Temp, C, V, Si.  
* **Action**: Generate a chart showing the "C-V Inversion Temperature" crossover point (usually around 1361℃).

### Skill 3: diagnose\_process\_quality (炉后诊断)

* **Logic (Source 106 4\)**:  
* Check V\_slag\_grade.  
* If Grade \< 12.5%:  
* Check Iron\_Si \> 0.25: "Si Dilution Effect".  
* Check V / (Si+Ti) \< 1.01: "Raw Material Deficit".  
* Check Process \== One\_Can & CaO\_slag \> 2.0: "Blast Furnace Slag Contamination".

## 5\. 开发 Prompt 示例 (Copy-Paste Ready)

### 用于生成动力学模型的 Prompt

"Role: Metallurgical Expert.Task: Write a Python function vanadium\_blow\_simulation using scipy.odeint.Physics:

1. Define rate constants ($k\_C, k\_V, k\_{Si}$) using Arrhenius equation: $k \= A \\cdot \\exp(-E\_a/RT)$.  
2. Implement Equation 7.32 (Source 18\) for Silicon removal: It is 0th order initially, then 1st order.  
3. Implement heat balance: reaction heat raises T, coolant melting (Eq 7.105) lowers T.  
4. **Constraint**: If T \> 1361 (Kelvin 1634), C oxidation rate triples, V oxidation rate halves (Thermodynamic crossover).Input: Initial composition C, Si, V, Ti, T, Coolant Mass.Output: Time-series data for T and composition."

### 用于生成配料规则的 Prompt

"Role: Production Planner.Task: Write a logic function recommend\_coolants.Logic Source: Source 106 (Page 96 table) and Source 95.Rules:

* Base demand: Calculate heat excess.  
* Equivalency: 1 ton Pig Iron \= 2.5 ton V-Slag \= 5.5 ton Oxide Scale.  
* Preference:  
* If Si \> 0.25%: Force Pig Iron (to avoid adding oxygen/oxides).  
* If Si \< 0.15%: Prefer Oxide Scale (cheap, adds V).  
* If One\_Can\_Process is True: Add extra 10kg/ton coolant to base demand."

通过这份细化文档，您现在拥有了具体的**微分方程编号**、**热力学常数来源**以及**现场操作的硬性约束（如900mm枪位）**。这将确保 Gemini 生成的代码不仅仅是通用的炼钢代码，而是专用于**建龙/攀钢模式**的提钒控制代码。  
