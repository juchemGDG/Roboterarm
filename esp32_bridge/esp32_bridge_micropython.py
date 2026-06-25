import struct
import time

import espnow
import machine
import network
import ujson


# 4 Ziel-ESP32 (je ein Motor-Controller). MAC-Adressen anpassen.
PEER_MACS = (
    b"\x24\x6f\x28\x00\x00\x01",
    b"\x24\x6f\x28\x00\x00\x02",
    b"\x24\x6f\x28\x00\x00\x03",
    b"\x24\x6f\x28\x00\x00\x04",
)

MOTOR_COUNT = 4


def mac_to_text(mac):
    return ":".join("%02X" % b for b in mac)


def make_packet(motor_id, target_deg, duration_ms, sequence):
    # Layout wie C-Struct auf ESP32 (16 Byte, inkl. Padding):
    # uint8_t motorId; float targetDeg; uint16_t durationMs; uint32_t sequence;
    # C-typisches Alignment wird hier mit Pad-Bytes nachgebildet.
    return struct.pack("<B3xfH2xI", motor_id, float(target_deg), int(duration_ms), int(sequence))


def setup_espnow():
    sta = network.WLAN(network.STA_IF)
    sta.active(True)

    e = espnow.ESPNow()
    e.active(True)

    for mac in PEER_MACS:
        try:
            e.add_peer(mac)
        except OSError:
            # Peer existiert evtl. schon nach Soft-Reset.
            pass

    return e


def setup_uart():
    # UART0 ist auf vielen ESP32-Boards die USB-Serial-Verbindung zum PC.
    return machine.UART(0, baudrate=115200, timeout=20, rxbuf=4096)


def read_json_line(uart):
    if not uart.any():
        return None

    raw = uart.readline()
    if not raw:
        return None

    try:
        line = raw.decode("utf-8").strip()
    except UnicodeError:
        return {"_parse_error": "utf8"}

    if not line:
        return None

    try:
        return ujson.loads(line)
    except ValueError:
        return {"_parse_error": "json"}


def write_status(uart, payload):
    uart.write(ujson.dumps(payload) + "\n")


def main():
    uart = setup_uart()
    now = setup_espnow()

    sequence = 1
    write_status(uart, {"status": "ready", "message": "ESP32 MicroPython Bridge bereit"})

    while True:
        doc = read_json_line(uart)
        if doc is None:
            time.sleep_ms(5)
            continue

        if "_parse_error" in doc:
            write_status(uart, {"status": "error", "message": "JSON ungueltig"})
            continue

        if doc.get("command") != "move":
            write_status(uart, {"status": "error", "message": "Unbekannter Befehl"})
            continue

        motors = doc.get("motors")
        if not isinstance(motors, list) or len(motors) == 0:
            write_status(uart, {"status": "error", "message": "Keine Motor-Daten enthalten"})
            continue

        forwarded = 0
        invalid = 0
        failed = 0

        for motor in motors:
            if not isinstance(motor, dict):
                invalid += 1
                continue

            motor_id = int(motor.get("id", 0))
            target_deg = float(motor.get("target_deg", 0.0))
            duration_ms = int(motor.get("duration_ms", 0))

            if motor_id < 1 or motor_id > MOTOR_COUNT:
                invalid += 1
                continue

            mac = PEER_MACS[motor_id - 1]
            packet = make_packet(motor_id, target_deg, duration_ms, sequence)

            try:
                now.send(mac, packet, True)
                forwarded += 1
                write_status(
                    uart,
                    {
                        "status": "tx",
                        "mac": mac_to_text(mac),
                        "result": "ok",
                        "motor_id": motor_id,
                    },
                )
            except OSError:
                failed += 1
                write_status(
                    uart,
                    {
                        "status": "tx",
                        "mac": mac_to_text(mac),
                        "result": "fail",
                        "motor_id": motor_id,
                    },
                )

        write_status(
            uart,
            {
                "status": "ok",
                "sequence": sequence,
                "forwarded": forwarded,
                "invalid": invalid,
                "failed": failed,
            },
        )
        sequence += 1


if __name__ == "__main__":
    main()
