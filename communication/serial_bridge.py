"""
串口通信桥接 - ESP32 舵机控制
以高频率将转向角发送给 ESP32，驱动舵机/电机

改动指南:
- 换串口号/波特率: 修改 settings.SERIAL_PORT / SERIAL_BAUD
- 改发送频率: 修改 settings.SERIAL_SEND_HZ
- 加速度/油门也要映射: 修改 _send_loop() 和 protocol.build_servo_packet()
- 改映射曲线: 修改 servo_mapper.py
- 用蓝牙代替串口: 替换 serial.Serial 为蓝牙 socket
"""

import threading
import time

try:
    import serial
except ImportError:
    serial = None
    print("[SERIAL] 警告: pyserial 未安装，串口功能不可用 (pip install pyserial)")

from config import settings
from core.vehicle_state import VehicleStateManager
from communication.protocol import build_servo_packet
from hardware.servo_mapper import ServoMapper


class SerialBridge:
    def __init__(self, state_manager: VehicleStateManager):
        self.state_manager = state_manager
        self.mapper = ServoMapper()
        self._serial = None
        self._running = False
        self._connected = False

    def start(self):
        """启动串口通信（非阻塞）"""
        if serial is None:
            print("[SERIAL] pyserial 未安装，跳过串口模块")
            return

        self._running = True
        self._connect_thread = threading.Thread(
            target=self._connect_and_send, daemon=True
        )
        self._connect_thread.start()

    def _connect_and_send(self):
        """连接串口并持续发送数据"""
        while self._running:
            # 尝试连接
            if not self._connected:
                try:
                    self._serial = serial.Serial(
                        port=settings.SERIAL_PORT,
                        baudrate=settings.SERIAL_BAUD,
                        timeout=settings.SERIAL_TIMEOUT
                    )
                    self._connected = True
                    print(f"[SERIAL] 已连接 {settings.SERIAL_PORT}")
                except Exception as e:
                    print(f"[SERIAL] 连接失败: {e}，5秒后重试...")
                    time.sleep(5)
                    continue

            # 发送循环
            self._send_loop()

    def _send_loop(self):
        """高频发送转向角数据"""
        interval = 1.0 / settings.SERIAL_SEND_HZ

        while self._running and self._connected:
            start = time.time()

            try:
                state = self.state_manager.get()

                # 通过映射器处理转向角（平滑、限幅等）
                mapped_angle = self.mapper.map(state.wheel_angle_deg)
                packet = build_servo_packet(mapped_angle, state.speed_kmh)

                self._serial.write(packet)
                self._serial.flush()

            except serial.SerialException as e:
                print(f"[SERIAL] 通信断开: {e}")
                self._connected = False
                try:
                    self._serial.close()
                except Exception:
                    pass
                break
            except Exception as e:
                print(f"[SERIAL] 发送错误: {e}")

            elapsed = time.time() - start
            sleep_time = max(0, interval - elapsed)
            time.sleep(sleep_time)

    @property
    def is_connected(self) -> bool:
        return self._connected

    def stop(self):
        self._running = False
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
        print("[SERIAL] 已停止")
