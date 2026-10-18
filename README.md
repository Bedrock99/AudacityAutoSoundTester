# AudacityAutoSoundTester

Ein interaktives Python-CLI-Tool zur manuellen Qualitätskontrolle und Lautstärkeanpassung einer Audiosammlung mit nahtloser Audacity-Integration.

## Ziel

`AudacityAutoSoundTester` arbeitet alle Audiodateien in einem Stammverzeichnis (rekursiv über alle Unterordner) einzeln und nacheinander ab.
Für jede Datei startet im Terminal sofort ein Autoplay, sodass der Benutzer unmittelbar reinhören kann. Audacity muss nur bei Bedarf zur Bearbeitung geöffnet werden, was die Durchsicht großer Audiobestände drastisch beschleunigt.

---

## Features

- **Rekursive Dateisuche:**
  - Unterstützt `.mp3`, `.wav`, `.ogg`, `.flac` und `.m4a`.
  - Durchsucht das angegebene Verzeichnis und alle Unterordner.
  - Sortiert alle Funde alphabetisch nach relativem Pfad.
- **Sofortiges Autoplay & Steuerung:**
  - Nutzt `pygame` für latenzarmes Autoplay direkt nach dem Aufruf jeder Datei.
  - Direkte Ein-Tasten-Bedienung in der Konsole:
    - `[Enter]` oder `[Space]`: Sound passt &rarr; weiter zur nächsten Datei.
    - `[r]`: Erneut abspielen (Replay).
    - `[e]`: In Audacity öffnen. Skript blockiert via `subprocess.run()`, bis Audacity geschlossen wird, und spielt die bearbeitete Datei zur Kontrolle automatisch erneut ab.
    - `[q]`: Programm beenden und aktuellen Fortschritt sichern.
- **Session-Handling & Persistenz:**
  - Speichert den Prüffortschritt in `.audacity_auto_sound_tester_session.json` im Audio-Stammverzeichnis.
  - Bei erneutem Start wird an der Stelle fortgesetzt, an der aufgehört wurde.
  - Fortschrittsanzeige im Format: `[14/120] relativer/pfad/sound.mp3`.
  - Atomares Speichern verhindert Datenverlust oder beschädigte Session-Dateien.
- **Fehlerbehandlung:**
  - Graceful Exit bei `Ctrl+C` (`KeyboardInterrupt`) mit automatischer Speicherung des aktuellen Zustands.
  - Freigabe von Dateisperren (`unload`) vor dem Öffnen in Audacity, damit Audacity Dateien ohne Zugriffsfehler überschreiben kann.
  - Fehlertolerant bei nicht unterstützten Codecs oder fehlender Audacity-Installation.

---

## Installation

### Voraussetzungen
- Python 3.8+
- [Audacity](https://www.audacityteam.org/)

### Abhängigkeiten installieren
```bash
pip install -r requirements.txt
```
*(Installiert `pygame`)*

---

## Verwendung

### Standardstart (aktuelles Verzeichnis)
```bash
python audacity_auto_sound_tester.py
```

### Eigenes Verzeichnis angeben
```bash
python audacity_auto_sound_tester.py --dir "D:\AudioSammlung\SFX"
```

### Eigenen Audacity-Pfad angeben
Standardmäßig sucht das Tool unter `C:\Program Files\Audacity\audacity.exe`:
```bash
python audacity_auto_sound_tester.py --audacity "C:\CustomPath\Audacity\audacity.exe"
```

### Session zurücksetzen
Um alle bisherigen Prüfmarkierungen zu verwerfen und wieder bei Datei 1 zu beginnen:
```bash
python audacity_auto_sound_tester.py --reset
```

### Hilfe anzeigen
```bash
python audacity_auto_sound_tester.py --help
```

---

## CLI-Optionen

| Parameter | Kurzform | Standardwert | Beschreibung |
|---|---|---|---|
| `--dir` | `-d` | `.` | Pfad zum Audio-Stammverzeichnis |
| `--audacity` | `-a` | `C:\Program Files\Audacity\audacity.exe` | Pfad zur `audacity.exe` |
| `--reset` | | `False` | Verwirft die gespeicherte Session und startet von vorn |

---

## Tastensteuerung während der Wiedergabe

| Taste | Aktion |
|---|---|
| `[Enter]` oder `[Space]` | **Passt (Weiter)**: Markiert Datei als geprüft, sichert die Session und geht zur nächsten Datei. |
| `[r]` | **Replay**: Startet die Wiedergabe der aktuellen Datei erneut. |
| `[e]` | **In Audacity öffnen**: Stoppt die Wiedergabe, löst Dateisperren und öffnet die Datei in Audacity. Wartet, bis Audacity geschlossen wird, und spielt die Datei zur Kontrolle automatisch erneut ab. |
| `[q]` | **Beenden**: Sichert den bisherigen Fortschritt in der Session-Datei und beendet das Tool. |
| `[Ctrl+C]` | **Abbruch**: Sichert den bisherigen Fortschritt und beendet das Tool sauber. |

---

## Tests ausführen

Das Repository enthält automatisierte Unit- und Integrationstests:

```bash
# Unit-Tests ausführen
python -m unittest test_audacity_auto_sound_tester.py

# End-to-End Integrationstests ausführen
python -m unittest test_integration.py
```

---

## Lizenz
MIT License
