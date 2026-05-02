"""
智慧驾驶座舱 - 主入口
启动所有模块，协调各子系统

启动方式:
  python main.py --web-hmi             CARLA + Web HMI + AI
  python main.py --web-hmi --no-ai     CARLA + Web HMI（无AI）
  python main.py --web-hmi --mock-carla Mock数据 + Web HMI + AI
  python main.py --hmi-only            仅 Web HMI（Mock数据，无CARLA无AI）
  python main.py                       传统模式（CARLA + TCP Unity）
"""

import sys
import signal
import threading
import time

from config import settings
from core.vehicle_state import VehicleStateManager
from core.cabin_state import CabinStateManager
from core.service_executor import ServiceExecutor


class SmartCockpitApp:
    def __init__(self):
        self.args = set(sys.argv[1:])

        # 核心共享状态
        self.state_manager = VehicleStateManager()
        self.cabin_state = CabinStateManager()
        self.service_executor = ServiceExecutor(self.cabin_state, self.state_manager)

        # 各子系统（按需初始化）
        self.carla_bridge = None
        self.tcp_server = None
        self.ai_assistant = None
        self.service_agent = None
        self.web_hmi_thread = None

    def start(self):
        print("=" * 50)
        print("  智慧驾驶座舱系统 v2.0")
        print("=" * 50)

        use_web_hmi = "--web-hmi" in self.args or "--hmi-only" in self.args
        use_carla = "--hmi-only" not in self.args and "--mock-carla" not in self.args
        use_ai = "--no-ai" not in self.args and "--hmi-only" not in self.args
        use_tcp = not use_web_hmi

        # 1. CARLA 桥接
        if use_carla:
            from core.carla_bridge import CarlaBridge
            self.carla_bridge = CarlaBridge(self.state_manager)
            if "--no-preview" in self.args:
                self.carla_bridge.enable_preview = False
            self.carla_bridge.setup()
        else:
            print("[MAIN] CARLA 跳过（使用 Mock 数据）")
            self._start_mock_state()

        # 2. TCP 服务端（传统 Unity 模式）
        if use_tcp:
            from communication.tcp_server import TCPServer
            self.tcp_server = TCPServer(self.state_manager)
            self.tcp_server.start()

        # 3. Web HMI 服务端
        if use_web_hmi:
            from web_hmi.server import start_server
            self.web_hmi_thread = start_server(
                self.state_manager,
                cabin_state=self.cabin_state,
                service_executor=self.service_executor,
            )

        # 4. AI 助手 + 服务 Agent
        if use_ai:
            from ai_assistant.assistant_manager import AssistantManager
            from ai_assistant.service_agent import ServiceAgent

            self.ai_assistant = AssistantManager(self.state_manager)
            self.service_agent = ServiceAgent(
                self.cabin_state, self.state_manager, self.service_executor
            )

            frame_getter = self.carla_bridge.get_latest_frame if self.carla_bridge else None
            self.ai_assistant.start(frame_getter=frame_getter)

            # AI 回复推送到 Web HMI
            if use_web_hmi:
                from web_hmi.server import push_ai_message_sync
                self.ai_assistant.on_reply(push_ai_message_sync)
        else:
            print("[MAIN] 跳过 AI 模块")

        # 打印启动信息
        print(f"\n[MAIN] 所有模块已启动!")
        if use_web_hmi:
            print(f"[MAIN] Web HMI: http://localhost:{settings.WEB_HMI_PORT}")
        if use_tcp:
            print(f"[MAIN] Unity TCP: {settings.TCP_HOST}:{settings.TCP_PORT}")
        if use_carla:
            print("[MAIN] SPACE: 切换视角 | ESC: 退出\n")

        # 5. 主循环
        if self.carla_bridge:
            self.carla_bridge.run()
        else:
            self._idle_loop()

    def _start_mock_state(self):
        """模拟车辆状态数据（无 CARLA 时使用）"""
        import math

        def _mock_loop():
            t = 0
            while True:
                speed = 60 + 20 * math.sin(t * 0.1)
                steer = 0.3 * math.sin(t * 0.2)
                self.state_manager.update(
                    speed_kmh=speed,
                    throttle=0.5,
                    brake=0.0,
                    steer=steer,
                    gear=3,
                    is_reverse=False,
                    autopilot_enabled=True,
                    wheel_angle_deg=steer * 540,
                )
                t += 1
                time.sleep(1.0 / settings.VEHICLE_STATE_HZ)

        threading.Thread(target=_mock_loop, daemon=True).start()
        print("[MAIN] Mock 车辆状态已启动")

    def _idle_loop(self):
        """无 CARLA 时的空闲循环"""
        print("[MAIN] 空闲循环中（Ctrl+C 退出）")
        while True:
            time.sleep(1)

    def stop(self):
        print("\n[MAIN] 正在关闭所有模块...")
        if self.carla_bridge:
            self.carla_bridge.stop()
        if self.tcp_server:
            self.tcp_server.stop()
        if self.ai_assistant:
            self.ai_assistant.stop()
        if self.carla_bridge:
            self.carla_bridge.cleanup()
        print("[MAIN] 系统已关闭")


def main():
    app = SmartCockpitApp()

    def signal_handler(sig, frame):
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        app.start()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n[MAIN] 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        app.stop()


if __name__ == "__main__":
    main()
