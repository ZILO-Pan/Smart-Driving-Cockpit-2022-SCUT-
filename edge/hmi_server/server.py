"""
Web HMI 服务端
FastAPI + WebSocket 推送车辆/座舱状态给 HTML 前端
"""

import asyncio
import json
import threading
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import settings
from edge.state.vehicle_state import VehicleStateManager

app = FastAPI(title="Smart Cockpit HMI")

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "hmi" / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_state_manager: VehicleStateManager = None
_cabin_state = None
_service_executor = None
_ai_assistant = None
_connected_clients: list[WebSocket] = []


def set_dependencies(state_manager, cabin_state=None, service_executor=None, ai_assistant=None):
    global _state_manager, _cabin_state, _service_executor, _ai_assistant
    _state_manager = state_manager
    _cabin_state = cabin_state
    _service_executor = service_executor
    _ai_assistant = ai_assistant


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _connected_clients.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            await _handle_client_message(msg, ws)
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _connected_clients:
            _connected_clients.remove(ws)


async def _handle_client_message(msg: dict, ws: WebSocket):
    msg_type = msg.get("type", "")

    if msg_type == "user_input":
        text = msg.get("text", "").strip()
        if text and _ai_assistant:
            _ai_assistant.process_user_input_async(text)

    elif msg_type == "cabin_control":
        if _service_executor:
            action = msg.get("action", "")
            params = msg.get("params", {})
            _service_executor.execute(action, params)

    elif msg_type == "demo_trigger":
        scenario = msg.get("scenario", "")
        if _ai_assistant:
            _ai_assistant.process_user_input_async(scenario)


async def broadcast_state():
    """定时广播状态给所有 WebSocket 客户端"""
    while True:
        if _state_manager and _connected_clients:
            state_data = {
                "type": "state_update",
                "timestamp": time.time(),
                "vehicle": _state_manager.get_dict(),
                "cabin": _cabin_state.get_dict() if _cabin_state else {},
            }
            payload = json.dumps(state_data, ensure_ascii=False)
            dead = []
            for ws in _connected_clients:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in _connected_clients:
                    _connected_clients.remove(ws)
        await asyncio.sleep(1.0 / 10)  # 10 Hz


async def push_ai_message(user_text: str, reply_text: str):
    """推送 AI 回复给前端"""
    msg = json.dumps({
        "type": "ai_reply",
        "user": user_text,
        "reply": reply_text,
        "timestamp": time.time(),
    }, ensure_ascii=False)
    dead = []
    for ws in _connected_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _connected_clients:
            _connected_clients.remove(ws)


def push_ai_message_sync(user_text: str, reply_text: str):
    """同步版本，供 AI 回调使用"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(push_ai_message(user_text, reply_text))
        else:
            loop.run_until_complete(push_ai_message(user_text, reply_text))
    except RuntimeError:
        pass


def start_server(state_manager, cabin_state=None, service_executor=None, ai_assistant=None):
    """在新线程中启动 Web HMI 服务"""
    import uvicorn

    set_dependencies(state_manager, cabin_state, service_executor, ai_assistant)

    @app.on_event("startup")
    async def startup_broadcast():
        asyncio.create_task(broadcast_state())

    def _run():
        uvicorn.run(
            app,
            host=settings.WEB_HMI_HOST,
            port=settings.WEB_HMI_PORT,
            log_level="warning",
        )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    print(f"[WEB-HMI] 服务已启动 http://localhost:{settings.WEB_HMI_PORT}")
    return thread
