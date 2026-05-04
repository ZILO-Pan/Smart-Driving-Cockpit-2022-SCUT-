# Active Cabin OS — 智能座舱 HMI 前端原型 · Claude Code 工作指令

> **给 Claude 4.6（Claude Code）的一次性完整工作指令**
> 目标：构建一个纯前端、可演示、不依赖任何后端的智能座舱 HMI 交互原型
> 后续我会自己用 Claude Code 接入 WebSocket / CARLA / 火山引擎 API

---

## 0. 工作模式说明

请你**分阶段实现**这个项目，每完成一个阶段就停下来让我确认效果，再进入下一阶段。

阶段顺序（严格遵守）：
1. **Stage 1**：项目脚手架 + 设计系统 CSS 变量 + 主界面静态视觉骨架
2. **Stage 2**：AI 助手液态玻璃球 + 6 种状态动画
3. **Stage 3**：启动动画
4. **Stage 4**：11 个 Dock 的点击交互 + 全局状态机
5. **Stage 5**：5 个 Demo 场景一键播放
6. **Stage 6**：服务卡片 + 文本输入 + 关键词触发

完成 Stage 1 后**停下来**告诉我："Stage 1 完成，请查看效果。视觉骨架是否符合 OVEA 风格？"。我确认后再继续 Stage 2。

---

## 1. 项目背景与定位

### 1.1 毕业设计主题

《面向舱驾一体场景的端云协同多模态智能座舱主动服务系统设计研究》

### 1.2 这是什么

一个运行在**车载横向长屏（3840 × 590）**上的车机操作系统 HMI 原型，用于答辩演示。

**不是**：网站、landing page、营销页面、手机 App、聊天软件。
**是**：真实运行在车机上的操作系统界面。

### 1.3 用户使用场景

答辩时用户会有两块屏幕：
- 屏幕 1：CARLA 自动驾驶仿真画面（独立运行）
- 屏幕 2：本 HTML HMI（这次要做的）

打开 HTML 立刻进入车机界面，所有数据用前端 Mock，**不接任何后端**。

### 1.4 核心体验关键词

舱驾一体 · 端云协同 · 多模态感知 · 主动服务 · 模糊意图理解 · AI 任务拆解 · HMI 可解释反馈 · CARLA 驾驶控制 · 生活服务调用 · 轻量语义知识库

---

## 2. 视觉风格（重中之重，反复强调）

### 2.1 主视觉风格：OVEA Design Language

**整体是 OVEA 设计语言**——一种克制、精密、车规级的未来感。参考要素：
- 深海军蓝实色背景（`#1A2840`）
- 巨大留白（≥ 50% 屏幕面积）
- 极细字体（weight 200-300 为主，几乎不用 600+）
- 圆角胶囊与卡片
- 单点信息聚焦（每个面板只突出一个核心数字/状态）
- 描边按钮为主，几乎不用实心填充

**禁止**：
- ❌ 整屏液态玻璃磨砂效果（这不是 visionOS 风格）
- ❌ 大面积渐变背景
- ❌ 高饱和霓虹色
- ❌ 纯黑 `#000000` 背景
- ❌ 任何手机 App 风格的彩色填充按钮
- ❌ 游戏 UI 风格的发光特效
- ❌ 营销网站风格的大标题

### 2.2 唯一的液态玻璃元素：AI 助手对话球 ⭐

**液态玻璃（Liquid Glass）只用在一处**：右侧 AI 助手核心球。

这个紫蓝色的 200×200px 玻璃球是**整套界面的视觉灵魂**——OVEA 极简骨架中唯一闪着光的液态元素。具体规范见第 5 节。

**其他所有卡片、面板、Dock 都禁止使用 backdrop-filter**。

---

## 3. 画布与适配

```
- 主设计尺寸：3840 × 590（车载横向长屏）
- HTML 容器：width: 100vw; height: 100vh;
- 内部主体严格按 3840:590 比例设计
- 浏览器窗口非该比例时：整体等比缩放或居中裁切
- 禁止纵向滚动条
- 禁止移动端响应式布局
```

实现建议：用一个 `transform: scale()` 让 3840×590 的内部画布等比缩放到当前 viewport，超出部分隐藏。

---

## 4. 设计系统（Stage 1 必须先建立的 CSS 变量）

### 4.1 颜色

```css
:root {
  /* 背景层 */
  --bg-deep:           #0A1628;
  --bg-night:          #1A2840;          /* 主背景 */
  --bg-card:           #1F2D45;          /* 卡片底（实色，不是玻璃）*/
  --bg-card-hover:     #243450;
  --bg-light:          #F2F2F2;

  /* 品牌主色 */
  --accent-primary:    #5B5BFF;          /* OVEA 紫蓝，AI 助手主色 */
  --accent-light:      #7B7BFF;
  --accent-glow:       rgba(91, 91, 255, 0.4);

  /* 功能色 */
  --success:           #3BE5B0;
  --info-cyan:         #4DD8E5;          /* 选中描边、数据高亮 */
  --alert-pink:        #FF4D8F;          /* 仅作小圆点提醒 */
  --warning:           #FFAA33;
  --danger:            #FF4D5E;

  /* 文字 */
  --text-primary:      rgba(255, 255, 255, 1);
  --text-secondary:    rgba(255, 255, 255, 0.6);
  --text-tertiary:     rgba(255, 255, 255, 0.35);

  /* 描边 */
  --border-subtle:     rgba(255, 255, 255, 0.08);
  --border-default:    rgba(255, 255, 255, 0.15);
  --border-active:     var(--info-cyan);

  /* 渐变 */
  --gradient-brand:    linear-gradient(135deg, #5B5BFF 0%, #8B6FFF 100%);
  --gradient-thruster: linear-gradient(180deg, rgba(91,91,255,0) 0%, #5B5BFF 100%);
}
```

### 4.2 字体

```css
:root {
  --font-display: 'Inter Display', 'Inter', 'PingFang SC', sans-serif;
  --font-body:    'Inter', 'PingFang SC', sans-serif;
  --font-mono:    'JetBrains Mono', 'SF Mono', monospace;
}
```

字号阶梯（车载 3840×590 实际像素）：

```css
.text-hero      { font-size: 200px; font-weight: 200; line-height: 1.0; }   /* 中央巨型数字 */
.text-display   { font-size: 96px;  font-weight: 300; line-height: 1.05; }  /* 屏幕级标题 */
.text-h1        { font-size: 64px;  font-weight: 300; line-height: 1.1; }   /* 卡片大数字 */
.text-h2        { font-size: 32px;  font-weight: 400; line-height: 1.2; }   /* 卡片标题 */
.text-h3        { font-size: 24px;  font-weight: 400; line-height: 1.3; }
.text-body      { font-size: 16px;  font-weight: 400; line-height: 1.5; }
.text-label     { font-size: 14px;  font-weight: 500; line-height: 1.4;
                  letter-spacing: 0.05em; text-transform: uppercase; }
.text-caption   { font-size: 12px;  font-weight: 400; line-height: 1.4; }
.text-mono      { font-family: var(--font-mono); font-size: 11px;
                  letter-spacing: 0.05em; }
```

**关键规则**：
- 大数字必须 weight 200-300（细体）
- 全大写标签（PROACTIVE / EDGE ONLINE / AUTO）必须 `letter-spacing: 0.05em`
- 中文配 PingFang SC，禁止微软雅黑

### 4.3 圆角

```css
:root {
  --radius-sm:     8px;
  --radius-md:     16px;
  --radius-lg:     24px;          /* 卡片默认 */
  --radius-xl:     32px;
  --radius-pill:   9999px;        /* 胶囊按钮、状态徽章 */
}
```

### 4.4 间距（8 倍数）

```css
:root {
  --space-1: 4px;    --space-2: 8px;     --space-3: 12px;
  --space-4: 16px;   --space-6: 24px;    --space-8: 32px;
  --space-12: 48px;  --space-16: 64px;   --space-24: 96px;
}
```

### 4.5 动效

```css
:root {
  --ease-default:  cubic-bezier(0.4, 0, 0.2, 1);
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-liquid:   cubic-bezier(0.32, 0.72, 0, 1);

  --dur-fast:    200ms;
  --dur-base:    350ms;
  --dur-slow:    600ms;
  --dur-ambient: 2400ms;          /* AI 球呼吸 */
}
```

---

## 5. 关键组件规范

### 5.1 标准卡片（OVEA 风格 — 实色，禁止玻璃）

```css
.card {
  background: var(--bg-card);                        /* 实色 #1F2D45 */
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  position: relative;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
  /* 禁止使用 backdrop-filter */
}

.card.active {
  border-color: var(--info-cyan);                    /* cyan 描边，不是品牌紫 */
  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.2),
    0 0 0 1px var(--info-cyan),
    0 0 16px rgba(77, 216, 229, 0.2);
}

/* 卡片右上角拖拽手柄（OVEA 标志细节 ⋮⋮）*/
.card-handle {
  position: absolute;
  top: 16px; right: 16px;
  width: 32px; height: 32px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.15);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
}
.card-handle::before {
  content: '⋮⋮';
  font-size: 14px;
  color: var(--text-tertiary);
  letter-spacing: -2px;
}
```

**卡片内部布局**：
- 标签贴顶（`text-label` UPPERCASE）
- 主数字偏中靠上
- 辅助信息贴底
- **中间大量留白**

### 5.2 按钮

```css
/* 默认：Outline 胶囊（OVEA 主流）*/
.btn-ghost {
  border: 1px solid rgba(255, 255, 255, 0.4);
  background: transparent;
  border-radius: var(--radius-pill);
  padding: 12px 24px;
  color: var(--text-primary);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  font-size: 14px;
  cursor: pointer;
  transition: all var(--dur-base) var(--ease-default);
}
.btn-ghost:hover {
  border-color: rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.04);
}

/* 主操作：实心紫蓝（每屏最多 1 个）*/
.btn-primary {
  background: var(--accent-primary);
  border: none;
  border-radius: var(--radius-pill);
  padding: 12px 24px;
  color: white;
  font-size: 14px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  cursor: pointer;
}

/* 状态徽章（小胶囊）*/
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-default);
  font-size: 11px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-secondary);
}
.status-badge::before {
  content: '';
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--success);          /* 状态点颜色，按状态切换 */
}
```

### 5.3 AI 助手液态玻璃球 ⭐（唯一使用 backdrop-filter 的组件）

这是整个界面的视觉灵魂，请重点投入精力。

```css
.ai-orb {
  width: 200px;
  height: 200px;
  border-radius: 50%;
  position: relative;

  /* 液态玻璃材质 */
  background: rgba(91, 91, 255, 0.12);
  backdrop-filter: blur(40px) saturate(160%);
  -webkit-backdrop-filter: blur(40px) saturate(160%);

  /* 玻璃边缘双层高光 */
  border: 1px solid rgba(255, 255, 255, 0.24);
  box-shadow:
    inset 0 1px 1px rgba(255, 255, 255, 0.5),     /* 顶部内高光 */
    inset 0 -1px 1px rgba(91, 91, 255, 0.3),      /* 底部紫色反射 */
    0 0 60px rgba(91, 91, 255, 0.4),              /* 外发光 */
    0 16px 48px rgba(0, 0, 0, 0.4);               /* 投影 */

  cursor: pointer;
  transition: all var(--dur-slow) var(--ease-liquid);
}

/* 球体内部的径向辉光（让球有"体积"和"液态感"）*/
.ai-orb::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: radial-gradient(
    circle at 35% 30%,
    rgba(255, 255, 255, 0.35) 0%,
    rgba(123, 123, 255, 0.2) 30%,
    rgba(91, 91, 255, 0) 70%
  );
  pointer-events: none;
}

/* 内部呼吸核心 */
.ai-orb::after {
  content: '';
  position: absolute;
  top: 50%; left: 50%;
  width: 60px; height: 60px;
  border-radius: 50%;
  background: var(--gradient-brand);
  filter: blur(8px);
  transform: translate(-50%, -50%);
  animation: ai-breathe var(--dur-ambient) ease-in-out infinite;
  pointer-events: none;
}

@keyframes ai-breathe {
  0%, 100% { opacity: 0.6; transform: translate(-50%, -50%) scale(1.0); }
  50%      { opacity: 1.0; transform: translate(-50%, -50%) scale(1.15); }
}

/* AI 球的 6 种状态（Stage 2 实现）*/
.ai-orb[data-state="idle"]          { /* 默认呼吸 */ }
.ai-orb[data-state="listening"]     { /* 同心圆音波扩散 */ }
.ai-orb[data-state="understanding"] { /* 水平扫描线 */ }
.ai-orb[data-state="planning"]      { /* 内部数据节点连线 */ }
.ai-orb[data-state="executing"]     { /* 表面粒子向外发射 */ }
.ai-orb[data-state="completed"]     { /* 短暂金绿色 success 外发光 */ }
```

### 5.4 进度环

参考 OVEA Battery 截图风格：
- 背景轨道：4px / `rgba(255,255,255,0.1)`
- 进度填充：6px / 对应功能色（success/info）
- 起点：底部 6 点钟方向，顺时针填充
- 中央：超细字重大数字 + 小字单位

### 5.5 推进器/能量条

参考 OVEA panoramic compass 截图风格的 L 形拐角条：
- 从底部向上填充紫蓝色
- 用于速度/油门/能耗等条状状态显示

### 5.6 图标

使用 **Lucide Icons**，通过 CDN 加载：

```html
<script src="https://unpkg.com/lucide@latest"></script>
<!-- 在页面底部初始化 -->
<script>lucide.createIcons();</script>
```

使用方式：
```html
<i data-lucide="mic"></i>
<i data-lucide="thermometer"></i>
```

规范：1.5px 描边、圆角端点、24×24 网格。**禁止**填充式、彩色、emoji 风格图标。

---

## 6. 文件结构

```
project/
├── index.html         # HTML 结构
├── styles.css         # 所有样式
└── app.js             # 状态管理 + 交互逻辑 + Mock 数据
```

不要使用任何构建工具（不要 React/Vue/Webpack/Vite），保持纯 HTML/CSS/JS。

---

## 7. 信息架构

页面分为 5 层：

```
┌──────────────────────────────────────────────────────────────────┐
│ 01 顶部状态栏（高 56px，实色细条）                                │
├──────────────────┬──────────────────────────┬───────────────────┤
│ 02 左侧状态区     │ 03 中央舱驾一体可视化区     │ 04 右侧 AI 服务区  │
│ (宽 ~600px)       │ (宽 ~1800px)              │ (宽 ~1300px)       │
│                  │                          │                   │
│ - 车辆状态卡       │ - 道路 + 自车 + 周车         │ - AI 助手液态球 ⭐ │
│ - 座舱状态卡       │ - 车道线 + 路线箭头          │ - 对话区          │
│ - 快捷控制         │ - 驾驶意图解释胶囊条          │ - 意图理解面板     │
│                  │ - Unity WebGL Slot 标记     │ - 任务拆解面板     │
│                  │                          │ - 服务卡片        │
├──────────────────┴──────────────────────────┴───────────────────┤
│ 05 底部 11 功能 Dock（高 80px，11 个胶囊按钮水平排列）             │
└──────────────────────────────────────────────────────────────────┘
```

宽度比例参考（3840 总宽）：
- 左侧：约 600px
- 中央：约 1800px
- 右侧：约 1300px
- 间距：约 24px × 4

---

# Stage 1：项目脚手架 + 主界面静态视觉骨架

完成后停下来等我确认。

## 1.1 创建文件

`index.html`、`styles.css`、`app.js` 三个文件。

`index.html` 引入 Lucide CDN。`styles.css` 顶部建立第 4 节的所有 CSS 变量。

## 1.2 主背景

- 背景色：`#1A2840`
- 可加非常微弱的网格线或粒子（透明度 < 5%），但不要喧宾夺主
- **禁止任何渐变背景或装饰性光球**

## 1.3 顶部状态栏（高 56px）

**左**（左对齐）：
- `ACTIVE CABIN OS`（text-h2，weight 300）
- 紧跟一个状态徽章 `PROACTIVE SERVICE`（紫蓝色描边胶囊）

**中**（居中）：5 个状态徽章水平排列，间距 12px：
- `Edge Online`（前面绿色 success 圆点）
- `Cloud Connected`（前面绿色圆点）
- `Doubao Model Ready`（前面绿色圆点）
- `CARLA Linked`（前面 cyan 圆点）
- `Voice Idle`（前面灰色圆点）

**右**（右对齐）：
- 当前时间 `09:42` (text-mono)
- `AutoPilot` 徽章（绿色描边）
- 目的地 `→ City Center`
- 网络延迟 `42ms`（小字、tertiary）

## 1.4 左侧状态区（两张卡片纵向排列）

### 车辆状态卡

```
┌─────────────────────────────┐
│ VEHICLE                [⋮⋮] │
│                              │
│                              │
│      42                      │  ← text-hero 缩小到 96px，weight 200
│      km/h                    │  ← text-caption，secondary
│                              │
│                              │
│      Lane 2 · Cruising       │  ← text-body
│      → City Center           │  ← text-body
│      8.4 km · ● Low risk     │  ← text-caption + 绿点
└─────────────────────────────┘
```

### 座舱状态卡

```
┌─────────────────────────────┐
│ CABIN                  [⋮⋮] │
│                              │
│      26°C                    │  ← 大数字
│      AC On · Fan 2           │
│                              │
│      Window         Closed   │
│      Light          ● Blue   │  ← 圆点用对应颜色
│      Music          Off      │
│      Mode           Commute  │
└─────────────────────────────┘
```

### 快捷控制（在两张卡片下方）

- 温度 `−` / `+` 圆形 outline 按钮
- 4 个氛围灯色卡（蓝/紫/绿/橙）的小色块，圆形
- 4 个模式胶囊：`COMMUTE` / `FOCUS` / `RELAX` / `REST`（当前激活的有 cyan 描边）

## 1.5 中央舱驾一体可视化区

用 SVG 实现一个 2.5D 透视的道路场景：

- 三车道路面（中央透视消失点在远处）
- 自车在中间车道（紫蓝发光描边的车形图标，从下往上看有透视）
- 车道虚线（白色虚线，可后续加滚动动画）
- 2-3 辆灰色周车散布在前方
- 一条紫蓝色发光的路线箭头延伸向远方
- 顶部右上角贴一个小字标 `UNITY WEBGL SLOT`（透明度 30%，small label，dashed 边框框起来一小块区域）

底部贴一个胶囊形状的驾驶意图解释条（**这里可以用极轻微的玻璃感**，但不要做强磨砂）：

```
驾驶意图：巡航跟车 · Cruising
```

## 1.6 右侧 AI 服务区 ⭐

**这是整个界面的视觉重心，请重点投入。**

### 顶部：AI 助手液态玻璃球

- 200×200px 的液态玻璃球（严格按 5.3 节规范实现）
- 球居中放置
- 球下方文字：`AI ASSISTANT · IDLE`（text-label，UPPERCASE，tracking 0.05em，secondary 色）

### 中部：对话气泡区

两条 mock 对话：
- 用户气泡（右对齐，深一点的实色 `#243450`，圆角矩形带左下角小尖）：
  ```
  我有点热，帮我舒服一点
  ```
- AI 气泡（左对齐，稍亮一点的实色 `#2D3F5C`，圆角矩形带右下角小尖）：
  ```
  我已为你降低空调温度并开启座椅通风，
  同时将氛围灯调整为冷色
  ```

### 下部：意图理解面板（小卡片）

```
INTENT          Thermal Comfort
CONFIDENCE      ████████░░  94%
SLOTS           hot · comfort · cabin
```

- 字段名（左列）：text-label，UPPERCASE，tertiary
- 字段值（右列）：text-body，primary
- Confidence 用 8 个 cyan 实心方块 + 2 个空心方块表示进度

## 1.7 底部 11 功能 Dock（高 80px）

11 个胶囊按钮水平排列，平均分布。每个按钮：

```
┌──────────────────┐
│   [icon]         │  ← Lucide 图标，24px，cyan 色
│   语音对话        │  ← text-body，primary
│   VOICE          │  ← text-mono，secondary，小字
└──────────────────┘
```

每个按钮：
- 圆角 16px（不是完全胶囊）
- 高 64px
- 默认：实色 `#1F2D45` + 1px subtle 描边
- hover：背景 `#243450`
- active：cyan 描边 + 0 0 16px cyan glow

11 个按钮内容（按顺序）：

| # | 图标（Lucide） | 中文名 | 英文副标 |
|---|---|---|---|
| 1 | mic | 语音对话 | VOICE |
| 2 | brain | 意图理解 | INTENT |
| 3 | sparkles | 主动服务 | PROACTIVE |
| 4 | activity | 多模态感知 | MULTIMODAL |
| 5 | car | 舱驾联动 | CABIN-DRIVE |
| 6 | cloud | 端云协同 | EDGE-CLOUD |
| 7 | message-square-quote | 可解释反馈 | EXPLAIN |
| 8 | sliders-horizontal | 座舱控制 | COCKPIT |
| 9 | navigation | 驾驶控制 | DRIVING |
| 10 | concierge-bell | 生活服务 | SERVICE |
| 11 | book-open | 语义知识 | KNOWLEDGE |

## 1.8 Stage 1 验收标准

- [x] 3840 × 590 下完美呈现，无溢出无错位
- [x] 整体视觉风格符合 OVEA：深海军 + 极细字体 + 大留白 + 实色卡片
- [x] AI 球做到了液态玻璃质感（紫蓝辉光、玻璃边缘高光、内部呼吸）
- [x] 卡片是实色 `#1F2D45`，**没有任何 backdrop-filter**
- [x] 所有大数字字重 200-300（细体）
- [x] 全大写标签有 letter-spacing
- [x] 11 个 Dock 按钮全部存在
- [x] 没有纵向滚动条

**完成 Stage 1 后停下来，告诉我："Stage 1 完成，请查看效果。视觉骨架是否符合 OVEA 风格？"**

---

# Stage 2：AI 球 6 种状态动画

让 AI 助手球支持 6 种状态切换：

```
Idle / Listening / Understanding / Planning / Executing / Completed
```

每种状态对应不同动画：

### Idle（默认）
- 内部呼吸核心持续呼吸（已在 Stage 1 实现）
- 外发光保持稳定

### Listening
- 球面发出多层同心圆音波，从球心向外扩散，逐渐淡出
- 间隔 800ms 一波
- 颜色用 `--accent-primary`，透明度递减

### Understanding
- 球体表面有水平扫描线从上向下掠过（每 1.2s 一次）
- 同时在球周围浮现 1-2 个关键词文字（如 "thermal" / "comfort"），淡入后向上飘动淡出

### Planning
- 球内部出现 4-6 个小光点，光点之间用细线连接
- 光点和连线脉动闪烁，模拟"AI 正在思考"

### Executing
- 球表面持续发射粒子（每 200ms 一个），粒子向左侧飞出（飞向左侧状态卡的方向）
- 粒子是 4×4px 的 cyan 小光点，带轨迹拖尾

### Completed
- 整个球短暂闪烁金绿色（`--success`）外发光
- 持续 600ms 后回到 Idle 状态
- 中央出现一个细描边的 ✓ 图标（Lucide check），淡入淡出

### 实现要求

1. 提供一个 JS 函数：`setAiStatus(status)`，可切换状态
2. 在页面右下角加一个**测试面板**（小玻璃浮层），有 6 个按钮可手动切换状态测试效果
3. 状态切换之间要平滑过渡，不要闪切

**完成 Stage 2 后停下来，告诉我："Stage 2 完成，AI 球 6 种状态已实现。"**

---

# Stage 3：启动动画

页面打开后先播放 4-6 秒的启动序列，再淡出进入 Stage 1 的主界面。

## 3.1 启动动画四阶段

### 阶段 1：黑场唤醒（0-1s）

- 全屏深黑 `#0A1628`
- 一条细横线从屏幕中央向左右两侧扩展
- 中央浮现文字（淡入）：
  ```
  ACTIVE CABIN OS
  舱驾一体主动服务系统
  ```
- 字重 200，字号 display

### 阶段 2：模块自检（1-3s）

文字下方左右两栏滚动出现 8 个自检项，每项格式：

```
[●] Vehicle State Sync         Checking → Ready
[●] Cabin Service Runtime      Checking → Ready
[●] CARLA Driving Link         Checking → Ready
[●] Multimodal Perception      Checking → Ready
[●] Volcengine Cloud Model     Checking → Ready
[●] Intent Understanding       Checking → Ready
[●] Service Executor           Checking → Ready
[●] HMI Feedback Layer         Checking → Ready
```

- 每项间隔 200ms 出现
- 状态从 `Checking`（黄色文字）变为 `Ready`（绿色文字），同时左侧圆点从黄变绿
- 用 mono 字体

### 阶段 3：端云协同连线（3-4.5s）

清空自检列表，中央出现三个实色圆形节点，水平排列：

```
   [Edge]  ──── [Cloud]  ──── [Vehicle]
```

- 每个节点直径 80px，深色填充，带紫蓝描边和小图标
- 三个节点之间有连线
- 连线上有紫蓝色光粒子，从 Vehicle → Edge → Cloud → Edge → Vehicle 来回流动
- 节点下方文字标签：`EDGE` / `CLOUD` / `VEHICLE`

### 阶段 4：进入主界面（4.5-6s）

- 启动层整体缩小、淡出
- 主 HMI 三栏从下方液态浮入（`translateY(40px) opacity(0)` → 实位）
- 各部分错峰浮入，间隔 100ms

## 3.2 Skip 按钮

- 右上角放一个 outline 胶囊 `Skip`
- 点击立即跳过启动动画进入主界面

## 3.3 实现

把启动动画封装成 `playStartupAnimation()` 函数，在页面加载时自动调用。

**完成 Stage 3 后停下来，告诉我："Stage 3 完成，启动动画已实现。"**

---

# Stage 4：11 个 Dock 点击交互 + 全局状态机

## 4.1 全局状态对象

在 `app.js` 顶部定义：

```js
const state = {
  system: {
    edge: "online",
    cloud: "connected",
    carla: "linked",
    voice: "idle",
    latency: 42,
    mode: "Proactive Service"
  },
  vehicle: {
    speed: 42,
    lane: 2,
    autopilot: true,
    action: "Cruising",
    destination: "City Center",
    distance: 8.4,
    risk: "Low"
  },
  cabin: {
    acOn: true,
    temperature: 26,
    fan: 2,
    window: "Closed",
    seatVentilation: false,
    seatHeating: false,
    ambientLight: "Blue",
    music: "Off",
    mode: "Commute"
  },
  user: {
    emotion: "Neutral",
    fatigue: "Low",
    thermal: "Comfortable",
    attention: "Normal"
  },
  ai: {
    status: "Idle",
    transcript: "",
    reply: "",
    intent: "",
    confidence: 0,
    slots: [],
    plan: [],
    explanation: "",
    activeCard: null
  }
};
```

## 4.2 全局函数

```js
playStartupAnimation()                   // 已在 Stage 3 实现
setAiStatus(status)                      // 已在 Stage 2 实现
runScenario(scenarioName)                // Stage 5 实现：'A' | 'B' | 'C' | 'D' | 'E'
updateVehicle(partial)                   // 部分更新车辆状态，触发 UI 更新
updateCabin(partial)                     // 部分更新座舱状态
updateUserState(partial)                 // 部分更新用户多模态状态
showIntent(intent, confidence, slots)    // 更新意图理解面板
showPlan(steps)                          // 步骤逐条出现，每条间隔 300ms
showExplanation(text)                    // 显示"为什么这样做"解释面板
showServiceCard(type, payload)           // Stage 6 实现：服务卡片
simulateVoiceInput(text)                 // 模拟语音输入
simulateDrivingAction(action)            // 触发中央 ADS 动作动画
resetDemo()                              // 重置所有状态到默认
```

每个函数更新 `state` 后，对应 UI 区域自动重渲染（手动 DOM 操作即可，不用框架）。

更新数值时要有动画效果：
- 数字变化用 odometer 风格滚动
- 状态变化时对应字段短暂高亮（cyan 边框闪一下）

## 4.3 11 个 Dock 点击行为

### Dock 1：语音对话

```js
async function handleVoice() {
  setAiStatus('Listening');
  await sleep(800);
  // 在对话区显示用户气泡
  addUserBubble("我有点热，帮我舒服一点");
  await sleep(1500);
  setAiStatus('Understanding');
  showIntent('Thermal Comfort', 94, ['hot', 'comfort', 'cabin temperature']);
  await sleep(1500);
  setAiStatus('Planning');
  showPlan([
    'Lower AC temperature to 22°C',
    'Enable seat ventilation',
    'Change ambient light to cool blue'
  ]);
  await sleep(2000);
  setAiStatus('Executing');
  updateCabin({ temperature: 22, seatVentilation: true, ambientLight: 'Cool' });
  await sleep(1500);
  setAiStatus('Completed');
  addAiBubble("我已为你开启舒适降温模式");
  await sleep(800);
  setAiStatus('Idle');
}
```

### Dock 2：意图理解

- 在右侧显示一个对照面板：
  - 左：用户原话 "好热啊"
  - 中：箭头
  - 右：识别意图 `Thermal Discomfort`
- 下方展示映射规则：`模糊表达 → 热舒适需求 → 空调 / 座椅 / 车窗策略`

### Dock 3：主动服务

- 不需要用户输入
- 直接弹出主动服务建议浮层：`检测到车内温度偏高，是否为你开启舒适降温模式？`
- 浮层中显示 3 个服务卡片预览：降低空调 / 开启座椅通风 / 推荐冷饮
- 浮层右下角有 `接受` / `稍后` 两个按钮

### Dock 4：多模态感知

- 用户状态面板（在右侧某处）从默认值切换为：
  - `Emotion: Low`（黄色）
  - `Fatigue: Medium`（橙色）
  - `Thermal: Hot`（红色）
  - `Attention: Normal`（绿色）
- 出现解释文字：`视觉与座舱状态共同判断用户可能处于疲劳和热不适状态`

### Dock 5：舱驾联动

- 中央 ADS 区显示 `Congestion Ahead` 标签 + 周围车辆密集起来
- AI 自动回复：`前方拥堵，预计等待 12 分钟。已为你切换 Relax 模式并推荐播客`
- 座舱模式更新：`Mode: Commute → Relax`，音乐：`Off → Podcast`

### Dock 6：端云协同

- 触发一个全屏覆盖的端云协同可视化（半透明深色背景）
- 显示数据流路径：
  ```
  Cabin State → Edge Runtime → Volcengine Cloud → Service Plan → HMI + Executor
  ```
- 每个节点的分工说明左右两栏并列：
  - 端侧：状态、执行、安全、HMI
  - 云端：对话、推理、复杂服务编排
- 紫蓝光粒子沿路径流动
- 点击空白处或 ESC 关闭

### Dock 7：可解释反馈

- 在右侧弹出"为什么这样做"解释面板：
  ```
  EXPLANATION
  
  用户表达热感，车内温度为 29°C，
  当前空调为 26°C。
  
  系统选择先降低空调并开启座椅通风，
  而不是直接打开车窗，因为：
  • 高速行驶时开窗会增加风噪
  • 当前外部空气质量为良
  • 用户偏好低风噪环境
  ```

### Dock 8：座舱控制

- 高亮左侧座舱控制面板（描边 cyan 闪烁 2s）
- 自动执行 `Comfort Cooling Mode` 组合动作：
  - 温度 26°C → 22°C（数字滚动）
  - 座椅通风 Off → On
  - 氛围灯 Blue → Cool
  - 音乐 Off → Soft
- 每个变化间隔 400ms，依次高亮

### Dock 9：驾驶控制

- 模拟语音输入：`帮我换到左车道`
- 中央 ADS 区执行左变道动画（自车从 Lane 2 平滑滑向 Lane 1，0.8s）
- 车辆状态卡更新：`Lane 2 → Lane 1`
- AI 回复：`正在确认左侧安全距离，并执行左变道`
- 驾驶意图条更新：`检测左侧安全距离后执行变道`

### Dock 10：生活服务

- 弹出服务卡片面板（5 张卡片网格）：奶茶 / 航班 / 新闻 / 视频 / 服务区
- 默认显示奶茶卡：
  ```
  推荐饮品：少冰三分糖拿铁奶茶
  店名：星茶坊（前方 2.1km）
  预计到店：8 分钟后
  [加入行程] [到店提醒]
  ```

### Dock 11：语义知识

- 弹出知识依据面板：
  ```
  KNOWLEDGE BASE
  
  规则库：
  • 热感表达 → 优先降温与座椅通风
  • 疲劳状态 → 提醒休息并降低信息密度
  • 赶时间 → 优先路线与目的地服务
  
  用户偏好：
  • 常用温度 22°C
  • 喜欢冷色氛围灯
  • 通勤时偏好播客
  • 不喜欢高速开窗（风噪敏感）
  ```

## 4.4 通用规则

- 每次点击 Dock 后，对应 Dock 项变为激活态（cyan 描边）
- 5 秒无操作后自动回到 Idle 状态
- 提供一个 `resetDemo()` 函数，重置所有状态

**完成 Stage 4 后停下来，告诉我："Stage 4 完成，11 个 Dock 已可点击交互。"**

---

# Stage 5：5 个 Demo 场景一键播放

## 5.1 Demo Scenarios 入口

页面右上角加一个 outline 胶囊按钮 `DEMO SCENARIOS`，点击展开浮层显示 5 个场景按钮。

## 5.2 Demo A：热舒适服务

触发文本：`我有点热，帮我舒服一点`

完整流程（约 12 秒）：

1. AI 状态 → Listening（800ms）
2. 显示用户气泡 + 语音识别文本
3. AI 状态 → Understanding（1.5s）
4. 意图识别面板：`Thermal Discomfort` 94%
5. AI 状态 → Planning
6. 任务拆解逐条出现：
   - Lower AC temperature to 22°C
   - Enable seat ventilation
   - Change ambient light to cool blue
   - Ask whether user wants a cold drink
7. AI 状态 → Executing
8. 左侧座舱状态依次更新（温度 26→22 滚动、座椅通风 Off→On、灯 Blue→Cool）
9. 服务卡片"舒适降温"显示完成
10. AI 状态 → Completed
11. AI 气泡：`我已为你开启舒适降温模式，空调调整到 22°C，并开启座椅通风`
12. AI 状态 → Idle

## 5.3 Demo B：情绪陪伴服务

触发文本：`今天有点烦，也有点累`

完整流程：

1. 意图识别：`Emotional Support`
2. 多模态状态变化：`Emotion: Low`、`Fatigue: Medium`
3. 座舱模式切换：`Commute → Relax`
4. 氛围灯：`Blue → Warm`
5. 音乐：`Off → Soft Music`
6. AI 回复：`我帮你把座舱切换到放松模式，播放一段舒缓音乐。现在不用急，我们慢慢来`

## 5.4 Demo C：赶飞机服务

触发文本：`我快赶不上飞机了，帮我规划最快路线`

完整流程：

1. 意图识别：`Travel Urgency`
2. 目的地更新：`City Center → Airport T2`
3. 中央 ADS 区动作：`Cruising → Rerouting`（路线箭头擦除重画）
4. 弹出 3 张服务卡片（从右侧滑入）：
   - 航班信息卡
   - 最快路线卡
   - 停车建议卡
5. AI 回复：`已为你切换至机场 T2 的最快路线，并整理航班和到达提醒`

## 5.5 Demo D：CARLA 语音驾驶控制

触发文本：`帮我换到左车道`

完整流程：

1. 意图识别：`Driving Command`
2. 中央 ADS 区执行左变道动画（自车从 Lane 2 → Lane 1）
3. 车辆状态卡更新：`Lane 2 → Lane 1`
4. 驾驶意图条更新：`检测左侧安全距离后执行变道`
5. AI 回复：`正在完成左变道，已保持安全车距`

## 5.6 Demo E：无语音主动服务

**触发条件**：无需用户输入，直接触发

完整流程：

1. 多模态状态面板主动变化：`Fatigue: Low → High`（红色高亮）
2. AI 状态：Understanding（自主理解）
3. 主动弹窗：`检测到你可能有些疲劳，是否为你降低屏幕亮度并推荐最近服务区？`
4. 三张服务卡片滑入：
   - 降低屏幕亮度
   - 播放提醒音
   - 推荐服务区（前方 5km）
5. AI 状态 → Idle

## 5.7 实现要求

- 把每个 Demo 写成 async 函数：`runDemoA()` / `runDemoB()` / ...
- 用 `await sleep(ms)` 编排时序
- 每个 Demo 完成后自动 `resetDemo()` 回到默认状态

**完成 Stage 5 后停下来，告诉我："Stage 5 完成，5 个 Demo 可一键播放。"**

---

# Stage 6：服务卡片 + 文本输入 + 关键词触发

## 6.1 5 种服务卡片（实色卡，从右侧滑入动画）

### 奶茶卡

```
┌─────────────────────────────┐
│ MILK TEA              [⋮⋮]  │
│                              │
│  星茶坊（商圈店）             │
│  少冰三分糖拿铁奶茶            │
│                              │
│  距离      2.1 km             │
│  预计到店   8 min               │
│  价格      ¥28                │
│                              │
│  [ 加入行程 ]  [ 到店提醒 ]   │
└─────────────────────────────┘
```

### 航班卡

```
┌─────────────────────────────┐
│ FLIGHT                [⋮⋮]  │
│                              │
│  CA1234                       │
│  PEK T3 → SHA T2              │
│                              │
│  起飞      14:30              │
│  登机      13:50              │
│  到达机场   13:15（最快路线）   │
│  ● 路线状态   畅通             │
│                              │
│  [ 导航前往 ]  [ 出发提醒 ]   │
└─────────────────────────────┘
```

### 新闻卡

```
┌─────────────────────────────┐
│ NEWS BRIEF            [⋮⋮]  │
│                              │
│  今日摘要                      │
│                              │
│  • 科技：AI 大模型新突破       │
│  • 财经：市场震荡走高           │
│  • 体育：欧冠决赛今晚开打        │
│                              │
│  [ 语音播报 ]                  │
└─────────────────────────────┘
```

### 视频卡

```
┌─────────────────────────────┐
│ VIDEO                 [⋮⋮]  │
│                              │
│  推荐：科技日报 · 第 42 期      │
│  时长       12 min             │
│                              │
│  ⚠ 行车中不建议观看            │
│                              │
│  [ 停车后观看 ]                │
└─────────────────────────────┘
```

### 服务区卡

```
┌─────────────────────────────┐
│ REST AREA             [⋮⋮]  │
│                              │
│  阳光服务区                    │
│  距离       5.2 km             │
│  预计到达    6 min              │
│  推荐原因    检测到驾驶疲劳      │
│                              │
│  [ 设为下一站 ]                │
└─────────────────────────────┘
```

## 6.2 文本输入框

页面底部 Dock 上方放一个 outline 胶囊形输入框，宽 600px，左侧有 Lucide `mic` 图标。

```html
<div class="text-input-bar">
  <i data-lucide="mic"></i>
  <input type="text" placeholder="说点什么或输入文字..." />
  <button class="btn-ghost-sm">SEND</button>
</div>
```

## 6.3 关键词触发

输入框支持以下关键词：

| 关键词 | 触发 |
|---|---|
| 包含"热" | Demo A（热舒适） |
| 包含"烦" / "难过" / "累" | Demo B（情绪陪伴） |
| 包含"机场" / "飞机" / "赶不上" | Demo C（赶飞机） |
| 包含"换道" / "左车道" / "右车道" | Demo D（驾驶控制） |
| 包含"奶茶" | 显示奶茶卡 |
| 包含"疲劳" / "困" | Demo E（主动疲劳） |
| 包含"新闻" | 显示新闻卡 |
| 其他 | AI 默认回复 `好的，我来想想怎么帮你` |

## 6.4 实现要求

```js
function handleTextInput(text) {
  if (text.includes('热')) runScenario('A');
  else if (text.match(/烦|难过|累/)) runScenario('B');
  else if (text.match(/机场|飞机|赶不上/)) runScenario('C');
  else if (text.match(/换道|左车道|右车道/)) runScenario('D');
  else if (text.includes('奶茶')) showServiceCard('milktea');
  else if (text.match(/疲劳|困/)) runScenario('E');
  else if (text.includes('新闻')) showServiceCard('news');
  else defaultResponse(text);
}
```

**完成 Stage 6 后告诉我：项目已完成，可以演示。**

---

# 最终验收清单

- [ ] 打开 HTML 立刻进入启动动画，4-6 秒后进入主界面
- [ ] 在 3840×590 下完美呈现，无溢出无错位
- [ ] 整体视觉风格符合 OVEA：深海军 + 极细字体 + 大留白 + 实色卡片
- [ ] AI 助手球做到了惊艳的液态玻璃质感
- [ ] **AI 球是唯一使用 backdrop-filter 的元素**，其他卡片都是实色
- [ ] 顶部状态栏 / 左侧状态卡 / 中央 ADS / 右侧 AI 区 / 底部 11 Dock 全部存在
- [ ] AI 球 6 种状态动画都实现并平滑切换
- [ ] 11 个 Dock 全部可点击且每个有明确 UI 反馈
- [ ] 5 个 Demo Scenario 可一键完整播放
- [ ] 5 种服务卡片都可显示
- [ ] 文本输入框支持关键词触发
- [ ] 完全本地运行，不依赖任何外部 API
- [ ] 无纵向滚动条
- [ ] 所有大数字字重 200-300（细体）
- [ ] 没有任何手机 App 风格的彩色填充按钮
- [ ] 没有任何整屏液态玻璃磨砂

---

# 重要提醒

请你**严格按 Stage 1 → 6 的顺序实现**，每完成一个 Stage 停下来等我确认。

如果对任何视觉细节或交互逻辑有疑问，请先问我，**不要自己脑补**。

特别强调三件事：

1. **OVEA 视觉骨架是底色，液态玻璃只在 AI 球上用**——千万不要把卡片做成磨砂玻璃
2. **大数字必须用细体（weight 200-300）**——粗体会立刻破坏未来感
3. **AI 球是视觉灵魂**——请重点投入精力做好这个组件，包括玻璃质感、辉光、6 种状态动画

开始 Stage 1。
