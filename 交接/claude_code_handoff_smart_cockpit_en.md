# Claude Code Handoff: Integrated Smart Driving Cockpit MVP

## 1. Project Goal

Repository:

https://github.com/ZILO-Pan/Smart-Driving-Cockpit-2022-SCUT-

Graduation design topic:

**Cloud-Edge Collaborative Multimodal Proactive Smart Cockpit Service System For Integrated Cockpit-Driving Scenarios**

Chinese title:

**《面向舱驾一体场景的端云协同多模态智能座舱主动服务系统设计研究》**

The immediate goal is a runnable MVP demo, not final visual polish.

The target system:

- CARLA represents the driving side.
- HTML is the primary HMI.
- HMI target size is **3840 x 590** ultra-wide.
- Volcengine/Doubao provides cloud intelligence: speech, dialogue, multimodal understanding, and service orchestration.
- Edge-side modules execute CARLA control, HMI rendering, cabin state management, safety policy, and simulated services.
- Unity is no longer the primary HMI runtime. Unity should only be reserved as a future WebGL visualization module embedded inside the HTML page.

## 2. Architecture Correction

The current repository contains a TCP-to-Unity native client skeleton. This was useful for the old plan, but it should not be the primary architecture anymore.

### Old Plan

```text
Python/CARLA -> TCP -> Native Unity client -> all HMI inside Unity
```

### New Plan

```text
Python/CARLA/FastAPI -> HTTP/WebSocket -> HTML HMI
                                      -> JS Bridge -> Unity WebGL visualization module
```

Conclusion:

- TCP-to-Unity is no longer the primary HMI link.
- Keep TCP only as a legacy/native Unity adapter if desired.
- Unity WebGL runs in the browser and should not rely on normal raw TCP sockets.
- The HTML HMI should connect to the backend through REST/WebSocket.
- Future Unity WebGL should receive state from the parent HTML page through JavaScript bridge, `postMessage`, or Unity WebGL `SendMessage`.

For the first MVP, only create a visible `Unity WebGL / ADS Visualization Slot`. Do not implement Unity WebGL yet.

## 3. Dual-Screen Demo Mode

User hardware context:

- One PC connected to two displays.
- Display 1: CARLA driving simulation.
- Display 2: HTML smart cockpit HMI.
- HMI target resolution: **3840 x 590**.

The system must support CARLA and HMI running in parallel.

Recommended demo setup:

```text
Display 1: CARLA / pygame preview / Unreal simulation window
Display 2: Chrome/Edge at http://localhost:8080 in fullscreen mode
```

Startup modes:

```bash
python main.py --web-hmi
python main.py --web-hmi --no-ai
python main.py --web-hmi --mock-carla
python main.py --hmi-only
```

Implementation requirements:

- `main.py --web-hmi` must start the web HMI server and then enter the CARLA loop, or run CARLA/web services in separate threads.
- The HMI server must not be blocked by CARLA's main loop.
- If CARLA is not running, the HMI must still work with mock state.
- The demo must allow CARLA and HMI to be displayed on different monitors.

## 4. Current Repository Understanding

- `main.py`
  - Starts `VehicleStateManager`, `CarlaBridge`, `TCPServer`, `AssistantManager`, and `UnityDataProvider`.
  - Currently enters blocking `carla_bridge.run()`.

- `config/settings.py`
  - Contains CARLA, TCP, Ark, ASR, TTS, microphone, and vision settings.
  - API credentials are currently hardcoded and must be moved to `.env`.

- `core/carla_bridge.py`
  - Connects to CARLA.
  - Spawns Tesla Model 3, NPC vehicles, pedestrians, and cameras.
  - Supports scene switching with keys `1` to `8`.
  - Supports chaos event with key `C`.
  - Updates `VehicleStateManager`.
  - Provides `get_latest_frame()` for vision analysis.

- `core/vehicle_state.py`
  - Defines vehicle speed, throttle, brake, steer, position, rotation, wheel angle, and autopilot state.

- `communication/tcp_server.py`
  - Legacy native Unity TCP server.
  - Keep it optional, but do not use it as the main HTML HMI link.

- `ai_assistant/assistant_manager.py`
  - Current chained assistant: ASR -> Doubao chat -> TTS.
  - Also supports CARLA screenshot -> Doubao vision -> TTS broadcast.

- `ai_assistant/doubao_chat.py`
  - Calls Volcengine Ark `chat/completions`.
  - Supports text and image input.
  - Needs structured service orchestration.

- `ai_assistant/microphone_asr.py`
  - Volcengine big model ASR WebSocket.

- `ai_assistant/speaker_tts.py`
  - Volcengine TTS WebSocket + pygame playback.

## 5. Required Security Fix

The current public repository contains Volcengine credentials in `config/settings.py`. Treat them as compromised.

Required:

1. Add `.env.example`.
2. Add `.env` to `.gitignore`.
3. Load settings from environment variables.
4. Never print secrets.
5. Show clear errors when required env vars are missing.
6. Tell the user to rotate credentials in the Volcengine console.

Suggested env vars:

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

## 6. Official References

### Volcengine / Doubao

- Intelligent cockpit solution  
  https://www.volcengine.com/docs/82379/1263275

- Doubao end-to-end realtime speech model  
  https://www.volcengine.com/docs/6561/1594360

- Realtime audio/video AI interaction guide  
  https://www.volcengine.com/docs/6348/1350595

- Function Calling for realtime audio/video AI  
  https://www.volcengine.com/docs/6348/1554654

- End-to-end realtime voice RTC integration  
  https://www.volcengine.com/docs/6348/1902994

### Qwen / Local Models

- Qwen3.6  
  https://github.com/QwenLM/Qwen3.6  
  https://qwen.ai/blog?id=qwen3.6-35b-a3b

- Qwen2.5-Omni  
  https://github.com/QwenLM/Qwen2.5-Omni

- Qwen3-Omni  
  https://github.com/QwenLM/Qwen3-Omni

Do not block the MVP on local Qwen. The user has RTX 4060 Laptop GPU with 8GB VRAM and 64GB RAM. Qwen3-4B/8B GGUF can be a reserved edge fallback or thesis extension.

## 7. Final System Positioning

This is not a normal in-car voice assistant. It is:

**A cloud-edge collaborative multimodal proactive service prototype for integrated cockpit-driving scenarios.**

Cloud side:

- Doubao natural language understanding.
- Complex intent reasoning.
- Multimodal/image understanding.
- Service orchestration.
- ASR/TTS or future end-to-end realtime speech.

Edge side:

- CARLA control.
- HTML HMI rendering.
- Vehicle/cabin state management.
- Simulated or lightweight user-state sensing.
- Service execution.
- Safety confirmation policy.
- Reserved local Qwen fallback.

Core loop:

```text
multimodal input
-> user state and driving context
-> LLM/Agent reasoning
-> service orchestration
-> cockpit/driving/local-life actions
-> HMI + speech feedback
```

## 8. The 11 Functions

All 11 functions must be visible in the 3840 x 590 HMI.

1. Natural voice conversation.
2. Fuzzy intent understanding.
3. Proactive service recommendation.
4. Multimodal state awareness.
5. Cockpit-driving integrated linkage.
6. Cloud-edge collaborative architecture.
7. Explainable HMI feedback.
8. Simulated cockpit control.
9. Voice control of CARLA driving tasks.
10. Local-life service cards.
11. Lightweight semantic mapping knowledge base / RAG.

## 9. New Modules To Add

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

## 10. HMI Design: 3840 x 590

No landing page. The first screen is the actual cockpit.

Recommended layout:

```text
3840 x 590

top status strip
left vehicle cluster | center navigation/ADS/WebGL slot | right AI/service panel
bottom function dock with 11 features and demo buttons
```

Required:

- Vehicle speed, gear, autopilot, steering angle.
- Destination, route status, CARLA command status.
- Assistant state, dialogue, intent, confidence, actions.
- User state chips.
- Cabin control states.
- Service cards: flight, milk tea, news, video.
- 11 function entries.
- `Unity WebGL / ADS Visualization Reserved` slot.

## 11. Unity WebGL Reserved Plan

First MVP:

- Place a visible WebGL placeholder container in HTML.
- Show mock ADS/vehicle visualization inside it.

Future integration:

```text
FastAPI/WebSocket -> HTML app.js -> Unity WebGL JS bridge -> Unity C# scripts
```

Do not make Unity WebGL connect directly to the old TCP server.

Suggested bridge:

```javascript
unityInstance.SendMessage("CockpitBridge", "OnVehicleState", JSON.stringify(state));
unityInstance.SendMessage("CockpitBridge", "OnServiceAction", JSON.stringify(action));
```

## 12. Demo Scenarios

- "好热啊" -> thermal comfort service.
- "我有点难过" / "好无聊" -> emotion/entertainment service.
- Fatigue toggle + high speed -> proactive rest recommendation.
- "帮我换到左车道" -> CARLA driving command.
- "去机场" -> destination/route update.
- "帮我订一张去上海的机票" -> mock flight card.
- "我想喝奶茶" -> mock milk tea card.
- "看一下今天新闻" -> mock news card.
- "刷会儿视频" -> mock video card.

## 13. Service Agent Output

The model must output strict JSON only.

Allowed actions:

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

Allowed intents:

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

Risk-sensitive driving actions require confirmation by default.

## 14. Implementation Order

1. Security/config cleanup.
2. Cabin state and service executor.
3. Service agent and lightweight semantic knowledge base.
4. FastAPI web HMI.
5. Dual-screen parallel launch.
6. CARLA driving commands.
7. Volcengine structured orchestration.
8. HMI visual polish.

## 15. Acceptance Criteria

First MVP passes when:

1. `python main.py --web-hmi` starts successfully.
2. `http://localhost:8080` shows the HMI.
3. HMI fits 3840 x 590.
4. HMI can run fullscreen on the second display.
5. CARLA can run on the first display.
6. HMI does not depend on Unity.
7. Unity WebGL reserved slot is visible.
8. All 11 functions are visible.
9. Five core demo commands produce visible state changes.
10. CARLA real state flows into HMI when available.
11. Mock state works when CARLA is unavailable.
12. ASR/TTS/Doubao chain is not broken.
13. Secrets are not hardcoded.

## 16. Do Not Do In First Pass

- Do not put the whole HMI back into Unity.
- Do not make Unity WebGL use the old TCP server.
- Do not integrate real payment or external service login.
- Do not deploy heavy local Omni/voice models as the main path.
- Do not train models.
- Do not rewrite the entire CARLA bridge.
- Do not hide AI actions only in chat. Make them explainable in the HMI.

## 17. Final Demo Feeling

The final first-stage demo should show:

- CARLA running on one display.
- Ultra-wide smart cockpit HMI on the second display.
- The assistant understands fuzzy user needs.
- The assistant proactively recommends services.
- HMI shows intent, context, actions, and execution.
- CARLA commands can be triggered by voice/text.
- Local-life cards open as simulated service panels.
- Unity WebGL is visibly reserved for future ADS/3D visualization.
