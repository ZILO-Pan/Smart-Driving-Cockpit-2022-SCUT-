"""
豆包 AI 对话接口
处理用户的文字对话请求

改动指南:
- 换模型: 修改 settings.DOUBAO_CHAT_MODEL
- 改 system prompt: 修改 SYSTEM_PROMPT
- 加 function calling: 在 _build_request() 里加 tools 字段
- 换成其他 LLM (OpenAI 等): 改 API 地址和请求格式
"""

import requests
import threading
from collections import deque

from config import settings


SYSTEM_PROMPT = """你是一个智能驾驶座舱AI助手，名叫"小驾"。你运行在一辆 L4 级自动驾驶汽车中。

你的能力:
1. 回答驾驶相关问题（路况、导航、交通规则等）
2. 闲聊和娱乐（讲笑话、播放音乐建议等）
3. 解读车辆状态（当前速度、是否自动驾驶等）
4. 安全提醒（提醒乘客系安全带、路况变化等）

注意事项:
- 回复简洁友好，适合车载语音播报（尽量控制在2-3句话）
- 如果涉及安全问题，始终优先提醒安全
- 你可以访问车辆的实时状态数据
"""


class DoubaoChat:
    def __init__(self):
        self._history = deque(maxlen=settings.DOUBAO_MAX_HISTORY * 2)
        self._lock = threading.Lock()

    def chat(self, user_text: str, vehicle_state: dict = None) -> str:
        """
        同步对话（会阻塞直到返回）
        user_text: 用户说的话
        vehicle_state: 可选，当前车辆状态
        返回: AI 回复文字
        """
        # 构建带车辆状态的用户消息
        enriched_text = user_text
        if vehicle_state:
            speed = vehicle_state.get('speed_kmh', 0)
            autopilot = vehicle_state.get('autopilot_enabled', True)
            enriched_text = (
                f"[车辆状态: 速度{speed:.0f}km/h, "
                f"{'自动驾驶中' if autopilot else '手动驾驶'}]\n"
                f"用户说: {user_text}"
            )

        with self._lock:
            self._history.append({"role": "user", "content": enriched_text})

        # 调用 API
        try:
            response = self._call_api()
            reply = response.get("choices", [{}])[0].get(
                "message", {}
            ).get("content", "抱歉，我没有听清。")
        except Exception as e:
            reply = f"AI 服务暂时不可用: {str(e)[:50]}"
            print(f"[AI-CHAT] API 调用失败: {e}")

        with self._lock:
            self._history.append({"role": "assistant", "content": reply})

        return reply

    def chat_async(self, user_text: str, callback, vehicle_state: dict = None):
        """
        异步对话（不阻塞，结果通过 callback 返回）
        callback(reply_text: str)
        """
        def _run():
            reply = self.chat(user_text, vehicle_state)
            callback(reply)

        threading.Thread(target=_run, daemon=True).start()

    def _call_api(self) -> dict:
        """调用豆包 API"""
        with self._lock:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ] + list(self._history)

        url = f"{settings.DOUBAO_API_BASE}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.DOUBAO_API_KEY}"
        }
        payload = {
            "model": settings.DOUBAO_CHAT_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 512,
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def clear_history(self):
        """清除对话历史"""
        with self._lock:
            self._history.clear()
