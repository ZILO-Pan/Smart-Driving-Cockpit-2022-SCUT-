"""
语音合成模块 (TTS)
文字 → 火山引擎 TTS → pygame.mixer 播放
不依赖 ffmpeg，不弹文件
"""

import threading
import struct
import json
import gzip
import uuid
import time
import asyncio
import tempfile
import os

try:
    import websockets
except ImportError:
    websockets = None

try:
    import pygame.mixer
except ImportError:
    pass

from config import settings


class Speaker:
    def __init__(self):
        self._lock = threading.Lock()
        self._is_speaking = False
        self._on_start_callbacks = []
        self._on_end_callbacks = []
        self._mixer_ready = False
        self._init_mixer()

    def _init_mixer(self):
        """初始化 pygame.mixer（独立于 pygame.display）"""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=4096)
            self._mixer_ready = True
            print("[TTS] pygame.mixer 已初始化")
        except Exception as e:
            print(f"[TTS] pygame.mixer 初始化失败: {e}")
            self._mixer_ready = False

    @property
    def is_speaking(self): return self._is_speaking

    def speak(self, text: str):
        if not text or not text.strip(): return
        if len(text) > 200: text = text[:200]
        threading.Thread(target=self._speak_sync, args=(text,), daemon=True).start()

    def _speak_sync(self, text: str):
        self._is_speaking = True
        for cb in self._on_start_callbacks:
            try: cb()
            except: pass

        try:
            audio = self._synthesize(text)
            if audio and len(audio) > 100:
                self._play(audio)
            else:
                print("[TTS] 未收到有效音频")
        except Exception as e:
            print(f"[TTS] 错误: {e}")
        finally:
            self._is_speaking = False
            for cb in self._on_end_callbacks:
                try: cb()
                except: pass

    def _synthesize(self, text: str) -> bytes:
        if websockets is None: return b""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try: return loop.run_until_complete(self._ws_synthesize(text))
        finally: loop.close()

    async def _ws_synthesize(self, text: str) -> bytes:
        reqid = str(uuid.uuid4())
        ws_headers = {
            "Authorization": f"Bearer;{settings.TTS_ACCESS_TOKEN}"
        }
        payload = {
            "app": {
                "appid": settings.TTS_APP_ID,
                "token": "access_token",
                "cluster": settings.TTS_CLUSTER,
            },
            "user": {"uid": "cockpit"},
            "audio": {
                "voice_type": settings.TTS_VOICE_TYPE,
                "encoding": settings.TTS_ENCODING,
                "speed_ratio": 1.1,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
                "sample_rate": settings.TTS_SAMPLE_RATE,
            },
            "request": {
                "reqid": reqid,
                "text": text,
                "text_type": "plain",
                "operation": "submit",
            }
        }

        pbytes = gzip.compress(json.dumps(payload).encode())
        req = bytearray([0x11, 0x10, 0x11, 0x00])
        req.extend(struct.pack('>I', len(pbytes)))
        req.extend(pbytes)

        audio = bytearray()
        try:
            async with websockets.connect(
                settings.TTS_WS_URL,
                additional_headers=ws_headers,
                ping_interval=None,
                max_size=10*1024*1024,
                close_timeout=5,
            ) as ws:
                await ws.send(bytes(req))
                while True:
                    try:
                        resp = await asyncio.wait_for(ws.recv(), timeout=15)
                    except asyncio.TimeoutError:
                        break
                    done, chunk = self._parse(resp)
                    if chunk: audio.extend(chunk)
                    if done: break
        except Exception as e:
            print(f"[TTS] WebSocket 错误: {e}")
        return bytes(audio)

    def _parse(self, msg):
        try:
            if len(msg) < 4: return False, None
            hs = msg[0] & 0x0f
            mt = (msg[1] >> 4) & 0x0f
            fl = msg[1] & 0x0f
            cp = msg[2] & 0x0f
            p = msg[hs*4:]
            is_last = fl in (2, 3)

            if mt == 0x0b:  # audio
                if fl in (1,2,3): p = p[4:]
                if len(p) >= 4:
                    sz = struct.unpack('>I', p[:4])[0]
                    return is_last, p[4:4+sz]
            elif mt == 0x0f:  # error
                if len(p) >= 8:
                    code = struct.unpack('>i', p[:4])[0]
                    print(f"[TTS] 服务端错误 code={code}")
                return True, None
            elif mt == 0x0c:  # metadata
                return is_last, None
        except Exception as e:
            print(f"[TTS] 解析错误: {e}")
        return False, None

    def _play(self, audio_data: bytes):
        """写临时mp3 → pygame播放 → 删除"""
        tmp = None
        try:
            # 确保 mixer 可用
            if not self._mixer_ready:
                self._init_mixer()
            if not self._mixer_ready:
                print("[TTS] mixer 不可用，跳过播放")
                return

            fd, tmp = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            with open(tmp, 'wb') as f:
                f.write(audio_data)

            pygame.mixer.music.load(tmp)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            pygame.mixer.music.unload()
            print("[TTS] 播放完成")

        except Exception as e:
            print(f"[TTS] 播放错误: {e}")
        finally:
            if tmp:
                try: time.sleep(0.3); os.unlink(tmp)
                except: pass

    def on_start(self, cb): self._on_start_callbacks.append(cb)
    def on_end(self, cb): self._on_end_callbacks.append(cb)