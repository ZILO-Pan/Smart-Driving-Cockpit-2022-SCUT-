"""
统一消息协议
定义 TCP (Unity) 和 串口 (ESP32) 的数据格式
所有通信都用这里的格式，方便统一管理

改动指南:
- 给 Unity 增加数据字段: 修改 build_unity_packet()
- 给 ESP32 增加数据字段: 修改 build_servo_packet()
- 换协议格式(如 protobuf): 替换这个文件的序列化逻辑
"""

import json
import struct
import time
from core.vehicle_state import VehicleState


# ============ TCP → Unity 协议 (JSON) ============

def build_unity_packet(state: VehicleState) -> bytes:
    """
    构建发送给 Unity 的数据包
    格式: [4字节长度头][JSON数据]
    Unity 端按长度头读取完整 JSON

    Unity C# 解析示例:
        byte[] lenBuf = new byte[4];
        stream.Read(lenBuf, 0, 4);
        int len = BitConverter.ToInt32(lenBuf, 0);
        byte[] data = new byte[len];
        stream.Read(data, 0, len);
        string json = Encoding.UTF8.GetString(data);
    """
    packet = {
        "type": "vehicle_state",
        "timestamp": time.time(),
        "data": {
            # 运动状态
            "speed_kmh": round(state.speed_kmh, 1),
            "throttle": round(state.throttle, 3),
            "brake": round(state.brake, 3),
            "steer": round(state.steer, 4),
            "gear": state.gear,
            "is_reverse": state.is_reverse,

            # 位置（Unity 坐标系: x右 y上 z前）
            # CARLA 坐标系: x前 y右 z上 → 需要转换
            "position": {
                "x": round(state.location_y, 2),    # CARLA.y → Unity.x
                "y": round(state.location_z, 2),    # CARLA.z → Unity.y
                "z": round(state.location_x, 2),    # CARLA.x → Unity.z
            },
            "rotation": {
                "yaw": round(state.rotation_yaw, 2),
                "pitch": round(state.rotation_pitch, 2),
                "roll": round(state.rotation_roll, 2),
            },

            # HMI 显示用
            "wheel_angle_deg": round(state.wheel_angle_deg, 1),
            "autopilot": state.autopilot_enabled,
        }
    }

    json_bytes = json.dumps(packet, ensure_ascii=False).encode('utf-8')
    length_header = struct.pack('<I', len(json_bytes))  # 小端 4字节
    return length_header + json_bytes


def parse_unity_message(data: bytes) -> dict | None:
    """
    解析 Unity 发来的消息（如用户指令）
    Unity 也用同样的 [4字节长度头][JSON] 格式
    """
    try:
        if len(data) < 4:
            return None
        msg_len = struct.unpack('<I', data[:4])[0]
        if len(data) < 4 + msg_len:
            return None
        json_str = data[4:4 + msg_len].decode('utf-8')
        return json.loads(json_str)
    except Exception:
        return None


# ============ 串口 → ESP32 协议 (紧凑二进制) ============

# 帧格式: [0xAA][0x55][steer_high][steer_low][speed][checksum]
# 总共 6 字节，保持低延迟
SERIAL_HEADER = bytes([0xAA, 0x55])

def build_servo_packet(steer_angle_deg: float, speed_kmh: float) -> bytes:
    """
    构建发送给 ESP32 的舵机控制数据包
    - steer_angle_deg: -540~540 度 → 映射为 0~65535 (uint16)
    - speed_kmh: 0~255 km/h → uint8

    ESP32 端解析 (Arduino):
        if (Serial.read() == 0xAA && Serial.read() == 0x55) {
            uint16_t steer = (Serial.read() << 8) | Serial.read();
            uint8_t speed = Serial.read();
            uint8_t checksum = Serial.read();
            if (checksum == ((steer >> 8) + (steer & 0xFF) + speed) & 0xFF) {
                float angle = (steer / 65535.0) * 1080.0 - 540.0;
                // 控制舵机...
            }
        }
    """
    # 映射: -540~540 → 0~65535
    steer_normalized = (steer_angle_deg + 540.0) / 1080.0
    steer_normalized = max(0.0, min(1.0, steer_normalized))
    steer_uint16 = int(steer_normalized * 65535)

    speed_uint8 = int(max(0, min(255, speed_kmh)))

    # 校验和
    high = (steer_uint16 >> 8) & 0xFF
    low = steer_uint16 & 0xFF
    checksum = (high + low + speed_uint8) & 0xFF

    return SERIAL_HEADER + struct.pack('>HB', steer_uint16, speed_uint8) + bytes([checksum])


# ============ AI 助手消息格式 ============

def build_ai_request(user_text: str, vehicle_state: dict = None) -> dict:
    """构建发给豆包 AI 的请求上下文"""
    system_context = (
        "你是一个智能驾驶座舱AI助手。"
        "你可以回答驾驶相关问题，描述路况，提供导航建议。"
        "当前车辆正在L4自动驾驶模式运行。"
    )
    if vehicle_state:
        system_context += f"\n当前车速: {vehicle_state.get('speed_kmh', 0):.0f} km/h"
        system_context += f"\n当前档位: {vehicle_state.get('gear', 0)}"

    return {
        "system": system_context,
        "user": user_text,
        "vehicle_state": vehicle_state
    }
