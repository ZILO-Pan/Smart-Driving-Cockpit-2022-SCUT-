"""
视觉观察模块
定时 / 事件触发 两种模式分析 CARLA 摄像头画面

改动指南:
- 改定时播报间隔: settings.VISION_CAPTURE_INTERVAL
- 改分析 prompt: 修改 doubao_chat.py 里的 VISION_PROMPT
- 切换模式: settings.VISION_AUTO_BROADCAST / VISION_EVENT_ENABLED
"""

import threading
import time
import numpy as np

from config import settings
from cloud.chat.doubao_chat import DoubaoChat, VISION_PROMPT


class VisionObserver:
    def __init__(self, chat: DoubaoChat):
        self.chat = chat
        self._frame_getter = None
        self._running = False
        self._latest_analysis = ""
        self._lock = threading.Lock()
        self._on_broadcast_callbacks = []  # (text) → TTS 播报

    def start(self, frame_getter):
        """启动视觉观察"""
        self._frame_getter = frame_getter
        self._running = True

        self._thread = threading.Thread(
            target=self._observation_loop, daemon=True
        )
        self._thread.start()
        print(f"[VISION] 已启动 (定时={settings.VISION_AUTO_BROADCAST}, "
              f"间隔={settings.VISION_CAPTURE_INTERVAL}s)")

    def _observation_loop(self):
        """主循环: 定时截图 → 视觉分析 → 语音播报"""
        while self._running:
            time.sleep(settings.VISION_CAPTURE_INTERVAL)

            if not self._running:
                break

            frame = self._frame_getter()
            if frame is None:
                continue

            try:
                analysis = self.chat.chat_with_image(VISION_PROMPT, frame)
                with self._lock:
                    self._latest_analysis = analysis

                print(f"[VISION] 分析结果: {analysis[:60]}...")

                # 定时模式: 自动播报
                if settings.VISION_AUTO_BROADCAST:
                    self._broadcast(analysis)

            except Exception as e:
                print(f"[VISION] 分析失败: {e}")

    def analyze_now(self) -> str:
        """立即分析一次（事件触发用）"""
        if self._frame_getter is None:
            return "摄像头未就绪"

        frame = self._frame_getter()
        if frame is None:
            return "没有获取到画面"

        try:
            analysis = self.chat.chat_with_image(VISION_PROMPT, frame)
            with self._lock:
                self._latest_analysis = analysis
            return analysis
        except Exception as e:
            return f"视觉分析失败"

    def get_latest(self) -> str:
        with self._lock:
            return self._latest_analysis

    def on_broadcast(self, callback):
        """注册播报回调 callback(text)"""
        self._on_broadcast_callbacks.append(callback)

    def _broadcast(self, text: str):
        """通知所有监听者（通常是 TTS 模块）"""
        for cb in self._on_broadcast_callbacks:
            try:
                cb(text)
            except Exception as e:
                print(f"[VISION] 播报回调失败: {e}")

    def stop(self):
        self._running = False
        print("[VISION] 已停止")
