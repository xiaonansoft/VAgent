# Vanadium Smelting Intelligent Agent (VEES v7.0)
# 钒冶炼智能体系统 (VEES v7.0)

A comprehensive AI-driven system for optimizing the vanadium extraction process in converter steelmaking. This system integrates L1 (Static), L2 (Dynamic), and L3 (AI Copilot) layers to provide real-time monitoring, process simulation, and decision support.

这是一个用于优化转炉炼钢提钒过程的综合 AI 驱动系统。该系统集成了 L1（静态）、L2（动态）和 L3（AI 助手）层，提供实时监控、过程仿真和决策支持。

## 🌟 Key Features / 核心功能

### 1. Multi-Layer Architecture / 多层架构
- **L1 Static Setup**: Calculates initial charge recipe (coolants, oxygen) based on heat and mass balance.
  **L1 静态设定**: 基于热平衡和质量平衡计算初始配料（冷却剂、氧气）。
- **L2 Dynamic Monitor**: Real-time "Digital Twin" simulation of the molten bath evolution using differential equations (ODEs).
  **L2 动态监控**: 使用微分方程 (ODEs) 对熔池演变进行实时“数字孪生”仿真。
- **L3 AI Copilot**: Intelligent assistant for anomaly detection, strategy recommendation, and natural language interaction.
  **L3 智能助手**: 用于异常检测、策略推荐和自然语言交互的智能助手。

### 2. Advanced Process Control / 高级过程控制
- **Soft Sensor (Mechanism Inference)**: Reconstructs critical data (e.g., Temperature) when physical sensors fail, using reaction kinetics and auxiliary signals.
  **软测量 (机理推断)**: 利用反应动力学和辅助信号，在物理传感器失效时重构关键数据（如温度）。
- **Self-Learning**: Automatically adjusts model parameters (Heat Efficiency, Reaction Rates) based on historical heat data.
  **自学习**: 根据历史炉次数据自动调整模型参数（热效率、反应速率）。
- **Diagnosis System**: Expert rules for detecting anomalies like "Splashing", "Dry Slag", and "Low Yield" with root cause analysis.
  **诊断系统**: 用于检测“喷溅”、“返干”和“低收得率”等异常的专家规则，并提供根因分析。

### 3. Modern Visualization / 现代可视化
- **Real-time Charts**: Interactive curves for Temperature, C/Si/V content, and Lance Height.
  **实时图表**: 温度、C/Si/V 含量和枪位的交互式曲线。
- **Discrete Sampling**: Correct visualization of TSC/TSO sub-lance measurements.
  **离散采样**: 正确显示 TSC/TSO 副枪测量值。
- **Persistence**: Simulation history is preserved across browser refreshes.
  **持久化**: 浏览器刷新后仿真历史数据得以保留。

## 🚀 Getting Started / 快速开始

### Prerequisites / 前置条件
- Python 3.10+
- Node.js 18+
- PostgreSQL (Optional, defaults to SQLite)

### Backend Setup / 后端设置
1. Navigate to backend directory:
   ```bash
   cd backend
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the server:
   ```bash
   uvicorn app.main:app --reload
   ```
   The API will be available at `http://localhost:8000`.

### Frontend Setup / 前端设置
1. Navigate to frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
   The application will be served at `http://localhost:5173`.

## 📚 Documentation / 文档
- **API Documentation**: [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) - Detailed API endpoints and schemas.
- **Model Algorithms**: [MODEL_ALGORITHM.md](./MODEL_ALGORITHM.md) - Mathematical models and physics engine details.
- **User Manual**: [USER_MANUAL.md](./USER_MANUAL.md) - Guide for operators and process engineers.

## 🛠 Tech Stack / 技术栈
- **Backend**: FastAPI, SQLAlchemy, Pydantic, SciPy (ODEs), NumPy.
- **Frontend**: React, TypeScript, Vite, Tailwind CSS, Recharts.
- **Database**: SQLite (Development), PostgreSQL (Production ready).
- **Architecture**: Modular Monolith with clean separation of concerns (Tools, Agents, Data).

## 🧪 Testing / 测试
Run backend tests:
```bash
cd backend
python -m pytest tests/
```

## 📄 License
Private / Proprietary
