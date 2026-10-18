#!/usr/bin/env python3
"""
AudacityAutoSoundTester
=======================
Ein interaktives Python-CLI-Tool zur manuellen Qualitätskontrolle
und Lautstärkeanpassung einer Audiosammlung mit direkter Audacity-Anbindung.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Set, List

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

try:
    import pygame
except ImportError:
    pygame = None

SESSION_FILENAME = ".audacity_auto_sound_tester_session.json"
SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
DEFAULT_AUDACITY_PATH = Path(r"C:\Program Files\Audacity\audacity.exe")


class SoundTester:
    def __init__(
        self,
        base_dir: Path,
        audacity_path: Path,
        reset: bool = False,
    ):
        self.base_dir = base_dir.resolve()
        self.audacity_path = audacity_path.resolve()
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
            # Ignoriere versteckte Ordner (z.B. .git)
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for file_name in files:
                if file_name.startswith("."):
                    continue
                ext = Path(file_name).suffix.lower()
                if ext in SUPPORTED_EXTENSIONS:
                    audio_files.append(Path(root) / file_name)

        # Alphabetisch nach relativem Pfad sortieren
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
        # Sortierte Liste für reproduzierbare JSON-Dateien
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

    def prompt_user_action(self) -> str:
        """
        Liest die Benutzeraktion ein.
        Unterstützt direkte Tastendrücke (msvcrt unter Windows)
        sowie Standard-input()-Fallback für Terminals ohne TTY oder andere Plattformen.
        """
        prompt_text = "  Aktion: [Enter/Space] Passt (Weiter) | [r] Replay | [e] Audacity | [q] Beenden\n  Auswahl: "
        sys.stdout.write(prompt_text)
        sys.stdout.flush()

        if sys.platform == "win32" and sys.stdin.isatty():
            import msvcrt
            while True:
                char = msvcrt.getwch()
                # Sonder- / Funktionstasten abfangen (bestehen aus 2 Codes)
                if char in ("\x00", "\xe0"):
                    msvcrt.getwch()
                    continue
                # Ctrl+C
                if char == "\x03":
                    print("^C")
                    raise KeyboardInterrupt

                # Enter (\r, \n) oder Leerzeichen -> Weiter
                if char in ("\r", "\n", " "):
                    print("[Weiter]")
                    return "next"

                c_lower = char.lower()
                if c_lower == "r":
                    print("[r - Replay]")
                    return "replay"
                elif c_lower == "e":
                    print("[e - Audacity]")
                    return "edit"
                elif c_lower == "q":
                    print("[q - Beenden]")
                    return "quit"

                # Ungültige Taste
                sys.stdout.write(f"\r  [Ungültig: '{char}'] " + prompt_text)
                sys.stdout.flush()
        else:
            # Fallback für nicht-interaktive Umgebungen / Linux / Tests
            while True:
                line = sys.stdin.readline()
                if not line:  # EOF
                    return "quit"
                line = line.strip().lower()
                if line in ("", " ", "next"):
                    return "next"
                if line in ("r", "replay"):
                    return "replay"
                if line in ("e", "edit"):
                    return "edit"
                if line in ("q", "quit", "exit"):
                    return "quit"
                sys.stdout.write("  Ungültige Eingabe. Bitte Enter/Space, r, e oder q wählen:\n  Auswahl: ")
                sys.stdout.flush()

    def open_in_audacity(self, file_path: Path) -> bool:
        """
        Öffnet die Datei in Audacity, blockiert bis Audacity geschlossen wird,
        und spielt die bearbeitete Datei anschließend zur Kontrolle ab.
        """
        if not self.audacity_path.is_file():
            print(f"\n  ❌ Audacity-Executable nicht gefunden unter:")
            print(f"     {self.audacity_path}")
            print(f"     Bitte gib den korrekten Pfad via '--audacity \"PFAD\"' an.\n")
            return False

        # Wichtig: Vor dem Starten von Audacity Datei-Locks von pygame lösen
        self.stop_audio()

        print(f"\n  🚀 Öffne in Audacity: {file_path.name}")
        print("  ⏳ Skript wartet, bis Audacity geschlossen wird...")

        try:
            subprocess.run([str(self.audacity_path), str(file_path.resolve())], check=False)
        except Exception as e:
            print(f"  ❌ Fehler beim Starten von Audacity: {e}\n")
            return False

        print("  ✅ Audacity geschlossen. Spiele Datei zur Kontrolle erneut ab...\n")
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

                # Bereits in vorheriger Session erledigte Dateien überspringen
                if rel_path in self.completed_files:
                    continue

                # Fortschrittsanzeige: [14/120] relativer/pfad/sound.mp3
                print(f"[{index}/{total_files}] {rel_path}")

                # Autoplay starten
                self.play_audio(file_path)

                # Interaktive Schleife für die aktuelle Datei
                while True:
                    action = self.prompt_user_action()

                    if action == "next":
                        self.stop_audio()
                        self.completed_files.add(rel_path)
                        self.save_session()
                        print()  # Leerzeile für Übersicht
                        break

                    elif action == "replay":
                        print("  ▶️  Replay...")
                        self.play_audio(file_path)

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
        description="Manuelle Qualitätskontrolle und Lautstärkeanpassung einer Audiosammlung mit Audacity-Integration.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dir",
        "-d",
        type=Path,
        default=Path("."),
        help="Pfad zum Audio-Stammverzeichnis.",
    )
    parser.add_argument(
        "--audacity",
        "-a",
        type=Path,
        default=DEFAULT_AUDACITY_PATH,
        help="Pfad zur audacity.exe.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Verwirft die gespeicherte Session und startet von vorn.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    tester = SoundTester(
        base_dir=args.dir,
        audacity_path=args.audacity,
        reset=args.reset,
    )
    tester.run()


if __name__ == "__main__":
    main()
