# VAgent 开发计划与路线图
> **状态**: 进行中
> **遵循规范**: 严格遵守 [.traerules](./.traerules)

## 1. 项目概况
**目标**: 构建一个工业级“钒冶炼智能体”，具备实时过程监控、异常诊断和闭环控制优化能力。
**当前状态**: 
- **前端**: React/Next.js，具备实时可视化 (Recharts) 和国际化 (i18n) 支持。
- **后端**: FastAPI，包含基础仿真引擎和 MCP 工具。
- **差距**: 缺乏工业级严谨性（存在硬编码值、测试不足、可观测性有限）。

---

## 2. Superpowers 工作流实施计划

### 第一阶段：基础与防御性设计 (🛡️ Skill: Defensive Design)
**目标**: 增强系统对不可靠输入的抵御能力，并确保配置灵活性。

- [x] **配置外部化 (已完成)**:
    - 将 `simulator.py` 和 `initial_charge.py` 中的所有硬编码系数（如 `heat_efficiency_factor`, `k_si`, `cp_hm`）提取到结构化配置文件 `backend/app/core/config.py` 中。
    - *原因*: 允许工艺工程师在不重新部署代码的情况下调整模型参数。
- [x] **严格输入验证 (已完成)**:
    - 在 `schemas.py` 中增强 Pydantic 模式，使用 `Field(..., ge=min, le=max)` 强制执行物理限制（例如：温度不能 < 1000°C 或 > 1800°C）。
    - *原因*: 防止物理上不可能的数据导致求解器崩溃。
- [x] **降级机制 (Fallback Mechanisms) (已完成)**:
    - 为智能体实现 `SafeMode`：如果 LLM/模型失败或超时，回退到确定性的“安全操作规则”（例如：“保持当前枪位”）。

### 第二阶段：核心逻辑与测试驱动开发 (🧪 Skill: TDD)
**目标**: 验证冶金模型的正确性并确保回归安全。

- [x] **单元测试 (已完成)**:
    - 创建 `tests/test_simulator.py`: 验证质量/能量守恒（输入 = 输出）。
    - 创建 `tests/test_initial_charge.py`: 对照已知 Excel 标准验证计算结果。
- [x] **边界情况测试 (已完成)**:
    - 测试“传感器故障”场景（输入为 0 或 Null）。
    - 测试“极端成分”场景（例如：Si > 1.0%）。

### 第三阶段：执行与可解释性 (💻 Skill: Execution)
**目标**: 让智能体的“黑盒”对操作员透明。

- [x] **结构化日志 (已完成)**:
    - 用结构化 Logger (JSON 格式) 替换 `print`。
    - 使用唯一的 `TraceID` 记录每个 `观察 -> 思考 -> 行动` 循环。
- [x] **推理追踪 (已完成)**:
    - 向前端 UI 展示智能体的内部推理过程（例如：“为什么推荐 1200mm 枪位？”）。
    - *实现*: `ChatResponse` 包含 `trace_id`，Agent 返回详细的 `content` 和 `tool_calls`。

### 第四阶段：生产就绪 (已完成)
**目标**: 准备部署到模拟工业环境。

- [x] **容器化 (Containerization) (已完成)**:
    - 创建 `Dockerfile` (Backend & Frontend) 和 `docker-compose.yml`。
    - 支持一键启动 Postgres + Backend + Frontend。
- [x] **性能优化 (已完成)**:
    - 分析 `asyncio` 循环瓶颈：`SimulationAgent` 中调用 `odeint` 时使用 `asyncio.to_thread` 避免阻塞。
    - 向量化评估：当前单炉次仿真无需 `numpy` 向量化，但在批量预测时可扩展。
- [x] **CI/CD (已完成)**:
    - 配置 GitHub Actions (`.github/workflows/ci.yml`) 进行自动化测试。

---

## 4. 第五阶段：深度冶金智能化 (Deep Metallurgical Intelligence)
**目标**: 基于达涅利 SDM 和建龙生产实绩，引入熔渣化学与精细热平衡，提升模型逼真度。

- [ ] **L2 炉渣成分动态仿真**:
    - *来源*: 《黑龙江建龙转炉提钒技术材料》 & 《第7章-转炉提钒动力学研究》.
    - *内容*: 在 `kinetics_simulator.py` 中增加渣相状态变量 (FeO, V2O5, SiO2, TiO2)。
    - *价值*: 实现对“钒渣品位”的实时预测，指导半钢与钒渣的平衡。
- [ ] **L1 精细化热损耗模型**:
    - *来源*: 《达涅利SDM自动炼钢模型...》.
    - *内容*: 引入“铁水包传输时间”、“空包时间”作为输入，计算 $\Delta T_{loss}$。
    - *公式*: $\Delta T = k \times \sqrt{t_{empty}} + ...$
- [ ] **工艺窗口智能监控**:
    - *来源*: 《铁水预处理提钒讲课稿》.
    - *内容*: 在 `SafetyAgent` 中集成 **1340~1400°C** 黄金温控区间监控，偏离即报警。
