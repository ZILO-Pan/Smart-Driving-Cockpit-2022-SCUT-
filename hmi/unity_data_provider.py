"""
Unity HMI 数据提供层
在 TCP 原始数据之上，提供更高层的 HMI 状态包
例如: 导航提示、AI 对话气泡、告警等

改动指南:
- 给 Unity HMI 加新的显示数据: 在 build_hmi_update() 中添加
- 添加导航指令: 修改 navigation 部分
- 添加告警: 修改 alerts 部分
"""

import json
import struct
import time

from core.vehicle_state import VehicleStateManager


class UnityDataProvider:
    def __init__(self, state_manager: VehicleStateManager):
        self.state_manager = state_manager
        self._ai_messages = []   # 待显示的 AI 对话
        self._alerts = []        # 告警信息

    def push_ai_message(self, user_text: str, ai_reply: str):
        """推送一条 AI 对话（Unity 在 HMI 上显示对话气泡）"""
        self._ai_messages.append({
            "user": user_text,
            "assistant": ai_reply,
            "time": time.time()
        })
        # 只保留最近5条
        self._ai_messages = self._ai_messages[-5:]

    def push_alert(self, level: str, message: str):
        """
        推送告警
        level: "info" / "warning" / "danger"
        """
        self._alerts.append({
            "level": level,
            "message": message,
            "time": time.time()
        })
        # 只保留最近3条，超过10秒自动过期
        now = time.time()
        self._alerts = [
            a for a in self._alerts[-3:] if now - a["time"] < 10.0
        ]

    def build_hmi_update(self) -> bytes:
        """
        构建完整的 HMI 更新包（包含车辆状态 + AI + 告警）
        可替代或补充 tcp_server 的基础推送
        """
        state = self.state_manager.get()

        packet = {
            "type": "hmi_update",
            "timestamp": time.time(),
            "vehicle": {
                "speed_kmh": round(state.speed_kmh, 1),
                "steer": round(state.steer, 4),
                "gear": state.gear,
                "autopilot": state.autopilot_enabled,
            },
            "ai_messages": self._ai_messages,
            "alerts": self._alerts,
        }

        json_bytes = json.dumps(packet, ensure_ascii=False).encode('utf-8')
        return struct.pack('<I', len(json_bytes)) + json_bytes
