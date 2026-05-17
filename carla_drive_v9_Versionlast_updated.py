"""
CARLA Drive v9 hybrid
=====================
自动模式：motorMoveTo 跟随 CARLA 实际前轮角，保证“方向盘像自动驾驶在打”。
手动模式：方向盘控制车辆；DirectInput 恒力只做导师阻力，不用 motorMoveTo 硬拽人手。

核心规则：
  - 运行中永不 motorStopMove / CenterWheel，只在退出清理时 stop。
  - 自动模式可选 motorMoveTo 精准映射，或 force 导师力自转实验。
  - 手动模式持续轻量 keepalive，切回自动时立即重新发送目标，减少电机睡死。
  - 按钮 31 加去抖，避免一次按压触发多次自动/手动切换。
"""
import ctypes
import ctypes.wintypes
import pygame
import time
import threading
import math
import sys
import os

# ====== 配置 ======
SDK_PATH = r"D:\MOZA\MOZA_SDK\1.0.1.8\MSVC2022-64\bin\MOZA_SDK.dll"

STEERING_AXIS  = 0
THROTTLE_AXIS  = 2
BRAKE_AXIS     = 5
SWITCH_BUTTON  = 31
REVERSE_BUTTON = 34
STEERING_RANGE = 450.0
WHEEL_MAX_DEG  = 450.0

STEER_RATIO_FALLBACK = STEERING_RANGE / 70.0
STEER_RATIO = STEER_RATIO_FALLBACK

MIN_RESEND_MS = 200
SPEED_K   = 5.0
SPEED_MIN = 150.0
SPEED_MAX = 500.0

STEER_SMOOTH_ALPHA = 0.5
SWITCH_DEBOUNCE_S = 0.45
DEFAULT_MODE = "MANUAL"      # "MANUAL" 或 "AUTO"
AUTO_ACTUATION_MODE = "force"  # "force" 导师力自转实验；"motor" 精准 motorMoveTo
AUTO_FORCE_SOURCE = "route"     # "tire" 更贴近前轮；"route" 看前方路线
AUTO_CENTER_DEAD_BAND = 8.0
AUTO_FORCE_DEAD_BAND = 4.0

# === 自动直线过零轻推 ===
CENTER_NUDGE_ENABLED = True
CENTER_NUDGE_START_DEG = 5.0
CENTER_NUDGE_MAX_DEG = 35.0
CENTER_NUDGE_TARGET_DEG = 28.0
CENTER_NUDGE_RELEASE_DEG = 6.0
CENTER_NUDGE_DURATION_S = 0.55
CENTER_NUDGE_COOLDOWN_S = 1.0
CENTER_NUDGE_FORCE_DEAD_BAND = 2.0

# === 直线检测 ===
STRAIGHT_TIRE_THRESHOLD = 1.5
STRAIGHT_DURATION_MS    = 400

# === 方向盘读数校准 ===
WHEEL_AUTO_ZERO_ON_START = True
WHEEL_ZERO_OFFSET_DEG = 9  # 手动微调：校准后仍偏右 +20°，就填 +20
WHEEL_READ_SCALE = 1.0       # 如果角度比例偏大/偏小，用这里微调
WHEEL_TARGET_OFFSET_DEG = 0.0 # 目标微调：target=0 时实体盘偏右 +20°，就填 -20

# === 手动模式导师力 ===
MENTOR_DEAD_BAND = 15
MIN_SPEED_FOR_MENTOR = 2.0
MENTOR_FORCE_KP = 18.0
MENTOR_FORCE_DAMPING = 0.7
MAX_MENTOR_FORCE = 1200
FORCE_SIGN = -1.0  # 如果手动导师力方向反了，改成 +1.0

STEER_SENSITIVITY = 1.0
THROTTLE_SCALE = 0.45

LOOKAHEAD_BASE = 6.0
LOOKAHEAD_SPEED_FACTOR = 0.3


def normalize_pedal(raw):
    val = (raw + 1.0) / 2.0
    val = max(0.0, min(1.0, val))
    return val if val > 0.02 else 0.0


def normalize_steering(raw):
    return max(-1.0, min(1.0, raw))


wheel_zero_offset_deg = WHEEL_ZERO_OFFSET_DEG


def raw_wheel_deg():
    return joy.get_axis(STEERING_AXIS) * STEERING_RANGE


def read_wheel_deg():
    angle = (raw_wheel_deg() - wheel_zero_offset_deg) * WHEEL_READ_SCALE
    return max(-WHEEL_MAX_DEG, min(WHEEL_MAX_DEG, angle))


def target_to_actuator_deg(target_angle):
    angle = target_angle + WHEEL_TARGET_OFFSET_DEG
    return max(-WHEEL_MAX_DEG, min(WHEEL_MAX_DEG, angle))


def calibrate_wheel_zero(samples=60):
    global wheel_zero_offset_deg
    if not WHEEL_AUTO_ZERO_ON_START:
        wheel_zero_offset_deg = WHEEL_ZERO_OFFSET_DEG
        return

    vals = []
    clk = pygame.time.Clock()
    for _ in range(samples):
        pygame.event.pump()
        vals.append(raw_wheel_deg())
        clk.tick(60)
    auto_zero = sum(vals) / len(vals)
    wheel_zero_offset_deg = auto_zero + WHEEL_ZERO_OFFSET_DEG
    print(f"wheel zero calibrated: raw={auto_zero:+.1f}°, trim={WHEEL_ZERO_OFFSET_DEG:+.1f}°, offset={wheel_zero_offset_deg:+.1f}°")


# ====== pygame ======
pygame.init()
pygame.joystick.init()
if pygame.joystick.get_count() == 0:
    print("未检测到控制器")
    sys.exit(1)

joy = pygame.joystick.Joystick(0)
joy.init()
print(f"控制器: {joy.get_name()}")

SCREEN_W, SCREEN_H = 1280, 720
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
pygame.display.set_caption("CARLA Drive v9 hybrid - ESC退出")
hwnd = pygame.display.get_wm_info()['window']
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
user32.SetForegroundWindow(hwnd)


def force_foreground(target_hwnd):
    fore_hwnd = user32.GetForegroundWindow()
    if fore_hwnd == target_hwnd:
        return
    fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
    cur_thread = kernel32.GetCurrentThreadId()
    if fore_thread != cur_thread:
        user32.AttachThreadInput(fore_thread, cur_thread, True)
        user32.SetForegroundWindow(target_hwnd)
        user32.AttachThreadInput(fore_thread, cur_thread, False)
    else:
        user32.SetForegroundWindow(target_hwnd)


# ====== SDK ======
print("加载 MOZA SDK...")
sdk = ctypes.CDLL(SDK_PATH)

install = sdk['?installMozaSDK@moza@@YAXXZ']
install.restype, install.argtypes = None, []

remove_sdk = sdk['?removeMozaSDK@moza@@YAXXZ']
remove_sdk.restype, remove_sdk.argtypes = None, []

CenterWheel_func = sdk['?CenterWheel@moza@@YA?AW4ERRORCODE@@XZ']
CenterWheel_func.restype = ctypes.c_int
CenterWheel_func.argtypes = []

motorMoveTo_func = sdk['?motorMoveTo@moza@@YAXPEAUHWND__@@MMAEAW4ERRORCODE@@@Z']
motorMoveTo_func.restype = None
motorMoveTo_func.argtypes = [ctypes.wintypes.HWND, ctypes.c_float, ctypes.c_float,
                              ctypes.POINTER(ctypes.c_int)]

motorStopMove_func = sdk['?motorStopMove@moza@@YAXXZ']
motorStopMove_func.restype = None
motorStopMove_func.argtypes = []

class SharedPtr(ctypes.Structure):
    _fields_ = [("ptr", ctypes.c_void_p), ("ctrl", ctypes.c_void_p)]


createConstantForce = sdk['?createWheelbaseETConstantForce@moza@@YA?AV?$shared_ptr@VETConstantForce@direct_input@RS21@@@std@@PEAUHWND__@@AEAW4ERRORCODE@@@Z']
createConstantForce.restype = SharedPtr
createConstantForce.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.c_int)]

effectStart = sdk['?start@Effect@direct_input@RS21@@QEAAXXZ']
effectStart.restype = None
effectStart.argtypes = [ctypes.c_void_p]

effectStop = sdk['?stop@Effect@direct_input@RS21@@QEAAXXZ']
effectStop.restype = None
effectStop.argtypes = [ctypes.c_void_p]

effectSetDuration = sdk['?setDuration@Effect@direct_input@RS21@@QEAAXK@Z']
effectSetDuration.restype = None
effectSetDuration.argtypes = [ctypes.c_void_p, ctypes.c_ulong]

constantForceSetMagnitude = sdk['?setMagnitude@ETConstantForce@direct_input@RS21@@QEAAXJ@Z']
constantForceSetMagnitude.restype = None
constantForceSetMagnitude.argtypes = [ctypes.c_void_p, ctypes.c_long]

setMotorSpringStrength = sdk['?setMotorSpringStrength@moza@@YA?AW4ERRORCODE@@H@Z']
setMotorSpringStrength.restype = ctypes.c_int
setMotorSpringStrength.argtypes = [ctypes.c_int]

setMotorNaturalDamper = sdk['?setMotorNaturalDamper@moza@@YA?AW4ERRORCODE@@H@Z']
setMotorNaturalDamper.restype = ctypes.c_int
setMotorNaturalDamper.argtypes = [ctypes.c_int]

getMotorSpringStrength = sdk['?getMotorSpringStrength@moza@@YAHAEAW4ERRORCODE@@@Z']
getMotorSpringStrength.restype = ctypes.c_int
getMotorSpringStrength.argtypes = [ctypes.POINTER(ctypes.c_int)]

getMotorNaturalDamper = sdk['?getMotorNaturalDamper@moza@@YAHAEAW4ERRORCODE@@@Z']
getMotorNaturalDamper.restype = ctypes.c_int
getMotorNaturalDamper.argtypes = [ctypes.POINTER(ctypes.c_int)]

print("SDK 接口加载完成")

install()
print("SDK init OK")
time.sleep(1)
CenterWheel_func()
print("wheel centered")
time.sleep(1)

err = ctypes.c_int(0)
backup_spring = getMotorSpringStrength(ctypes.byref(err))
backup_damper = getMotorNaturalDamper(ctypes.byref(err))
print(f"备份 Pit House 设置: spring={backup_spring}%, damper={backup_damper}%")

warmup_clock = pygame.time.Clock()
for i in range(30):
    pygame.event.get()
    pygame.event.pump()
    screen.fill((20, 20, 30))
    pygame.display.flip()
    warmup_clock.tick(60)

err_warmup = ctypes.c_int(0)
motorMoveTo_func(ctypes.wintypes.HWND(hwnd), ctypes.c_float(10.0),
                 ctypes.c_float(150.0), ctypes.byref(err_warmup))
print(f"motor warmup -> 10° (err={err_warmup.value})")
time.sleep(1.0)
motorMoveTo_func(ctypes.wintypes.HWND(hwnd), ctypes.c_float(0.0),
                 ctypes.c_float(150.0), ctypes.byref(err_warmup))
time.sleep(0.5)
calibrate_wheel_zero()

cf = None
cf_shared = None
try:
    ff_err = ctypes.c_int(0)
    cf_shared = createConstantForce(ctypes.wintypes.HWND(hwnd), ctypes.byref(ff_err))
    cf = cf_shared.ptr
    if cf:
        effectSetDuration(cf, 0xFFFF)
        constantForceSetMagnitude(cf, 1)
        effectStart(cf)
        print(f"constant force ready (err={ff_err.value})")
    else:
        print(f"WARNING: constant force init failed (err={ff_err.value})")
except Exception as exc:
    cf = None
    print(f"WARNING: constant force unavailable: {exc}")


# ====== CARLA ======
import carla
import numpy as np

print("连接 CARLA...")
client = carla.Client('localhost', 2000)
client.set_timeout(10.0)
try:
    world = client.get_world()
except RuntimeError:
    print("无法连接 CARLA")
    remove_sdk()
    pygame.quit()
    sys.exit(1)
print(f"CARLA: {client.get_server_version()}")

for a in world.get_actors().filter('vehicle.*'):
    a.destroy()
for a in world.get_actors().filter('sensor.*'):
    a.destroy()
time.sleep(1)

bp_lib = world.get_blueprint_library()
spawn_pts = world.get_map().get_spawn_points()
vehicle_bp = bp_lib.filter('vehicle.tesla.model3')[0]

vehicle = None
for sp in spawn_pts:
    try:
        vehicle = world.spawn_actor(vehicle_bp, sp)
        break
    except RuntimeError:
        continue

if vehicle is None:
    print("无法生成车辆")
    remove_sdk()
    pygame.quit()
    sys.exit(1)

print(f"车辆: {vehicle.type_id}")

if not hasattr(vehicle, 'get_wheel_steer_angle'):
    print("ERROR: CARLA 版本太老")
    vehicle.destroy()
    remove_sdk()
    pygame.quit()
    sys.exit(1)

try:
    physics = vehicle.get_physics_control()
    front_max_steer = max(abs(w.max_steer_angle) for w in physics.wheels[:2])
    if front_max_steer > 1.0:
        STEER_RATIO = STEERING_RANGE / front_max_steer
    else:
        front_max_steer = STEERING_RANGE / STEER_RATIO
    print(f"前轮 max_steer_angle={front_max_steer:.1f}°, STEER_RATIO={STEER_RATIO:.3f}")
except Exception as exc:
    front_max_steer = STEERING_RANGE / STEER_RATIO
    print(f"WARNING: 无法读取前轮最大转角，使用 fallback ratio={STEER_RATIO:.3f}: {exc}")

carla_map = world.get_map()


# ====== FPV ======
fpv_surface = None
fpv_lock = threading.Lock()

cam_bp = bp_lib.find('sensor.camera.rgb')
cam_bp.set_attribute('image_size_x', str(SCREEN_W))
cam_bp.set_attribute('image_size_y', str(SCREEN_H))
cam_bp.set_attribute('fov', '100')

cam_transform = carla.Transform(
    carla.Location(x=0.4, y=-0.4, z=1.2),
    carla.Rotation(pitch=-5)
)
camera = world.spawn_actor(cam_bp, cam_transform, attach_to=vehicle)


def on_camera_image(image):
    global fpv_surface
    arr = np.frombuffer(image.raw_data, dtype=np.uint8)
    arr = arr.reshape((image.height, image.width, 4))
    rgb = arr[:, :, [2, 1, 0]]
    surf = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
    with fpv_lock:
        fpv_surface = surf


camera.listen(on_camera_image)
print("FPV 摄像头已挂载")

# ====== 状态 ======
current_mode = DEFAULT_MODE if DEFAULT_MODE in ("AUTO", "MANUAL") else "MANUAL"
is_reverse = False
btn_switch_last = False
btn_reverse_last = False
smoothed_target = 0.0
straight_start_time = None
last_switch_time = 0.0

vehicle.set_autopilot(current_mode == "AUTO")
if current_mode == "MANUAL":
    setMotorSpringStrength(0)
    setMotorNaturalDamper(0)
print("自动驾驶已启动" if current_mode == "AUTO" else "默认手动模式已启动")


# ====== ESC ======
_exit_flag = False


def _key_monitor():
    global _exit_flag
    while not _exit_flag:
        if user32.GetAsyncKeyState(0x1B) & 0x8000:
            _exit_flag = True
        time.sleep(0.05)


threading.Thread(target=_key_monitor, daemon=True).start()


# ====== 电机驱动（永不 stop）======
_last_send_time = 0.0
_cmd_count = 0

_prev_force_angle = 0.0
_prev_force_time = time.time()
center_nudge_active = False
center_nudge_until = 0.0
center_nudge_cooldown_until = 0.0
center_nudge_target = 0.0
center_nudge_start_sign = 0


def motor_command(target_angle, cur_angle, speed_override=None, apply_target_offset=True):
    global _last_send_time, _cmd_count
    target_angle = max(-WHEEL_MAX_DEG, min(WHEEL_MAX_DEG, target_angle))
    command_angle = target_to_actuator_deg(target_angle) if apply_target_offset else target_angle
    now = time.time()

    if (now - _last_send_time) * 1000 < MIN_RESEND_MS:
        return False

    if speed_override is not None:
        speed = speed_override
    else:
        error = abs(command_angle - cur_angle)
        speed = max(SPEED_MIN, min(SPEED_MAX, error * SPEED_K))

    err = ctypes.c_int(0)
    motorMoveTo_func(ctypes.wintypes.HWND(hwnd),
                     ctypes.c_float(command_angle),
                     ctypes.c_float(speed),
                     ctypes.byref(err))
    _last_send_time = now
    _cmd_count += 1
    return True


def set_mentor_force(value):
    if not cf:
        return
    mag = int(max(-MAX_MENTOR_FORCE, min(MAX_MENTOR_FORCE, value)))
    if abs(mag) < 20:
        mag = 1
    constantForceSetMagnitude(cf, mag)


def compute_guidance_force(target_angle, cur_angle, speed_kmh, dead_band=MENTOR_DEAD_BAND):
    global _prev_force_angle, _prev_force_time
    force_now = time.time()
    force_dt = max(0.005, min(0.05, force_now - _prev_force_time))
    wheel_speed_dps = (cur_angle - _prev_force_angle) / force_dt
    _prev_force_angle = cur_angle
    _prev_force_time = force_now

    control_target = target_to_actuator_deg(target_angle)
    guide_error = control_target - cur_angle
    if abs(guide_error) < dead_band:
        return 0

    speed_gain = max(0.25, min(1.0, speed_kmh / 35.0))
    raw_force = (MENTOR_FORCE_KP * guide_error
                 - MENTOR_FORCE_DAMPING * wheel_speed_dps)
    return FORCE_SIGN * raw_force * speed_gain


def compute_auto_force_target(tire_deg, speed_kmh):
    if AUTO_FORCE_SOURCE == "tire":
        target = tire_deg * STEER_RATIO
    else:
        target = compute_suggested_wheel_angle(speed_kmh)
        if target is None:
            target = tire_deg * STEER_RATIO

    if abs(target) < AUTO_CENTER_DEAD_BAND:
        return 0.0
    return max(-WHEEL_MAX_DEG, min(WHEEL_MAX_DEG, target))


def apply_center_nudge(base_target, cur_angle, in_straight, now):
    global center_nudge_active, center_nudge_until
    global center_nudge_cooldown_until, center_nudge_target, center_nudge_start_sign

    if not CENTER_NUDGE_ENABLED or not in_straight or abs(base_target) > 0.1:
        center_nudge_active = False
        return base_target, False

    cur_abs = abs(cur_angle)
    if center_nudge_active:
        crossed_center = center_nudge_start_sign * cur_angle <= 0
        close_enough = cur_abs <= CENTER_NUDGE_RELEASE_DEG
        expired = now >= center_nudge_until
        if crossed_center or close_enough or expired:
            center_nudge_active = False
            center_nudge_cooldown_until = now + CENTER_NUDGE_COOLDOWN_S
            return base_target, False
        return center_nudge_target, True

    can_start = (
        now >= center_nudge_cooldown_until
        and CENTER_NUDGE_START_DEG <= cur_abs <= CENTER_NUDGE_MAX_DEG
    )
    if can_start:
        center_nudge_start_sign = 1 if cur_angle > 0 else -1
        center_nudge_target = -center_nudge_start_sign * CENTER_NUDGE_TARGET_DEG
        center_nudge_until = now + CENTER_NUDGE_DURATION_S
        center_nudge_active = True
        return center_nudge_target, True

    return base_target, False


# ====== waypoint ======
def compute_suggested_wheel_angle(speed_kmh):
    if speed_kmh < MIN_SPEED_FOR_MENTOR:
        return None
    try:
        veh_transform = vehicle.get_transform()
        veh_loc = veh_transform.location
        veh_yaw = math.radians(veh_transform.rotation.yaw)

        cur_wp = carla_map.get_waypoint(veh_loc, project_to_road=True,
                                         lane_type=carla.LaneType.Driving)
        if cur_wp is None:
            return None

        lookahead = LOOKAHEAD_BASE + speed_kmh * LOOKAHEAD_SPEED_FACTOR
        lookahead = max(4.0, min(25.0, lookahead))

        next_wps = cur_wp.next(lookahead)
        if not next_wps:
            return None
        target_wp = next_wps[0]
        target_loc = target_wp.transform.location

        dx = target_loc.x - veh_loc.x
        dy = target_loc.y - veh_loc.y
        local_x = math.cos(-veh_yaw) * dx - math.sin(-veh_yaw) * dy
        local_y = math.sin(-veh_yaw) * dx + math.cos(-veh_yaw) * dy

        if abs(local_x) < 0.5:
            return 0.0

        alpha = math.atan2(local_y, local_x)
        wheelbase = 2.875
        Ld = math.sqrt(local_x ** 2 + local_y ** 2)
        front_wheel_rad = math.atan2(2 * wheelbase * math.sin(alpha), Ld)
        front_wheel_deg = math.degrees(front_wheel_rad)

        front_wheel_deg = max(-70.0, min(70.0, front_wheel_deg))
        return front_wheel_deg * STEER_RATIO
    except Exception:
        return None


# ====== 清理（唯一 stop 的地方）======
_cleaning = False


def cleanup():
    global _cleaning
    if _cleaning:
        return
    _cleaning = True
    print("\n正在清理...")
    try:
        set_mentor_force(0)
        if cf:
            effectStop(cf)
    except Exception:
        pass
    try:
        motorStopMove_func()
    except Exception:
        pass
    try:
        setMotorSpringStrength(backup_spring)
        setMotorNaturalDamper(backup_damper)
        print(f"已恢复 spring={backup_spring}%, damper={backup_damper}%")
    except Exception:
        pass
    time.sleep(0.2)
    try:
        camera.stop()
        camera.destroy()
    except Exception:
        pass
    try:
        vehicle.set_autopilot(False)
        vehicle.destroy()
    except Exception:
        pass
    time.sleep(0.3)
    try:
        remove_sdk()
    except Exception:
        pass
    time.sleep(0.3)
    pygame.quit()
    print("退出完成")
    os._exit(0)


# ====== 主循环 ======
print("\n" + "=" * 60)
print("CARLA Drive v9 hybrid 运行中")
print(f"  STEER_RATIO    = {STEER_RATIO}")
print(f"  默认模式: {current_mode}")
print(f"  自动执行: {AUTO_ACTUATION_MODE} / source={AUTO_FORCE_SOURCE}")
print(f"  直线检测: |tire| < {STRAIGHT_TIRE_THRESHOLD}° 持续 {STRAIGHT_DURATION_MS}ms")
print(f"  过零轻推: enabled={CENTER_NUDGE_ENABLED}, start={CENTER_NUDGE_START_DEG:.0f}°..{CENTER_NUDGE_MAX_DEG:.0f}°, target={CENTER_NUDGE_TARGET_DEG:.0f}°")
print(f"  方向盘校准: read_offset={wheel_zero_offset_deg:+.1f}°, target_offset={WHEEL_TARGET_OFFSET_DEG:+.1f}°, scale={WHEEL_READ_SCALE:.3f}, auto_zero={WHEEL_AUTO_ZERO_ON_START}")
print(f"  手动转向灵敏度: {STEER_SENSITIVITY:.2f} (1.0 = 450° 对 CARLA steer 1.0)")
print(f"  手动导师力: KP={MENTOR_FORCE_KP}, damping={MENTOR_FORCE_DAMPING}, max={MAX_MENTOR_FORCE}, sign={FORCE_SIGN:+.0f}")
print(f"  规则: 永不 motorStopMove / CenterWheel（运行中）")
print(f"  按钮 {SWITCH_BUTTON}: 自动/手动")
print(f"  按钮 {REVERSE_BUTTON}: 倒车")
print("  ESC: 退出")
print("=" * 60)

font = pygame.font.Font(None, 32)
font_small = pygame.font.Font(None, 24)
clock = pygame.time.Clock()


def draw_mentor_arrow(screen, suggested_wheel, current_wheel):
    if suggested_wheel is None:
        return
    error = suggested_wheel - current_wheel
    if abs(error) < MENTOR_DEAD_BAND:
        pygame.draw.circle(screen, (80, 255, 80), (SCREEN_W // 2, 100), 8)
        return
    cx, cy = SCREEN_W // 2, 100
    arrow_len = min(150, abs(error) * 1.5)
    direction = 1 if error > 0 else -1
    color = (255, 200, 80) if abs(error) < 50 else (255, 100, 80)
    pygame.draw.rect(screen, color,
                     (cx - direction * arrow_len if direction < 0 else cx,
                      cy - 4, arrow_len, 8))
    tip_x = cx + direction * arrow_len
    pygame.draw.polygon(screen, color, [
        (tip_x, cy - 12),
        (tip_x + direction * 16, cy),
        (tip_x, cy + 12),
    ])


while True:
    if _exit_flag:
        cleanup()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            cleanup()
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            cleanup()

    pygame.event.pump()

    if user32.GetForegroundWindow() != hwnd:
        force_foreground(hwnd)

    # ===== 按钮 =====
    btn_switch_now = joy.get_button(SWITCH_BUTTON)
    now = time.time()
    if btn_switch_now and not btn_switch_last and now - last_switch_time >= SWITCH_DEBOUNCE_S:
        last_switch_time = now
        if current_mode == "AUTO":
            current_mode = "MANUAL"
            vehicle.set_autopilot(False)
            set_mentor_force(0)
            # 不 stop！只换 target（v6 原则）
            setMotorSpringStrength(0)
            setMotorNaturalDamper(0)
            is_reverse = False
            straight_start_time = None
            _prev_force_angle = read_wheel_deg()
            _prev_force_time = time.time()
            print(f"\n[模式] -> MANUAL")
        else:
            current_mode = "AUTO"
            is_reverse = False
            set_mentor_force(0)
            # 不 stop！用当前 tire 角度初始化 target，让电机无缝衔接
            try:
                tire_now = vehicle.get_wheel_steer_angle(carla.VehicleWheelLocation.FL_Wheel)
                smoothed_target = tire_now * STEER_RATIO
            except Exception:
                smoothed_target = 0.0
            smoothed_target = max(-WHEEL_MAX_DEG, min(WHEEL_MAX_DEG, smoothed_target))
            vehicle.set_autopilot(True)
            straight_start_time = None
            # 立即发一次命令让电机切换 target
            _last_send_time = 0.0
            motor_command(smoothed_target, read_wheel_deg())
            print(f"\n[模式] -> AUTO (init target = {smoothed_target:+.1f}°)")
    btn_switch_last = btn_switch_now

    btn_reverse_now = joy.get_button(REVERSE_BUTTON)
    if btn_reverse_now and not btn_reverse_last and current_mode == "MANUAL":
        is_reverse = not is_reverse
        print(f"\n[档位] -> {'R' if is_reverse else 'D'}")
    btn_reverse_last = btn_reverse_now

    # ===== 车辆状态 =====
    v = vehicle.get_velocity()
    speed_kmh = 3.6 * (v.x ** 2 + v.y ** 2 + v.z ** 2) ** 0.5
    cur_angle = read_wheel_deg()

    suggested_wheel_angle = None

    # ===== 模式逻辑 =====
    if current_mode == "AUTO":
        tire_deg = vehicle.get_wheel_steer_angle(carla.VehicleWheelLocation.FL_Wheel)
        raw_target = tire_deg * STEER_RATIO
        smoothed_target += STEER_SMOOTH_ALPHA * (raw_target - smoothed_target)
        if abs(smoothed_target) < 1.0 and abs(raw_target) < 2.0:
            smoothed_target = 0.0

        # === 直线检测 ===
        is_tire_straight = abs(tire_deg) < STRAIGHT_TIRE_THRESHOLD
        now = time.time()
        if is_tire_straight:
            if straight_start_time is None:
                straight_start_time = now
            straight_duration_ms = (now - straight_start_time) * 1000
        else:
            straight_start_time = None
            straight_duration_ms = 0

        in_straight = straight_duration_ms >= STRAIGHT_DURATION_MS
        status = "straight" if in_straight else "turning"

        if AUTO_ACTUATION_MODE == "force":
            auto_target = compute_auto_force_target(tire_deg, speed_kmh)
            if in_straight:
                auto_target = 0.0
            auto_target, nudge_on = apply_center_nudge(auto_target, cur_angle,
                                                       in_straight, now)
            force_dead_band = CENTER_NUDGE_FORCE_DEAD_BAND if nudge_on else AUTO_FORCE_DEAD_BAND
            mentor_force = compute_guidance_force(auto_target, cur_angle, speed_kmh,
                                                  dead_band=force_dead_band)
            set_mentor_force(mentor_force)
            motor_command(cur_angle, cur_angle, speed_override=50,
                          apply_target_offset=False)
            shown_target = auto_target
            if nudge_on:
                status = "nudge"
        else:
            set_mentor_force(0)
            shown_target = 0.0 if in_straight else smoothed_target
            shown_target, nudge_on = apply_center_nudge(shown_target, cur_angle,
                                                        in_straight, now)
            motor_command(shown_target, cur_angle)
            if nudge_on:
                status = "nudge"

        print(f"  [AUTO|{AUTO_ACTUATION_MODE}|{status:9s}] tire:{tire_deg:+5.1f}° "
              f"target:{shown_target:+6.1f}° cur:{cur_angle:+6.1f}° "
              f"spd:{speed_kmh:5.1f}km/h cmds:{_cmd_count}   ", end='\r')

    else:
        # 手动驾驶
        steer = normalize_steering((cur_angle / STEERING_RANGE) * STEER_SENSITIVITY)
        throttle = normalize_pedal(joy.get_axis(THROTTLE_AXIS)) * THROTTLE_SCALE
        brake = normalize_pedal(joy.get_axis(BRAKE_AXIS))

        vehicle.apply_control(carla.VehicleControl(
            throttle=throttle,
            steer=steer,
            brake=brake,
            reverse=is_reverse,
            hand_brake=False,
            manual_gear_shift=False
        ))

        suggested_wheel_angle = compute_suggested_wheel_angle(speed_kmh)
        mentor_force = 0

        if suggested_wheel_angle is not None:
            mentor_force = compute_guidance_force(suggested_wheel_angle, cur_angle, speed_kmh)
        else:
            _prev_force_angle = cur_angle
            _prev_force_time = time.time()

        set_mentor_force(mentor_force)

        # 手动模式仍轻量 keepalive：target=当前位置，避免切回 AUTO 时 motorMoveTo 睡死。
        motor_command(cur_angle, cur_angle, speed_override=50,
                      apply_target_offset=False)

        print(f"  [MAN ] sug:{suggested_wheel_angle if suggested_wheel_angle else 0:+6.1f}° "
              f"cur:{cur_angle:+6.1f}° force:{mentor_force:+6.0f} "
              f"spd:{speed_kmh:5.1f}km/h cmds:{_cmd_count}   ", end='\r')

    # ===== 渲染 =====
    with fpv_lock:
        surf = fpv_surface
    if surf is not None:
        screen.blit(surf, (0, 0))

    gear = "R" if is_reverse else "D"
    mode_color = (100, 255, 100) if current_mode == "AUTO" else (255, 200, 80)
    hud1 = font.render(f"[{current_mode}] [{gear}]  {speed_kmh:.0f} km/h",
                       True, mode_color)
    screen.blit(hud1, (20, 20))

    if current_mode == "MANUAL":
        thr = normalize_pedal(joy.get_axis(THROTTLE_AXIS))
        brk = normalize_pedal(joy.get_axis(BRAKE_AXIS))
        hud2 = font.render(f"THR:{thr:.0%}  BRK:{brk:.0%}  STEER:{cur_angle:+.0f}°",
                           True, (255, 255, 255))
        screen.blit(hud2, (20, 55))

        if suggested_wheel_angle is not None:
            err = suggested_wheel_angle - cur_angle
            hint = f"建议: {suggested_wheel_angle:+.0f}°  偏差: {err:+.0f}°"
            color = (100, 255, 100) if abs(err) < MENTOR_DEAD_BAND else \
                    (255, 200, 80) if abs(err) < 50 else (255, 100, 100)
            hud3 = font_small.render(hint, True, color)
            screen.blit(hud3, (20, 90))
            draw_mentor_arrow(screen, suggested_wheel_angle, cur_angle)
    else:
        hud2 = font.render(f"Wheel:{cur_angle:+.0f}°  Target:{smoothed_target:+.0f}°",
                           True, (200, 200, 200))
        screen.blit(hud2, (20, 55))

    pygame.display.flip()
    clock.tick(60)
