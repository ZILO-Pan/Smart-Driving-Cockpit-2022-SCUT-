"""
豆包视觉助手
定时截取 CARLA 摄像头画面，用豆包视觉模型分析路况

改动指南:
- 改截图频率: 修改 settings.VISION_CAPTURE_HZ
- 改分析 prompt: 修改 VISION_PROMPT
- 不用豆包换其他视觉模型: 改 _call_vision_api()
- 加更多分析维度(车牌识别等): 修改 VISION_PROMPT 或调用专门的 CV 模型
"""

import base64
import threading
import time
import io

import requests
import numpy as np

try:
    from PIL import Image
except ImportError:
    Image = None
    print("[VISION] 警告: Pillow 未安装 (pip install Pillow)")

from config import settings


VISION_PROMPT = """你是一个智能驾驶视觉分析助手。请分析这张来自自动驾驶汽车前方摄像头的画面。

请简要描述:
1. 当前道路类型和状况
2. 前方是否有车辆或行人
3. 交通信号灯状态（如果可见）
4. 任何需要注意的安全隐患

回复要简洁，适合车载语音播报（2-3句话）。"""


class DoubaoVision:
    def __init__(self):
        self._latest_analysis = ""
        self._lock = threading.Lock()
        self._running = False

    def analyze_frame(self, frame: np.ndarray) -> str:
        """
        分析单帧画面
        frame: numpy array (H, W, 3) BGR
        返回: 分析结果文字
        """
        if Image is None:
            return "视觉模块未安装 Pillow"

        # numpy → JPEG → base64
        img = Image.fromarray(frame[:, :, ::-1])  # BGR → RGB
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=75)
        b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        try:
            result = self._call_vision_api(b64)
            analysis = result.get("choices", [{}])[0].get(
                "message", {}
            ).get("content", "无法分析画面")
        except Exception as e:
            analysis = f"视觉分析暂不可用: {str(e)[:50]}"
            print(f"[VISION] API 调用失败: {e}")

        with self._lock:
            self._latest_analysis = analysis

        return analysis

    def start_periodic(self, frame_getter):
        """
        启动周期性分析
        frame_getter: callable，返回 numpy array 或 None
        """
        self._running = True
        self._thread = threading.Thread(
            target=self._periodic_loop,
            args=(frame_getter,),
            daemon=True
        )
        self._thread.start()
        print(f"[VISION] 周期分析已启动 ({settings.VISION_CAPTURE_HZ} Hz)")

    def _periodic_loop(self, frame_getter):
        interval = 1.0 / settings.VISION_CAPTURE_HZ

        while self._running:
            start = time.time()

            frame = frame_getter()
            if frame is not None:
                self.analyze_frame(frame)

            elapsed = time.time() - start
            sleep_time = max(0, interval - elapsed)
            time.sleep(sleep_time)

    def get_latest_analysis(self) -> str:
        with self._lock:
            return self._latest_analysis

    def _call_vision_api(self, image_b64: str) -> dict:
        url = f"{settings.DOUBAO_API_BASE}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.DOUBAO_API_KEY}"
        }
        payload = {
            "model": settings.DOUBAO_VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 256,
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def stop(self):
        self._running = False
        print("[VISION] 已停止")
