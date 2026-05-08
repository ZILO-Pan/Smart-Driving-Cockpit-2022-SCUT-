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
            "OutputMode": 1,
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
        "LLMConfig": {
            "Mode": "ArkV3",
            "EndPointId": settings.ARK_ENDPOINT_ID,
            "SystemMessages": [settings.NOVA_SYSTEM_PROMPT],
            "MaxTokens": 128,
            "Temperature": 0.1,
            "Tools": _get_tools_definition(),
        },
        "SubtitleConfig": {
            "SubtitleMode": 1,
        },
        "InterruptMode": 0,
    }

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

    print(f"[RTC] StartVoiceChat request body:")
    print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))

    try:
        resp = requests.post(url, headers=headers, data=body, timeout=15)
        result = resp.json()
        result["_task_id"] = task_id
        print(f"[RTC] StartVoiceChat response ({resp.status_code}):")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if resp.status_code == 200 and result.get("Result") == "ok":
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
    """5 grouped tools, minimal JSON to stay under S2S prompt limit."""
    return [
        {
            "type": "function",
            "function": {
                "name": "cabin_control",
                "description": "cabin device control",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["set_ac_temperature", "set_seat_ventilation", "toggle_window", "set_ambient_light", "set_cabin_mode"]
                        },
                        "params": {"type": "object"}
                    },
                    "required": ["action", "params"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "media_nav_control",
                "description": "media and navigation",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["play_music", "set_destination", "change_lane"]
                        },
                        "params": {"type": "object"}
                    },
                    "required": ["action", "params"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "panel_control",
                "description": "show/hide HMI panels",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["toggle_adas", "toggle_navigation", "toggle_cabin_cards", "toggle_service_panel", "toggle_3d_scene", "open_service_card", "show_alert"]
                        },
                        "params": {"type": "object"}
                    },
                    "required": ["action", "params"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "unity_control",
                "description": "3D scene control",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["switch_camera", "reset_camera", "toggle_car_part", "open_car_part", "close_car_part", "rotate_car"]
                        },
                        "params": {"type": "object"}
                    },
                    "required": ["action", "params"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_state",
                "description": "query current state",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "enum": ["cabin", "vehicle", "navigation"]
                        }
                    },
                    "required": ["target"]
                }
            }
        }
    ]
