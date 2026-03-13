"""
Tesla 自动驾驶跟随视角脚本
- 自动驾驶的 Tesla Model 3 + 30辆NPC车辆
- 按空格键切换：车外第三人称视角 / 车内驾驶舱视角
- 按 ESC 退出
"""

import carla
import pygame
import numpy as np
import sys
import random

# ============ 配置 ============
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 30


class TeslaFollower:
    def __init__(self):
        self.client = None
        self.world = None
        self.vehicle = None
        self.traffic_manager = None
        self.npc_vehicles = []

        # 两个摄像头同时存在，切换时不销毁
        self.cam_third = None
        self.cam_cabin = None
        self.img_third = None
        self.img_cabin = None

        self.is_cabin_view = False
        self.display = None
        self.clock = None

    def setup(self):
        # ---- 连接 ----
        print("正在连接 CARLA...")
        self.client = carla.Client('localhost', 2000)
        self.client.set_timeout(30.0)
        self.world = self.client.get_world()
        print(f"连接成功! 地图: {self.world.get_map().name}")

        # ---- 同步模式 ----
        settings = self.world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = 1.0 / FPS
        self.world.apply_settings(settings)

        # ---- Traffic Manager ----
        self.traffic_manager = self.client.get_trafficmanager(8000)
        self.traffic_manager.set_synchronous_mode(True)
        self.traffic_manager.set_global_distance_to_leading_vehicle(2.5)

        # ---- 生成 Tesla ----
        bp_lib = self.world.get_blueprint_library()
        tesla_bp = bp_lib.find('vehicle.tesla.model3')
        spawn_points = self.world.get_map().get_spawn_points()
        if not spawn_points:
            print("错误：没有可用的出生点!")
            sys.exit(1)

        random.shuffle(spawn_points)
        self.vehicle = self.world.spawn_actor(tesla_bp, spawn_points[0])
        self.vehicle.set_autopilot(True, 8000)
        print("Tesla Model 3 已生成，自动驾驶已开启")

        # ---- 生成 NPC 车辆 ----
        vehicle_bps = bp_lib.filter('vehicle.*')
        for sp in spawn_points[1:30]:
            try:
                npc = self.world.spawn_actor(random.choice(vehicle_bps), sp)
                npc.set_autopilot(True, 8000)
                self.npc_vehicles.append(npc)
            except:
                pass
        print(f"已生成 {len(self.npc_vehicles)} 辆 NPC 车辆")

        # ---- 创建两个摄像头（同时运行） ----
        cam_bp = bp_lib.find('sensor.camera.rgb')
        cam_bp.set_attribute('image_size_x', str(WINDOW_WIDTH))
        cam_bp.set_attribute('image_size_y', str(WINDOW_HEIGHT))

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
        self.cam_third.listen(lambda img: self._save_image(img, 'third'))

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
        self.cam_cabin.listen(lambda img: self._save_image(img, 'cabin'))
        print("两个摄像头已创建")

        # ---- pygame 窗口 ----
        pygame.init()
        self.display = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Tesla 自动驾驶 | 空格切换视角 | ESC退出")
        self.clock = pygame.time.Clock()

        # 先 tick 几帧让摄像头出图
        for _ in range(5):
            self.world.tick()

        print("\n========================================")
        print("  空格键: 切换车外/车内视角")
        print("  ESC:   退出")
        print("========================================\n")

    def _save_image(self, image, which):
        array = np.frombuffer(image.raw_data, dtype=np.uint8)
        array = array.reshape((WINDOW_HEIGHT, WINDOW_WIDTH, 4))[:, :, :3][:, :, ::-1]
        if which == 'third':
            self.img_third = array
        else:
            self.img_cabin = array

    def run(self):
        running = True
        while running:
            self.world.tick()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        self.is_cabin_view = not self.is_cabin_view
                        name = "车内驾驶舱" if self.is_cabin_view else "车外第三人称"
                        print(f"切换到: {name}")

            # 选择当前视角的图像
            img = self.img_cabin if self.is_cabin_view else self.img_third
            if img is not None:
                surface = pygame.surfarray.make_surface(img.swapaxes(0, 1))
                self.display.blit(surface, (0, 0))

            self._draw_hud()
            pygame.display.flip()
            self.clock.tick(FPS)

    def _draw_hud(self):
        font = pygame.font.SysFont('arial', 22, bold=True)
        view_text = "Cabin View" if self.is_cabin_view else "Third Person View"
        v = self.vehicle.get_velocity()
        speed = 3.6 * (v.x**2 + v.y**2 + v.z**2)**0.5

        lines = [
            f"View: {view_text}",
            f"Speed: {speed:.0f} km/h",
            "SPACE: Switch | ESC: Quit"
        ]
        y = 15
        for line in lines:
            shadow = font.render(line, True, (0, 0, 0))
            text = font.render(line, True, (255, 255, 255))
            self.display.blit(shadow, (17, y + 2))
            self.display.blit(text, (15, y))
            y += 30

    def cleanup(self):
        print("\n正在清理...")

        if self.world:
            settings = self.world.get_settings()
            settings.synchronous_mode = False
            settings.fixed_delta_seconds = None
            self.world.apply_settings(settings)

        for cam in [self.cam_third, self.cam_cabin]:
            if cam:
                try:
                    cam.stop()
                    cam.destroy()
                except:
                    pass

        for npc in self.npc_vehicles:
            try:
                npc.set_autopilot(False, 8000)
                npc.destroy()
            except:
                pass

        if self.vehicle:
            try:
                self.vehicle.set_autopilot(False, 8000)
                self.vehicle.destroy()
            except:
                pass

        if self.traffic_manager:
            self.traffic_manager.set_synchronous_mode(False)

        pygame.quit()
        print("清理完成!")


def main():
    app = TeslaFollower()
    try:
        app.setup()
        app.run()
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        app.cleanup()


if __name__ == '__main__':
    main()