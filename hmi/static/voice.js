/**
 * NOVA Voice — 火山 RTC 实时语音对话 + 唤醒词检测
 *
 * 架构:
 *   常驻监听: AudioWorklet → VAD → /ws/wake → ASR → 检测 "HI NOVA"
 *   对话模式: 浏览器 RTC SDK → 火山 RTC 房间 → S2S 端到端语音模型
 *
 * 使用方式:
 *   window.novaVoice.start()  — 开始语音对话
 *   window.novaVoice.stop()   — 结束语音对话
 *   window.novaVoice.toggle() — 切换
 *   (自动) 说 "HI NOVA" 唤醒
 */

(function() {
    'use strict';

    // ─── RTC 状态 ──────────────────────────────────────────
    let engine = null;
    let isActive = false;
    let isConnecting = false;
    let lastUserText = '';
    let lastInstantSignature = '';
    let lastInstantAt = 0;
    const recentInstantActions = new Map();
    const instantRoundActions = new Map();
    let currentNovaState = 'idle';
    const ROOM_ID = 'nova_room_001';
    const USER_ID = 'hmi_user_' + Date.now().toString(36);
    const BOT_USER_ID = 'NOVA_bot';

    // ─── 唤醒词监听状态 ────────────────────────────────────
    let wakeAudioContext = null;
    let wakeWorkletNode = null;
    let wakeStream = null;
    let wakeWs = null;
    let wakeListening = false;
    let wakePaused = false;

    // ─── UI 元素 ────────────────────────────────────────────
    const overlay = document.getElementById('nova-overlay');
    const orb = document.getElementById('nova-orb');
    const transcript = document.getElementById('nova-transcript');
    const reply = document.getElementById('nova-reply');
    const stateLabel = document.getElementById('nova-state');

    // ─── UI 控制 ────────────────────────────────────────────
    function showNova() {
        if (overlay) {
            overlay.classList.add('active');
            overlay.style.display = 'flex';
        }
    }

    function hideNova() {
        if (overlay) {
            overlay.classList.remove('active');
            overlay.style.display = 'none';
        }
    }

    function setNovaState(state) {
        currentNovaState = state;
        if (!stateLabel) return;
        const states = {
            'idle': { text: 'Ready', cls: 'state-idle' },
            'connecting': { text: 'Connecting...', cls: 'state-connecting' },
            'listening': { text: 'Listening...', cls: 'state-listening' },
            'thinking': { text: 'Thinking...', cls: 'state-thinking' },
            'speaking': { text: 'Speaking...', cls: 'state-speaking' },
            'error': { text: 'Error', cls: 'state-error' },
        };
        const s = states[state] || states['idle'];
        stateLabel.textContent = s.text;
        stateLabel.className = 'nova-state ' + s.cls;

        if (orb) {
            orb.className = 'nova-orb';
            if (state === 'listening') orb.classList.add('nova-listening');
            else if (state === 'speaking') orb.classList.add('nova-speaking');
            else if (state === 'thinking') orb.classList.add('nova-thinking');
            else if (state === 'connecting') orb.classList.add('nova-connecting');
        }

        if (window.setMediaDucking) {
            window.setMediaDucking(state === 'speaking');
        }
    }

    function setTranscript(text) {
        if (transcript) transcript.textContent = text;
    }

    function setReply(text) {
        if (reply) reply.textContent = text;
    }

    // ═══════════════════════════════════════════════════════════
    // 唤醒词监听（常驻）
    // ═══════════════════════════════════════════════════════════

    async function initWakeListener() {
        try {
            wakeStream = await navigator.mediaDevices.getUserMedia({
                audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
            });
            console.log('[WAKE] Microphone access granted');

            wakeAudioContext = new AudioContext();
            // 确保 AudioContext 不是 suspended（Chrome 安全策略）
            if (wakeAudioContext.state === 'suspended') {
                await wakeAudioContext.resume();
            }
            console.log('[WAKE] AudioContext state:', wakeAudioContext.state, 'sampleRate:', wakeAudioContext.sampleRate);
            await wakeAudioContext.audioWorklet.addModule('/static/wake-processor.js');

            const source = wakeAudioContext.createMediaStreamSource(wakeStream);
            wakeWorkletNode = new AudioWorkletNode(wakeAudioContext, 'wake-processor');

            wakeWorkletNode.port.onmessage = (e) => {
                if (wakePaused || !wakeListening) return;
                const { audio, isSpeech } = e.data;
                _sendWakeAudio(audio, isSpeech);
            };

            source.connect(wakeWorkletNode);
            // 不连接 destination，避免麦克风回放到扬声器

            _connectWakeWs();
            wakeListening = true;
            console.log('[WAKE] Listening for wake word...');

        } catch (err) {
            console.warn('[WAKE] Init failed:', err.message);
        }
    }

    function _connectWakeWs() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${location.host}/ws/wake`;
        wakeWs = new WebSocket(url);

        wakeWs.onopen = () => {
            console.log('[WAKE] WebSocket connected');
        };

        wakeWs.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                if (msg.type === 'wake_detected') {
                    console.log('[WAKE] Wake word detected:', msg.text);
                    _onWakeDetected();
                } else if (msg.type === 'ready') {
                    console.log('[WAKE] ASR session ready');
                } else if (msg.type === 'error') {
                    console.warn('[WAKE] Error:', msg.message);
                }
            } catch (err) {
                console.warn('[WAKE] Message parse error:', err);
            }
        };

        wakeWs.onclose = () => {
            console.log('[WAKE] WebSocket closed');
            if (wakeListening && !wakePaused) {
                setTimeout(_connectWakeWs, 3000);
            }
        };

        wakeWs.onerror = (err) => {
            console.warn('[WAKE] WebSocket error');
        };
    }

    let _silenceCounter = 0;

    function _sendWakeAudio(audioBuffer, isSpeech) {
        if (!wakeWs || wakeWs.readyState !== WebSocket.OPEN) return;

        if (isSpeech) {
            _silenceCounter = 0;
            wakeWs.send(audioBuffer);
        } else {
            _silenceCounter++;
            if (_silenceCounter === 15) {
                // 1.5s 静音，通知后端重置 ASR
                wakeWs.send(JSON.stringify({ type: 'silence' }));
            }
        }
    }

    function _onWakeDetected() {
        if (isActive || isConnecting) return;
        start();
    }

    function _pauseWake() {
        wakePaused = true;
        if (wakeWs && wakeWs.readyState === WebSocket.OPEN) {
            wakeWs.send(JSON.stringify({ type: 'pause' }));
        }
    }

    function _resumeWake() {
        wakePaused = false;
        _silenceCounter = 0;
        if (wakeWs && wakeWs.readyState === WebSocket.OPEN) {
            wakeWs.send(JSON.stringify({ type: 'resume' }));
        }
    }

    // ═══════════════════════════════════════════════════════════
    // RTC 语音对话
    // ═══════════════════════════════════════════════════════════

    function getRTCEngine() {
        if (typeof VERTC !== 'undefined') return VERTC;
        if (typeof VolcEngineRTC !== 'undefined') return VolcEngineRTC;
        if (window.VERTC) return window.VERTC;
        if (window.VolcEngineRTC) return window.VolcEngineRTC;
        console.error('[NOVA] RTC SDK not loaded.');
        return null;
    }

    async function start() {
        if (isActive || isConnecting) return;
        isConnecting = true;

        _pauseWake();
        showNova();
        setNovaState('connecting');
        setTranscript('');
        setReply('');

        try {
            const tokenResp = await fetch('/api/voice/token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ room_id: ROOM_ID, user_id: USER_ID }),
            });
            const tokenData = await tokenResp.json();
            console.log('[NOVA] Token obtained:', tokenData.app_id);

            const VERTC_SDK = getRTCEngine();
            if (!VERTC_SDK) {
                throw new Error('RTC SDK not available');
            }

            if (typeof VERTC_SDK.createEngine === 'function') {
                engine = VERTC_SDK.createEngine(tokenData.app_id);
            } else if (VERTC_SDK.RTCEngine) {
                engine = new VERTC_SDK.RTCEngine(tokenData.app_id);
            } else if (VERTC_SDK.default && typeof VERTC_SDK.default.createEngine === 'function') {
                engine = VERTC_SDK.default.createEngine(tokenData.app_id);
            } else {
                throw new Error('Cannot find createEngine in RTC SDK');
            }
            console.log('[NOVA] Engine created');

            _bindEngineEvents(engine);

            await engine.joinRoom(tokenData.token, ROOM_ID,
                { userId: USER_ID },
                { isAutoPublish: true, isAutoSubscribeAudio: true, isAutoSubscribeVideo: true }
            );
            console.log('[NOVA] Joined room:', ROOM_ID);

            await engine.startAudioCapture();
            console.log('[NOVA] Microphone started');

            // 开启摄像头（视觉理解，AI 可以看到用户）
            try {
                await engine.startVideoCapture();
                console.log('[NOVA] Camera started (vision enabled)');
            } catch (camErr) {
                console.warn('[NOVA] Camera unavailable:', camErr.message);
            }

            const startResp = await fetch('/api/voice/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ room_id: ROOM_ID, user_id: USER_ID }),
            });
            const startData = await startResp.json();
            console.log('[NOVA] Bot start result:', startData);

            if (startData.status !== 'ok') {
                throw new Error(startData.error?.Message || JSON.stringify(startData.error) || 'Failed to start bot');
            }

            isActive = true;
            isConnecting = false;
            setNovaState('listening');
            console.log('[NOVA] Voice session started successfully');

        } catch (err) {
            console.error('[NOVA] Start failed:', err);
            setNovaState('error');
            setReply('连接失败: ' + err.message);
            isConnecting = false;
            setTimeout(() => {
                hideNova();
                _resumeWake();
            }, 3000);
            _cleanup();
        }
    }

    async function stop() {
        if (!isActive && !isConnecting) return;

        setNovaState('idle');

        try {
            await fetch('/api/voice/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ room_id: ROOM_ID }),
            });
        } catch (e) {
            console.warn('[NOVA] Stop bot error:', e);
        }

        _cleanup();
        isActive = false;
        isConnecting = false;

        setTimeout(() => {
            hideNova();
            _resumeWake();
        }, 500);
        console.log('[NOVA] Voice session stopped');
    }

    function toggle() {
        if (isActive || isConnecting) {
            stop();
        } else {
            start();
        }
    }

    function _cleanup() {
        if (engine) {
            try {
                engine.stopAudioCapture();
                engine.stopVideoCapture();
                engine.leaveRoom();
                engine.destroyEngine();
            } catch (e) {}
            engine = null;
        }
    }

    // ─── RTC 事件绑定 ───────────────────────────────────────
    function _bindEngineEvents(eng) {
        eng.on('onRoomBinaryMessageReceived', (event) => {
            try {
                _handleBinaryMessage(event.message || event.data);
            } catch (e) {
                console.warn('[NOVA] Binary message parse error:', e);
            }
        });

        eng.on('onUserJoined', (event) => {
            if (event.userInfo && event.userInfo.userId === BOT_USER_ID) {
                console.log('[NOVA] Bot joined room');
                setNovaState('listening');
            }
        });

        eng.on('onUserLeave', (event) => {
            if (event.userInfo && event.userInfo.userId === BOT_USER_ID) {
                console.log('[NOVA] Bot left room');
                if (isActive) {
                    setNovaState('idle');
                    setReply('对话已结束');
                    setTimeout(() => {
                        stop();
                    }, 2000);
                }
            }
        });

        eng.on('onError', (event) => {
            console.error('[NOVA] RTC error:', event);
            setNovaState('error');
        });
    }

    function _handleBinaryMessage(data) {
        let buffer;
        if (data instanceof ArrayBuffer) {
            buffer = new Uint8Array(data);
        } else if (data instanceof Uint8Array) {
            buffer = data;
        } else {
            return;
        }

        if (buffer.length < 8) return;

        const magic = String.fromCharCode(buffer[0], buffer[1], buffer[2], buffer[3]);
        const len = (buffer[4] << 24) | (buffer[5] << 16) | (buffer[6] << 8) | buffer[7];
        const payload = new TextDecoder().decode(buffer.slice(8, 8 + len));

        console.log('[NOVA-BIN] magic=' + magic + ', len=' + len + ', payload=', payload.substring(0, 200));

        let parsed;
        try {
            parsed = JSON.parse(payload);
        } catch (e) {
            console.warn('[NOVA-BIN] JSON parse failed for magic=' + magic);
            return;
        }

        if (magic === 'subv' && Array.isArray(parsed.data)) {
            const finalItems = parsed.data.filter(item => item && item.definite && item.text);
            const latest = finalItems[finalItems.length - 1] || parsed.data.find(item => item && item.text);
            const text = latest ? String(latest.text || '').trim() : '';
            if (text) {
                const roundId = latest ? latest.roundId : undefined;
                const finalText = latest ? !!latest.definite : false;
                const likelyAssistant = currentNovaState === 'speaking' || /^(好的|已|正在|我来|可以|当然|没问题)/.test(text);
                if (likelyAssistant) {
                    setReply(text);
                } else {
                    lastUserText = text;
                    _tryInstantHMIShortcut(text, { roundId, finalText });
                    setTranscript(text);
                }
            }
        } else if (magic === 'subt' || parsed.text !== undefined) {
            const text = parsed.text || parsed.data || '';
            const isUser = parsed.role === 'user' || parsed.is_user;
            if (isUser) {
                lastUserText = text;
                _tryInstantHMIShortcut(text, { roundId: parsed.roundId ?? parsed.round_id, finalText: parsed.definite ?? true });
                setTranscript(text);
            } else {
                setReply(text);
            }
        }

        if (parsed.state || parsed.ai_state) {
            const state = parsed.state || parsed.ai_state;
            if (state === 'listening' || state === 0) setNovaState('listening');
            else if (state === 'thinking' || state === 1) setNovaState('thinking');
            else if (state === 'speaking' || state === 2) setNovaState('speaking');
            else if (state === 'interrupted' || state === 3) setNovaState('listening');
        }

        // Function Calling（客户端模式 — 无需公网穿透）
        // 当不配 ServerMessageUrl 时，FC 通过 binary message 直接推到客户端
        if (parsed.tool_calls || parsed.function_call) {
            const calls = parsed.tool_calls || [parsed.function_call];
            for (const call of calls) {
                const funcName = call.function?.name || call.name || '';
                const rawArgs = call.function?.arguments ?? call.arguments ?? {};
                const args = typeof rawArgs === 'string' ? JSON.parse(rawArgs || '{}') : (rawArgs || {});
                const callId = call.id || '';
                console.log('[NOVA-FC] Tool call received:', funcName, args);
                setReply('正在执行: ' + funcName + '...');
                _handleFunctionCall(funcName, args, callId);
            }
        }
    }

    // ─── Function Calling 客户端执行 ────────────────────────
    const GROUPED_TOOLS = {
        cabin_control: true,
        media_nav_control: true,
        panel_control: true,
        unity_control: true,
    };

    function _handleFunctionCall(funcName, args, callId) {
        let realAction = funcName;
        let realParams = args;

        // 分组工具拆解：提取真实 action 和 params
        if (GROUPED_TOOLS[funcName] && args.action) {
            realAction = args.action;
            realParams = args.params || {};
            console.log('[NOVA-FC] Unpack grouped:', funcName, '→', realAction, realParams);
        }

        const normalized = _normalizeActionFromUserText(realAction, realParams);
        const backendFunction = normalized.changed ? normalized.action : funcName;
        const backendParams = normalized.changed ? normalized.params : args;
        realAction = normalized.action;
        realParams = normalized.params;

        // query_state 不需要前端执行（纯查询，后端返回结果给 AI 播报）
        if (realAction !== 'query_state' && window._executeFCAction) {
            const signature = _actionSignature(realAction, realParams);
            const recentlyDone = Date.now() - (recentInstantActions.get(signature) || 0) < 3600;
            if (!recentlyDone) window._executeFCAction(realAction, realParams);
        }

        // 通知后端执行（传原始分组工具名，让后端自己分发）
        fetch('/api/voice/fc-execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                room_id: ROOM_ID,
                function: backendFunction,
                params: backendParams,
                call_id: callId,
                client_executed: realAction !== 'query_state',
            }),
        }).then(r => r.json()).then(data => {
            setReply(data.result || ('已执行: ' + realAction));
        }).catch(() => {
            setReply('已执行: ' + realAction);
        });
    }

    function _isMusicService(params) {
        const service = String(params?.service || params?.card || params?.name || '').toLowerCase();
        return /music|音乐|歌曲|歌/.test(service);
    }

    function _looksLikeMusicPlayback(text) {
        return /播放|放一下|听|来一首|下一首|上一首|暂停|继续|starboy|晴天|blackpink|周杰伦|weeknd|jennie|lisa|ros[eé]|born|toxic|handlebars/i.test(text || '');
    }

    function _normalizeText(text) {
        return String(text || '').toLowerCase().replace(/\s+/g, '');
    }

    function _actionSignature(action, params) {
        return action + ':' + JSON.stringify(params || {});
    }

    function _boolIntentFromText(text) {
        const raw = text || '';
        if (/关闭|关掉|隐藏|收起|不要显示|close|hide/i.test(raw)) return false;
        if (/打开|开启|显示|展开|进入|切到|切换到|open|show/i.test(raw)) return true;
        return undefined;
    }

    function _dockActionsFromText(text) {
        const raw = text || '';
        const open = _boolIntentFromText(raw);
        if (open === undefined) return [];
        const actions = [];
        if (/导航|地图|路线|nav/i.test(raw)) actions.push({ action: 'toggle_navigation', params: { show: open } });
        if (/adas|ads|智驾|驾驶辅助|辅助驾驶|左侧/i.test(raw)) actions.push({ action: 'toggle_adas', params: { show: open } });
        if (/服务面板|服务列表|应用面板|应用列表|service/i.test(raw)) actions.push({ action: 'toggle_service_panel', params: { open } });
        if (/右侧卡片|卡片区|座舱卡片|cabin/i.test(raw)) actions.push({ action: 'toggle_cabin_cards', params: { show: open } });
        if (/3d|展车|车模|unity|三维/i.test(raw)) actions.push({ action: 'toggle_3d_scene', params: { show: open } });
        return actions;
    }

    function _serviceActionFromText(text) {
        const raw = text || '';
        const key = _normalizeText(raw);
        if (!/打开|开启|进入|看|我要|想|帮我|支付|付款|下单|点|播放|听/i.test(raw)) return null;
        if (/支付宝|支付|付款|付费|奶茶|下单|买单|结账|缴费/i.test(raw)) return { action: 'open_service_card', params: { service: 'alipay' } };
        if (/携程|机票|航班|酒店|旅行/i.test(raw)) return { action: 'open_service_card', params: { service: 'ctrip' } };
        if (/新闻|资讯/i.test(raw)) return { action: 'open_service_card', params: { service: 'news' } };
        if (/停车|车位/i.test(raw)) return { action: 'open_service_card', params: { service: 'parking' } };
        if (/充电|充电桩/i.test(raw)) return { action: 'open_service_card', params: { service: 'charging' } };
        if (/b站|bilibili|视频|电影|星际穿越|霸王别姬|普拉达|huntrix|interstellar/i.test(raw)) {
            if (/星际穿越|霸王别姬|普拉达|huntrix|interstellar|farewell|devil/i.test(raw)) {
                return { action: 'play_video', params: { title: raw } };
            }
            return { action: 'open_service_card', params: { service: 'bilibili' } };
        }
        if (_looksLikeMusicPlayback(raw)) {
            return {
                action: 'play_music',
                params: {
                    title: raw,
                    control: /暂停|停一下/i.test(raw) ? 'pause' : /下一首/i.test(raw) ? 'next' : /上一首/i.test(raw) ? 'prev' : 'play',
                }
            };
        }
        if (/音乐|歌曲/.test(key)) return { action: 'open_service_card', params: { service: 'music' } };
        return null;
    }

    function _navigationActionFromText(text) {
        const raw = text || '';
        if (!/去|到|导航|路线|目的地|下班/i.test(raw)) return null;
        if (/视角|镜头|相机|回到默认|默认视角/i.test(raw) && !/导航|路线|目的地/i.test(raw)) return null;
        if (/宇航员|太空人|astronaut/i.test(raw) && !/导航|路线|目的地|开车|带我|送我|去/i.test(raw)) return null;
        let destination = '';
        const match = raw.match(/(?:去|到|导航到|目的地是)(.+)$/);
        if (match) destination = match[1].replace(/吧|呀|啊|。|，|,/g, '').trim();
        if (/吃饭|餐厅|晚饭|午饭/i.test(raw)) destination = destination || '附近餐厅';
        if (/回家/i.test(raw)) destination = '家';
        if (/公司|上班/i.test(raw)) destination = '公司';
        if (!destination) return null;
        return { action: 'set_destination', params: { destination } };
    }

    function _cameraViewFromText(text) {
        const raw = text || '';
        if (/宇航员|太空人|astronaut/i.test(raw)) return 'astronaut';
        if (/车内|内部|座舱|内饰|interior/i.test(raw)) return 'carInterior';
        if (/正面|车头|车外|整车|车的视角|front|rear|top|后面|车尾|俯视|顶部/i.test(raw)) return 'carExterior';
        if (/回到默认|默认视角|default/i.test(raw)) return 'default';
        return '';
    }

    function _carPartFromText(text) {
        const raw = text || '';
        if (/右车门|右门|副驾门|doorr|rightdoor/i.test(raw)) return 'doorR';
        if (/左车门|左门|主驾门|车门|doorl|leftdoor|door/i.test(raw)) return 'doorL';
        if (/引擎盖|前盖|hood/i.test(raw)) return 'hood';
        if (/后备箱|尾箱|trunk/i.test(raw)) return 'trunk';
        if (/右车窗|windowr/i.test(raw)) return 'windowR';
        if (/左车窗|车窗|windowl|window/i.test(raw)) return 'windowL';
        return '';
    }

    function _rememberInstantAction(signature, roundKey) {
        const now = Date.now();
        recentInstantActions.set(signature, now);
        for (const [key, timestamp] of recentInstantActions) {
            if (now - timestamp > 8000) recentInstantActions.delete(key);
        }

        if (roundKey !== undefined && roundKey !== null && roundKey !== '') {
            const set = instantRoundActions.get(roundKey) || new Set();
            set.add(signature);
            instantRoundActions.set(roundKey, set);
            if (instantRoundActions.size > 8) {
                const firstKey = instantRoundActions.keys().next().value;
                instantRoundActions.delete(firstKey);
            }
        }
    }

    function _runInstantAction(action, params, meta) {
        if (!window._executeFCAction) return false;
        const signature = _actionSignature(action, params);
        const now = Date.now();
        const roundKey = meta && meta.roundId !== undefined && meta.roundId !== null ? String(meta.roundId) : '';
        if (roundKey && instantRoundActions.get(roundKey)?.has(signature)) return false;
        if (now - (recentInstantActions.get(signature) || 0) < 3600) return false;
        lastInstantSignature = signature;
        lastInstantAt = now;
        _rememberInstantAction(signature, roundKey);
        console.log('[NOVA-INSTANT]', action, params);
        window._executeFCAction(action, params || {});
        return true;
    }

    function _tryInstantHMIShortcut(text, meta) {
        const raw = text || '';
        const key = _normalizeText(raw);
        if (!key) return false;

        if (/关闭|清空|收起|关掉/.test(raw) && /卡片|这些|右侧/.test(raw)) {
            return _runInstantAction('close_all_cards', {}, meta);
        }

        const dockActions = _dockActionsFromText(raw);
        if (dockActions.length) {
            let executed = false;
            dockActions.forEach(item => {
                executed = _runInstantAction(item.action, item.params, meta) || executed;
            });
            return executed;
        }

        const view = _cameraViewFromText(raw);
        if (view) return _runInstantAction('switch_camera', { view }, meta);

        const navigation = _navigationActionFromText(raw);
        if (navigation) return _runInstantAction(navigation.action, navigation.params, meta);

        const service = _serviceActionFromText(raw);
        if (service) return _runInstantAction(service.action, service.params, meta);

        const wantsClose = /关闭|关上|合上|收起|close/i.test(raw);
        const wantsOpen = /打开|开启|开一下|open/i.test(raw);
        if (!wantsOpen && !wantsClose) return false;

        const part = _carPartFromText(raw);
        if (!part) return false;

        return _runInstantAction(wantsClose ? 'close_car_part' : 'open_car_part', {
            part,
            view: 'carExterior',
        }, meta);
    }

    function _normalizeActionFromUserText(action, params) {
        const nextParams = Object.assign({}, params || {});
        const utterance = lastUserText || (transcript ? transcript.textContent : '') || '';

        if (action === 'switch_camera') {
            const view = _cameraViewFromText(utterance);
            if (view && nextParams.view !== view) {
                nextParams.view = view;
                return { action, params: nextParams, changed: true };
            }
        }

        if (action === 'open_car_part' || action === 'close_car_part' || action === 'toggle_car_part') {
            const part = _carPartFromText(utterance);
            let changed = false;
            if (part && nextParams.part !== part) {
                nextParams.part = part;
                changed = true;
            }
            if (!nextParams.view) {
                nextParams.view = 'carExterior';
                changed = true;
            } else if (nextParams.view === 'default' || nextParams.view === 'astronaut' || nextParams.view === 'front' || nextParams.view === 'rear' || nextParams.view === 'top') {
                nextParams.view = 'carExterior';
                changed = true;
            }
            if (changed) return { action, params: nextParams, changed: true };
        }

        if (action === 'open_service_card' && /关闭|清空|收起|关掉/.test(utterance) && /卡片|这些|右侧/.test(utterance)) {
            return { action: 'close_all_cards', params: {}, changed: true };
        }

        if (action === 'set_destination') {
            const view = _cameraViewFromText(utterance);
            if (view) {
                return { action: 'switch_camera', params: { view }, changed: true };
            }
            const nav = _navigationActionFromText(utterance);
            if (nav && nav.params.destination && nextParams.destination !== nav.params.destination) {
                nextParams.destination = nav.params.destination;
                return { action, params: nextParams, changed: true };
            }
        }

        if (/^toggle_(adas|navigation|cabin_cards|service_panel|3d_scene)$/.test(action)) {
            const desired = _boolIntentFromText(utterance);
            if (desired !== undefined) {
                if (action === 'toggle_service_panel') {
                    if (nextParams.open !== desired) {
                        nextParams.open = desired;
                        return { action, params: nextParams, changed: true };
                    }
                } else if (nextParams.show !== desired) {
                    nextParams.show = desired;
                    return { action, params: nextParams, changed: true };
                }
            }
        }

        if (action === 'open_service_card' && _isMusicService(nextParams) && _looksLikeMusicPlayback(utterance)) {
            return {
                action: 'play_music',
                params: {
                    title: utterance,
                    control: /暂停|停一下/i.test(utterance) ? 'pause' : /下一首/i.test(utterance) ? 'next' : /上一首/i.test(utterance) ? 'prev' : 'play',
                },
                changed: true,
            };
        }

        if (action === 'play_music') {
            const hasSelector = nextParams.title || nextParams.artist || nextParams.query || nextParams.name;
            if (!hasSelector && utterance) {
                nextParams.title = utterance;
                return { action, params: nextParams, changed: true };
            }
        }

        return { action, params: nextParams, changed: false };
    }

    // ─── FC 消息处理（来自 WebSocket 推送的兼容接口） ───────
    window._novaHandleFCMessage = function(msg) {
        if (msg.type === 'fc_pending') {
            setReply('正在执行: ' + msg.function + '...');
        } else if (msg.type === 'fc_executed') {
            setReply(msg.result || ('已执行: ' + msg.function));
        }
    };

    // ─── 暴露全局 API ───────────────────────────────────────
    window.novaVoice = {
        start,
        stop,
        toggle,
        initWakeListener,
        get isActive() { return isActive; },
        get isWakeListening() { return wakeListening && !wakePaused; },
    };

    // ─── 自动启动唤醒监听 ───────────────────────────────────
    // AudioContext 必须在用户手势后才能启动（Chrome 安全策略）
    // 监听用户首次点击（锁屏点击即可触发）
    let _wakeInited = false;

    function _tryInitWake() {
        if (_wakeInited) return;
        _wakeInited = true;
        console.log('[WAKE] User gesture detected, starting wake listener...');
        setTimeout(() => initWakeListener(), 500);
    }

    document.addEventListener('click', _tryInitWake, { once: true });
    document.addEventListener('touchstart', _tryInitWake, { once: true });

})();
