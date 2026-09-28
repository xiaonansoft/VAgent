# VERO 项目交接文档（HANDOVER）

> 交接日期：2026-09-23 · 交接对象：workbuddy · 接手前必读
> 工作目录：`~/Documents/VAgent`（OpenCode 会话所在，git 已初始化的本地克隆）

---

## 1. 项目一句话

**提钒冶炼智能体（VERO）**：把攀钢专家的四大多平衡 Excel 模型（703 公式）变成可治理、可学习、可解释的工业智能体。当前进度：**MVP 驾驶舱已交付并通过验收**，下一步是数据接口规范与后端真实 API 接入。

## 2. 目录即地图

```
~/Documents/VAgent/
│
├─ 核心结论文档（按阅读顺序）
│   ├─ ① PANGANG_EXCEL_DECODED.md     攀钢秘诀 Excel 解码报告
│   │     8 表 703 公式全解码；专家常数清单（1.157 系数、Ti 折算比、
│   │     凝固点双公式）；6 处引用怪癖 Q1–Q6；与仓库建龙口径的 5+1 条冲突
│   ├─ ② VERO_AGENT_BRAINSTORM.html    第一轮：多专家头脑风暴（四层架构定案）
│   ├─ ③ VERO_TECH_DEEPDIVE.html       第二轮：前沿技术辩论（七项技术裁决：采 3 试点 3 拒 1）
│   ├─ ④ VERO_DEV_PROCESS_PLAN.html    第三轮：开发方法论 + 14 份待写文档清单 + RACI
│   ├─ ⑤ VERO_MVP.html                 ★ 可运行 MVP v0.2（浏览器直接打开，离线，单文件）
│   ├─ ⑥ ARBITRATION_DEMO.md           双引擎冲突仲裁演示报告（CF-001~006）
│   └─ ⑦ docs/MVP_SPEC.md              MVP 规格（验收硬条款 A1–A8）★ 已达成
│
├─ knowledge/packs/industry/base.yaml   行业基线知识包（行业通用规则：枪位模式/去钒保碳/终点目标/判据）
├─ knowledge/packs/pangang/base.yaml  ★ 专家知识包 YAML（厂级：攀钢四大平衡）
│     31 类参数全部溯源到 Excel 单元格 · status: draft · 待专家批准
│     ⚠️ 与 pangang_reference.py 的常数一致性由 pangang_pack.py 校验（必须保持同步）
├─ knowledge/packs/jianlong/base.yaml  建龙 L1 配料知识包（厂级：查表法+枪位默认值）
│     ★ scope 分层：行业基线(industry) < 厂(plant) < 车间 < 炉座；引擎经 resolve_parameters()
│       以行业基线打底、厂级包覆盖合并取值（默认厂 jianlong，可用 VERO_PLANT 覆盖）
│
├─ backend/                            Python 后端（⚠️ 需 Python 3.10+，系统只有 3.9）
│   app/tools/pangang_reference.py    ★ 四大平衡参考实现（黄金 75/75，误差 0.0002%）
│   app/tools/pangang_pack.py         知识包加载 + 包/代码一致性校验
│   app/tools/v_heat_calibration.py   V 氧化热反演（16 炉，文献 15000 占优）
│   app/tools/arbitration_demo.py     双引擎仲裁演示
│   app/tools/initial_charge.py       建龙查表 L1 引擎（硬编码，待迁知识包）
│   app/tools/{kinetics_simulator, equilibrium_model, thermal_balance, lance_profile,
│               critical_temp, diagnose_process_quality}.py
│   app/agents/{core,team}.py         LangGraph 多智能体（配料/仿真/诊断 Agent）
│   app/mcp/                          MCP 工具服务器雏形（jsonrpc/tools_server/data_server）
│   app/data/soft_sensor.py           软测量（热平衡推断 + 烟气反算）
│   tests/test_pangang_reference.py   ★ 黄金用例（python3 直接可跑，无需 pytest）
│   pytest.ini / requirements.txt     FastAPI+LangGraph 栈（需 3.10+ 环境）
│
├─ frontend/ web/                     原有前端骨架（本次未动）
├─ docker-compose.yml                 P4 部署形态基础
├─ .agents/skills/                    已装 12 个方法论技能（见 §5）
├─ README.md / MODEL_ALGORITHM.md / API_DOCUMENTATION.md / DEPLOYMENT.md
│   DEVELOPMENT_PLAN.md / SOLUTION_PITCH.md / USER_MANUAL.md
│   └─ 仓库原有文档（建龙口径基线，部分数字已过时——冲突见 DECODED §3）
└─ 提钒冶炼智能体 VERO v6.0 实施 PRD.md   原始 PRD（Source 106/95 引用体系）
```

**仓库之外的关联资产**

- 攀钢专家 Excel 原件：`/Volumes/数据/提钒/提钒预算测算钒品位低原因说明(1).xlsx`（移动硬盘；未入库，系 IP 秘诀，勿提交）
- 3 份 PDF 语料（建龙规程/动力学/讲课稿）在仓库根目录，P2 RAG 素材
- Node v22.23.2：`~/.local/node22/`（已写入 ~/.zshrc PATH）
- Python 3.9.6（系统自带）：仅够跑 pangang 工具链；backend 完整栈需升级

## 3. 已验证资产（信任基底——不要重造）

| 资产 | 验证方式 | 结果 |
|---|---|---|
| Python 四大平衡参考实现 | 75 项黄金用例对照 Excel 缓存值 | 75/75，最大误差 0.0002% |
| 「热平衡富余 93MJ」之谜 | 修正口径验证 | 确认系 Excel 表格漏项（Q5），修正后闭合 1e-16 |
| JS 引擎（MVP 内嵌） | JavaScriptCore 独立运行 11 项 + RMSE 对照 | 11/11，RMSE 2.178/1.679 与 Python 完全一致 |
| 知识包一致性 | pangang_pack.py 逐项核对 | 31 类参数零漂移 |
| V 氧化热（2777 vs 15000） | 16 炉回放 | 文献 15000 RMSE 优（0.999 vs 1.466），**未终审** |

## 4. 排期状态（P1–P4 / D1–D10）

- **P1 规则引擎/知识资产（✅ 收尾）**：✅ 解码/复现/YAML/校验器/仲裁演示；✅ 知识包接入 initial_charge 替代硬编码（建龙包 `knowledge/packs/jianlong/base.yaml`，108 组等价对照 + 回归通过，行为零漂移）
- **P2 认知层（下一步主攻）**：⬜ D6 数据接口规范（最紧急）· 真 RAG+IP 分级 · 三要素回答模板 · 仲裁工作台
- **P3 学习闭环**：炉次误差回流 RLS/PINN 残差 · TabPFN 试点 · 漂移检测
- **P4 治理**：审批流/跨厂判例/例外率看板
- MVP 已按 D1–D5 交付：`VERO_MVP.html`（验收硬条款 A1–A8 除 A7 演示脚本人工完成外全部通过）

## 5. 工具链状态

- OpenCode 桌面版（`/Applications/OpenCode.app`，自带 CLI v2.0.13，软链到 `~/.local/bin/opencode`）
- Node v22.23.2 @ `~/.local/node22`（PATH 已入 ~/.zshrc）
- 已装 Agent Skills（`.agents/skills/`，OpenCode 已识别）：brainstorming / writing-plans / executing-plans / test-driven-development / verification-before-completion / systematic-debugging / to-spec / to-tickets / implement / tdd / code-review / skill-creator / find-skills / opencode
- Python 包（--user）：openpyxl / pyyaml / pytest
- 技巧：GitHub 直连会超时，用 jsDelivr CDN（apk 文件级）或 gh-proxy 镜像浅克隆拉取开源资源

## 6. 未决事项（挂责任人，来自第三轮 §07）

1. **[冶炼**] CF-001 V 氧化热终审——证据已备（反演脚本可复跑）
2. **[冶炼**] 1.157 系数适用边界（是否随铁水来源变化）
3. **[工艺**] 建龙基准 45 vs 上限 25 内部矛盾澄清（CF-006）
4. **[冶炼**] 金属铁/块矿冷料的成分行映射意图确认（Q1/Q3/Q4/Q6）
5. **[工艺**] 品位归因口径：14 日专家算 12.48% vs 复现 12.91%，差 0.4pp 待解释
6. **[产品**] 知识包批准签字流程 + 仲裁判例字段定义
7. **[数据**] TSC/TSO/烟气/氧枪 数据接口规范（D6，决定 P3 一切成败）
8. **[安全**] shadow mode 并行炉数与切换标准
9. **[AI**] L2 10 秒步长的延迟预算切分
10. **[产品**] KPI 定义（品位达标率/例外率/采纳率）

## 7. 接手后第一个 commands

```bash
cd ~/Documents/VAgent
git add -A && git commit -m "chore: lock in P1 artifacts + MVP v0.2 (pre-handover state)"   # 先锁定现场
python3 backend/tests/test_pangang_reference.py                                          # 验证引擎基线
open VERO_MVP.html                                                                       # 看当前 MVP
```

然后二选一推进：
- **A 路（数据线）**：起草 `docs/DATA_INTERFACE_SPEC.md`（字段/频率/网络边界），解锁 P3 全部学习类任务
- **B 路（产品线）**：把 MVP 接上真实后端 API（需先升级 Python 3.10 环境），MVP 静态页 → P2 内网 Web

---

*交接完成。规则：系统只呈证据不代决策；所有新数字都过黄金用例这道门。*
