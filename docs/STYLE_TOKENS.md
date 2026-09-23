# VEES 风格 token 规范（STYLE_TOKENS）

> 版本 v1.0 · 2026-09-23 · 单一事实来源：本文件是 `VEES_MVP.html`、`VEES_MVP_v0.3.html` 与后续前端共用的 CSS 变量规范。
> 原则：**暖色机理风**——工业纸质报告 + 熔融金属；只保留 红/黄/绿 三态工艺语义色，剔除无工艺语义的装饰色。

---

## 1. 色彩（Colors）

### 1.1 中性底（纸面 / 墨色）

| Token | 值 | 用途 |
|---|---|---|
| `--paper` | `#f5f2ec` | 页面背景（暖米纸色） |
| `--card` | `#ffffff` | 面板/卡片底色 |
| `--line` | `#ddd8ce` | 边框、分隔线 |
| `--ink` | `#141d2b` | 主文字（深墨蓝） |
| `--ink2` | `#3d4a5f` | 次级文字 |
| `--mut` | `#8a94a6` | 弱化/提示文字 |

### 1.2 品牌与工艺语义色

| Token | 值 | 用途 |
|---|---|---|
| `--molten` | `#e8590c` | 熔融橙：主强调、配吃量、曲线、选中态 |
| `--steel` | `#2b4a6f` | 钢蓝：次级强调、面板编号、深色区块 |
| `--blue` | `#1971c2` | 链接/当前点标记 |
| `--ok` | `#2b8a3e` | 绿：正常/通过（工艺三态） |
| `--warn` | `#b54708` | 黄：偏离/待确认（工艺三态） |
| `--danger` | `#c92a2a` | 红：危险/超差（工艺三态） |
| `--teal` | `#0f766e` | 数据治理台专属强调色（可选） |

### 1.3 顶栏渐变（唯一允许的渐变）

```css
background: linear-gradient(120deg, #141d2b, #2b4a6f 55%, #7a431d);
```

### 1.4 三态徽章（badge）

| 状态 | 背景 / 文字 |
|---|---|
| 绿灯 | `#d3f9d8` / `#2b8a3e` |
| 黄灯 | `#fff3bf` / `#b54708` |
| 红灯 | `#ffe3e3` / `#c92a2a` |

---

## 2. 排版（Typography）

| Token | 值 |
|---|---|
| 字体栈 | `"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif` |
| 正文 | 15px / `line-height: 1.65` |
| 面板标题 | 14.5–16px / `font-weight: 700` |
| KPI 数值 | 22px（主 34px）/ `font-weight: 800` / `font-variant-numeric: tabular-nums` |
| 弱化说明 | 11.5–12px / `--mut` |

> 数字一律 `tabular-nums`，保证配吃量/品位等数值对齐可扫读。

---

## 3. 组件（Components）

| 组件 | 规格 |
|---|---|
| 面板 `.panel` | 白底、`1px solid --line`、`border-radius: 14px`、`box-shadow: 0 2px 8px rgba(20,29,43,.05)` |
| 面板编号 `.n` | 11px、圆角 6px、白字（`--steel` 或 `--molten` 底） |
| 大数字 KPI `.kpi.hl` | 渐变底 `linear-gradient(135deg,#fff8ef,#fff1e0)`、边框 `#f3c89e`、数值 34px 熔融橙 |
| 证据卡 `.explain` | 虚线边框 `1px dashed --line`、米白底 `#fbfaf8` |
| 建议框 `.say` | 橙底 `#fff4e6`、边框 `#f3c89e`、文字 `#7c2d12` |
| 输入滑杆 | `accent-color: var(--molten)` |

---

## 4. 角色视图配色（分角色切换）

| 视图 | 主强调色 | 顶栏渐变 |
|---|---|---|
| 炉长驾驶舱（生产） | `--molten` 熔融橙 | `linear-gradient(120deg,#c2410c,#e8590c)` |
| 工艺工作台（工艺专家） | `--steel` 钢蓝 | `linear-gradient(120deg,#1e3a5f,#2b4a6f)` |
| 数据治理台（数据专家） | `--teal` 青绿 | `linear-gradient(120deg,#0b4f44,#0f766e)` |

---

## 5. 废弃清单（frontend/ 霓虹主题，禁止复用）

| 元素 | 原因 |
|---|---|
| 暗色霓虹底 + neon 光晕（`shadow-neon-*`） | 消费级 SaaS 审美，炼钢中控室高亮/粉尘环境可读性差 |
| indigo→purple 渐变、紫色系 | 无工艺语义 |
| `uppercase` 英文标签 + `tracking-widest` | 目标用户为中文现场，无必要 |
| 外链头像/字体/图标（`lh3.googleusercontent.com` 等） | 违反 A6 离线、数据不出厂 |
| 悬浮 AI Copilot 聊天框 + 多智能体卡片 | 违反「对话对象是机理，不是聊天机器人」 |
| 动画 `animate-ping` 常驻呼吸灯 | 工业 HMI 应静止、扫一眼即懂，避免视觉噪声 |

---

## 6. 规则（Rules）

1. **只允许顶部一条渐变**，其余全用扁平实色。
2. **颜色语义收敛为 红=危险 / 黄=偏离 / 绿=正常**，与报警体系（USER_MANUAL §4）一致。
3. **数字必须 tabular-nums 对齐**。
4. **全离线**：不引外链字体/图标/头像，图标用内联 SVG 或 CSS 形状。
5. 新增颜色须在本文档登记 token，禁止散写 hex。

---

*对齐：`VEES_UI_SPEC.html` §04「风格 token」；`PRODUCT_DEFINITION.md` §六「品牌口径」。*
