"""
豆包大模型对话接口 (火山方舟 Responses API)
同时支持纯文字对话和图片+文字多模态输入

改动指南:
- 改 system prompt: 修改 SYSTEM_PROMPT
- 换模型/接入点: 修改 settings.ARK_ENDPOINT_ID
- 加 function calling: 在 payload 里加 tools 字段
"""

import requests
import threading
import base64
import io
from collections import deque

import numpy as np

try:
    from PIL import Image
except ImportError:
    Image = None

from config import settings


SYSTEM_PROMPT = """你是一个智能驾驶座舱AI助手，名叫"小驾"。你运行在一辆 L4 级自动驾驶汽车中。

你的能力:
1. 观察前方路况（通过摄像头画面）并主动提醒驾驶安全
2. 回答驾驶相关问题（路况、导航、交通规则等）
3. 闲聊和娱乐（讲笑话、推荐音乐等）
4. 解读车辆状态（当前速度、是否自动驾驶等）

注意事项:
- 回复简洁友好，适合车载语音播报（控制在2-3句话，不超过80字）
- 不要使用markdown格式、列表符号、星号等，只用纯文本
- 如果涉及安全问题，始终优先提醒安全
- 你可以访问车辆的实时状态数据
"""

VISION_PROMPT = """你是一个智能驾驶视觉分析助手。请分析这张来自自动驾驶汽车前方摄像头的画面。

请用2-3句话简要描述:
1. 道路状况和前方车辆/行人情况
2. 是否有需要注意的安全隐患

回复要简洁自然，像一个副驾在和你聊天一样，不要用列表格式。"""


class DoubaoChat:
    def __init__(self):
        self._history = deque(maxlen=settings.DOUBAO_MAX_HISTORY * 2)
        self._lock = threading.Lock()
        self._url = f"{settings.ARK_API_BASE}/chat/completions"
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.ARK_API_KEY}"
        }

    def chat(self, user_text: str, vehicle_state: dict = None) -> str:
        """纯文字对话"""
        enriched = user_text
        if vehicle_state:
            speed = vehicle_state.get('speed_kmh', 0)
            autopilot = vehicle_state.get('autopilot_enabled', True)
            enriched = (
                f"[车辆状态: 速度{speed:.0f}km/h, "
                f"{'自动驾驶中' if autopilot else '手动驾驶'}]\n"
                f"用户说: {user_text}"
            )

        with self._lock:
            self._history.append({"role": "user", "content": enriched})

        try:
            reply = self._call_text_api()
        except Exception as e:
            reply = f"AI暂时无法回复"
            print(f"[CHAT] API 调用失败: {e}")

        with self._lock:
            self._history.append({"role": "assistant", "content": reply})

        return reply

    def chat_with_image(self, text: str, frame: np.ndarray) -> str:
        """带图片的多模态对话（用于视觉分析）"""
        if Image is None or frame is None:
            return self.chat(text)

        b64 = self._frame_to_base64(frame)

        try:
            reply = self._call_vision_api(text, b64)
        except Exception as e:
            reply = "视觉分析暂不可用"
            print(f"[VISION] API 调用失败: {e}")

        return reply

    def _frame_to_base64(self, frame: np.ndarray) -> str:
        """numpy BGR → JPEG base64"""
        img = Image.fromarray(frame[:, :, ::-1])  # BGR → RGB
        # 缩小图片以减少 API 延迟和成本
        img.thumbnail((640, 480))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60)
        return base64.b64encode(buf.getvalue()).decode('utf-8')

    def _call_text_api(self) -> str:
        """调用纯文字对话 API"""
        with self._lock:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ] + list(self._history)

        payload = {
            "model": settings.ARK_ENDPOINT_ID,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 256,
        }

        resp = requests.post(
            self._url, json=payload, headers=self._headers, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def _call_vision_api(self, text: str, image_b64: str) -> str:
        """调用视觉理解 API（多模态）"""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        }
                    }
                ]
            }
        ]

        payload = {
            "model": settings.ARK_ENDPOINT_ID,
            "messages": messages,
            "max_tokens": 256,
        }

        resp = requests.post(
            self._url, json=payload, headers=self._headers, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def chat_async(self, user_text: str, callback, vehicle_state: dict = None):
        """异步对话"""
        def _run():
            reply = self.chat(user_text, vehicle_state)
            callback(reply)
        threading.Thread(target=_run, daemon=True).start()

    def clear_history(self):
        with self._lock:
            self._history.clear()
