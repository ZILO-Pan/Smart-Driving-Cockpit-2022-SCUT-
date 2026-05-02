"""
服务执行器
接收 Agent 输出的结构化动作，执行到座舱/车辆/HMI 上
"""

from core.cabin_state import CabinStateManager
from core.vehicle_state import VehicleStateManager


class ServiceExecutor:
    def __init__(self, cabin_state: CabinStateManager, vehicle_state: VehicleStateManager):
        self.cabin = cabin_state
        self.vehicle = vehicle_state
        self._action_log = []

    def execute(self, action: str, params: dict = None) -> str:
        params = params or {}
        handler = self._handlers.get(action)
        if handler:
            result = handler(self, params)
            self._action_log.append({"action": action, "params": params, "result": result})
            return result
        return f"未知动作: {action}"

    def _set_ac_temperature(self, params):
        temp = params.get("temperature", 24)
        self.cabin.update(ac_temperature=temp)
        return f"空调已设置为 {temp}°C"

    def _set_seat_ventilation(self, params):
        on = params.get("on", True)
        self.cabin.update(seat_ventilation=on)
        return f"座椅通风已{'开启' if on else '关闭'}"

    def _toggle_window(self, params):
        open_it = params.get("open", True)
        self.cabin.update(window_open=open_it)
        return f"车窗已{'开启' if open_it else '关闭'}"

    def _set_ambient_light(self, params):
        color = params.get("color", "柔白")
        self.cabin.update(ambient_light=color)
        return f"氛围灯已切换为 {color}"

    def _play_music(self, params):
        title = params.get("title", "轻松音乐")
        self.cabin.update(music_playing=True, music_title=title)
        return f"正在播放: {title}"

    def _set_cabin_mode(self, params):
        mode = params.get("mode", "标准")
        self.cabin.update(cabin_mode=mode)
        if mode == "休息":
            self.cabin.update(ambient_light="暖橙", seat_ventilation=False)
        elif mode == "运动":
            self.cabin.update(ambient_light="红色")
        return f"座舱模式切换为: {mode}"

    def _show_alert(self, params):
        return f"提示: {params.get('message', '')}"

    def _set_destination(self, params):
        dest = params.get("destination", "")
        return f"导航目的地已设置: {dest}"

    def _change_lane(self, params):
        direction = params.get("direction", "左")
        return f"正在执行变道({direction})"

    def _open_service_card(self, params):
        service = params.get("service", "")
        return f"已打开服务卡片: {service}"

    def _set_user_state(self, params):
        if "emotion" in params:
            self.cabin.update(user_emotion=params["emotion"])
        if "fatigue" in params:
            self.cabin.update(user_fatigue=params["fatigue"])
        if "thermal" in params:
            self.cabin.update(thermal_comfort=params["thermal"])
        return "用户状态已更新"

    def get_log(self) -> list:
        return self._action_log[-20:]

    _handlers = {
        "set_ac_temperature": _set_ac_temperature,
        "set_seat_ventilation": _set_seat_ventilation,
        "toggle_window": _toggle_window,
        "set_ambient_light": _set_ambient_light,
        "play_music": _play_music,
        "set_cabin_mode": _set_cabin_mode,
        "show_alert": _show_alert,
        "set_destination": _set_destination,
        "change_lane": _change_lane,
        "open_service_card": _open_service_card,
        "set_user_state": _set_user_state,
    }
