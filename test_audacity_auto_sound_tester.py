import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add current folder to path
sys.path.insert(0, str(Path(__file__).parent))

from audacity_auto_sound_tester import (
    DEFAULT_AUDACITY_PATH,
    SESSION_FILENAME,
    SUPPORTED_EXTENSIONS,
    SoundTester,
    parse_arguments,
)


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
        # Create subfolders and files
        sub1 = self.test_dir / "subfolder_b"
        sub2 = self.test_dir / "subfolder_a"
        hidden = self.test_dir / ".hidden_folder"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)
        hidden.mkdir(parents=True)

        # Files
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

        # Tester 2 loads session
        tester2 = SoundTester(base_dir=self.test_dir, audacity_path=DEFAULT_AUDACITY_PATH)
        tester2.load_session()
        self.assertEqual(tester2.completed_files, {"a.wav"})

    def test_session_reset(self):
        # Create session file
        session_file = self.test_dir / SESSION_FILENAME
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump({"completed_files": ["track1.wav"]}, f)

        self.assertTrue(session_file.exists())

        # Load with reset=True
        tester = SoundTester(base_dir=self.test_dir, audacity_path=DEFAULT_AUDACITY_PATH, reset=True)
        tester.load_session()

        self.assertFalse(session_file.exists())
        self.assertEqual(tester.completed_files, set())

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

    def test_parse_arguments_defaults(self):
        with patch("sys.argv", ["audacity_auto_sound_tester.py"]):
            args = parse_arguments()
            self.assertEqual(args.dir, Path("."))
            self.assertEqual(args.audacity, DEFAULT_AUDACITY_PATH)
            self.assertFalse(args.reset)

    def test_parse_arguments_custom(self):
        custom_args = [
            "audacity_auto_sound_tester.py",
            "--dir", r"C:\Music",
            "--audacity", r"D:\Tools\audacity.exe",
            "--reset"
        ]
        with patch("sys.argv", custom_args):
            args = parse_arguments()
            self.assertEqual(args.dir, Path(r"C:\Music"))
            self.assertEqual(args.audacity, Path(r"D:\Tools\audacity.exe"))
            self.assertTrue(args.reset)

    def test_full_run_with_simulated_inputs(self):
        (self.test_dir / "track1.wav").touch()
        (self.test_dir / "track2.wav").touch()

        tester = SoundTester(base_dir=self.test_dir, audacity_path=DEFAULT_AUDACITY_PATH)
        tester.init_audio = MagicMock()
        tester.play_audio = MagicMock()
        tester.stop_audio = MagicMock()
        tester.cleanup_audio = MagicMock()

        # Simulate user actions: track1 -> replay once, then next; track2 -> next
        simulated_actions = iter(["replay", "next", "next"])
        tester.prompt_user_action = lambda: next(simulated_actions)

        tester.run()

        # Both tracks should now be completed
        self.assertEqual(tester.completed_files, {"track1.wav", "track2.wav"})
        self.assertTrue((self.test_dir / SESSION_FILENAME).exists())


if __name__ == "__main__":
    unittest.main()
