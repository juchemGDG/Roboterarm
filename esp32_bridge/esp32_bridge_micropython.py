import time

import machine
import ujson
from nitbw_espnow import ESPNow


MOTOR_COUNT = 4
PING_INTERVAL_MS = 3000

MOTOR_NAMES = ("base", "shoulder", "wrist", "gripper")


def mac_to_bytes(mac_text):
    # "AA:BB:CC:DD:EE:FF" -> 6 Bytes, None bei ungueltiger Eingabe.
    try:
        parts = mac_text.strip().replace("-", ":").split(":")
        if len(parts) != 6:
            return None
        return bytes(int(p, 16) for p in parts)
    except (ValueError, AttributeError):
        return None


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


def send_acked(esp, mac_text, data):
    # nitbw_espnow.send() meldet nur Fehler beim Senden. Fuer die Anzeige
    # "ESP32 erreichbar" brauchen wir die Empfangsbestaetigung (ACK) des Peers,
    # die der darunterliegende espnow-Treiber als Rueckgabewert liefert.
    mac = mac_to_bytes(mac_text)
    if mac is None:
        return False
    try:
        esp.add_peer(mac_text)
        return bool(esp._esp.send(mac, ujson.dumps(data)))
    except (OSError, ValueError):
        return False


def apply_config(uart, esp, peers, doc):
    macs = doc.get("peers")
    if not isinstance(macs, list):
        write_status(uart, {"status": "error", "message": "Keine MAC-Liste enthalten"})
        return

    for index in range(MOTOR_COUNT):
        text = macs[index] if index < len(macs) else ""
        if isinstance(text, str) and mac_to_bytes(text) is not None:
            peers[index] = text.strip().upper().replace("-", ":")
        else:
            peers[index] = None

    count = len([p for p in peers if p])
    write_status(uart, {"status": "config", "count": count})


def handle_move(uart, esp, peers, doc, sequence):
    motors = doc.get("motors")
    if not isinstance(motors, list) or len(motors) == 0:
        write_status(uart, {"status": "error", "message": "Keine Motor-Daten enthalten"})
        return

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

        if motor_id < 1 or motor_id > MOTOR_COUNT or peers[motor_id - 1] is None:
            invalid += 1
            continue

        mac_text = peers[motor_id - 1]
        # Dieses Dictionary erhalten die Schueler mit esp.receive_json().
        message = {
            "id": motor_id,
            "name": MOTOR_NAMES[motor_id - 1],
            "target_deg": target_deg,
            "duration_ms": duration_ms,
            "seq": sequence,
        }
        acked = send_acked(esp, mac_text, message)
        if acked:
            forwarded += 1
        else:
            failed += 1

        write_status(
            uart,
            {
                "status": "tx",
                "motor_id": motor_id,
                "mac": mac_text,
                "target_deg": target_deg,
                "duration_ms": duration_ms,
                "result": "ok" if acked else "fail",
            },
        )

    write_status(
        uart,
        {"status": "ok", "sequence": sequence, "forwarded": forwarded, "invalid": invalid, "failed": failed},
    )


def ping_peers(uart, esp, peers):
    for index in range(MOTOR_COUNT):
        if peers[index] is None:
            continue
        online = send_acked(esp, peers[index], {"ping": 1})
        write_status(uart, {"status": "peer", "motor_id": index + 1, "online": online})


def forward_incoming(uart, esp):
    # Nachrichten, die Schueler-ESP32 an die Bridge schicken, werden an die GUI weitergereicht.
    try:
        msg, sender = esp.receive(timeout_ms=0, decode=True)
    except (OSError, ValueError):
        return
    if msg is None:
        return
    if isinstance(msg, (bytes, bytearray)):
        msg = "".join("%02x" % b for b in msg)
    write_status(uart, {"status": "rx", "mac": sender, "data": msg[:200]})


def main():
    uart = setup_uart()
    esp = ESPNow()
    peers = [None] * MOTOR_COUNT

    sequence = 1
    next_ping = time.ticks_add(time.ticks_ms(), PING_INTERVAL_MS)
    write_status(uart, {"status": "ready", "message": "ESP32 Bridge bereit", "mac": esp.get_mac()})

    while True:
        forward_incoming(uart, esp)

        if time.ticks_diff(time.ticks_ms(), next_ping) >= 0:
            ping_peers(uart, esp, peers)
            next_ping = time.ticks_add(time.ticks_ms(), PING_INTERVAL_MS)

        doc = read_json_line(uart)
        if doc is None:
            time.sleep_ms(5)
            continue

        if "_parse_error" in doc:
            write_status(uart, {"status": "error", "message": "JSON ungueltig"})
            continue

        command = doc.get("command")
        if command == "info":
            write_status(uart, {"status": "ready", "message": "ESP32 Bridge bereit", "mac": esp.get_mac()})
        elif command == "config":
            apply_config(uart, esp, peers, doc)
        elif command == "move":
            handle_move(uart, esp, peers, doc, sequence)
            sequence += 1
        else:
            write_status(uart, {"status": "error", "message": "Unbekannter Befehl"})


if __name__ == "__main__":
    main()
