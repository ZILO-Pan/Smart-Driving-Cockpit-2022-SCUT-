"""
TCP 服务端 - Unity HMI 连接
异步推送车辆状态给 Unity，同时接收 Unity 发来的用户指令

改动指南:
- 调整发送频率: 修改 settings.TCP_SEND_HZ
- 增加发送的数据: 修改 protocol.build_unity_packet()
- 处理 Unity 发来的新指令: 修改 _handle_client_messages()
- 多 Unity 客户端: 当前支持多连接，无需修改
"""

import socket
import threading
import time
import struct

from config import settings
from edge.state.vehicle_state import VehicleStateManager
from communication.protocol import build_unity_packet, parse_unity_message


class TCPServer:
    def __init__(self, state_manager: VehicleStateManager):
        self.state_manager = state_manager
        self._server_socket = None
        self._clients = []  # [(socket, address), ...]
        self._clients_lock = threading.Lock()
        self._running = False

        # Unity 发来的消息队列（供其他模块消费）
        self._incoming_messages = []
        self._msg_lock = threading.Lock()

    def start(self):
        """启动 TCP 服务端（非阻塞，开新线程）"""
        self._running = True

        # 监听线程
        self._accept_thread = threading.Thread(
            target=self._accept_loop, daemon=True
        )
        self._accept_thread.start()

        # 推送线程
        self._push_thread = threading.Thread(
            target=self._push_loop, daemon=True
        )
        self._push_thread.start()

        print(f"[TCP] 服务端已启动 {settings.TCP_HOST}:{settings.TCP_PORT}")

    def _accept_loop(self):
        """接受新的 Unity 客户端连接"""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.settimeout(1.0)
        self._server_socket.bind((settings.TCP_HOST, settings.TCP_PORT))
        self._server_socket.listen(settings.TCP_MAX_CLIENTS)

        while self._running:
            try:
                client_sock, addr = self._server_socket.accept()
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                print(f"[TCP] Unity 客户端已连接: {addr}")

                with self._clients_lock:
                    self._clients.append((client_sock, addr))

                # 为每个客户端开一个接收线程
                threading.Thread(
                    target=self._receive_loop,
                    args=(client_sock, addr),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print(f"[TCP] 接受连接错误: {e}")

    def _receive_loop(self, client_sock, addr):
        """接收 Unity 发来的消息"""
        buffer = b""
        while self._running:
            try:
                data = client_sock.recv(4096)
                if not data:
                    break
                buffer += data

                # 尝试解析完整消息
                while len(buffer) >= 4:
                    msg_len = struct.unpack('<I', buffer[:4])[0]
                    if len(buffer) < 4 + msg_len:
                        break

                    msg = parse_unity_message(buffer[:4 + msg_len])
                    buffer = buffer[4 + msg_len:]

                    if msg:
                        self._handle_client_message(msg, addr)
            except Exception:
                break

        # 客户端断开
        print(f"[TCP] Unity 客户端断开: {addr}")
        with self._clients_lock:
            self._clients = [(s, a) for s, a in self._clients if a != addr]
        try:
            client_sock.close()
        except Exception:
            pass

    def _handle_client_message(self, msg: dict, addr):
        """
        处理 Unity 发来的消息
        例如: 用户在 HMI 上输入了语音指令
        """
        msg_type = msg.get("type", "")

        if msg_type == "voice_command":
            # 语音指令 → 转发给 AI 助手
            with self._msg_lock:
                self._incoming_messages.append(msg)
            print(f"[TCP] 收到语音指令: {msg.get('text', '')}")

        elif msg_type == "hmi_action":
            # HMI 按钮操作
            print(f"[TCP] 收到 HMI 操作: {msg.get('action', '')}")

    def get_pending_messages(self) -> list:
        """获取并清空待处理的 Unity 消息"""
        with self._msg_lock:
            msgs = self._incoming_messages.copy()
            self._incoming_messages.clear()
            return msgs

    def _push_loop(self):
        """定时推送车辆状态给所有 Unity 客户端"""
        interval = 1.0 / settings.TCP_SEND_HZ

        while self._running:
            start = time.time()

            state = self.state_manager.get()
            packet = build_unity_packet(state)

            with self._clients_lock:
                dead = []
                for client_sock, addr in self._clients:
                    try:
                        client_sock.sendall(packet)
                    except Exception:
                        dead.append(addr)

                # 移除断开的客户端
                if dead:
                    self._clients = [
                        (s, a) for s, a in self._clients if a not in dead
                    ]

            elapsed = time.time() - start
            sleep_time = max(0, interval - elapsed)
            time.sleep(sleep_time)

    @property
    def client_count(self) -> int:
        with self._clients_lock:
            return len(self._clients)

    def stop(self):
        """停止服务端"""
        self._running = False

        with self._clients_lock:
            for client_sock, _ in self._clients:
                try:
                    client_sock.close()
                except Exception:
                    pass
            self._clients.clear()

        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass

        print("[TCP] 服务端已停止")
