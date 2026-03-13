"""
AI 助手管理器
统一管理对话和视觉分析，处理来自各渠道的请求

改动指南:
- 加语音识别 (ASR): 在 handle_voice_input() 接入 ASR API
- 加语音合成 (TTS): 在 _on_reply() 接入 TTS API
- 改对话策略: 修改 process_user_input() 的逻辑
"""

import threading
from core.vehicle_state import VehicleStateManager
from ai_assistant.doubao_chat import DoubaoChat
from ai_assistant.doubao_vision import DoubaoVision


class AssistantManager:
    def __init__(self, state_manager: VehicleStateManager):
        self.state_manager = state_manager
        self.chat = DoubaoChat()
        self.vision = DoubaoVision()
        self._reply_callbacks = []

    def start(self, frame_getter=None):
        """
        启动 AI 助手
        frame_getter: 获取摄像头画面的函数（来自 CarlaBridge）
        """
        if frame_getter:
            self.vision.start_periodic(frame_getter)
        print("[AI] 助手管理器已启动")

    def process_user_input(self, text: str) -> str:
        """
        处理用户输入（同步）
        自动携带车辆状态和最新路况分析
        """
        vehicle_state = self.state_manager.get_dict()

        # 如果用户问路况相关，附加视觉分析结果
        vision_keywords = ["路况", "前面", "看到", "路上", "前方", "周围"]
        enriched = text
        if any(kw in text for kw in vision_keywords):
            latest_vision = self.vision.get_latest_analysis()
            if latest_vision:
                enriched = f"{text}\n[视觉助手分析: {latest_vision}]"

        return self.chat.chat(enriched, vehicle_state)

    def process_user_input_async(self, text: str, callback=None):
        """异步处理用户输入"""
        def _run():
            reply = self.process_user_input(text)
            if callback:
                callback(reply)
            for cb in self._reply_callbacks:
                cb(text, reply)

        threading.Thread(target=_run, daemon=True).start()

    def on_reply(self, callback):
        """注册回复回调 callback(user_text, reply_text)"""
        self._reply_callbacks.append(callback)

    def stop(self):
        self.vision.stop()
        print("[AI] 助手管理器已停止")
