"""
全局配置文件
所有端口号、API Key、串口号等都在这里统一管理
修改配置只需要改这一个文件
"""

# ============ CARLA 配置 ============
CARLA_HOST = "localhost"
CARLA_PORT = 2000
CARLA_FPS = 30
CARLA_NPC_COUNT = 30

# 窗口（pygame 本地预览用）
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

# ============ TCP 服务端（Unity 连接用） ============
TCP_HOST = "0.0.0.0"          # 监听所有网卡
TCP_PORT = 9000                # Unity 客户端连接这个端口
TCP_MAX_CLIENTS = 3            # 最多同时连接数

# ============ 串口（ESP32 舵机控制） ============
SERIAL_PORT = "COM3"           # Windows 示例，Linux 改为 /dev/ttyUSB0
SERIAL_BAUD = 115200
SERIAL_TIMEOUT = 0.01          # 10ms 超时，保持低延迟

# ============ 豆包 AI API ============
DOUBAO_API_KEY = "your-doubao-api-key-here"
DOUBAO_API_BASE = "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_CHAT_MODEL = "doubao-pro-32k"       # 对话模型
DOUBAO_VISION_MODEL = "doubao-vision-pro"   # 视觉模型
DOUBAO_MAX_HISTORY = 20                     # 对话上下文保留轮数

# ============ 数据更新频率 ============
VEHICLE_STATE_HZ = 30          # 车辆状态更新频率（与 CARLA FPS 一致）
TCP_SEND_HZ = 30               # TCP 发送给 Unity 的频率
SERIAL_SEND_HZ = 50            # 串口发送给 ESP32 的频率（高一点减少延迟）
VISION_CAPTURE_HZ = 2          # 视觉分析截图频率（太高会浪费 API 调用）
