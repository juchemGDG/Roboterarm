# Datenübertragung per ESP-NOW

## Ablauf in Kürze

1. **Bridge verbinden:** Bridge-ESP32 per USB anschließen, Port wählen, *Verbinden*. Die **MAC der Bridge** erscheint im Fenster und wird an die Schüler weitergegeben.
2. **Schüler-ESP32 eintragen:** Die MAC-Adresse des ESP32 jedes Gelenks in das passende Feld (Motor 1 bis 4) eintragen. Mit *Speichern* wird die Konfiguration unter dem Roboternamen abgelegt.
3. **Winkel berechnen und senden:** Schritt wählen, *Senden*. Die Bridge schickt jedem Gelenk seine eigene Nachricht.

## Was die Bridge sendet

**Bewegungsbefehl** (je Gelenk eine Nachricht, als JSON-Text):

| Feld | Bedeutung |
|---|---|
| `id` | Gelenk: 1 Standachse, 2 Arm kippen, 3 Handgelenk, 4 Greifer |
| `name` | Name des Gelenks (`base`, `shoulder`, `wrist`, `gripper`) |
| `target_deg` | Zielwinkel in Grad |
| `duration_ms` | Zeit, in der der Winkel erreicht werden soll |
| `seq` | laufende Nummer des Befehls |

**Ping:** Alle 3 Sekunden schickt die Bridge `{"ping": 1}` an jede eingetragene MAC. Nachrichten ohne `id` sollen vom Gelenk-Programm ignoriert werden.

## Was das Gelenk zurückmelden muss

**Nichts.** Die Bridge wertet nur die Empfangsbestätigung auf Funkebene (ACK) aus. Sie kommt automatisch vom ESP-NOW-Treiber des Schüler-ESP32, sobald dieser eingeschaltet ist und ESP-NOW aktiv hat. Das Programm der Schüler muss dafür nichts senden.

| Anzeige | Bedeutung |
|---|---|
| grüner Punkt, *angekommen* | ESP32 hat den Empfang bestätigt |
| roter Punkt, *KEINE Bestätigung* | MAC eingetragen, aber ESP32 nicht erreichbar (aus, falsche MAC, zu weit weg) |
| grauer Punkt | keine MAC eingetragen |

Der Status *Verbunden* erscheint, sobald mindestens ein ESP32 bestätigt.

**Wichtig:** Das ACK sagt nur, dass die Nachricht den ESP32 erreicht hat. Ob der Motor die Bewegung ausgeführt hat, erfährt die Bridge dadurch nicht.

## Optional: Nachrichten der Gelenke an die Bridge

Ein Schüler-ESP32 kann der Bridge zusätzlich beliebigen Text oder JSON schicken, z. B. eine Fertigmeldung oder den aktuellen Winkel. Dazu wird die MAC der Bridge als Empfänger verwendet. Alles, was ankommt, erscheint im Fenster *Übertragene Daten* mit einem `←`. Die Bridge wertet den Inhalt nicht aus.

## Hinweise

- Alle ESP32 müssen sich im selben WLAN-Kanal befinden (Standard beim Start, solange kein WLAN verbunden wird).
- Die Reichweite im Klassenzimmer reicht normalerweise aus. Bei roten Punkten zuerst Stromversorgung und MAC prüfen.
