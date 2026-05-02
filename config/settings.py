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
TCP_HOST = "0.0.0.0"
TCP_PORT = 9000
TCP_MAX_CLIENTS = 3


# ============ 火山方舟 - 豆包大模型 (对话 + 视觉) ============
ARK_API_KEY = "c5504110-d5bd-4876-8009-d3ddf3897ef8"
ARK_API_BASE = "https://ark.cn-beijing.volces.com/api/v3"
ARK_ENDPOINT_ID = "ep-20260316012441-lwsjl"   # 视觉+对话 同一个接入点
DOUBAO_MAX_HISTORY = 20

# ============ 火山引擎 - 语音识别 ASR ============
ASR_APP_KEY = "3121922445"
ASR_ACCESS_KEY = "qAyVTVefm_F9L2OyacRqchiishYBrXNk"
ASR_WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"

# ============ 火山引擎 - 语音合成 TTS ============
TTS_APP_ID = "3121922445"
TTS_ACCESS_TOKEN = "qAyVTVefm_F9L2OyacRqchiishYBrXNk"
TTS_VOICE_TYPE = "zh_female_vv_uranus_bigtts"
TTS_CLUSTER = "volcano_tts"
TTS_WS_URL = "wss://openspeech.bytedance.com/api/v1/tts/ws_binary"
TTS_ENCODING = "mp3"
TTS_SAMPLE_RATE = 24000

# ============ 麦克风录音 ============
MIC_SAMPLE_RATE = 16000
MIC_CHANNELS = 1
MIC_CHUNK_MS = 200            # 每个音频片段的毫秒数
MIC_SILENCE_THRESHOLD = 300   # 静音检测阈值（可按环境调整）
MIC_SILENCE_DURATION = 2.5    # 静音多久算说完（秒）

# ============ AI 助手行为 ============
VISION_CAPTURE_INTERVAL = 15  # 定时播报: 每 N 秒分析一次画面
VISION_EVENT_ENABLED = True   # 事件触发播报: 是否启用
VISION_AUTO_BROADCAST = True  # 是否自动语音播报路况（定时模式）

# ============ 数据更新频率 ============
VEHICLE_STATE_HZ = 30
TCP_SEND_HZ = 30
