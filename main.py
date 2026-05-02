"""
智慧驾驶座舱 - 主入口
启动所有模块，协调各子系统

启动方式: python main.py
可选参数:
  --no-preview     不开 pygame 本地预览窗口
  --no-ai          不启动 AI 助手（没配 API Key 时用）
"""

import sys
import signal

from config import settings
from core.vehicle_state import VehicleStateManager
from core.carla_bridge import CarlaBridge
from communication.tcp_server import TCPServer
from ai_assistant.assistant_manager import AssistantManager
from hmi.unity_data_provider import UnityDataProvider


class SmartCockpitApp:
    def __init__(self):
        self.args = set(sys.argv[1:])

        # 核心: 共享的车辆状态管理器
        self.state_manager = VehicleStateManager()

        # 各子系统
        self.carla_bridge = CarlaBridge(self.state_manager)
        self.tcp_server = TCPServer(self.state_manager)
        self.ai_assistant = AssistantManager(self.state_manager)
        self.hmi_provider = UnityDataProvider(self.state_manager)

    def start(self):
        print("=" * 50)
        print("  智慧驾驶座舱系统 v1.0")
        print("=" * 50)

        # 1. CARLA 桥接（核心，必须启动）
        if "--no-preview" in self.args:
            self.carla_bridge.enable_preview = False
        self.carla_bridge.setup()

        # 2. TCP 服务端（Unity 连接）
        self.tcp_server.start()

        # 3. AI 助手
        if "--no-ai" not in self.args:
            self.ai_assistant.start(
                frame_getter=self.carla_bridge.get_latest_frame
            )
            # AI 回复时推送给 Unity HMI
            self.ai_assistant.on_reply(self.hmi_provider.push_ai_message)
        else:
            print("[MAIN] 跳过 AI 模块 (--no-ai)")

        print("\n[MAIN] 所有模块已启动!")
        print("[MAIN] Unity 连接: TCP {}:{}".format(
            settings.TCP_HOST, settings.TCP_PORT
        ))
        print("[MAIN] SPACE: 切换视角 | ESC: 退出\n")

        # 4. 启动 CARLA 主循环（阻塞）
        self.carla_bridge.run()

    def _poll_unity_messages(self):
        """检查 Unity 发来的消息（在主循环中调用）"""
        messages = self.tcp_server.get_pending_messages()
        for msg in messages:
            if msg.get("type") == "voice_command":
                text = msg.get("text", "")
                if text:
                    self.ai_assistant.process_user_input_async(text)

    def stop(self):
        print("\n[MAIN] 正在关闭所有模块...")
        self.carla_bridge.stop()
        self.tcp_server.stop()
        self.ai_assistant.stop()
        self.carla_bridge.cleanup()
        print("[MAIN] 系统已关闭")


def main():
    app = SmartCockpitApp()

    # 优雅关闭
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
