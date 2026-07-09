import json
import tempfile
import unittest
import wave
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from flow_features import (
    HistoryStore,
    apply_vocabulary,
    apply_spoken_correction,
    choose_profile,
    polish_text,
    read_wav,
    transform_selected_text,
    write_wav,
)


class TextFeatureTests(unittest.TestCase):
    def test_spoken_correction_drops_previous_clause(self):
        self.assertEqual(
            apply_spoken_correction("Meet at four, no wait actually five"),
            "five",
        )

    def test_polish_formats_bullets(self):
        self.assertEqual(
            polish_text("bullet apples bullet bread bullet milk", "notes"),
            "- Apples\n- Bread\n- Milk",
        )

    def test_email_profile_spaces_greeting_and_signoff(self):
        self.assertEqual(
            polish_text("hi Sam, the build is ready. thanks, Kariim", "email"),
            "Hi Sam,\n\nThe build is ready.\n\nThanks,\nKariim",
        )

    def test_messages_profile_removes_trailing_period(self):
        self.assertEqual(polish_text("This is ready.", "messages"), "This is ready")

    def test_selected_text_transform_is_safe_for_unknown_command(self):
        self.assertIsNone(transform_selected_text("Keep me", "translate to Klingon"))

    def test_selected_text_replacement(self):
        self.assertEqual(
            transform_selected_text("Meet Tuesday", "replace Tuesday with Wednesday"),
            "Meet Wednesday",
        )

    def test_profile_detection(self):
        self.assertEqual(choose_profile("OUTLOOK.EXE"), "email")
        self.assertEqual(choose_profile("Code.exe"), "coding")

    def test_vocabulary_restores_saved_casing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "vocabulary.txt"
            path.write_text("Flow State\nGraphQL\n", encoding="utf-8")
            self.assertEqual(
                apply_vocabulary("flow state uses graphql", path),
                "Flow State uses GraphQL",
            )


class AudioFeatureTests(unittest.TestCase):
    def test_wav_round_trip_and_resample(self):
        with tempfile.TemporaryDirectory() as temp:
            source = np.sin(np.linspace(0, np.pi * 4, 8000)).astype(np.float32) * 0.5
            path = write_wav(Path(temp) / "sample.wav", source, 8000)
            loaded = read_wav(path, 16000)
            self.assertGreaterEqual(len(loaded), 15998)
            self.assertLessEqual(len(loaded), 16002)
            self.assertLess(float(np.max(np.abs(loaded))), 0.51)

    def test_rejects_non_pcm16_wav(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.wav"
            with wave.open(str(path), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(1)
                out.setframerate(16000)
                out.writeframes(b"\x80" * 32)
            with self.assertRaises(ValueError):
                read_wav(path)


class HistoryStoreTests(unittest.TestCase):
    def test_history_round_trip_with_audio_and_stats(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(temp)
            record = store.add(
                original="hello world",
                final="Hello world.",
                duration=2,
                latency=0.4,
                engine="test",
                profile="default",
                audio=np.zeros(32000, dtype=np.float32),
            )
            self.assertTrue(Path(record["audio_path"]).exists())
            self.assertEqual(store.find(record["id"])["final"], "Hello world.")
            self.assertEqual(store.stats()["words"], 2)

    def test_delete_never_unlinks_audio_outside_recordings(self):
        """BITE-PROOF: removing _safe_audio_path containment unlinks outside.wav."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside.wav"
            outside.write_bytes(b"keep")
            store = HistoryStore(root / "data")
            store.path.parent.mkdir(parents=True)
            record = {
                "id": "unsafe",
                "timestamp": datetime.now().isoformat(),
                "final": "text",
                "audio_path": str(outside),
            }
            store.path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            self.assertTrue(store.delete("unsafe"))
            self.assertTrue(outside.exists())

    def test_prune_removes_old_record_and_owned_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(temp)
            old = store.add(
                original="old",
                final="old",
                audio=np.zeros(160, dtype=np.float32),
            )
            records = store.read()
            records[0]["timestamp"] = (datetime.now() - timedelta(days=40)).isoformat()
            store.rewrite(records)
            self.assertEqual(store.prune(30), 1)
            self.assertFalse(Path(old["audio_path"]).exists())


if __name__ == "__main__":
    unittest.main()
