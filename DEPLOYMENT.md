# VEES v7.0 系统部署指南 (Deployment Guide)

本指南旨在指导技术人员在生产环境或测试环境中部署 **VEES (Vanadium Extraction Expert System)** 提钒冶炼智能体。

## 1. 系统架构概览

VEES 采用现代化的微服务架构：
*   **前端 (Frontend)**: React 18 + Vite + TailwindCSS (可视化大屏)
*   **后端 (Backend)**: Python 3.10+ + FastAPI + Uvicorn (仿真计算与 AI 逻辑)
*   **数据库 (Database)**: PostgreSQL (生产) / SQLite (开发) + SQLAlchemy (异步 ORM)
*   **容器化 (Containerization)**: Docker + Docker Compose

---

## 2. 环境要求 (Prerequisites)

### 硬件要求
*   **CPU**: 4 vCPU 以上 (推荐 8 vCPU 用于并行仿真)
*   **RAM**: 8 GB 以上 (推荐 16 GB)
*   **Disk**: 50 GB SSD

### 软件依赖
*   **Docker Engine**: v20.10+
*   **Docker Compose**: v2.0+
*   *(可选，仅源码部署)*: Node.js v18+, Python v3.10+

---

## 3. 快速启动 (Docker Compose) - 推荐

这是最简单的部署方式，适合演示和快速验证。

### 步骤 1: 获取代码
```bash
git clone https://github.com/your-repo/vagent.git
cd vagent
```

### 步骤 2: 配置环境变量
复制 `.env.example` 到 `.env` 并根据需要修改：
```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env 设置数据库密码等
```

### 步骤 3: 启动服务
```bash
docker-compose up -d --build
```

### 步骤 4: 验证状态
```bash
docker-compose ps
```
确保 `backend` 和 `frontend` 容器状态为 `Up`。

*   **访问前端**: `http://localhost:3000` (或服务器 IP)
*   **访问后端 API 文档**: `http://localhost:8000/docs`

---

## 4. 手动部署 (Manual Deployment)

适用于开发调试或不支持 Docker 的环境。

### 4.1 后端部署

1.  **进入目录**:
    ```bash
    cd backend
    ```
2.  **创建虚拟环境**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/Mac
    # venv\Scripts\activate  # Windows
    ```
3.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **初始化数据库**:
    ```bash
    # 系统启动时会自动初始化，但需确保目录有写权限
    ```
5.  **启动服务**:
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ```

### 4.2 前端部署

1.  **进入目录**:
    ```bash
    cd frontend
    ```
2.  **安装依赖**:
    ```bash
    npm install
    ```
3.  **启动开发服务器**:
    ```bash
    npm run dev
    ```
    或者构建生产版本：
    ```bash
    npm run build
    npm run preview
    ```

---

## 5. 生产环境配置 (Production Tuning)

### 5.1 数据库迁移
在生产环境中，建议使用 PostgreSQL 替代 SQLite。
修改 `backend/app/core/config.py` 或 `.env`：
```ini
DATABASE_URL=postgresql+asyncpg://user:password@localhost/vagent
```

### 5.2 并发与性能
`backend/app/tools/kinetics_simulator.py` 中的 ODE 求解器是计算密集型任务。
*   在 `gunicorn` 配置中增加 Workers 数量：
    ```bash
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app
    ```

### 5.3 端口映射
如果是公网部署，请使用 Nginx 反向代理：
```nginx
server {
    listen 80;
    server_name vees.example.com;

    location / {
        proxy_pass http://localhost:3000;
    }

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 6. 常见问题 (Troubleshooting)

*   **Q: 前端显示 "System Offline"**
    *   A: 检查后端服务是否启动，以及浏览器控制台是否有 CORS 跨域错误。
*   **Q: 仿真速度很慢**
    *   A: 检查服务器 CPU 负载。如果并发用户多，考虑增加后端 Worker 数。
*   **Q: 数据库报错 "Locked"**
    *   A: SQLite 在高并发写时会锁库。生产环境请务必迁移到 Postgres。
