import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

import benchmark_flow
import flow
import flow_hub


class ImmediateThread:
    def __init__(self, *, target, daemon):
        self.target = target

    def start(self):
        self.target()


class DeliveryTests(unittest.TestCase):
    def test_reprocess_lab_builds_five_previews_without_mutating_settings(self):
        original_settings = (flow.VERBATIM, flow.POLISH, flow.PROFILE)
        raw = "um hello team comma first reliability second faster delivery"
        with mock.patch.object(flow, "log_history") as history:
            previews = flow.reprocess_previews(raw)
        self.assertEqual(
            list(previews), ["Verbatim", "Light", "Notes", "Email", "Coding"]
        )
        self.assertIn("um hello team", previews["Verbatim"].lower())
        self.assertNotIn("um ", previews["Light"].lower())
        self.assertEqual((flow.VERBATIM, flow.POLISH, flow.PROFILE), original_settings)
        history.assert_not_called()

    def test_bounded_watcher_queues_only_inserted_replacement(self):
        before = "Notes: floor state "
        after = "Notes: Flow State "
        snapshots = iter([
            {
                "window": 42,
                "control": 7,
                "text": before,
                "selection_start": len(before),
                "selection_end": len(before),
            },
            {
                "window": 42,
                "control": 7,
                "text": after,
                "selection_start": len(after),
                "selection_end": len(after),
            },
        ])
        with (
            mock.patch.object(flow.CORRECTIONS, "observe", return_value={
                "id": "pair-1", "status": "pending", "matches": 2,
            }) as observe,
            mock.patch.object(flow.CORRECTIONS, "set_status") as set_status,
            mock.patch.object(flow, "CORRECTION_MODE", "after_2_matches"),
            mock.patch.object(flow, "ui_events") as events,
        ):
            pairs = flow.watch_inserted_correction(
                "floor state ",
                {"hwnd": 42},
                snapshot_reader=lambda: next(snapshots),
                sleep=lambda _delay: None,
                timeout=1,
            )
        self.assertEqual(pairs, [("floor state", "Flow State")])
        observe.assert_called_once()
        set_status.assert_not_called()
        events.put.assert_called_once_with(("accuracy_changed", "Correction ready in Accuracy"))

    def test_repeat_mode_hides_first_observation_without_notification(self):
        before = "Notes: floor state "
        after = "Notes: Flow State "
        snapshots = iter([
            {
                "window": 42,
                "control": 7,
                "text": before,
                "selection_start": len(before),
                "selection_end": len(before),
            },
            {
                "window": 42,
                "control": 7,
                "text": after,
                "selection_start": len(after),
                "selection_end": len(after),
            },
        ])
        with (
            mock.patch.object(flow.CORRECTIONS, "observe", return_value={
                "id": "pair-1", "status": "pending", "matches": 1,
            }),
            mock.patch.object(flow, "CORRECTION_MODE", "after_2_matches"),
            mock.patch.object(flow, "ui_events") as events,
        ):
            pairs = flow.watch_inserted_correction(
                "floor state ",
                {"hwnd": 42},
                snapshot_reader=lambda: next(snapshots),
                sleep=lambda _delay: None,
                timeout=1,
            )
        self.assertEqual(pairs, [("floor state", "Flow State")])
        events.put.assert_not_called()

    def test_oversized_observation_is_ignored_without_crashing(self):
        before = "Notes: floor state "
        after = "Notes: Flow State "
        snapshots = iter([
            {
                "window": 42,
                "control": 7,
                "text": before,
                "selection_start": len(before),
                "selection_end": len(before),
            },
            {
                "window": 42,
                "control": 7,
                "text": after,
                "selection_start": len(after),
                "selection_end": len(after),
            },
        ])
        with (
            mock.patch.object(flow.CORRECTIONS, "observe", return_value=None),
            mock.patch.object(flow, "CORRECTION_MODE", "after_2_matches"),
            mock.patch.object(flow, "ui_events") as events,
        ):
            pairs = flow.watch_inserted_correction(
                "floor state ",
                {"hwnd": 42},
                snapshot_reader=lambda: next(snapshots),
                sleep=lambda _delay: None,
                timeout=1,
            )
        self.assertEqual(pairs, [("floor state", "Flow State")])
        events.put.assert_not_called()

    def test_watcher_storage_failure_is_visible_and_contained(self):
        with (
            mock.patch.object(
                flow,
                "watch_inserted_correction",
                side_effect=OSError("disk full"),
            ),
            mock.patch.object(flow, "ui_events") as events,
        ):
            flow._correction_watch_worker("floor state ", {"hwnd": 42})
        events.put.assert_called_once_with((
            "notice", "Correction was detected but could not be saved"
        ))

    def test_accuracy_event_refreshes_open_hub_badge(self):
        overlay = object.__new__(flow.Overlay)
        overlay.root = mock.Mock()
        overlay._show_partial = mock.Mock()
        overlay._show = mock.Mock()
        overlay._hide_partial = mock.Mock()
        overlay.hub = SimpleNamespace(
            top=SimpleNamespace(winfo_exists=lambda: True),
            _update_accuracy_badge=mock.Mock(),
        )
        events = flow.queue.Queue()
        events.put(("accuracy_changed", "Correction ready in Accuracy"))
        with mock.patch.object(flow, "ui_events", events):
            overlay._poll()
        overlay.hub._update_accuracy_badge.assert_called_once_with()
        overlay._show_partial.assert_called_once_with(
            "Correction ready in Accuracy", 2600
        )
    def test_watcher_stops_when_the_focused_control_changes(self):
        before = "floor state "
        snapshots = iter([
            {
                "window": 42,
                "control": 7,
                "text": before,
                "selection_start": len(before),
                "selection_end": len(before),
            },
            {
                "window": 42,
                "control": 8,
                "text": "Flow State ",
                "selection_start": 11,
                "selection_end": 11,
            },
        ])
        with mock.patch.object(flow.CORRECTIONS, "observe") as observe:
            pairs = flow.watch_inserted_correction(
                before,
                {"hwnd": 42},
                snapshot_reader=lambda: next(snapshots),
                sleep=lambda _delay: None,
                timeout=1,
            )
        self.assertEqual(pairs, [])
        observe.assert_not_called()

    def test_whisper_receives_only_approved_replacement_terms_as_hotwords(self):
        engine = object.__new__(flow.WhisperEngine)
        engine.model = mock.Mock()
        engine.model.transcribe.return_value = (
            [SimpleNamespace(text=" Flow State is ready ")],
            None,
        )
        with mock.patch.object(flow.CORRECTIONS, "hotwords", return_value="Flow State"):
            self.assertEqual(engine.transcribe(np.zeros(160, dtype=np.float32)), "Flow State is ready")
        self.assertEqual(
            engine.model.transcribe.call_args.kwargs["hotwords"],
            "Flow State",
        )

    def test_scoped_undo_and_redo_require_same_untouched_target(self):
        target = {"hwnd": 42, "process": "notepad.exe", "title": "Notes"}
        original = (flow.last_insertion, flow.keyboard_generation)
        try:
            flow.last_insertion = {
                "text": "Exact text ",
                "target": target,
                "keyboard_generation": 7,
                "undone": False,
            }
            flow.keyboard_generation = 7
            with (
                mock.patch.object(flow, "active_window_info", return_value=target),
                mock.patch.object(flow.keyboard, "send") as send,
                mock.patch.object(flow, "inject") as inject,
                mock.patch.object(flow, "wait_for_modifiers_released"),
            ):
                self.assertTrue(flow.undo_last_insertion())
                send.assert_called_once_with("ctrl+z")
                self.assertTrue(flow.redo_last_insertion())
                inject.assert_called_once_with("Exact text ", trailing_space=False)

            flow.last_insertion["undone"] = False
            flow.last_insertion["keyboard_generation"] = 7
            flow.keyboard_generation = 8
            with (
                mock.patch.object(flow, "active_window_info", return_value=target),
                mock.patch.object(flow.keyboard, "send") as send,
            ):
                self.assertFalse(flow.undo_last_insertion())
                send.assert_not_called()

            flow.keyboard_generation = 7
            with (
                mock.patch.object(
                    flow,
                    "active_window_info",
                    return_value={"hwnd": 99, "process": "notepad.exe", "title": "Notes"},
                ),
                mock.patch.object(flow.keyboard, "send") as send,
            ):
                self.assertFalse(flow.undo_last_insertion())
                send.assert_not_called()
        finally:
            flow.last_insertion, flow.keyboard_generation = original

    def test_successful_delivery_records_exact_inserted_payload(self):
        target = {"hwnd": 42, "process": "notepad.exe", "title": "Notes"}
        original = (
            flow.last_insertion,
            flow.keyboard_generation,
            flow.delivery_keyboard_generation,
        )
        try:
            flow.last_insertion = None
            flow.keyboard_generation = 11
            flow.delivery_keyboard_generation = 11
            with (
                mock.patch.object(flow, "active_window_info", return_value=target),
                mock.patch.object(flow, "inject"),
                mock.patch.object(flow, "log_history", return_value={"id": "saved"}),
            ):
                flow.deliver_text("Hello", target=target, source="dictation")
            self.assertEqual(flow.last_insertion["text"], "Hello ")
            self.assertEqual(flow.last_insertion["target"], target)
            self.assertEqual(flow.last_insertion["keyboard_generation"], 11)
            self.assertFalse(flow.last_insertion["undone"])
        finally:
            (
                flow.last_insertion,
                flow.keyboard_generation,
                flow.delivery_keyboard_generation,
            ) = original

    def test_delivery_retry_becomes_latest_scoped_insertion(self):
        target = {"hwnd": 42, "process": "notepad.exe", "title": "Notes"}
        original = (flow.last_insertion, flow.keyboard_generation)
        try:
            flow.last_insertion = None
            flow.keyboard_generation = 4
            with (
                mock.patch.object(flow, "focus_delivery_target", return_value=True),
                mock.patch.object(flow, "active_window_info", return_value=target),
                mock.patch.object(flow, "inject"),
                mock.patch.object(flow, "log_history"),
            ):
                self.assertTrue(flow.retry_queued_delivery({
                    "text": "Recovered exactly",
                    "target": target,
                    "profile": "notes",
                }))
            self.assertEqual(flow.last_insertion["text"], "Recovered exactly")
            self.assertEqual(flow.last_insertion["target"], target)
        finally:
            flow.last_insertion, flow.keyboard_generation = original

    def test_keyboard_activity_counts_only_after_recording_stops(self):
        original = (flow.recording, flow.keyboard_generation)
        try:
            flow.keyboard_generation = 0
            flow.recording = True
            flow.note_keyboard_activity(SimpleNamespace(event_type="down"))
            self.assertEqual(flow.keyboard_generation, 0)
            flow.recording = False
            flow.note_keyboard_activity(SimpleNamespace(event_type="up"))
            self.assertEqual(flow.keyboard_generation, 0)
            flow.note_keyboard_activity(SimpleNamespace(event_type="down"))
            self.assertEqual(flow.keyboard_generation, 1)
        finally:
            flow.recording, flow.keyboard_generation = original

    def test_flow_hotkeys_and_synthetic_keys_do_not_count_as_user_takeover(self):
        original = (flow.recording, flow.keyboard_generation, flow.synthetic_keyboard)
        try:
            flow.recording = False
            flow.keyboard_generation = 0
            flow.note_keyboard_activity(SimpleNamespace(event_type="down", name="ctrl"))
            self.assertEqual(flow.keyboard_generation, 0)
            with mock.patch.object(flow.keyboard, "is_pressed", return_value=True):
                flow.note_keyboard_activity(SimpleNamespace(event_type="down", name="z"))
            self.assertEqual(flow.keyboard_generation, 0)
            flow.synthetic_keyboard = True
            flow.note_keyboard_activity(SimpleNamespace(event_type="down", name="x"))
            self.assertEqual(flow.keyboard_generation, 0)
            flow.synthetic_keyboard = False
            with mock.patch.object(flow.keyboard, "is_pressed", return_value=False):
                flow.note_keyboard_activity(SimpleNamespace(event_type="down", name="x"))
            self.assertEqual(flow.keyboard_generation, 1)
        finally:
            flow.recording, flow.keyboard_generation, flow.synthetic_keyboard = original

    def test_register_hotkeys_installs_typing_collision_hook(self):
        with (
            mock.patch.object(flow.keyboard, "add_hotkey") as add_hotkey,
            mock.patch.object(flow.keyboard, "on_release_key"),
            mock.patch.object(flow.keyboard, "hook") as hook,
        ):
            flow.register_hotkeys()
        hook.assert_called_once_with(flow.note_keyboard_activity)
        self.assertIn(
            mock.call(flow.PAUSE_HOTKEY, flow.toggle_pause),
            add_hotkey.call_args_list,
        )
        self.assertIn(
            mock.call(flow.UNDO_HOTKEY, flow.undo_last_insertion),
            add_hotkey.call_args_list,
        )
        self.assertIn(
            mock.call(flow.REDO_HOTKEY, flow.redo_last_insertion),
            add_hotkey.call_args_list,
        )

    def test_voice_control_routes_exact_undo_and_redo_commands(self):
        with mock.patch.object(flow, "undo_last_insertion", return_value=True) as undo:
            self.assertTrue(flow.run_voice_control("undo that"))
        undo.assert_called_once_with()
        with mock.patch.object(flow, "redo_last_insertion", return_value=True) as redo:
            self.assertTrue(flow.run_voice_control("redo"))
        redo.assert_called_once_with()
        self.assertIsNone(flow.run_voice_control("make this shorter"))

    def test_command_hotkey_without_selection_starts_voice_control(self):
        original = (flow.command_mode, flow.command_selection, flow.recording)
        try:
            flow.command_mode = False
            flow.command_selection = "stale"
            flow.recording = False
            with (
                mock.patch.object(flow, "capture_selected_text", return_value=""),
                mock.patch.object(flow, "start_recording") as start,
                mock.patch.object(flow, "ui_events") as events,
            ):
                flow.toggle_command_mode()
            self.assertTrue(flow.command_mode)
            self.assertEqual(flow.command_selection, "")
            start.assert_called_once_with()
            events.put.assert_called_once_with(
                ("notice", "Say undo or redo; press again to apply")
            )
        finally:
            flow.command_mode, flow.command_selection, flow.recording = original

    def test_continuous_live_delivery_skips_per_piece_history(self):
        with (
            mock.patch.object(flow, "inject") as inject,
            mock.patch.object(flow, "log_history") as history,
        ):
            result = flow.deliver_text(
                "Live piece", persist_history=False, source="continuous"
            )
        self.assertEqual(result, {"delivered": True})
        inject.assert_called_once_with("Live piece", trailing_space=True)
        history.assert_not_called()

    def test_active_window_identity_always_returns_structured_target(self):
        target = {"hwnd": 42, "process": "notepad.exe", "title": "Notes"}
        with (
            mock.patch.object(flow.ctypes.windll.user32, "GetForegroundWindow", return_value=42),
            mock.patch.object(flow, "window_info", return_value=target),
        ):
            self.assertEqual(flow.active_window_info(), target)

    def test_delivery_target_requires_same_process_and_compatible_title(self):
        saved = {"process": "notepad.exe", "title": "Launch notes - Notepad"}
        self.assertTrue(flow.delivery_target_matches(
            saved,
            {"process": "NOTEPAD.EXE", "title": "*Launch notes - Notepad"},
        ))
        self.assertFalse(flow.delivery_target_matches(
            saved,
            {"process": "notepad.exe", "title": "Private notes - Notepad"},
        ))
        self.assertFalse(flow.delivery_target_matches(
            saved,
            {"process": "outlook.exe", "title": "Launch notes - Notepad"},
        ))

    def test_import_does_not_eagerly_load_audio_backend(self):
        self.assertNotIn("sounddevice", sys.modules)

    def test_overlay_event_poll_ceiling_is_25ms(self):
        self.assertLessEqual(flow.Overlay.POLL_MS, 25)

    def test_overlay_partial_text_fits_one_measured_line(self):
        overlay = flow.Overlay.__new__(flow.Overlay)
        overlay.partial_font = mock.Mock()
        overlay.partial_font.measure.side_effect = lambda value: len(value) * 8
        overlay.partial_max_width = 80

        fitted = overlay._fit_partial_text(
            "Flow State keeps every word safe and ready."
        )

        self.assertTrue(fitted.startswith("..."))
        self.assertLessEqual(overlay.partial_font.measure(fitted), 80)
        self.assertNotIn("\n", fitted)

    def test_delivery_precedes_history_and_survives_history_failure(self):
        calls = []

        def inject(text, trailing_space=True):
            calls.append(("inject", text, trailing_space))

        def fail_history(*_args, **_kwargs):
            calls.append(("history",))
            raise OSError("disk unavailable")

        with (
            mock.patch.object(flow, "inject", side_effect=inject),
            mock.patch.object(flow, "log_history", side_effect=fail_history),
            mock.patch.object(flow.CORRECTIONS, "set_status") as set_status,
            mock.patch.object(flow, "CORRECTION_MODE", "after_2_matches"),
            mock.patch.object(flow, "ui_events") as events,
        ):
            flow.deliver_text("Hello", trailing_space=False, source="test")

        self.assertEqual(calls[0], ("inject", "Hello", False))
        self.assertEqual(calls[1], ("history",))
        events.put.assert_called_once_with(("notice", "Text inserted; history save failed"))

    def test_delivery_records_actual_stop_to_insert_time(self):
        with (
            mock.patch.object(flow, "inject", return_value=105.25),
            mock.patch.object(flow, "log_history", return_value={"id": "saved"}) as history,
            mock.patch.object(flow, "active_window_info", return_value={}),
        ):
            flow.deliver_text(
                "Hello", delivery_started=100.0, source="dictation"
            )
        self.assertEqual(history.call_args.kwargs["delivery_latency"], 5.25)

    def test_insertion_exception_durably_queues_text_and_still_saves_history(self):
        target = {"hwnd": 42, "process": "notepad.exe", "title": "Notes"}
        queue = mock.Mock()
        history_record = {"id": "saved"}
        with (
            mock.patch.object(flow, "inject", side_effect=OSError("blocked")),
            mock.patch.object(flow, "active_window_info", return_value=target),
            mock.patch.object(flow, "DELIVERY", queue),
            mock.patch.object(flow, "log_history", return_value=history_record) as history,
            mock.patch.object(flow.CORRECTIONS, "set_status") as set_status,
            mock.patch.object(flow, "CORRECTION_MODE", "after_2_matches"),
            mock.patch.object(flow, "ui_events") as events,
        ):
            result = flow.deliver_text(
                "Protected text",
                trailing_space=False,
                target=target,
                profile="notes",
                source="dictation",
            )

        self.assertEqual(result, history_record)
        queue.add.assert_called_once_with(
            "Protected text",
            target=target,
            profile="notes",
            source="dictation",
            reason="OSError: blocked",
        )
        history.assert_called_once_with(
            "Protected text", profile="notes", source="dictation"
        )
        events.put.assert_called_once_with(("notice", "Text protected in Delivery queue"))

    def test_queue_write_failure_keeps_crash_recovery_even_if_history_saves(self):
        queue = mock.Mock()
        queue.add.side_effect = OSError("disk locked")
        with (
            mock.patch.object(flow, "inject", side_effect=OSError("blocked")),
            mock.patch.object(
                flow, "active_window_info",
                return_value={"hwnd": 7, "process": "notepad.exe", "title": ""},
            ),
            mock.patch.object(flow, "DELIVERY", queue),
            mock.patch.object(flow, "log_history", return_value={"id": "saved"}),
            mock.patch.object(flow, "ui_events"),
        ):
            result = flow.deliver_text(
                "Protected text",
                target={"process": "notepad.exe"},
                source="dictation",
            )

        self.assertIsNone(result)

    def test_focus_lock_holds_text_when_destination_changes(self):
        target = {"hwnd": 42, "process": "notepad.exe", "title": "Launch notes"}
        current = {"hwnd": 77, "process": "outlook.exe", "title": "Inbox"}
        queue = mock.Mock()
        history_record = {"id": "saved"}
        with (
            mock.patch.object(flow, "active_window_info", return_value=current),
            mock.patch.object(flow, "inject") as inject,
            mock.patch.object(flow, "DELIVERY", queue),
            mock.patch.object(flow, "log_history", return_value=history_record),
            mock.patch.object(flow, "ui_events"),
        ):
            result = flow.deliver_text(
                "Do not misdirect me",
                target=target,
                profile="notes",
                source="dictation",
            )

        self.assertEqual(result, history_record)
        inject.assert_not_called()
        queue.add.assert_called_once_with(
            "Do not misdirect me",
            target=target,
            profile="notes",
            source="dictation",
            reason="Destination changed before insertion",
        )

    def test_focus_lock_allows_compatible_original_window(self):
        target = {"hwnd": 42, "process": "notepad.exe", "title": "Launch notes"}
        current = {"hwnd": 42, "process": "NOTEPAD.EXE", "title": "*Launch notes"}
        with (
            mock.patch.object(flow, "active_window_info", return_value=current),
            mock.patch.object(flow, "inject") as inject,
            mock.patch.object(flow, "log_history", return_value={"id": "saved"}),
            mock.patch.object(flow, "DELIVERY") as queue,
        ):
            result = flow.deliver_text("Deliver me", target=target)

        self.assertEqual(result, {"id": "saved"})
        inject.assert_called_once_with("Deliver me", trailing_space=True)
        queue.add.assert_not_called()

    def test_typing_collision_holds_text_before_injection(self):
        original = (flow.keyboard_generation, flow.delivery_keyboard_generation)
        target = {"hwnd": 42, "process": "notepad.exe", "title": "Launch notes"}
        queue = mock.Mock()
        try:
            flow.delivery_keyboard_generation = 10
            flow.keyboard_generation = 11
            with (
                mock.patch.object(flow, "active_window_info", return_value=target),
                mock.patch.object(flow, "inject") as inject,
                mock.patch.object(flow, "DELIVERY", queue),
                mock.patch.object(flow, "log_history", return_value={"id": "saved"}),
                mock.patch.object(flow, "ui_events"),
            ):
                result = flow.deliver_text(
                    "Do not overwrite typing",
                    target=target,
                    profile="notes",
                    source="dictation",
                )
            self.assertEqual(result, {"id": "saved"})
            inject.assert_not_called()
            queue.add.assert_called_once_with(
                "Do not overwrite typing",
                target=target,
                profile="notes",
                source="dictation",
                reason="Keyboard input detected after recording stopped",
            )
        finally:
            flow.keyboard_generation, flow.delivery_keyboard_generation = original

    def test_queued_retry_focuses_intended_app_before_injection(self):
        calls = []
        record = {
            "text": "Protected text",
            "target": {"process": "notepad.exe", "title": "Notes", "hwnd": 42},
            "profile": "notes",
        }
        with (
            mock.patch.object(
                flow, "focus_delivery_target",
                side_effect=lambda _target: calls.append("focus") or True,
            ),
            mock.patch.object(
                flow, "inject",
                side_effect=lambda *_args, **_kwargs: calls.append("inject"),
            ),
            mock.patch.object(
                flow, "log_history",
                side_effect=lambda *_args, **_kwargs: calls.append("history"),
            ),
        ):
            delivered = flow.retry_queued_delivery(record)

        self.assertTrue(delivered)
        self.assertEqual(calls, ["focus", "inject", "history"])

    def test_queued_retry_never_injects_when_target_is_unavailable(self):
        with (
            mock.patch.object(flow, "focus_delivery_target", return_value=False),
            mock.patch.object(flow, "inject") as inject,
        ):
            delivered = flow.retry_queued_delivery({
                "text": "Protected text",
                "target": {"process": "closed.exe"},
            })

        self.assertFalse(delivered)
        inject.assert_not_called()

    def test_clipboard_shield_does_not_overwrite_newer_clipboard_data(self):
        """BITE-PROOF: removing the sequence check restores stale clipboard data."""
        with (
            mock.patch.object(flow.keyboard, "is_pressed", return_value=False),
            mock.patch.object(flow.keyboard, "send"),
            mock.patch.object(flow.pyperclip, "paste", return_value="before"),
            mock.patch.object(flow.pyperclip, "copy") as copy,
            mock.patch.object(flow, "clipboard_sequence", side_effect=[20, 21]),
            mock.patch.object(flow.time, "sleep"),
            mock.patch.object(flow.threading, "Thread", ImmediateThread),
        ):
            flow.inject("dictated", trailing_space=False)

        copy.assert_called_once_with("dictated")

    def test_clipboard_shield_restores_unchanged_clipboard(self):
        with (
            mock.patch.object(flow.keyboard, "is_pressed", return_value=False),
            mock.patch.object(flow.keyboard, "send"),
            mock.patch.object(flow.pyperclip, "paste", return_value="before"),
            mock.patch.object(flow.pyperclip, "copy") as copy,
            mock.patch.object(flow, "clipboard_sequence", side_effect=[20, 20]),
            mock.patch.object(flow.time, "sleep"),
            mock.patch.object(flow.threading, "Thread", ImmediateThread),
        ):
            flow.inject("dictated", trailing_space=False)

        self.assertEqual(
            copy.call_args_list,
            [mock.call("dictated"), mock.call("before")],
        )

    def test_clipboard_restore_retries_a_temporary_windows_lock(self):
        with (
            mock.patch.object(
                flow.pyperclip,
                "copy",
                side_effect=[OSError("locked"), OSError("locked"), None],
            ) as copy,
            mock.patch.object(flow, "clipboard_sequence", return_value=20),
            mock.patch.object(flow.time, "sleep"),
            mock.patch.object(flow, "report_runtime_error") as report,
            mock.patch.object(flow, "_clipboard_restore_original", "before"),
            mock.patch.object(flow, "_clipboard_restore_token", 3),
            mock.patch.object(flow, "_clipboard_last_sequence", 20),
        ):
            flow._restore_clipboard_after_delay(3, 20)

        self.assertEqual(copy.call_count, 3)
        report.assert_not_called()

    def test_clipboard_restore_surfaces_a_persistent_windows_lock(self):
        with (
            mock.patch.object(
                flow.pyperclip, "copy", side_effect=OSError("still locked")
            ) as copy,
            mock.patch.object(flow, "clipboard_sequence", return_value=20),
            mock.patch.object(flow.time, "sleep"),
            mock.patch.object(flow, "report_runtime_error") as report,
            mock.patch.object(flow, "_clipboard_restore_original", "before"),
            mock.patch.object(flow, "_clipboard_restore_token", 3),
            mock.patch.object(flow, "_clipboard_last_sequence", 20),
        ):
            flow._restore_clipboard_after_delay(3, 20)

        self.assertEqual(copy.call_count, 3)
        report.assert_called_once()

    def test_clipboard_failure_falls_back_to_typing(self):
        with (
            mock.patch.object(flow.keyboard, "is_pressed", return_value=False),
            mock.patch.object(flow.keyboard, "write") as write,
            mock.patch.object(flow.pyperclip, "paste", return_value="before"),
            mock.patch.object(flow.pyperclip, "copy", side_effect=OSError("locked")),
        ):
            flow.inject("dictated", trailing_space=False)

        write.assert_called_once_with("dictated", delay=flow.TYPE_DELAY)

    def test_paste_returns_before_clipboard_restore_delay(self):
        worker = mock.Mock()
        with (
            mock.patch.object(flow.keyboard, "is_pressed", return_value=False),
            mock.patch.object(flow.keyboard, "send"),
            mock.patch.object(flow.pyperclip, "paste", return_value="before"),
            mock.patch.object(flow.pyperclip, "copy"),
            mock.patch.object(flow, "clipboard_sequence", return_value=20),
            mock.patch.object(flow.time, "sleep") as sleep,
            mock.patch.object(flow.threading, "Thread", return_value=worker) as thread,
            mock.patch.object(flow, "_clipboard_restore_original", None, create=True),
            mock.patch.object(flow, "_clipboard_restore_token", 0, create=True),
            mock.patch.object(flow, "_clipboard_last_sequence", None, create=True),
        ):
            flow.inject("dictated", trailing_space=False)
        sleep.assert_not_called()
        thread.assert_called_once()
        worker.start.assert_called_once_with()

    def test_rapid_pastes_restore_the_original_clipboard_once(self):
        workers = []

        class DeferredThread:
            def __init__(self, *, target, daemon):
                workers.append(target)

            def start(self):
                pass

        with (
            mock.patch.object(flow.keyboard, "is_pressed", return_value=False),
            mock.patch.object(flow.keyboard, "send"),
            mock.patch.object(
                flow.pyperclip, "paste", side_effect=["before", "dictated one"]
            ) as paste,
            mock.patch.object(flow.pyperclip, "copy") as copy,
            mock.patch.object(
                flow, "clipboard_sequence", side_effect=[20, 20, 21, 21]
            ),
            mock.patch.object(flow.time, "sleep"),
            mock.patch.object(flow.threading, "Thread", DeferredThread),
            mock.patch.object(flow, "_clipboard_restore_original", None, create=True),
            mock.patch.object(flow, "_clipboard_restore_token", 0, create=True),
            mock.patch.object(flow, "_clipboard_last_sequence", None, create=True),
        ):
            flow.inject("dictated one", trailing_space=False)
            flow.inject("dictated two", trailing_space=False)
            for worker in workers:
                worker()

        paste.assert_called_once_with()
        self.assertEqual(
            copy.call_args_list,
            [mock.call("dictated one"), mock.call("dictated two"), mock.call("before")],
        )

    def test_newer_external_clipboard_becomes_the_next_restore_value(self):
        workers = []

        class DeferredThread:
            def __init__(self, *, target, daemon):
                workers.append(target)

            def start(self):
                pass

        with (
            mock.patch.object(flow.keyboard, "is_pressed", return_value=False),
            mock.patch.object(flow.keyboard, "send"),
            mock.patch.object(
                flow.pyperclip, "paste", side_effect=["before", "external"]
            ) as paste,
            mock.patch.object(flow.pyperclip, "copy") as copy,
            mock.patch.object(
                flow, "clipboard_sequence", side_effect=[20, 21, 22, 22]
            ),
            mock.patch.object(flow.time, "sleep"),
            mock.patch.object(flow.threading, "Thread", DeferredThread),
            mock.patch.object(flow, "_clipboard_restore_original", None),
            mock.patch.object(flow, "_clipboard_restore_token", 0),
            mock.patch.object(flow, "_clipboard_last_sequence", None),
        ):
            flow.inject("dictated one", trailing_space=False)
            flow.inject("dictated two", trailing_space=False)
            for worker in workers:
                worker()

        self.assertEqual(paste.call_count, 2)
        self.assertEqual(
            copy.call_args_list,
            [mock.call("dictated one"), mock.call("dictated two"), mock.call("external")],
        )


class RecoveryRuntimeTests(unittest.TestCase):
    def setUp(self):
        flow.recovery_session = None
        flow.recovery_failed = False

    def tearDown(self):
        flow.recovery_session = None
        flow.recovery_failed = False

    def test_recovery_lifecycle_journals_partial_then_completes(self):
        recovery = mock.Mock()
        recovery.begin.return_value = "20260711-120000-12345678"
        recovery.attach_audio.return_value = "recovery.wav"
        with mock.patch.object(flow, "RECOVERY", recovery):
            flow.begin_recovery("notes", "dictation")
            flow.journal_partial("recover me")
            flow.journal_audio(np.zeros(1600, dtype=np.float32))
            flow.finish_recovery(success=True)

        recovery.begin.assert_called_once_with(profile="notes", source="dictation")
        recovery.append.assert_called_once_with(
            "20260711-120000-12345678", "recover me"
        )
        recovery.attach_audio.assert_called_once()
        self.assertEqual(recovery.attach_audio.call_args.args[0], "20260711-120000-12345678")
        np.testing.assert_array_equal(
            recovery.attach_audio.call_args.args[1],
            np.zeros(1600, dtype=np.float32),
        )
        self.assertEqual(recovery.attach_audio.call_args.args[2], flow.SAMPLE_RATE)
        recovery.complete.assert_called_once_with("20260711-120000-12345678")
        self.assertIsNone(flow.recovery_session)

    def test_stopped_audio_is_journaled_before_transcription(self):
        original = (flow.vad_enabled, flow.chunks, flow.ACTIVE_ENGINE)
        try:
            flow.vad_enabled = False
            flow.chunks = [np.zeros(4800, dtype=np.float32)]
            flow.ACTIVE_ENGINE = mock.Mock()
            flow.ACTIVE_ENGINE.transcribe.side_effect = RuntimeError("engine stopped")
            with (
                mock.patch.object(flow, "journal_audio") as journal,
                mock.patch.object(flow, "beep"),
                mock.patch.object(flow, "ui_events"),
                self.assertRaises(RuntimeError),
            ):
                flow.stop_and_transcribe()
            journal.assert_called_once()
            np.testing.assert_array_equal(
                journal.call_args.args[0],
                np.zeros(4800, dtype=np.float32),
            )
        finally:
            flow.vad_enabled, flow.chunks, flow.ACTIVE_ENGINE = original

    def test_finish_worker_surfaces_failure_without_raising(self):
        original = (flow.recording, flow.continuous_mode)
        try:
            flow.recording = True
            flow.continuous_mode = False
            with (
                mock.patch.object(
                    flow, "stop_and_transcribe", side_effect=RuntimeError("engine stopped")
                ),
                mock.patch.object(flow, "report_runtime_error") as report,
            ):
                flow._finish()
            report.assert_called_once()
            self.assertEqual(report.call_args.args[0], "Dictation")
        finally:
            flow.recording, flow.continuous_mode = original

    def test_transcriber_worker_survives_one_bad_segment(self):
        event = mock.Mock()
        segment = np.ones(flow.SAMPLE_RATE, dtype=np.float32)
        original_engine = flow.ACTIVE_ENGINE
        try:
            flow.ACTIVE_ENGINE = mock.Mock()
            flow.ACTIVE_ENGINE.transcribe.side_effect = RuntimeError("bad segment")
            with (
                mock.patch.object(
                    flow.seg_queue,
                    "get",
                    side_effect=[("seg", segment), ("end", event), KeyboardInterrupt],
                ),
                mock.patch.object(flow, "report_runtime_error") as report,
                self.assertRaises(KeyboardInterrupt),
            ):
                flow.transcriber_worker()
            report.assert_called_once()
            event.set.assert_called_once_with()
        finally:
            flow.ACTIVE_ENGINE = original_engine

    def test_vad_flush_failure_releases_waiter_and_keeps_worker_alive(self):
        event = mock.Mock()
        vad = mock.Mock()
        vad.flush.side_effect = RuntimeError("vad failed")
        flow.recovery_failed = False
        with (
            mock.patch.object(flow, "create_vad", return_value=vad),
            mock.patch.object(
                flow.vad_queue,
                "get",
                side_effect=[("flush", event), KeyboardInterrupt],
            ),
            mock.patch.object(flow, "report_runtime_error") as report,
            self.assertRaises(KeyboardInterrupt),
        ):
            flow.vad_worker()
        event.set.assert_called_once_with()
        report.assert_called_once()
        self.assertTrue(flow.recovery_failed)

    def test_vad_startup_failure_switches_to_fallback_capture(self):
        original = flow.vad_enabled
        try:
            flow.vad_enabled = True
            with (
                mock.patch.object(
                    flow, "create_vad", side_effect=RuntimeError("model unavailable")
                ),
                mock.patch.object(flow, "report_runtime_error") as report,
            ):
                flow.vad_worker()
            self.assertFalse(flow.vad_enabled)
            report.assert_called_once()
        finally:
            flow.vad_enabled = original

    def test_continuous_worker_failure_resets_mode_and_surfaces_error(self):
        original = (
            flow.recording,
            flow.continuous_mode,
            flow.continuous_paused,
            flow.continuous_resumed_at,
        )
        try:
            flow.recording = True
            flow.continuous_mode = True
            flow.continuous_paused = False
            flow.continuous_resumed_at = 10.0
            with (
                mock.patch.object(flow, "beep", side_effect=RuntimeError("audio failed")),
                mock.patch.object(flow, "report_runtime_error") as report,
                mock.patch.object(flow, "ui_events") as events,
            ):
                flow.end_continuous()
            self.assertFalse(flow.recording)
            self.assertFalse(flow.continuous_mode)
            self.assertFalse(flow.continuous_paused)
            self.assertEqual(flow.continuous_resumed_at, 0.0)
            report.assert_called_once()
            events.put.assert_called_with("idle")
        finally:
            (
                flow.recording,
                flow.continuous_mode,
                flow.continuous_paused,
                flow.continuous_resumed_at,
            ) = original

    def test_failed_final_save_keeps_recovery_journal(self):
        recovery = mock.Mock()
        recovery.begin.return_value = "20260711-120000-12345678"
        with mock.patch.object(flow, "RECOVERY", recovery):
            flow.begin_recovery("notes", "dictation")
            flow.finish_recovery(success=False)

        recovery.complete.assert_not_called()
        self.assertIsNone(flow.recovery_session)

    def test_partial_delivery_keeps_journal_after_segment_failure(self):
        original = (
            flow.vad_enabled,
            flow.chunks,
            flow.ACTIVE_ENGINE,
            flow.recovery_failed,
            list(flow.partials),
        )
        try:
            flow.vad_enabled = False
            flow.chunks = [np.zeros(4800, dtype=np.float32)]
            flow.ACTIVE_ENGINE = mock.Mock()
            flow.ACTIVE_ENGINE.transcribe.return_value = "partial result"
            flow.recovery_failed = True
            flow.partials.clear()
            with (
                mock.patch.object(flow, "journal_audio"),
                mock.patch.object(flow, "journal_partial"),
                mock.patch.object(flow, "finish_text", return_value="Partial result."),
                mock.patch.object(flow, "deliver_text", return_value={"id": "saved"}),
                mock.patch.object(flow, "finish_recovery") as finish,
                mock.patch.object(flow, "beep"),
                mock.patch.object(flow, "ui_events"),
            ):
                flow.stop_and_transcribe()
            finish.assert_called_once_with(success=False)
        finally:
            (
                flow.vad_enabled,
                flow.chunks,
                flow.ACTIVE_ENGINE,
                flow.recovery_failed,
                partials,
            ) = original
            flow.partials[:] = partials

    def test_recording_start_opens_journal_for_every_mode(self):
        """BITE-PROOF: removing begin_recovery from start_recording makes this fail."""
        original = (flow.command_mode, flow.continuous_mode, flow.vad_enabled)
        try:
            flow.vad_enabled = False
            for command, continuous, source in (
                (False, False, "dictation"),
                (True, False, "command"),
                (False, True, "continuous"),
            ):
                with self.subTest(source=source):
                    flow.recording = False
                    flow.command_mode = command
                    flow.continuous_mode = continuous
                    with (
                        mock.patch.object(flow, "begin_recovery") as begin,
                        mock.patch.object(flow, "current_profile", return_value="notes"),
                        mock.patch.object(
                            flow, "active_window_info",
                            return_value={"hwnd": 42, "process": "notepad.exe", "title": "Notes"},
                        ),
                        mock.patch.object(flow, "beep"),
                        mock.patch.object(flow, "ui_events"),
                    ):
                        flow.start_recording()
                    begin.assert_called_once_with("notes", source)
                    self.assertEqual(
                        flow.delivery_target,
                        {"hwnd": 42, "process": "notepad.exe", "title": "Notes"},
                    )
        finally:
            flow.recording = False
            flow.command_mode, flow.continuous_mode, flow.vad_enabled = original

    def test_paused_continuous_callback_excludes_new_audio(self):
        original = (
            flow.recording,
            flow.continuous_mode,
            flow.continuous_paused,
            flow.vad_enabled,
        )
        try:
            flow.recording = True
            flow.continuous_mode = True
            flow.continuous_paused = True
            flow.vad_enabled = True
            with (
                mock.patch.object(flow, "preroll") as preroll,
                mock.patch.object(flow, "vad_queue") as vad_queue,
                mock.patch.object(flow, "_update_spectrum") as spectrum,
            ):
                flow.audio_callback(np.ones((1600, 1), dtype=np.float32), 1600, None, None)
            preroll.append.assert_not_called()
            vad_queue.put.assert_not_called()
            spectrum.assert_not_called()
        finally:
            (
                flow.recording,
                flow.continuous_mode,
                flow.continuous_paused,
                flow.vad_enabled,
            ) = original

    def test_pause_and_resume_keep_same_continuous_session(self):
        original = (
            flow.continuous_mode,
            flow.continuous_paused,
            flow.vad_enabled,
            flow.continuous_active_elapsed,
            flow.continuous_resumed_at,
        )
        flow.continuous_mode = True
        flow.continuous_paused = False
        flow.vad_enabled = True
        flow.continuous_active_elapsed = 5.0
        flow.continuous_resumed_at = 100.0
        session = flow.recovery_session
        try:
            with (
                mock.patch.object(flow, "vad_queue") as vad_queue,
                mock.patch.object(flow, "ui_events") as events,
                mock.patch.object(flow.time, "time", side_effect=[110.0, 120.0]),
            ):
                flow.toggle_pause()
                self.assertTrue(flow.continuous_paused)
                self.assertEqual(flow.continuous_active_elapsed, 15.0)
                self.assertEqual(flow.continuous_resumed_at, 0.0)
                self.assertEqual(vad_queue.put.call_args.args[0][0], "flush")
                events.put.assert_called_with("paused")
                flow.toggle_pause()
                self.assertFalse(flow.continuous_paused)
                self.assertEqual(flow.continuous_resumed_at, 120.0)
                vad_queue.put.assert_called_with(("reset",))
                events.put.assert_called_with("continuous")
            self.assertIs(flow.recovery_session, session)
        finally:
            (
                flow.continuous_mode,
                flow.continuous_paused,
                flow.vad_enabled,
                flow.continuous_active_elapsed,
                flow.continuous_resumed_at,
            ) = original

    def test_continuous_session_writes_one_aggregate_history_item(self):
        original = (
            flow.recording,
            flow.continuous_mode,
            flow.continuous_paused,
            flow.vad_enabled,
            flow.recovery_failed,
            flow.continuous_profile,
            flow.continuous_active_elapsed,
            flow.continuous_resumed_at,
            list(flow.continuous_final_text),
            list(flow.continuous_original_text),
            list(flow.continuous_audio),
        )
        try:
            flow.recording = True
            flow.continuous_mode = True
            flow.continuous_paused = True
            flow.vad_enabled = False
            flow.recovery_failed = False
            flow.continuous_profile = "notes"
            flow.continuous_active_elapsed = 12.5
            flow.continuous_resumed_at = 0.0
            flow.continuous_final_text[:] = ["First.", "Second."]
            flow.continuous_original_text[:] = ["first", "second"]
            flow.continuous_audio[:] = [
                np.zeros(1600, dtype=np.float32),
                np.ones(1600, dtype=np.float32) * 0.1,
            ]
            with (
                mock.patch.object(flow, "log_history", return_value={"id": "session"}) as history,
                mock.patch.object(flow, "journal_audio") as journal_audio,
                mock.patch.object(flow, "finish_recovery") as finish,
                mock.patch.object(flow, "beep"),
                mock.patch.object(flow, "ui_events"),
            ):
                flow.end_continuous()
            history.assert_called_once()
            self.assertEqual(history.call_args.args[0], "First. Second.")
            self.assertEqual(history.call_args.kwargs["original"], "first second")
            self.assertEqual(history.call_args.kwargs["source"], "continuous")
            self.assertEqual(history.call_args.kwargs["profile"], "notes")
            self.assertEqual(history.call_args.kwargs["duration"], 12.5)
            self.assertEqual(len(history.call_args.kwargs["audio"]), 3200)
            journal_audio.assert_called_once()
            finish.assert_called_once_with(success=True)
            self.assertFalse(flow.continuous_mode)
            self.assertFalse(flow.continuous_paused)
            self.assertEqual(flow.continuous_final_text, [])
        finally:
            (
                flow.recording,
                flow.continuous_mode,
                flow.continuous_paused,
                flow.vad_enabled,
                flow.recovery_failed,
                flow.continuous_profile,
                flow.continuous_active_elapsed,
                flow.continuous_resumed_at,
                final_text,
                original_text,
                audio,
            ) = original
            flow.continuous_final_text[:] = final_text
            flow.continuous_original_text[:] = original_text
            flow.continuous_audio[:] = audio

    def test_continuous_mode_stays_active_until_final_vad_segment_finishes(self):
        original = (
            flow.recording,
            flow.continuous_mode,
            flow.continuous_paused,
            flow.vad_enabled,
            flow.recovery_failed,
            flow.continuous_active_elapsed,
            flow.continuous_resumed_at,
            list(flow.continuous_final_text),
            list(flow.continuous_original_text),
            list(flow.continuous_audio),
        )
        event = mock.Mock()
        event.wait.side_effect = lambda timeout: self.assertTrue(flow.continuous_mode)
        try:
            flow.recording = True
            flow.continuous_mode = True
            flow.continuous_paused = False
            flow.vad_enabled = True
            flow.recovery_failed = False
            flow.continuous_active_elapsed = 0.0
            flow.continuous_resumed_at = 0.0
            flow.continuous_final_text.clear()
            flow.continuous_original_text.clear()
            flow.continuous_audio.clear()
            with (
                mock.patch.object(flow.threading, "Event", return_value=event),
                mock.patch.object(flow, "vad_queue") as vad_queue,
                mock.patch.object(flow, "finish_recovery"),
                mock.patch.object(flow, "beep"),
                mock.patch.object(flow, "ui_events"),
            ):
                flow.end_continuous()
            vad_queue.put.assert_called_once_with(("flush", event))
            event.wait.assert_called_once_with(timeout=120)
            self.assertFalse(flow.continuous_mode)
        finally:
            (
                flow.recording,
                flow.continuous_mode,
                flow.continuous_paused,
                flow.vad_enabled,
                flow.recovery_failed,
                flow.continuous_active_elapsed,
                flow.continuous_resumed_at,
                final_text,
                original_text,
                audio,
            ) = original
            flow.continuous_final_text[:] = final_text
            flow.continuous_original_text[:] = original_text
            flow.continuous_audio[:] = audio

    def test_startup_reuses_fresh_icons_and_rebuilds_from_brand_art(self):
        # Fresh icons already present: no rebuild of either kind.
        with (
            mock.patch.object(flow, "make_cues") as make_cues,
            mock.patch.object(flow, "_brand_icons_stale", return_value=False),
            mock.patch.object(flow, "build_brand_icons") as build,
            mock.patch.object(flow, "make_icon") as make_icon,
        ):
            flow.ensure_assets()
        make_cues.assert_called_once_with()
        build.assert_not_called()
        make_icon.assert_not_called()

        # A stale/missing icon with the brand art present: rebuild from the art,
        # never fall back to the drawn icons.
        with (
            mock.patch.object(flow, "make_cues"),
            mock.patch.object(flow, "_brand_icons_stale", return_value=True),
            mock.patch.object(flow, "build_brand_icons", return_value=True) as build,
            mock.patch.object(flow, "make_icon") as make_icon,
        ):
            flow.ensure_assets()
        build.assert_called_once_with()
        make_icon.assert_not_called()

        # Icons missing and the brand art absent: draw the fallback icons.
        with (
            mock.patch.object(flow, "make_cues"),
            mock.patch.object(flow, "_brand_icons_stale", return_value=True),
            mock.patch.object(flow, "build_brand_icons", return_value=False),
            mock.patch.object(flow.os.path, "exists", return_value=False),
            mock.patch.object(flow, "make_icon") as make_icon,
        ):
            flow.ensure_assets()
        make_icon.assert_called_once_with()

    def test_saved_audio_benchmark_measures_every_round(self):
        engine = mock.Mock()
        engine.transcribe.return_value = "um benchmark result"
        with mock.patch(
            "flow_features.read_wav", return_value=np.zeros(1600, dtype=np.float32)
        ):
            report = benchmark_flow.saved_audio_stop_to_text(
                engine, ["sample.wav"], rounds=3, max_audio_seconds=0.05
            )
        self.assertEqual(report["overall"]["rounds"], 3)
        self.assertEqual(report["files"][0]["audio_seconds"], 0.05)
        self.assertEqual(len(engine.transcribe.call_args.args[0]), 800)
        self.assertEqual(engine.transcribe.call_count, 3)

    def test_delivery_return_benchmark_restores_runtime_dependencies(self):
        original_injection = flow.INJECTION
        report = benchmark_flow.delivery_return_latency(5)
        self.assertEqual(report["rounds"], 5)
        self.assertGreater(report["max_ms"], 0)
        self.assertEqual(flow.INJECTION, original_injection)

    def test_vad_caps_live_segments_at_three_and_a_half_seconds(self):
        config = SimpleNamespace(silero_vad=SimpleNamespace())
        detector = object()
        sherpa = SimpleNamespace(
            VadModelConfig=mock.Mock(return_value=config),
            VoiceActivityDetector=mock.Mock(return_value=detector),
        )
        with mock.patch.dict(sys.modules, {"sherpa_onnx": sherpa}):
            result = flow.create_vad()
        self.assertIs(result, detector)
        self.assertEqual(config.silero_vad.max_speech_duration, 3.5)
        self.assertEqual(config.sample_rate, flow.SAMPLE_RATE)
        sherpa.VoiceActivityDetector.assert_called_once_with(
            config, buffer_size_in_seconds=120
        )

    def test_moonshine_uses_measured_four_thread_sweet_spot(self):
        fake_sherpa = SimpleNamespace(
            OfflineRecognizer=SimpleNamespace(from_moonshine=mock.Mock())
        )
        with mock.patch.dict(sys.modules, {"sherpa_onnx": fake_sherpa}):
            flow.MoonshineEngine()

        kwargs = fake_sherpa.OfflineRecognizer.from_moonshine.call_args.kwargs
        self.assertEqual(kwargs["num_threads"], 4)

    def test_main_creates_ui_before_starting_runtime_worker(self):
        events = []

        class FakeOverlay:
            def __init__(self):
                events.append("overlay")

            def run(self):
                events.append("run")

        class DeferredThread:
            def __init__(self, target, daemon=False):
                self.target = target

            def start(self):
                events.append("thread:" + self.target.__name__)

            def join(self):
                pass

        engine = SimpleNamespace(
            name="test", transcribe=mock.Mock(return_value="")
        )
        backend = SimpleNamespace(
            InputStream=mock.Mock(
                return_value=SimpleNamespace(start=mock.Mock())
            )
        )
        original_queue, original_sd = flow.ui_events, flow.sd
        try:
            flow.ui_events = flow.queue.Queue()
            flow.sd = backend
            with (
                mock.patch.object(flow, "ipc_server", return_value=True),
                mock.patch.object(flow, "Overlay", FakeOverlay),
                mock.patch.object(flow.threading, "Thread", DeferredThread),
                mock.patch.object(flow, "ensure_assets"),
                mock.patch.object(flow.HISTORY, "prune", return_value=0),
                mock.patch.object(
                    flow, "load_engine", side_effect=lambda: (events.append("engine"), engine)[1]
                ),
                mock.patch.object(flow, "start_tray"),
                mock.patch.object(flow, "register_hotkeys"),
                mock.patch.object(flow.keyboard, "add_hotkey"),
                mock.patch.object(flow.os.path, "exists", return_value=False),
                mock.patch.object(flow.sys, "argv", ["flow.py"]),
            ):
                flow.main()
            self.assertEqual(
                events[:3], ["overlay", "thread:initialize_runtime", "run"]
            )
        finally:
            flow.ui_events, flow.sd = original_queue, original_sd

    def test_runtime_initialization_reports_ready_and_keeps_audio_stream(self):
        engine = SimpleNamespace(
            name="test", transcribe=mock.Mock(return_value="")
        )
        stream = SimpleNamespace(start=mock.Mock())
        backend = SimpleNamespace(InputStream=mock.Mock(return_value=stream))
        original = (
            flow.ui_events,
            flow.sd,
            getattr(flow, "runtime_ready", False),
            getattr(flow, "runtime_error", ""),
            getattr(flow, "AUDIO_STREAM", None),
        )
        try:
            flow.ui_events = flow.queue.Queue()
            flow.sd = None

            def load_audio():
                flow.sd = backend
                return backend

            loader = mock.Mock()
            loader.start.side_effect = load_audio
            with (
                mock.patch.object(flow.threading, "Thread", return_value=loader),
                mock.patch.object(flow, "ensure_assets"),
                mock.patch.object(flow.HISTORY, "prune", return_value=0),
                mock.patch.object(flow, "load_engine", return_value=engine),
                mock.patch.object(flow, "start_tray"),
                mock.patch.object(flow, "register_hotkeys"),
                mock.patch.object(flow.keyboard, "add_hotkey"),
                mock.patch.object(flow.os.path, "exists", return_value=False),
            ):
                flow.initialize_runtime()
            self.assertTrue(flow.runtime_ready)
            self.assertEqual(flow.runtime_error, "")
            self.assertIs(flow.AUDIO_STREAM, stream)
            stream.start.assert_called_once_with()
            self.assertEqual(flow.ui_events.get_nowait(), "ready")
        finally:
            (
                flow.ui_events,
                flow.sd,
                flow.runtime_ready,
                flow.runtime_error,
                flow.AUDIO_STREAM,
            ) = original

    def test_runtime_initialization_surfaces_startup_failure(self):
        engine = SimpleNamespace(
            name="test", transcribe=mock.Mock(return_value="")
        )
        stream = SimpleNamespace(
            start=mock.Mock(), stop=mock.Mock(), close=mock.Mock()
        )
        backend = SimpleNamespace(InputStream=mock.Mock(return_value=stream))
        original = (
            flow.ui_events,
            flow.sd,
            getattr(flow, "runtime_ready", False),
            getattr(flow, "runtime_error", ""),
            getattr(flow, "AUDIO_STREAM", None),
        )
        try:
            flow.ui_events = flow.queue.Queue()
            flow.sd = None

            def load_audio():
                flow.sd = backend

            loader = mock.Mock()
            loader.start.side_effect = load_audio
            with (
                mock.patch.object(flow, "ensure_assets"),
                mock.patch.object(flow.HISTORY, "prune", return_value=0),
                mock.patch.object(flow, "start_tray"),
                mock.patch.object(flow.threading, "Thread", return_value=loader),
                mock.patch.object(flow, "load_engine", return_value=engine),
                mock.patch.object(flow.os.path, "exists", return_value=False),
                mock.patch.object(
                    flow, "register_hotkeys", side_effect=RuntimeError("hotkey failed")
                ),
            ):
                flow.initialize_runtime()
            self.assertFalse(flow.runtime_ready)
            self.assertEqual(flow.runtime_error, "hotkey failed")
            self.assertIsNone(flow.AUDIO_STREAM)
            stream.stop.assert_called_once_with()
            stream.close.assert_called_once_with()
            self.assertEqual(
                flow.ui_events.get_nowait(), ("startup_error", "hotkey failed")
            )
        finally:
            (
                flow.ui_events,
                flow.sd,
                flow.runtime_ready,
                flow.runtime_error,
                flow.AUDIO_STREAM,
            ) = original

    def test_hub_blocks_engine_actions_until_runtime_is_ready(self):
        hub = object.__new__(flow.ModernHub)
        hub.flash = mock.Mock()
        hub.app = SimpleNamespace(runtime_ready=False, runtime_error="")
        self.assertFalse(hub.engine_ready())
        hub.flash.assert_called_once_with("Speech engine is still starting")

        hub.flash.reset_mock()
        hub.app.runtime_error = "model failed"
        self.assertFalse(hub.engine_ready())
        hub.flash.assert_called_once_with("Speech engine unavailable")

        hub.app.runtime_ready = True
        self.assertTrue(hub.engine_ready())

    def test_microphone_button_waits_for_runtime_readiness(self):
        hub = object.__new__(flow.ModernHub)
        hub.engine_ready = mock.Mock(return_value=False)
        hub.mic_map = {"System default": None}
        hub.mic_var = SimpleNamespace(get=lambda: "System default")
        hub.flash = mock.Mock()
        with mock.patch("flow_hub.threading.Thread") as thread_class:
            hub.test_microphone()
        hub.engine_ready.assert_called_once_with()
        thread_class.assert_not_called()

    def test_microphone_failure_callback_preserves_error_message(self):
        callbacks = []

        class ImmediateThread:
            def __init__(self, *, target, daemon):
                self.target = target

            def start(self):
                self.target()

        hub = object.__new__(flow.ModernHub)
        hub.engine_ready = mock.Mock(return_value=True)
        hub.mic_map = {"System default": None}
        hub.mic_var = SimpleNamespace(get=lambda: "System default")
        hub.flash = mock.Mock()
        hub.top = SimpleNamespace(after=lambda _delay, callback: callbacks.append(callback))
        hub.app = SimpleNamespace(
            SAMPLE_RATE=flow.SAMPLE_RATE,
            sd=SimpleNamespace(
                rec=mock.Mock(side_effect=OSError("device busy")),
                wait=mock.Mock(),
            ),
        )
        with mock.patch("flow_hub.threading.Thread", ImmediateThread):
            hub.test_microphone()
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        hub.flash.assert_called_with("Microphone test failed: device busy")

    def test_dictionary_buttons_persist_and_report_write_failures(self):
        hub = object.__new__(flow.ModernHub)
        hub.flash = mock.Mock()
        with tempfile.TemporaryDirectory() as temp:
            dictionary_path = str(Path(temp) / "dictionary.txt")
            hub.app = SimpleNamespace(
                BASE_DIR=temp,
                DICT=SimpleNamespace(path=dictionary_path),
                read_rules=mock.Mock(return_value=[("old", "Old")]),
                write_rules=mock.Mock(),
            )

            self.assertTrue(hub.save_vocabulary_word("Moonshine", ["Flow State"]))
            vocabulary = (Path(temp) / "vocabulary.txt").read_text(encoding="utf-8")
            self.assertIn("Flow State", vocabulary)
            self.assertIn("Moonshine", vocabulary)

            self.assertTrue(hub.save_dictionary_rule("hello", "Hello there"))
            hub.app.write_rules.assert_called_with(
                dictionary_path, [("old", "Old"), ("hello", "Hello there")]
            )

            hub.app.write_rules.reset_mock()
            self.assertTrue(hub.delete_dictionary_rule(("old", "Old")))
            hub.app.write_rules.assert_called_with(dictionary_path, [])

            hub.app.write_rules.side_effect = OSError("file locked")
            self.assertFalse(hub.save_dictionary_rule("new", "New"))
            self.assertFalse(hub.delete_dictionary_rule(("old", "Old")))
            hub.flash.assert_called_with("Dictionary save failed: file locked")

            with mock.patch("flow_hub.Path.write_text", side_effect=OSError("file locked")):
                self.assertFalse(hub.save_vocabulary_word("Aqua", []))
            hub.flash.assert_called_with("Vocabulary save failed: file locked")

    def test_copy_buttons_share_guarded_clipboard_path(self):
        hub = object.__new__(flow.ModernHub)
        hub.safe_copy = mock.Mock(return_value=True)
        hub.flash = mock.Mock()
        hub._selected_delivery = mock.Mock(return_value={"text": "Queued"})
        hub._selected_recovery = mock.Mock(return_value={"text": "Recovered"})
        hub._selected_history = mock.Mock(return_value={"final": "History"})

        with mock.patch("flow_hub.pyperclip.copy"):
            hub.copy_delivery()
            hub.copy_recovery()
            hub.copy_history()
            hub.copy_reprocess_preview("Preview")

        self.assertEqual(
            hub.safe_copy.call_args_list,
            [
                mock.call("Queued", "Queued text copied"),
                mock.call("Recovered", "Recovered text copied"),
                mock.call("History", "Copied"),
                mock.call("Preview", "Preview copied; original history unchanged"),
            ],
        )

        hub.flash = mock.Mock()
        with mock.patch("flow_hub.pyperclip.copy") as copy:
            self.assertTrue(flow.ModernHub.safe_copy(hub, "Text", "Copied"))
        copy.assert_called_once_with("Text")
        hub.flash.assert_called_once_with("Copied")

        hub.flash.reset_mock()
        with mock.patch("flow_hub.pyperclip.copy", side_effect=OSError("clipboard busy")):
            self.assertFalse(flow.ModernHub.safe_copy(hub, "Text", "Copied"))
        hub.flash.assert_called_once_with("Copy failed: clipboard busy")

    def test_clear_delete_and_play_failures_stay_inside_hub(self):
        hub = object.__new__(flow.ModernHub)
        hub.top = object()
        hub.flash = mock.Mock()
        hub.show_current = mock.Mock()
        hub.current_page = "history"
        hub._selected_delivery = mock.Mock(return_value={"id": "delivery"})
        hub._selected_recovery = mock.Mock(return_value={"id": "recovery"})
        hub._selected_history = mock.Mock(
            return_value={"id": "history", "audio_path": "saved.wav"}
        )
        hub.app = SimpleNamespace(
            HISTORY=SimpleNamespace(
                clear=mock.Mock(side_effect=OSError("history locked")),
                delete=mock.Mock(side_effect=OSError("history locked")),
            ),
            DELIVERY=SimpleNamespace(
                complete=mock.Mock(side_effect=OSError("queue locked"))
            ),
            RECOVERY=SimpleNamespace(
                complete=mock.Mock(side_effect=OSError("recovery locked"))
            ),
        )
        with (
            mock.patch("flow_hub.messagebox.askyesno", return_value=True),
            mock.patch("flow_hub.os.path.exists", return_value=True),
            mock.patch(
                "flow_hub.winsound.PlaySound", side_effect=RuntimeError("audio busy")
            ),
        ):
            hub.clear_history()
            hub.delete_delivery()
            hub.delete_recovery()
            hub.delete_history()
            hub.play_history()
        messages = [call.args[0] for call in hub.flash.call_args_list]
        self.assertIn("History clear failed: history locked", messages)
        self.assertIn("Queue removal failed: queue locked", messages)
        self.assertIn("Recovery removal failed: recovery locked", messages)
        self.assertIn("History removal failed: history locked", messages)
        self.assertIn("Audio playback failed: audio busy", messages)

    def test_settings_button_reports_persistence_failure(self):
        def variable(value):
            return SimpleNamespace(get=lambda: value)

        hub = object.__new__(flow.ModernHub)
        for name, value in {
            "auto_stop_var": "1.5",
            "max_record_var": "45",
            "fade_var": "60",
            "retention_var": "30",
            "hotkey_var": "ctrl+windows",
            "continuous_hotkey_var": "ctrl+windows+space",
            "pause_hotkey_var": "ctrl+windows+shift+space",
            "command_hotkey_var": "ctrl+windows+alt",
            "undo_hotkey_var": "ctrl+windows+z",
            "redo_hotkey_var": "ctrl+windows+shift+z",
            "engine_var": "moonshine",
            "inject_var": "paste",
            "verbatim_var": False,
            "polish_var": True,
            "profile_var": "auto",
            "mic_var": "System default",
            "sound_var": True,
            "save_audio_var": True,
            "theme_var": "light",
            "open_hub_var": False,
            "autostart_var": False,
        }.items():
            setattr(hub, name, variable(value))
        hub.mic_map = {"System default": None}
        hub.colors = flow_hub.LIGHT
        hub.flash = mock.Mock()
        hub.app = SimpleNamespace(
            save_settings=mock.Mock(side_effect=OSError("settings locked")),
            set_autostart=mock.Mock(),
            HISTORY=SimpleNamespace(prune=mock.Mock()),
        )

        hub.save_settings()

        hub.flash.assert_called_once_with("Settings save failed: settings locked")
        hub.app.set_autostart.assert_not_called()
        hub.app.HISTORY.prune.assert_not_called()

        hub.flash.reset_mock()
        hub.max_record_var = variable("1e999")
        hub.save_settings()
        hub.flash.assert_called_once_with("Use numbers in timing and retention fields")

    def test_history_and_wav_commands_complete_successfully(self):
        class ImmediateThread:
            def __init__(self, *, target, daemon):
                self.target = target

            def start(self):
                self.target()

        top = SimpleNamespace(after=lambda _delay, callback: callback())
        record = {"id": "history", "final": "Saved", "audio_path": "saved.wav"}
        history = SimpleNamespace(
            clear=mock.Mock(return_value=2), delete=mock.Mock(return_value=True)
        )
        hub = object.__new__(flow.ModernHub)
        hub.top = top
        hub.current_page = "history"
        hub.flash = mock.Mock()
        hub.show_current = mock.Mock()
        hub.show_reprocess_lab = mock.Mock()
        hub.engine_ready = mock.Mock(return_value=True)
        hub._selected_history = mock.Mock(return_value=record)
        hub.app = SimpleNamespace(
            HISTORY=history,
            transcribe_wav_path=mock.Mock(return_value={"id": "saved"}),
        )

        with (
            mock.patch("flow_hub.messagebox.askyesno", return_value=True),
            mock.patch("flow_hub.os.path.exists", return_value=True),
            mock.patch("flow_hub.winsound.PlaySound") as play,
            mock.patch("flow_hub.filedialog.askopenfilename", return_value="chosen.wav"),
            mock.patch("flow_hub.threading.Thread", ImmediateThread),
        ):
            hub.clear_history()
            hub.play_history()
            hub.retry_history()
            hub.reprocess_history()
            hub.delete_history()
            hub.choose_wav()

        history.clear.assert_called_once_with()
        history.delete.assert_called_once_with("history")
        play.assert_called_once_with(
            "saved.wav", flow_hub.winsound.SND_FILENAME | flow_hub.winsound.SND_ASYNC
        )
        self.assertEqual(
            hub.app.transcribe_wav_path.call_args_list,
            [mock.call("saved.wav", "retry"), mock.call("chosen.wav")],
        )
        hub.show_reprocess_lab.assert_called_once_with(record)
        messages = [call.args[0] for call in hub.flash.call_args_list]
        self.assertIn("Removed 2 history item(s)", messages)
        self.assertIn("Retry saved", messages)
        self.assertIn("History item removed", messages)
        self.assertIn("File transcript saved", messages)

    def test_closed_hub_drops_worker_callback_without_error(self):
        hub = object.__new__(flow.ModernHub)
        callback = mock.Mock()
        hub.top = SimpleNamespace(
            after=mock.Mock(side_effect=RuntimeError("window destroyed"))
        )
        self.assertFalse(hub.post_ui(callback))
        callback.assert_not_called()

        hub.top = SimpleNamespace(after=lambda _delay, action: action())
        self.assertTrue(hub.post_ui(callback))
        callback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
