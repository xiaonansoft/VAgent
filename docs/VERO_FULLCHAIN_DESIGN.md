# VERO_FULLCHAIN_BLUEPRINT · DESIGN.md 设计契约 v1.0

> 生成日期：2026-09-28 | 设计师：颜好看 | 基于：VERO_FULLCHAIN_SPEC.md v1.0（已确认）+ design-system/design-tokens.css v1.0
> 三轴刻度：DESIGN_VARIANCE=3 / MOTION_INTENSITY=2 / VISUAL_DENSITY=7
> 寄存器：Product（文档面）——目标是"赢得工程师的熟悉感与信任"，不是视觉惊艳
> 本文件是 VERO_FULLCHAIN_BLUEPRINT.html 的唯一设计契约源；实现与设计冲突时，以本文件为准，修改须走 §9.4 变更程序

---

## 1. 设计原则（十诫）

1. **文档即工具**：每个视觉决策服务"工程师每天对照使用"，不服务"看起来先进"。对标 Stripe Docs（文与图永不分离）、AWS Well-Architected（支柱式结构）、Vercel/Linear（工程图纸气质）。
2. **首屏即结论**：§0 文档头 + 全链路架构总图，无营销 Hero、无空洞口号、无抽象装饰图形。
3. **零硬编码色**：正文样式 100% 引用 :root Token（design-tokens.css 原样内联到 `<style>` 头部）；style 属性中仅允许 #fff/#000（AC-03）。
4. **零 emoji 图标**：全部功能图标来自内联 Lucide sprite（§附录C 清单，30 个）；正则扫描命中数必须为 0（AC-02）。
5. **工艺域色叙事**：橙=提钒域、钢蓝=炼钢域、灰=公共底座，禁止第四种域色。域色必须同时有文字/图标冗余标注（色弱可读）。
6. **诚实呈现**：仿真/回放驱动的 MVP 内容如实标注（"仿真引擎+SSE+16炉回放驱动"徽章）；"待厂级确认"用显式徽章（AC-06/AC-11）；数字要么可溯源要么标来源（AC-08）。
7. **可编辑性是灵魂**：单文件、零构建、零 CDN、零 JS 框架；内容全在语义 HTML 里，JS 只做三件事（TOC 高亮/折叠/designMode 开关）。
8. **信息密度靠线不靠盒**：VISUAL_DENSITY=7——表格与 1px 分隔线优先，卡片容器克制使用，阴影仅两级。
9. **状态语言统一**：全文档复用 pill 四态（done/run/todo/pending）+ 厂情三态徽章 + 域色三点图例，各只出现一种视觉写法。
10. **克制装饰**：无渐变文字、无毛玻璃、无侧条纹强调、卡片圆角 ≤12px、动效 ≤180ms 且支持 reduced-motion。

## 2. 版式骨架

### 2.1 页面分区（桌面 ≥1024px）

```
┌──────────────────────────────────────────────────────────┐
│ 顶栏 60px（sticky）：文档名+版本 · 状态徽章 · 编辑模式开关   │
├──────────┬──────────────────────────────┬───────────────┤
│ TOC      │ 阅读列（max 1200px 容器内     │ 速览栏        │
│ 216px    │ 实际内容列 max 860px）        │ ≥1440px 显示  │
│ sticky   │                              │ sticky        │
└──────────┴──────────────────────────────┴───────────────┘
```

- **顶栏**：高 60px，surface 底 + 底部 1px border；左=文档短名（fs-h3/600）+ 版本号（等宽 fs-cap/meta 色）；中=当前章节面包屑（速览，非必须）；右=状态 pill 组（版本状态/日期）+ 编辑模式按钮（ghost 样式，pen-line 图标 16px）。
- **TOC（左 216px）**：sticky，top 60px；两级缩进（§ 一级 13px/600，§N.N 二级 12.5px/400 muted）；当前章节 --accent-text 色 + 左侧 2px 当前指示条（TOC 专用，非卡片侧条纹——这是导航态指示，属于允许的导航模式）。
- **速览栏（右，≥1440px）**：sticky；内容=章节进度（已完成/全部，等宽数字）+ 本文档关键结论 3-5 条（一行一条，13px）+ 跳转链接。
- **阅读列**：内容列 max 860px（表格类章节允许破格到 1200px 满宽：§5 模块清单、§3 总图、§4 大图、§8 时间轴，用 `.fullbleed` 类）。

### 2.2 节奏

- 章节纵向间距 --section-y 56px；章节内小节间距 --s6 32px。
- 章节头结构：等宽 §N 编号（--sec-no）+ 章节标题（fs-h2/tracking-title）+ 一句话导读（fs-md/fg-2，≤2 行）。
- 章节分隔：上一章节末尾 1px border-soft + 56px 间距，不用重卡片框住每章。

### 2.3 文档头（§0，非营销 Hero）

- 布局：左 60% 文档题名区 / 右 40% 元信息卡（surface、1px border、r-lg）。
- 左：文档全名（fs-doc）+ 一句话定位（fs-md/fg-2）+ pill 组（文档状态/版本/面向读者/密级）。
- 右：元信息表（无标签行，label-value 两列 13px）：版本号、基线 Spec、变更记录、编辑指南锚点、"如何改这份文档"一句话。
- §0 下方紧跟 §3 架构总图完整呈现（首屏即结论；TOC 中 §3 图与 §0 合并引导，文档实际位置在 §3，§0 末尾放"总图见 §3"锚链 + 缩略示意，避免同图重复渲染两份 DOM）。

## 3. 导航与信息架构

### 3.1 章节地图（对齐 Spec §5 内容契约，版式责任归属）

| 章节 | 版式模式 | fullbleed | 核心组件 |
|------|----------|-----------|----------|
| §0 文档头 | 文档头布局 | - | pill 组、元信息表 |
| §1 使命与边界 | 双栏文本 + 不做清单表 | - | 表格、verdict 框 |
| §2 现状基线 | 资产盘点表 + 证据索引 | - | .tbl、pill 状态 |
| §3 架构总图 | 五层分层横条 | ✓ | .layer、域色节点、图例 |
| §4 数据流大图 | 内联 SVG + 横滚容器 | ✓ | SVG、图例、图注 |
| §5 模块清单 | M1-M18 大表 | ✓ | .tbl--matrix、厂徽章、pill |
| §6 数据资产 | 分组表 + schema 代码块 | - | .tbl、.code |
| §7 门禁 | 支柱式分组（对标 WA）| - | 卡片组、C 编号、警告框 |
| §8 路线图 | 阶段时间轴网格 | ✓ | Grid 时间轴、pill |
| §9 效果验证 | 切换门阶梯 + KPI 表 | - | 步骤条、.tbl |
| §10 风险 | 问题卡 + 未决表 | - | 警告框、help 徽章 |
| §11 附录 | 术语表 + 索引 + 编辑指南 | - | 定义列表、.code |

### 3.2 深链体系

- 每章节 `<section id="sec-3">`，小节 `<h3 id="sec-5-2">`；id 命名 `sec-N`/`sec-N-M`，禁止拼音。
- 章节标题 hover 时右侧出现 hash 图标按钮（16px，muted 色），点击复制 `VERO_FULLCHAIN_BLUEPRINT.html#sec-5-2` 到剪贴板并 toast 提示"已复制深链"（AC-10 配套）。
- 所有 `scroll-margin-top: 72px`（60px 顶栏 + 12px 呼吸）。
- 正文交叉引用统一写法："见 §5.3"，渲染为 `<a href="#sec-5-3">§5.3</a>`（--accent-text 色，下划线仅 hover）。

### 3.3 图例体系（全文档唯一出处）

- 域色三点：`.dot-vanadium`（提钒域）/`.dot-steel`（炼钢域）/`.dot-common`（公共底座）。
- 状态 pill：done（已完成，success tint）/ run（进行中，warn tint）/ todo（待启动，sunken 底）/ pending（待厂级确认，info tint + help-circle 图标 12px）。
- 厂情徽章（中性配色，刻意与域色区分避免混淆）：攀钢西昌 = sunken 底 + fg-2 字；承德建龙 = sunken 底 + fg-2 字 + factory 图标 12px；通用 = 白底 1px border + muted 字。区分靠文字与图标冗余，不靠色相。
- 图例组件 `.legend`：§3/§4 图内图例 + §5 表头下方微型图例，三处图例内容与顺序完全一致。

## 4. 组件规范

### 4.1 表格 `.tbl`（核心资产组件）

- 基础态：1px border 外框，th=sunken 底/fs-cap/600/左对齐，td=13px/fg-2/tabular-nums，行线 border-soft，td 内强调用 `<b>`（fg 色）。
- 大表变体 `.tbl--matrix`（§5 模块清单）：`th` sticky top 60px（表头钉住，长表滚动时不丢列名）；首列 M 编号用等宽/600；行高密度 padding 8px 12px；列宽建议：模块 9% / 职责 18% / 输入 14% / 输出 14% / 推荐逻辑 18% / 复用引擎 12% / 厂情 8% / 状态 7%。
- 数字单元格强制 `font-variant-numeric: var(--num)`；来源标注用 `<sup>` + meta 色，锚到 §11 索引。
- 状态：行 hover 背景 var(--accent-tint) 50% 透明度（用 color-mix），整行可点击跳转对应章节（§5 行 → §4 图中节点位置，视实现成本列为 P1）。

### 4.2 徽章与 pill

见 §3.3；补充规格：pill 高度 22px，padding 2px 10px，fs-cap/600，图标与文字间距 4px（--s1），white-space nowrap；pill 不得嵌套、不得加阴影。

### 4.3 折叠面板

- 原生 `<details><summary>`（键盘与无障碍免费获得）。
- summary 样式：fs-md/600/fg 色，cursor pointer，focus-visible 走全局焦点环；右侧 chevron-down 图标 16px，open 态旋转 180deg，transition transform var(--motion-base) var(--ease)；reduced-motion 下无旋转直接切换。
- 用于：§6 schema 展示、§2 证据明细、§11 术语表分组。**不用于**正文主叙述（首层内容必须直接可见，折叠只放二级细节）。

### 4.4 提示框三型（承袭 DEV_PROCESS_PLAN 的 verdict/warn 语言，Token 化）

- 结论框 `.verdict`：accent-tint 底 + 1px var(--c-molten-600) 40% 透明边，左侧 lucide target 图标 16px + "结论"标签；用于各章末一句话裁决。
- 警告框 `.warnbox`：warn-tint 底 + 1px warn 边，alert-triangle 图标；用于不可行警告/红线。
- 信息框 `.notebox`：sunken 底无图标；用于口径说明与来源标注。

### 4.5 架构图节点卡（§3 总图专用，HTML 组件）

- 尺寸：min-width 148px，min-height 56px，padding 8px 12px，r-md。
- 域节点：底色 var(--domain-*-tint) + 1px var(--domain-*) 边框 + 标题 13px/600/fg + 副行（模块编号/引擎名）等宽 fs-cap/fg-2 + 左上角域色 dot 8px。**禁止左侧粗色条**（绝对禁令：侧条纹强调）。
- 公共节点：surface 底 + border + meta 色图标。
- 选中/悬停：边框加深（color-mix 域色 80% 黑），无阴影跳动。

### 4.6 步骤条与时间轴

- 步骤条（§9 切换门）：flex 横排，每步 = sunken 底块 + 状态 pill + 箭头分隔（lucide arrow-right 16px，meta 色）；移动端自动纵排。
- 时间轴（§8）：CSS Grid，列 = 阶段（MVP/P2/P3/P4），行 = 工作流泳道；单元格 = 事件卡（§4.5 节点卡语言）；阶段列头 = 等宽编号 + 阶段名 + 起止 pill；MVP 列视觉加重（1px --accent 边 + accent-tint 底 40%）。

## 5. 图表规范

### 5.1 通用规则

- 所有图形颜色引用 Token（SVG 内 `fill="var(--domain-steel)"` 合法且必须）。
- SVG 坐标全部吸附 8px 网格；viewBox 整数。
- 每张图必须有：`role="img"` + `aria-label`（一句话总述）+ `<title>`；数据流图另加 `<desc>` 长描述（无障碍）。
- 图内文字最小 11px（等宽轴标注允许 10px），禁止小于 10px。
- 图例位置固定右下角（§4 大图）/图下方（§3 总图），样式用 §3.3 统一图例。

### 5.2 §3 架构总图（五层 × 双工序，HTML/CSS Grid 分层横条）——绘制规范见附录 A

### 5.3 §4 全链路数据流大图（内联 SVG，双工序生命周期）——绘制规范见附录 B

### 5.4 数据小图（曲线/回放示意，如 §2 现状基线引用）

- 承袭 MVP 的手绘 SVG 曲线语言：坐标轴 #999 系（用 var(--meta)）、网格线 var(--border-soft)、曲线 1.5-2px、数据点半径 3-3.5px + `<title>` tooltip。
- 蓝图文档中的数据图一律为"示意图"属性：图注必须标注数据来源（如"数据：16 炉回放，PLANT_A_EXCEL_DECODED.md"），禁止无来源图表。

## 6. 交互规范

### 6.1 TOC 滚动高亮（scroll spy）

- IntersectionObserver 监听全部 section，rootMargin 顶部 -40% 底部 -55%，当前章节 TOC 项加 `.on` 类（--accent-text 色 + 2px 指示条）。
- 切换动效：颜色 120ms；不做滚动动画。

### 6.2 折叠

- 原生 details；批量控制仅在 §11 术语表提供"展开全部/收起全部"两个 ghost 按钮。

### 6.3 编辑模式（designMode 开关）

- 顶栏按钮，点击 `document.designMode = 'on'/'off'` 切换；开启后：
  - 页面顶部出现 32px 提示条（sticky，accent-tint 底）："编辑模式已开启——直接点击修改文字，改完全选复制即可带走。关闭请再点一次按钮。"（语言具体，无空话）
  - 按钮态变为 .on（accent 底白字）。
  - designMode 对 TOC/顶栏同样可编辑，属预期行为，不做屏蔽。

### 6.4 深链复制

- 章节 hover hash 按钮 → `navigator.clipboard.writeText` → 右下角 toast（180ms 进入，2.4s 自动消失，surface 底 + 1px border + check-circle-2 图标）。clipboard 失败降级为 prompt 选中文本。

### 6.5 动效预算（全文档）

| 交互 | 时长 | 缓动 |
|------|------|------|
| TOC 高亮换色 | 120ms | ease |
| summary chevron 旋转 | 180ms | --ease |
| toast 进入/退出 | 180ms | --ease |
| 节点/行 hover 边框 | 120ms | ease |
| 深链滚动定位 | 浏览器原生 | - |

- 全局 `@media (prefers-reduced-motion: reduce){ *{transition:none!important;animation:none!important} }`。
- 禁止：弹跳缓动（AC-12 正则扫描项）、滚动劫持、入场级联动画。

## 7. 响应式

| 断点 | 行为 |
|------|------|
| ≥1440px | 三栏：TOC + 阅读列 + 速览栏 |
| 1024-1439px | 两栏：TOC + 阅读列；速览栏隐藏 |
| 768-1023px | 单列：TOC 收进顶栏下拉（顶栏汉堡按钮 + chevron）；fullbleed 章节恢复 860px |
| <768px | 单列窄版：表格字号保持 13px（禁止缩小到 12px 以下）；.tbl--matrix 允许横向滚动容器（overflow-x:auto + 容器右缘 24px 渐隐遮罩提示可滚）；§4 大图横向滚动（见附录 B §B6） |

- 触摸目标：所有可点击元素 ≥44×44px（含 TOC 链接 padding 补足、hash 按钮 hit-area 32px + padding）。
- 断点只有 768/1024/1440 三档（Spec 边界约束），不引入更多断点。

## 8. 无障碍

### 8.1 对比度（已验证组合，实现时不得偏离）

| 前景 | 背景 | 比值 | 用途 |
|------|------|------|------|
| --fg #141D2B | --bg #F6F7F9 | 14.9:1 | 正文 |
| --fg-2 #3D4A5F | --surface #FFF | 9.4:1 | 表格正文 |
| --muted #6B7686 | --surface #FFF | 4.6:1 | 辅助文字（≥12px 专用） |
| --accent-text #C2410C | --surface #FFF | 5.2:1 | 链接/强调文字 |
| --c-molten-600 #E8590C | --surface #FFF | 3.4:1 | **仅限 ≥18px/600 图形与大字号**，禁止用于正文与 13px 以下文字 |
| --success/--warn/--danger | 各自 tint 底 | ≥4.5:1 | pill 文字 |
| --fg #141D2B | --accent-tint #FDEEE3 | 12.8:1 | 结论框正文 |

### 8.2 键盘导航

- Skip link："跳到正文"（首个 Tab 焦点，视觉隐藏聚焦时显示）。
- Tab 顺序：顶栏 → TOC → 正文（details/summary、hash 按钮、表格内链接原生可达）。
- focus-visible 全局：`outline: 2px solid var(--info); outline-offset: 2px`（承袭 v0.9 焦点语言，橙色焦点环预留给编辑模式按钮等品牌触点：`--focus-ring`）。

### 8.3 非颜色冗余

- 域色必有文字/图标冗余：节点 dot + 域名文字；图例三色三点 + 文字。
- 状态 pill 有文字；箭头语言（实/虚/渐变）有图例文字 + 线端 marker 形状差异。
- 禁止仅用颜色区分（如"红色行 = 风险"必须同时有 alert 图标或文字标签）。

### 8.4 屏幕阅读器

- SVG role="img" + title + desc（§4）；分层横条用语义列表或带 aria-labelledby 的分区。
- 表格 th scope="col/row"；厂情徽章有文字本身，无需额外 aria。
- toast 用 aria-live="polite"。

## 9. 自查清单（QA 门禁前置自检）

### 9.1 P0 硬门（任何一条不过 = 重做）

- [ ] emoji 正则 `[\x{1F300}-\x{1F9FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}]` 全文扫描命中 0（AC-02）
- [ ] style 属性十六进制扫描命中 0（#fff/#000 除外）（AC-03）
- [ ] 紫粉渐变正则 + 弹跳缓动正则命中 0（AC-12）
- [ ] 断网打开完整渲染，零外部请求（AC-01）
- [ ] Lucide sprite 仅含附录 C 清单图标，无第二图标库混入
- [ ] 无 "Lorem ipsum"/"Welcome to"/空洞占位文案；全部数字可溯源或带来源（AC-08）
- [ ] "待厂级确认"项 100% 有 pending 徽章（AC-11）

### 9.2 结构门

- [ ] §3 总图：五层 × 双工序、节点 ≤22、工序内前/中/后合并分组（AC-04）
- [ ] §5 表：M1-M18 全行 × 7 列齐全（AC-05）
- [ ] §8 路线图：MVP 三阶段 × 双工序 + 仿真驱动标注（AC-06）
- [ ] §9：切换门按操作包络覆盖度表述 + KPI ≥7 项含数据源列（AC-07）

### 9.3 体验门

- [ ] 深链直达 + TOC 高亮正确（AC-10）
- [ ] designMode 开关 + 编辑指南注释在文件头（AC-09）
- [ ] 对比度全部落在 §8.1 验证组合内
- [ ] prefers-reduced-motion 生效
- [ ] <768px 无横向页面滚动（表格/SVG 容器内滚动除外）、文字 ≥12px
- [ ] 交互组件键盘可达、focus-visible 可见

### 9.4 变更程序

本文档修改：只追加/修正具体条目（禁止整篇重写），末尾变更表记一行（日期+条目+原因+影响）。

---
---

# 附录 A · §3 架构总图绘制规范（五层 × 双工序分层横条）

> 本附录可直接指导前端实现，含节点清单、布局网格、域色分配。

## A1 布局结构

整体 = 垂直堆叠 5 条层横条（layer），每条内部 = CSS Grid 横排节点卡（§4.5 组件）。层条间距 --s4 16px。

```
┌─ 应用层（触点层）────────────────────────────── [灰/公共] ─┐
│  [驾驶舱] [仲裁工作台] [治理看板]                          │
├─ L3 智能体编排层 ─────────────────────────────────────────┤
│  [提钒三阶段图 (LangGraph)]   [半钢三阶段图 (LangGraph)]   │ ← 橙 | 钢蓝
├─ L2 机理引擎层 ───────────────────────────────────────────┤
│  [既有八大引擎组(提钒)] [sdm_semisteel_balance] [reheating_agent_solver] │
├─ 数据层 ─────────────────────────────────────────────────┤
│  [DATA_INTERFACE_SPEC v0.2] [semisteel_transfer 契约] [软测量] [知识包 plant_a/plant_b] │
├─ L3' 学习治理层（虚线框=贯穿层）──────────────────────────┤
│  [RLS 双段独立参数组] [知识包审批流] [mode_control 三态]    │
└───────────────────────────────────────────────────────────┘
         ↕ 层间垂直细箭头（调用方向，meta 色 1px）
```

## A2 节点清单与域色分配（共 16 节点，预算 ≤22 达标）

| # | 层 | 节点 | 域色 | 副行文字（等宽 fs-cap） | 备注 |
|---|----|------|------|------------------------|------|
| 1 | 应用 | 驾驶舱（操作工） | 公共 | cockpit | 含 v0.9 存量 |
| 2 | 应用 | 仲裁工作台（专家） | 公共 | arbiter | P4 设计呈现 |
| 3 | 应用 | 治理看板（管理员） | 公共 | governance | P4 设计呈现 |
| 4 | L3 | 提钒三阶段图 | 提钒(橙) | graph_v · 前/中/后 | 组内三行小字列"冶炼前/冶炼中/冶炼后" |
| 5 | L3 | 半钢三阶段图 | 炼钢(钢蓝) | graph_s · 前/中/后 | 同上 |
| 6 | L2 | 既有八大引擎组（提钒） | 提钒 | plant_a engines ×8 | 单节点聚合，避免节点爆炸 |
| 7 | L2 | sdm_semisteel_balance | 炼钢 | semisteel_balance | 新增 |
| 8 | L2 | reheating_agent_solver | 炼钢 | reheating_solver | 新增 |
| 9 | 数据 | DATA_INTERFACE_SPEC v0.2 | 公共 | data_interface | |
| 10 | 数据 | semisteel_transfer 契约 §3.6 | 公共 | transfer_contract | 双工序衔接数据契约 |
| 11 | 数据 | 软测量 | 公共 | soft_sensor | |
| 12 | 数据 | 知识包（plant_a/plant_b） | 公共 | packs v1.1.0 | 双厂徽章（攀钢/建龙）|
| 13 | L3' | RLS 双段独立参数组 | 公共 | rls ×2 | 虚线连 L2（回流）|
| 14 | L3' | 知识包审批流 | 公共 | approval_flow | |
| 15 | L3' | mode_control 三态 | 公共 | shadow/advisory/learn | |
| 16 | （浮层）| 双工序衔接锚 | 交接 | transfer | 见 A4 |

## A3 网格与尺寸

- 层横条：padding --s3 12px --s4 16px；`grid-template-columns: repeat(auto-fit, minmax(148px, 1fr))`；gap --s3 12px。
- 层头：左侧等宽层名（fs-cap/600/meta 色/ALL CAPS 0.06em）+ 右侧一句话职责（fs-cap/muted）。
- 节点卡：min-height 56px；L3 两个三阶段图节点 min-height 72px（容纳三行小字）。
- 层间关系：不画 DOM 连线（HTML 层条之间用 12px 间距 + 层序自明）；仅 L3' 与 L2 之间放一条 1px 虚线水平分隔 + 中央小字"RLS 参数回流 / 知识包版本注入"（refresh-cw 图标 12px + 等宽标注），表达贯穿关系。

## A4 双工序衔接视觉锚

- L3 层内两节点（graph_v 与 graph_s）之间放一个交接元素：git-merge 图标 20px（fg-2 色）+ "半钢+钒渣"标注（fs-cap/600）+ 上下短箭头指向两节点；此元素不带底色（负空间锚点，非卡片）。
- 这是总图唯一的工序衔接视觉重点，不使用渐变（渐变语言保留给 §4 大图的交接箭头，全文档渐变仅 1-2 处，集中在数据流大图）。

## A5 图例与图注

- 总图下方：§3.3 统一图例（三域色点 + "节点=模块/引擎/契约"说明）+ 图注一行："节点计数 15 + 1 交接锚 = 16（预算 ≤22）；M1-M18 明细见 §5；数据流走向见 §4。"
- 禁止在总图内塞模块编号明细（M1-M18 全量在 §5 表格，总图 L3 节点内只列"前/中/后"三行）。

## A6 响应式

- ≥768px：层条横排；<768px：每层节点自动换行（auto-fit 兜底），层头保持横排。
- 无横向滚动（HTML 组件天然回流，这是选择 CSS Grid 而非 SVG 做总图的核心原因）。

---

# 附录 B · §4 全链路数据流大图绘制规范（内联 SVG）

> 双工序生命周期核心图。SVG 手写，文字 `<text>` 直改，颜色全 Token 引用。

## B1 画布与总体结构

- viewBox `0 0 1360 780`，`width="100%"`，置于 `.svg-scroll` 容器（见 B6）。
- 结构 = 上下两条工艺泳道 + 底部数据带 + 中央垂直交接区：

```
y:0-40    标题带：图名（13px/600）+ 泳道标签
y:48-268  泳道① 提钒转炉（橙域）：铁水 → 冶炼前 → 冶炼中 → 冶炼后 ─┐
y:300-420 中央交接区：半钢（主交接·渐变箭头） / 钒渣（侧出口·虚线）  │
y:452-672 泳道② 半钢冶炼转炉（钢蓝域）：冶炼前 → 冶炼中 → 冶炼后 → 出钢
y:700-760 底部数据带（灰域）：接口/契约/知识包/RLS 回流（点线回路上行）
```

- 泳道背景：泳道① fill var(--domain-vanadium-tint) 30% 不透明度（或 color-mix 进 bg）、圆角 r-lg；泳道② 同理钢蓝。泳道左上角标签：dot + "提钒转炉（工序一）"13px/600。

## B2 节点清单（15 主节点）

| # | 泳道 | 节点 | x 区段 | 域色 | 节点内文字 |
|---|------|------|--------|------|-----------|
| 1 | ① | 铁水输入（化验单） | 左端 | 公共 | 铁水 · 化验单 / 等宽: hot_metal |
| 2 | ① | 冶炼前·配料优化 | | 橙 | M1-M3 / 配吃建议 |
| 3 | ① | 冶炼中·实时推荐 | | 橙 | M5-M8 / SSE 仿真回放驱动 |
| 4 | ① | 冶炼后·复盘归因 | | 橙 | M9-M12 / 品位归因+判例 |
| 5 | 交 | 半钢（主交接节点） | 中央 | 交接 | 半钢 / semisteel |
| 6 | 交 | 钒渣出口 | 中央偏下 | 橙(虚线出) | 钒渣 / → M13 契约预留 |
| 7 | ② | 冶炼前·配料+提温剂 | | 钢蓝 | M14-M15 / 提温剂求解 |
| 8 | ② | 冶炼中·动态推荐 | | 钢蓝 | M16 / 碳温双命中 |
| 9 | ② | 冶炼后·复盘 | | 钢蓝 | M17 / 命中归因+RLS |
| 10 | ② | 出钢 | 右端 | 公共 | 出钢 / tapping |
| 11 | 数据带 | DATA_INTERFACE_SPEC | | 灰 | v0.2 |
| 12 | 数据带 | semisteel_transfer | | 灰 | 双工序契约 |
| 13 | 数据带 | 知识包 plant_a/plant_b | | 灰 | v1.1.0 · 双厂 |
| 14 | 数据带 | RLS 双段参数组 | | 灰 | rls_v / rls_s |
| 15 | 数据带 | 判例库 | | 灰 | precedent |

## B3 节点尺寸与文字层级

- 工艺节点：136×64，r-md 8px；交接节点（半钢）：160×76，边框 2px fg 色加粗 + 轻微 accent-tint 底——全图唯一加粗边框节点（视觉锚点）。
- 数据节点：120×44。
- 节点文字三行制：标题 13px/600/fg（工艺节点白字仅当深色底；本图节点底色均为 tint 浅底故文字统一 var(--fg)）；模块编号等宽 11px/fg-2；域标签 10px/meta。
- 全部 `<text>` 直改；节点 `<g id="node-m5" ...>` 注释分组，坐标吸附 8px。

## B4 箭头语言（marker 预定义 4 种）

| marker id | 形态 | 语义 | 规格 |
|-----------|------|------|------|
| arr-solid | 实线箭头 | 主工艺流（物料/铁水/半钢/出钢） | 1.5px，泳道内同域色 |
| arr-data | 虚线箭头 | 数据流（化验/台账→节点） | 1px，meta 色，dasharray 4 3 |
| arr-feedback | 点线箭头 | 知识/参数回流（复盘→知识包/RLS→下一炉） | 1px，var(--info)，dasharray 1 3，linecap round |
| arr-transfer | 渐变箭头 | **双工序交接专用（唯一渐变）** | 2px，stroke=url(#grad-handover)，linearGradient 从 var(--domain-vanadium) → var(--domain-steel)，方向沿箭头走向 |

- 渐变箭头仅 1 处：节点4(冶炼后·提钒) → 交接节点5(半钢)。钒渣出口用虚线（数据契约性质，非物料主流程入图）。
- 侧向约束线：泳道①上缘画一条 1px var(--c-molten-600) 40% 透明长线 + 端点小字"提钒域边界"；泳道②下缘同理钢蓝（域边界显式化，帮助读者理解"跨域"发生在哪里）。

## B5 图例（右下角固定块，120×160）

内容三组，顺序固定：① 域色三点（提钒/炼钢/公共）；② 四箭头线型各一小段 + 语义文字（10.5px）；③ 一行注："半钢交接节点=全链路唯一加粗框；MVP 阶段冶炼中节点由仿真引擎+SSE+16炉回放驱动（run pill 小徽章内嵌于节点 3/8 角标）"。

## B6 响应式与可编辑性

- 容器 `.svg-scroll`：`overflow-x:auto; min-width:0`；SVG `min-width:960px`（<768px 时横向滚动而非等比缩小——保证 13px 文字可读，这是有意决策：可读性 > 一屏完整）。
- 容器右缘滚动渐隐提示：24px 宽遮罩渐变（bg→透明，纯 CSS mask）。
- 图下方紧跟"图注行"：数据来源标注（如"口径：plant_a/base.yaml；回放：16 炉实绩"）+ "此图为 SVG，文字可直改：F12 定位 `<text>` 或 VS Code 搜索节点 id"一句（可编辑性引导，具体操作链到 §11 编辑指南）。

---

# 附录 C · Lucide 图标清单（sprite 内联 30 个，锁定）

> sprite 结构：`<svg style="display:none">` 内 30 个 `<symbol id="i-*" viewBox="0 0 24 24">`；正文引用 `<svg class="icon" aria-hidden="true"><use href="#i-layers"/></svg>`。仅以下 30 个允许出现，禁止再加第二图标库。

| # | symbol id | Lucide 名 | 使用位置 | 语义 |
|---|-----------|-----------|----------|------|
| 1 | i-target | target | §1 章头 / verdict 框 | 使命/结论 |
| 2 | i-trending-up | trending-up | §2 章头 | 现状基线 |
| 3 | i-layers | layers | §3 章头 / L2 层头 | 架构分层 |
| 4 | i-workflow | workflow | §4 章头 / L3 层头 | 数据流/编排 |
| 5 | i-boxes | boxes | §5 章头 | 模块清单 |
| 6 | i-database | database | §6 章头 / 数据层节点 | 数据资产 |
| 7 | i-shield-check | shield-check | §7 章头 | 质量门禁 |
| 8 | i-map | map | §8 章头 | 路线图 |
| 9 | i-chart-line | chart-line | §9 章头 | 效果验证 |
| 10 | i-alert-triangle | alert-triangle | §10 章头 / warnbox | 风险/警告 |
| 11 | i-book-open | book-open | §11 章头 / 术语表 | 附录 |
| 12 | i-flame | flame | 域色图例/提钒域标注 | 提钒域（铁水） |
| 13 | i-factory | factory | 厂情徽章/厂适配节 | 工厂/双厂 |
| 14 | i-git-merge | git-merge | 总图交接锚/§4 交接区 | 双工序衔接 |
| 15 | i-refresh-cw | refresh-cw | RLS 回流/闭环标注 | 知识回流 |
| 16 | i-cpu | cpu | L2 引擎节点 | 机理引擎 |
| 17 | i-zap | zap | SSE/实时推荐标注 | 实时流 |
| 18 | i-clock | clock | 延迟预算表 | 10s 预算切分 |
| 19 | i-check-circle-2 | check-circle-2 | done pill / toast | 已完成 |
| 20 | i-play | play | run pill | 进行中 |
| 21 | i-circle-dashed | circle-dashed | todo pill | 待启动 |
| 22 | i-alert-octagon | alert-octagon | 不可行警告/永久红线 | 红线 |
| 23 | i-lock | lock | IP 边界标注 | 密级/不出厂 |
| 24 | i-help-circle | help-circle | pending 徽章（待厂级确认） | 未决 |
| 25 | i-chevron-down | chevron-down | details 折叠 | 展开/收起 |
| 26 | i-pen-line | pen-line | 编辑模式按钮 | designMode |
| 27 | i-copy | copy | 复制/导出标注 | 可编辑性 |
| 28 | i-hash | hash | 章节深链按钮 | #锚点 |
| 29 | i-external-link | external-link | 工件索引外链 | 引用 |
| 30 | i-users | users | 角色相关表格（Owner 列） | 角色 |

**尺寸纪律**：行内 16px / 按钮 16px / 章头 20px / 交接锚等强调位 20px / 大图域标注 24px 仅限图内。stroke-width 统一 2（继承 .icon 类），stroke=currentColor。

---

## 变更记录

| 日期 | 条目 | 变更 | 原因 | 影响 |
|------|------|------|------|------|
| 2026-09-28 | 全文 | 初版 v1.0 | Phase 2 启动 | 全文档 |
