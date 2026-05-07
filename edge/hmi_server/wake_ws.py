"""
唤醒词检测 WebSocket 端点
/ws/wake — 接收前端 PCM 音频帧，通过火山 ASR 识别，检测唤醒词
"""

import json
import gzip
import struct
import uuid
import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from config import settings

try:
    import websockets
except ImportError:
    websockets = None

WAKE_KEYWORDS = ["nova", "hi nova", "你好nova", "嘿nova", "hey nova"]


def _build_full_request(seq: int) -> bytes:
    """构建 ASR 首帧请求（建连 + 配置）"""
    payload = json.dumps({
        "user": {"uid": "wake_listener"},
        "audio": {
            "format": "pcm",
            "codec": "raw",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": False,
            "enable_punc": False,
            "enable_ddc": False,
            "show_utterances": True,
            "enable_nonstream": False,
        }
    }).encode()
    compressed = gzip.compress(payload)
    buf = bytearray([0x11, 0x11, 0x11, 0x00])
    buf.extend(struct.pack('>i', seq))
    buf.extend(struct.pack('>I', len(compressed)))
    buf.extend(compressed)
    return bytes(buf)


def _build_audio_request(seq: int, audio: bytes, is_last: bool) -> bytes:
    """构建音频帧请求"""
    header = bytearray([0x11])
    if is_last:
        header.append(0x23)
        seq = -seq
    else:
        header.append(0x21)
    header.extend([0x01, 0x00])
    compressed = gzip.compress(audio)
    buf = bytearray(header)
    buf.extend(struct.pack('>i', seq))
    buf.extend(struct.pack('>I', len(compressed)))
    buf.extend(compressed)
    return bytes(buf)


def _parse_asr_response(msg: bytes) -> str:
    """解析 ASR 服务器返回的二进制消息，提取文本"""
    try:
        if len(msg) < 4:
            return ""
        hs = msg[0] & 0x0f
        mt = msg[1] >> 4
        fl = msg[1] & 0x0f
        sr = msg[2] >> 4
        cp = msg[2] & 0x0f
        p = msg[hs * 4:]
        if fl & 0x01:
            p = p[4:]
        if fl & 0x04:
            p = p[4:]
        if mt == 0x09:
            p = p[4:]
        if not p:
            return ""
        if cp == 1:
            p = gzip.decompress(p)
        if sr == 1:
            data = json.loads(p.decode())
            return data.get("result", {}).get("text", "")
    except Exception:
        pass
    return ""


def _check_wake_word(text: str) -> bool:
    """检查文本是否包含唤醒词"""
    t = text.lower().strip().replace(" ", "")
    for kw in WAKE_KEYWORDS:
        if kw.replace(" ", "") in t:
            return True
    return False


async def wake_websocket_handler(ws: WebSocket):
    """唤醒词 WebSocket 主逻辑"""
    await ws.accept()
    print("[WAKE] Client connected")

    if websockets is None:
        await ws.send_json({"type": "error", "message": "websockets not installed"})
        await ws.close()
        return

    asr_ws = None
    seq = 1
    session_active = False

    async def _start_asr_session():
        nonlocal asr_ws, seq, session_active
        headers = {
            "X-Api-Resource-Id": "volc.bigasr.sauc.duration",
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Access-Key": settings.ASR_ACCESS_KEY,
            "X-Api-App-Key": settings.ASR_APP_KEY,
        }
        try:
            asr_ws = await websockets.connect(
                settings.ASR_WS_URL,
                additional_headers=headers,
                max_size=10 * 1024 * 1024,
            )
            seq = 1
            await asr_ws.send(_build_full_request(seq))
            seq += 1
            await asyncio.wait_for(asr_ws.recv(), timeout=5)
            session_active = True
        except Exception as e:
            print(f"[WAKE] ASR connect failed: {e}")
            asr_ws = None
            session_active = False

    async def _end_asr_session():
        nonlocal asr_ws, session_active
        if asr_ws:
            try:
                await asr_ws.close()
            except Exception:
                pass
            asr_ws = None
        session_active = False

    async def _read_asr_results():
        """非阻塞读取 ASR 返回的文本"""
        if not asr_ws:
            return ""
        try:
            msg = await asyncio.wait_for(asr_ws.recv(), timeout=0.05)
            return _parse_asr_response(msg)
        except asyncio.TimeoutError:
            return ""
        except Exception:
            return ""

    try:
        await _start_asr_session()
        if not session_active:
            await ws.send_json({"type": "error", "message": "ASR session failed"})
            await ws.close()
            return

        await ws.send_json({"type": "ready"})

        silence_frames = 0
        max_silence_frames = 10  # 10 * 200ms = 2s

        while True:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=30)
            except asyncio.TimeoutError:
                # 长时间无数据，重置 ASR 会话
                await _end_asr_session()
                await _start_asr_session()
                if session_active:
                    await ws.send_json({"type": "ready"})
                continue

            if msg.get("type") == "websocket.disconnect":
                break

            if "bytes" in msg and msg["bytes"]:
                audio_data = msg["bytes"]

                if not session_active:
                    await _start_asr_session()
                    if not session_active:
                        continue

                # 发送音频帧到 ASR
                try:
                    await asr_ws.send(_build_audio_request(seq, audio_data, False))
                    seq += 1
                except Exception as e:
                    print(f"[WAKE] ASR send error: {e}")
                    await _end_asr_session()
                    continue

                # 读取 ASR 结果
                text = await _read_asr_results()
                if text:
                    if _check_wake_word(text):
                        print(f"[WAKE] Detected wake word in: '{text}'")
                        await ws.send_json({"type": "wake_detected", "text": text})
                        # 重置会话准备下一次
                        await _end_asr_session()
                        await asyncio.sleep(0.5)
                        await _start_asr_session()
                        if session_active:
                            await ws.send_json({"type": "ready"})
                        silence_frames = 0

                silence_frames = 0

            elif "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                if data.get("type") == "silence":
                    # 前端报告静音
                    silence_frames += 1
                    if silence_frames >= max_silence_frames and session_active:
                        # 发送结束帧，重置
                        try:
                            await asr_ws.send(_build_audio_request(seq, b'\x00' * 640, True))
                        except Exception:
                            pass
                        # 读取最终结果
                        for _ in range(5):
                            text = await _read_asr_results()
                            if text and _check_wake_word(text):
                                await ws.send_json({"type": "wake_detected", "text": text})
                                break
                        await _end_asr_session()
                        await _start_asr_session()
                        if session_active:
                            await ws.send_json({"type": "ready"})
                        silence_frames = 0

                elif data.get("type") == "pause":
                    await _end_asr_session()

                elif data.get("type") == "resume":
                    if not session_active:
                        await _start_asr_session()
                        if session_active:
                            await ws.send_json({"type": "ready"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WAKE] Error: {e}")
    finally:
        await _end_asr_session()
        print("[WAKE] Client disconnected")
