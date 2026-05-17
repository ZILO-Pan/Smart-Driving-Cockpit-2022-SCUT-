# NOVA 语音助手 ↔ HMI 前端完整控制协议

> 给 Codex / AI 阅读：本文档描述了 HMI 前端所有可交互节点、资源清单、以及语音 FC 应如何精确控制它们。

---

## 一、调用链路

```
用户语音 → RTC SDK → 火山 S2S 模型 → Function Calling
                                            ↓
                          voice.js 接收 binary message（tool_calls）
                                            ↓
                          拆解分组工具 → _executeFCAction(action, params)
                                            ↓
                          前端即时执行 HMI 动画 / 状态变化
                                            ↓
                          同时 POST /api/voice/fc-execute（后端持久化 + 通知AI继续说话）
```

---

## 二、HMI 界面布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        3840 × 590 超宽屏幕                                │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────────┐ │
│  │  左区 ADAS    │  │  中区 导航     │  │  右区 动态卡片（4槽位）         │ │
│  │  - ADAS Canvas│  │  - Nav Canvas │  │  [卡片1][卡片2][卡片3][卡片4]  │ │
│  │  - 速度仪表   │  │  - 目的地文本  │  │                               │ │
│  └──────────────┘  └──────────────┘  └────────────────────────────────┘ │
│                                                                          │
│  ┌──────────────────────── 底部 Dock ────────────────────────────────┐  │
│  │ [Nav] [ADAS] [AI Voice] [Service] [Cabin] [3D]                    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─── Unity 3D 覆盖层（toggle，z-index 最高）───┐                        │
│  │  3D 展车 / 内部视角 / 部件动画                  │                        │
│  └────────────────────────────────────────────────┘                      │
│                                                                          │
│  ┌─── NOVA 语音浮窗 ───┐                                                 │
│  │  语音识别文本 / AI回复 │                                                │
│  └──────────────────────┘                                                │
│                                                                          │
│  ┌─── Service 弹窗面板 ───┐                                              │
│  │  7个服务图标网格         │                                              │
│  └─────────────────────────┘                                             │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 三、底部 Dock 按钮（6个）

| 按钮 | ID | 点击效果 | 对应语音 FC |
|------|-----|---------|-----------|
| Nav | dock-nav | 显示/隐藏中区导航 | `toggle_navigation` |
| ADAS | dock-adas | 显示/隐藏左区ADAS | `toggle_adas` |
| AI Voice | dock-ai | 开启/关闭 NOVA 语音 | 无需FC，直接唤醒 |
| Service | dock-service | 打开/关闭服务选择面板 | `toggle_service_panel` |
| Cabin | dock-cabin | 显示/隐藏右区卡片 | `toggle_cabin_cards` |
| 3D | dock-3d | 打开/关闭 Unity 3D 场景 | `toggle_3d_scene` |

---

## 四、Service 面板（7个服务）

点击 dock-service 后弹出的网格面板，包含以下可点击服务：

| 服务 | data-service | 点击效果 | 对应语音 FC |
|------|------------|---------|-----------|
| Alipay（支付宝） | alipay | 右区添加支付宝截图卡片 | `open_service_card({service:'alipay'})` |
| Ctrip（携程） | ctrip | 右区添加携程截图卡片 | `open_service_card({service:'ctrip'})` |
| Music（音乐） | music | 打开音乐播放器卡片 | `open_service_card({service:'music'})` |
| Bilibili（视频） | bilibili | 打开B站推荐卡片 | `open_service_card({service:'bilibili'})` |
| Parking（停车） | parking | 右区添加3D停车卡片 | `open_service_card({service:'parking'})` |
| Charging（充电） | charging | 右区添加3D充电卡片 | `open_service_card({service:'charging'})` |
| News（新闻） | news | 右区添加新闻截图卡片 | `open_service_card({service:'news'})` |

**中文别名映射**（AI 说中文时自动转换）：
```
奶茶/点奶茶/支付/支付宝 → alipay
机票/航班/携程 → ctrip
新闻 → news
停车/停车场 → parking
充电 → charging
音乐 → music
视频 → bilibili
```

---

## 五、音乐播放器（完整资源）

### 播放列表（6首，有序）

| 索引 | 标题 | 歌手 | 文件 |
|------|------|------|------|
| 0 | Starboy | The Weeknd | starboy.mp3 |
| 1 | How You Like That | BLACKPINK | how you like that.mp3 |
| 2 | 晴天 | 周杰伦 | 晴天.mp3 |
| 3 | Handlebars | Jennie | handlebars.mp3 |
| 4 | Born Again | Lisa | born again.mp3 |
| 5 | Toxic Till The End | ROSÉ | toxic till the end.mp3 |

### 语音控制应实现的操作

| 用户说的话 | 应执行的动作 |
|-----------|------------|
| "播放音乐" | 继续播放当前曲目 |
| "播放 Starboy" | 匹配 index=0，切换并播放 |
| "播放晴天" | 匹配 index=2，切换并播放 |
| "播放 BLACKPINK" | 按歌手匹配 index=1 |
| "下一首" | nextTrack() |
| "上一首" | prevTrack() |
| "暂停音乐" | pause() |

### FC 协议设计

```json
{
  "action": "play_music",
  "params": {
    "title": "Starboy",
    "control": "play"
  }
}
```

`control` 可选值：`play`（播放/恢复）、`pause`（暂停）、`next`（下一首）、`prev`（上一首）

`title` 用于匹配曲目（模糊匹配 title 或 artist）

**前端执行逻辑应该是**：
```js
case 'play_music': {
    // 1. 确保音乐卡片可见
    if (!musicOpen) { musicOpen = true; handleMusicBilibili(); }
    
    // 2. 处理 control
    if (params.control === 'pause') { if (isPlaying) togglePlay(); break; }
    if (params.control === 'next') { nextTrack(); break; }
    if (params.control === 'prev') { prevTrack(); break; }
    
    // 3. 匹配歌名/歌手
    const query = (params.title || '').toLowerCase();
    if (query) {
        const idx = playlist.findIndex(t =>
            t.title.toLowerCase().includes(query) ||
            t.artist.toLowerCase().includes(query)
        );
        if (idx !== -1 && idx !== currentTrack) loadTrack(idx);
    }
    
    // 4. 播放
    if (!isPlaying) { audio.play(); isPlaying = true; }
    const btn = document.getElementById('btn-play');
    if (btn) btn.textContent = '⏸';
    break;
}
```

---

## 六、Bilibili 视频卡片（完整资源）

### 视频列表（5个）

| 索引 | 电影/内容 | BV号 | 海报文件 |
|------|----------|------|---------|
| 0 | Huntrix（猎杀） | BV1oeNXzBEK6 | Huntrix.jpg |
| 1 | Interstellar（星际穿越） | BV19A411q7sB | Interstellar.jpg |
| 2 | Farewell My Concubine（霸王别姬） | BV1wF411S71j | Faerwell My Concubine.jpg |
| 3 | The Devil Wears Prada（穿普拉达的女王） | BV1dzHzzyERq | The Devil wears Prrada.jpg |
| 4 | Nghesieu DE | BV15czjBNEn6 | Nghesieu DE.jpg |

### 语音控制应实现的操作

| 用户说的话 | 应执行的动作 |
|-----------|------------|
| "我想看星际穿越" | 匹配 index=1，直接打开 iframe 播放器 |
| "播放霸王别姬" | 匹配 index=2，打开播放器 |
| "看个视频" | 打开 bilibili 推荐卡片（让用户自己选） |
| "关闭视频" | 关闭 bili-player 卡片 |

### FC 协议设计

```json
{
  "action": "play_video",
  "params": {
    "title": "星际穿越",
    "bvid": "BV19A411q7sB"
  }
}
```

`title` 用于模糊匹配视频名；`bvid` 用于精确指定（可选，AI 如果记住了 bvid 可以直接传）。

**前端执行逻辑应该是**：
```js
case 'play_video': {
    const query = (params.title || '').toLowerCase();
    const bvid = params.bvid || '';
    
    // 视频名 → bvid 映射
    const videoMap = [
        { names: ['huntrix', '猎杀'], bvid: 'BV1oeNXzBEK6' },
        { names: ['interstellar', '星际穿越'], bvid: 'BV19A411q7sB' },
        { names: ['farewell', '霸王别姬', 'concubine'], bvid: 'BV1wF411S71j' },
        { names: ['devil', 'prada', '穿普拉达', '女王'], bvid: 'BV1dzHzzyERq' },
        { names: ['nghesieu'], bvid: 'BV15czjBNEn6' },
    ];
    
    let targetBvid = bvid;
    if (!targetBvid && query) {
        const match = videoMap.find(v => v.names.some(n => query.includes(n)));
        if (match) targetBvid = match.bvid;
    }
    
    if (targetBvid) {
        openBiliPlayer(targetBvid);
    } else {
        // 无法匹配，打开推荐列表让用户选
        if (!bilibiliOpen) { bilibiliOpen = true; handleMusicBilibili(); }
    }
    break;
}
```

---

## 七、座舱环境控制

### 空调温度 `set_ac_temperature`
```json
{ "action": "set_ac_temperature", "params": { "temperature": 22 } }
```
- 范围：16-30
- **前端效果**：状态卡片 + 主题色变化
- **应增加**：自动打开 3D → 切换到 interior 视角

### 座椅通风 `set_seat_ventilation`
```json
{ "action": "set_seat_ventilation", "params": { "on": true } }
```
- **应增加**：自动打开 3D → 切换到 interior 视角

### 车窗 `toggle_window`
```json
{ "action": "toggle_window", "params": { "open": true } }
```
- **已有**：自动打开 3D + 调用 Unity openPart/closePart('windowL')

### 氛围灯 `set_ambient_light`
```json
{ "action": "set_ambient_light", "params": { "color": "蓝" } }
```
- 可选颜色：蓝、红、绿、紫、暖白、橙
- **应增加**：自动打开 3D → 切换到 interior 视角

### 座舱模式 `set_cabin_mode`
```json
{ "action": "set_cabin_mode", "params": { "mode": "运动" } }
```
- 可选模式：舒适、运动、休息、标准
- 运动模式自动设氛围灯红色，休息模式设暖橙+关通风
- **应增加**：自动打开 3D → 切换到 interior 视角

---

## 八、3D 展车控制

### 核心规则

**一切跟车外观有关的操作** → 自动打开 3D 外部视角 + 执行动画：

| 操作 | FC action | 参数 |
|------|-----------|------|
| 打开左车门 | open_car_part | {part: 'doorL'} |
| 打开右车门 | open_car_part | {part: 'doorR'} |
| 打开引擎盖 | open_car_part | {part: 'hood'} |
| 打开后备箱 | open_car_part | {part: 'trunk'} |
| 打开左车窗 | open_car_part | {part: 'windowL'} |
| 打开右车窗 | open_car_part | {part: 'windowR'} |
| 关闭对应部件 | close_car_part | {part: '...'} |
| 切换部件状态 | toggle_car_part | {part: '...'} |
| 看车正面 | switch_camera | {view: 'front'} |
| 看车后面 | switch_camera | {view: 'rear'} |
| 看车俯视 | switch_camera | {view: 'top'} |
| 看车内部 | switch_camera | {view: 'interior'} |
| 看宇航员 | switch_camera | {view: 'astronaut'} |
| 默认视角 | switch_camera | {view: 'default'} |
| 重置视角 | reset_camera | {} |
| 旋转到指定角度 | rotate_car | {mode:'absolute', angle:90} |
| 相对旋转 | rotate_car | {mode:'relative', angle:45} |
| 旋转复位 | rotate_car | {mode:'reset'} |

**一切座舱内部的操作**（空调/座椅/氛围灯/模式）→ 自动打开 3D + 切到 `interior` 视角

---

## 九、导航与驾驶控制

### 导航面板 `toggle_navigation`
```json
{ "action": "toggle_navigation", "params": { "show": true } }
```
- **唯一真实交互**：打开/关闭中区导航面板
- `set_destination` 只是改了个文字显示，不算真实导航功能，仅作为辅助文案展示

### 变道 `change_lane`
```json
{ "action": "change_lane", "params": { "direction": "右" } }
```
- 修改 ADAS 车道位置
- 自动显示左区 ADAS 面板

---

## 十、主动服务计划 `proactive_service_plan`

当用户说模糊需求时（如"好热"、"无聊"、"赶飞机"），AI 输出：

```json
{
  "intent": "thermal_comfort",
  "confidence": 0.92,
  "reason": "用户表达了热感不适",
  "hmi_feedback": "正在为您调整座舱温度和通风",
  "actions": [
    { "action": "set_ac_temperature", "params": { "temperature": 22 } },
    { "action": "set_seat_ventilation", "params": { "on": true } },
    { "action": "set_ambient_light", "params": { "color": "蓝" } }
  ]
}
```

前端会先显示意图理解卡片，再依次执行每个 action。

---

## 十一、状态查询 `query_state`

```json
{ "action": "query_state", "params": { "target": "cabin" } }
```

| target | 返回内容 |
|--------|---------|
| cabin | 空调温度 + 氛围灯颜色 + 当前模式 |
| vehicle | 车速 + 挡位 + 自动驾驶状态 |
| navigation | 当前车道 + 车道总数 |

纯查询，后端返回文本给 AI 播报，前端不需要做视觉动作（仅显示一个状态卡片）。

---

## 十二、右区卡片系统规则

4 个槽位，先进先出：

| 卡片类型 | 占用槽位 | 说明 |
|---------|---------|------|
| music（音乐播放器） | 1 | 含封面+标题+播放控制 |
| bilibili（视频推荐） | 2 | 5个海报横滚，可点击播放 |
| combo（音乐+视频合并） | 2 | music和bilibili同时开启时自动合并 |
| bili-player（iframe播放） | 4 | 全占，播放时清除其他卡片 |
| alipay / ctrip / news | 1 | 截图卡片 |
| parking | 1 | Three.js 3D停车场景 |
| charging | 1 | Three.js 3D充电场景 |
| fc-xxx（FC执行结果） | 1 | NOVA执行结果反馈卡片 |

**自动替换规则**：
- 新卡片从左侧插入
- 如果总槽位 > 4，从右侧（最旧的）开始移除
- 同 ID 卡片不会重复（已有则移除后 return，相当于 toggle 关闭）
- FC 结果卡片用 upsert（同 action 只保留最新一张，动画更新）

---

## 十三、分组工具格式（给 LLM 调用）

LLM 调用时的 JSON 格式：

```json
// 座舱控制
{ "function": "cabin_control", "arguments": { "action": "set_ac_temperature", "params": { "temperature": 22 } } }

// 媒体导航
{ "function": "media_nav_control", "arguments": { "action": "play_music", "params": { "title": "晴天", "control": "play" } } }

// 面板控制
{ "function": "panel_control", "arguments": { "action": "open_service_card", "params": { "service": "parking" } } }

// 3D控制
{ "function": "unity_control", "arguments": { "action": "open_car_part", "params": { "part": "doorL" } } }

// 状态查询
{ "function": "query_state", "arguments": { "target": "vehicle" } }

// 主动服务
{ "function": "proactive_service_plan", "arguments": { "intent": "...", "confidence": 0.9, "actions": [...] } }
```

---

## 十四、需要新增/改进的 FC action 汇总

| 新 action | 分组 | 参数 | 说明 |
|-----------|------|------|------|
| `play_video` | media_nav_control | {title?, bvid?} | 按名字匹配打开B站视频 |
| `stop_video` | media_nav_control | {} | 关闭视频播放器 |
| `play_music` 增强 | media_nav_control | {title?, control?} | 支持按歌名匹配+暂停/上下首 |

### 现有 action 需增强行为

| action | 当前行为 | 应增加 |
|--------|---------|--------|
| set_ac_temperature | 状态卡片 | + 打开3D + 切interior视角 |
| set_seat_ventilation | 状态卡片 | + 打开3D + 切interior视角 |
| set_ambient_light | 状态卡片 + CSS色 | + 打开3D + 切interior视角 |
| set_cabin_mode | 状态卡片 | + 打开3D + 切interior视角 |
| play_music | 只audio.play() | + 匹配歌名 + 显示音乐卡片 |
