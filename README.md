# Roboterarm-GUI

Dieses Python-Programm berechnet aus mehreren Zielpunkten im Raum (A, B, C, ...) die benoetigten Motorwinkel fuer einen Roboterarm mit drei Schrittmotoren und einem Greifer-Servo (SG90):

- Motor 1: Drehung um die Standachse
- Motor 2: Kippen des ersten Armsegments
- Motor 3: Kippen des zweiten Armsegments am Handgelenk
- Motor 4: Greifer (Servo SG90), oeffnen und schliessen

Zusatzfunktionen:

- Seitenansicht, Draufsicht und 3D-Ansicht des Arms
- serielle Anbindung an einen angeschlossenen ESP32
- ESP-NOW-Bridge (nitbw_espnow) fuer bis zu vier Schueler-ESP32, mit Roboter-Profilen und Statusanzeige
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

## Bridge-Firmware direkt aus der GUI auf den ESP32 schreiben

Im Fenster `ESP32-Kommunikation` gibt es den Button `Bridge-Firmware auf ESP32 schreiben`.

1. ESP32 (mit MicroPython) per USB verbinden.
2. In der GUI den seriellen Port auswaehlen.
3. Button klicken.

Die GUI schreibt `nitbw_espnow.py` (ESP-NOW-Bibliothek) und die Bridge als `main.py` auf den ESP32 (mit `mpremote`) und fuehrt einen Reset aus.

In den fertigen Installern ist `mpremote` bereits eingebaut. Wenn die GUI direkt aus dem Quellcode gestartet wird, kommt es ueber `pip install -r requirements.txt`.

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

Die Motoren werden von den Schuelern selbst angesteuert. Die GUI berechnet nur die Winkel und schickt sie ueber **eine** Bridge (ein per USB angeschlossener ESP32) per ESP-NOW an bis zu vier Schueler-ESP32. Die Bridge ([esp32_bridge/esp32_bridge_micropython.py](esp32_bridge/esp32_bridge_micropython.py)) nutzt dafuer die Bibliothek `nitbw_espnow` aus [NIT_Bibliotheken/ESPNOW](https://github.com/juchemGDG/NIT_Bibliotheken/tree/main/ESPNOW).

### Bedienung im Fenster `ESP32-Kommunikation`

1. Bridge-Firmware aufspielen (siehe oben), Port waehlen und `Verbinden`.
2. Unter `MAC der Bridge` steht die MAC-Adresse der Bridge. Mit `Kopieren` in die Zwischenablage legen und den Schuelern geben.
3. Unter `ESP32 der Schueler` die MAC-Adressen der vier Schueler-ESP32 eintragen (Motor 1 bis 4). Leere Felder werden uebersprungen.
4. Mit Namen und `Speichern` wird die Konfiguration pro Roboter abgelegt und kann spaeter ueber die Auswahlliste `Roboter` wieder geladen werden. Die Datei `roboter_profile.json` liegt im Anwendungsdaten-Ordner des Benutzers.
5. Der Status zeigt `Verbunden – n von m ESP32 erreichbar`, sobald Schueler-ESP32 per ESP-NOW antworten. Der Punkt neben jedem Motor ist gruen (erreichbar), rot (MAC eingetragen, aber keine Antwort) oder grau (keine MAC).
6. Der Button `Anleitung` zeigt die Beschreibung der Uebertragung ([esp32_bridge/uebertragung_anleitung.md](esp32_bridge/uebertragung_anleitung.md)).
7. Unter `Uebertragene Daten` erscheinen alle gesendeten Winkel (`→`) und alle Nachrichten, die Schueler-ESP32 an die Bridge schicken (`←`).

ESP-NOW kennt keine echte Verbindung. "Erreichbar" heisst: Die Bridge sendet alle 3 Sekunden ein `{"ping": 1}` an jede eingetragene MAC, und der ESP32 bestaetigt den Empfang auf Funkebene. Dafuer muss auf dem Schueler-ESP32 lediglich ESP-NOW aktiv sein.

### Datenformat fuer die Schueler-ESP32

Jeder Motor bekommt eine eigene JSON-Nachricht (zu empfangen mit `esp.receive_json()`):

```json
{"id": 1, "name": "base", "target_deg": 45.0, "duration_ms": 1000, "seq": 7}
```

Nachrichten ohne `id` (z. B. `{"ping": 1}`) koennen ignoriert werden. Ein Beispiel liegt in [esp32_bridge/esp32_schueler_beispiel.py](esp32_bridge/esp32_schueler_beispiel.py).

### Serielle Befehle GUI -> Bridge

- `{"command":"info"}`: Bridge antwortet mit `{"status":"ready","mac":"..."}`
- `{"command":"config","peers":["MAC1","MAC2","MAC3","MAC4"]}`: setzt die Ziel-MACs (leerer String = nicht belegt)
- `{"command":"move",...}`: siehe oben

Rueckmeldungen der Bridge:

- `{"status":"ready","mac":"..."}` nach dem Start
- `{"status":"config","count":n}` nach `config`
- `{"status":"tx","motor_id":..,"mac":"..","target_deg":..,"duration_ms":..,"result":"ok|fail"}` pro Motor
- `{"status":"ok","sequence":...,"forwarded":...,"invalid":...,"failed":...}` pro Move-Befehl
- `{"status":"peer","motor_id":..,"online":true|false}` pro Ping
- `{"status":"rx","mac":"..","data":".."}` fuer Nachrichten, die an die Bridge gesendet werden

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