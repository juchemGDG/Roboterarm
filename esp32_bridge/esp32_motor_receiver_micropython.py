import struct
import time

import espnow
import machine
import network
import ujson


# Pro Motor-ESP32 anpassen.
MOTOR_ID = 1  # 1..4
ACTUATOR_MODE = "servo"  # "servo" oder "stepper"

# Optional: Bridge-MAC eintragen, um nur Pakete dieser Bridge zu akzeptieren.
# Beispiel: BRIDGE_MAC = b"\x24\x6f\x28\xaa\xbb\xcc"
BRIDGE_MAC = None

# Servo-Konfiguration
SERVO_PIN = 18
SERVO_FREQ = 50
SERVO_MIN_DEG = 0.0
SERVO_MAX_DEG = 180.0
SERVO_MIN_US = 500
SERVO_MAX_US = 2500

# Stepper-Konfiguration (A4988/DRV8825-artig)
STEPPER_STEP_PIN = 18
STEPPER_DIR_PIN = 19
STEPPER_EN_PIN = 5
STEPPER_ENABLE_LEVEL = 0
STEPPER_STEPS_PER_REV = 200
STEPPER_MICROSTEPS = 16
STEPPER_GEAR_RATIO = 1.0
STEPPER_DIR_INVERT = False
STEPPER_MIN_PULSE_US = 300


def clamp(value, lo, hi):
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def write_status(payload):
    print(ujson.dumps(payload))


class ServoActuator:
    def __init__(self):
        self.pwm = machine.PWM(machine.Pin(SERVO_PIN), freq=SERVO_FREQ)
        self.current_deg = 90.0
        self.set_angle(self.current_deg)

    def _duty_u16_for_us(self, us):
        period_us = int(1_000_000 / SERVO_FREQ)
        return int((us / period_us) * 65535)

    def set_angle(self, angle_deg):
        angle = clamp(float(angle_deg), SERVO_MIN_DEG, SERVO_MAX_DEG)
        span_deg = SERVO_MAX_DEG - SERVO_MIN_DEG
        if span_deg <= 0:
            span_deg = 1.0
        rel = (angle - SERVO_MIN_DEG) / span_deg
        pulse_us = int(SERVO_MIN_US + rel * (SERVO_MAX_US - SERVO_MIN_US))
        duty = self._duty_u16_for_us(pulse_us)
        self.pwm.duty_u16(clamp(duty, 0, 65535))
        self.current_deg = angle

    def move_to(self, target_deg, duration_ms):
        start = self.current_deg
        target = clamp(float(target_deg), SERVO_MIN_DEG, SERVO_MAX_DEG)
        duration = max(int(duration_ms), 0)
        if duration <= 0:
            self.set_angle(target)
            return

        step_ms = 20
        steps = max(1, duration // step_ms)
        for i in range(1, steps + 1):
            factor = i / steps
            angle = start + (target - start) * factor
            self.set_angle(angle)
            time.sleep_ms(step_ms)


class StepperActuator:
    def __init__(self):
        self.step_pin = machine.Pin(STEPPER_STEP_PIN, machine.Pin.OUT)
        self.dir_pin = machine.Pin(STEPPER_DIR_PIN, machine.Pin.OUT)
        self.en_pin = machine.Pin(STEPPER_EN_PIN, machine.Pin.OUT)
        self.en_pin.value(1 - STEPPER_ENABLE_LEVEL)
        self.current_steps = 0
        self.steps_per_degree = (
            STEPPER_STEPS_PER_REV * STEPPER_MICROSTEPS * STEPPER_GEAR_RATIO
        ) / 360.0

    def _set_enabled(self, enabled):
        self.en_pin.value(STEPPER_ENABLE_LEVEL if enabled else (1 - STEPPER_ENABLE_LEVEL))

    def _pulse(self, pulse_us):
        self.step_pin.value(1)
        time.sleep_us(pulse_us)
        self.step_pin.value(0)
        time.sleep_us(pulse_us)

    def move_to(self, target_deg, duration_ms):
        target_steps = int(round(float(target_deg) * self.steps_per_degree))
        delta = target_steps - self.current_steps
        if delta == 0:
            return

        direction = 1 if delta > 0 else 0
        if STEPPER_DIR_INVERT:
            direction = 1 - direction
        self.dir_pin.value(direction)

        total_steps = abs(delta)
        duration = max(int(duration_ms), 0)
        if duration <= 0:
            pulse_us = STEPPER_MIN_PULSE_US
        else:
            pulse_us = max(STEPPER_MIN_PULSE_US, int((duration * 1000) / (2 * total_steps)))

        self._set_enabled(True)
        for _ in range(total_steps):
            self._pulse(pulse_us)
        self._set_enabled(False)
        self.current_steps = target_steps


def setup_radio():
    sta = network.WLAN(network.STA_IF)
    sta.active(True)

    e = espnow.ESPNow()
    e.active(True)

    if BRIDGE_MAC:
        try:
            e.add_peer(BRIDGE_MAC)
        except OSError:
            pass

    return e, sta


def parse_packet(raw):
    if raw is None or len(raw) != 16:
        return None

    # Entspricht der Bridge-Payload: <B3xfH2xI
    motor_id, target_deg, duration_ms, sequence = struct.unpack("<B3xfH2xI", raw)
    return {
        "motor_id": motor_id,
        "target_deg": float(target_deg),
        "duration_ms": int(duration_ms),
        "sequence": int(sequence),
    }


def mac_text(mac):
    if mac is None:
        return "none"
    return ":".join("%02X" % b for b in mac)


def main():
    e, sta = setup_radio()
    actuator = ServoActuator() if ACTUATOR_MODE == "servo" else StepperActuator()
    last_sequence = -1

    write_status(
        {
            "status": "ready",
            "mode": ACTUATOR_MODE,
            "motor_id": MOTOR_ID,
            "mac": mac_text(sta.config("mac")),
        }
    )

    while True:
        host, msg = e.recv(100)
        if not msg:
            continue

        if BRIDGE_MAC is not None and host != BRIDGE_MAC:
            write_status({"status": "drop", "reason": "unknown_sender", "from": mac_text(host)})
            continue

        data = parse_packet(msg)
        if data is None:
            write_status({"status": "drop", "reason": "invalid_packet", "len": len(msg)})
            continue

        if data["motor_id"] != MOTOR_ID:
            write_status(
                {
                    "status": "drop",
                    "reason": "wrong_motor",
                    "expected": MOTOR_ID,
                    "got": data["motor_id"],
                    "sequence": data["sequence"],
                }
            )
            continue

        if data["sequence"] == last_sequence:
            write_status({"status": "drop", "reason": "duplicate", "sequence": data["sequence"]})
            continue

        try:
            actuator.move_to(data["target_deg"], data["duration_ms"])
        except Exception as exc:
            write_status(
                {
                    "status": "error",
                    "sequence": data["sequence"],
                    "message": "actuator_failed",
                    "detail": str(exc),
                }
            )
            continue

        last_sequence = data["sequence"]
        write_status(
            {
                "status": "ok",
                "sequence": data["sequence"],
                "motor_id": MOTOR_ID,
                "target_deg": round(data["target_deg"], 3),
                "duration_ms": data["duration_ms"],
                "from": mac_text(host),
            }
        )


if __name__ == "__main__":
    main()
