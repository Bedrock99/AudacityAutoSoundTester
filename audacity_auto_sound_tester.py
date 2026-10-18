#!/usr/bin/env python3
"""
AudacityAutoSoundTester
=======================
Ein interaktives Python-CLI-Tool zur manuellen Qualitätskontrolle
und Lautstärkeanpassung einer Audiosammlung mit direkter
Pegelbearbeitung (+ / - / n) und Audacity-Anbindung.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Set, List, Dict, Any

# Unterdrücke pygame Begrüßungstext im Terminal
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

# UTF-8 Encoding auf Windows Terminal sicherstellen
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def ensure_ffmpeg_in_path() -> None:
    """Stellt sicher, dass FFmpeg im Suchpfad auffindbar ist (auch unter Windows nach WinGet-Installation)."""
    if shutil.which("ffmpeg") is not None:
        return

    # Windows Registry User-Environment PATH prüfen
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                user_path, _ = winreg.QueryValueEx(key, "Path")
                for item in user_path.split(";"):
                    item = item.strip()
                    if item and item not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = item + ";" + os.environ.get("PATH", "")
        except Exception:
            pass

    # WinGet / LocalAppData Pakete durchsuchen
    if shutil.which("ffmpeg") is None:
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            candidate = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
            if candidate.is_dir():
                for exe in candidate.glob("**/ffmpeg.exe"):
                    os.environ["PATH"] = str(exe.parent) + ";" + os.environ.get("PATH", "")
                    break


ensure_ffmpeg_in_path()

try:
    import pygame
except ImportError:
    pygame = None

try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None

SESSION_FILENAME = ".audacity_auto_sound_tester_session.json"
CONFIG_FILENAME = "config.json"
SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
DEFAULT_AUDACITY_PATH = Path(r"C:\Program Files\Audacity\audacity.exe")

DEFAULT_CONFIG: Dict[str, Any] = {
    "audio_dir": ".",
    "audacity_path": r"C:\Program Files\Audacity\audacity.exe",
    "volume_step_db": 1.5,
    "target_peak_db": -1.0,
    "skip_normalized": False,
    "skip_tolerance_db": 0.1,
}


def load_or_create_config(config_path: Path) -> Dict[str, Any]:
    """Lädt die Konfiguration aus einer JSON-Datei oder legt sie mit Standardwerten an."""
    config = dict(DEFAULT_CONFIG)
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    config.update(data)
        except Exception as e:
            print(f"⚠️  Konfigurationsdatei '{config_path}' konnte nicht gelesen werden ({e}). Verwende Standardwerte.")
    else:
        # Standardkonfiguration erstellen
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"📄 Neue Konfigurationsdatei erstellt: {config_path.name}")
        except Exception as e:
            print(f"⚠️  Konnte Standard-Konfiguration nicht schreiben: {e}")

    return config


class SoundTester:
    def __init__(
        self,
        base_dir: Path,
        audacity_path: Path,
        volume_step_db: float = 1.5,
        target_peak_db: float = -1.0,
        skip_normalized: bool = False,
        skip_tolerance_db: float = 0.1,
        reset: bool = False,
    ):
        self.base_dir = base_dir.resolve()
        self.audacity_path = audacity_path.resolve()
        self.volume_step_db = volume_step_db
        self.target_peak_db = target_peak_db
        self.skip_normalized = skip_normalized
        self.skip_tolerance_db = skip_tolerance_db
        self.reset = reset
        self.session_file = self.base_dir / SESSION_FILENAME
        self.completed_files: Set[str] = set()
        self.all_files: List[Path] = []
        self._mixer_initialized = False

    def init_audio(self) -> None:
        """Initialisiert den pygame Audio-Mixer."""
        if pygame is None:
            print("❌ Fehler: Das Paket 'pygame' ist nicht installiert.")
            print("   Bitte installiere es mit: pip install pygame")
            sys.exit(1)

        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            self._mixer_initialized = True
        except Exception as e:
            print(f"⚠️  Warnung: Audio-Mixer konnte nicht initialisiert werden: {e}")
            self._mixer_initialized = False

    def cleanup_audio(self) -> None:
        """Stoppt die Wiedergabe und gibt Audio-Ressourcen frei."""
        self.stop_audio()
        if self._mixer_initialized and pygame and pygame.mixer.get_init():
            try:
                pygame.mixer.quit()
            except Exception:
                pass
            self._mixer_initialized = False

    def play_audio(self, file_path: Path) -> bool:
        """Spielt eine Audiodatei über pygame.mixer ab."""
        if not self._mixer_initialized:
            return False

        self.stop_audio()
        try:
            pygame.mixer.music.load(str(file_path))
            pygame.mixer.music.play()
            return True
        except pygame.error as e:
            print(f"\n  ⚠️  Wiedergabefehler: {e}")
            print("     (Format evtl. von pygame nicht direkt unterstützt. Audacity [e] kann genutzt werden.)")
            return False
        except Exception as e:
            print(f"\n  ⚠️  Unerwarteter Fehler beim Abspielen: {e}")
            return False

    def stop_audio(self) -> None:
        """Stoppt die aktuelle Wiedergabe und entlädt die Datei (wichtig für Datei-Locks unter Windows)."""
        if self._mixer_initialized and pygame and pygame.mixer.get_init():
            try:
                pygame.mixer.music.stop()
                if hasattr(pygame.mixer.music, "unload"):
                    pygame.mixer.music.unload()
            except Exception:
                pass

    def scan_files(self) -> List[Path]:
        """Durchsucht das Stammverzeichnis rekursiv nach Audiodateien und sortiert sie alphabetisch."""
        audio_files: List[Path] = []
        for root, dirs, files in os.walk(self.base_dir, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for file_name in files:
                if file_name.startswith("."):
                    continue
                ext = Path(file_name).suffix.lower()
                if ext in SUPPORTED_EXTENSIONS:
                    audio_files.append(Path(root) / file_name)

        audio_files.sort(key=lambda p: p.relative_to(self.base_dir).as_posix().lower())
        return audio_files

    def load_session(self) -> None:
        """Lädt bestehende Session oder setzt sie zurück."""
        if self.reset:
            if self.session_file.exists():
                try:
                    self.session_file.unlink()
                    print(f"🔄 Vorherige Session verworfen (--reset).")
                except OSError as e:
                    print(f"⚠️  Konnte Session-Datei nicht löschen: {e}")
            self.completed_files = set()
            return

        if self.session_file.exists():
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.completed_files = set(data.get("completed_files", []))
                    print(f"📂 Vorherige Session geladen: {len(self.completed_files)} Datei(en) bereits als geprüft markiert.")
            except Exception as e:
                print(f"⚠️  Konnte Session-Datei nicht lesen ({e}). Starte neue Session.")
                self.completed_files = set()
        else:
            self.completed_files = set()

    def save_session(self) -> None:
        """Speichert den aktuellen Fortschritt atomar in der Session-Datei."""
        sorted_completed = sorted(list(self.completed_files))
        session_data = {
            "version": 1,
            "base_dir": str(self.base_dir),
            "total_files": len(self.all_files),
            "completed_count": len(self.completed_files),
            "completed_files": sorted_completed,
            "last_updated": datetime.now().isoformat(),
        }

        temp_file = self.base_dir / f"{SESSION_FILENAME}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.session_file)
        except Exception as e:
            print(f"\n⚠️  Fehler beim Speichern der Session-Datei: {e}")

    def export_audio(self, sound: Any, target_path: Path) -> None:
        """Exportiert ein AudioSegment atomar in das Zielformat."""
        ext = target_path.suffix.lower()
        temp_path = target_path.with_name(f"{target_path.stem}.tmp_edit{target_path.suffix}")
        try:
            if ext == ".mp3":
                sound.export(str(temp_path), format="mp3", bitrate="320k")
            elif ext == ".wav":
                sound.export(str(temp_path), format="wav")
            elif ext == ".flac":
                sound.export(str(temp_path), format="flac")
            elif ext == ".ogg":
                sound.export(str(temp_path), format="ogg", bitrate="320k")
            elif ext == ".m4a":
                sound.export(str(temp_path), format="ipod", bitrate="256k")
            else:
                sound.export(str(temp_path), format=ext.lstrip("."))

            temp_path.replace(target_path)
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise

    def get_peak_dbfs(self, file_path: Path) -> Optional[float]:
        """Berechnet den Spitzenpegel (Peak) einer Audiodatei in dBFS."""
        if AudioSegment is None:
            return None
        try:
            sound = AudioSegment.from_file(str(file_path))
            return sound.max_dBFS
        except Exception:
            return None

    def format_peak(self, peak: Optional[float]) -> str:
        """Formatiert einen Peak-Wert lesbar für das Terminal."""
        if peak is None:
            return "n/a"
        if peak == float("-inf"):
            return "-inf (Stille)"
        if peak >= -0.05:
            return f"{peak:.1f} dBFS ⚠️ CLIPPING"
        return f"{peak:.1f} dBFS"

    def adjust_volume(self, file_path: Path, delta_db: float) -> bool:
        """Passt die Lautstärke um delta_db an, überschreibt die Datei und spielt sie erneut ab."""
        if AudioSegment is None:
            print("  ❌ 'pydub' ist nicht installiert. Lautstärkeanpassung nicht verfügbar.")
            return False

        self.stop_audio()
        try:
            sound = AudioSegment.from_file(str(file_path))
            new_sound = sound.apply_gain(delta_db)
            self.export_audio(new_sound, file_path)

            direction = f"+{delta_db:.1f} dB" if delta_db > 0 else f"{delta_db:.1f} dB"
            new_peak = new_sound.max_dBFS
            print(f"  🔊 Lautstärke um {direction} angepasst (Neuer Peak: {self.format_peak(new_peak)})")
            self.play_audio(file_path)
            return True
        except Exception as e:
            print(f"  ❌ Fehler bei der Lautstärkeanpassung: {e}")
            self.play_audio(file_path)
            return False

    def normalize_audio(self, file_path: Path, target_peak_db: float) -> bool:
        """Normalisiert die Audiodatei auf target_peak_db, überschreibt die Datei und spielt sie erneut ab."""
        if AudioSegment is None:
            print("  ❌ 'pydub' ist nicht installiert. Normalisierung nicht verfügbar.")
            return False

        self.stop_audio()
        try:
            sound = AudioSegment.from_file(str(file_path))
            current_peak = sound.max_dBFS
            if current_peak == float("-inf"):
                print("  ⚠️  Datei enthält nur Stille, keine Normalisierung möglich.")
                self.play_audio(file_path)
                return False

            delta_db = target_peak_db - current_peak
            new_sound = sound.apply_gain(delta_db)
            self.export_audio(new_sound, file_path)

            direction = f"+{delta_db:.1f} dB" if delta_db > 0 else f"{delta_db:.1f} dB"
            print(f"  🎯 Normalisiert auf {target_peak_db:.1f} dBFS (Änderung: {direction}, alter Peak: {self.format_peak(current_peak)})")
            self.play_audio(file_path)
            return True
        except Exception as e:
            print(f"  ❌ Fehler beim Normalisieren: {e}")
            self.play_audio(file_path)
            return False

    def prompt_user_action(self) -> str:
        """Liest die Benutzeraktion ein (Tastendruck unter Windows, Input-Fallback)."""
        prompt_text = (
            f"  Aktion: [Enter/Space] Passt | [r] Replay | [+] Lauter (+{self.volume_step_db}dB) | "
            f"[-] Leiser (-{self.volume_step_db}dB) | [n] Normalisieren ({self.target_peak_db}dBFS) | "
            f"[e] Audacity | [q] Beenden\n  Auswahl: "
        )
        sys.stdout.write(prompt_text)
        sys.stdout.flush()

        if sys.platform == "win32" and sys.stdin.isatty():
            import msvcrt
            while True:
                char = msvcrt.getwch()
                if char in ("\x00", "\xe0"):
                    msvcrt.getwch()
                    continue
                if char == "\x03":
                    print("^C")
                    raise KeyboardInterrupt

                if char in ("\r", "\n", " "):
                    print("[Weiter]")
                    return "next"
                elif char in ("+", "="):
                    print("[+] Lauter")
                    return "volume_up"
                elif char == "-":
                    print("[-] Leiser")
                    return "volume_down"

                c_lower = char.lower()
                if c_lower == "n":
                    print("[n - Normalisieren]")
                    return "normalize"
                elif c_lower == "r":
                    print("[r - Replay]")
                    return "replay"
                elif c_lower == "e":
                    print("[e - Audacity]")
                    return "edit"
                elif c_lower == "q":
                    print("[q - Beenden]")
                    return "quit"

                sys.stdout.write(f"\r  [Ungültig: '{char}'] " + prompt_text)
                sys.stdout.flush()
        else:
            while True:
                line = sys.stdin.readline()
                if not line:
                    return "quit"
                line = line.strip().lower()
                if line in ("", " ", "next"):
                    return "next"
                if line in ("+", "plus", "louder", "lauter"):
                    return "volume_up"
                if line in ("-", "minus", "quieter", "leiser"):
                    return "volume_down"
                if line in ("n", "norm", "normalize", "normalisieren"):
                    return "normalize"
                if line in ("r", "replay"):
                    return "replay"
                if line in ("e", "edit"):
                    return "edit"
                if line in ("q", "quit", "exit"):
                    return "quit"
                sys.stdout.write("  Ungültige Eingabe. Bitte Enter/Space, r, +, -, n, e oder q wählen:\n  Auswahl: ")
                sys.stdout.flush()

    def open_in_audacity(self, file_path: Path) -> bool:
        """Öffnet die Datei in Audacity, blockiert bis Audacity geschlossen wird, und spielt sie zur Kontrolle ab."""
        if not self.audacity_path.is_file():
            print(f"\n  ❌ Audacity-Executable nicht gefunden unter:")
            print(f"     {self.audacity_path}")
            print(f"     Bitte gib den korrekten Pfad via '--audacity \"PFAD\"' oder in config.json an.\n")
            return False

        self.stop_audio()
        print(f"\n  🚀 Öffne in Audacity: {file_path.name}")
        print("  ⏳ Skript wartet, bis Audacity geschlossen wird...")

        try:
            subprocess.run([str(self.audacity_path), str(file_path.resolve())], check=False)
        except Exception as e:
            print(f"  ❌ Fehler beim Starten von Audacity: {e}\n")
            return False

        cur_peak = self.get_peak_dbfs(file_path)
        print(f"  ✅ Audacity geschlossen. Spiele Datei zur Kontrolle erneut ab... (Peak: {self.format_peak(cur_peak)})\n")
        self.play_audio(file_path)
        return True

    def run(self) -> None:
        """Hauptablauf des SoundTesters."""
        if not self.base_dir.is_dir():
            print(f"❌ Fehler: Das angegebene Verzeichnis existiert nicht: {self.base_dir}")
            sys.exit(1)

        print("\n" + "=" * 64)
        print(" 🎵  AudacityAutoSoundTester  🎵")
        print("=" * 64)
        print(f" Stammverzeichnis: {self.base_dir}")
        print(f" Audacity:        {self.audacity_path}")
        print(f" Pegel-Schritt:   ±{self.volume_step_db} dB")
        print(f" Ziel-Peak:       {self.target_peak_db} dBFS")
        if self.skip_normalized:
            print(f" Skip-Normalisiert: Aktiv (±{self.skip_tolerance_db} dB um {self.target_peak_db} dBFS)")
        else:
            print(f" Skip-Normalisiert: Deaktiviert")
        print(f" Session-Datei:   {self.session_file.name}")
        print("-" * 64)

        self.load_session()
        self.all_files = self.scan_files()
        total_files = len(self.all_files)

        if total_files == 0:
            print(f"ℹ️  Keine unterstützten Audiodateien in '{self.base_dir}' gefunden.")
            print(f"   Unterstützte Formate: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
            return

        already_done = len(self.completed_files)
        print(f"📊 Gefundene Audiodateien: {total_files} (bereits geprüft: {already_done})")
        print("-" * 64 + "\n")

        self.init_audio()

        try:
            for index, file_path in enumerate(self.all_files, start=1):
                rel_path = file_path.relative_to(self.base_dir).as_posix()

                if rel_path in self.completed_files:
                    continue

                peak = self.get_peak_dbfs(file_path)

                # Prüfen, ob die Datei bereits im Normalisierungsbereich liegt (+/- 0.1 dB)
                if self.skip_normalized and peak is not None and peak != float("-inf"):
                    if abs(peak - self.target_peak_db) <= self.skip_tolerance_db + 1e-6:
                        print(
                            f"⏭️  [{index}/{total_files}] {rel_path}  (Peak: {self.format_peak(peak)}) "
                            f"-> Bereits normalisiert (±{self.skip_tolerance_db} dB), übersprungen."
                        )
                        self.completed_files.add(rel_path)
                        self.save_session()
                        continue

                print(f"[{index}/{total_files}] {rel_path}  (Peak: {self.format_peak(peak)})")
                self.play_audio(file_path)

                while True:
                    action = self.prompt_user_action()

                    if action == "next":
                        self.stop_audio()
                        self.completed_files.add(rel_path)
                        self.save_session()
                        print()
                        break

                    elif action == "replay":
                        cur_peak = self.get_peak_dbfs(file_path)
                        print(f"  ▶️  Replay... (Peak: {self.format_peak(cur_peak)})")
                        self.play_audio(file_path)

                    elif action == "volume_up":
                        self.adjust_volume(file_path, delta_db=+self.volume_step_db)

                    elif action == "volume_down":
                        self.adjust_volume(file_path, delta_db=-self.volume_step_db)

                    elif action == "normalize":
                        self.normalize_audio(file_path, target_peak_db=self.target_peak_db)

                    elif action == "edit":
                        self.open_in_audacity(file_path)

                    elif action == "quit":
                        self.stop_audio()
                        self.save_session()
                        print(f"\n💾 Programm beendet. Fortschritt gespeichert ({len(self.completed_files)}/{total_files}).")
                        return

            print("=" * 64)
            print(f"🎉 Fertig! Alle {total_files} Audiodateien wurden geprüft.")
            print("=" * 64)

        except KeyboardInterrupt:
            self.stop_audio()
            self.save_session()
            print(f"\n\n⏹️  Abbruch durch Benutzer (Ctrl+C). Fortschritt wurde gespeichert ({len(self.completed_files)}/{total_files}).")
        finally:
            self.cleanup_audio()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="AudacityAutoSoundTester",
        description="Manuelle Qualitätskontrolle und Lautstärkeanpassung einer Audiosammlung mit direkter Pegel- und Audacity-Integration.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path(__file__).parent / CONFIG_FILENAME,
        help="Pfad zur Konfigurationsdatei (Standard: config.json im Skriptverzeichnis).",
    )
    parser.add_argument(
        "--dir",
        "-d",
        type=Path,
        default=None,
        help="Pfad zum Audio-Stammverzeichnis (überschreibt config.json).",
    )
    parser.add_argument(
        "--audacity",
        "-a",
        type=Path,
        default=None,
        help="Pfad zur audacity.exe (überschreibt config.json).",
    )
    parser.add_argument(
        "--step-db",
        type=float,
        default=None,
        help="dB-Schrittweite für lauter/leiser (+/-) (überschreibt config.json).",
    )
    parser.add_argument(
        "--target-peak-db",
        type=float,
        default=None,
        help="Ziel-Peak in dBFS für Normalisierung (n) (überschreibt config.json).",
    )
    parser.add_argument(
        "--skip-normalized",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Überspringt Dateien, deren Peak bereits innerhalb der Toleranz (+/- 0.1 dB) des Ziel-Peaks liegt.",
    )
    parser.add_argument(
        "--skip-tolerance",
        type=float,
        default=None,
        help="Toleranz in dB für --skip-normalized (Standard: 0.1, überschreibt config.json).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Verwirft die gespeicherte Session und startet von vorn.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    config = load_or_create_config(args.config)

    # CLI-Argumente haben Vorrang vor config.json
    base_dir = args.dir if args.dir is not None else Path(config.get("audio_dir", "."))
    audacity_path = (
        args.audacity
        if args.audacity is not None
        else Path(config.get("audacity_path", DEFAULT_AUDACITY_PATH))
    )
    volume_step_db = (
        args.step_db
        if args.step_db is not None
        else float(config.get("volume_step_db", 1.5))
    )
    target_peak_db = (
        args.target_peak_db
        if args.target_peak_db is not None
        else float(config.get("target_peak_db", -1.0))
    )
    skip_normalized = (
        args.skip_normalized
        if args.skip_normalized is not None
        else bool(config.get("skip_normalized", False))
    )
    skip_tolerance_db = (
        args.skip_tolerance
        if args.skip_tolerance is not None
        else float(config.get("skip_tolerance_db", 0.1))
    )

    tester = SoundTester(
        base_dir=base_dir,
        audacity_path=audacity_path,
        volume_step_db=volume_step_db,
        target_peak_db=target_peak_db,
        skip_normalized=skip_normalized,
        skip_tolerance_db=skip_tolerance_db,
        reset=args.reset,
    )
    tester.run()


if __name__ == "__main__":
    main()
