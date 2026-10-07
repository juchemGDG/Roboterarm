# Beispiel fuer den ESP32 der Schueler (MicroPython).
# Die Bibliothek nitbw_espnow.py muss ebenfalls auf dem ESP32 liegen.
#
# BRIDGE_MAC: MAC-Adresse der Bridge, wie sie in der Roboterarm-GUI angezeigt wird.
from nitbw_espnow import ESPNow

BRIDGE_MAC = "AA:BB:CC:DD:EE:FF"
MEINE_MOTOR_ID = 1  # 1 = Standachse, 2 = Arm kippen, 3 = Handgelenk, 4 = Greifer

esp = ESPNow()
esp.add_peer(BRIDGE_MAC)
print("Meine MAC:", esp.get_mac())

while True:
    try:
        daten, sender = esp.receive_json(timeout_ms=200)
    except ValueError:
        continue  # keine JSON-Nachricht

    if daten is None or sender != BRIDGE_MAC:
        continue
    if daten.get("id") != MEINE_MOTOR_ID:
        continue  # z. B. Ping-Nachrichten {"ping": 1} der Bridge

    winkel = daten["target_deg"]
    dauer_ms = daten["duration_ms"]
    print("Winkel:", winkel, "Grad in", dauer_ms, "ms")
    # Hier den eigenen Motor ansteuern ...
