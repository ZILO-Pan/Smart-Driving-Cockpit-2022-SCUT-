# """
# CARLA 核心桥接模块
# 基于原始 follow_car.py 重构，增加:
# - 车辆状态输出到 VehicleStateManager
# - 摄像头画面可供 AI 视觉分析使用
# - 与主系统解耦，可独立运行测试

# 改动指南:
# - 换地图/天气: 修改 setup() 中的地图加载部分
# - 加传感器(激光雷达、IMU等): 在 _setup_sensors() 中添加
# - 调摄像头位置: 修改 _setup_cameras() 中的 Transform
# - 改 NPC 数量/行为: 修改 _spawn_npcs()
# """

# import carla
# import pygame
# import numpy as np
# import sys
# import random
# import threading
# import time

# from config import settings
# from core.vehicle_state import VehicleStateManager


# class CarlaBridge:
#     def __init__(self, state_manager: VehicleStateManager):
#         self.state_manager = state_manager

#         self.client = None
#         self.world = None
#         self.vehicle = None
#         self.traffic_manager = None
#         self.npc_vehicles = []

#         # 摄像头
#         self.cam_third = None
#         self.cam_cabin = None
#         self.img_third = None
#         self.img_cabin = None

#         # 视角切换
#         self.is_cabin_view = False

#         # pygame（本地预览用，可选）
#         self.display = None
#         self.clock = None
#         self.enable_preview = True

#         # 用于 AI 视觉分析的最新帧
#         self._latest_frame_lock = threading.Lock()
#         self._latest_frame = None  # numpy array, BGR

#         self._running = False

#     def setup(self):
#         """初始化 CARLA 连接、车辆、传感器"""
#         print("[CARLA] 正在连接...")
#         self.client = carla.Client(settings.CARLA_HOST, settings.CARLA_PORT)
#         self.client.set_timeout(30.0)
#         self.world = self.client.get_world()
#         print(f"[CARLA] 连接成功! 地图: {self.world.get_map().name}")

#         # 同步模式
#         world_settings = self.world.get_settings()
#         world_settings.synchronous_mode = True
#         world_settings.fixed_delta_seconds = 1.0 / settings.CARLA_FPS
#         self.world.apply_settings(world_settings)

#         # Traffic Manager
#         self.traffic_manager = self.client.get_trafficmanager(8000)
#         self.traffic_manager.set_synchronous_mode(True)
#         self.traffic_manager.set_global_distance_to_leading_vehicle(2.5)

#         # 生成主车
#         self._spawn_ego_vehicle()

#         # 生成 NPC
#         self._spawn_npcs()

#         # 创建摄像头
#         self._setup_cameras()

#         # pygame 本地预览
#         if self.enable_preview:
#             self._setup_pygame()

#         # 预热
#         for _ in range(5):
#             self.world.tick()

#         print("[CARLA] 初始化完成")

#     def _spawn_ego_vehicle(self):
#         bp_lib = self.world.get_blueprint_library()
#         tesla_bp = bp_lib.find('vehicle.tesla.model3')
#         spawn_points = self.world.get_map().get_spawn_points()

#         if not spawn_points:
#             print("[CARLA] 错误：没有可用的出生点!")
#             sys.exit(1)

#         random.shuffle(spawn_points)
#         self.vehicle = self.world.spawn_actor(tesla_bp, spawn_points[0])
#         self.vehicle.set_autopilot(True, 8000)
#         self._spawn_points = spawn_points
#         print("[CARLA] Tesla Model 3 已生成")

#     def _spawn_npcs(self):
#         bp_lib = self.world.get_blueprint_library()
#         vehicle_bps = bp_lib.filter('vehicle.*')

#         for sp in self._spawn_points[1:settings.CARLA_NPC_COUNT]:
#             try:
#                 npc = self.world.spawn_actor(random.choice(vehicle_bps), sp)
#                 npc.set_autopilot(True, 8000)
#                 self.npc_vehicles.append(npc)
#             except Exception:
#                 pass
#         print(f"[CARLA] 已生成 {len(self.npc_vehicles)} 辆 NPC")

#     def _setup_cameras(self):
#         bp_lib = self.world.get_blueprint_library()
#         cam_bp = bp_lib.find('sensor.camera.rgb')
#         cam_bp.set_attribute('image_size_x', str(settings.WINDOW_WIDTH))
#         cam_bp.set_attribute('image_size_y', str(settings.WINDOW_HEIGHT))

#         # 车外第三人称
#         cam_bp.set_attribute('fov', '90')
#         self.cam_third = self.world.spawn_actor(
#             cam_bp,
#             carla.Transform(
#                 carla.Location(x=-6.0, z=3.0),
#                 carla.Rotation(pitch=-15.0)
#             ),
#             attach_to=self.vehicle
#         )
#         self.cam_third.listen(lambda img: self._on_camera_image(img, 'third'))

#         # 车内驾驶舱
#         cam_bp.set_attribute('fov', '100')
#         self.cam_cabin = self.world.spawn_actor(
#             cam_bp,
#             carla.Transform(
#                 carla.Location(x=0.3, y=-0.3, z=1.2),
#                 carla.Rotation(pitch=-5.0)
#             ),
#             attach_to=self.vehicle
#         )
#         self.cam_cabin.listen(lambda img: self._on_camera_image(img, 'cabin'))
#         print("[CARLA] 摄像头已创建")

#     def _on_camera_image(self, image, which):
#         """摄像头回调 - 保存图像数据"""
#         array = np.frombuffer(image.raw_data, dtype=np.uint8)
#         array = array.reshape(
#             (settings.WINDOW_HEIGHT, settings.WINDOW_WIDTH, 4)
#         )[:, :, :3][:, :, ::-1]

#         if which == 'third':
#             self.img_third = array
#         else:
#             self.img_cabin = array

#         # 更新供 AI 视觉分析用的最新帧
#         with self._latest_frame_lock:
#             self._latest_frame = array.copy()

#     def _update_vehicle_state(self):
#         """从 CARLA 读取车辆状态，写入 StateManager"""
#         if not self.vehicle:
#             return

#         v = self.vehicle.get_velocity()
#         speed = 3.6 * (v.x**2 + v.y**2 + v.z**2)**0.5

#         control = self.vehicle.get_control()
#         transform = self.vehicle.get_transform()

#         self.state_manager.update(
#             speed_kmh=speed,
#             throttle=control.throttle,
#             brake=control.brake,
#             steer=control.steer,
#             gear=control.gear,
#             is_reverse=control.reverse,
#             location_x=transform.location.x,
#             location_y=transform.location.y,
#             location_z=transform.location.z,
#             rotation_yaw=transform.rotation.yaw,
#             rotation_pitch=transform.rotation.pitch,
#             rotation_roll=transform.rotation.roll,
#             wheel_angle_deg=control.steer * 540.0,
#             autopilot_enabled=True,
#         )

#     def get_latest_frame(self) -> np.ndarray | None:
#         """获取最新摄像头画面（供 AI 视觉分析）"""
#         with self._latest_frame_lock:
#             return self._latest_frame.copy() if self._latest_frame is not None else None

#     def _setup_pygame(self):
#         pygame.init()
#         self.display = pygame.display.set_mode(
#             (settings.WINDOW_WIDTH, settings.WINDOW_HEIGHT)
#         )
#         pygame.display.set_caption("Smart Cockpit | SPACE: View | ESC: Quit")
#         self.clock = pygame.time.Clock()

#     def run(self):
#         """主循环"""
#         self._running = True
#         print("[CARLA] 主循环启动")

#         while self._running:
#             self.world.tick()

#             # 更新车辆状态
#             self._update_vehicle_state()

#             # pygame 事件处理
#             if self.enable_preview:
#                 for event in pygame.event.get():
#                     if event.type == pygame.QUIT:
#                         self._running = False
#                     elif event.type == pygame.KEYDOWN:
#                         if event.key == pygame.K_ESCAPE:
#                             self._running = False
#                         elif event.key == pygame.K_SPACE:
#                             self.is_cabin_view = not self.is_cabin_view

#                 # 渲染
#                 img = self.img_cabin if self.is_cabin_view else self.img_third
#                 if img is not None:
#                     surface = pygame.surfarray.make_surface(img.swapaxes(0, 1))
#                     self.display.blit(surface, (0, 0))

#                 self._draw_hud()
#                 pygame.display.flip()
#                 self.clock.tick(settings.CARLA_FPS)

#     def _draw_hud(self):
#         font = pygame.font.SysFont('arial', 22, bold=True)
#         state = self.state_manager.get()
#         view_text = "Cabin" if self.is_cabin_view else "Third Person"

#         lines = [
#             f"View: {view_text}",
#             f"Speed: {state.speed_kmh:.0f} km/h",
#             f"Steer: {state.steer:.2f}",
#             "SPACE: Switch | ESC: Quit"
#         ]
#         y = 15
#         for line in lines:
#             shadow = font.render(line, True, (0, 0, 0))
#             text = font.render(line, True, (255, 255, 255))
#             self.display.blit(shadow, (17, y + 2))
#             self.display.blit(text, (15, y))
#             y += 30

#     def stop(self):
#         self._running = False

#     def cleanup(self):
#         """清理所有 CARLA 资源"""
#         print("[CARLA] 正在清理...")

#         if self.world:
#             s = self.world.get_settings()
#             s.synchronous_mode = False
#             s.fixed_delta_seconds = None
#             self.world.apply_settings(s)

#         for cam in [self.cam_third, self.cam_cabin]:
#             if cam:
#                 try:
#                     cam.stop()
#                     cam.destroy()
#                 except Exception:
#                     pass

#         for npc in self.npc_vehicles:
#             try:
#                 npc.set_autopilot(False, 8000)
#                 npc.destroy()
#             except Exception:
#                 pass

#         if self.vehicle:
#             try:
#                 self.vehicle.set_autopilot(False, 8000)
#                 self.vehicle.destroy()
#             except Exception:
#                 pass

#         if self.traffic_manager:
#             self.traffic_manager.set_synchronous_mode(False)

#         pygame.quit()
#         print("[CARLA] 清理完成")

"""
CARLA 核心桥接模块 (增强版)
基于原始 follow_car.py 重构，增加:
- 车辆状态输出到 VehicleStateManager
- 摄像头画面可供 AI 视觉分析使用
- 按 1~8 切换地图+天气场景
- 按 C 触发极端交通事件（鬼探头、急停、逆行等）
- 与主系统解耦，可独立运行测试

快捷键:
  1~8    切换场景（地图+天气）
  C      触发随机极端交通事件
  SPACE  切换视角
  ESC    退出

改动指南:
- 加新场景: 在 SCENE_PRESETS 里追加
- 加新极端事件: 在 CHAOS_EVENTS 和对应方法里添加
- 调摄像头位置: 修改 _setup_cameras() 中的 Transform
"""

import carla
import pygame
import numpy as np
import sys
import random
import threading
import time
import math

from config import settings
from core.vehicle_state import VehicleStateManager


# ============ 场景预设 (按键 1~8) ============
SCENE_PRESETS = {
    pygame.K_1: {
        "name": "晴天城市",
        "map": "Town03",
        "weather": carla.WeatherParameters(
            cloudiness=10, precipitation=0, sun_altitude_angle=60,
            fog_density=0, wetness=0, wind_intensity=5,
        ),
        "npc_count": 30,
        "pedestrian_count": 20,
    },
    pygame.K_2: {
        "name": "暴雨夜间",
        "map": "Town03",
        "weather": carla.WeatherParameters(
            cloudiness=100, precipitation=90, sun_altitude_angle=-30,
            fog_density=20, wetness=100, wind_intensity=80,
            precipitation_deposits=80,
        ),
        "npc_count": 15,
        "pedestrian_count": 5,
    },
    pygame.K_3: {
        "name": "大雾清晨",
        "map": "Town05",
        "weather": carla.WeatherParameters(
            cloudiness=70, precipitation=0, sun_altitude_angle=5,
            fog_density=80, fog_distance=20, fog_falloff=2,
            wetness=30, wind_intensity=10,
        ),
        "npc_count": 20,
        "pedestrian_count": 10,
    },
    pygame.K_4: {
        "name": "黄昏高速",
        "map": "Town04",
        "weather": carla.WeatherParameters(
            cloudiness=40, precipitation=0, sun_altitude_angle=8,
            fog_density=5, wetness=0, wind_intensity=30,
            sun_azimuth_angle=270,
        ),
        "npc_count": 40,
        "pedestrian_count": 0,
    },
    pygame.K_5: {
        "name": "拥堵闹市",
        "map": "Town10HD",
        "weather": carla.WeatherParameters.ClearNoon,
        "npc_count": 50,
        "pedestrian_count": 40,
    },
    pygame.K_6: {
        "name": "雪后乡村",
        "map": "Town07",
        "weather": carla.WeatherParameters(
            cloudiness=90, precipitation=0, sun_altitude_angle=30,
            fog_density=10, wetness=60, wind_intensity=15,
        ),
        "npc_count": 10,
        "pedestrian_count": 5,
    },
    pygame.K_7: {
        "name": "午夜空城",
        "map": "Town01",
        "weather": carla.WeatherParameters(
            cloudiness=20, precipitation=0, sun_altitude_angle=-60,
            fog_density=5, wetness=10, wind_intensity=5,
        ),
        "npc_count": 5,
        "pedestrian_count": 2,
    },
    pygame.K_8: {
        "name": "暴风骤雨",
        "map": "Town02",
        "weather": carla.WeatherParameters(
            cloudiness=100, precipitation=100, sun_altitude_angle=15,
            fog_density=40, wetness=100, wind_intensity=100,
            precipitation_deposits=100,
        ),
        "npc_count": 20,
        "pedestrian_count": 10,
    },
}


# ============ 极端交通事件定义 ============
CHAOS_EVENTS = [
    "pedestrian_jaywalk",    # 行人鬼探头
    "vehicle_sudden_stop",   # 前车急停
    "vehicle_run_red",       # 闯红灯
    "vehicle_wrong_way",     # 逆行
    "vehicle_swerve",        # 急变道
    "pedestrian_group",      # 人群横穿
]


class CarlaBridge:
    def __init__(self, state_manager: VehicleStateManager):
        self.state_manager = state_manager

        self.client = None
        self.world = None
        self.vehicle = None
        self.traffic_manager = None
        self.npc_vehicles = []
        self.npc_walkers = []
        self.walker_controllers = []

        # 摄像头
        self.cam_third = None
        self.cam_cabin = None
        self.img_third = None
        self.img_cabin = None

        # 视角切换
        self.is_cabin_view = False

        # 当前场景
        self._current_scene_name = "默认"

        # pygame
        self.display = None
        self.clock = None
        self.enable_preview = True

        # AI 视觉分析用
        self._latest_frame_lock = threading.Lock()
        self._latest_frame = None

        # HUD 通知
        self._hud_notification = ""
        self._hud_notify_time = 0

        self._running = False

    # ================================================================
    #  初始化
    # ================================================================

    def setup(self):
        print("[CARLA] 正在连接...")
        self.client = carla.Client(settings.CARLA_HOST, settings.CARLA_PORT)
        self.client.set_timeout(30.0)
        self.world = self.client.get_world()
        print(f"[CARLA] 连接成功! 地图: {self.world.get_map().name}")

        self._apply_sync_settings()

        self.traffic_manager = self.client.get_trafficmanager(8000)
        self.traffic_manager.set_synchronous_mode(True)
        self.traffic_manager.set_global_distance_to_leading_vehicle(2.5)

        self._spawn_ego_vehicle()
        self._spawn_npcs(settings.CARLA_NPC_COUNT)
        self._spawn_walkers(20)
        self._setup_cameras()

        if self.enable_preview:
            self._setup_pygame()

        for _ in range(5):
            self.world.tick()

        self._current_scene_name = "默认"
        print("[CARLA] 初始化完成")
        print("\n========================================")
        print("  1~8:  切换场景(地图+天气)")
        print("  C:    触发极端交通事件")
        print("  SPACE: 切换视角")
        print("  ESC:  退出")
        print("========================================\n")

    def _apply_sync_settings(self):
        ws = self.world.get_settings()
        ws.synchronous_mode = True
        ws.fixed_delta_seconds = 1.0 / settings.CARLA_FPS
        self.world.apply_settings(ws)

    # ================================================================
    #  生成车辆和行人
    # ================================================================

    def _spawn_ego_vehicle(self):
        bp_lib = self.world.get_blueprint_library()
        tesla_bp = bp_lib.find('vehicle.tesla.model3')
        spawn_points = self.world.get_map().get_spawn_points()

        if not spawn_points:
            print("[CARLA] 错误：没有可用的出生点!")
            sys.exit(1)

        random.shuffle(spawn_points)
        self.vehicle = self.world.spawn_actor(tesla_bp, spawn_points[0])
        self.vehicle.set_autopilot(True, 8000)
        self._spawn_points = spawn_points
        print("[CARLA] Tesla Model 3 已生成")

    def _spawn_npcs(self, count):
        bp_lib = self.world.get_blueprint_library()
        vehicle_bps = bp_lib.filter('vehicle.*')

        for sp in self._spawn_points[1:count + 1]:
            try:
                bp = random.choice(vehicle_bps)
                if bp.has_attribute('color'):
                    colors = bp.get_attribute('color').recommended_values
                    bp.set_attribute('color', random.choice(colors))
                npc = self.world.spawn_actor(bp, sp)
                npc.set_autopilot(True, 8000)
                self.npc_vehicles.append(npc)
            except Exception:
                pass
        print(f"[CARLA] 已生成 {len(self.npc_vehicles)} 辆 NPC 车辆")

    def _spawn_walkers(self, count):
        """生成行人（AI 控制，随机在人行道上走）"""
        bp_lib = self.world.get_blueprint_library()
        walker_bps = bp_lib.filter('walker.pedestrian.*')
        controller_bp = bp_lib.find('controller.ai.walker')

        spawned = 0
        for _ in range(count):
            try:
                spawn_loc = self.world.get_random_location_from_navigation()
                if spawn_loc is None:
                    continue

                walker_bp = random.choice(walker_bps)
                if walker_bp.has_attribute('is_invincible'):
                    walker_bp.set_attribute('is_invincible', 'false')

                walker = self.world.spawn_actor(walker_bp, carla.Transform(spawn_loc))
                self.npc_walkers.append(walker)

                controller = self.world.spawn_actor(
                    controller_bp, carla.Transform(), attach_to=walker
                )
                self.walker_controllers.append(controller)
                spawned += 1
            except Exception:
                pass

        # 等一帧让控制器初始化
        self.world.tick()

        # 启动行人 AI
        for ctrl in self.walker_controllers:
            try:
                ctrl.start()
                dest = self.world.get_random_location_from_navigation()
                if dest:
                    ctrl.go_to_location(dest)
                ctrl.set_max_speed(1.0 + random.random() * 1.5)
            except Exception:
                pass

        print(f"[CARLA] 已生成 {spawned} 个行人")

    # ================================================================
    #  摄像头
    # ================================================================

    def _setup_cameras(self):
        bp_lib = self.world.get_blueprint_library()
        cam_bp = bp_lib.find('sensor.camera.rgb')
        cam_bp.set_attribute('image_size_x', str(settings.WINDOW_WIDTH))
        cam_bp.set_attribute('image_size_y', str(settings.WINDOW_HEIGHT))

        cam_bp.set_attribute('fov', '90')
        self.cam_third = self.world.spawn_actor(
            cam_bp,
            carla.Transform(
                carla.Location(x=-6.0, z=3.0),
                carla.Rotation(pitch=-15.0)
            ),
            attach_to=self.vehicle
        )
        self.cam_third.listen(lambda img: self._on_camera_image(img, 'third'))

        cam_bp.set_attribute('fov', '100')
        self.cam_cabin = self.world.spawn_actor(
            cam_bp,
            carla.Transform(
                carla.Location(x=0.3, y=-0.3, z=1.2),
                carla.Rotation(pitch=-5.0)
            ),
            attach_to=self.vehicle
        )
        self.cam_cabin.listen(lambda img: self._on_camera_image(img, 'cabin'))
        print("[CARLA] 摄像头已创建")

    def _on_camera_image(self, image, which):
        array = np.frombuffer(image.raw_data, dtype=np.uint8)
        array = array.reshape(
            (settings.WINDOW_HEIGHT, settings.WINDOW_WIDTH, 4)
        )[:, :, :3][:, :, ::-1]

        if which == 'third':
            self.img_third = array
        else:
            self.img_cabin = array

        with self._latest_frame_lock:
            self._latest_frame = array.copy()

    # ================================================================
    #  场景切换 (按键 1~8)
    # ================================================================

    def _switch_scene(self, key):
        """销毁当前所有 → 换地图 → 换天气 → 重新生成"""
        preset = SCENE_PRESETS.get(key)
        if not preset:
            return

        scene_name = preset["name"]
        target_map = preset["map"]
        print(f"\n[SCENE] 正在切换到: {scene_name} ({target_map})...")
        self._notify(f"切换场景: {scene_name}")

        # 1. 销毁摄像头
        self._destroy_cameras()

        # 2. 销毁所有 NPC
        self._destroy_all_npcs()

        # 3. 销毁主车
        if self.vehicle:
            try:
                self.vehicle.set_autopilot(False, 8000)
                self.vehicle.destroy()
            except Exception:
                pass
            self.vehicle = None

        # 4. 切换地图
        current_map = self.world.get_map().name.split('/')[-1]
        if current_map != target_map:
            print(f"[SCENE] 加载地图: {target_map}")
            self.world = self.client.load_world(target_map)
            time.sleep(2.0)
            self.world = self.client.get_world()
        else:
            print(f"[SCENE] 地图相同，跳过加载")

        # 5. 重新设置同步模式
        self._apply_sync_settings()

        # 6. 重新配置 Traffic Manager
        self.traffic_manager = self.client.get_trafficmanager(8000)
        self.traffic_manager.set_synchronous_mode(True)
        self.traffic_manager.set_global_distance_to_leading_vehicle(2.5)

        # 7. 设置天气
        self.world.set_weather(preset["weather"])

        # 8. 重新生成
        self._spawn_ego_vehicle()
        self._spawn_npcs(preset.get("npc_count", 30))
        self._spawn_walkers(preset.get("pedestrian_count", 20))
        self._setup_cameras()

        for _ in range(10):
            self.world.tick()

        self._current_scene_name = scene_name
        print(f"[SCENE] 场景切换完成: {scene_name}\n")
        self._notify(f"已切换: {scene_name}")

    def _destroy_cameras(self):
        for cam in [self.cam_third, self.cam_cabin]:
            if cam:
                try:
                    cam.stop()
                    cam.destroy()
                except Exception:
                    pass
        self.cam_third = None
        self.cam_cabin = None
        self.img_third = None
        self.img_cabin = None

    def _destroy_all_npcs(self):
        for ctrl in self.walker_controllers:
            try:
                ctrl.stop()
                ctrl.destroy()
            except Exception:
                pass
        self.walker_controllers.clear()

        for walker in self.npc_walkers:
            try:
                walker.destroy()
            except Exception:
                pass
        self.npc_walkers.clear()

        for npc in self.npc_vehicles:
            try:
                npc.set_autopilot(False, 8000)
                npc.destroy()
            except Exception:
                pass
        self.npc_vehicles.clear()

    # ================================================================
    #  极端交通事件 (按键 C)
    # ================================================================

    def _trigger_chaos_event(self):
        event = random.choice(CHAOS_EVENTS)
        print(f"[CHAOS] 触发事件: {event}")

        handler = {
            "pedestrian_jaywalk": self._chaos_pedestrian_jaywalk,
            "vehicle_sudden_stop": self._chaos_vehicle_sudden_stop,
            "vehicle_run_red": self._chaos_vehicle_run_red,
            "vehicle_wrong_way": self._chaos_vehicle_wrong_way,
            "vehicle_swerve": self._chaos_vehicle_swerve,
            "pedestrian_group": self._chaos_pedestrian_group,
        }
        handler.get(event, lambda: None)()

    def _chaos_pedestrian_jaywalk(self):
        """鬼探头：主车前方 15~25m 突然冲出一个行人"""
        try:
            bp_lib = self.world.get_blueprint_library()
            walker_bp = random.choice(bp_lib.filter('walker.pedestrian.*'))
            if walker_bp.has_attribute('is_invincible'):
                walker_bp.set_attribute('is_invincible', 'false')

            tf = self.vehicle.get_transform()
            yaw = math.radians(tf.rotation.yaw)
            dist = random.uniform(15, 25)
            lateral = random.choice([-5, 5])

            loc = carla.Location(
                x=tf.location.x + dist * math.cos(yaw) - lateral * math.sin(yaw),
                y=tf.location.y + dist * math.sin(yaw) + lateral * math.cos(yaw),
                z=tf.location.z + 1.0,
            )

            walker = self.world.try_spawn_actor(walker_bp, carla.Transform(loc))
            if walker is None:
                print("[CHAOS] 鬼探头行人生成失败")
                return

            ctrl_bp = bp_lib.find('controller.ai.walker')
            ctrl = self.world.spawn_actor(ctrl_bp, carla.Transform(), attach_to=walker)
            self.world.tick()
            ctrl.start()

            # 冲向马路对面
            target = carla.Location(
                x=loc.x + lateral * 2 * math.sin(yaw),
                y=loc.y - lateral * 2 * math.cos(yaw),
                z=loc.z,
            )
            ctrl.go_to_location(target)
            ctrl.set_max_speed(3.0 + random.random() * 2.0)  # 跑步

            self.npc_walkers.append(walker)
            self.walker_controllers.append(ctrl)

            self._notify("! 鬼探头！行人突然横穿")
            print("[CHAOS] 鬼探头行人已生成")
        except Exception as e:
            print(f"[CHAOS] 鬼探头失败: {e}")

    def _chaos_vehicle_sudden_stop(self):
        """前车急停：离主车最近的前方 NPC 紧急刹车"""
        try:
            if not self.npc_vehicles:
                return

            ego_loc = self.vehicle.get_location()
            ego_fwd = self.vehicle.get_transform().get_forward_vector()

            best, best_dist = None, 999
            for npc in self.npc_vehicles:
                try:
                    diff = npc.get_location() - ego_loc
                    dot = diff.x * ego_fwd.x + diff.y * ego_fwd.y
                    d = diff.length()
                    if 5 < d < 50 and dot > 0 and d < best_dist:
                        best, best_dist = npc, d
                except Exception:
                    pass

            if best is None:
                print("[CHAOS] 前方没有合适的 NPC")
                return

            best.set_autopilot(False, 8000)
            best.apply_control(carla.VehicleControl(throttle=0, brake=1, steer=0))

            def _restore():
                time.sleep(3.0)
                try:
                    best.set_autopilot(True, 8000)
                except Exception:
                    pass

            threading.Thread(target=_restore, daemon=True).start()

            self._notify(f"! 前车急停！距离 {best_dist:.0f}m")
            print(f"[CHAOS] 前车急停 {best_dist:.0f}m")
        except Exception as e:
            print(f"[CHAOS] 急停失败: {e}")

    def _chaos_vehicle_run_red(self):
        """闯红灯：让几辆 NPC 无视交通灯"""
        try:
            targets = random.sample(
                self.npc_vehicles, min(5, len(self.npc_vehicles))
            )
            for npc in targets:
                self.traffic_manager.ignore_lights_percentage(npc, 100.0)

            def _restore():
                time.sleep(15.0)
                for npc in targets:
                    try:
                        self.traffic_manager.ignore_lights_percentage(npc, 0.0)
                    except Exception:
                        pass

            threading.Thread(target=_restore, daemon=True).start()

            self._notify(f"! {len(targets)} 辆车闯红灯！")
            print(f"[CHAOS] {len(targets)} 辆车闯红灯")
        except Exception as e:
            print(f"[CHAOS] 闯红灯失败: {e}")

    def _chaos_vehicle_wrong_way(self):
        """逆行：强制一辆 NPC 变道 + 加速"""
        try:
            if not self.npc_vehicles:
                return

            target = random.choice(self.npc_vehicles)
            self.traffic_manager.force_lane_change(target, True)
            self.traffic_manager.distance_to_leading_vehicle(target, 0.5)
            self.traffic_manager.vehicle_percentage_speed_difference(target, -50)

            def _restore():
                time.sleep(10.0)
                try:
                    self.traffic_manager.distance_to_leading_vehicle(target, 2.5)
                    self.traffic_manager.vehicle_percentage_speed_difference(target, 0)
                except Exception:
                    pass

            threading.Thread(target=_restore, daemon=True).start()

            self._notify("! 有车辆逆行！")
            print("[CHAOS] 逆行车辆已触发")
        except Exception as e:
            print(f"[CHAOS] 逆行失败: {e}")

    def _chaos_vehicle_swerve(self):
        """急变道：前方 NPC 突然变道"""
        try:
            if not self.npc_vehicles:
                return

            ego_loc = self.vehicle.get_location()
            ego_fwd = self.vehicle.get_transform().get_forward_vector()

            nearby = []
            for npc in self.npc_vehicles:
                try:
                    diff = npc.get_location() - ego_loc
                    dot = diff.x * ego_fwd.x + diff.y * ego_fwd.y
                    if 10 < diff.length() < 40 and dot > 0:
                        nearby.append(npc)
                except Exception:
                    pass

            if not nearby:
                print("[CHAOS] 前方没有可变道的车辆")
                return

            target = random.choice(nearby)
            direction = random.choice([True, False])
            self.traffic_manager.force_lane_change(target, direction)
            self.traffic_manager.vehicle_percentage_speed_difference(target, -30)

            def _restore():
                time.sleep(5.0)
                try:
                    self.traffic_manager.vehicle_percentage_speed_difference(target, 0)
                except Exception:
                    pass

            threading.Thread(target=_restore, daemon=True).start()

            side = "右" if direction else "左"
            self._notify(f"! 前车急变道（向{side}）！")
            print(f"[CHAOS] 前车急变道 {side}")
        except Exception as e:
            print(f"[CHAOS] 急变道失败: {e}")

    def _chaos_pedestrian_group(self):
        """人群横穿：在主车前方生成一群行人过马路"""
        try:
            bp_lib = self.world.get_blueprint_library()
            walker_bps = bp_lib.filter('walker.pedestrian.*')
            ctrl_bp = bp_lib.find('controller.ai.walker')

            tf = self.vehicle.get_transform()
            yaw = math.radians(tf.rotation.yaw)
            base_dist = random.uniform(20, 35)
            count = random.randint(4, 8)
            spawned = 0

            for i in range(count):
                try:
                    wb = random.choice(walker_bps)
                    if wb.has_attribute('is_invincible'):
                        wb.set_attribute('is_invincible', 'false')

                    offset_fwd = base_dist + random.uniform(-3, 3)
                    lateral = 6 + random.uniform(0, 3)
                    offset_lat = lateral * (-1 if i % 2 == 0 else 1)

                    loc = carla.Location(
                        x=tf.location.x + offset_fwd * math.cos(yaw) - offset_lat * math.sin(yaw),
                        y=tf.location.y + offset_fwd * math.sin(yaw) + offset_lat * math.cos(yaw),
                        z=tf.location.z + 1.0,
                    )

                    w = self.world.try_spawn_actor(wb, carla.Transform(loc))
                    if w is None:
                        continue

                    c = self.world.spawn_actor(ctrl_bp, carla.Transform(), attach_to=w)
                    self.world.tick()
                    c.start()

                    target = carla.Location(
                        x=loc.x + offset_lat * 2 * math.sin(yaw),
                        y=loc.y - offset_lat * 2 * math.cos(yaw),
                        z=loc.z,
                    )
                    c.go_to_location(target)
                    c.set_max_speed(1.5 + random.random())

                    self.npc_walkers.append(w)
                    self.walker_controllers.append(c)
                    spawned += 1
                except Exception:
                    pass

            self._notify(f"! {spawned} 人横穿马路！")
            print(f"[CHAOS] {spawned} 个行人集体横穿")
        except Exception as e:
            print(f"[CHAOS] 人群横穿失败: {e}")

    # ================================================================
    #  车辆状态
    # ================================================================

    def _update_vehicle_state(self):
        if not self.vehicle:
            return

        v = self.vehicle.get_velocity()
        speed = 3.6 * (v.x ** 2 + v.y ** 2 + v.z ** 2) ** 0.5
        control = self.vehicle.get_control()
        transform = self.vehicle.get_transform()

        self.state_manager.update(
            speed_kmh=speed,
            throttle=control.throttle,
            brake=control.brake,
            steer=control.steer,
            gear=control.gear,
            is_reverse=control.reverse,
            location_x=transform.location.x,
            location_y=transform.location.y,
            location_z=transform.location.z,
            rotation_yaw=transform.rotation.yaw,
            rotation_pitch=transform.rotation.pitch,
            rotation_roll=transform.rotation.roll,
            wheel_angle_deg=control.steer * 540.0,
            autopilot_enabled=True,
        )

    def get_latest_frame(self):
        with self._latest_frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    # ================================================================
    #  HUD 通知
    # ================================================================

    def _notify(self, text, duration=3.0):
        self._hud_notification = text
        self._hud_notify_time = time.time() + duration

    # ================================================================
    #  pygame 预览和主循环
    # ================================================================

    def _setup_pygame(self):
        pygame.init()
        self.display = pygame.display.set_mode(
            (settings.WINDOW_WIDTH, settings.WINDOW_HEIGHT)
        )
        pygame.display.set_caption(
            "Smart Cockpit | 1-8:Scene | C:Chaos | SPACE:View | ESC:Quit"
        )
        self.clock = pygame.time.Clock()

    def run(self):
        self._running = True
        print("[CARLA] 主循环启动")

        while self._running:
            self.world.tick()
            self._update_vehicle_state()

            if self.enable_preview:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self._running = False

                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self._running = False

                        elif event.key == pygame.K_SPACE:
                            self.is_cabin_view = not self.is_cabin_view
                            v = "车内" if self.is_cabin_view else "车外"
                            self._notify(f"视角: {v}")

                        elif event.key in SCENE_PRESETS:
                            self._switch_scene(event.key)

                        elif event.key == pygame.K_c:
                            self._trigger_chaos_event()

                img = self.img_cabin if self.is_cabin_view else self.img_third
                if img is not None:
                    surface = pygame.surfarray.make_surface(img.swapaxes(0, 1))
                    self.display.blit(surface, (0, 0))

                self._draw_hud()
                pygame.display.flip()
                self.clock.tick(settings.CARLA_FPS)

    def _draw_hud(self):
        state = self.state_manager.get()
        view_text = "Cabin" if self.is_cabin_view else "Third Person"
        font = pygame.font.SysFont('arial', 22, bold=True)

        lines = [
            f"Scene: {self._current_scene_name}",
            f"View: {view_text}",
            f"Speed: {state.speed_kmh:.0f} km/h",
            f"Steer: {state.steer:.2f}",
            f"NPCs: {len(self.npc_vehicles)} cars, {len(self.npc_walkers)} peds",
            "1-8:Scene C:Chaos SPACE:View ESC:Quit",
        ]

        y = 15
        for line in lines:
            shadow = font.render(line, True, (0, 0, 0))
            text = font.render(line, True, (255, 255, 255))
            self.display.blit(shadow, (17, y + 2))
            self.display.blit(text, (15, y))
            y += 28

        # 中间大字通知
        if self._hud_notification and time.time() < self._hud_notify_time:
            nf = pygame.font.SysFont('arial', 36, bold=True)
            ts = nf.render(self._hud_notification, True, (255, 255, 80))
            tr = ts.get_rect(center=(settings.WINDOW_WIDTH // 2, 80))
            bg = pygame.Surface((tr.width + 40, tr.height + 16))
            bg.set_alpha(160)
            bg.fill((0, 0, 0))
            self.display.blit(bg, (tr.x - 20, tr.y - 8))
            self.display.blit(ts, tr)

    # ================================================================
    #  停止和清理
    # ================================================================

    def stop(self):
        self._running = False

    def cleanup(self):
        print("[CARLA] 正在清理...")

        if self.world:
            s = self.world.get_settings()
            s.synchronous_mode = False
            s.fixed_delta_seconds = None
            self.world.apply_settings(s)

        self._destroy_cameras()
        self._destroy_all_npcs()

        if self.vehicle:
            try:
                self.vehicle.set_autopilot(False, 8000)
                self.vehicle.destroy()
            except Exception:
                pass

        if self.traffic_manager:
            self.traffic_manager.set_synchronous_mode(False)

        pygame.quit()
        print("[CARLA] 清理完成")