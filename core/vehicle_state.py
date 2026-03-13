"""
车辆状态数据模型
所有模块共享的车辆数据都在这里定义
线程安全 - 使用锁保护读写
"""

import threading
import time
import math
from dataclasses import dataclass, field, asdict


@dataclass
class VehicleState:
    """车辆实时状态，所有数据由 CARLA Bridge 写入"""

    # 基础运动状态
    speed_kmh: float = 0.0              # 速度 km/h
    throttle: float = 0.0               # 油门 0~1
    brake: float = 0.0                  # 刹车 0~1
    steer: float = 0.0                  # 转向角 -1(左)~1(右)
    gear: int = 0                       # 档位
    is_reverse: bool = False            # 是否倒车

    # 位置和朝向
    location_x: float = 0.0
    location_y: float = 0.0
    location_z: float = 0.0
    rotation_yaw: float = 0.0          # 航向角（度）
    rotation_pitch: float = 0.0
    rotation_roll: float = 0.0

    # 车轮状态（用于 HMI 动画）
    wheel_angle_deg: float = 0.0       # 前轮转角（度），映射到舵机

    # 自动驾驶状态
    autopilot_enabled: bool = True
    current_speed_limit: float = 0.0   # 当前路段限速

    # 时间戳
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class VehicleStateManager:
    """
    线程安全的车辆状态管理器
    - CARLA Bridge (生产者) 调用 update() 写入
    - TCP Server / Serial Bridge / AI (消费者) 调用 get() 读取
    """

    def __init__(self):
        self._state = VehicleState()
        self._lock = threading.RLock()
        self._callbacks = []  # 状态变化回调

    def update(self, **kwargs):
        """更新车辆状态（由 CARLA Bridge 调用）"""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)
            self._state.timestamp = time.time()

        # 通知回调（不在锁内，避免死锁）
        for cb in self._callbacks:
            try:
                cb(self.get())
            except Exception:
                pass

    def get(self) -> VehicleState:
        """获取当前车辆状态的快照（线程安全拷贝）"""
        with self._lock:
            return VehicleState(**asdict(self._state))

    def get_dict(self) -> dict:
        """获取字典格式（方便 JSON 序列化）"""
        with self._lock:
            return self._state.to_dict()

    def on_update(self, callback):
        """注册状态更新回调"""
        self._callbacks.append(callback)

    def get_steer_angle_deg(self) -> float:
        """
        获取转向角（度数），用于舵机映射
        CARLA steer: -1.0 ~ 1.0
        映射为: -540 ~ 540 度（典型方向盘范围）
        """
        with self._lock:
            return self._state.steer * 540.0
