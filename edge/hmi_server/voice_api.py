"""
语音对话 API 端点
- POST /api/voice/start  — 启动 RTC 语音 Bot
- POST /api/voice/stop   — 停止语音 Bot
- POST /api/voice/token  — 获取 RTC 加入房间 Token
- POST /api/voice/fc-callback — 接收 Function Calling 回调
"""

import json
import time
import asyncio
from typing import Optional

from fastapi import APIRouter, Request, WebSocket
from pydantic import BaseModel

from cloud.voice.rtc_service import start_voice_chat, stop_voice_chat, update_voice_chat, generate_rtc_token
from config import settings

router = APIRouter(prefix="/api/voice", tags=["voice"])

# 依赖注入（由 server.py 设置）
_service_executor = None
_cabin_state = None
_vehicle_state = None
_connected_ws_clients: list = None  # 引用 server.py 的 _connected_clients

# 当前活跃的语音会话
_active_sessions: dict = {}  # room_id → {task_id, bot_user_id, target_user_id}


def set_voice_dependencies(service_executor, cabin_state, vehicle_state, ws_clients):
    global _service_executor, _cabin_state, _vehicle_state, _connected_ws_clients
    _service_executor = service_executor
    _cabin_state = cabin_state
    _vehicle_state = vehicle_state
    _connected_ws_clients = ws_clients


class StartVoiceRequest(BaseModel):
    room_id: str = "nova_room_001"
    user_id: str = "hmi_user"


class StopVoiceRequest(BaseModel):
    room_id: str = "nova_room_001"


class TokenRequest(BaseModel):
    room_id: str = "nova_room_001"
    user_id: str = "hmi_user"


@router.post("/token")
async def get_token(req: TokenRequest):
    """获取 RTC 加入房间的 Token"""
    token = generate_rtc_token(req.room_id, req.user_id)
    return {
        "token": token,
        "app_id": settings.RTC_APP_ID,
        "room_id": req.room_id,
        "user_id": req.user_id,
    }


@router.post("/start")
async def start_voice(req: StartVoiceRequest):
    """启动 AI 语音 Bot 加入房间"""
    bot_user_id = "NOVA_bot"

    # FC 回调模式选择：
    # - 有公网 URL → 服务端回调模式（火山 POST 到你的后端）
    # - 无公网 URL → 客户端模式（FC 通过 RTC binary message 推到浏览器，浏览器调 /fc-execute）
    fc_url = None
    if settings.VOICE_CALLBACK_URL:
        fc_url = settings.VOICE_CALLBACK_URL.rstrip("/") + "/api/voice/fc-callback"
        print(f"[VOICE] FC 模式: 服务端回调 → {fc_url}")
    else:
        print("[VOICE] FC 模式: 客户端（RTC binary message → 浏览器执行 → /fc-execute）")

    result = start_voice_chat(
        room_id=req.room_id,
        bot_user_id=bot_user_id,
        target_user_id=req.user_id,
        fc_callback_url=fc_url,
    )

    if "Result" in result and result["Result"] == "ok":
        _active_sessions[req.room_id] = {
            "task_id": result.get("_task_id", ""),
            "bot_user_id": bot_user_id,
            "target_user_id": req.user_id,
            "started_at": time.time(),
        }
        return {"status": "ok", "room_id": req.room_id, "bot_user_id": bot_user_id}
    else:
        error = result.get("ResponseMetadata", {}).get("Error", {})
        return {"status": "error", "error": error}


@router.post("/stop")
async def stop_voice(req: StopVoiceRequest):
    """停止 AI 语音 Bot"""
    session = _active_sessions.pop(req.room_id, None)
    if session:
        result = stop_voice_chat(req.room_id, session["task_id"])
        return {"status": "ok"}
    return {"status": "no_active_session"}


@router.post("/fc-callback")
async def function_calling_callback(request: Request):
    """
    接收火山 RTC Function Calling 回调

    回调类型:
    - Type: "information" — 预通知（即将调用某函数）
    - Type: "tool_calls" — 实际的函数调用指令
    """
    body = await request.json()

    msg_type = body.get("Type", "")
    signature = body.get("Signature", "")
    room_id = body.get("RoomID", "")
    task_id = body.get("TaskID", "")

    # 验证签名
    if signature != settings.RTC_FC_SIGNATURE:
        print(f"[FC] Invalid signature: {signature}")
        return {"status": "invalid_signature"}

    if msg_type == "information":
        # 预通知：函数即将被调用
        info = json.loads(body.get("Message", "{}"))
        func_name = info.get("function", "")
        print(f"[FC] Notification: will call {func_name}")
        # 推送前端显示 "正在执行..."
        await _push_to_frontend({
            "type": "fc_pending",
            "function": func_name,
        })
        return {"status": "ok"}

    elif msg_type == "tool_calls":
        # 实际函数调用
        tool_calls = json.loads(body.get("Message", "[]"))
        results = []

        for call in tool_calls:
            func = call.get("function", {})
            func_name = func.get("name", "")
            arguments = json.loads(func.get("arguments", "{}"))
            call_id = call.get("id", "")

            print(f"[FC] Executing: {func_name}({arguments})")

            # 通过 ServiceExecutor 执行
            result_text = _execute_function(func_name, arguments)
            results.append({
                "tool_call_id": call_id,
                "content": result_text,
            })

            # 推送前端执行 HMI 动作
            real_action, real_params, error = _unpack_grouped_tool(func_name, arguments)
            if not error:
                await _push_to_frontend(_frontend_event(
                    real_action, real_params, result_text,
                    original_function=func_name,
                ))

            # 通过 UpdateVoiceChat 把工具结果返回给 AI（让 AI 继续说话）
            if room_id and task_id and call_id:
                update_voice_chat(room_id, task_id, call_id, result_text)

        # 同时在 HTTP response 中返回结果（兼容两种模式）
        return {"results": results}

    return {"status": "unknown_type"}


# 分组工具 → 真实 action 的分发表
_GROUPED_TOOL_DISPATCH = {
    "cabin_control": {"set_ac_temperature", "set_seat_ventilation", "toggle_window",
                      "set_ambient_light", "set_cabin_mode"},
    "media_nav_control": {"play_music", "set_destination", "change_lane"},
    "panel_control": {"toggle_adas", "toggle_navigation", "toggle_cabin_cards",
                      "toggle_service_panel", "toggle_3d_scene",
                      "open_service_card", "show_alert"},
    "unity_control": {"switch_camera", "reset_camera", "toggle_car_part",
                      "open_car_part", "close_car_part", "rotate_car"},
}


def _execute_function(func_name: str, params: dict) -> str:
    """执行 Function Calling 工具（支持分组工具分发）"""
    if not _service_executor:
        return "服务执行器未就绪"

    if func_name == "proactive_service_plan":
        return _execute_service_plan(params)

    # 分组工具分发
    if func_name in _GROUPED_TOOL_DISPATCH:
        real_action, real_params, error = _unpack_grouped_tool(func_name, params)
        if error:
            return error
        print(f"[FC] Dispatch: {func_name}.{real_action}({real_params})")
        return _execute_function(real_action, real_params)

    # query_state 单独处理（查询型，不是执行型）
    if func_name == "query_state":
        target = params.get("target", "")
        return _query_state(target)

    try:
        _service_executor.execute(func_name, params)

        descriptions = {
            "set_ac_temperature": f"已将空调设置为{params.get('temperature', '?')}°C",
            "set_seat_ventilation": f"座椅通风已{'开启' if params.get('on') else '关闭'}",
            "toggle_window": f"车窗已{'打开' if params.get('open') else '关闭'}",
            "set_ambient_light": f"氛围灯已切换为{params.get('color', '?')}色",
            "play_music": f"正在播放{params.get('title', '音乐')}",
            "set_cabin_mode": f"已切换到{params.get('mode', '?')}模式",
            "set_destination": f"导航目的地已设为{params.get('destination', '?')}",
            "change_lane": f"正在向{params.get('direction', '?')}变道",
            "open_service_card": f"已打开{params.get('service', '?')}服务",
            "show_alert": f"提示: {params.get('message', '')}",
            "toggle_adas": f"ADAS面板已{'显示' if params.get('show') else '隐藏'}",
            "toggle_navigation": f"导航面板已{'显示' if params.get('show') else '隐藏'}",
            "toggle_cabin_cards": f"座舱卡片已{'显示' if params.get('show') else '隐藏'}",
            "toggle_service_panel": f"服务面板已{'打开' if params.get('open') else '关闭'}",
            "toggle_3d_scene": f"3D展车场景已{'打开' if params.get('show') else '关闭'}",
            "switch_camera": f"已切换到{params.get('view', '默认')}视角",
            "reset_camera": "已重置到默认视角",
            "toggle_car_part": f"已切换{params.get('part', '')}状态",
            "open_car_part": f"已打开{params.get('part', '')}",
            "close_car_part": f"已关闭{params.get('part', '')}",
            "rotate_car": f"车辆已旋转到{params.get('angle', 0)}°" if params.get('mode') != 'reset' else "车辆已复位",
        }
        return descriptions.get(func_name, f"已执行{func_name}")
    except Exception as e:
        print(f"[FC] Execute error: {e}")
        return f"执行失败: {e}"


def _execute_service_plan(params: dict) -> str:
    """执行主动服务计划中的动作列表。"""
    params = params or {}
    actions = params.get("actions", []) or []
    results = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        action = item.get("action") or item.get("function") or item.get("name")
        action_params = item.get("params") or item.get("parameters") or {}
        if not action:
            continue
        results.append(_execute_function(action, action_params))

    feedback = params.get("hmi_feedback") or params.get("reason") or "已根据你的需求完成座舱服务计划"
    if results:
        return feedback + "；" + "；".join(results[:4])
    return feedback


def _query_state(target: str) -> str:
    """查询型工具，返回当前状态文本（让 AI 用语音播报）"""
    if target == "cabin" and _cabin_state:
        d = _cabin_state.get_dict()
        return (f"空调{d.get('ac_temperature', '?')}度，"
                f"氛围灯{d.get('ambient_light', '?')}色，"
                f"模式{d.get('cabin_mode', '?')}")
    elif target == "vehicle" and _vehicle_state:
        d = _vehicle_state.get_dict()
        return (f"当前车速{round(d.get('speed_kmh', 0))}公里每小时，"
                f"挡位{d.get('gear', '?')}，"
                f"自动驾驶{'开' if d.get('autopilot_enabled') else '关'}")
    elif target == "navigation" and _vehicle_state:
        d = _vehicle_state.get_dict()
        return f"目前在第{d.get('ego_lane_index', 0) + 1}车道，共{d.get('lane_count', 0)}车道"
    return "暂无可用状态"


def _unpack_grouped_tool(func_name: str, params: dict) -> tuple[str, dict, str]:
    """把 RTC 分组工具拆成 HMI/ServiceExecutor 能直接执行的真实动作。"""
    if func_name not in _GROUPED_TOOL_DISPATCH:
        return func_name, params or {}, ""

    params = params or {}
    real_action = params.get("action", "")
    real_params = params.get("params", {}) or {}
    if real_action not in _GROUPED_TOOL_DISPATCH[func_name]:
        return real_action, real_params, f"无效的{func_name}动作: {real_action}"
    return real_action, real_params, ""


def _frontend_event(func_name: str, params: dict, result_text: str,
                    original_function: str = None) -> dict:
    """生成前端可直接消费的 FC 执行事件。"""
    return {
        "type": "fc_executed",
        "function": func_name,
        "params": params or {},
        "result": result_text,
        "original_function": original_function or func_name,
        "timestamp": time.time(),
    }


class FCExecuteRequest(BaseModel):
    room_id: str = "nova_room_001"
    function: str = ""
    params: dict = {}
    call_id: str = ""
    client_executed: bool = False


@router.post("/fc-execute")
async def fc_execute_from_client(req: FCExecuteRequest):
    """
    客户端模式 FC 执行：前端收到 RTC binary message 中的 tool_call，
    调此接口让后端执行 + 调 UpdateVoiceChat 通知 AI 结果
    """
    result_text = _execute_function(req.function, req.params)
    print(f"[FC-Client] {req.function}({req.params}) → {result_text}")

    real_action, real_params, error = _unpack_grouped_tool(req.function, req.params)
    if not error and not req.client_executed:
        await _push_to_frontend(_frontend_event(
            real_action, real_params, result_text,
            original_function=req.function,
        ))

    # 通知 AI 工具执行结果（让 AI 继续说话）
    session = _active_sessions.get(req.room_id)
    if session and req.call_id:
        task_id = session.get("task_id", "")
        if task_id:
            update_voice_chat(req.room_id, task_id, req.call_id, result_text)

    return {"status": "ok", "result": result_text}


async def _push_to_frontend(msg: dict):
    """通过 WebSocket 推送消息给前端"""
    if not _connected_ws_clients:
        return
    payload = json.dumps(msg, ensure_ascii=False)
    dead = []
    for ws in _connected_ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _connected_ws_clients:
            _connected_ws_clients.remove(ws)
