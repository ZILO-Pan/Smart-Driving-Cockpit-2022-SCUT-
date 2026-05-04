# Unity WebGL 集成任务清单

> 给 Claude Code 的实施任务说明
> 项目：SMART_COCKPIT（智慧驾驶座舱·端云协同多模态主动服务系统）
> 目标：把已经 Build 完成的 Unity WebGL 场景嵌入到现有 HMI 前端，并打通 AI 语音助手 → JSON 指令 → Unity 控制的完整链路

---

## 背景

本项目已有完整的端云协同架构：

- **后端 (Edge)**：`edge/hmi_server/server.py` 是 FastAPI + WebSocket 服务，已经在 serve 静态前端 `hmi/static/`
- **前端 (HMI)**：`hmi/static/index.html` 是 3840×590 超宽屏界面，已经通过 WebSocket 接收后端推送的状态
- **云端 AI**：`cloud/agent/service_agent.py` 是结构化 JSON 输出的服务编排 Agent，由豆包大模型驱动

现在需要**把 Unity WebGL 3D 场景集成进来**，并扩展 AI Agent 让它能控制这个 3D 场景。

---

## 已完成的事（不需要重做）

1. ✅ Unity WebGL 已 Build 完成，产物在 `D:\AI4HMI\Build\`（用户会复制到 hmi/static/unity/ai-car-scene/）
2. ✅ Unity 内部所有交互都已通过统一的 JSON 协议暴露
3. ✅ 完整的 API 文档在 `docs/HMI_API_Reference.md`
4. ✅ WebGL 集成参考指南在 `docs/WebGL_Integration_Guide.md`

---

## 你要做的事（按顺序）

### 阶段 1：让 FastAPI 正确 serve Unity WebGL 文件

**问题：** Unity Build 产物中的 `.gz` 文件需要服务器返回 `Content-Encoding: gzip` header，否则浏览器无法解析。

**任务：**
1. 阅读 `edge/hmi_server/server.py`，了解现有静态文件挂载方式
2. 添加专门的中间件或路由处理 `/unity/` 路径下的 `.gz` 文件，正确设置：
   - `.framework.js.gz` → `Content-Type: application/javascript` + `Content-Encoding: gzip`
   - `.wasm.gz` → `Content-Type: application/wasm` + `Content-Encoding: gzip`
   - `.data.gz` → `Content-Type: application/octet-stream` + `Content-Encoding: gzip`
3. 不要破坏现有的其他静态文件 serve 逻辑

**验证：** 启动后端，浏览器 F12 → Network 检查 `framework.js.gz` 的响应头有 `Content-Encoding: gzip`

---

### 阶段 2：在 HMI 前端嵌入 Unity canvas

**任务：**
1. 在 `hmi/static/unity/ai-car-scene/` 目录下放好 Unity Build 产物（用户会自己复制）
2. 修改 `hmi/static/index.html`：
   - 在合适的位置（README 中提到的 "Unity 预留区"）添加一个 `<canvas id="unity-canvas">`
   - 加载遮罩（loading mask）盖住 Unity 默认 logo
   - 引入 `Build/AI4HMI.loader.js`
3. 创建 `hmi/static/unity-bridge.js`：
   - 用 `createUnityInstance()` 加载 Unity，绑定到 canvas
   - 暴露全局对象 `window.HMI`，包含以下方法（参考 `docs/WebGL_Integration_Guide.md` 第 2.2 节）：
     - `switchCamera(view)` - view 是 default/astronaut/carExterior/carInterior
     - `togglePart(partId)` - 切换部件开关
     - `openPart(partId)` / `closePart(partId)` - 明确开/关
     - `rotateCarTo(angle)` / `rotateCarBy(angle)` / `resetCarRotation()` - 车的旋转
     - `getState()` - 查询 Unity 状态
   - 实现 `window.OnUnityEvent(jsonStr)` 函数接收 Unity 发回的事件
   - 创建 `window.HMIBus` 事件总线，让其他模块能订阅 Unity 事件
4. 在 `hmi/static/app.js` 里集成 `window.HMI` 调用（按需）

**关键 CSS：**
```css
#unity-canvas {
  touch-action: none;          /* 必须！防止浏览器手势冲突 */
  -webkit-user-select: none;
  user-select: none;
}
```

**验证：**
- 浏览器打开 HMI，能看到 Unity 加载进度，加载完显示太空场景
- F12 控制台执行 `HMI.switchCamera("astronaut")` 能切视角
- F12 控制台执行 `HMI.getState()` 能在 Console 看到状态快照事件

---

### 阶段 3：扩展 AI Agent，让它能控制 Unity

**任务：**
1. 阅读 `cloud/agent/service_agent.py` 现有实现
2. 把 `docs/HMI_API_Reference.md` 中"推荐的 AI System Prompt 模板"那一节，**合并**到现有的服务 Agent system prompt 里
   - 不要替换原有 prompt，只是**追加** Unity 控制能力的描述
3. 扩展 Agent 的输出 JSON schema，让它**除了原有的服务编排指令外**，还能输出 `unityCommand` 字段：
   ```json
   {
     "tts": "好的，正在切换到车外视角",
     "unityCommand": {
       "action": "switchCamera",
       "target": "carExterior"
     },
     "service_card": null
   }
   ```
4. 在 Edge 端（FastAPI WebSocket handler）处理 Agent 返回，如果包含 `unityCommand`，通过 WebSocket 推给前端
5. 前端 `app.js` 收到 WebSocket 消息后，如果有 `unityCommand`，调用 `window.HMI.sendCommand(...)`

**验证：**
- 用户说"我想看看车" → Agent 输出 unityCommand 切到 carExterior 视角，TTS 念出"好的"
- 用户说"打开车门" → Agent 先确认视角，再输出 togglePart 指令
- AI 决策时能感知 Unity 当前状态（通过订阅 stateSnapshot 事件）

---

### 阶段 4：测试与验证

写一个简单的测试页面或测试按钮，覆盖以下场景：

- [ ] Unity 加载成功，能看到 3D 场景
- [ ] 鼠标点击 Unity canvas 内的物体能正确响应（宇航员、车）
- [ ] HTML 端按钮调用 `HMI.switchCamera()` 等方法能控制 Unity
- [ ] Unity 的状态变化（如车门打开）能通过事件通知到 HTML
- [ ] 通过语音触发的 AI 指令能控制 Unity（端到端）
- [ ] 触屏交互不与浏览器手势冲突（需在触屏设备上测）

---

## 重要原则

### 必须遵守

1. **不要修改 Unity Build 产物**：`hmi/static/unity/ai-car-scene/Build/` 里的文件是 Unity 编译输出，不是前端代码
2. **不要破坏现有功能**：CARLA bridge、WebSocket 推送、TTS/ASR、服务卡片等现有逻辑必须照常工作
3. **保持架构一致性**：Unity 控制走和现有 service_agent 一样的"AI 输出 JSON → WebSocket 转发 → 前端执行"链路，不要为 Unity 单独搞一套
4. **向后兼容**：未启用 Unity 时（比如开发阶段），HMI 应该照常工作

### 应该做

1. **加载性能**：Unity 文件很大（几十 MB），第一次加载慢是正常的，加载遮罩要做好
2. **错误处理**：Unity 加载失败时，HMI 其他部分仍可用，加载错误要在 console 清晰打印
3. **延迟加载**：可以考虑用户进入特定场景时才 `createUnityInstance`，节省首屏时间（但不强制）

### 不要做

1. **不要用 iframe 嵌入 Unity**：性能差且通信麻烦
2. **不要给 Unity 单独起一个 HTTP 服务**：FastAPI 已经能 serve 静态文件
3. **不要在 Unity 加载完成前调用 `unityInstance.SendMessage`**：会报错
4. **暂时不要接 CARLA 数据到 Unity**：先把基础链路跑通，CARLA→Unity 是后续阶段

---

## 参考文档

- `docs/HMI_API_Reference.md` - Unity 能接受的所有 JSON 指令、能发出的所有事件、AI system prompt 模板
- `docs/WebGL_Integration_Guide.md` - HTML 嵌入示例代码、配置注意事项、常见问题排查
- `README.md` - 项目整体架构

---

## 实施前请确认

请先告诉我：

1. 你的实施计划（你打算先做哪一步？）
2. 你需要我提供什么额外信息？
3. 有没有看到我上面任务描述里不清楚的地方？

确认后再开始改代码。
