"""
CARLA 核心桥接模块
基于原始 follow_car.py 重构，增加:
- 车辆状态输出到 VehicleStateManager
- 摄像头画面可供 AI 视觉分析使用
- 与主系统解耦，可独立运行测试

改动指南:
- 换地图/天气: 修改 setup() 中的地图加载部分
- 加传感器(激光雷达、IMU等): 在 _setup_sensors() 中添加
- 调摄像头位置: 修改 _setup_cameras() 中的 Transform
- 改 NPC 数量/行为: 修改 _spawn_npcs()
"""

import carla
import pygame
import numpy as np
import sys
import random
import threading
import time

from config import settings
from core.vehicle_state import VehicleStateManager


class CarlaBridge:
    def __init__(self, state_manager: VehicleStateManager):
        self.state_manager = state_manager

        self.client = None
        self.world = None
        self.vehicle = None
        self.traffic_manager = None
        self.npc_vehicles = []

        # 摄像头
        self.cam_third = None
        self.cam_cabin = None
        self.img_third = None
        self.img_cabin = None

        # 视角切换
        self.is_cabin_view = False

        # pygame（本地预览用，可选）
        self.display = None
        self.clock = None
        self.enable_preview = True

        # 用于 AI 视觉分析的最新帧
        self._latest_frame_lock = threading.Lock()
        self._latest_frame = None  # numpy array, BGR

        self._running = False

    def setup(self):
        """初始化 CARLA 连接、车辆、传感器"""
        print("[CARLA] 正在连接...")
        self.client = carla.Client(settings.CARLA_HOST, settings.CARLA_PORT)
        self.client.set_timeout(30.0)
        self.world = self.client.get_world()
        print(f"[CARLA] 连接成功! 地图: {self.world.get_map().name}")

        # 同步模式
        world_settings = self.world.get_settings()
        world_settings.synchronous_mode = True
        world_settings.fixed_delta_seconds = 1.0 / settings.CARLA_FPS
        self.world.apply_settings(world_settings)

        # Traffic Manager
        self.traffic_manager = self.client.get_trafficmanager(8000)
        self.traffic_manager.set_synchronous_mode(True)
        self.traffic_manager.set_global_distance_to_leading_vehicle(2.5)

        # 生成主车
        self._spawn_ego_vehicle()

        # 生成 NPC
        self._spawn_npcs()

        # 创建摄像头
        self._setup_cameras()

        # pygame 本地预览
        if self.enable_preview:
            self._setup_pygame()

        # 预热
        for _ in range(5):
            self.world.tick()

        print("[CARLA] 初始化完成")

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

    def _spawn_npcs(self):
        bp_lib = self.world.get_blueprint_library()
        vehicle_bps = bp_lib.filter('vehicle.*')

        for sp in self._spawn_points[1:settings.CARLA_NPC_COUNT]:
            try:
                npc = self.world.spawn_actor(random.choice(vehicle_bps), sp)
                npc.set_autopilot(True, 8000)
                self.npc_vehicles.append(npc)
            except Exception:
                pass
        print(f"[CARLA] 已生成 {len(self.npc_vehicles)} 辆 NPC")

    def _setup_cameras(self):
        bp_lib = self.world.get_blueprint_library()
        cam_bp = bp_lib.find('sensor.camera.rgb')
        cam_bp.set_attribute('image_size_x', str(settings.WINDOW_WIDTH))
        cam_bp.set_attribute('image_size_y', str(settings.WINDOW_HEIGHT))

        # 车外第三人称
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

        # 车内驾驶舱
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
        """摄像头回调 - 保存图像数据"""
        array = np.frombuffer(image.raw_data, dtype=np.uint8)
        array = array.reshape(
            (settings.WINDOW_HEIGHT, settings.WINDOW_WIDTH, 4)
        )[:, :, :3][:, :, ::-1]

        if which == 'third':
            self.img_third = array
        else:
            self.img_cabin = array

        # 更新供 AI 视觉分析用的最新帧
        with self._latest_frame_lock:
            self._latest_frame = array.copy()

    def _update_vehicle_state(self):
        """从 CARLA 读取车辆状态，写入 StateManager"""
        if not self.vehicle:
            return

        v = self.vehicle.get_velocity()
        speed = 3.6 * (v.x**2 + v.y**2 + v.z**2)**0.5

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

    def get_latest_frame(self) -> np.ndarray | None:
        """获取最新摄像头画面（供 AI 视觉分析）"""
        with self._latest_frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def _setup_pygame(self):
        pygame.init()
        self.display = pygame.display.set_mode(
            (settings.WINDOW_WIDTH, settings.WINDOW_HEIGHT)
        )
        pygame.display.set_caption("Smart Cockpit | SPACE: View | ESC: Quit")
        self.clock = pygame.time.Clock()

    def run(self):
        """主循环"""
        self._running = True
        print("[CARLA] 主循环启动")

        while self._running:
            self.world.tick()

            # 更新车辆状态
            self._update_vehicle_state()

            # pygame 事件处理
            if self.enable_preview:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self._running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self._running = False
                        elif event.key == pygame.K_SPACE:
                            self.is_cabin_view = not self.is_cabin_view

                # 渲染
                img = self.img_cabin if self.is_cabin_view else self.img_third
                if img is not None:
                    surface = pygame.surfarray.make_surface(img.swapaxes(0, 1))
                    self.display.blit(surface, (0, 0))

                self._draw_hud()
                pygame.display.flip()
                self.clock.tick(settings.CARLA_FPS)

    def _draw_hud(self):
        font = pygame.font.SysFont('arial', 22, bold=True)
        state = self.state_manager.get()
        view_text = "Cabin" if self.is_cabin_view else "Third Person"

        lines = [
            f"View: {view_text}",
            f"Speed: {state.speed_kmh:.0f} km/h",
            f"Steer: {state.steer:.2f}",
            "SPACE: Switch | ESC: Quit"
        ]
        y = 15
        for line in lines:
            shadow = font.render(line, True, (0, 0, 0))
            text = font.render(line, True, (255, 255, 255))
            self.display.blit(shadow, (17, y + 2))
            self.display.blit(text, (15, y))
            y += 30

    def stop(self):
        self._running = False

    def cleanup(self):
        """清理所有 CARLA 资源"""
        print("[CARLA] 正在清理...")

        if self.world:
            s = self.world.get_settings()
            s.synchronous_mode = False
            s.fixed_delta_seconds = None
            self.world.apply_settings(s)

        for cam in [self.cam_third, self.cam_cabin]:
            if cam:
                try:
                    cam.stop()
                    cam.destroy()
                except Exception:
                    pass

        for npc in self.npc_vehicles:
            try:
                npc.set_autopilot(False, 8000)
                npc.destroy()
            except Exception:
                pass

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
