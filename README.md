# 智慧驾驶座舱系统 - Smart Driving Cockpit

## 项目架构

```
smart_cockpit/
├── config/
│   └── settings.py                # 全局配置（API Key、端口、串口、AI参数等）
├── core/
│   ├── carla_bridge.py            # CARLA 核心桥接（场景切换、极端事件、摄像头）
│   └── vehicle_state.py           # 车辆状态数据模型（速度、转向角、位置等）
├── communication/
│   ├── tcp_server.py              # TCP 服务端 → Unity HMI 连接
│   ├── serial_bridge.py           # 串口通信 → ESP32 舵机控制
│   └── protocol.py                # 统一消息协议定义（JSON schema）
├── ai_assistant/
│   ├── doubao_chat.py             # 豆包大模型对话 + 视觉理解（火山方舟 API）
│   ├── doubao_vision.py           # 视觉观察模块（定时/事件触发截图分析）
│   ├── microphone_asr.py          # 麦克风语音识别（火山引擎 ASR WebSocket）
│   ├── speaker_tts.py             # 语音合成播放（火山引擎 TTS + pygame）
│   └── assistant_manager.py       # AI 助手管理器（编排所有AI模块）
├── hmi/
│   └── unity_data_provider.py     # 为 Unity 准备 HMI 数据包
├── hardware/
│   ├── servo_mapper.py            # 转向角 → 舵机 PWM 映射逻辑
│   └── esp32_servo_controller.ino # ESP32 Arduino 参考代码
├── main.py                        # 主入口 - 启动所有模块
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install pygame numpy carla requests pyaudio websockets==12.0 Pillow
```

### 2. 启动 CARLA 模拟器

先启动 CARLA（CarlaUE4.exe），然后运行项目：

```bash
# 完整启动（需要所有硬件和API就绪）
python main.py

# 不接串口（没有ESP32时）
python main.py --no-serial

# 不接串口也不启动AI（纯CARLA测试）
python main.py --no-serial --no-ai
```

### 3. 运行效果

启动后系统会：
- CARLA 中生成 Tesla Model 3 + NPC 车辆 + 行人，自动驾驶
- 麦克风常开，对着电脑说话 AI 会回应（语音对话）
- 每15秒自动分析前方路况并语音播报
- 按 1~8 切换场景，按 C 触发极端交通事件
- TCP 服务端等待 Unity HMI 连接
- 车辆转向角数据实时发送给 ESP32 舵机

## 快捷键

| 按键 | 功能 |
|------|------|
| 1~8 | 切换场景（晴天城市/暴雨夜间/大雾/高速/拥堵/乡村/午夜/暴风） |
| C | 触发随机极端交通事件（鬼探头/急停/闯红灯/逆行/急变道/人群横穿） |
| SPACE | 切换车外/车内视角 |
| ESC | 退出 |

## 模块职责 & 改动指南

### 改 CARLA 场景

| 你要做的事 | 改哪个文件 |
|---|---|
| 换地图/天气/NPC数量 | `core/carla_bridge.py` 里的 `SCENE_PRESETS` |
| 加新的极端事件 | `core/carla_bridge.py` 里的 `CHAOS_EVENTS` + 对应方法 |
| 调摄像头位置 | `core/carla_bridge.py` 里的 `_setup_cameras()` |
| 改NPC默认数量 | `config/settings.py` 里的 `CARLA_NPC_COUNT` |

### 改 AI 助手

| 你要做的事 | 改哪个文件 |
|---|---|
| 改 AI 人设/性格 | `ai_assistant/doubao_chat.py` 里的 `SYSTEM_PROMPT` |
| 改视觉分析提示词 | `ai_assistant/doubao_chat.py` 里的 `VISION_PROMPT` |
| 改路况播报间隔 | `config/settings.py` 里的 `VISION_CAPTURE_INTERVAL` |
| 关闭自动播报 | `config/settings.py` 里 `VISION_AUTO_BROADCAST = False` |
| 换大模型/接入点 | `config/settings.py` 里的 `ARK_ENDPOINT_ID` |
| 换 TTS 音色 | `config/settings.py` 里的 `TTS_VOICE_TYPE` |
| 调麦克风灵敏度 | `config/settings.py` 里的 `MIC_SILENCE_THRESHOLD` |
| 改对话流程 | `ai_assistant/assistant_manager.py` 里的 `_on_user_speech()` |

### 改通信

| 你要做的事 | 改哪个文件 |
|---|---|
| 调试 Unity TCP 通信 | `communication/tcp_server.py` + `hmi/unity_data_provider.py` |
| 给 Unity 增加数据字段 | `core/vehicle_state.py` + `communication/protocol.py` |
| 调试 ESP32 舵机 | `communication/serial_bridge.py` + `hardware/servo_mapper.py` |
| 改端口/串口号 | `config/settings.py` |

## 数据流

```
┌─────────────────── AI 对话链路 ───────────────────┐
│                                                     │
│  麦克风 → ASR识别 → 大模型对话 → TTS语音播放       │
│              ↑            ↑                         │
│         pyaudio      车辆状态+路况                  │
│                                                     │
├─────────────────── 视觉播报链路 ──────────────────┤
│                                                     │
│  CARLA摄像头 → 定时截图 → 大模型视觉分析 → TTS     │
│                                                     │
├─────────────────── Unity HMI 链路 ────────────────┤
│                                                     │
│  车辆状态 → TCP推送 → Unity 显示仪表盘/导航/AI气泡  │
│                                                     │
├─────────────────── 硬件控制链路 ──────────────────┤
│                                                     │
│  转向角 → 串口 → ESP32 → 舵机/电机                  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## 使用的 API

| 服务 | 用途 | 配置位置 |
|------|------|----------|
| 火山方舟 (豆包大模型) | 对话 + 视觉理解 | `ARK_API_KEY` / `ARK_ENDPOINT_ID` |
| 火山引擎 ASR | 语音识别 | `ASR_APP_KEY` / `ASR_ACCESS_KEY` |
| 火山引擎 TTS | 语音合成 | `TTS_APP_ID` / `TTS_ACCESS_TOKEN` / `TTS_VOICE_TYPE` |

## 后续开发方向

1. **Unity HMI**: 连接 TCP 服务端，显示智驾界面、AI 助手形象动画
2. **ESP32 舵机**: 接入串口，实时映射方向盘转角到物理舵机
3. **AI 增强**: 接入更多豆包能力（导航、音乐推荐、function calling）
