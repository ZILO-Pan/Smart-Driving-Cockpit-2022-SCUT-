# Active Cabin OS · 智慧驾驶座舱

> 面向舱驾一体场景的端云协同多模态智能座舱主动服务系统设计研究

## 系统定位

**一个端云协同的多模态主动服务原型，面向舱驾一体化场景。**

- CARLA 模拟器代表驾驶侧（Mercedes AMG GT Coupe 白色主车）
- HTML 超宽屏（3840×590）作为 HMI 主界面
- Unity WebGL 提供 3D 交互可视化场景
- 火山引擎/豆包提供云端智能：语音、对话、多模态理解、服务编排
- 边缘端执行 CARLA 控制、HMI 渲染、座舱状态管理、安全策略

## 项目架构

```
smart_cockpit/
├── main.py                          # 主入口 - 多模式启动
├── config/
│   └── settings.py                  # 全局配置（从 .env 加载）
│
├── edge/                            # ===== 边缘端 =====
│   ├── carla/
│   │   └── bridge.py                # CARLA 仿真桥接 + ADAS 感知 + 路网生成
│   ├── state/
│   │   ├── vehicle_state.py         # 车辆状态数据模型
│   │   ├── cabin_state.py           # 座舱状态
│   │   └── service_executor.py      # 服务执行器
│   └── hmi_server/
│       └── server.py                # FastAPI + WebSocket + 路网推送
│
├── cloud/                           # ===== 云端 =====
│   ├── agent/
│   │   ├── assistant_manager.py     # AI 助手编排器
│   │   └── service_agent.py         # 服务编排 Agent
│   ├── chat/
│   │   └── doubao_chat.py           # 豆包大模型对话 + 视觉理解
│   ├── vision/
│   │   └── doubao_vision.py         # 视觉观察模块
│   └── voice/
│       ├── microphone_asr.py        # 火山引擎 ASR
│       └── speaker_tts.py           # 火山引擎 TTS
│
├── hmi/                             # ===== HMI 前端 =====
│   └── static/
│       ├── index.html               # 3840×590 超宽座舱界面
│       ├── styles.css               # 车规级深色主题样式
│       ├── app.js                   # 主逻辑 + Three.js ADAS + Unity Bridge
│       ├── fonts/                   # MB Corpo 字体
│       ├── videos/                  # 壁纸视频 + 音频
│       └── unity/                   # Unity WebGL Build 产物（本地）
│
├── handoff/                         # 交接文档
├── communication/                   # TCP 通信（保留兼容 Unity 原生）
├── .env                             # 密钥配置（不提交）
├── .env.example                     # 密钥模板
├── requirements.txt                 # Python 依赖
└── COMMANDS.md                      # 常用命令速查
```

## 核心数据流

```
┌─────────────── 云端 (Cloud) ───────────────┐
│                                             │
│  语音输入 → ASR → 服务Agent → TTS输出       │
│                    ↕                        │
│            豆包大模型推理                     │
│         (意图/编排/视觉/对话)                │
│                                             │
├─────────────── 边缘端 (Edge) ──────────────┤
│                                             │
│  CARLA仿真 → 车辆状态 → WebSocket 10Hz     │
│                ↕                            │
│         路网数据（启动时一次性推送）           │
│                ↕                            │
│         ADAS 感知（车辆/行人/红绿灯）        │
│                ↕                            │
│         服务执行器                           │
│    (Agent指令→座舱/驾驶/Unity动作)          │
│                                             │
├─────────────── HMI 前端 ───────────────────┤
│                                             │
│  3840×590 超宽屏 HTML 界面                  │
│  视频壁纸 | Unity 3D | ADAS | AI助手        │
│                                             │
└─────────────────────────────────────────────┘
```

## ADAS 实时可视化

Three.js 3D 鸟瞰场景，与 CARLA 实时联动：

| 功能 | 实现 |
|------|------|
| 路面渲染 | 启动时一次性构建完整路网 mesh（世界坐标），每帧仅做平移+旋转变换 |
| 车道线 | 相邻车道共享边为虚线分隔，外边界为实线 |
| 周围车辆 | 15 个 NPC 池，按 CARLA actor ID 稳定分配，lerp 插值平滑 |
| 车辆类型 | 根据 `number_of_wheels` 区分 car/bike/truck，不同渲染模型 |
| 行人 | 10 个行人池，骨骼动画 + 横穿检测（红色高亮） |
| Waypoint 路线 | 前方 120m 规划路径，青色半透明宽带实时渲染 |
| 红绿灯 | 仅当 `is_at_traffic_light()` 时显示，billboard 朝向摄像头 |
| 驾驶仪表 | 速度/档位/功率/油门/刹车/方向盘转角 |

## HMI 界面设计

### 分层架构

| 层级 | 内容 |
|------|------|
| z-0 背景 | HMI.mp4 循环视频壁纸 |
| z-50 | Unity WebGL 3D 场景（太空 + 跑车） |
| z-100 | 主 UI（半透明面板浮在壁纸上） |

### UI 布局

```
┌───────────────────────────────────────────────────────────┐
│ 顶部状态栏 — 连接状态 · AutoPilot · 时间                   │
├────────┬──────────────────────────────┬───────────────────┤
│ 左侧   │         中 央                │     右 侧         │
│ ADAS   │    视频壁纸 / Unity 3D       │   动态卡片(4槽)   │
│ Three.js│    导航地图                  │   音乐/视频/服务  │
│ 仪表板  │                             │                   │
├────────┴──────────────────────────────┴───────────────────┤
│ 底部 Dock：导航 · ADAS · AI助手 · 服务 · 座舱 · 3D        │
└───────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置密钥

```bash
cp .env.example .env
# 编辑 .env 填入火山引擎 API Key
```

### 3. 启动

```bash
# 纯 HMI 测试（无需 CARLA）
python main.py --hmi-only

# Web HMI + AI（Mock 数据）
python main.py --web-hmi --mock-carla

# 完整模式（需要 CARLA 运行中）
python main.py --web-hmi

# CARLA + Web HMI（无 AI）
python main.py --web-hmi --no-ai
```

### 4. 访问

浏览器打开 `http://localhost:8080`，建议第二显示器全屏。

## 双屏演示模式

```
显示器1: CARLA / pygame 仿真窗口
显示器2: Chrome 全屏 http://localhost:8080（3840×590）
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 仿真 | CARLA 0.9.15 + pygame |
| 后端 | Python 3.12 + FastAPI + WebSocket |
| 前端 | HTML/CSS/JS（3840×590 超宽适配） |
| 3D | Unity WebGL（太空 + 跑车场景） |
| ADAS | Three.js 实时鸟瞰可视化 |
| 云端AI | 火山方舟 豆包大模型（对话+视觉） |
| 语音 | 火山引擎 ASR/TTS WebSocket |
| 字体 | Mercedes-Benz Corporate (MB Corpo) |
