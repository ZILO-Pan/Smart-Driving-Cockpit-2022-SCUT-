# 智慧驾驶座舱 · 端云协同多模态主动服务系统

> 面向舱驾一体场景的端云协同多模态智能座舱主动服务系统设计研究

## 系统定位

这不是一个普通的车载语音助手。它是：

**一个端云协同的多模态主动服务原型，面向舱驾一体化场景。**

- CARLA 模拟器代表驾驶侧
- HTML 超宽屏（3840×590）作为 HMI 主界面
- 火山引擎/豆包提供云端智能：语音、对话、多模态理解、服务编排
- 边缘端执行 CARLA 控制、HMI 渲染、座舱状态管理、安全策略

## 项目架构

```
smart_cockpit/
├── main.py                          # 主入口 - 多模式启动
├── config/
│   └── settings.py                  # 全局配置（从 .env 加载敏感信息）
│
├── edge/                            # ===== 边缘端 =====
│   ├── carla/
│   │   └── bridge.py                # CARLA 仿真桥接（场景/事件/摄像头）
│   ├── state/
│   │   ├── vehicle_state.py         # 车辆状态数据模型
│   │   ├── cabin_state.py           # 座舱状态（空调/座椅/氛围灯/用户感知）
│   │   └── service_executor.py      # 服务执行器（Agent动作→状态变更）
│   └── hmi_server/
│       └── server.py                # FastAPI + WebSocket 服务端
│
├── cloud/                           # ===== 云端 =====
│   ├── agent/
│   │   ├── assistant_manager.py     # AI 助手编排器
│   │   └── service_agent.py         # 服务编排 Agent（结构化JSON输出）
│   ├── chat/
│   │   └── doubao_chat.py           # 豆包大模型对话 + 视觉理解
│   ├── vision/
│   │   └── doubao_vision.py         # 视觉观察模块（定时截图分析）
│   └── voice/
│       ├── microphone_asr.py        # 火山引擎 ASR（语音识别）
│       └── speaker_tts.py           # 火山引擎 TTS（语音合成）
│
├── hmi/                             # ===== HMI 前端 =====
│   └── static/
│       ├── index.html               # 3840×590 超宽座舱界面
│       ├── styles.css               # 深色科技风格样式
│       └── app.js                   # WebSocket 客户端
│
├── communication/                   # ===== 通信（保留兼容） =====
│   ├── tcp_server.py                # TCP 服务端（Unity 原生客户端适配）
│   └── protocol.py                  # 消息协议定义
│
├── .env                             # 密钥配置（不提交）
├── .env.example                     # 密钥模板
├── requirements.txt                 # Python 依赖
└── COMMANDS.md                      # 常用命令速查
```

## 核心数据流

```
┌────────────── 云端 (Cloud) ──────────────┐
│                                           │
│  语音输入 → ASR → 服务Agent → TTS输出     │
│                    ↕                      │
│            豆包大模型推理                   │
│         (意图/编排/视觉/对话)              │
│                                           │
├────────────── 边缘端 (Edge) ─────────────┤
│                                           │
│  CARLA仿真 → 车辆状态 → WebSocket推送     │
│                ↕                          │
│          座舱状态管理                      │
│     (空调/座椅/氛围/用户感知)              │
│                ↕                          │
│         服务执行器                         │
│    (Agent指令→座舱/驾驶动作)              │
│                                           │
├────────────── HMI 前端 ─────────────────┤
│                                           │
│  3840×590 超宽屏 HTML 界面                │
│  车辆仪表 | Unity预留区 | AI助手+服务卡片  │
│                                           │
└───────────────────────────────────────────┘
```

## 11 项功能

1. 自然语音对话
2. 模糊意图理解
3. 主动服务推荐
4. 多模态状态感知
5. 舱驾一体联动
6. 端云协同架构
7. 可解释 HMI 反馈
8. 模拟座舱控制
9. 语音控制驾驶任务
10. 生活服务卡片
11. 轻量语义知识库

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置密钥

```bash
# 复制模板并填入你的火山引擎 API Key
cp .env.example .env
# 编辑 .env 填入密钥
```

### 3. 启动

```bash
# 纯 HMI 测试（Mock 数据，无需 CARLA）
python main.py --hmi-only

# Web HMI + AI（Mock 数据，无需 CARLA）
python main.py --web-hmi --mock-carla

# 完整模式（需要 CARLA 运行中）
python main.py --web-hmi

# CARLA + Web HMI（无 AI）
python main.py --web-hmi --no-ai
```

### 4. 访问 HMI

浏览器打开 `http://localhost:8080`，建议第二显示器全屏。

## 双屏演示模式

```
显示器1: CARLA / pygame 仿真窗口
显示器2: Chrome 全屏 http://localhost:8080（3840×590）
```

## 演示场景

| 用户说 | 触发效果 |
|--------|----------|
| "好热啊" | 空调降温 + 座椅通风 |
| "我有点难过" | 情感陪伴 + 氛围灯切换 |
| "帮我换到左车道" | CARLA 变道指令 |
| "去机场" | 导航目的地设置 |
| "帮我订一张去上海的机票" | 机票服务卡片 |
| "我想喝奶茶" | 奶茶服务卡片 |
| "看一下今天新闻" | 新闻服务卡片 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 仿真 | CARLA 0.9.15 + pygame |
| 后端 | Python 3.12 + FastAPI + WebSocket |
| 前端 | HTML/CSS/JS（3840×590 超宽适配） |
| 云端AI | 火山方舟 豆包大模型（对话+视觉） |
| 语音 | 火山引擎 ASR/TTS WebSocket |
| 未来 | 豆包端到端实时语音 / Unity WebGL 嵌入 |

## 后续开发方向

1. **豆包实时语音**：接入端到端实时语音大模型，替代 ASR+TTS 三段式
2. **Unity WebGL**：在 HMI 预留区嵌入 3D 驾驶可视化
3. **本地推理**：Qwen3-4B 作为边缘端 fallback
4. **Function Calling**：结构化服务编排升级
