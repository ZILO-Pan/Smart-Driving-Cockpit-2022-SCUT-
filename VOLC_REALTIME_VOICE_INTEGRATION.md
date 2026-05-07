# 火山引擎实时对话式 AI 集成方案

> 给 Claude Code 的实施任务文档
> 项目：SMART_COCKPIT 智慧驾驶座舱
> 目标：在现有架构上集成火山引擎"实时对话式 AI"，实现端到端实时语音 + 视频 + Function Calling 控制 HMI/Unity

---

## 一、最终效果描述

集成完成后的体验：

1. **实时语音对话**：用户说话，AI 用语音回复，延迟 500~800ms（接近真人对话）
2. **视频理解**：用户摄像头画面被 AI"看到"，AI 能理解视觉信息（如用户表情、手势、车内场景）
3. **AI 主动操控 HMI**：通过 Function Calling，AI 决定要做什么操作时，自动调用 Unity 接口（switchCamera、togglePart、rotateCar 等）
4. **智能打断**：用户能随时插话打断 AI；AI 也能监听用户全程
5. **保留现有架构**：不破坏现有的 CARLA、服务卡片、WebSocket 推送等功能

### 数据流概览

```
用户 (麦克风+摄像头) 
    ↓ [RTC SDK 上行]
火山 RTC 房间
    ↓
端到端实时语音大模型 (听 + 想 + 说)
    ↓ 触发 Function Calling
你的 FastAPI /voice-callback
    ↓ WebSocket 推送
浏览器前端 → window.HMI.xxx() → Unity 执行
    ↑
模型同时通过 RTC 把语音回复发回浏览器播放
```

---

## 二、技术栈与凭证

### 2.1 已开通的服务（用户已完成）

| 服务 | 用途 |
|------|------|
| 火山 RTC | 浏览器和云端之间传音视频的"管道" |
| 豆包端到端实时语音大模型 | AI 大脑，听说一体化 |
| 火山方舟 + Endpoint | Function Calling 调度引擎 |

### 2.2 凭证清单（写到 `.env` 文件）

```bash
# 火山 RTC（浏览器音视频传输管道）
VOLC_RTC_APP_ID="69f9e4de9f2c7701693990b4"
VOLC_RTC_APP_KEY="58f6b72c1ede4712ac2647475c3bdde5"

# 豆包端到端实时语音
VOLC_VOICE_APP_ID="3121922445"
VOLC_VOICE_ACCESS_TOKEN="qAyVTVefm_F9L2OyacRqchiishYBrXNk"
VOLC_VOICE_API_KEY="4927180c-6b5e-48ba-844d-2b756d004984"

# 火山方舟（function calling 用）
ARK_API_KEY="c5504110-d5bd-4876-8009-d3ddf3897ef8"
ARK_ENDPOINT_ID="ep-20260316012441-lwsjl"

# 后端服务回调地址（你的 FastAPI 必须能被火山访问到，开发期可用 ngrok/cpolar）
VOICE_CALLBACK_URL="https://your-public-host/voice-callback"
```

### 2.3 需要新增的依赖

**Python 后端 (`requirements.txt`)：**
```
volcengine-python-sdk>=1.0.100   # 用于签名调用 RTC OpenAPI
httpx>=0.27.0                     # 异步 HTTP 客户端
```

**前端：**
```
@volcengine/rtc                  # 火山 RTC Web SDK（核心）
```
通过 npm 或 CDN 引入。SMART_COCKPIT 是纯静态 HTML，**推荐用 CDN**：
```html
<script src="https://lf-unpkg.volccdn.com/obj/vcloudfe/sdk/@volcengine/rtc/4.66.1/index.min.js"></script>
```

---

## 三、整体架构改造

### 3.1 新增文件

```
SMART_COCKPIT/
├── cloud/voice/
│   ├── microphone_asr.py      # 旧版 ASR，保留作降级
│   ├── speaker_tts.py         # 旧版 TTS，保留作降级
│   └── realtime_voice.py      # 🆕 新增：火山 RTC + 端到端语音桥接
│
├── edge/hmi_server/
│   └── server.py              # 🔧 修改：添加 /voice-callback、/voice-token 路由
│
├── hmi/static/
│   ├── index.html             # 🔧 修改：引入 RTC SDK，添加摄像头区域
│   ├── unity-bridge.js        # 已存在
│   ├── voice-room.js          # 🆕 新增：火山 RTC Room 管理
│   └── app.js                 # 🔧 修改：处理后端 voice 事件
│
└── docs/
    └── VOLC_REALTIME_VOICE_INTEGRATION.md  # 本文档
```

### 3.2 工作流程（11 步）

```
1. 用户点击"开始对话"按钮
2. 前端 → 后端 /voice-token 请求 RTC token
3. 后端生成 token，调用火山 StartVoiceChat 启动智能体
4. 智能体加入 RTC 房间
5. 前端用 RTC SDK 加入同一房间，开麦克风+摄像头
6. 用户说话 → SDK 自动上传音频到云端
7. 端到端语音模型听懂 → 决定调用工具
8. 模型 HTTP POST 到后端 /voice-callback (function call)
9. 后端通过现有 WebSocket 推送给前端
10. 前端 app.js 调用 window.HMI.xxx() → Unity 执行
11. 模型同时通过 RTC 发回语音回复，前端自动播放
```

---

## 四、后端实现（核心）

### 4.1 新建 `cloud/voice/realtime_voice.py`

负责调用火山 OpenAPI 启动智能体。关键 API：

**接口：** `POST https://rtc.volcengineapi.com?Action=StartVoiceChat&Version=2024-12-01`

**Python 示例：**
```python
import os
import json
import httpx
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request
from volcengine.Credentials import Credentials

class VolcRealtimeVoice:
    """
    火山引擎实时对话式 AI 智能体管理器
    """
    
    def __init__(self):
        self.rtc_app_id = os.getenv("VOLC_RTC_APP_ID")
        self.rtc_app_key = os.getenv("VOLC_RTC_APP_KEY")
        self.voice_app_id = os.getenv("VOLC_VOICE_APP_ID")
        self.voice_token = os.getenv("VOLC_VOICE_ACCESS_TOKEN")
        self.ark_endpoint_id = os.getenv("ARK_ENDPOINT_ID")
        self.callback_url = os.getenv("VOICE_CALLBACK_URL")

    def build_start_voice_chat_payload(
        self,
        room_id: str,
        task_id: str,
        bot_user_id: str = "smart_cockpit_agent",
        target_user_ids: list = None,
    ) -> dict:
        """构建启动智能体的请求体"""
        return {
            "AppId": self.rtc_app_id,
            "RoomId": room_id,
            "TaskId": task_id,
            "AgentConfig": {
                "TargetUserId": target_user_ids or ["user_1"],
                "WelcomeMessage": "您好，我是您的智能座舱助手，有什么可以帮您？",
                "UserId": bot_user_id,
            },
            "Config": {
                # 端到端语音模型（替代 ASR+TTS）
                "S2SConfig": {
                    "AppId": self.voice_app_id,
                    "AccessToken": self.voice_token,
                    "ResourceId": "volc.speech.dialog",
                    "BotName": "智能座舱助手",
                    "SystemRole": SYSTEM_PROMPT,    # 见下面
                    "SpeakingStyle": "您是专业、友好的车载 AI 助手",
                    "Dialog": {
                        "BotName": "小智",
                        "Voice": "BV001_streaming",  # 默认音色
                    },
                },
                # LLM 配置 - function calling 走方舟
                "LLMConfig": {
                    "Mode": "ArkV3",
                    "EndPointId": self.ark_endpoint_id,
                    "MaxTokens": 1024,
                    "Temperature": 0.3,
                    "TopP": 0.7,
                    "SystemMessages": [SYSTEM_PROMPT],
                    "HistoryLength": 10,
                    # ⭐ 关键：注册工具
                    "Tools": HMI_TOOLS,  # 见下面
                    # ⭐ 关键：配置 function call 回调
                    "FunctionCallingConfig": {
                        "ServerMessageUrl": self.callback_url,
                    },
                },
                # 视觉理解（可选）
                "VisionConfig": {
                    "Enable": True,        # 启用视觉
                    "SnapshotInterval": 3, # 每 3 秒截图分析一次
                },
                # 字幕（可选，用于日志/调试）
                "SubtitleConfig": {
                    "SubtitleMode": 0,
                },
                # 中断配置：支持智能打断
                "InterruptMode": 1,
            },
        }
    
    async def start_agent(self, room_id: str, task_id: str) -> dict:
        """启动智能体"""
        url = "https://rtc.volcengineapi.com"
        params = {"Action": "StartVoiceChat", "Version": "2024-12-01"}
        payload = self.build_start_voice_chat_payload(room_id, task_id)
        
        # 用火山 SDK 签名（必须）
        # ... 签名逻辑见火山文档
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, params=params, json=payload, headers=signed_headers)
        return resp.json()
    
    async def stop_agent(self, room_id: str, task_id: str) -> dict:
        """停止智能体"""
        url = "https://rtc.volcengineapi.com"
        params = {"Action": "StopVoiceChat", "Version": "2024-12-01"}
        payload = {
            "AppId": self.rtc_app_id,
            "RoomId": room_id,
            "TaskId": task_id,
        }
        # ... 签名 + 请求
    
    async def send_tool_result(
        self, room_id: str, task_id: str, 
        tool_call_id: str, result: dict
    ) -> dict:
        """把工具调用结果传回 RTC 服务端"""
        url = "https://rtc.volcengineapi.com"
        params = {"Action": "UpdateVoiceChat", "Version": "2024-12-01"}
        payload = {
            "AppId": self.rtc_app_id,
            "RoomId": room_id,
            "TaskId": task_id,
            "Command": "function",
            "Message": json.dumps({
                "ToolCallID": tool_call_id,
                "Content": json.dumps(result),
            }),
        }
        # ... 签名 + 请求


SYSTEM_PROMPT = """
你是 SMART_COCKPIT 的车载智能助手。
你能：
1. 自然地与用户对话
2. 控制车内 3D 视觉化界面（视角切换、车门开关等）
3. 提供生活服务（订机票、订奶茶、查新闻等）
4. 协助驾驶任务（变道、导航等）

你必须遵守：
- 不要重复用户的话
- 回复简洁自然，避免冗长
- 涉及车内功能时，用 Function Calling 调用相应工具
- 用户表达情绪时（如"好热"、"我累了"），主动提供贴心建议
"""

HMI_TOOLS = [
    {
        "Type": "function",
        "function": {
            "name": "switch_camera",
            "description": "切换 3D 视角到指定视图",
            "parameters": {
                "type": "object",
                "properties": {
                    "view": {
                        "type": "string",
                        "enum": ["default", "astronaut", "carExterior", "carInterior"],
                        "description": "目标视图：default 默认全景，astronaut 宇航员，carExterior 车外环视，carInterior 车内"
                    }
                },
                "required": ["view"]
            }
        }
    },
    {
        "Type": "function",
        "function": {
            "name": "toggle_car_part",
            "description": "开关车辆部件（车门、引擎盖、后备箱、车窗）",
            "parameters": {
                "type": "object",
                "properties": {
                    "part_id": {
                        "type": "string",
                        "enum": ["doorL", "doorR", "hood", "trunk", "windowL", "windowR"],
                        "description": "部件 ID"
                    },
                    "action": {
                        "type": "string",
                        "enum": ["open", "close", "toggle"],
                        "description": "动作"
                    }
                },
                "required": ["part_id", "action"]
            }
        }
    },
    {
        "Type": "function",
        "function": {
            "name": "rotate_car",
            "description": "旋转 3D 车模到指定角度（仅在 carExterior 视角下生效）",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["absolute", "relative", "reset"],
                        "description": "旋转模式：absolute 旋转到绝对角度，relative 相对当前角度旋转，reset 复位到 0"
                    },
                    "angle": {
                        "type": "number",
                        "description": "角度值（度），0~360"
                    }
                },
                "required": ["mode"]
            }
        }
    },
    {
        "Type": "function",
        "function": {
            "name": "show_service_card",
            "description": "在 HMI 上显示生活服务卡片",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_type": {
                        "type": "string",
                        "enum": ["flight", "milk_tea", "news", "weather", "music"],
                        "description": "服务类型"
                    },
                    "params": {
                        "type": "object",
                        "description": "服务相关参数（如机票出发地/目的地）"
                    }
                },
                "required": ["service_type"]
            }
        }
    },
    {
        "Type": "function",
        "function": {
            "name": "control_cabin",
            "description": "控制车内空调、座椅、氛围灯",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {
                        "type": "string",
                        "enum": ["ac_temp", "ac_fan", "seat_heat", "seat_ventilate", "ambient_light"],
                    },
                    "value": {"type": "string", "description": "目标值或档位"}
                },
                "required": ["device", "value"]
            }
        }
    }
]
```

### 4.2 修改 `edge/hmi_server/server.py`

添加 3 个新路由：

```python
from cloud.voice.realtime_voice import VolcRealtimeVoice

voice_manager = VolcRealtimeVoice()
active_sessions = {}  # room_id -> task_id

# ============================================
# 路由 1: 前端请求开始对话，后端启动智能体
# ============================================
@app.post("/api/voice/start")
async def start_voice_session(request: dict):
    user_id = request.get("user_id", "user_1")
    room_id = f"sc_room_{user_id}_{int(time.time())}"
    task_id = f"task_{int(time.time())}"
    
    # 生成 RTC token (前端进房用)
    rtc_token = generate_rtc_token(
        app_id=voice_manager.rtc_app_id,
        app_key=voice_manager.rtc_app_key,
        room_id=room_id,
        user_id=user_id,
    )
    
    # 启动 AI 智能体加入房间
    result = await voice_manager.start_agent(room_id, task_id)
    
    active_sessions[room_id] = task_id
    return {
        "room_id": room_id,
        "token": rtc_token,
        "user_id": user_id,
        "rtc_app_id": voice_manager.rtc_app_id,
    }

# ============================================
# 路由 2: 火山推送的 function call 回调
# ============================================
@app.post("/voice-callback")
async def voice_callback(request: Request):
    """
    火山服务器在 LLM 触发 function call 时 HTTP POST 这里
    格式：{
      "ToolCallID": "call_xxx",
      "Name": "switch_camera",
      "Arguments": "{\"view\":\"astronaut\"}",
      "RoomId": "...",
      "TaskId": "..."
    }
    """
    body = await request.json()
    tool_name = body["Name"]
    arguments = json.loads(body["Arguments"])
    room_id = body["RoomId"]
    task_id = body["TaskId"]
    tool_call_id = body["ToolCallID"]
    
    # 1. 通过 WebSocket 推送给前端，触发 Unity/HMI 执行
    unity_command = translate_tool_to_hmi_command(tool_name, arguments)
    await websocket_broadcast({
        "type": "ai_function_call",
        "tool": tool_name,
        "args": arguments,
        "unity_command": unity_command,  # window.HMI 用
    })
    
    # 2. 把执行结果传回 RTC（让 AI 知道完成了，可以接着说话）
    # 对于"执行型"工具（如切视角），返回简单成功即可
    result = {"status": "success", "message": "已完成"}
    await voice_manager.send_tool_result(room_id, task_id, tool_call_id, result)
    
    return {"ok": True}

def translate_tool_to_hmi_command(tool_name: str, args: dict) -> dict:
    """把火山 function call 翻译成 HMI JSON 协议"""
    if tool_name == "switch_camera":
        return {"action": "switchCamera", "target": args["view"]}
    elif tool_name == "toggle_car_part":
        action_map = {"open": "openPart", "close": "closePart", "toggle": "togglePart"}
        return {
            "action": action_map[args["action"]],
            "target": args["part_id"]
        }
    elif tool_name == "rotate_car":
        return {
            "action": "rotateCar",
            "params": {"mode": args["mode"], "angle": args.get("angle", 0)}
        }
    elif tool_name == "show_service_card":
        return {
            "action": "showServiceCard",
            "params": args
        }
    # ... 其他工具
    return None

# ============================================
# 路由 3: 结束对话
# ============================================
@app.post("/api/voice/stop")
async def stop_voice_session(request: dict):
    room_id = request["room_id"]
    if room_id in active_sessions:
        await voice_manager.stop_agent(room_id, active_sessions[room_id])
        del active_sessions[room_id]
    return {"ok": True}
```

### 4.3 关于 `/voice-callback` 的网络可达性

⚠️ **关键问题**：火山服务器要能 HTTP POST 到你的 `/voice-callback`。本地开发时 `localhost` 火山访问不到，必须穿透：

**方案 A（推荐）：cpolar 内网穿透**（国内访问稳定）
```bash
# 安装 cpolar：https://www.cpolar.com/
cpolar http 8080
# 拿到公网 https URL 后填到 .env 的 VOICE_CALLBACK_URL
```

**方案 B：ngrok**（需翻墙）

**方案 C：部署到云服务器**（最稳定，长期方案）

---

## 五、前端实现

### 5.1 修改 `hmi/static/index.html`

```html
<!-- 在 <head> 中引入 RTC SDK -->
<script src="https://lf-unpkg.volccdn.com/obj/vcloudfe/sdk/@volcengine/rtc/4.66.1/index.min.js"></script>

<!-- 在主界面添加摄像头区域和对话按钮 -->
<div id="voice-control">
  <button id="btn-start-voice">🎤 开始对话</button>
  <button id="btn-stop-voice" style="display:none">停止对话</button>
  <div id="local-camera"></div>          <!-- 本地摄像头预览 -->
  <div id="ai-status">就绪</div>
  <div id="subtitle"></div>              <!-- AI 说的话 -->
</div>

<script src="voice-room.js"></script>
```

### 5.2 新建 `hmi/static/voice-room.js`

```javascript
/**
 * 火山 RTC 实时对话房间管理
 */
class VoiceRoom {
  constructor() {
    this.engine = null;
    this.roomId = null;
    this.userId = null;
    this.isInRoom = false;
  }

  async start() {
    // 1. 请求后端启动智能体并获取 RTC token
    const resp = await fetch('/api/voice/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({user_id: 'cabin_user_1'}),
    });
    const { room_id, token, user_id, rtc_app_id } = await resp.json();
    this.roomId = room_id;
    this.userId = user_id;

    // 2. 创建 RTC 引擎并加入房间
    this.engine = VERTC.createEngine(rtc_app_id);
    
    // 监听 AI 智能体的语音流（自动播放）
    this.engine.on(VERTC.events.onUserPublishStream, (event) => {
      console.log('[Voice] AI 智能体已加入', event.userId);
    });
    
    // 监听字幕（用于在 HMI 上显示 AI 说的话）
    this.engine.on(VERTC.events.onRoomBinaryMessageReceived, (event) => {
      this._handleBinaryMessage(event.message);
    });
    
    // 加入房间
    await this.engine.joinRoom(token, room_id, { userId: user_id }, {
      isAutoPublish: true,
      isAutoSubscribeAudio: true,
      isAutoSubscribeVideo: true,
    });

    // 3. 开启麦克风采集
    await this.engine.startAudioCapture();
    
    // 4. 开启摄像头采集（可选）
    await this.engine.startVideoCapture();
    const localView = document.getElementById('local-camera');
    this.engine.setLocalVideoPlayer(VERTC.StreamIndex.STREAM_INDEX_MAIN, {
      renderDom: localView,
    });

    this.isInRoom = true;
    document.getElementById('ai-status').textContent = '对话中...';
  }

  async stop() {
    if (!this.isInRoom) return;
    
    await this.engine.stopAudioCapture();
    await this.engine.stopVideoCapture();
    await this.engine.leaveRoom();
    VERTC.destroyEngine(this.engine);
    
    // 通知后端停止智能体
    await fetch('/api/voice/stop', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({room_id: this.roomId}),
    });
    
    this.isInRoom = false;
    document.getElementById('ai-status').textContent = '就绪';
  }
  
  _handleBinaryMessage(buffer) {
    // 字幕、function call 通知等都通过 binary message 来
    try {
      const text = new TextDecoder().decode(buffer);
      const msg = JSON.parse(text);
      if (msg.type === 'subtitle') {
        document.getElementById('subtitle').textContent = msg.text;
      }
      // function call 走的是后端 callback，前端不用处理
    } catch (e) { /* 忽略非 JSON */ }
  }
}

// 全局单例
window.voiceRoom = new VoiceRoom();

document.getElementById('btn-start-voice').onclick = async () => {
  try {
    await window.voiceRoom.start();
    document.getElementById('btn-start-voice').style.display = 'none';
    document.getElementById('btn-stop-voice').style.display = '';
  } catch (e) {
    alert('启动失败：' + e.message);
  }
};
document.getElementById('btn-stop-voice').onclick = async () => {
  await window.voiceRoom.stop();
  document.getElementById('btn-start-voice').style.display = '';
  document.getElementById('btn-stop-voice').style.display = 'none';
};
```

### 5.3 修改 `hmi/static/app.js`

监听后端 WebSocket 推送的 `ai_function_call` 事件：

```javascript
// 在现有 WebSocket onmessage 处理中加入：
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'ai_function_call') {
    // AI 触发了 function call，执行 Unity 操作
    const cmd = data.unity_command;
    if (cmd && window.HMI) {
      window.HMI.sendCommand(cmd);
    }
    // 如果是显示服务卡片
    if (data.tool === 'show_service_card') {
      renderServiceCard(data.args);
    }
  }
  
  // 现有的其他消息处理...
};
```

---

## 六、低延迟关键点

火山的方案天然低延迟，但仍需注意：

### 6.1 后端配置降低延时

在 `LLMConfig` 中：
```json
{
  "prefill": true,        // ASR 中间结果提前送 LLM，降低延时
  "MaxTokens": 1024,      // 限制单次输出，避免长尾延迟
  "Temperature": 0.3      // 降低随机性也微降延迟
}
```

### 6.2 网络要求

- **后端服务器到火山服务器之间**：必须公网可达，国内带宽稳定
- **浏览器到火山 RTC 服务**：自动选择最近的边缘节点，无需配置
- **WebSocket 推送（后端 → 前端）**：尽量在同一个机房

### 6.3 SDK 配置

前端 `joinRoom` 时设置：
```javascript
roomProfileType: VERTC.RoomProfileType.communication,  // 通话模式（最低延迟）
```

### 6.4 视频采样

如果开启视觉理解：
```json
"VisionConfig": {
  "Enable": true,
  "SnapshotInterval": 3   // 截图间隔，越短延迟越敏感，建议 3~5 秒
}
```

---

## 七、Function Calling 详细工作机制

### 7.1 火山如何把工具调用通知到你

**方式 A：HTTP 回调（推荐）** ⭐
- 在 `LLMConfig.FunctionCallingConfig.ServerMessageUrl` 配置回调地址
- 模型决定调用工具时，火山服务器 HTTP POST JSON 到这个地址
- 回调格式：
  ```json
  {
    "ToolCallID": "call_abc123",
    "Name": "switch_camera",
    "Arguments": "{\"view\":\"astronaut\"}",
    "RoomId": "sc_room_user_1_xxx",
    "TaskId": "task_xxx"
  }
  ```

**方式 B：客户端二进制消息**
- 不配置 ServerMessageUrl 的话，火山会通过 RTC 的 `onRoomBinaryMessageReceived` 回调发到客户端
- **不推荐**，因为：1) 需要前端解析二进制；2) 工具结果回传更麻烦

### 7.2 工具结果如何传回（让 AI 接着说话）

```python
# 你的后端收到 function call → 执行操作 → 调 UpdateVoiceChat
await voice_manager.send_tool_result(
    room_id=room_id,
    task_id=task_id,
    tool_call_id="call_abc123",
    result={"status": "success", "message": "视角已切换"}
)
```

**对纯执行类工具（如切视角）**：结果可以是简单的 `{status: "success"}`，模型会自己组织一句"好的，已切换"。

**对查询类工具（如查天气）**：结果要包含数据，模型会基于数据组织回答："上海现在 28 度，比较舒适"。

---

## 八、视频/视觉理解能力

火山 RTC 同时支持音视频流。开启 `VisionConfig.Enable=true` 后：

1. 浏览器摄像头画面通过 RTC 上传到云端
2. 云端按 `SnapshotInterval` 间隔抽帧
3. 帧送给豆包视觉模型理解
4. 模型可以基于视觉信息回答问题

### 用例

- "你看我现在表情怎么样？" → AI 看到摄像头画面，回答"看起来您有点疲劳"
- "我手里拿的是什么？" → 视觉识别 + 语音回答
- 主动检测：用户打哈欠 → AI 主动说"看您有点累，要不要听点提神音乐？"

### 注意

- 视觉理解会**消耗更多 token**，建议 `SnapshotInterval` 设 5 秒以上
- 不需要视觉时**关掉**：`"VisionConfig": {"Enable": false}`

---

## 九、调试与排错

### 9.1 后端调试

启动后端，看 FastAPI 日志：
```
[StartVoiceChat] 调用成功，TaskID=task_xxx
[VoiceCallback] 收到 function call: switch_camera({view:"astronaut"})
```

### 9.2 前端调试

浏览器 F12 Console：
```
[VoiceRoom] joinRoom success
[VoiceRoom] AI agent joined: smart_cockpit_agent
[VoiceRoom] 收到字幕: "好的，正在切换视角"
```

### 9.3 常见问题

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| `getUserMedia` undefined | 不是 https 也不是 localhost | 改用 https，或确保 localhost 测试 |
| Invalid Authorization | RTC 签名错误 | 检查 RTC AppKey、UTC 时间 |
| 智能体不进房间 | StartVoiceChat 报错 | 检查 VOICE_APP_ID、AccessToken |
| function call 没回调 | callback URL 不可达 | 用 cpolar 等穿透 |
| AI 说但是听不到 | RTC token 错误 / autoSubscribe 没开 | 检查 joinRoom 配置 |
| 延迟很高 | 网络问题 / 配置不对 | 看上面"低延迟关键点"章节 |

---

## 十、给 Claude Code 的实施步骤建议

### 阶段 1：后端能调通火山 API（1~2 天）

- [ ] 安装依赖（volcengine-python-sdk、httpx）
- [ ] 实现 `realtime_voice.py` 的 `start_agent` 方法（含签名）
- [ ] 用 Postman/curl 测试 `/api/voice/start` 能成功启动智能体
- [ ] 火山控制台监控页能看到智能体已启动

### 阶段 2：前端能加入 RTC 房间（1 天）

- [ ] 引入 RTC SDK
- [ ] 实现 `voice-room.js` 加入房间逻辑
- [ ] 浏览器麦克风、摄像头能采集
- [ ] 能听到 AI 智能体说话（先用默认 prompt 测试）

### 阶段 3：Function Calling 联通（2~3 天）

- [ ] 部署后端服务，让火山能回调 `/voice-callback`（用 cpolar 等内网穿透）
- [ ] 注册 5 个 HMI 工具 schema
- [ ] 测试用户语音指令能触发工具调用
- [ ] 工具调用通过 WebSocket 推到前端 → window.HMI 执行

### 阶段 4：体验打磨（持续）

- [ ] 调试 SystemRole prompt（让 AI 风格符合车载场景）
- [ ] 调试 SnapshotInterval（视觉理解的频率）
- [ ] 调试 InterruptMode（打断的灵敏度）
- [ ] 添加错误处理、断线重连

---

## 十一、参考链接

- 实时对话式 AI 场景介绍：https://www.volcengine.com/docs/6348/1310537
- StartVoiceChat OpenAPI：https://www.volcengine.com/docs/6348/1404673
- Function Calling 配置：https://www.volcengine.com/docs/6348/1359441
- Web SDK 文档：https://www.volcengine.com/docs/6348/106914
- 端到端语音模型接入：https://www.volcengine.com/docs/6348/1581712
- RTC AIGC Demo（GitHub）：https://github.com/volcengine/rtc-aigc-demo

---

## 十二、对 Claude Code 的特别提醒

1. **不要破坏现有功能**：原 `microphone_asr.py`、`speaker_tts.py`、`service_agent.py` 全部保留，新功能并行存在，不要重写
2. **先做后端再做前端**：后端能 curl 通过再写前端
3. **签名是难点**：调用火山 OpenAPI 需要 V4 签名，**直接用 `volcengine-python-sdk` 的 `Service` 类，不要手写**
4. **本地开发必须公网穿透**：cpolar / ngrok / frp 三选一，否则 function call 回调收不到
5. **写代码先测最小路径**：能进房间 + 能听到 AI 说话 → 再加工具调用 → 再加视觉。不要一步到位
6. **凭证不要硬编码**：全部从 `.env` 读
7. **新依赖别忘了加到 requirements.txt**

---

文档完成。请按"阶段 1 → 4"顺序实施，每个阶段做完跟用户确认效果再进入下一阶段。
