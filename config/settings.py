"""
全局配置文件
敏感信息从 .env 文件加载，其余硬编码在此
"""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("[CONFIG] 警告: python-dotenv 未安装 (pip install python-dotenv)")
    print("[CONFIG] 将仅从系统环境变量读取配置")
    load_dotenv = None

# 加载 .env 文件
_env_path = Path(__file__).resolve().parent.parent / ".env"
if load_dotenv and _env_path.exists():
    load_dotenv(_env_path)

def _require_env(key: str, default: str = None) -> str:
    val = os.getenv(key, default)
    if not val:
        print(f"[CONFIG] 错误: 环境变量 {key} 未设置，请检查 .env 文件")
        sys.exit(1)
    return val

# ============ CARLA 配置 ============
CARLA_HOST = "localhost"
CARLA_PORT = 2000
CARLA_FPS = 30
CARLA_NPC_COUNT = 30

# 窗口（pygame 本地预览用）
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

# ============ TCP 服务端（Unity 连接用，保留为可选） ============
TCP_HOST = "0.0.0.0"
TCP_PORT = 9000
TCP_MAX_CLIENTS = 3

# ============ Web HMI 服务端 ============
WEB_HMI_HOST = "0.0.0.0"
WEB_HMI_PORT = 8080

# ============ 火山方舟 - 豆包大模型 (对话 + 视觉) ============
ARK_API_KEY = _require_env("ARK_API_KEY")
ARK_API_BASE = os.getenv("ARK_API_BASE", "https://ark.cn-beijing.volces.com/api/v3")
ARK_ENDPOINT_ID = _require_env("ARK_ENDPOINT_ID")
DOUBAO_MAX_HISTORY = 20

# ============ 火山引擎 - 语音识别 ASR ============
ASR_APP_KEY = _require_env("ASR_APP_KEY")
ASR_ACCESS_KEY = _require_env("ASR_ACCESS_KEY")
ASR_WS_URL = os.getenv("ASR_WS_URL", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel")

# ============ 火山引擎 - 语音合成 TTS ============
TTS_APP_ID = _require_env("TTS_APP_ID")
TTS_ACCESS_TOKEN = _require_env("TTS_ACCESS_TOKEN")
TTS_VOICE_TYPE = os.getenv("TTS_VOICE_TYPE", "zh_female_vv_uranus_bigtts")
TTS_CLUSTER = os.getenv("TTS_CLUSTER", "volcano_tts")
TTS_WS_URL = os.getenv("TTS_WS_URL", "wss://openspeech.bytedance.com/api/v1/tts/ws_binary")
TTS_ENCODING = "mp3"
TTS_SAMPLE_RATE = 24000

# ============ 麦克风录音 ============
MIC_SAMPLE_RATE = 16000
MIC_CHANNELS = 1
MIC_CHUNK_MS = 200
MIC_SILENCE_THRESHOLD = 300
MIC_SILENCE_DURATION = 2.5

# ============ AI 助手行为 ============
VISION_CAPTURE_INTERVAL = 15
VISION_EVENT_ENABLED = True
VISION_AUTO_BROADCAST = True

# ============ 数据更新频率 ============
VEHICLE_STATE_HZ = 30
TCP_SEND_HZ = 30
