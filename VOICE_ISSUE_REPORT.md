# NOVA 语音控制问题排查报告

## 当前症状

**Bot 加入房间后只说一次 WelcomeMessage（"你好，我是NOVA"），之后无论用户说什么都不回复。**

- `StartVoiceChat` API 返回 `"Result": "ok"` HTTP 200
- Bot 成功加入 RTC 房间（前端收到 `onUserJoined` 事件）
- 浏览器麦克风已开启，音频正在发布到房间
- 没有任何错误日志

## 根因定位

经逐步排查确认：**LLMConfig.Tools 数量/大小超限时，S2S 语音管线静默失败。**

| 配置 | 结果 |
|------|------|
| 纯 S2S（OutputMode=0，无 LLMConfig） | 能说话 |
| OutputMode=1 + LLMConfig（无 Tools） | 能说话 |
| OutputMode=1 + LLMConfig + 5 个 Tools | 能说话 + FC 正常触发 |
| OutputMode=1 + LLMConfig + 10 个 Tools | 不说话 |
| OutputMode=1 + LLMConfig + 17 个 Tools | 不说话 |
| OutputMode=1 + LLMConfig + 21 个 Tools | 不说话 |

## 技术细节

### API 配置

```
URL: https://rtc.volcengineapi.com?Action=StartVoiceChat&Version=2024-12-01
签名: V4 HMAC-SHA256（已确认通过）
```

### 关键参数

```json
{
  "S2SConfig": {
    "Provider": "volcano",
    "OutputMode": 1,
    "ProviderParams": {
      "app": { "appid": "S2S_APP_ID", "token": "S2S_ACCESS_TOKEN" },
      "dialog": { "bot_name": "NOVA", "extra": { "model": "1.2.1.1" } }
    }
  },
  "LLMConfig": {
    "Mode": "ArkV3",
    "EndPointId": "ep-20260316012441-lwsjl",
    "SystemMessages": ["..."],
    "MaxTokens": 256,
    "Temperature": 0.1,
    "Tools": [...]  // <-- 超过5个就不说话
  }
}
```

### Payload 大小估算

- 5 个工具 JSON 约 2KB → 正常
- 10 个工具 JSON 约 4KB → 静默失败
- 21 个工具 JSON 约 8KB → 静默失败

## 需要解决的问题

**如何在火山 RTC S2S 的工具限制下，实现完整的 HMI 语音控制（约 15-20 个操作）？**

## 可能的解决方向

### 方向 1：确认是大小限制还是数量限制
- 试 5 个工具但把 description 写得很长（测试是否为 payload 字节数限制）
- 试 10 个工具但全部极简（无 description，无 enum）

### 方向 2：万能工具模式
AI 只注册一个工具 `execute_action(action, params)`，后端根据 action 路由：
```json
{
  "name": "execute_action",
  "parameters": {
    "action": "string (e.g. open_car_part, set_ac_temperature...)",
    "params": "object"
  }
}
```
优点：只有 1 个工具定义，payload 极小。
缺点：AI 需要 prompt 告诉它有哪些 action，参数类型没有 schema 约束。

### 方向 3：工具合并
将 21 个工具合并为 5 个（如 `cabin_control`, `panel_control`, `car_3d_control` 等），每个工具内用 action 字段区分具体操作。需要前后端做映射层。

### 方向 4：联系火山技术支持
询问 RTC VoiceChat 的 Tools 数量/payload 大小限制，是否有文档说明或配额提升方式。

## 当前代码状态（commit 07b3a6e）

工具数限制为 10 个（但实测可能只有 5 个能跑）：
1. set_ac_temperature
2. set_seat_ventilation
3. toggle_window
4. set_ambient_light
5. play_music
6. set_cabin_mode
7. set_destination
8. open_service_card
9. open_car_part
10. close_car_part

## FC 数据流

```
用户说话
  ↓ (RTC 音频)
火山 S2S 端到端模型 (语音理解 → LLM 决策 → 生成 tool_calls)
  ↓ (RTC binary message)
voice.js 解析 binary message
  ├──→ app.js._executeFCAction(funcName, args) → HMI 立即执行
  └──→ POST /api/voice/fc-execute → voice_api.py → UpdateVoiceChat → AI 继续说话
```

## 关键文件

| 文件 | 职责 |
|------|------|
| `cloud/voice/rtc_service.py` | _get_tools_definition() + start/stop/update_voice_chat |
| `edge/hmi_server/voice_api.py` | FC 执行 + UpdateVoiceChat 异步回传 |
| `hmi/static/voice.js` | 前端解析 binary message + 调 _executeFCAction |
| `hmi/static/app.js` | _executeFCAction() 实际操作 HMI |
| `config/settings.py` | NOVA_SYSTEM_PROMPT |
