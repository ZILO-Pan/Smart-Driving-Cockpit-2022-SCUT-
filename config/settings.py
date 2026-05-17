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

# ============ 火山 RTC + 端到端语音 ============
VOLC_ACCESS_KEY_ID = os.getenv("VOLC_ACCESS_KEY_ID", "")
VOLC_SECRET_ACCESS_KEY = os.getenv("VOLC_SECRET_ACCESS_KEY", "")
RTC_APP_ID = os.getenv("RTC_APP_ID", "")
RTC_APP_KEY = os.getenv("RTC_APP_KEY", "")
S2S_APP_ID = os.getenv("S2S_APP_ID", "")
S2S_ACCESS_TOKEN = os.getenv("S2S_ACCESS_TOKEN", "")
RTC_FC_SIGNATURE = os.getenv("RTC_FC_SIGNATURE", "nova_fc_secret")
VOICE_CALLBACK_URL = os.getenv("VOICE_CALLBACK_URL", "")
VOICE_VISION_ENABLED = os.getenv("VOICE_VISION_ENABLED", "false").lower() == "true"
VOICE_VISION_INTERVAL = int(os.getenv("VOICE_VISION_INTERVAL", "5"))
RTC_VOICE_ENABLED = bool(VOLC_ACCESS_KEY_ID and RTC_APP_ID and S2S_APP_ID)

NOVA_SYSTEM_PROMPT = os.getenv("NOVA_SYSTEM_PROMPT",
    "你是车载AI助手NOVA。回复简短自然（不超过20字），适合语音播报。"
    "\n【重要】凡是用户表达了座舱、驾驶、娱乐、导航、生活服务需求，你必须调用工具，不能只用语言回复。"
    "\n【意图识别】用户说“好热/有点冷/很烦/有点累/赶飞机/想喝奶茶/无聊/困了”等模糊表达时，优先调用 proactive_service_plan，输出 intent、confidence、reason、hmi_feedback 和 actions。"
    "\n【动作规划】actions 只能使用允许动作，例如 set_ac_temperature、set_seat_ventilation、toggle_window、set_ambient_light、set_cabin_mode、play_music、set_destination、change_lane、open_service_card、show_alert。"
    "\n示例：用户说好热 → proactive_service_plan(intent='thermal_comfort', actions=[{action:'set_ac_temperature',params:{temperature:22}},{action:'set_seat_ventilation',params:{on:true}},{action:'set_ambient_light',params:{color:'蓝'}}])。"
    "\n示例：用户说赶不上飞机 → proactive_service_plan(intent='travel_urgency', actions=[{action:'set_destination',params:{destination:'Airport T2'}},{action:'open_service_card',params:{service:'ctrip'}}])。"
    "\n【直接控制】用户明确说打开某个面板、播放音乐、打开车窗、换车道时，也可以直接调用对应分组工具。"
    "\n工具调用规则："
    "\n- proactive_service_plan: 模糊意图识别与服务计划"
    "\n- cabin_control: action∈{set_ac_temperature,set_seat_ventilation,toggle_window,set_ambient_light,set_cabin_mode}"
    "\n- media_nav_control: action∈{play_music,set_destination,change_lane}"
    "\n- panel_control: action∈{toggle_adas,toggle_navigation,toggle_cabin_cards,toggle_service_panel,toggle_3d_scene,open_service_card,show_alert}"
    "\n- unity_control: action∈{switch_camera,reset_camera,toggle_car_part,open_car_part,close_car_part,rotate_car}"
    "\n- query_state: target∈{cabin,vehicle,navigation}"
    "\n参数: cabin_control(action='set_ac_temperature',params={temperature:22})"
    "\n打开/关闭车门车窗等→直接调unity_control(action='open_car_part',params={part:'doorL'})，part值:doorL,doorR,hood,trunk,windowL,windowR"
)

# ============ 唤醒词检测 ============
VOICE_WAKE_WORD = os.getenv("VOICE_WAKE_WORD", "NOVA")
WAKE_VAD_THRESHOLD = int(os.getenv("WAKE_VAD_THRESHOLD", "200"))
WAKE_SILENCE_MS = int(os.getenv("WAKE_SILENCE_MS", "2000"))

# ============ 麦克风录音（Legacy fallback） ============
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
