# 智慧驾驶座舱系统 - Smart Driving Cockpit

## 项目架构

```
smart_cockpit/
├── config/
│   └── settings.py              # 全局配置（端口、API Key、串口等）
├── core/
│   ├── carla_bridge.py          # CARLA 核心桥接（基于你的 follow_car.py 重构）
│   └── vehicle_state.py         # 车辆状态数据模型（速度、转向角、位置等）
├── communication/
│   ├── tcp_server.py            # TCP 服务端 → Unity HMI 连接
│   ├── serial_bridge.py         # 串口通信 → ESP32 舵机控制
│   └── protocol.py              # 统一消息协议定义（JSON schema）
├── ai_assistant/
│   ├── doubao_chat.py           # 豆包 AI 对话接口
│   ├── doubao_vision.py         # 豆包视觉助手（摄像头画面分析）
│   └── assistant_manager.py     # AI 助手管理器（对话上下文、调度）
├── hmi/
│   └── unity_data_provider.py   # 为 Unity 准备 HMI 数据包
├── hardware/
│   └── servo_mapper.py          # 转向角 → 舵机 PWM 映射逻辑
├── main.py                      # 主入口 - 启动所有模块
└── README.md
```

## 模块职责 & 改动指南

| 你要做的事 | 改哪个文件 |
|---|---|
| 调整 CARLA 场景/车辆/摄像头 | `core/carla_bridge.py` |
| 修改车辆状态数据结构 | `core/vehicle_state.py` + `communication/protocol.py` |
| 调试 Unity 通信 | `communication/tcp_server.py` + `hmi/unity_data_provider.py` |
| 接入/调试豆包 API | `ai_assistant/doubao_chat.py` 或 `doubao_vision.py` |
| 调试 ESP32 舵机 | `communication/serial_bridge.py` + `hardware/servo_mapper.py` |
| 修改端口/API Key/串口号 | `config/settings.py` |
| 新增传感器数据 | `core/carla_bridge.py` 里加传感器 → `vehicle_state.py` 加字段 |
