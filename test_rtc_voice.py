"""
最小测试：验证火山 RTC StartVoiceChat API 是否可用
用法: python test_rtc_voice.py

需要先安装: pip install volcenginesdkcore volcenginesdkrtc
如果安装失败，脚本会自动尝试用 requests 手动签名。
"""

import sys
import os
import json
import time
import uuid
import hashlib
import hmac
import datetime
from urllib.parse import quote

# Fix Windows console encoding
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

try:
    import requests
except ImportError:
    print("请先 pip install requests")
    sys.exit(1)

# ============================================================
# 配置区 - 填入你的火山引擎凭证
# ============================================================

# 火山引擎 IAM 访问密钥（控制台 → 右上角头像 → API访问密钥）
# 如果你没有，去这里创建: https://console.volcengine.com/iam/keymanage/
VOLC_ACCESS_KEY_ID = os.getenv("VOLC_ACCESS_KEY_ID", "")
VOLC_SECRET_ACCESS_KEY = os.getenv("VOLC_SECRET_ACCESS_KEY", "")

# RTC 应用信息
RTC_APP_ID = os.getenv("RTC_APP_ID", "")

# 端到端语音服务信息
S2S_APP_ID = os.getenv("S2S_APP_ID", "")
S2S_ACCESS_TOKEN = os.getenv("S2S_ACCESS_TOKEN", "")

# 火山方舟 (LLM for Function Calling in hybrid mode)
ARK_ENDPOINT_ID = os.getenv("ARK_ENDPOINT_ID", "")

# ============================================================


def sign_v4(method, url, body, ak, sk, service="rtc", region="cn-north-1"):
    """火山引擎 API V4 签名"""
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    host = parsed.hostname
    path = parsed.path or "/"
    query_string = parsed.query

    now = datetime.datetime.now(datetime.timezone.utc)
    date_stamp = now.strftime('%Y%m%d')
    amz_date = now.strftime('%Y%m%dT%H%M%SZ')

    # Step 1: Canonical Request
    content_hash = hashlib.sha256(body.encode() if isinstance(body, str) else body).hexdigest()

    headers_to_sign = {
        'host': host,
        'x-date': amz_date,
        'x-content-sha256': content_hash,
        'content-type': 'application/json',
    }

    signed_headers = ';'.join(sorted(headers_to_sign.keys()))
    canonical_headers = ''.join(f'{k}:{v}\n' for k, v in sorted(headers_to_sign.items()))

    canonical_request = '\n'.join([
        method,
        path,
        query_string,
        canonical_headers,
        signed_headers,
        content_hash,
    ])

    # Step 2: String to Sign
    credential_scope = f'{date_stamp}/{region}/{service}/request'
    string_to_sign = '\n'.join([
        'HMAC-SHA256',
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    # Step 3: Signing Key
    def hmac_sha256(key, msg):
        return hmac.new(key, msg.encode() if isinstance(msg, str) else msg, hashlib.sha256).digest()

    k_date = hmac_sha256(sk.encode(), date_stamp)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    k_signing = hmac_sha256(k_service, "request")

    # Step 4: Signature
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    # Step 5: Authorization Header
    authorization = (
        f'HMAC-SHA256 Credential={ak}/{credential_scope}, '
        f'SignedHeaders={signed_headers}, '
        f'Signature={signature}'
    )

    return {
        'Host': host,
        'X-Date': amz_date,
        'X-Content-Sha256': content_hash,
        'Content-Type': 'application/json',
        'Authorization': authorization,
    }


def test_start_voice_chat():
    """尝试调用 StartVoiceChat API"""

    if not VOLC_ACCESS_KEY_ID or not VOLC_SECRET_ACCESS_KEY:
        print("=" * 60)
        print("  错误: 请先填入火山引擎 IAM 访问密钥")
        print()
        print("  获取方式:")
        print("  1. 打开 https://console.volcengine.com/iam/keymanage/")
        print("  2. 点击 '新建密钥'")
        print("  3. 把 Access Key ID 和 Secret Access Key 填到本文件顶部")
        print("=" * 60)
        return False

    # 构造请求
    room_id = f"test_room_{int(time.time())}"
    task_id = str(uuid.uuid4())
    bot_user_id = "NOVA_bot_001"

    # 先用纯 S2S 模式 (OutputMode=0) 测试基本连通性
    # 纯模式不需要 LLMConfig，减少参数出错可能
    body = json.dumps({
        "AppId": RTC_APP_ID,
        "RoomId": room_id,
        "TaskId": task_id,
        "AgentConfig": {
            "UserId": bot_user_id,
            "TargetUserId": ["test_human_user"],
            "IdleTimeout": 30,
        },
        "Config": {
            "S2SConfig": {
                "Provider": "volcano",
                "OutputMode": 0,  # 纯端到端模式（先验证连通性）
                "ProviderParams": {
                    "app": {
                        "appid": S2S_APP_ID,
                        "token": S2S_ACCESS_TOKEN,
                    },
                    "dialog": {
                        "bot_name": "NOVA",
                        "system_role": "你是智能驾驶座舱AI助手NOVA。",
                        "extra": {
                            "model": "1.2.1.1",
                        }
                    }
                }
            },
            "SubtitleConfig": {
                "SubtitleMode": 1,
            }
        }
    })

    url = "https://rtc.volcengineapi.com?Action=StartVoiceChat&Version=2024-12-01"

    print(f"[TEST] 正在调用 StartVoiceChat API...")
    print(f"[TEST] RoomId: {room_id}")
    print(f"[TEST] TaskId: {task_id}")
    print()

    try:
        headers = sign_v4("POST", url, body, VOLC_ACCESS_KEY_ID, VOLC_SECRET_ACCESS_KEY)
        resp = requests.post(url, headers=headers, data=body, timeout=15)

        print(f"[TEST] HTTP Status: {resp.status_code}")
        print(f"[TEST] Response:")
        try:
            result = resp.json()
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except:
            print(resp.text[:500])

        if resp.status_code == 200:
            print()
            print("=" * 60)
            print("  ✅ 成功！RTC + S2S 方案可行！")
            print("  个人账号可以使用 StartVoiceChat API")
            print()
            print("  接下来停止测试任务...")
            print("=" * 60)

            # 停止刚创建的任务
            stop_body = json.dumps({
                "AppId": RTC_APP_ID,
                "RoomId": room_id,
                "TaskId": task_id,
            })
            stop_url = "https://rtc.volcengineapi.com?Action=StopVoiceChat&Version=2024-12-01"
            stop_headers = sign_v4("POST", stop_url, stop_body, VOLC_ACCESS_KEY_ID, VOLC_SECRET_ACCESS_KEY)
            requests.post(stop_url, headers=stop_headers, data=stop_body, timeout=10)
            print("[TEST] 已停止测试任务")
            return True
        else:
            print()
            print("=" * 60)
            print("  ❌ 调用失败")
            if resp.status_code == 403:
                print("  可能原因: 个人账号权限不足 / AK/SK 错误")
            elif resp.status_code == 400:
                print("  可能原因: 参数错误 / S2S 服务未开通")
            print("  需要回退到自建 WebSocket 方案")
            print("=" * 60)
            return False

    except Exception as e:
        print(f"[TEST] 请求异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_sdk():
    """尝试用官方 SDK 调用（如果安装了的话）"""
    try:
        import volcenginesdkcore
        import volcenginesdkrtc
        print("[TEST] 检测到火山 SDK，使用 SDK 模式...")
        # SDK 模式实现（略，优先用 requests 手动签名）
        return None
    except ImportError:
        return None


if __name__ == "__main__":
    print("=" * 60)
    print("  火山 RTC AI 语音对话 - 可行性测试")
    print("=" * 60)
    print()

    # 尝试 SDK 模式
    sdk_result = test_with_sdk()
    if sdk_result is not None:
        sys.exit(0 if sdk_result else 1)

    # 手动签名模式
    result = test_start_voice_chat()
    sys.exit(0 if result else 1)
