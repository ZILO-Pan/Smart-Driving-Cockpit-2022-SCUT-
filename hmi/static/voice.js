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

        let parsed;
        try {
            parsed = JSON.parse(payload);
        } catch (e) {
            return;
        }

        if (magic === 'subt' || parsed.text !== undefined) {
            const text = parsed.text || parsed.data || '';
            const isUser = parsed.role === 'user' || parsed.is_user;
            if (isUser) {
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
                const args = JSON.parse(call.function?.arguments || call.arguments || '{}');
                const callId = call.id || '';
                console.log('[NOVA-FC] Tool call received:', funcName, args);
                setReply('正在执行: ' + funcName + '...');
                _handleFunctionCall(funcName, args, callId);
            }
        }
    }

    // ─── Function Calling 客户端执行 ────────────────────────
    function _handleFunctionCall(funcName, args, callId) {
        // 通过 app.js 暴露的 _executeFCAction 执行
        if (window._executeFCAction) {
            window._executeFCAction(funcName, args);
        }
        // 同时通知后端执行（状态同步 + 可选的 UpdateVoiceChat）
        fetch('/api/voice/fc-execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                room_id: ROOM_ID,
                function: funcName,
                params: args,
                call_id: callId,
            }),
        }).then(r => r.json()).then(data => {
            setReply(data.result || ('已执行: ' + funcName));
        }).catch(() => {
            setReply('已执行: ' + funcName);
        });
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
