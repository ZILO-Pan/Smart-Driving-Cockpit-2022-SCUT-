"""
舵机映射逻辑
将 CARLA 的转向角映射到物理舵机角度
包含平滑滤波和限幅保护

改动指南:
- 改舵机角度范围: 修改 SERVO_MIN_DEG / SERVO_MAX_DEG
- 改平滑程度: 修改 SMOOTHING_FACTOR (0=不平滑, 1=完全不动)
- 改映射曲线(线性→非线性): 修改 map() 方法
- 加死区: 修改 _apply_deadzone()
"""

import time


class ServoMapper:
    # 舵机角度范围（根据你的舵机型号调整）
    SERVO_MIN_DEG = -90.0    # 舵机最左
    SERVO_MAX_DEG = 90.0     # 舵机最右

    # CARLA 方向盘角度范围
    CARLA_STEER_RANGE = 540.0  # -540 ~ +540

    # 指数移动平均平滑系数 (0.0~1.0)
    # 越大越平滑但延迟越高，0.3 是个不错的起点
    SMOOTHING_FACTOR = 0.3

    # 死区（度数），避免抖动
    DEADZONE_DEG = 2.0

    # 最大变化速率（度/秒），防止舵机打太快损坏
    MAX_RATE_DEG_PER_SEC = 720.0

    def __init__(self):
        self._prev_output = 0.0
        self._prev_time = time.time()

    def map(self, carla_steer_deg: float) -> float:
        """
        输入: CARLA 转向角 (-540 ~ 540)
        输出: 舵机角度 (SERVO_MIN ~ SERVO_MAX)
        """
        now = time.time()
        dt = now - self._prev_time
        self._prev_time = now

        # 1. 线性映射: CARLA范围 → 舵机范围
        ratio = carla_steer_deg / self.CARLA_STEER_RANGE
        target = ratio * (self.SERVO_MAX_DEG - self.SERVO_MIN_DEG)

        # 2. 限幅
        target = max(self.SERVO_MIN_DEG, min(self.SERVO_MAX_DEG, target))

        # 3. 死区
        target = self._apply_deadzone(target)

        # 4. 平滑滤波 (EMA)
        smoothed = (
            self.SMOOTHING_FACTOR * self._prev_output +
            (1.0 - self.SMOOTHING_FACTOR) * target
        )

        # 5. 限速保护
        if dt > 0:
            max_delta = self.MAX_RATE_DEG_PER_SEC * dt
            delta = smoothed - self._prev_output
            if abs(delta) > max_delta:
                smoothed = self._prev_output + max_delta * (1 if delta > 0 else -1)

        self._prev_output = smoothed
        return round(smoothed, 2)

    def _apply_deadzone(self, angle: float) -> float:
        """死区处理：角度太小时归零"""
        if abs(angle) < self.DEADZONE_DEG:
            return 0.0
        return angle

    def reset(self):
        """复位到中间位置"""
        self._prev_output = 0.0
        self._prev_time = time.time()
