import json
import tempfile
import threading
import unittest
import wave
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from flow_features import (
    CorrectionStore,
    DeliveryQueue,
    HistoryStore,
    RecoveryJournal,
    apply_vocabulary,
    apply_spoken_correction,
    choose_profile,
    extract_correction_pairs,
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

    def test_correction_save_cannot_race_a_new_history_append(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(temp)
            original = store.add(original="old", final="old")
            entered = threading.Event()
            release = threading.Event()
            append_done = threading.Event()
            real_read = store._read_unlocked

            def paused_read(strict=False):
                records = real_read(strict)
                if strict:
                    entered.set()
                    release.wait(2)
                return records

            store._read_unlocked = paused_read
            correction = threading.Thread(
                target=store.save_correction,
                args=(original["id"], "corrected"),
            )
            correction.start()
            self.assertTrue(entered.wait(1))

            def append():
                store.add(original="new", final="new")
                append_done.set()

            writer = threading.Thread(target=append)
            writer.start()
            append_was_blocked = not append_done.wait(0.05)
            release.set()
            correction.join(2)
            writer.join(2)
            self.assertTrue(append_was_blocked)
            self.assertFalse(correction.is_alive())
            self.assertFalse(writer.is_alive())
            records = store.read()
            self.assertEqual({record["final"] for record in records}, {"old", "new"})
            self.assertEqual(store.find(original["id"])["corrected"], "corrected")

    def test_correction_save_refuses_to_drop_malformed_history(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(temp)
            saved = store.add(original="keep", final="keep")
            with open(store.path, "a", encoding="utf-8") as out:
                out.write("not json\n")
            original_bytes = store.path.read_bytes()
            with self.assertRaisesRegex(ValueError, "original file kept"):
                store.save_correction(saved["id"], "corrected")
            self.assertEqual(store.path.read_bytes(), original_bytes)
    def test_delete_never_unlinks_audio_outside_recordings(self):
        """BITE-PROOF: removing _safe_audio_path containment unlinks outside.wav."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside.wav"
            outside.write_bytes(b"keep")
            store = HistoryStore(root / "data")
            store.path.parent.mkdir(parents=True, exist_ok=True)
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


class CorrectionLearningTests(unittest.TestCase):
    def test_extracts_only_small_replacements_inside_inserted_range(self):
        before = "Old note. floor state ships today. Unrelated tail."
        after = "Rewritten note. Flow State ships today. Different tail."
        start = before.index("floor state")
        end = start + len("floor state ships today.")
        self.assertEqual(
            extract_correction_pairs(before, after, start, end),
            [("floor state", "Flow State")],
        )
        crossing_before = "memo floor state"
        crossing_after = "note Flow State"
        trusted_start = crossing_before.index("floor state")
        self.assertEqual(
            extract_correction_pairs(
                crossing_before,
                crossing_after,
                trusted_start,
                len(crossing_before),
            ),
            [],
        )

    def test_pending_pair_cannot_change_text_until_approved(self):
        """BITE-PROOF: removing approved-only filtering makes the first assertion fail."""
        with tempfile.TemporaryDirectory() as temp:
            store = CorrectionStore(temp)
            item = store.observe("floor state", "Flow State", source_id="history-1")
            self.assertEqual(store.apply("open floor state"), "open floor state")
            self.assertTrue(store.set_status(item["id"], "approved"))
            self.assertEqual(store.apply("open floor state"), "open Flow State")
            self.assertEqual(store.hotwords(), "Flow State")

    def test_unicode_case_variant_outside_rule_does_not_crash(self):
        with tempfile.TemporaryDirectory() as temp:
            store = CorrectionStore(temp)
            item = store.observe("i", "eye")
            store.set_status(item["id"], "approved")
            self.assertEqual(store.apply("i ı"), "eye ı")

    def test_repeated_source_does_not_inflate_match_count(self):
        with tempfile.TemporaryDirectory() as temp:
            store = CorrectionStore(temp)
            first = store.observe("pair a key", "Parakeet", source_id="watch-1")
            repeated = store.observe("pair a key", "Parakeet", source_id="watch-1")
            second = store.observe("pair a key", "Parakeet", source_id="history-2")
            self.assertEqual(first["matches"], 1)
            self.assertEqual(repeated["matches"], 1)
            self.assertEqual(second["matches"], 2)

    def test_corrupt_store_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            store = CorrectionStore(temp)
            store.path.parent.mkdir(parents=True, exist_ok=True)
            store.path.write_text("not json", encoding="utf-8")
            self.assertEqual(store.read(), [])
            self.assertEqual(store.apply("floor state"), "floor state")
            with self.assertRaisesRegex(ValueError, "original file kept"):
                store.observe("floor state", "Flow State")
            self.assertEqual(store.path.read_text(encoding="utf-8"), "not json")

    def test_approved_rules_do_not_cascade(self):
        with tempfile.TemporaryDirectory() as temp:
            store = CorrectionStore(temp)
            alpha = store.observe("alpha", "beta")
            beta = store.observe("beta", "gamma")
            store.set_status(alpha["id"], "approved")
            store.set_status(beta["id"], "approved")
            self.assertEqual(store.apply("alpha beta"), "beta gamma")
    def test_clear_removes_only_correction_memory(self):
        with tempfile.TemporaryDirectory() as temp:
            store = CorrectionStore(temp)
            store.observe("floor state", "Flow State")
            store.observe("pair a key", "Parakeet")
            self.assertEqual(store.clear(), 2)
            self.assertEqual(store.read(), [])
    def test_history_correction_preserves_delivered_and_original_text(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(temp)
            saved = store.add(original="floor state", final="Floor state.")
            corrected = store.save_correction(saved["id"], "Flow State.")
            self.assertEqual(corrected["original"], "floor state")
            self.assertEqual(corrected["final"], "Floor state.")
            self.assertEqual(corrected["corrected"], "Flow State.")
            self.assertTrue(corrected["corrected_at"])

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

    def test_complete_cannot_drop_a_concurrent_append(self):
        with tempfile.TemporaryDirectory() as temp:
            queue = DeliveryQueue(temp)
            original = queue.add("First")
            entered = threading.Event()
            release = threading.Event()
            append_done = threading.Event()
            real_read = queue.read

            def paused_read():
                records = real_read()
                entered.set()
                release.wait(2)
                return records

            queue.read = paused_read
            cleanup = threading.Thread(
                target=queue.complete,
                args=(original["id"],),
            )
            cleanup.start()
            self.assertTrue(entered.wait(1))

            def append():
                queue.add("Second")
                append_done.set()

            writer = threading.Thread(target=append)
            writer.start()
            append_was_blocked = not append_done.wait(0.05)
            release.set()
            cleanup.join(2)
            writer.join(2)
            self.assertTrue(append_was_blocked)
            self.assertFalse(cleanup.is_alive())
            self.assertFalse(writer.is_alive())
            self.assertEqual(
                [record["text"] for record in queue.read()],
                ["Second"],
            )

    def test_invalid_id_cannot_change_delivery_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            queue = DeliveryQueue(temp)
            record = queue.add("Keep me")

            self.assertFalse(queue.complete("../../outside"))
            self.assertEqual(queue.read(), [record])


if __name__ == "__main__":
    unittest.main()
