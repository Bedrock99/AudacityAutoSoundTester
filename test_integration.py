import json
import math
import os
import shutil
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent))

from audacity_auto_sound_tester import (
    DEFAULT_AUDACITY_PATH,
    SESSION_FILENAME,
    SoundTester,
)


def create_test_wav(path: Path, duration_sec: float = 0.05, freq: float = 440.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    framerate = 44100
    nframes = int(framerate * duration_sec)
    with wave.open(str(path), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(framerate)
        for i in range(nframes):
            val = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * freq * i / framerate))
            f.writeframes(struct.pack("<h", val))


class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="sound_tester_e2e_"))
        self.wav1 = self.temp_dir / "folder_a" / "sound1.wav"
        self.wav2 = self.temp_dir / "folder_b" / "sound2.wav"
        self.wav3 = self.temp_dir / "folder_c" / "sound3.wav"

        create_test_wav(self.wav1, freq=300)
        create_test_wav(self.wav2, freq=500)
        create_test_wav(self.wav3, freq=700)

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_session_lifecycle(self):
        # 1. Run tester, approve first file, then quit at second file
        tester1 = SoundTester(base_dir=self.temp_dir, audacity_path=DEFAULT_AUDACITY_PATH)
        actions1 = iter(["next", "quit"])
        tester1.prompt_user_action = lambda: next(actions1)
        tester1.run()

        session_path = self.temp_dir / SESSION_FILENAME
        self.assertTrue(session_path.exists())

        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["completed_files"], ["folder_a/sound1.wav"])
            self.assertEqual(data["completed_count"], 1)
            self.assertEqual(data["total_files"], 3)

        # 2. Run tester again to resume; it should skip folder_a/sound1.wav and process sound2 and sound3
        tester2 = SoundTester(base_dir=self.temp_dir, audacity_path=DEFAULT_AUDACITY_PATH)
        actions2 = iter(["next", "next"])
        tester2.prompt_user_action = lambda: next(actions2)
        tester2.run()

        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(
                data["completed_files"],
                ["folder_a/sound1.wav", "folder_b/sound2.wav", "folder_c/sound3.wav"],
            )
            self.assertEqual(data["completed_count"], 3)

        # 3. Run tester again when all files are completed
        tester3 = SoundTester(base_dir=self.temp_dir, audacity_path=DEFAULT_AUDACITY_PATH)
        # Should finish immediately without requesting any user action
        tester3.prompt_user_action = MagicMock()
        tester3.run()
        tester3.prompt_user_action.assert_not_called()

        # 4. Run tester with --reset
        tester4 = SoundTester(base_dir=self.temp_dir, audacity_path=DEFAULT_AUDACITY_PATH, reset=True)
        actions4 = iter(["next", "quit"])
        tester4.prompt_user_action = lambda: next(actions4)
        tester4.run()

        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["completed_files"], ["folder_a/sound1.wav"])
            self.assertEqual(data["completed_count"], 1)


if __name__ == "__main__":
    unittest.main()
