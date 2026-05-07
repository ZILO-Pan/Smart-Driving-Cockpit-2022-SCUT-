"""
火山 RTC AI 语音服务
封装 StartVoiceChat / StopVoiceChat / Token 生成

架构:
  浏览器 RTC SDK → 火山 RTC 房间 → S2S 端到端语音模型
  Function Calling → ServerMessageUrl 回调 → FastAPI 执行动作
"""

import json
import time
import uuid
import hashlib
import hmac
import datetime
from urllib.parse import urlparse

import requests

from config import settings


def _sign_request(method: str, url: str, body: str) -> dict:
    """火山引擎 OpenAPI V4 签名"""
    parsed = urlparse(url)
    host = parsed.hostname
    path = parsed.path or "/"
    query_string = parsed.query

    now = datetime.datetime.now(datetime.timezone.utc)
    date_stamp = now.strftime('%Y%m%d')
    x_date = now.strftime('%Y%m%dT%H%M%SZ')

    content_hash = hashlib.sha256(body.encode()).hexdigest()

    headers_to_sign = {
        'host': host,
        'x-date': x_date,
        'x-content-sha256': content_hash,
        'content-type': 'application/json',
    }

    signed_headers = ';'.join(sorted(headers_to_sign.keys()))
    canonical_headers = ''.join(f'{k}:{v}\n' for k, v in sorted(headers_to_sign.items()))

    canonical_request = '\n'.join([
        method, path, query_string,
        canonical_headers, signed_headers, content_hash,
    ])

    service = "rtc"
    region = "cn-north-1"
    credential_scope = f'{date_stamp}/{region}/{service}/request'
    string_to_sign = '\n'.join([
        'HMAC-SHA256', x_date, credential_scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    def hmac_sha256(key, msg):
        return hmac.new(key, msg.encode() if isinstance(msg, str) else msg, hashlib.sha256).digest()

    k_date = hmac_sha256(settings.VOLC_SECRET_ACCESS_KEY.encode(), date_stamp)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    k_signing = hmac_sha256(k_service, "request")

    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    authorization = (
        f'HMAC-SHA256 Credential={settings.VOLC_ACCESS_KEY_ID}/{credential_scope}, '
        f'SignedHeaders={signed_headers}, '
        f'Signature={signature}'
    )

    return {
        'Host': host,
        'X-Date': x_date,
        'X-Content-Sha256': content_hash,
        'Content-Type': 'application/json',
        'Authorization': authorization,
    }


def generate_rtc_token(room_id: str, user_id: str, ttl: int = 86400) -> str:
    """
    生成 RTC 加入房间的 Token（二进制格式）

    火山 RTC Token 格式 (与 Agora 类似的二进制协议):
      Token = VERSION(3字节"001") + APP_ID(24字节) + Base64(content)
      content = pack(msg_bytes) + pack(signature_bytes)
      msg = nonce(uint32) + issuedAt(uint32) + expireAt(uint32)
            + roomID(len_prefixed_string) + userID(len_prefixed_string)
            + privileges(treemap<uint16,uint32>)
      signature = HMAC-SHA256(appKey, msg_bytes)

    所有整数使用 little-endian 编码，字符串用 uint16 长度前缀。

    参考: https://www.volcengine.com/docs/6348/70121
    """
    import base64
    import struct
    import random

    app_id = settings.RTC_APP_ID
    app_key = settings.RTC_APP_KEY

    now = int(time.time())
    expire_at = now + ttl
    nonce = random.randint(0, 0xFFFFFFFF)

    # 权限定义
    PRIV_PUBLISH_STREAM = 0
    PRIV_PUBLISH_AUDIO_STREAM = 1
    PRIV_PUBLISH_VIDEO_STREAM = 2
    PRIV_PUBLISH_DATA_STREAM = 3
    PRIV_SUBSCRIBE_STREAM = 4

    # 设置权限（发布+订阅，过期时间与token一致）
    privileges = {
        PRIV_PUBLISH_STREAM: expire_at,
        PRIV_PUBLISH_AUDIO_STREAM: expire_at,
        PRIV_PUBLISH_VIDEO_STREAM: expire_at,
        PRIV_PUBLISH_DATA_STREAM: expire_at,
        PRIV_SUBSCRIBE_STREAM: expire_at,
    }

    # --- 构造 msg 二进制 ---
    def pack_uint16(val):
        return struct.pack('<H', val)

    def pack_uint32(val):
        return struct.pack('<I', val)

    def pack_string(s):
        b = s.encode('utf-8') if isinstance(s, str) else s
        return pack_uint16(len(b)) + b

    def pack_treemap_uint32(m):
        buf = pack_uint16(len(m))
        for k in sorted(m.keys()):
            buf += pack_uint16(k)
            buf += pack_uint32(m[k])
        return buf

    msg = b''
    msg += pack_uint32(nonce)
    msg += pack_uint32(now)        # issuedAt
    msg += pack_uint32(expire_at)  # expireAt
    msg += pack_string(room_id)
    msg += pack_string(user_id)
    msg += pack_treemap_uint32(privileges)

    # --- HMAC-SHA256 签名 ---
    signature = hmac.new(
        app_key.encode('utf-8'), msg, hashlib.sha256
    ).digest()

    # --- 构造 content: pack(msg) + pack(signature) ---
    content = pack_string(msg) + pack_string(signature)

    # --- 最终 token: VERSION + APP_ID + Base64(content) ---
    token = "001" + app_id + base64.b64encode(content).decode('utf-8')
    return token


def start_voice_chat(room_id: str, bot_user_id: str, target_user_id: str,
                     fc_callback_url: str = None) -> dict:
    """
    调用 StartVoiceChat 启动 AI 语音 Bot

    Args:
        room_id: RTC 房间 ID
        bot_user_id: Bot 的用户 ID
        target_user_id: 对话目标用户 ID
        fc_callback_url: Function Calling 回调 URL（可选）

    Returns:
        API 响应 dict
    """
    config = {
        "S2SConfig": {
            "Provider": "volcano",
            "OutputMode": 0,
            "ProviderParams": {
                "app": {
                    "appid": settings.S2S_APP_ID,
                    "token": settings.S2S_ACCESS_TOKEN,
                },
                "dialog": {
                    "bot_name": "NOVA",
                    "system_role": settings.NOVA_SYSTEM_PROMPT,
                    "extra": {
                        "model": "1.2.1.1",
                    }
                }
            }
        },
        "SubtitleConfig": {
            "SubtitleMode": 1,
        },
        "InterruptMode": 1,
    }

    # 视觉理解（用户摄像头 → AI 可感知画面）
    if settings.VOICE_VISION_ENABLED:
        config["VisionConfig"] = {
            "Enable": True,
            "SnapshotInterval": settings.VOICE_VISION_INTERVAL,
        }

    # Function Calling: 始终启用 LLM + Tools（混合模式）
    config["S2SConfig"]["OutputMode"] = 1
    config["LLMConfig"] = {
        "Mode": "ArkV3",
        "EndPointId": settings.ARK_ENDPOINT_ID,
        "SystemMessages": [settings.NOVA_SYSTEM_PROMPT],
        "MaxTokens": 1024,
        "Temperature": 0.3,
        "Tools": _get_tools_definition(),
    }

    # 如果有公网回调 URL → 服务端模式（火山 POST 到你的后端）
    # 如果没有 → 客户端模式（FC 通过 RTC binary message 推到浏览器）
    if fc_callback_url:
        config["FunctionCallingConfig"] = {
            "ServerMessageUrl": fc_callback_url,
            "ServerMessageSignature": settings.RTC_FC_SIGNATURE,
        }

    task_id = str(uuid.uuid4())
    body = json.dumps({
        "AppId": settings.RTC_APP_ID,
        "RoomId": room_id,
        "TaskId": task_id,
        "AgentConfig": {
            "UserId": bot_user_id,
            "TargetUserId": [target_user_id],
            "IdleTimeout": 180,
            "WelcomeMessage": "你好，我是NOVA，你的智能座舱助手。有什么我可以帮你的？",
        },
        "Config": config,
    })

    url = "https://rtc.volcengineapi.com?Action=StartVoiceChat&Version=2024-12-01"
    headers = _sign_request("POST", url, body)

    try:
        resp = requests.post(url, headers=headers, data=body, timeout=15)
        result = resp.json()
        result["_task_id"] = task_id
        if resp.status_code == 200:
            print(f"[RTC] VoiceChat started: room={room_id}, bot={bot_user_id}, task={task_id}")
        else:
            error = result.get("ResponseMetadata", {}).get("Error", {})
            print(f"[RTC] StartVoiceChat failed: {error.get('Code')} - {error.get('Message')}")
        return result
    except Exception as e:
        print(f"[RTC] StartVoiceChat error: {e}")
        return {"error": str(e)}


def update_voice_chat(room_id: str, task_id: str, tool_call_id: str, result_content: str) -> dict:
    """
    调用 UpdateVoiceChat 将 Function Calling 结果返回给 AI
    AI 收到结果后会继续生成语音回复
    """
    body = json.dumps({
        "AppId": settings.RTC_APP_ID,
        "RoomId": room_id,
        "TaskId": task_id,
        "Command": "function",
        "Message": json.dumps({
            "ToolCallID": tool_call_id,
            "Content": result_content,
        }),
    })

    url = "https://rtc.volcengineapi.com?Action=UpdateVoiceChat&Version=2024-12-01"
    headers = _sign_request("POST", url, body)

    try:
        resp = requests.post(url, headers=headers, data=body, timeout=10)
        result = resp.json()
        print(f"[RTC] UpdateVoiceChat: tool_call_id={tool_call_id}")
        return result
    except Exception as e:
        print(f"[RTC] UpdateVoiceChat error: {e}")
        return {"error": str(e)}


def stop_voice_chat(room_id: str, task_id: str) -> dict:
    """停止 AI 语音 Bot"""
    body = json.dumps({
        "AppId": settings.RTC_APP_ID,
        "RoomId": room_id,
        "TaskId": task_id,
    })

    url = "https://rtc.volcengineapi.com?Action=StopVoiceChat&Version=2024-12-01"
    headers = _sign_request("POST", url, body)

    try:
        resp = requests.post(url, headers=headers, data=body, timeout=10)
        result = resp.json()
        print(f"[RTC] VoiceChat stopped: room={room_id}")
        return result
    except Exception as e:
        print(f"[RTC] StopVoiceChat error: {e}")
        return {"error": str(e)}


def _get_tools_definition() -> list:
    """Function Calling 工具定义（座舱控制）"""
    return [
        {
            "type": "function",
            "function": {
                "name": "set_ac_temperature",
                "description": "设置车内空调温度",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "temperature": {"type": "number", "description": "目标温度(摄氏度)，范围16-30"}
                    },
                    "required": ["temperature"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "set_seat_ventilation",
                "description": "开关座椅通风",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "on": {"type": "boolean", "description": "true开启/false关闭"}
                    },
                    "required": ["on"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "toggle_window",
                "description": "开关车窗",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "open": {"type": "boolean", "description": "true开窗/false关窗"}
                    },
                    "required": ["open"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "set_ambient_light",
                "description": "设置氛围灯颜色",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "color": {"type": "string", "description": "颜色名称(蓝/红/绿/紫/暖白)"}
                    },
                    "required": ["color"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "play_music",
                "description": "播放音乐",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "歌曲名或类型"}
                    },
                    "required": ["title"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "set_cabin_mode",
                "description": "切换座舱模式",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["标准", "休息", "运动", "影院"], "description": "模式名称"}
                    },
                    "required": ["mode"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "set_destination",
                "description": "设置导航目的地",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "destination": {"type": "string", "description": "目的地名称"}
                    },
                    "required": ["destination"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "change_lane",
                "description": "变道",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["左", "右"], "description": "变道方向"}
                    },
                    "required": ["direction"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_service_card",
                "description": "打开服务卡片。alipay=支付宝, ctrip=携程旅行, music=音乐, bilibili=B站视频, parking=智慧停车, charging=充电站, news=新闻",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "enum": ["alipay", "ctrip", "music", "bilibili", "parking", "charging", "news"], "description": "服务类型"}
                    },
                    "required": ["service"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "show_alert",
                "description": "在HMI上显示提示信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "提示内容"}
                    },
                    "required": ["message"]
                }
            }
        },
        # ─── Dock 面板控制 ───
        {
            "type": "function",
            "function": {
                "name": "toggle_adas",
                "description": "显示或隐藏ADAS驾驶辅助面板",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "show": {"type": "boolean", "description": "true显示/false隐藏"}
                    },
                    "required": ["show"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "toggle_navigation",
                "description": "显示或隐藏导航地图面板",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "show": {"type": "boolean", "description": "true显示/false隐藏"}
                    },
                    "required": ["show"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "toggle_cabin_cards",
                "description": "显示或隐藏座舱娱乐卡片区域(音乐/视频等)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "show": {"type": "boolean", "description": "true显示/false隐藏"}
                    },
                    "required": ["show"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "toggle_service_panel",
                "description": "打开或关闭服务应用面板(支付宝/携程/充电/停车等)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "open": {"type": "boolean", "description": "true打开/false关闭"}
                    },
                    "required": ["open"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "toggle_3d_scene",
                "description": "打开或关闭3D展车场景(Unity)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "show": {"type": "boolean", "description": "true打开/false关闭"}
                    },
                    "required": ["show"]
                }
            }
        },
        # ─── Unity 3D 场景控制 ───
        {
            "type": "function",
            "function": {
                "name": "switch_camera",
                "description": "切换3D场景视角(需先打开3D场景)。default=默认全景, astronaut=宇航员近景, carExterior=车外, carInterior=车内",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "view": {"type": "string", "enum": ["default", "astronaut", "carExterior", "carInterior"], "description": "目标视角"}
                    },
                    "required": ["view"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "reset_camera",
                "description": "重置3D场景到默认视角",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "toggle_car_part",
                "description": "切换车辆部件开关状态(需在carExterior视角)。doorL=左车门, doorR=右车门, hood=引擎盖, trunk=后备箱, windowL=左车窗, windowR=右车窗",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "part": {"type": "string", "enum": ["doorL", "doorR", "hood", "trunk", "windowL", "windowR"], "description": "部件ID"}
                    },
                    "required": ["part"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_car_part",
                "description": "打开车辆指定部件(需在carExterior视角)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "part": {"type": "string", "enum": ["doorL", "doorR", "hood", "trunk", "windowL", "windowR"], "description": "部件ID"}
                    },
                    "required": ["part"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "close_car_part",
                "description": "关闭车辆指定部件(需在carExterior视角)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "part": {"type": "string", "enum": ["doorL", "doorR", "hood", "trunk", "windowL", "windowR"], "description": "部件ID"}
                    },
                    "required": ["part"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "rotate_car",
                "description": "旋转3D车辆查看不同角度。absolute=转到指定角度, relative=相对当前转, reset=复位",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["absolute", "relative", "reset"], "description": "旋转模式"},
                        "angle": {"type": "number", "description": "角度(-180到180)，reset模式下可不传"}
                    },
                    "required": ["mode"]
                }
            }
        },
    ]
