import json
import tempfile
import unittest
import wave
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from flow_features import (
    DeliveryQueue,
    HistoryStore,
    RecoveryJournal,
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
    def test_reliability_stats_report_delivery_percentiles_and_cutoffs(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(temp)
            for index, latency in enumerate((0.2, 0.4, 0.8, 1.6)):
                store.add(
                    original="test",
                    final="Test",
                    duration=45 if index == 3 else 3,
                    delivery_latency=latency,
                    source="dictation",
                )
            store.add(
                original="recovered",
                final="Recovered",
                source="recovery",
            )
            stats = store.stats(max_record=45)
            self.assertEqual(stats["median_delivery_latency"], 0.6)
            self.assertEqual(stats["p95_delivery_latency"], 1.6)
            self.assertEqual(stats["cutoff_warnings"], 1)
            self.assertEqual(stats["recovered_sessions"], 1)

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


class RecoveryJournalTests(unittest.TestCase):
    def test_partial_text_survives_as_an_orphan_session(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = RecoveryJournal(temp)
            session_id = journal.begin(profile="notes", source="dictation")
            journal.append(session_id, "First recovered segment")
            journal.append(session_id, "second segment")

            self.assertEqual(
                journal.orphans(),
                [{
                    "id": session_id,
                    "started": journal.orphans()[0]["started"],
                    "profile": "notes",
                    "source": "dictation",
                    "text": "First recovered segment second segment",
                    "segments": 2,
                    "audio_path": "",
                }],
            )

    def test_attached_audio_is_listed_and_removed_with_owned_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = RecoveryJournal(temp)
            session_id = journal.begin(profile="notes")
            audio_path = journal.attach_audio(
                session_id,
                np.zeros(1600, dtype=np.float32),
                sample_rate=16000,
            )

            self.assertTrue(Path(audio_path).exists())
            self.assertEqual(journal.orphans()[0]["audio_path"], audio_path)
            self.assertTrue(journal.complete(session_id))
            self.assertFalse(Path(audio_path).exists())

    def test_complete_removes_owned_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = RecoveryJournal(temp)
            session_id = journal.begin()
            journal.append(session_id, "done")
            self.assertTrue(journal.complete(session_id))
            self.assertEqual(journal.orphans(), [])

    def test_complete_never_deletes_outside_recovery_directory(self):
        """BITE-PROOF: removing session-id validation unlinks outside.jsonl."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside.jsonl"
            outside.write_text("keep", encoding="utf-8")
            journal = RecoveryJournal(root / "data")

            self.assertFalse(journal.complete("../../outside"))
            self.assertTrue(outside.exists())


class DeliveryQueueTests(unittest.TestCase):
    def test_failed_delivery_round_trip_and_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            queue = DeliveryQueue(temp)
            record = queue.add(
                "Protected text",
                target={"process": "notepad.exe", "title": "Notes", "hwnd": 42},
                profile="notes",
                source="dictation",
                reason="paste blocked",
            )

            self.assertEqual(queue.read(), [record])
            self.assertEqual(record["target"]["process"], "notepad.exe")
            self.assertTrue(queue.complete(record["id"]))
            self.assertEqual(queue.read(), [])

    def test_invalid_id_cannot_change_delivery_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            queue = DeliveryQueue(temp)
            record = queue.add("Keep me")

            self.assertFalse(queue.complete("../../outside"))
            self.assertEqual(queue.read(), [record])


if __name__ == "__main__":
    unittest.main()
