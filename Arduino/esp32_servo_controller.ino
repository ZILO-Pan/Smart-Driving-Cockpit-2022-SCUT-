/*
 * ESP32 舵机控制端 - Arduino 参考代码
 * 接收 Python 串口发来的转向角数据，驱动舵机
 *
 * 硬件接线:
 * - ESP32 GPIO 13 → 舵机信号线（橙色）
 * - ESP32 GND → 舵机 GND（棕色）
 * - 外部 5V 电源 → 舵机 VCC（红色）⚠️ 不要用 ESP32 的 5V，电流不够
 *
 * 协议格式: [0xAA][0x55][steer_high][steer_low][speed][checksum]
 */

#include <ESP32Servo.h>

#define SERVO_PIN 13
#define SERIAL_BAUD 115200

Servo steerServo;

// 舵机角度范围（根据实际舵机调整）
const float SERVO_MIN = 0.0;    // 最左
const float SERVO_MAX = 180.0;  // 最右
const float SERVO_CENTER = 90.0;

void setup() {
    Serial.begin(SERIAL_BAUD);
    steerServo.attach(SERVO_PIN, 500, 2500); // min/max 微秒
    steerServo.write(SERVO_CENTER);
    Serial.println("ESP32 Servo Controller Ready");
}

void loop() {
    if (Serial.available() >= 6) {
        uint8_t header1 = Serial.read();
        uint8_t header2 = Serial.read();

        if (header1 == 0xAA && header2 == 0x55) {
            uint8_t steer_high = Serial.read();
            uint8_t steer_low = Serial.read();
            uint8_t speed = Serial.read();
            uint8_t checksum = Serial.read();

            // 校验
            uint8_t calc_checksum = (steer_high + steer_low + speed) & 0xFF;
            if (checksum == calc_checksum) {
                uint16_t steer_raw = (steer_high << 8) | steer_low;

                // 0~65535 → -540~540 度
                float carla_angle = (steer_raw / 65535.0) * 1080.0 - 540.0;

                // -540~540 → 0~180 (舵机范围)
                float servo_angle = map_float(carla_angle, -540.0, 540.0, SERVO_MIN, SERVO_MAX);
                servo_angle = constrain(servo_angle, SERVO_MIN, SERVO_MAX);

                steerServo.write((int)servo_angle);
            }
        }
    }
}

float map_float(float x, float in_min, float in_max, float out_min, float out_max) {
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}
