import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add current folder to path
sys.path.insert(0, str(Path(__file__).parent))

from audacity_auto_sound_tester import (
    DEFAULT_AUDACITY_PATH,
    DEFAULT_CONFIG,
    SESSION_FILENAME,
    CONFIG_FILENAME,
    SUPPORTED_EXTENSIONS,
    SoundTester,
    load_or_create_config,
    parse_arguments,
)


def create_test_wav(path: Path, duration_sec: float = 0.05, amplitude: int = 8000):
    path.parent.mkdir(parents=True, exist_ok=True)
    framerate = 44100
    nframes = int(framerate * duration_sec)
    with wave.open(str(path), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(framerate)
        for i in range(nframes):
            val = int(amplitude * math.sin(2.0 * math.pi * 440.0 * i / framerate))
            f.writeframes(struct.pack("<h", val))


class TestAudacityAutoSoundTester(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="sound_tester_test_"))

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_supported_extensions(self):
        expected = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
        self.assertEqual(SUPPORTED_EXTENSIONS, expected)

    def test_scan_files_recursive_and_sorted(self):
        sub1 = self.test_dir / "subfolder_b"
        sub2 = self.test_dir / "subfolder_a"
        hidden = self.test_dir / ".hidden_folder"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)
        hidden.mkdir(parents=True)

        (sub1 / "track_2.wav").touch()
        (sub1 / "track_1.mp3").touch()
        (sub2 / "sample_z.flac").touch()
        (sub2 / "sample_a.ogg").touch()
        (sub2 / "sample_caps.M4A").touch()
        (sub2 / "ignore.txt").touch()
        (hidden / "secret.wav").touch()
        (self.test_dir / ".hidden_file.mp3").touch()

        tester = SoundTester(base_dir=self.test_dir, audacity_path=DEFAULT_AUDACITY_PATH)
        files = tester.scan_files()

        rel_paths = [f.relative_to(self.test_dir).as_posix() for f in files]
        expected = [
            "subfolder_a/sample_a.ogg",
            "subfolder_a/sample_caps.M4A",
            "subfolder_a/sample_z.flac",
            "subfolder_b/track_1.mp3",
            "subfolder_b/track_2.wav",
        ]
        self.assertEqual(rel_paths, expected)

    def test_session_save_and_load(self):
        tester1 = SoundTester(base_dir=self.test_dir, audacity_path=DEFAULT_AUDACITY_PATH)
        tester1.all_files = [self.test_dir / "a.wav", self.test_dir / "b.wav"]
        tester1.completed_files.add("a.wav")
        tester1.save_session()

        session_file = self.test_dir / SESSION_FILENAME
        self.assertTrue(session_file.exists())

        with open(session_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["completed_files"], ["a.wav"])
            self.assertEqual(data["completed_count"], 1)
            self.assertEqual(data["total_files"], 2)

        tester2 = SoundTester(base_dir=self.test_dir, audacity_path=DEFAULT_AUDACITY_PATH)
        tester2.load_session()
        self.assertEqual(tester2.completed_files, {"a.wav"})

    def test_session_reset(self):
        session_file = self.test_dir / SESSION_FILENAME
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump({"completed_files": ["track1.wav"]}, f)

        self.assertTrue(session_file.exists())

        tester = SoundTester(base_dir=self.test_dir, audacity_path=DEFAULT_AUDACITY_PATH, reset=True)
        tester.load_session()

        self.assertFalse(session_file.exists())
        self.assertEqual(tester.completed_files, set())

    def test_load_or_create_config(self):
        cfg_path = self.test_dir / "custom_config.json"
        self.assertFalse(cfg_path.exists())

        cfg = load_or_create_config(cfg_path)
        self.assertTrue(cfg_path.exists())
        self.assertEqual(cfg["volume_step_db"], 1.5)
        self.assertEqual(cfg["target_peak_db"], -1.0)

        # Modify and reload
        cfg["volume_step_db"] = 2.5
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        cfg2 = load_or_create_config(cfg_path)
        self.assertEqual(cfg2["volume_step_db"], 2.5)

    def test_adjust_volume_and_normalize(self):
        wav_path = self.test_dir / "adjust_test.wav"
        create_test_wav(wav_path, amplitude=8000)

        from pydub import AudioSegment
        initial_peak = AudioSegment.from_file(str(wav_path)).max_dBFS

        tester = SoundTester(base_dir=self.test_dir, audacity_path=DEFAULT_AUDACITY_PATH)
        tester.play_audio = MagicMock()
        tester.stop_audio = MagicMock()

        # Volume up +3 dB
        success = tester.adjust_volume(wav_path, delta_db=+3.0)
        self.assertTrue(success)
        peak_after_up = AudioSegment.from_file(str(wav_path)).max_dBFS
        self.assertAlmostEqual(peak_after_up, initial_peak + 3.0, places=1)

        # Volume down -2 dB
        success = tester.adjust_volume(wav_path, delta_db=-2.0)
        self.assertTrue(success)
        peak_after_down = AudioSegment.from_file(str(wav_path)).max_dBFS
        self.assertAlmostEqual(peak_after_down, peak_after_up - 2.0, places=1)

        # Normalize to -1.0 dBFS
        success = tester.normalize_audio(wav_path, target_peak_db=-1.0)
        self.assertTrue(success)
        peak_normalized = AudioSegment.from_file(str(wav_path)).max_dBFS
        self.assertAlmostEqual(peak_normalized, -1.0, places=1)

    @patch("subprocess.run")
    def test_open_in_audacity(self, mock_subprocess):
        dummy_audacity = self.test_dir / "audacity.exe"
        dummy_audacity.touch()
        dummy_sound = self.test_dir / "test.wav"
        dummy_sound.touch()

        tester = SoundTester(base_dir=self.test_dir, audacity_path=dummy_audacity)
        tester._mixer_initialized = True
        tester.play_audio = MagicMock()
        tester.stop_audio = MagicMock()

        result = tester.open_in_audacity(dummy_sound)
        self.assertTrue(result)
        tester.stop_audio.assert_called_once()
        mock_subprocess.assert_called_once_with([str(dummy_audacity), str(dummy_sound.resolve())], check=False)
        tester.play_audio.assert_called_once_with(dummy_sound)

    def test_open_in_audacity_missing_exe(self):
        missing_audacity = self.test_dir / "nonexistent_audacity.exe"
        dummy_sound = self.test_dir / "test.wav"
        dummy_sound.touch()

        tester = SoundTester(base_dir=self.test_dir, audacity_path=missing_audacity)
        result = tester.open_in_audacity(dummy_sound)
        self.assertFalse(result)

    def test_parse_arguments_defaults_and_custom(self):
        with patch("sys.argv", ["audacity_auto_sound_tester.py"]):
            args = parse_arguments()
            self.assertIsNone(args.dir)
            self.assertIsNone(args.audacity)
            self.assertIsNone(args.step_db)
            self.assertIsNone(args.target_peak_db)
            self.assertIsNone(args.skip_normalized)
            self.assertIsNone(args.skip_tolerance)
            self.assertFalse(args.reset)

        custom_args = [
            "audacity_auto_sound_tester.py",
            "--dir", r"C:\Music",
            "--audacity", r"D:\Tools\audacity.exe",
            "--step-db", "2.0",
            "--target-peak-db", "-0.5",
            "--skip-normalized",
            "--skip-tolerance", "0.2",
            "--reset"
        ]
        with patch("sys.argv", custom_args):
            args = parse_arguments()
            self.assertEqual(args.dir, Path(r"C:\Music"))
            self.assertEqual(args.audacity, Path(r"D:\Tools\audacity.exe"))
            self.assertEqual(args.step_db, 2.0)
            self.assertEqual(args.target_peak_db, -0.5)
            self.assertTrue(args.skip_normalized)
            self.assertEqual(args.skip_tolerance, 0.2)
            self.assertTrue(args.reset)

    def test_skip_normalized(self):
        # Create normalized track (target -1.0 dBFS, max 32767 * 10^(-1/20) = ~29205)
        t_norm = self.test_dir / "already_normalized.wav"
        create_test_wav(t_norm, amplitude=29200)

        # Create quiet track (amplitude 5000 -> approx -16 dBFS)
        t_quiet = self.test_dir / "quiet.wav"
        create_test_wav(t_quiet, amplitude=5000)

        tester = SoundTester(
            base_dir=self.test_dir,
            audacity_path=DEFAULT_AUDACITY_PATH,
            target_peak_db=-1.0,
            skip_normalized=True,
            skip_tolerance_db=0.1,
        )
        tester.init_audio = MagicMock()
        tester.play_audio = MagicMock()
        tester.stop_audio = MagicMock()
        tester.cleanup_audio = MagicMock()

        # Only the quiet track should prompt the user; already_normalized must be skipped!
        user_actions = iter(["next"])
        tester.prompt_user_action = lambda: next(user_actions)

        tester.run()

        # Both tracks should now be completed (one via skip, one via next)
        self.assertEqual(tester.completed_files, {"already_normalized.wav", "quiet.wav"})

    def test_full_run_with_simulated_inputs(self):
        t1 = self.test_dir / "track1.wav"
        t2 = self.test_dir / "track2.wav"
        create_test_wav(t1, amplitude=5000)
        create_test_wav(t2, amplitude=5000)

        tester = SoundTester(base_dir=self.test_dir, audacity_path=DEFAULT_AUDACITY_PATH)
        tester.init_audio = MagicMock()
        tester.play_audio = MagicMock()
        tester.stop_audio = MagicMock()
        tester.cleanup_audio = MagicMock()

        # Simulate: track1 -> normalize -> volume_up -> next; track2 -> next
        simulated_actions = iter(["normalize", "volume_up", "next", "next"])
        tester.prompt_user_action = lambda: next(simulated_actions)

        tester.run()

        self.assertEqual(tester.completed_files, {"track1.wav", "track2.wav"})
        self.assertTrue((self.test_dir / SESSION_FILENAME).exists())


if __name__ == "__main__":
    unittest.main()
