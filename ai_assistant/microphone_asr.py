"""
语音识别模块 (ASR)
持续监听麦克风 -> 火山引擎流式语音识别 -> 输出文字
"""

import threading
import struct
import json
import gzip
import uuid
import time
import asyncio
import numpy as np

try:
    import pyaudio
except ImportError:
    pyaudio = None
    print("[ASR] pyaudio 未安装 (pip install pyaudio)")

try:
    import websockets
except ImportError:
    websockets = None
    print("[ASR] websockets 未安装 (pip install websockets)")

from config import settings


class MicrophoneASR:
    def __init__(self):
        self._running = False
        self._on_text_callbacks = []
        self._is_listening = True

    def start(self):
        if pyaudio is None or websockets is None:
            print("[ASR] 缺少依赖，跳过")
            return
        self._running = True
        threading.Thread(target=self._run_loop, daemon=True).start()
        print("[ASR] 麦克风已开启，持续监听中...")

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._listen_forever())

    async def _listen_forever(self):
        pa = pyaudio.PyAudio()
        chunk_size = int(settings.MIC_SAMPLE_RATE * settings.MIC_CHUNK_MS / 1000)
        while self._running:
            stream = None
            try:
                stream = pa.open(
                    format=pyaudio.paInt16, channels=settings.MIC_CHANNELS,
                    rate=settings.MIC_SAMPLE_RATE, input=True,
                    frames_per_buffer=chunk_size)
                while self._running:
                    data = stream.read(chunk_size, exception_on_overflow=False)
                    if not self._is_listening:
                        continue
                    volume = np.abs(np.frombuffer(data, dtype=np.int16)).mean()
                    if volume > settings.MIC_SILENCE_THRESHOLD:
                        print(f"[ASR] 检测到说话 (音量={volume:.0f})")
                        text = await self._recognize(stream, chunk_size, data)
                        if text and text.strip():
                            print(f"[ASR] 识别结果: {text}")
                            self._notify(text.strip())
                stream.stop_stream()
                stream.close()
            except Exception as e:
                print(f"[ASR] 错误: {e}")
                if stream:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception:
                        pass
                await asyncio.sleep(2)
        pa.terminate()

    async def _recognize(self, stream, chunk_size, first_chunk):
        headers = {
            "X-Api-Resource-Id": "volc.bigasr.sauc.duration",
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Access-Key": settings.ASR_ACCESS_KEY,
            "X-Api-App-Key": settings.ASR_APP_KEY,
        }
        seq = 1
        try:
            async with websockets.connect(
                settings.ASR_WS_URL,
                extra_headers=headers,
                max_size=10 * 1024 * 1024
            ) as ws:
                await ws.send(self._full_req(seq))
                seq += 1
                await asyncio.wait_for(ws.recv(), timeout=5)
                await ws.send(self._audio_req(seq, first_chunk, False))
                seq += 1
                silence_start = None
                texts = []
                while self._running:
                    try:
                        data = stream.read(chunk_size, exception_on_overflow=False)
                    except Exception:
                        break
                    vol = np.abs(np.frombuffer(data, dtype=np.int16)).mean()
                    if vol < settings.MIC_SILENCE_THRESHOLD:
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start > settings.MIC_SILENCE_DURATION:
                            await ws.send(self._audio_req(seq, data, True))
                            break
                    else:
                        silence_start = None
                    await ws.send(self._audio_req(seq, data, False))
                    seq += 1
                    try:
                        r = await asyncio.wait_for(ws.recv(), timeout=0.01)
                        t = self._parse(r)
                        if t:
                            texts.append(t)
                    except asyncio.TimeoutError:
                        pass
                try:
                    while True:
                        r = await asyncio.wait_for(ws.recv(), timeout=3)
                        t = self._parse(r)
                        if t:
                            texts.append(t)
                        if len(r) >= 2 and (r[1] & 0x02):
                            break
                except Exception:
                    pass
                return texts[-1] if texts else ""
        except Exception as e:
            print(f"[ASR] WebSocket 错误: {e}")
        return ""

    def _full_req(self, seq):
        p = json.dumps({
            "user": {"uid": "cockpit_user"},
            "audio": {"format": "pcm", "codec": "raw", "rate": settings.MIC_SAMPLE_RATE, "bits": 16, "channel": settings.MIC_CHANNELS},
            "request": {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True, "enable_ddc": True, "show_utterances": True, "enable_nonstream": False}
        }).encode()
        c = gzip.compress(p)
        r = bytearray([0x11, 0x11, 0x11, 0x00])
        r.extend(struct.pack('>i', seq))
        r.extend(struct.pack('>I', len(c)))
        r.extend(c)
        return bytes(r)

    def _audio_req(self, seq, audio, is_last):
        h = bytearray([0x11])
        if is_last:
            h.append(0x23)
            seq = -seq
        else:
            h.append(0x21)
        h.extend([0x01, 0x00])
        c = gzip.compress(audio)
        r = bytearray(h)
        r.extend(struct.pack('>i', seq))
        r.extend(struct.pack('>I', len(c)))
        r.extend(c)
        return bytes(r)

    def _parse(self, msg):
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
                return json.loads(p.decode()).get("result", {}).get("text", "")
        except Exception:
            pass
        return ""

    def pause(self):
        self._is_listening = False

    def resume(self):
        self._is_listening = True

    def on_text(self, cb):
        self._on_text_callbacks.append(cb)

    def _notify(self, t):
        for cb in self._on_text_callbacks:
            try:
                cb(t)
            except Exception as e:
                print(f"[ASR] 回调错误: {e}")

    def stop(self):
        self._running = False
        print("[ASR] 已停止")
