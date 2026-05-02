"""
AI 助手管理器 (完整版)
统一编排: 视觉观察 + 语音识别 + 大模型对话 + 语音合成

数据流:
  麦克风 → ASR识别 → 大模型对话(附带车辆状态+路况) → TTS语音播放
  CARLA画面 → 定时/事件截图 → 大模型视觉分析 → TTS语音播报

改动指南:
- 改 AI 播报逻辑: 修改 _on_user_speech()
- 加新的触发条件: 修改 _on_vision_broadcast()
- 接 Unity HMI: 用 on_reply() 注册回调
"""

import threading
from edge.state.vehicle_state import VehicleStateManager
from cloud.chat.doubao_chat import DoubaoChat
from cloud.vision.doubao_vision import VisionObserver
from cloud.voice.microphone_asr import MicrophoneASR
from cloud.voice.speaker_tts import Speaker


class AssistantManager:
    def __init__(self, state_manager: VehicleStateManager):
        self.state_manager = state_manager

        # 各子模块
        self.chat = DoubaoChat()
        self.vision = VisionObserver(self.chat)
        self.asr = MicrophoneASR()
        self.speaker = Speaker()

        # 外部回调（给 Unity HMI 用）
        self._reply_callbacks = []

    def start(self, frame_getter=None):
        """启动所有 AI 模块"""

        # 1. TTS 开始/结束时，暂停/恢复 ASR（防止回声）
        self.speaker.on_start(self.asr.pause)
        self.speaker.on_end(self.asr.resume)

        # 2. 启动视觉观察
        if frame_getter:
            self.vision.start(frame_getter)
            # 视觉播报 → TTS 说出来
            self.vision.on_broadcast(self._on_vision_broadcast)

        # 3. 启动麦克风 ASR
        self.asr.on_text(self._on_user_speech)
        self.asr.start()

        # 4. 开机问候
        self.speaker.speak("你好，我是小驾，智能驾驶座舱助手已启动。有什么可以帮你的？")

        print("[AI] 助手管理器已启动（视觉+对话+语音）")

    def _on_user_speech(self, text: str):
        """
        用户说了一句话（ASR 回调）
        → 调大模型对话 → TTS 回复
        """
        print(f"[AI] 用户说: {text}")

        # 获取车辆状态
        vehicle_state = self.state_manager.get_dict()

        # 如果用户问路况，附加最新视觉分析
        vision_keywords = ["路况", "前面", "看到", "路上", "前方", "周围", "什么情况"]
        enriched = text
        if any(kw in text for kw in vision_keywords):
            # 先做一次即时视觉分析
            latest = self.vision.analyze_now()
            if latest:
                enriched = f"{text}\n[视觉分析: {latest}]"

        # 调大模型
        def _process():
            reply = self.chat.chat(enriched, vehicle_state)
            print(f"[AI] 回复: {reply}")

            # TTS 播放
            self.speaker.speak(reply)

            # 通知外部（Unity HMI 等）
            for cb in self._reply_callbacks:
                try:
                    cb(text, reply)
                except Exception:
                    pass

        threading.Thread(target=_process, daemon=True).start()

    def _on_vision_broadcast(self, analysis: str):
        """视觉模块定时播报回调 → TTS 说出来"""
        # 如果正在和用户对话，不打断
        if self.speaker.is_speaking:
            return

        print(f"[AI] 路况播报: {analysis[:50]}...")
        self.speaker.speak(analysis)

        # 通知外部
        for cb in self._reply_callbacks:
            try:
                cb("[路况播报]", analysis)
            except Exception:
                pass

    def process_user_input(self, text: str) -> str:
        """手动文字输入（供 Unity TCP 消息调用）"""
        vehicle_state = self.state_manager.get_dict()
        reply = self.chat.chat(text, vehicle_state)
        self.speaker.speak(reply)
        return reply

    def process_user_input_async(self, text: str, callback=None):
        """异步文字输入"""
        def _run():
            reply = self.process_user_input(text)
            if callback:
                callback(reply)
        threading.Thread(target=_run, daemon=True).start()

    def on_reply(self, callback):
        """注册回复回调 callback(user_text, reply_text)"""
        self._reply_callbacks.append(callback)

    def stop(self):
        self.asr.stop()
        self.vision.stop()
        print("[AI] 助手管理器已停止")
