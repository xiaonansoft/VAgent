# 模型算法文档 (Model Algorithm Documentation)

本文档详细介绍了钒冶炼智能体系统 (VEES v7.0) 中使用的数学模型和算法。

## 1. L1 静态模型 (操作级)
**代码位置**: `backend/app/tools/initial_charge.py`

操作级 L1 模型基于**建龙钢铁现场规程**（查表法）计算初始配料。

### 输入 (Inputs)
*   **铁水条件**: 重量 ($W_{iron}$), 温度 ($T_{iron}$), 成分 ($[Si], [V], [Ti]$ 等)
*   **工艺参数**: 是否“一罐到底”模式
*   **历史状态**: 上一炉留渣/蓄热情况 (可选)

### 输出 (Outputs)
*   **推荐配方**: 冷却剂类型及重量 (例如: 球团 1.5t, 钒渣铁 0.5t)
*   **工艺指标**: 预计总耗氧量 ($m^3$), 预计渣量 (t)
*   **警报**: 针对高硅喷溅风险或配料超限的警告

### 1.1 冷却剂计算逻辑
总冷却剂重量 ($W_{coolant}$) 由基于硅含量的基准值和温度修正值决定。

$$ W_{coolant} = W_{base}(Si) + \Delta W_{temp} $$

**基准冷却剂查表 ($W_{base}$ @ 1300°C)**:
*   $Si \le 0.15\%$: $22.5 \text{ kg/t}$
*   $0.15 < Si \le 0.20\%$: $33.0 \text{ kg/t}$
*   $0.20 < Si \le 0.25\%$: $39.0 \text{ kg/t}$
*   $Si > 0.25\%$: $45.0 \text{ kg/t}$

**温度修正 ($\Delta W_{temp}$)**:
$$ \Delta W_{temp} = (T_{iron} - 1300) \times 0.18 \text{ kg/t} $$
*(修正系数: 每 10°C 增加 1.8 kg/t)*

**约束条件**: $W_{coolant} \le 25 \text{ kg/t}$ (每 100t 炉次最大 2.5t)。

### 1.2 冷却剂分配策略
按优先级分配总冷却剂重量：
1.  **钒渣铁 ($W_{vslag}$)**:
    *   条件: $Si \ge 0.20\%$ (高硅优先回吃)
    *   $$ W_{vslag} = \min(2.0, 0.5 \times W_{total}) $$
2.  **氧化铁皮 ($W_{scale}$)**:
    *   $$ W_{scale} = \min(0.5, 0.3 \times (W_{total} - W_{vslag})) $$
3.  **球团/球返 ($W_{pellet}$)**:
    *   $$ W_{pellet} = W_{total} - W_{vslag} - W_{scale} $$

---

## 2. L2 动态模型 (动力学)
**代码位置**: `backend/app/tools/kinetics_simulator.py`

使用常微分方程组 (ODEs) 模拟熔池实时演变，引入了**枪位动态影响**机制。

### 输入 (Inputs)
*   **初始状态**: 初始温度, 初始成分 ($[C], [Si], [V], [Ti]$)
*   **控制变量**: 氧气流量 ($Q_{O2}$), **枪位高度** ($H_{lance}$), 加料操作
*   **炉役状态**: 炉龄阶段 (影响搅拌因子)

### 输出 (Outputs)
*   **状态轨迹**: 随时间变化的温度 $T(t)$ 和成分 $[X](t)$ 曲线
*   **关键事件**: 碳钒临界转化温度点 ($T_c$) 的预测时间
*   **终点预测**: 终点温度, 终点残钒, 终点碳含量

### 2.1 反应动力学方程
元素 $i$ 的反应速率 ($r_i$) 受浓度 $[i]$、温度开关及**混合能量**控制。

**搅拌因子 ($\eta_{stir}$)**: 模拟炉役影响 (前期 1.0 $\to$ 后期 0.7)。
**混合因子 ($\eta_{mix}$)**: 受枪位影响，枪位越低，搅拌能越大。
$$ \eta_{mix} = (1400 / H_{lance})^{1.5} $$

**温度开关函数 (Sigmoid)**:
$$ S(T) = \frac{1}{1 + e^{-(T - 1380)/50}} $$
*(转化中心温度 $T_c = 1380^\circ C$)*

**速率方程**:
*   **Si**: $r_{Si} = k_{Si} \cdot \eta_{stir} \cdot \eta_{mix} \cdot [Si]$
*   **Ti**: $r_{Ti} = k_{Ti} \cdot \eta_{stir} \cdot \eta_{mix} \cdot [Ti]$
*   **V**: $r_{V} = k_{V} \cdot \eta_{stir} \cdot \eta_{mix} \cdot [V] \cdot (1.5 - S(T))$  *(低温优先)*
*   **C**: $r_{C} = k_{C} \cdot \eta_{stir} \cdot \eta_{mix} \cdot [C] \cdot (0.1 + 5.0 \cdot S(T))$ *(高温优先)*

### 2.2 二次燃烧与氧平衡
**二次燃烧率 (PCR)**: $CO \to CO_2$ 的比例受枪位影响，高枪位促进二次燃烧。
$$ PCR = 0.10 + 0.15 \times \frac{\max(0, H_{lance} - 1200)}{400} $$
*(范围: 10% - 40%)*

总需氧量 ($D_{O2}$) vs 供氧量 ($S_{O2}$):
$$ D_{O2} = \sum \frac{r_i \cdot m_{bath}}{M_i} \cdot Stoich_i $$
**供应因子 ($f$)**:
$$ f = \min(1.0, \frac{S_{O2}}{D_{O2}}) $$
**实际速率**: $r_{i, real} = r_i \times f$

### 2.3 热演变方程
$$ \frac{dT}{dt} = \frac{Q_{gen} - Q_{loss} - Q_{coolant}}{m_{bath} \cdot C_p} $$
其中产热 $Q_{gen}$ 考虑了动态 PCR:
$$ Q_{gen} = \sum \dot{m}_{i} \Delta H_{i} + \dot{m}_{C} [ (1-PCR)\Delta H_{CO} + PCR \Delta H_{CO2} ] $$

### 2.4 卡尔曼滤波 (数据融合)
用于融合 **模型预测** ($x_{pred}$) 与 **软测量/烟气分析** ($z_{meas}$) 以修正碳含量 $[C]$。

1.  **预测 (Predict)**:
    $$ x_{k|k-1} = x_{k-1} + u_k $$
    $$ P_{k|k-1} = P_{k-1} + Q $$
2.  **更新 (Update)**:
    $$ K_k = P_{k|k-1}(P_{k|k-1} + R)^{-1} $$
    $$ x_{k|k} = x_{k|k-1} + K_k(z_k - x_{k|k-1}) $$

---

## 3. L2 平衡模型 (热力学)
**代码位置**: `backend/app/tools/equilibrium_model.py`

基于 **Danieli SDM** 原理，求解理论极限状态。

### 输入 (Inputs)
*   **物料清单**: 铁水, 废钢, 石灰, 冷却剂的准确重量
*   **供氧总量**: 全程吹炼耗氧量
*   **热力学参数**: 反应焓, 比热容 (常量)

### 输出 (Outputs)
*   **理论终点**: 理论终点温度 ($T_{eq}$), 理论终点成分
*   **渣系状态**: 渣量, 渣成分 ($SiO_2, V_2O_3, FeO$ 等)
*   **四大平衡**: 物料平衡, 氧平衡, 渣平衡, 热平衡明细表

### 3.1 焓平衡方程
$$ H_{in} + H_{gen} - H_{loss} = H_{out} $$

### 3.2 热项计算
1.  **输入热 ($H_{in}$)**:
    $$ H_{in} = m_{iron}(C_{p,hm}T_{hm} + H_{0,hm}) + m_{scrap}(C_{p,sc}(T_{sc}-25)) $$
2.  **反应热 ($H_{gen}$)**:
    $$ H_{gen} = \sum m_{i, reacted} \cdot \Delta H_{i} $$
    *   $\Delta H_{Si} = 27620 \text{ MJ/t}$
    *   $\Delta H_{V} = 15000 \text{ MJ/t}$
    *   $\Delta H_{C \to CO} = 7470 \text{ MJ/t}$
3.  **输出热 ($H_{out}$)**:
    $$ H_{out} = m_{steel}(C_{p,st}T_{final} + H_{0,st}) + m_{slag}(C_{p,slag}T_{final}) $$

### 3.3 理论温度求解 ($T_{final}$)
解析求解平衡方程得到：
$$ T_{final} = \frac{H_{available} - m_{steel}H_{0,st}}{m_{steel}C_{p,st} + m_{slag}C_{p,slag}} $$

---

## 4. 开吹前热平衡模型
**代码位置**: `backend/app/tools/thermal_balance.py`

### 输入 (Inputs)
*   **铁水条件**: 温度, Si 含量
*   **目标状态**: 目标出钢温度 (例如 1380°C)
*   **废钢装入量**: 计划废钢量

### 输出 (Outputs)
*   **热盈余状态**: 热量盈余或亏损值 (MJ)
*   **冷却策略**: 建议冷却剂类型 (球返/弃渣球) 及 吨钢加入量 (kg/t)

### 4.1 计算逻辑
1.  **热盈余 ($H_{surplus}$)**:
    $$ H_{surplus} = (H_{in} + H_{gen} - H_{loss}) - H_{out}(T_{target}) $$
2.  **冷却效率 ($h_{eff}$)**:
    冷却剂升温至目标温度吸收的热焓：
    $$ h_{eff} = (C_{p,st}T_{target} + H_{0,st}) - (C_{p,sc} \cdot 25) $$
3.  **冷却剂需求 ($W_{coolant}$)**:
    $$ W_{coolant} = \frac{H_{surplus}}{h_{eff}} $$

---

## 5. 软测量模型 (机理推断)
**代码位置**: `backend/app/data/soft_sensor.py`

### 输入 (Inputs)
*   **传感器读数**: 原始温度值 (可能含噪或丢失)
*   **辅助变量**: 氧气流量, 烟气成分 ($CO, CO_2$)
*   **时间步长**: $\Delta t$

### 输出 (Outputs)
*   **估计温度**: 经机理修正后的温度值
*   **置信度**: 数据可信度评分 (0.0 - 1.0)
*   **状态标志**: 传感器是否故障 (Valid/Invalid)

### 5.1 热平衡推断
当物理传感器失效时，使用热平衡递推：
$$ T_{k+1} = T_k + \frac{(k_{Si}\dot{Si} + k_{C}\dot{C} - Q_{loss})}{C_p \cdot m} \Delta t $$

### 5.2 烟气反算脱碳率 ($dC/dt$)
$$ \dot{n}_{gas} = \frac{Flow_{Nm^3/s}}{0.0224} \text{ mol/s} $$
$$ \dot{C}_{mass} = \dot{n}_{gas} \times (\%CO + \%CO_2) \times M_C $$
$$ \frac{dC}{dt} (\%) = - \frac{\dot{C}_{mass}}{m_{bath}} \times 100 $$

---

## 6. L3 深度自学习架构 (Advanced Self-Learning)
为应对生产环境的复杂变化（“千变万化”），系统采用了多层次自学习架构。

### 6.1 炉次间参数自适应 (Inter-heat Adaptation)
针对每一炉的预测误差，使用**递归最小二乘法 (RLS)** 或 **梯度下降** 更新模型参数。

*   **目标函数**: $J = (T_{actual} - T_{pred})^2 + \lambda (\Delta \theta)^2$
*   **可调参数**:
    *   $\theta_1$: 热效率因子 (Heat Efficiency)
    *   $\theta_2$: 全局反应速率系数 (Rate Modifier)
*   **更新规则**:
    $$ \theta_{k+1} = \theta_k - \alpha \frac{\partial J}{\partial \theta} $$

### 6.2 情境感知学习 (Context-Aware Learning)
不同原料条件（如高硅 vs 低硅）需要不同的模型参数。
*   **聚类**: 将历史炉次按 $[Si], T_{iron}$ 进行 K-Means 聚类。
*   **参数库**: 为每个类别维护独立的最佳参数集 ($\theta_{HighSi}, \theta_{LowSi}$)。
*   **推理时**: 根据当前铁水条件匹配最近邻类别的参数。

### 6.3 漂移检测 (Drift Detection)
监测长期趋势以发现设备老化或原料变更。
*   如果连续 N 炉的预测偏差 $\mu_{err}$ 超过阈值 $3\sigma$，触发**全局重校准 (Global Recalibration)**。
*   识别炉底透气砖堵塞（搅拌能下降）或氧枪喷头磨损。

---

## 常量参考表
| 符号 | 数值 | 单位 | 描述 |
| :--- | :--- | :--- | :--- |
| $C_{p,hm}$ | 0.88 | MJ/°C/t | 铁水比热容 |
| $C_{p,st}$ | 0.76 | MJ/°C/t | 钢水比热容 |
| $C_{p,slag}$ | 1.19 | MJ/°C/t | 炉渣比热容 |
| $H_{0,hm}$ | 42.0 | MJ/t | 铁水 0°C 焓值 |
| $H_{0,st}$ | 193.0 | MJ/t | 钢水 0°C 焓值 |
| $M_{Si}$ | 28.09 | g/mol | 硅摩尔质量 |
| $M_{V}$ | 50.94 | g/mol | 钒摩尔质量 |
