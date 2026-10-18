# AudacityAutoSoundTester

Ein interaktives Python-CLI-Tool zur manuellen Qualitätskontrolle und Lautstärkeanpassung einer Audiosammlung mit **direkter Pegelbearbeitung per Tastendruck** und nahtloser Audacity-Integration.

## Ziel

`AudacityAutoSoundTester` arbeitet alle Audiodateien in einem Stammverzeichnis (rekursiv über alle Unterordner) einzeln und nacheinander ab.
Für jede Datei startet im Terminal sofort ein Autoplay, sodass der Benutzer unmittelbar reinhören kann. 

**Kein umständliches Projekt-Speichern in Audacity nötig:**
- Pegelanpassungen und Normalisierungen können **direkt mit einer einzigen Taste** im Terminal vorgenommen werden (`+`, `-`, `n`). Die Datei wird sofort überschrieben und zur Kontrolle neu abgespielt.
- Audacity muss nur noch bei Bedarf für komplexe Schnitte oder Effekte geöffnet werden (`e`).

---

## Features

- **Direkte Pegelbearbeitung (In-Place Overwrite):**
  - `[+]`: Erhöht die Lautstärke um den konfigurierten dB-Wert (Standard: `+1.5 dB`), überschreibt die Datei und spielt sie sofort zur Kontrolle ab.
  - `[-]`: Senkt die Lautstärke um den konfigurierten dB-Wert (Standard: `-1.5 dB`), überschreibt die Datei und spielt sie ab.
  - `[n]`: Normalisiert die Datei automatisch auf den konfigurierten Ziel-Peak (Standard: `-1.0 dBFS`), überschreibt die Datei und spielt sie ab.
- **Konfigurationsdatei (`config.json`):**
  - Alle Standardwerte (Audio-Verzeichnis, Audacity-Pfad, dB-Schrittweite, Ziel-Peak) werden in `config.json` hinterlegt.
  - Startet man das Skript ohne Parameter (`python audacity_auto_sound_tester.py`), werden automatisch die Pfade und Werte aus der `config.json` geladen.
- **Rekursive Dateisuche:**
  - Unterstützt `.mp3`, `.wav`, `.ogg`, `.flac` und `.m4a`.
  - Durchsucht das angegebene Verzeichnis und alle Unterordner.
  - Sortiert alle Funde alphabetisch nach relativem Pfad.
- **Session-Handling & Persistenz:**
  - Speichert den Prüffortschritt in `.audacity_auto_sound_tester_session.json` im Audio-Stammverzeichnis.
  - Bei erneutem Start wird exakt an der Stelle fortgesetzt, an der aufgehört wurde.
  - Fortschrittsanzeige im Format: `[14/120] relativer/pfad/sound.mp3`.
  - Atomares Speichern verhindert Datenverlust oder beschädigte Dateien.
- **Audacity-Integration:**
  - `[e]` öffnet die Datei in Audacity und pausiert das Skript, bis Audacity geschlossen wird.
  - Nach dem Schließen spielt das Skript die bearbeitete Datei zur Kontrolle automatisch erneut ab.
- **Fehlerbehandlung:**
  - Graceful Exit bei `Ctrl+C` (`KeyboardInterrupt`) mit automatischer Speicherung des aktuellen Zustands.
  - Saubere Freigabe von Dateisperren (`unload`) vor Änderungen oder Öffnen in Audacity.

---

## Installation

### Voraussetzungen
- Python 3.8+
- [Audacity](https://www.audacityteam.org/) (optional für komplexe Schnitte)
- [FFmpeg](https://ffmpeg.org/) (wird für Audio-Konvertierung von MP3, OGG, FLAC, M4A genutzt; wird unter Windows automatisch gefunden)

### Abhängigkeiten installieren
```bash
pip install -r requirements.txt
```
*(Installiert `pygame` und `pydub`)*

---

## Konfiguration (`config.json`)

Im Skriptverzeichnis liegt die `config.json` (wird beim ersten Start automatisch erstellt, falls nicht vorhanden):

```json
{
  "audio_dir": ".",
  "audacity_path": "C:\\Program Files\\Audacity\\audacity.exe",
  "volume_step_db": 1.5,
  "target_peak_db": -1.0
}
```

- **`audio_dir`**: Das Standard-Stammverzeichnis deiner Audio-Dateien (wird genutzt, wenn kein `--dir` angegeben wird).
- **`audacity_path`**: Pfad zur `audacity.exe`.
- **`volume_step_db`**: Schrittweite in dB beim Drücken von `+` bzw. `-`.
- **`target_peak_db`**: Ziel-Peak in dBFS beim Drücken von `n` (z. B. `-1.0`).

---

## Verwendung

### Einfacher Start ohne Parameter (nutzt `config.json`)
```bash
python audacity_auto_sound_tester.py
```

### Parameter manuell übersteuern
```bash
# Anderes Verzeichnis prüfen:
python audacity_auto_sound_tester.py --dir "D:\AudioSammlung\SFX"

# Bereits normalisierte Dateien überspringen (+/- 0.1 dB um Normalwert):
python audacity_auto_sound_tester.py --skip-normalized

# Eigene Toleranz angeben (z. B. +/- 0.2 dB):
python audacity_auto_sound_tester.py --skip-normalized --skip-tolerance 0.2

# Andere Schrittweite (z. B. 2.0 dB) und Ziel-Peak (-0.5 dBFS):
python audacity_auto_sound_tester.py --step-db 2.0 --target-peak-db -0.5

# Session zurücksetzen und von vorn beginnen:
python audacity_auto_sound_tester.py --reset
```

---

## CLI-Optionen

| Parameter | Kurzform | Standardwert | Beschreibung |
|---|---|---|---|
| `--config` | `-c` | `config.json` | Pfad zur Konfigurationsdatei |
| `--dir` | `-d` | Wert aus `config.json` | Pfad zum Audio-Stammverzeichnis |
| `--audacity` | `-a` | Wert aus `config.json` | Pfad zur `audacity.exe` |
| `--step-db` | | Wert aus `config.json` | dB-Schrittweite für lauter/leiser (`+` / `-`) |
| `--target-peak-db` | | Wert aus `config.json` | Ziel-Peak in dBFS für Normalisierung (`n`) |
| `--skip-normalized` / `--no-skip-normalized` | | Wert aus `config.json` (`false`) | Überspringt Dateien, deren Peak bereits innerhalb der Toleranz des Ziel-Peaks liegt |
| `--skip-tolerance` | | Wert aus `config.json` (`0.1`) | Toleranz in dB für `--skip-normalized` (Standard: `±0.1 dB`) |
| `--reset` | | `False` | Verwirft die gespeicherte Session und startet von vorn |

---

## Tastensteuerung während der Wiedergabe

| Taste | Aktion |
|---|---|
| `[Enter]` oder `[Space]` | **Passt (Weiter)**: Markiert Datei als geprüft, sichert die Session und geht zur nächsten Datei. |
| `[r]` | **Replay**: Startet die Wiedergabe der aktuellen Datei erneut. |
| `[+]` | **Lauter**: Hebt den Pegel um `+volume_step_db` an, überschreibt die Datei und spielt sie sofort zur Kontrolle ab. |
| `[-]` | **Leiser**: Senkt den Pegel um `-volume_step_db` ab, überschreibt die Datei und spielt sie sofort ab. |
| `[n]` | **Normalisieren**: Setzt den Spitzenpegel auf `target_peak_db` (z. B. -1.0 dBFS), überschreibt die Datei und spielt sie ab. |
| `[e]` | **In Audacity öffnen**: Öffnet die Datei in Audacity für komplexe Schnitte. Nach dem Schließen wird die Datei zur Kontrolle erneut abgespielt. |
| `[q]` | **Beenden**: Sichert den bisherigen Fortschritt in der Session-Datei und beendet das Tool. |
| `[Ctrl+C]` | **Abbruch**: Sichert den bisherigen Fortschritt und beendet das Tool sauber. |

---

## Tests ausführen

```bash
# Alle Unit- und Integrationstests ausführen
python -m unittest discover
```

---

## Lizenz
MIT License
