"""
服务编排 Agent
将用户输入交给大模型，大模型输出结构化 JSON 动作
再由 ServiceExecutor 执行

输出格式:
{
  "intent": "thermal_comfort",
  "confidence": 0.95,
  "reply": "好的，我帮你把空调调低一点",
  "actions": [
    {"action": "set_ac_temperature", "params": {"temperature": 22}}
  ]
}
"""

import json
import requests
import threading

from config import settings
from core.cabin_state import CabinStateManager
from core.vehicle_state import VehicleStateManager
from core.service_executor import ServiceExecutor

SERVICE_AGENT_PROMPT = """你是智能驾驶座舱AI助手"小驾"，运行在L4级自动驾驶汽车中。
你需要理解用户的模糊需求，推断意图，并输出结构化 JSON 来执行座舱服务。

你必须严格按以下 JSON 格式回复（不要有其他内容）：
{
  "intent": "意图类别",
  "confidence": 0.0到1.0的置信度,
  "reply": "简洁的语音回复（不超过50字）",
  "actions": [
    {"action": "动作名", "params": {参数}}
  ]
}

可用意图类别：
thermal_comfort, emotion_companion, entertainment, fatigue_safety, driving_control, navigation, local_life, news, video, general_chat, unknown

可用动作：
- set_ac_temperature: {"temperature": 数字}
- set_seat_ventilation: {"on": true/false}
- toggle_window: {"open": true/false}
- set_ambient_light: {"color": "颜色名"}
- play_music: {"title": "歌名或类型"}
- set_cabin_mode: {"mode": "标准/休息/运动/影院"}
- show_alert: {"message": "提示内容"}
- set_destination: {"destination": "目的地"}
- change_lane: {"direction": "左/右"}
- open_service_card: {"service": "flight/milktea/news/video"}
- set_user_state: {"emotion": "正常/开心/难过/疲惫", "fatigue": true/false, "thermal": "热/冷/适宜"}

示例：
用户说"好热啊"
回复：{"intent":"thermal_comfort","confidence":0.92,"reply":"确实有点热，我帮你把空调调低两度，再开一下座椅通风","actions":[{"action":"set_ac_temperature","params":{"temperature":22}},{"action":"set_seat_ventilation","params":{"on":true}},{"action":"set_user_state","params":{"thermal":"热"}}]}

用户说"帮我订一张去上海的机票"
回复：{"intent":"local_life","confidence":0.95,"reply":"好的，已为你打开机票预订","actions":[{"action":"open_service_card","params":{"service":"flight"}},{"action":"set_destination","params":{"destination":"上海"}}]}

用户说"帮我换到左车道"
回复：{"intent":"driving_control","confidence":0.90,"reply":"好的，正在执行向左变道","actions":[{"action":"change_lane","params":{"direction":"左"}}]}

注意：
- 回复要简洁自然，适合语音播报
- 可以同时执行多个动作
- 如果用户只是闲聊，intent 设为 general_chat，actions 为空数组
- 驾驶控制类动作要在 reply 中提醒安全确认
"""


class ServiceAgent:
    def __init__(self, cabin_state: CabinStateManager, vehicle_state: VehicleStateManager,
                 service_executor: ServiceExecutor):
        self.cabin_state = cabin_state
        self.vehicle_state = vehicle_state
        self.executor = service_executor
        self._url = f"{settings.ARK_API_BASE}/chat/completions"
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.ARK_API_KEY}"
        }
        self._on_result_callbacks = []

    def process(self, user_text: str) -> dict:
        """
        同步处理用户输入，返回结构化结果
        """
        context = self._build_context()

        messages = [
            {"role": "system", "content": SERVICE_AGENT_PROMPT},
            {"role": "user", "content": f"{context}\n用户说: {user_text}"}
        ]

        payload = {
            "model": settings.ARK_ENDPOINT_ID,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 512,
        }

        try:
            resp = requests.post(self._url, json=payload, headers=self._headers, timeout=15)
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            result = self._parse_response(raw)
        except Exception as e:
            print(f"[AGENT] 调用失败: {e}")
            result = {
                "intent": "unknown",
                "confidence": 0.0,
                "reply": "抱歉，我暂时无法处理这个请求",
                "actions": []
            }

        # 执行动作
        for act in result.get("actions", []):
            action_name = act.get("action", "")
            params = act.get("params", {})
            self.executor.execute(action_name, params)

        # 通知回调
        for cb in self._on_result_callbacks:
            try:
                cb(user_text, result)
            except Exception:
                pass

        return result

    def process_async(self, user_text: str, callback=None):
        def _run():
            result = self.process(user_text)
            if callback:
                callback(result)
        threading.Thread(target=_run, daemon=True).start()

    def on_result(self, callback):
        self._on_result_callbacks.append(callback)

    def _build_context(self) -> str:
        v = self.vehicle_state.get_dict()
        c = self.cabin_state.get_dict()
        return (
            f"[车辆状态: 速度{v.get('speed_kmh', 0):.0f}km/h, "
            f"{'自动驾驶' if v.get('autopilot_enabled') else '手动'}]\n"
            f"[座舱状态: 空调{c.get('ac_temperature')}°C, "
            f"模式={c.get('cabin_mode')}, "
            f"用户情绪={c.get('user_emotion')}, "
            f"疲劳={'是' if c.get('user_fatigue') else '否'}]"
        )

    def _parse_response(self, raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {
                "intent": "general_chat",
                "confidence": 0.5,
                "reply": raw[:100],
                "actions": []
            }
