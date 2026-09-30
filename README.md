# Roboterarm-GUI

Dieses Python-Programm berechnet aus mehreren Zielpunkten im Raum (A, B, C, ...) die benoetigten Motorwinkel fuer einen Roboterarm mit drei Schrittmotoren und einem Greifer-Servo (SG90):

- Motor 1: Drehung um die Standachse
- Motor 2: Kippen des ersten Armsegments
- Motor 3: Kippen des zweiten Armsegments am Handgelenk
- Motor 4: Greifer (Servo SG90), oeffnen und schliessen

Zusatzfunktionen:

- Seitenansicht, Draufsicht und 3D-Ansicht des Arms
- serielle Anbindung an einen angeschlossenen ESP32
- vorbereitete ESP-NOW-Bridge fuer vier Motor-ESP32
- Hilfe-Menue mit direkter Anzeige dieser README in der GUI

## Annahmen des Modells

- Die Basis des Roboterarms steht im Ursprung `(0, 0, 0)`.
- Das Schultergelenk sitzt in der Hoehe `z0` ueber dem Boden.
- Der Arm wird als 2-gliedrige Kette mit den Laengen `Armlaenge 1` und `Armlaenge 2` modelliert.
- Die Koordinaten `x` und `y` bestimmen die Drehung um die Standachse.
- Die Koordinate `z` bestimmt gemeinsam mit dem radialen Abstand die Kippwinkel.
- Der Greifer-Servo bekommt die Winkel fuer "offen" und "geschlossen" aus dem Bereich `Greifer (Servo SG90)`. Am Anfang ist der Greifer offen.

## Starten

Python 3 installieren, die Abhaengigkeiten installieren und dann im Projektordner ausfuehren:

```bash
python3 -m pip install -r requirements.txt
python3 roboterarm_gui.py
```

## Bedienung

1. Geometrie des Arms in Zentimetern eintragen.
2. Punkte A, B und beliebig viele weitere (`Punkt hinzufuegen`, maximal 12) mit `x`, `y`, `z` angeben. Der Arm faehrt sie nacheinander an.
3. Pro Punkt die Greiferaktion waehlen: keine Aktion, schliessen, oeffnen, oeffnen und schliessen oder schliessen und oeffnen (bei A nur keine Aktion oder schliessen, da der Greifer offen startet).
4. Auf `Winkel berechnen` klicken.
5. Optional die Bewegung mit `Bewegung animieren` abspielen.
6. Optional einen per USB angeschlossenen ESP32 als Bridge verbinden und einzelne Schritte senden.

Die GUI zeigt:

- die berechneten Winkel fuer alle vier Motoren
- die Winkeldifferenzen zwischen A und B
- eine Seitenansicht des Arms
- eine Draufsicht mit der Basisdrehung
- eine zusaetzliche 3D-Ansicht
- Beispielpakete fuer die serielle ESP32-Bridge

## Hilfe in der GUI

In der Anwendung gibt es im Menue `Hilfe` den Eintrag `README anzeigen`.
Damit wird diese Datei direkt in einem Hilfefenster geoeffnet.

## Firmware direkt aus der GUI auf ESP32 schreiben

Im Bereich `ESP32-Bridge` gibt es die Funktion `Firmware als main.py auf ESP32`.

Vorgehen:

1. ESP32 per USB verbinden.
2. In der GUI den seriellen Port auswaehlen.
3. Firmware-Typ waehlen:
	- `Bridge (MicroPython)` fuer den zentralen Bridge-ESP32
	- `Motor-Empfaenger (MicroPython)` fuer Motor-ESP32
4. Beim Motor-Empfaenger die gewuenschte Motor-ID (1..4) waehlen.
5. Button `Firmware als main.py auf ESP32` klicken.

Die GUI schreibt dann die ausgewaehlte Firmware als `main.py` auf den ESP32 (mit `mpremote`) und fuehrt einen Reset aus.

Voraussetzung auf dem Rechner:

```bash
python3 -m pip install mpremote
```

## Serielles Protokoll zur ESP32-Bridge

Die Python-Anwendung sendet pro Zielposition eine JSON-Zeile ueber USB-Serial an einen angeschlossenen ESP32. Beispiel:

```json
{
	"command": "move",
	"profile": "Position B",
	"duration_ms": 3000,
	"target_point_cm": {
		"x": 12.0,
		"y": -14.0,
		"z": 20.0,
		"gripper": 24.0
	},
	"motors": [
		{"id": 1, "name": "base", "label": "Standachse", "target_deg": -49.4, "duration_ms": 3000},
		{"id": 2, "name": "shoulder", "label": "Arm kippen", "target_deg": -29.89, "duration_ms": 3000},
		{"id": 3, "name": "wrist", "label": "Handgelenk", "target_deg": 116.39, "duration_ms": 3000},
		{"id": 4, "name": "gripper", "label": "Klammer", "target_deg": 24.0, "duration_ms": 3000}
	]
}
```

## ESP32-Bridge mit ESP-NOW

Im Ordner [esp32_bridge/esp32_bridge.ino](esp32_bridge/esp32_bridge.ino) liegt ein Beispiel fuer einen ESP32, der:

- die JSON-Zeile seriell vom PC entgegennimmt
- fuer jeden Motor ein kompaktes Paket erstellt
- die vier Pakete per ESP-NOW an die Motor-ESP32 sendet

### MicroPython-Variante der Bridge

Zusaetzlich gibt es eine Bridge-Firmware in MicroPython:
[esp32_bridge/esp32_bridge_micropython.py](esp32_bridge/esp32_bridge_micropython.py)

Kurz nutzen:

1. Auf dem Bridge-ESP32 MicroPython installieren.
2. Die Datei [esp32_bridge/esp32_bridge_micropython.py](esp32_bridge/esp32_bridge_micropython.py) als `main.py` auf den ESP32 kopieren.
3. In der Datei die 4 MAC-Adressen in `PEER_MACS` auf eure Motor-ESP32 anpassen.
4. ESP32 neu starten und in der GUI den seriellen Port mit 115200 Baud verbinden.

Die MicroPython-Bridge nutzt dasselbe serielle JSON-Protokoll wie die Desktop-GUI.
Die Weiterleitung erfolgt ebenfalls nach Motor-ID (`id=1..4`) an den jeweils passenden Peer.

### MicroPython-Empfaenger fuer Motor-ESP32

Fuer die 4 Motor-Controller gibt es eine zusaetzliche MicroPython-Datei:
[esp32_bridge/esp32_motor_receiver_micropython.py](esp32_bridge/esp32_motor_receiver_micropython.py)

Diese Firmware laeuft auf jedem Motor-ESP32 und:

- empfaengt ESP-NOW-Pakete von der Bridge
- entpackt das Motorpaket (16 Byte, gleiches Format wie in der Bridge)
- akzeptiert nur den eigenen `MOTOR_ID`-Wert
- steuert wahlweise Servo oder Stepper

Kurz nutzen (pro Motor-ESP32):

1. Datei [esp32_bridge/esp32_motor_receiver_micropython.py](esp32_bridge/esp32_motor_receiver_micropython.py) als `main.py` auf den Motor-ESP32 kopieren.
2. `MOTOR_ID` auf 1, 2, 3 oder 4 setzen (je Board unterschiedlich).
3. `ACTUATOR_MODE` auf `servo` oder `stepper` setzen.
4. Passende Pins und Grenzen fuer den Motor im Kopf der Datei anpassen.
5. Optional `BRIDGE_MAC` setzen, damit nur die bekannte Bridge akzeptiert wird.
6. Neustarten und serielle Konsole pruefen (`{"status":"ready",...}`).

Hinweis: Das Paketformat ist identisch zur Bridge-Firmware:

```cpp
struct MotorCommandPacket {
	uint8_t motorId;
	float targetDeg;
	uint16_t durationMs;
	uint32_t sequence;
};
```

### Firmware der Bridge nutzen (kurz)

1. Bridge-ESP32 per USB verbinden und [esp32_bridge/esp32_bridge.ino](esp32_bridge/esp32_bridge.ino) flashen.
2. In der Firmware die 4 MAC-Adressen in `PEER_MACS` auf die 4 Motor-ESP32 anpassen.
3. Sicherstellen, dass alle ESP32 im gleichen WLAN-Kanal arbeiten (ESP-NOW).
4. In der GUI den seriellen Port auswaehlen, verbinden und den gewuenschten Schritt (z. B. `B` oder `B · Oeffnen`) auswaehlen und `Senden` klicken.
5. Die Bridge verteilt jedes Motorobjekt nach `id` an den passenden Peer:
	- `id=1` -> Peer 1 (Motor 1)
	- `id=2` -> Peer 2 (Motor 2)
	- `id=3` -> Peer 3 (Motor 3)
	- `id=4` -> Peer 4 (Motor 4)

Rueckmeldungen der Bridge auf Serial:

- `{"status":"ready",...}` nach dem Start
- `{"status":"ok","sequence":...,"forwarded":...,"invalid":...,"failed":...}` pro empfangenem Move-Befehl
- `{"status":"tx","mac":"...","result":"ok|fail"}` pro ESP-NOW-Übertragung

Vor dem Flashen anpassen:

1. In [esp32_bridge/esp32_bridge.ino](esp32_bridge/esp32_bridge.ino) die vier MAC-Adressen der Motor-ESP32 eintragen.
2. In der Arduino-IDE fuer den Bridge-ESP32 die Bibliothek `ArduinoJson` installieren.
3. Sicherstellen, dass die Motor-ESP32 dasselbe Datenformat empfangen:

```cpp
struct MotorCommandPacket {
	uint8_t motorId;
	float targetDeg;
	uint16_t durationMs;
	uint32_t sequence;
};
```

## Hinweise

- Nicht jeder Punkt im Raum ist erreichbar. Die Anwendung meldet das direkt.
- Falls der Arm geometrisch gespiegelt fahren soll, kann die alternative IK-Loesung aktiviert werden.
- Die Desktop-Anwendung sendet nur an den per USB angeschlossenen Bridge-ESP32. Die eigentliche Funkverteilung uebernimmt dann ESP-NOW auf dem ESP32.

## Standalone-Installer bauen (macOS und Windows)

Im Projekt sind Build-Dateien enthalten, um eine standalone Version der GUI zu erzeugen:

- PyInstaller-Spezifikation: [roboterarm_gui.spec](roboterarm_gui.spec)
- Build-Skript macOS: [scripts/build_mac.sh](scripts/build_mac.sh)
- Build-Skript Windows: [scripts/build_windows.bat](scripts/build_windows.bat)
- Inno-Setup-Skript Windows: [installer/windows/roboterarm_gui.iss](installer/windows/roboterarm_gui.iss)
- Build-Abhaengigkeiten: [requirements-build.txt](requirements-build.txt)

### macOS

```bash
chmod +x scripts/build_mac.sh
./scripts/build_mac.sh
```

Ergebnis:

- App-Bundle in `dist/RoboterarmSteuerung.app`
- DMG-Installationsdatei in `dist/RoboterarmSteuerung-macOS.dmg`

### Windows

```bat
scripts\build_windows.bat
```

Ergebnis:

- Portable Build in `dist\RoboterarmSteuerung\`
- Setup-EXE in `dist\RoboterarmSteuerung-Setup.exe` (wenn Inno Setup / `iscc` installiert ist)

## Automatischer Build mit GitHub Actions

Es gibt eine CI-Pipeline in [.github/workflows/build-installers.yml](.github/workflows/build-installers.yml).

Die Pipeline baut automatisch:

- macOS: `RoboterarmSteuerung-macOS.dmg`
- Windows: `RoboterarmSteuerung-Setup.exe`

Ausfuehrung:

1. Manuell in GitHub ueber `Actions` -> `Build Installers` -> `Run workflow`.
2. Automatisch bei Git-Tags, die mit `v` beginnen (z.B. `v1.0.0`).

Bei einem Tag-Build erstellt die Pipeline zusaetzlich ein GitHub Release und haengt beide Installer-Dateien an.