# Smart Cockpit 项目交接文档

> 面向舱驾一体场景的端云协同多模态智能座舱主动服务系统
> 
> 最后更新：2026-05-05

---

## 一、项目概述

本项目是毕业设计，实现一套 **3840×590 超宽屏** 车载智能座舱 HMI 系统，包含：

- **前端 HMI**：纯 HTML/CSS/JS 实现的车载界面（无框架依赖）
- **边缘端服务**：FastAPI 后端 + CARLA 仿真桥接
- **云端 AI**：火山引擎豆包大模型（对话 + 视觉）+ ASR/TTS 语音链路
- **3D 场景**：Unity WebGL 车辆展示（独立构建，通过 JS Bridge 通信）

---

## 二、技术栈

| 层级 | 技术 |
|------|------|
| 前端 | HTML5 + CSS3 + Vanilla JS（无框架） |
| 字体 | Mercedes-Benz MB Corpo 家族 |
| 后端 | Python 3.10+ / FastAPI / Uvicorn |
| 仿真 | CARLA 0.9.x（可选） |
| AI 对话 | 火山方舟 - 豆包大模型 |
| 语音识别 | 火山引擎 ASR（WebSocket 流式） |
| 语音合成 | 火山引擎 TTS（WebSocket 流式） |
| 3D 引擎 | Unity 2022 → WebGL Build |
| 通信 | WebSocket（前端↔后端），TCP（保留 Unity 原生客户端兼容） |

---

## 三、目录结构

```
smart_cockpit/
├── main.py                     # 主入口（所有模式统一入口）
├── config/
│   └── settings.py             # 全局配置（环境变量从 .env 加载）
│
├── edge/                       # 边缘端
│   ├── carla/
│   │   └── bridge.py           # CARLA 仿真桥接
│   ├── hmi_server/
│   │   └── server.py           # FastAPI 服务端（静态文件 + WebSocket）
│   └── state/
│       ├── vehicle_state.py    # 车辆状态管理
│       ├── cabin_state.py      # 座舱状态管理
│       └── service_executor.py # 服务执行器
│
├── cloud/                      # 云端
│   ├── agent/
│   │   ├── assistant_manager.py # AI 助手管理
│   │   └── service_agent.py    # 服务决策 Agent
│   ├── chat/
│   │   └── doubao_chat.py      # 豆包对话接口
│   ├── vision/
│   │   └── doubao_vision.py    # 豆包视觉接口
│   └── voice/
│       ├── microphone_asr.py   # 麦克风录音 + ASR
│       └── speaker_tts.py      # TTS 播放
│
├── communication/
│   ├── protocol.py             # JSON 通信协议定义
│   └── tcp_server.py           # TCP 服务端（Unity 原生客户端用）
│
├── hmi/                        # 前端资源
│   └── static/
│       ├── index.html          # 主页面
│       ├── styles.css          # 完整样式（~600行）
│       ├── app.js              # 完整逻辑（~610行）
│       ├── fonts/              # MB Corpo 字体文件
│       ├── media/              # 音频、封面、海报、截图
│       ├── wallpaper/          # 锁屏壁纸
│       ├── videos/             # 背景视频 HMI.mp4 + 音效（.gitignore）
│       └── unity/              # Unity WebGL Build（.gitignore）
│
└── handoff/                    # 交接文档
```

---

## 四、启动方式

```bash
# 环境准备
pip install fastapi uvicorn python-dotenv volcengine-python-sdk

# 仅 HMI 前端开发模式（不需要 CARLA / AI）
python main.py --hmi-only

# 完整模式：CARLA + Web HMI + AI
python main.py --web-hmi

# Mock 数据 + Web HMI + AI（无需 CARLA 连接）
python main.py --web-hmi --mock-carla

# 无 AI 模式
python main.py --web-hmi --no-ai
```

启动后访问 `http://localhost:8080`

### 环境变量（.env 文件）

```env
ARK_API_KEY=your_volcengine_ark_key
ARK_ENDPOINT_ID=your_endpoint_id
ASR_APP_KEY=your_asr_app_key
ASR_ACCESS_KEY=your_asr_access_key
TTS_APP_ID=your_tts_app_id
TTS_ACCESS_TOKEN=your_tts_access_token
```

---

## 五、HMI 前端架构

### 5.1 画布缩放

固定 3840×590 画布，通过 CSS `transform: scale()` 自适应视口：

```
scaleX = window.innerWidth / 3840
scaleY = window.innerHeight / 590
scale = min(scaleX, scaleY)
```

### 5.2 Z-Index 层级

| Z-Index | 层 | 说明 |
|---------|-----|------|
| 0 | 背景视频 | HMI.mp4 循环播放 |
| 50 | Unity 覆盖层 | 默认不可交互 |
| 150 | Unity（激活） | 激活时提升到 HMI 之下 |
| 200 | HMI 主层 | 三区布局（pointer-events: none 容器） |
| 300 | Dock | 始终可见可交互 |
| 500 | 锁屏 | 最顶层 |

### 5.3 三区布局

- **左区（ADAS）**：2D Canvas 鸟瞰车道可视化 + 速度卡片
- **中区（导航）**：2D Canvas 路线可视化 + 目的地信息
- **右区（娱乐）**：动态卡片系统

每区固定 `width: calc(100%/3 - 8px)`，通过 Dock 按钮独立显示/隐藏。

### 5.4 右区动态卡片系统

核心机制：**4 槽位管理器**

```
MAX_SLOTS = 4
每张卡片占 1 或 2 个槽位
新卡片从左侧插入，超出 4 槽时从右侧挤出最旧的卡片
```

**卡片类型：**

| ID | 槽位 | 说明 |
|----|------|------|
| music | 1 | 音乐播放器（封面 + 控制） |
| bilibili | 2 | B站推荐（横滑海报） |
| combo | 2 | 音乐+B站合体（上下排布） |
| alipay | 1 | 支付宝截图（不拉伸） |
| ctrip | 1 | 携程截图（不拉伸） |
| news | 1 | 新闻截图（不拉伸） |
| parking | 1 | 停车场 UI（生成式） |
| charging | 1 | 充电站 UI（生成式） |

**Music + Bilibili 联动逻辑：**
- 都开启 → 合并为 combo（2 槽，上下排布）
- 只开 music → 独立 1 槽
- 只开 bilibili → 独立 2 槽

**动画流程（关闭卡片）：**
1. 添加 `.leaving` → 下滑 + 淡出（0.35s）
2. 350ms 后添加 `.collapsing` → 宽度收缩到 0（0.4s）
3. 750ms 后从 DOM 移除

### 5.5 锁屏

- 30 秒无操作自动显示
- 点击任意位置解锁（slide up 动画）
- 显示时间、日期、天气

### 5.6 Dock 按钮

从左到右：导航 | ADAS | AI语音 | 服务面板 | 座舱(娱乐区) | 3D

### 5.7 Service 面板

点击 Dock 服务按钮弹出九宫格应用面板，包含：
Alipay / Ctrip / Music / Bilibili / Parking / Charging / News

点击应用图标 → 在右区创建/关闭对应卡片。

---

## 六、Unity WebGL 集成

### 构建文件

```
hmi/static/unity/ai-car-scene/Build/
├── AI4HMI.loader.js
├── AI4HMI.data.gz
├── AI4HMI.framework.js.gz
└── AI4HMI.wasm.gz
```

### 通信协议

前端 → Unity：
```javascript
window.HMI.switchCamera('astronaut')
window.HMI.openPart('door_fl')
window.HMI.rotateCarTo(90)
```

Unity → 前端：
```javascript
window.OnUnityEvent(jsonStr)
// { eventType: 'cameraTransitionEnd', target: 'astronaut' }
```

### 音效

- 切换到 astronaut 视角 → 播放 Hello.mp3
- 离开 astronaut 视角 → 播放 Bye.mp3

---

## 七、后端 API

### REST

| 路径 | 说明 |
|------|------|
| `GET /` | 返回 index.html |
| `GET /static/*` | 静态资源 |
| `GET /static/unity/*` | Unity .gz 文件（自动 Content-Encoding: gzip） |

### WebSocket `/ws`

**服务端推送：**
```json
{
  "type": "state_update",
  "vehicle": { "speed_kmh": 89, "steer": 0.1, ... },
  "cabin": { ... }
}
```

```json
{
  "type": "ai_reply",
  "user": "用户输入",
  "reply": "AI 回复"
}
```

**客户端发送：**
```json
{ "type": "user_input", "text": "导航到最近的充电站" }
{ "type": "cabin_control", "action": "set_temperature", "params": { "value": 24 } }
```

---

## 八、AI 控制协议

AI 可通过 JSON 指令控制前端媒体播放：

```javascript
window.MediaControl.play()
window.MediaControl.pause()
window.MediaControl.next()
window.MediaControl.prev()
window.MediaControl.playTrack(2)  // 播放第3首（晴天）
```

音乐列表：
| Index | Title | Artist |
|-------|-------|--------|
| 0 | Starboy | The Weeknd |
| 1 | How You Like That | BLACKPINK |
| 2 | 晴天 | 周杰伦 |
| 3 | Handlebars | Jennie |
| 4 | Born Again | Lisa |
| 5 | Toxic Till The End | ROSÉ |

---

## 九、设计规范

### 视觉风格

- **背景**：深色 + 视频壁纸
- **卡片**：白色半透明毛玻璃 `rgba(255,255,255,0.10)` + `backdrop-filter: blur(20px)` + 白色边框 `rgba(255,255,255,0.18)`
- **圆角**：小 10px / 中 16px / 大 22px
- **字体**：MB Corpo 家族（奔驰企业字体）
- **强调色**：Cyan `#4DD8E5` / Blue `#5B8DEF` / Green `#4DDB8F`

### 截图类卡片（Alipay/Ctrip/News）

- 不拉伸填满，保持原始比例
- 无磨砂底色，透明背景
- 按内容宽度自适应，不占 flex 空间

---

## 十、本地开发注意事项

### 不纳入 Git 的大文件

- `hmi/static/unity/` — Unity WebGL 构建（~200MB）
- `hmi/static/videos/*.mp4` — 背景视频
- `hmi/static/fonts/` — 字体文件（已 track）

### 代理问题

Git 配置了 HTTP 代理 `127.0.0.1:7897`（Clash），推送前需确保代理软件运行。

### 端口

- HMI 服务：8080
- CARLA：2000
- TCP（Unity 原生）：9000

---

## 十一、待完善 / 可扩展

1. **横版海报**（Devil.jpg, The Queen's Gambit.jpg, Se7en.webp）尚未在 UI 中使用，可作为推荐 Banner
2. **AI 语音对话** Dock 按钮已预留，前端尚未接入 WebSocket ASR/TTS 流式交互
3. **CARLA 实时数据** 在 `--hmi-only` 模式下为 Mock 正弦波，接入 CARLA 后 ADAS 可视化可显示真实感知数据
4. **Unity 3D 场景** 需本地放置 Build 文件才可加载
5. **Service Agent** 云端决策 Agent 已有框架，可根据场景自动推送服务卡片

---

## 十二、快速验证清单

- [ ] `python main.py --hmi-only` 启动无报错
- [ ] 浏览器访问 localhost:8080 看到锁屏
- [ ] 点击解锁进入主界面
- [ ] 右区默认显示 Music+Bilibili combo 卡片
- [ ] 点击 Dock 服务按钮 → 面板弹出
- [ ] 点击 Alipay → 右区出现支付宝截图卡片（不拉伸）
- [ ] 点击 ✕ 关闭卡片 → 下滑动画 + 剩余卡片填满
- [ ] 30秒不操作 → 锁屏自动出现
- [ ] 音乐播放控制正常（播放/暂停/上下曲）
