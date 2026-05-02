"""
座舱状态管理
管理空调、座椅、车窗、氛围灯、座舱模式、用户状态等
由 ServiceExecutor 写入，Web HMI 读取
"""

import threading
from dataclasses import dataclass, field, asdict


@dataclass
class CabinState:
    # 空调
    ac_temperature: int = 24
    ac_on: bool = True

    # 座椅
    seat_ventilation: bool = False
    seat_heating: bool = False

    # 车窗
    window_open: bool = False

    # 氛围灯
    ambient_light: str = "柔白"

    # 座舱模式
    cabin_mode: str = "标准"

    # 音乐
    music_playing: bool = False
    music_title: str = ""

    # 用户状态（模拟感知）
    user_emotion: str = "正常"
    user_fatigue: bool = False
    thermal_comfort: str = "适宜"

    def to_dict(self) -> dict:
        return asdict(self)


class CabinStateManager:
    def __init__(self):
        self._state = CabinState()
        self._lock = threading.RLock()
        self._callbacks = []

    def update(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)

        for cb in self._callbacks:
            try:
                cb(self.get_dict())
            except Exception:
                pass

    def get(self) -> CabinState:
        with self._lock:
            return CabinState(**asdict(self._state))

    def get_dict(self) -> dict:
        with self._lock:
            return self._state.to_dict()

    def on_update(self, callback):
        self._callbacks.append(callback)
