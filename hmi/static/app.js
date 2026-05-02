/**
 * 智慧驾驶座舱 HMI 前端
 * WebSocket 连接后端，实时更新车辆/座舱状态
 */

let ws = null;
let reconnectTimer = null;

function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        console.log('[WS] 已连接');
        document.getElementById('cloud-status').textContent = '云端在线';
        document.getElementById('cloud-status').style.borderColor = '#10b981';
        document.getElementById('cloud-status').style.color = '#10b981';
    };

    ws.onclose = () => {
        console.log('[WS] 断开，3秒后重连...');
        document.getElementById('cloud-status').textContent = '已断开';
        document.getElementById('cloud-status').style.borderColor = '#ef4444';
        document.getElementById('cloud-status').style.color = '#ef4444';
        reconnectTimer = setTimeout(connect, 3000);
    };

    ws.onerror = () => {};

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
    };
}

function handleMessage(msg) {
    switch (msg.type) {
        case 'state_update':
            updateVehicleState(msg.vehicle);
            updateCabinState(msg.cabin);
            break;
        case 'ai_reply':
            appendChat('user', msg.user);
            appendChat('assistant', msg.reply);
            break;
        case 'service_action':
            handleServiceAction(msg);
            break;
        case 'intent_update':
            updateIntent(msg);
            break;
    }
}

function updateVehicleState(v) {
    if (!v) return;
    document.getElementById('speed-value').textContent = Math.round(v.speed_kmh || 0);
    document.getElementById('steer-value').textContent = ((v.steer || 0) * 540).toFixed(0) + '°';

    const gear = v.gear || 0;
    let gearText = 'P';
    if (v.is_reverse) gearText = 'R';
    else if (gear > 0) gearText = 'D' + gear;
    else if (gear === 0 && (v.speed_kmh || 0) > 1) gearText = 'D';
    document.getElementById('gear-value').textContent = gearText;

    const apChip = document.getElementById('autopilot-chip');
    if (v.autopilot_enabled) {
        apChip.classList.add('active');
        apChip.textContent = '自动驾驶中';
    } else {
        apChip.classList.remove('active');
        apChip.textContent = '手动驾驶';
    }
}

function updateCabinState(cabin) {
    if (!cabin || Object.keys(cabin).length === 0) return;
    if (cabin.ac_temperature !== undefined)
        document.getElementById('ac-temp').textContent = cabin.ac_temperature + '°C';
    if (cabin.seat_ventilation !== undefined)
        document.getElementById('seat-vent').textContent = cabin.seat_ventilation ? '开' : '关';
    if (cabin.window_open !== undefined)
        document.getElementById('window-state').textContent = cabin.window_open ? '开启' : '关闭';
    if (cabin.ambient_light !== undefined)
        document.getElementById('ambient-light').textContent = cabin.ambient_light;
    if (cabin.cabin_mode !== undefined)
        document.getElementById('cabin-mode').textContent = cabin.cabin_mode;
    if (cabin.user_emotion !== undefined)
        document.getElementById('emotion-chip').textContent = '情绪：' + cabin.user_emotion;
    if (cabin.user_fatigue !== undefined)
        document.getElementById('fatigue-chip').textContent = '疲劳：' + (cabin.user_fatigue ? '是' : '否');
    if (cabin.thermal_comfort !== undefined)
        document.getElementById('thermal-chip').textContent = '体感：' + cabin.thermal_comfort;
}

function updateIntent(msg) {
    document.getElementById('intent-display').textContent = msg.intent || '--';
    document.getElementById('confidence-display').textContent =
        msg.confidence ? (msg.confidence * 100).toFixed(0) + '%' : '--';
}

function handleServiceAction(msg) {
    const action = msg.action;
    if (action === 'open_service_card') {
        const cardType = msg.params?.service;
        document.querySelectorAll('.service-card').forEach(c => c.classList.remove('active'));
        const card = document.querySelector(`.service-card[data-service="${cardType}"]`);
        if (card) card.classList.add('active');
    }
}

function appendChat(role, text) {
    const chat = document.getElementById('ai-chat');
    const div = document.createElement('div');
    div.className = 'chat-msg ' + role;
    div.textContent = (role === 'user' ? '我：' : '小驾：') + text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;

    // 保持最近 20 条
    while (chat.children.length > 20) {
        chat.removeChild(chat.firstChild);
    }
}

function sendUserInput(text) {
    if (!text.trim()) return;
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'user_input', text: text }));
        appendChat('user', text);
    }
}

// 发送按钮
document.getElementById('send-btn').addEventListener('click', () => {
    const input = document.getElementById('user-input');
    sendUserInput(input.value);
    input.value = '';
});

// 回车发送
document.getElementById('user-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        sendUserInput(e.target.value);
        e.target.value = '';
    }
});

// Demo 触发按钮
document.getElementById('demo-triggers').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    const scenario = btn.dataset.scenario;
    if (scenario) sendUserInput(scenario);
});

// 服务卡片点击
document.querySelectorAll('.service-card').forEach(card => {
    card.addEventListener('click', () => {
        const service = card.dataset.service;
        const textMap = {
            flight: '帮我订一张去上海的机票',
            milktea: '我想喝奶茶',
            news: '看一下今天新闻',
            video: '刷会儿视频',
        };
        sendUserInput(textMap[service] || service);
    });
});

// 时钟
function updateClock() {
    const now = new Date();
    document.getElementById('clock').textContent =
        now.getHours().toString().padStart(2, '0') + ':' +
        now.getMinutes().toString().padStart(2, '0');
}
setInterval(updateClock, 10000);
updateClock();

// 启动连接
connect();
