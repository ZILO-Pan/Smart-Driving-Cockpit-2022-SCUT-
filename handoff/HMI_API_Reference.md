# HMI Unity 场景控制 API 参考

> **用途：** 这份文档描述了 Unity HMI 场景能接收的所有 JSON 指令，以及它会发出的所有事件。
> AI 语音助手通过把用户的自然语言意图翻译成对应的 JSON 指令，发送给 Unity 来控制 3D 场景。
>
> **场景描述：** 一个太空主题的 HMI 待机/交互画面，包含一个浮动的宇航员、火星、跑车，以及缓慢旋转的星空。
> 用户可以触摸屏直接交互，也可以通过 AI 语音助手发起同样的操作。

---

## 一、通信协议

### 输入：JSON 指令（HTML → Unity）

格式统一为：

```json
{
  "action": "动作名称",
  "target": "目标标识",
  "paramsJson": "参数JSON字符串（可选）"
}
```

**注意：** `paramsJson` 是一个**字符串**（不是嵌套对象），里面再放 JSON。这是 Unity 的 JsonUtility 的限制。

调用方式（HTML 端）：

```javascript
unityInstance.SendMessage("HMIController", "ExecuteCommand", JSON.stringify(command));
```

### 输出：JSON 事件（Unity → HTML）

Unity 通过调用 `window.OnUnityEvent(jsonStr)` 把事件传回 HTML。事件格式：

```json
{
  "eventType": "事件类型",
  "target": "目标标识",
  "detail": "附加信息（字符串或嵌套JSON）",
  "timestamp": 1700000000000
}
```

HTML 端要实现 `window.OnUnityEvent` 函数来接收：

```javascript
window.OnUnityEvent = function(jsonStr) {
  const evt = JSON.parse(jsonStr);
  // 处理事件
};
```

---

## 二、可用动作清单（AI 可发送的指令）

### 2.1 视角切换

#### `switchCamera` — 切换到指定视角

| 字段 | 值 |
|------|-----|
| action | `switchCamera` |
| target | `default` / `astronaut` / `carExterior` / `carInterior` |

**视角说明：**
- `default` — 默认全景视角，能看到宇航员、火星、跑车的整体构图（场景待机状态）
- `astronaut` — 推近到宇航员面部的近景视角
- `carExterior` — 车外视角，可以围观跑车
- `carInterior` — 车内驾驶座视角，看到内饰

**示例：**

```json
{"action":"switchCamera","target":"astronaut"}
{"action":"switchCamera","target":"default"}
```

**行为：**
- 摄像机用 1.2 秒丝滑过渡到目标视角（缓动曲线）
- 切换时车身浮动会自动停下（在 carExterior/carInterior 下）
- 切换回默认视角时，车浮动恢复
- 过渡中重复调用会被忽略

---

#### `resetCamera` — 复位到默认视角

等价于 `switchCamera + target=default`，提供给 AI 一个更直观的指令名。

```json
{"action":"resetCamera"}
```

---

### 2.2 车的部件控制（车门/引擎盖/后备箱/车窗）

#### `togglePart` — 切换部件开关状态

| 字段 | 值 |
|------|-----|
| action | `togglePart` |
| target | `doorL` / `doorR` / `hood` / `trunk` / `windowL` / `windowR` |

**目标说明：**
- `doorL` — 左车门
- `doorR` — 右车门
- `hood` — 引擎盖
- `trunk` — 后备箱
- `windowL` — 左车窗（向下移开窗）
- `windowR` — 右车窗

**示例：**

```json
{"action":"togglePart","target":"doorL"}
```

**行为：**
- 0.6~0.8 秒的丝滑开关动画
- 仅在 `currentView === "carExterior"` 时生效
- 在其他视角下调用，会发出 `partInteractionBlocked` 事件

---

#### `openPart` / `closePart` — 明确指定开/关

如果 AI 已知部件状态，可以发明确的开/关指令：

```json
{"action":"openPart","target":"doorL"}
{"action":"closePart","target":"hood"}
```

如果状态已经是目标状态（已开/已关），指令会被忽略，不会重复动画。

---

### 2.3 车的旋转控制

#### `rotateCar` — 旋转车身

车的旋转有 3 种用法：

**(a) 转到绝对角度**

| 字段 | 值 |
|------|-----|
| action | `rotateCar` |
| target | `absolute` |
| paramsJson | `{"angle":90}` （-180 到 180 度）|

```json
{"action":"rotateCar","target":"absolute","paramsJson":"{\"angle\":90}"}
```

**含义：**
- `angle=0` 是车的初始正面
- `angle=90` 顺时针 90 度（侧面）
- `angle=180` 反向（背面）
- `angle=-90` 逆时针 90 度（另一侧）

**(b) 相对当前旋转**

```json
{"action":"rotateCar","target":"relative","paramsJson":"{\"angle\":-30}"}
```

含义：在当前角度基础上再转 -30 度。

**(c) 复位**

```json
{"action":"rotateCar","target":"reset"}
```

转回到 0 度。

**行为：**
- 默认 1 秒丝滑动画
- 走最短路径（不会绕远路）
- 仅当 `currentView === "carExterior"` 时操作直观可见
- 用户用手指拖动会立刻打断 AI 动画
- 完成后发 `carRotationComplete` 事件

---

### 2.4 状态查询

#### `getState` — 查询场景所有当前状态

```json
{"action":"getState","target":"all"}
```

**Unity 会返回 `stateSnapshot` 事件**，detail 字段是序列化的状态快照：

```json
{
  "eventType": "stateSnapshot",
  "target": "all",
  "detail": "{\"currentView\":\"carExterior\",\"isTransitioning\":false,\"carRotationAngle\":45.0,\"partIds\":[\"doorL\",\"doorR\",\"hood\",\"trunk\",\"windowL\",\"windowR\"],\"partOpenStates\":[true,false,false,false,false,false]}",
  "timestamp": 1700000000000
}
```

解析 detail 可得：
- `currentView` — 当前视角名
- `isTransitioning` — 是否在过渡中
- `carRotationAngle` — 车的当前旋转角度（-180 ~ 180）
- `partIds` 和 `partOpenStates` — 各部件的开关状态（一一对应）

---

## 三、Unity → HTML 的事件清单

下面这些事件 Unity 会主动发给 HTML，AI 助手可以监听以了解场景实时状态：

| eventType | target 字段 | detail 字段 | 触发时机 |
|-----------|------------|------------|---------|
| `cameraTransitionStart` | 目标视角名 | `""` | 开始切换视角 |
| `cameraTransitionEnd` | 目标视角名 | `""` | 切换完成 |
| `partOpened` | 部件 id | `""` | 部件开启动画完成 |
| `partClosed` | 部件 id | `""` | 部件关闭动画完成 |
| `partInteractionBlocked` | `""` | `currentView=xxx` | 在错误视角下尝试操作部件 |
| `carRotationComplete` | `""` | 角度（字符串）| 车旋转动画完成 |
| `stateSnapshot` | `all` | 状态快照 JSON | 响应 getState 查询 |
| `error` | 错误类型 | 错误详情 | 任何错误 |

---

## 四、设计约束（AI 必须知道）

1. **视角是分层的**：`default` ↔ `astronaut`、`default` ↔ `carExterior` ↔ `carInterior`。
   AI 可以从任何视角直接跳到任何视角，过渡是丝滑的。

2. **车部件操作必须在 carExterior 视角下**。如果当前不在该视角，应该先 `switchCamera` 切过去再操作。
   AI 可以选择：
   - 自动连续发指令（先切视角再操作）
   - 或者向用户确认（"需要我先切到车外视角吗？"）

3. **过渡中调用会被忽略**。建议监听 `cameraTransitionEnd` 事件再发下一条指令；或者通过 `getState` 检查 `isTransitioning`。

4. **车窗有特殊性**：车窗下移后看起来"消失"了，但点击区域是固定的代理（用户看不见但能点）。AI 调用 `togglePart windowL` 不受这个影响，永远能正常切换。

5. **手势和 AI 同时存在**：用户的手指拖动可以打断 AI 触发的动画。AI 不需要做特殊处理，Unity 会自动处理冲突。

---

## 五、推荐的 AI System Prompt 模板

下面是建议给 AI 助手的 system prompt 片段（可以基于这个改）：

```
你是一个车载 HMI 智能助手，可以通过 JSON 指令控制一个 Unity 3D 场景。
场景包含：浮动的宇航员、火星、跑车，以及星空背景。

【你能做的事】
1. 切换视角：default(默认)、astronaut(看宇航员)、carExterior(看车外)、carInterior(车内)
2. 控制车的部件：开关左右车门、引擎盖、后备箱、左右车窗
3. 旋转车身查看不同角度
4. 查询场景当前状态

【操作规则】
- 控制车部件前，必须先确保在 carExterior 视角
- 用户可能用自然语言要求（"打开车门"、"我想看看车的另一边"），你需要把意图翻译成 JSON
- 如果操作需要多步（比如"看看车内"需要先切 exterior 再切 interior），你应该一步步来，等每步完成事件再发下一步
- 用户用手指操作时，你也能感知到（通过事件流），不要重复执行

【指令格式】
所有指令都是这种结构：
{"action":"...", "target":"...", "paramsJson":"..."}

【可用动作】
- switchCamera(target=default/astronaut/carExterior/carInterior)
- togglePart(target=doorL/doorR/hood/trunk/windowL/windowR)
- openPart, closePart（明确指定）
- rotateCar(target=absolute/relative/reset, paramsJson={"angle":N})
- getState(target=all) — 查询当前状态

【典型场景】
用户："让我看看这辆车"
你：发送 switchCamera→carExterior

用户："打开车门"
你：先确认视角是 carExterior，然后 togglePart→doorL（或 doorR，看用户上下文）

用户："换个角度看"
你：发送 rotateCar→relative，angle=90

用户："回到原来"
你：发送 resetCamera 或 rotateCar→reset
```

---

## 六、版本

- **API 版本**：v1.0
- **对应 Unity 项目**：HMI Demo Unity 2022.3 LTS
- **最后更新**：根据当前脚本 `HMIController.cs` v2 / `CarSelfRotation.cs` v2
