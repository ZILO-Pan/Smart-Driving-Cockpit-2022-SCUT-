# Active Cabin OS · 智慧驾驶座舱

> 面向舱驾一体场景的端云协同多模态智能座舱主动服务系统设计研究

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│  浏览器 HMI（3840×590 超宽屏）                           │
│  ┌──────────┬──────────────┬───────────────┐            │
│  │ ADAS 3D  │  导航/Unity  │  座舱卡片/服务 │            │
│  └──────────┴──────────────┴───────────────┘            │
│  + NOVA 语音助手 (RTC SDK + 唤醒词)                      │
└────────────────────┬────────────────────────────────────┘
                     │ WebSocket + REST API
┌────────────────────┴────────────────────────────────────┐
│  FastAPI 后端（edge/hmi_server/）                         │
│  - 车辆状态推送 (30Hz)                                    │
│  - 语音 API (/api/voice/start|stop|token|fc-execute)     │
│  - 唤醒词 WebSocket (/ws/wake)                           │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│  火山引擎云服务                                           │
│  - RTC 房间（S2S 端到端语音模型）                          │
│  - 方舟 LLM（Function Calling）                          │
│  - ASR 流式识别（唤醒词检测用）                            │
└─────────────────────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│  CARLA 仿真器 / Mock 数据                                │
│  - 车辆状态、周围车辆、路网、红绿灯                        │
└─────────────────────────────────────────────────────────┘
```

## 启动方式

```bash
# 标准模式：Mock 数据 + Web HMI + NOVA 语音
python main.py --web-hmi --mock-carla

# 连接 CARLA 仿真器
python main.py --web-hmi

# 仅 HMI（无 AI 无 CARLA）
python main.py --hmi-only

# 旧版本地语音（PyAudio，需 --legacy-voice）
python main.py --web-hmi --mock-carla --legacy-voice
```

## 目录结构（当前活跃）

```
smart_cockpit/
├── main.py                          # 主入口
├── config/
│   └── settings.py                  # 全局配置（从 .env 加载）
│
├── cloud/voice/
│   └── rtc_service.py               # 火山 RTC API（Start/Stop/Update VoiceChat + Token）
│
├── edge/hmi_server/
│   ├── server.py                    # FastAPI 主服务 + WebSocket 状态推送
│   ├── voice_api.py                 # 语音 API 路由（/api/voice/*）+ FC 执行
│   └── wake_ws.py                   # 唤醒词 WebSocket（/ws/wake）
│
├── edge/state/
│   ├── vehicle_state.py             # 车辆状态管理（速度/转向/ADAS感知）
│   ├── cabin_state.py               # 座舱状态管理（空调/氛围灯/模式）
│   └── service_executor.py          # FC 执行器（WebSocket 广播动作给前端）
│
├── edge/carla/
│   └── bridge.py                    # CARLA 仿真器桥接
│
├── hmi/static/
│   ├── index.html                   # HMI 主页面
│   ├── app.js                       # HMI 核心逻辑 + _executeFCAction
│   ├── styles.css                   # 样式
│   ├── voice.js                     # NOVA 语音前端（RTC + 唤醒词 + FC）
│   ├── wake-processor.js            # AudioWorklet VAD 处理器
│   ├── volc-rtc.min.js              # 火山 RTC SDK
│   └── unity/                       # Unity WebGL 3D 场景
│
├── .env                             # 密钥（不入库）
├── .env.example                     # 密钥模板
└── VOICE_ISSUE_REPORT.md            # 当前语音问题排查报告
```

## 可以删除的旧文件

以下文件属于**旧 TTS/ASR 本地语音方案**（PyAudio + pygame + 火山 TTS/ASR WebSocket），已被 RTC 端到端方案替代：

| 文件 | 用途（已废弃） |
|------|----------------|
| `cloud/voice/microphone_asr.py` | 本地 PyAudio 录音 + 火山 ASR WebSocket |
| `cloud/voice/speaker_tts.py` | 火山 TTS WebSocket + pygame 播放 |
| `cloud/agent/assistant_manager.py` | 旧 AI 编排（ASR→LLM→TTS 循环） |
| `cloud/agent/service_agent.py` | 旧 Agent 模式（LLM 输出 JSON 动作） |
| `cloud/chat/doubao_chat.py` | 旧豆包对话接口（HTTP Responses API） |
| `cloud/vision/doubao_vision.py` | 旧视觉分析（定时截图 → LLM） |
| `communication/protocol.py` | TCP Unity 协议（已用 WebSocket 替代） |
| `communication/tcp_server.py` | TCP 服务端（旧 Unity 原生客户端用） |
| `test_rtc_voice.py` | 一次性测试脚本 |

以下**文档**也可以清理：

| 文件 | 说明 |
|------|------|
| `VOLC_REALTIME_VOICE_INTEGRATION.md` | 集成过程文档（已完成） |
| `UNITY_INTEGRATION_TASKS.md` | Unity 集成任务（已完成） |
| `COMMANDS.md` | 命令备忘（个人用） |
| `handoff/` 整个目录 | 项目交接文档（看你要不要保留） |

## 保留的文件

这些是当前系统正在使用的，**不要删**：

- `main.py` — 仍引用旧模块做 `--legacy-voice` 降级，删旧文件后需同步清理
- `config/settings.py` — 仍有 ASR/TTS 相关配置项，删后需清理
- `edge/state/*` — 仍在使用
- `edge/hmi_server/*` — 核心服务
- `cloud/voice/rtc_service.py` — RTC 新方案核心
- `hmi/static/*` — 全部保留

## 删除后需要同步修改的代码

1. **`main.py`**：删除 `--legacy-voice` 分支代码（第 84-99 行）
2. **`config/settings.py`**：删除 `ASR_*`、`TTS_*`、`MIC_*`、`VISION_*` 相关配置
3. **`cloud/__init__.py`** 及各子目录 `__init__.py`**：如果目录清空了就删掉


