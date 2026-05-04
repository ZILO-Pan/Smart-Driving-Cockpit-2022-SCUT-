# Unity WebGL 嵌入与集成指南

> **用途：** 这份文档描述了 Unity HMI 场景从 Build 到嵌入 HTML 页面、再到与 AI 语音助手对接的完整流程。
> 这是给开发者（你或 Claude Code）的实操参考。

---

## 一、Unity 端：Build WebGL

### 1.1 Build 前检查

在 Unity 编辑器里确认这些设置（**File → Build Settings → Player Settings → WebGL Tab**）：

| 配置项 | 推荐值 | 原因 |
|-------|-------|------|
| Color Space | Linear | 画质显著优于 Gamma |
| Graphics APIs | 仅 WebGL 2.0 | 1.0 不支持 Linear |
| IL2CPP Code Generation | Faster runtime | 运行性能优先 |
| Compression Format | **Gzip** | 必须！Brotli 在本地测试有问题 |
| Decompression Fallback | 不勾选 | 减小体积 |
| Default Canvas Width | 3840 | 匹配目标 HMI 分辨率 |
| Default Canvas Height | 590 | 同上 |
| Run In Background | 勾选 | HMI 持续运行 |

### 1.2 Build 操作

1. **File → Build Settings**
2. Platform 选 **WebGL**
3. 点 **Build**
4. 选个空文件夹，比如 `Builds/hmi-v1/`
5. **首次 Build 会非常慢**（10~30 分钟，IL2CPP 编译），后续增量 Build 快很多

### 1.3 Build 产物结构

Build 完成后，会得到：

```
Builds/hmi-v1/
├── index.html              ← Unity 默认的测试页面（不直接用）
├── Build/
│   ├── hmi-v1.loader.js    ← Unity 的 loader，必须引入
│   ├── hmi-v1.data.gz      ← 资源数据（最大）
│   ├── hmi-v1.framework.js.gz  ← Unity 框架代码
│   └── hmi-v1.wasm.gz      ← WebAssembly 主体
├── TemplateData/
│   ├── style.css
│   └── ... 模板资源
└── StreamingAssets/        ← 如果用了 StreamingAssets
```

**真正需要的文件**：`Build/` 和 `StreamingAssets/`（如果有）这两个文件夹，加上 `loader.js` 路径。其他都可以忽略，会在你的 HTML 里自己写。

---

## 二、嵌入到 HTML 页面

### 2.1 推荐方案：直接嵌入（不用 iframe）

**为什么不用 iframe：**
- iframe 是隔离环境，通信要走 postMessage，麻烦
- iframe 多一层开销，性能差 5%~10%
- 多个 iframe 各自创建 WebGL 上下文，显存翻倍

**直接嵌入的好处：**
- Unity 和你的 HTML 共享同一个 window
- JS 直接调 unityInstance.SendMessage()
- Unity 通过 .jslib 直接调 window.xxx() 函数
- 通信延迟 < 1ms

### 2.2 最小集成代码

把 Build 文件夹的 `Build/` 和 `StreamingAssets/`（如果有）放到你的 web 项目目录下，比如：

```
your-html-project/
├── index.html
├── js/
│   └── unity-loader.js     ← 你写的加载逻辑
└── public/
    └── unity/
        └── hmi/
            ├── Build/
            │   ├── hmi-v1.loader.js
            │   ├── hmi-v1.data.gz
            │   ├── hmi-v1.framework.js.gz
            │   └── hmi-v1.wasm.gz
            └── StreamingAssets/  (如有)
```

#### index.html

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>HMI Demo</title>
  <style>
    body { margin: 0; background: #000; }
    #unity-container {
      width: 3840px;
      height: 590px;
      position: relative;
    }
    #unity-canvas {
      width: 100%;
      height: 100%;
      display: block;
      touch-action: none;        /* 禁止浏览器手势冲突 */
      -webkit-user-select: none;
      user-select: none;
    }
    #unity-loading {
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      background: #000;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-family: sans-serif;
      transition: opacity 0.5s;
    }
    #unity-loading.hidden { opacity: 0; pointer-events: none; }
    #unity-progress {
      width: 300px;
      height: 4px;
      background: #333;
      border-radius: 2px;
      overflow: hidden;
      margin-left: 20px;
    }
    #unity-progress-bar {
      height: 100%;
      width: 0%;
      background: #fff;
      transition: width 0.2s;
    }
  </style>
</head>
<body>

<div id="unity-container">
  <canvas id="unity-canvas" tabindex="-1"></canvas>
  <div id="unity-loading">
    <span>Loading HMI...</span>
    <div id="unity-progress"><div id="unity-progress-bar"></div></div>
  </div>
</div>

<script src="public/unity/hmi/Build/hmi-v1.loader.js"></script>
<script>
  const buildUrl = "public/unity/hmi/Build";
  const config = {
    dataUrl: buildUrl + "/hmi-v1.data.gz",
    frameworkUrl: buildUrl + "/hmi-v1.framework.js.gz",
    codeUrl: buildUrl + "/hmi-v1.wasm.gz",
    streamingAssetsUrl: "public/unity/hmi/StreamingAssets",
    companyName: "YourCompany",
    productName: "HMI",
    productVersion: "1.0",
  };

  const canvas = document.querySelector("#unity-canvas");
  const loading = document.querySelector("#unity-loading");
  const progressBar = document.querySelector("#unity-progress-bar");

  // ============ Unity → HTML 事件接收 ============
  // Unity 的 .jslib 会调这个函数
  window.OnUnityEvent = function(jsonStr) {
    try {
      const evt = JSON.parse(jsonStr);
      console.log("[Unity Event]", evt);
      // 把事件分发给你的状态管理 / AI 助手
      window.HMIBus?.emit(evt);
    } catch (e) {
      console.error("Failed to parse Unity event:", e, jsonStr);
    }
  };

  // ============ 加载 Unity 实例 ============
  let unityInstance = null;

  createUnityInstance(canvas, config, (progress) => {
    progressBar.style.width = (progress * 100) + "%";
  }).then((instance) => {
    unityInstance = instance;
    window.unityInstance = instance;  // 暴露到全局，方便调试和 AI 调用
    loading.classList.add("hidden");
    setTimeout(() => loading.remove(), 600);
  }).catch((message) => {
    console.error("Unity load failed:", message);
  });

  // ============ HTML → Unity 指令发送（封装）============
  window.HMI = {
    sendCommand(action, target, params) {
      if (!unityInstance) {
        console.warn("Unity not loaded yet");
        return;
      }
      const cmd = {
        action: action,
        target: target || "",
        paramsJson: params ? JSON.stringify(params) : ""
      };
      unityInstance.SendMessage("HMIController", "ExecuteCommand", JSON.stringify(cmd));
    },

    // 便捷方法
    switchCamera(view) { this.sendCommand("switchCamera", view); },
    togglePart(partId) { this.sendCommand("togglePart", partId); },
    openPart(partId) { this.sendCommand("openPart", partId); },
    closePart(partId) { this.sendCommand("closePart", partId); },
    rotateCarTo(angle) { this.sendCommand("rotateCar", "absolute", {angle}); },
    rotateCarBy(angle) { this.sendCommand("rotateCar", "relative", {angle}); },
    resetCarRotation() { this.sendCommand("rotateCar", "reset"); },
    getState() { this.sendCommand("getState", "all"); },
  };

  // ============ 简单的事件总线 ============
  window.HMIBus = {
    listeners: [],
    on(fn) { this.listeners.push(fn); },
    emit(evt) { this.listeners.forEach(fn => fn(evt)); }
  };

  // 默认监听一下，把状态打印
  window.HMIBus.on(evt => {
    if (evt.eventType === "stateSnapshot") {
      try { console.log("State:", JSON.parse(evt.detail)); } catch {}
    }
  });
</script>

</body>
</html>
```

### 2.3 测试

**关键：必须用 HTTP 服务器打开，不能直接双击 HTML。**

最简单的测试方法（任选一种）：

```bash
# 方法 1：Python（最常用）
cd your-html-project
python -m http.server 8000
# 浏览器访问 http://localhost:8000

# 方法 2：Node.js
npx http-server -p 8000

# 方法 3：VSCode Live Server 扩展
# 右键 index.html → Open with Live Server
```

打开后浏览器 F12 控制台，可以手动测试：

```javascript
HMI.switchCamera("astronaut")
HMI.switchCamera("carExterior")
HMI.togglePart("doorL")
HMI.rotateCarTo(90)
HMI.getState()
```

---

## 三、与 AI 语音助手对接

### 3.1 推荐架构

```
用户语音输入
    ↓
语音识别 (STT)
    ↓
LLM (带 HMI_API_Reference.md 作为 system prompt)
    ↓
LLM 输出 JSON 指令
    ↓
window.HMI.sendCommand(...)
    ↓
Unity 执行
    ↓
Unity 发事件 → window.OnUnityEvent
    ↓
LLM 收到反馈，决定下一步
```

### 3.2 AI 调用代码示例

假设你已经有一个 LLM 客户端（比如调 Claude API），让它返回 JSON：

```javascript
async function handleVoiceCommand(userText) {
  // 1. 调 LLM 把语音文字转成指令
  const systemPrompt = await fetch('/HMI_API_Reference.md').then(r => r.text());

  const response = await callLLM({
    system: systemPrompt,
    user: userText,
    response_format: "json"
  });

  // 2. LLM 返回类似 {"action":"switchCamera","target":"astronaut"}
  const cmd = JSON.parse(response);

  // 3. 发给 Unity
  window.HMI.sendCommand(cmd.action, cmd.target,
    cmd.paramsJson ? JSON.parse(cmd.paramsJson) : null);
}
```

### 3.3 让 AI 知道场景实时状态

每次 AI 决策前，先查询当前状态：

```javascript
async function aiDecide(userText) {
  // 查状态
  window.HMI.getState();

  // 等状态返回（监听 stateSnapshot 事件）
  const state = await new Promise((resolve) => {
    const handler = (evt) => {
      if (evt.eventType === "stateSnapshot") {
        window.HMIBus.listeners = window.HMIBus.listeners.filter(f => f !== handler);
        resolve(JSON.parse(evt.detail));
      }
    };
    window.HMIBus.on(handler);
  });

  // 把状态作为上下文喂给 LLM
  const cmd = await callLLM({
    system: HMI_API_REFERENCE,
    user: `当前场景状态：${JSON.stringify(state)}\n\n用户说：${userText}`,
    response_format: "json"
  });

  window.HMI.sendCommand(cmd.action, cmd.target,
    cmd.paramsJson ? JSON.parse(cmd.paramsJson) : null);
}
```

### 3.4 AI 多步指令（带反馈循环）

如果 AI 需要多步操作（如"打开车门"先切视角再开门）：

```javascript
async function aiExecutePlan(userText) {
  let plan = [];  // LLM 返回的指令数组

  for (const cmd of plan) {
    window.HMI.sendCommand(cmd.action, cmd.target, cmd.params);

    // 等关键事件完成
    if (cmd.action === "switchCamera") {
      await waitForEvent("cameraTransitionEnd");
    } else if (cmd.action === "togglePart" || cmd.action === "openPart") {
      await waitForEvent("partOpened");
    }
    // 其他指令异步进行就行
  }
}

function waitForEvent(eventType, timeout = 5000) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("timeout")), timeout);
    const handler = (evt) => {
      if (evt.eventType === eventType) {
        clearTimeout(t);
        window.HMIBus.listeners = window.HMIBus.listeners.filter(f => f !== handler);
        resolve(evt);
      }
    };
    window.HMIBus.on(handler);
  });
}
```

---

## 四、常见问题排查

### 4.1 加载失败：`Unable to parse Build/...wasm.gz`

**原因：** 服务器返回的 MIME type 不对。

**解决：** 服务器需要给 `.wasm` 返回 `application/wasm`。Python `http.server` 默认就支持。如果是 Nginx，加：

```nginx
types {
    application/wasm wasm;
    application/octet-stream gz;
}
```

### 4.2 加载特别慢

第一次访问任何 WebGL 都比较慢（要下 wasm + data，几十 MB）。
**解决方案：**
- 服务器开启 gzip 缓存
- Unity Build 时 `Data Caching` 勾上，第二次访问会从浏览器 IndexedDB 读
- 用 CDN

### 4.3 触屏点击没反应 / 双指手势冲突

确保 canvas 加了：

```css
canvas {
  touch-action: none;
}
```

### 4.4 多个 AudioListener 警告

不影响功能。Unity 切换相机时会自动管理 AudioListener，但首帧可能有警告。可忽略。

### 4.5 Build 出来的 index.html 里有 Unity Logo 闪一下

这是免费版的限制。**用我上面给的自定义 index.html**，加载遮罩会盖住 Unity 默认 Logo，用户基本看不到。

---

## 五、与现有项目集成的目录结构建议

```
your-project/
├── frontend/                    # 你的 HMI 主项目
│   ├── index.html               # 主页面
│   ├── js/
│   │   ├── hmi-bridge.js        # window.HMI / window.HMIBus（封装好的接口）
│   │   ├── ai-assistant.js      # AI 语音助手逻辑
│   │   └── ws-client.js         # CARLA WebSocket 客户端（如果接 CARLA）
│   └── public/
│       └── unity/
│           └── hmi/             # Unity Build 产物放这里
│               ├── Build/
│               └── StreamingAssets/
│
├── docs/
│   ├── HMI_API_Reference.md     # 给 AI 用的 API 文档
│   └── WebGL_Integration_Guide.md  # 本文档
│
└── unity-source/                # Unity 工程源码（不部署，只用来 Build）
```

---

## 六、Build 与发布流程

每次更新 Unity 场景后：

1. Unity 里 **File → Build Settings → Build**，输出到一个临时文件夹
2. 复制 Build 文件夹的 `Build/` 和 `StreamingAssets/` 到 `frontend/public/unity/hmi/`
3. **注意 loader.js 文件名可能变化**（Unity 用 productName 作为前缀）
4. 如果文件名变了，更新 HTML 里的 `<script src="..."`和 `config` 中的 URL
5. 强制刷新浏览器（Ctrl+F5），清掉 IndexedDB 缓存看到新版本

---

## 七、性能调优建议

参考现有项目情况（4060/3080 8GB 显存 + CARLA 同时运行）：

- CARLA 用 `-quality-level=Medium` 启动，省 1~2GB 显存
- Unity Build 不要超过 100MB（首次加载体验关键）
- 多个 Unity 场景共存时，每个 canvas 1280x720 比 1920x1080 省 30% 显存
- 浏览器开发者工具 → Performance Monitor 实时观察 GPU 占用
- 后台标签页帧率会降，不是 bug

---

## 八、版本

- **指南版本**：v1.0
- **对应 Unity 项目**：HMI Demo Unity 2022.3 LTS
- **目标分辨率**：3840 × 590 (HMI 触控屏)
