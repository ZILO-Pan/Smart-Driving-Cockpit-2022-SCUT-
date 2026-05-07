# 常用命令

## Git 推送到 GitHub

```bash
# 代理可用时直接推
git add -A
git commit -m "提交说明"
git push origin main

# 代理不可用时（绕过 Clash 7897 端口）
git add -A
git commit -m "提交说明"
git -c http.proxy="" -c https.proxy="" push origin main

# 如果远程有新提交，先拉再推
git -c http.proxy="" -c https.proxy="" pull origin main --rebase
git -c http.proxy="" -c https.proxy="" push origin main
```

## 清理 __pycache__

```powershell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Where-Object { $_.FullName -notlike "*\.venv\*" } | Remove-Item -Recurse -Force
```

## 启动项目

```bash
# 标准模式：Mock 数据 + Web HMI + NOVA 语音
python main.py --web-hmi --mock-carla

# 连接 CARLA 仿真器
python main.py --web-hmi

# 仅 HMI（无 AI 无 CARLA）
python main.py --hmi-only

# 旧版本地语音（PyAudio，需 --legacy-voice）
python main.py --web-hmi --mock-carla --legacy-voice
```

## 清理旧文件（已废弃的 TTS/ASR 本地语音方案）

```bash
git rm cloud/voice/microphone_asr.py
git rm cloud/voice/speaker_tts.py
git rm cloud/agent/assistant_manager.py
git rm cloud/agent/service_agent.py
git rm cloud/chat/doubao_chat.py
git rm cloud/vision/doubao_vision.py
git rm communication/protocol.py
git rm communication/tcp_server.py
git rm test_rtc_voice.py
git rm VOLC_REALTIME_VOICE_INTEGRATION.md
git rm UNITY_INTEGRATION_TASKS.md
git rm -r handoff/
git rm cloud/chat/__init__.py
git rm cloud/vision/__init__.py
git rm cloud/agent/__init__.py

git add -A
git commit -m "清理旧 TTS/ASR 本地语音方案，保留 RTC 端到端架构"
git -c http.proxy="" -c https.proxy="" push origin main
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 查看 Git 状态

```bash
git status
git log --oneline -10
```
