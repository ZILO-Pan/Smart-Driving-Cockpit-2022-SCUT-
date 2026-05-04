# Claude Code 交接文档：舱驾一体智能座舱 MVP

## 1. 项目目标

仓库：

https://github.com/ZILO-Pan/Smart-Driving-Cockpit-2022-SCUT-

毕业设计主题：

**《面向舱驾一体场景的端云协同多模态智能座舱主动服务系统设计研究》**

当前目标不是先做最终视觉，而是先跑通一个可以演示的 MVP：

- CARLA 负责“驾”：展示自动驾驶仿真画面、车辆状态、天气、路线、场景、风险事件。
- HTML 负责主 HMI：展示 3840 x 590 超宽智能座舱屏幕。
- 火山引擎/豆包负责云端智能：语音、对话、视觉/多模态理解、服务编排。
- 端侧负责执行：CARLA 控制、HMI 渲染、座舱状态、规则、安全确认、模拟服务卡片。
- Unity 不再作为主 HMI 技术栈。Unity 只作为后续可嵌入 HTML 的 WebGL 可视化模块，用于 ADS 可视化、车状态动画、装饰动画或 3D 座舱效果。

## 2. 关键方向纠偏

原方案中有 TCP 到 Unity 的雏形，但现在项目方向已经调整：

### 旧方案

```text
Python/CARLA -> TCP -> Unity 原生客户端 -> Unity 内完成全部 HMI
```

### 新方案

```text
Python/CARLA/FastAPI -> HTTP/WebSocket -> HTML HMI
                                      -> JS Bridge -> Unity WebGL 可视化模块
```

结论：

- TCP 到 Unity 不再是主链路。
- TCP 可以保留为 legacy/native Unity adapter，但第一版 MVP 不依赖它。
- WebGL 运行在浏览器里，不能像原生 Unity 一样稳定使用普通 TCP socket。
- HTML HMI 应通过 REST/WebSocket 连接后端。
- Unity WebGL 嵌入 HTML 后，应通过 JavaScript bridge、`postMessage` 或 Unity WebGL 的 `SendMessage` 接收 HTML 传来的车辆状态。

第一版只需要在 HMI 中预留一个 `Unity WebGL / ADS Visualization Slot`，不要先做 Unity WebGL 实装。

## 3. 双屏演示模式

用户的硬件场景：

- 同一台电脑接两个显示屏。
- 屏幕 1：显示 CARLA 驾驶仿真画面。
- 屏幕 2：显示 HTML 智能座舱 HMI。
- HMI 屏幕规格为 **3840 x 590** 横向超宽屏。

必须支持 CARLA 和 HMI 并行运行。

推荐运行方式：

```text
显示器 1：CARLA / pygame preview / Unreal 仿真窗口
显示器 2：Chrome/Edge 打开 http://localhost:8080，全屏显示 HMI
```

后端启动方式应支持：

```bash
python main.py --web-hmi
python main.py --web-hmi --no-ai
python main.py --web-hmi --mock-carla
python main.py --hmi-only
```

实现要求：

- `main.py --web-hmi` 启动 Web HMI 服务后，再进入 CARLA 主循环，或者把 CARLA/Web 服务分别放在线程里。
- HMI 服务不能被 CARLA 主循环阻塞。
- 如果 CARLA 没启动，HMI 也要能用 mock 数据启动。
- Demo 时，CARLA 和 HMI 可以各自在不同屏幕中展示。

## 4. 当前仓库理解

已读到的现有结构：

- `main.py`
  - 启动 `VehicleStateManager`、`CarlaBridge`、`TCPServer`、`AssistantManager`、`UnityDataProvider`。
  - 目前主循环进入 `carla_bridge.run()`，这是阻塞式。

- `config/settings.py`
  - 包含 CARLA、TCP、火山方舟、ASR、TTS、麦克风和视觉配置。
  - 当前硬编码了 API 密钥，必须迁移到 `.env`。

- `core/carla_bridge.py`
  - 连接 CARLA。
  - 生成 Tesla Model 3、NPC 车辆、行人、摄像头。
  - 支持 1-8 场景切换。
  - 支持 `C` 触发极端交通事件。
  - 更新 `VehicleStateManager`。
  - 提供 `get_latest_frame()` 给视觉分析。

- `core/vehicle_state.py`
  - 定义车辆速度、油门、刹车、方向、位置、旋转、自动驾驶状态。

- `communication/tcp_server.py`
  - 旧的 Unity 原生客户端通信服务器。
  - 可保留，但不作为 HTML HMI 主链路。

- `ai_assistant/assistant_manager.py`
  - 现在是 ASR -> 豆包对话 -> TTS 的级联助手。
  - 也支持 CARLA 截图 -> 豆包视觉分析 -> TTS 播报。

- `ai_assistant/doubao_chat.py`
  - 调火山方舟 `chat/completions`。
  - 支持文本和图片输入。
  - 需要升级为结构化服务编排。

- `ai_assistant/microphone_asr.py`
  - 火山大模型 ASR WebSocket。

- `ai_assistant/speaker_tts.py`
  - 火山 TTS WebSocket + pygame 播放。

## 5. 第一优先级：安全修复

当前 `config/settings.py` 里出现了真实火山引擎密钥。因为仓库是公开的，应假设这些密钥已经泄露。

必须先做：

1. 新建 `.env.example`，只放变量名。
2. `.gitignore` 加入 `.env`。
3. `settings.py` 改为从环境变量读取。
4. 不要在日志里打印密钥。
5. 缺少必需环境变量时给出清晰提示。
6. README 提醒用户去火山控制台轮换密钥。

建议变量：

```env
ARK_API_KEY=
ARK_API_BASE=https://ark.cn-beijing.volces.com/api/v3
ARK_ENDPOINT_ID=

ASR_APP_KEY=
ASR_ACCESS_KEY=
ASR_WS_URL=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel

TTS_APP_ID=
TTS_ACCESS_TOKEN=
TTS_VOICE_TYPE=zh_female_vv_uranus_bigtts
TTS_CLUSTER=volcano_tts
TTS_WS_URL=wss://openspeech.bytedance.com/api/v1/tts/ws_binary

REALTIME_VOICE_APP_ID=
REALTIME_VOICE_APP_KEY=
REALTIME_VOICE_TOKEN=
REALTIME_VOICE_RESOURCE_ID=
```

## 6. 官方参考文档

### 火山引擎 / 豆包

- 智能座舱解决方案  
  https://www.volcengine.com/docs/82379/1263275  
  用于支撑论文方向：意图理解、娱乐、车控、导航、本地生活、Function Calling、座舱服务编排。

- 豆包端到端实时语音大模型  
  https://www.volcengine.com/docs/6561/1594360  
  用作低延迟自然语音趋势参考。它是云端 API/SDK 路线，不是本地下载模型。

- 实时音视频 AI 互动方案  
  https://www.volcengine.com/docs/6348/1350595  
  可参考其中 ASR/LLM/TTS、端到端实时语音、字幕、记忆、打断、情绪、多模态、Function Calling、MCP、RAG、AI 状态等能力。

- 实时音视频 Function Calling  
  https://www.volcengine.com/docs/6348/1554654  
  用于支撑“自然语言转座舱动作”的技术路线。

- 端到端实时语音 RTC 接入  
  https://www.volcengine.com/docs/6348/1902994

### Qwen / 本地模型

- Qwen3.6  
  https://github.com/QwenLM/Qwen3.6  
  https://qwen.ai/blog?id=qwen3.6-35b-a3b

- Qwen2.5-Omni  
  https://github.com/QwenLM/Qwen2.5-Omni

- Qwen3-Omni  
  https://github.com/QwenLM/Qwen3-Omni

本项目四天 MVP 不应把 Qwen 本地部署作为阻塞项。用户电脑为 RTX 4060 Laptop GPU，8GB 显存，64GB 内存。Qwen3-4B/8B GGUF 可以作为可选端侧兜底或论文扩展，不作为第一版主链路。

## 7. 最终系统定位

本系统不是普通车载语音助手，而是：

**面向舱驾一体场景的端云协同多模态主动服务原型系统。**

云端：

- 豆包自然语言理解。
- 复杂意图推理。
- 多模态/图像理解。
- 服务编排。
- ASR/TTS 或未来端到端实时语音。

端侧：

- CARLA 驾驶控制。
- HTML HMI 渲染。
- 车辆与座舱状态管理。
- 用户状态模拟/轻量识别。
- 服务执行。
- 安全确认策略。
- 预留本地 Qwen 兜底。

核心闭环：

```text
多模态输入
-> 用户状态与驾驶场景判断
-> 大模型/Agent 推理
-> 服务编排与动作生成
-> 座舱/驾驶/生活服务执行
-> HMI + 语音反馈
```

## 8. 11 个功能

所有功能都要在 3840 x 590 HMI 中可见。

### 1. 自然语音对话

用户可以自然说话与助手互动。

MVP：

- 保留现有 ASR -> 豆包 -> TTS 链路。
- 增加文本输入，方便调试和答辩。
- 端到端实时语音作为后续增强。

HMI 显示：

- 助手状态：Listening / Thinking / Executing / Speaking。
- 用户文本。
- 助手回复。

### 2. 模糊意图理解

用户不必说精确命令。

示例：

- “好热啊” -> 热舒适服务。
- “有点无聊” -> 娱乐/陪伴服务。
- “我好累” -> 疲劳安全服务。
- “前面太堵了” -> 路线/驾驶策略。

### 3. 主动服务推荐

系统主动提出服务，而不是只被动执行。

示例：

- 调空调。
- 开座椅通风。
- 调氛围灯。
- 播放音乐。
- 推荐服务区。
- 建议改路线。

### 4. 多模态状态感知

MVP 不做复杂真实视觉识别，先用 HMI debug 状态模拟：

- fatigue
- distracted
- sad
- bored
- hot
- busy

同时保留现有 CARLA 摄像头视觉分析。

### 5. 舱驾一体联动

AI 决策要结合驾驶状态：

- 高速 + 疲劳 -> 休息提醒。
- 拥堵 + 赶时间 -> 改路线/服务规划。
- 暴雨 + 高速 -> 安全提醒。

### 6. 端云协同架构

不要强制本地 Qwen 进入 MVP。

MVP 中：

- 云端：豆包推理、语音、多模态。
- 端侧：CARLA、HMI、座舱状态、服务执行、安全策略。

可预留：

- `edge_model_provider.py`
- UI 上显示 “Edge Fallback Reserved”

### 7. HMI 可解释反馈

HMI 必须展示：

- AI 识别了什么意图。
- 当前上下文是什么。
- 为什么推荐这个服务。
- 将执行哪些动作。
- 是否需要用户确认。

这是交互设计项目的重点。

### 8. 模拟座舱控制

MVP 动作：

- `set_ac_temperature`
- `toggle_window`
- `set_seat_ventilation`
- `set_ambient_light`
- `play_music`
- `set_cabin_mode`
- `show_alert`

### 9. CARLA 驾驶任务语音控制

这是“舱驾一体”的关键。

支持命令：

- “切换到自动驾驶”
- “靠边停车”
- “减速一点”
- “换到左车道”
- “换到右车道”
- “去机场”
- “改去最近的服务区”
- “前面太堵了，换条路线”

MVP 方法：

- 在 `CarlaBridge` 或 `core/carla_commands.py` 中实现：
  - `enable_autopilot()`
  - `stop_vehicle()`
  - `slow_down()`
  - `change_lane(direction)`
  - `set_destination(destination_label)`
  - `reroute(reason)`

如果真实 CARLA 路线规划来不及，HMI 可以先模拟目的地/路线状态，同时尽可能执行 CARLA 可行控制。

### 10. 本地生活服务卡片

不接真实 API，不做支付。

支持模拟：

- 订机票
- 点奶茶
- 看新闻
- 刷视频

流程：

```text
用户说需求
-> AI 识别 local_life/news/video
-> HMI 打开对应服务卡片
-> 自动填入模拟数据
-> 用户确认/取消
```

### 11. 轻量语义映射知识库 / RAG

不要做复杂 RAG。

建立：

`ai_assistant/service_knowledge.json`

内容是主动服务语义映射：

```json
{
  "thermal_comfort": {
    "triggers": ["热", "闷", "出汗", "好晒"],
    "actions": ["set_ac_temperature", "set_seat_ventilation", "toggle_window"],
    "confirm": true
  }
}
```

MVP 可以用关键词 + 模糊匹配 + LLM prompt，不需要向量数据库。

## 9. 推荐新增模块

```text
core/cabin_state.py
core/service_executor.py
core/carla_commands.py
ai_assistant/service_agent.py
ai_assistant/service_knowledge.json
web_hmi/server.py
web_hmi/static/index.html
web_hmi/static/styles.css
web_hmi/static/app.js
web_hmi/static/assets/
```

### `core/cabin_state.py`

维护座舱状态：

```python
temperature = 26
ac_enabled = False
window = "closed"
seat_ventilation = 0
ambient_light = "normal"
music = "off"
cabin_mode = "normal"
user_state = "neutral"
active_service = None
```

### `core/service_executor.py`

执行 AI 输出的 actions：

- 更新座舱状态。
- 调用 CARLA 指令。
- 打开服务卡片。
- 推送告警。
- 对风险动作要求确认。

### `ai_assistant/service_agent.py`

服务编排层。

输入：

```json
{
  "user_input": "好热啊",
  "vehicle_state": {},
  "cabin_state": {},
  "vision_state": {},
  "knowledge_matches": []
}
```

输出：

```json
{
  "intent": "thermal_comfort",
  "confidence": 0.92,
  "need_confirm": true,
  "reply": "我感觉你有点热，我可以帮你把空调调低并打开座椅通风。",
  "actions": [
    {"name": "set_ac_temperature", "params": {"temperature": 23}},
    {"name": "set_seat_ventilation", "params": {"level": 2}}
  ],
  "hmi": {
    "card": "comfort",
    "title": "热舒适主动服务",
    "explanation": "根据你的表达和当前座舱状态，建议调节空调和座椅通风。"
  }
}
```

### `web_hmi/server.py`

使用 FastAPI。

接口：

```text
GET  /                         -> HMI 页面
GET  /api/state                -> 车辆 + 座舱 + AI + 服务状态
POST /api/command              -> HMI 文本命令
POST /api/demo-state           -> 设置模拟用户状态
POST /api/action/confirm       -> 确认待执行动作
POST /api/action/cancel        -> 取消待执行动作
POST /api/carla                -> 直接 CARLA demo 指令
WS   /ws                       -> 可选实时推送
```

HMI 即使在 CARLA 未启动时也要可运行。

## 10. HMI 设计要求：3840 x 590

第一屏就是实际 HMI，不要做落地页。

建议布局：

```text
3840 x 590

┌────────────────────────────────────────────────────────────────────────────┐
│ 顶部状态条：时间 | 网络 | 模式 | CARLA 场景 | 风险等级 | 云端/端侧状态        │
├───────────────┬───────────────────────────────┬────────────────────────────┤
│ 左侧车辆仪表   │ 中央导航/ADS/WebGL 预留区       │ 右侧 AI 助手/服务编排区      │
│ 速度/档位/方向 │ 路线/天气/道路状态/Unity slot   │ 对话/意图/动作/确认         │
├───────────────┴───────────────────────────────┴────────────────────────────┤
│ 底部功能 Dock：11 个功能入口 + 当前服务 + 快捷演示按钮                      │
└────────────────────────────────────────────────────────────────────────────┘
```

必须可见：

- 车辆速度、档位、自动驾驶、方向盘角度。
- 目的地、路线状态、CARLA 指令状态。
- 助手状态、对话、意图、置信度、动作列表。
- 用户状态 chips。
- 空调、车窗、座椅通风、氛围灯、音乐状态。
- 机票、奶茶、新闻、视频服务卡片。
- 11 个功能入口。
- `Unity WebGL / ADS Visualization Reserved` 占位区域。

视觉风格：

- 深色高对比汽车 HMI。
- 信息密度高但清晰。
- 不做营销页。
- 不做大 hero。
- 不使用装饰性渐变球。
- 文字必须适配 3840 x 590，不溢出。

## 11. Unity WebGL 预留方案

第一版：

- HTML 中放一个 WebGL 预留容器。
- 显示 ADS/车辆状态可视化占位内容。

后续接入方式：

```text
FastAPI/WebSocket -> HTML app.js -> Unity WebGL JS bridge -> Unity C# scripts
```

不要让 Unity WebGL 直接连接旧 TCP server。

建议接口：

```javascript
unityInstance.SendMessage("CockpitBridge", "OnVehicleState", JSON.stringify(state));
unityInstance.SendMessage("CockpitBridge", "OnServiceAction", JSON.stringify(action));
```

## 12. Demo 场景

### 场景 A：热舒适服务

输入：

```text
好热啊
```

期望：

- intent: `thermal_comfort`
- 调低空调。
- 打开座椅通风。
- HMI 打开舒适服务卡。
- TTS 回复。

### 场景 B：情绪/娱乐服务

输入：

```text
我有点难过 / 好无聊
```

期望：

- 切换氛围灯。
- 推荐音乐。
- 助手进行简短陪伴回复。

### 场景 C：无语音疲劳主动服务

输入：

```text
HMI 打开 fatigue 状态，车辆高速/自动驾驶
```

期望：

- 系统主动触发。
- 推荐服务区。
- 切换舒缓模式。
- HMI 展示主动服务解释。

### 场景 D：CARLA 驾驶控制

输入：

```text
帮我换到左车道
```

期望：

- intent: `driving_control`
- action: `change_lane(left)`
- CARLA 尽可能执行，HMI 显示指令已下发。

输入：

```text
去机场
```

期望：

- 目的地变更为机场。
- 路线面板更新。

### 场景 E：本地生活服务

输入：

```text
帮我订一张去上海的机票
我想喝奶茶
看一下今天新闻
刷会儿视频
```

期望：

- 打开对应模拟卡片。
- 不接真实 API。

## 13. 服务编排 Prompt 要求

模型输出必须是 JSON。

允许 actions：

```text
set_ac_temperature
set_seat_ventilation
toggle_window
set_ambient_light
play_music
set_cabin_mode
show_alert
set_destination
reroute
change_lane
enable_autopilot
stop_vehicle
slow_down
open_service_card
set_user_state
```

允许 intents：

```text
thermal_comfort
emotion_companion
entertainment
fatigue_safety
driving_control
navigation
local_life
news
video
general_chat
unknown
```

风险驾驶动作默认需要确认。

## 14. 开发顺序

### Step 1：安全和配置

- `.env.example`
- `.gitignore`
- `settings.py` 环境变量化
- `requirements.txt`

### Step 2：状态和服务层

- `CabinStateManager`
- `ServiceExecutor`
- `service_knowledge.json`
- `ServiceAgent`

### Step 3：Web HMI

- FastAPI server
- 静态页面
- `/api/state`
- `/api/command`
- demo buttons

### Step 4：双屏并行启动

- `main.py --web-hmi`
- Web server 线程启动。
- CARLA 主循环继续运行。
- `--mock-carla` 和 `--hmi-only` 可用。

### Step 5：CARLA 指令

- lane change
- stop
- slow down
- set destination/reroute state

### Step 6：火山能力接入

- 保留 ASR/TTS。
- 保留豆包对话。
- 新增结构化服务编排。
- 端到端实时语音作为可选后续，不阻塞 MVP。

### Step 7：视觉打磨

- 超宽屏布局。
- 服务卡片。
- Unity WebGL 预留区。

## 15. 验收标准

第一版合格条件：

1. `python main.py --web-hmi` 能启动。
2. 浏览器打开 `http://localhost:8080` 能看到 3840 x 590 HMI。
3. HMI 可在第二块屏幕全屏展示。
4. CARLA/pygame 画面可在第一块屏幕运行。
5. HMI 不依赖 Unity。
6. Unity WebGL 预留容器可见。
7. HMI 上显示 11 个功能。
8. 文本命令至少能跑通：
   - “好热啊”
   - “我有点难过”
   - fatigue toggle
   - “换到左车道”
   - “我想喝奶茶”
9. CARLA 真实状态能进入 HMI；CARLA 不在时也有 mock 状态。
10. 火山 ASR/TTS/豆包链路不被破坏。
11. 密钥不再硬编码。

## 16. 不要做的事

- 第一版不要把完整 HMI 放回 Unity。
- 不要让 Unity WebGL 直接使用旧 TCP。
- 不要真实下单、支付、登录外部账号。
- 不要部署 Qwen3-Omni / MiniCPM-o / GLM-4-Voice 作为主线。
- 不要训练模型。
- 不要重写整个 CARLA 桥接。
- 不要把 AI 动作只藏在聊天框里，必须在 HMI 中可解释展示。

## 17. 最终演示效果

用户打开双屏：

- 一个屏幕看到 CARLA 车辆在跑。
- 另一个屏幕看到超宽智能座舱 HMI。
- 用户说“好热啊”，HMI 显示 AI 理解为热舒适需求，并执行空调/座椅通风。
- 用户说“换到左车道”，HMI 显示驾驶指令，CARLA 尽可能响应。
- 用户不开口但切换疲劳状态，系统主动推荐休息。
- 用户说“我想喝奶茶”，HMI 打开奶茶服务卡片。
- 中央 WebGL 区域暂时显示 ADS/Unity 预留可视化，后续再接 Unity WebGL。

这就是第一阶段可交付 MVP。
