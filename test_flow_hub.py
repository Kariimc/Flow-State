import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import flow
from flow_hub import Hub


def cancel_tk_callbacks(root, owner):
    for callback_id in root.tk.call("after", "info"):
        try:
            owner.after_cancel(callback_id)
        except tk.TclError:
            pass

class FakeHistory:
    def __init__(self):
        self.records = []

    def read(self):
        return list(self.records)

    def save_correction(self, record_id, corrected):
        record = next((item for item in self.records if item["id"] == record_id), None)
        if record is None:
            return None
        record["corrected"] = corrected
        record["corrected_at"] = "2026-07-14T12:00:00"
        return dict(record)

    def stats(self, *_args):
        return {
            "dictations": 0,
            "words": 0,
            "minutes": 0.0,
            "average_latency": 0.0,
            "median_delivery_latency": 0.0,
            "p95_delivery_latency": 0.0,
            "timed_deliveries": 0,
            "cutoff_warnings": 0,
            "recovered_sessions": 0,
            "top_profile": "default",
        }

    def prune(self, _days):
        return 0

    def clear(self):
        return 0

    def delete(self, _record_id):
        return False


class FakeCorrections:
    def __init__(self):
        self.records = []

    def read(self, status=None):
        records = list(self.records)
        return [item for item in records if item["status"] == status] if status else records

    def stats(self):
        return {
            "pending": sum(item["status"] == "pending" for item in self.records),
            "approved": sum(item["status"] == "approved" for item in self.records),
            "rejected": sum(item["status"] == "rejected" for item in self.records),
        }

    def observe(self, spoken, replacement, **_kwargs):
        item = {
            "id": f"pair-{len(self.records) + 1}",
            "spoken": spoken,
            "replacement": replacement,
            "status": "pending",
            "matches": 1,
        }
        self.records.append(item)
        return item

    def clear(self):
        count = len(self.records)
        self.records = []
        return count
    def set_status(self, correction_id, status):
        item = next((item for item in self.records if item["id"] == correction_id), None)
        if item is None:
            return False
        item["status"] = status
        return True

class FakeRecovery:
    def __init__(self):
        self.records = [{
            "id": "20260712-094200-abcdef12",
            "started": "2026-07-12T09:42:00",
            "profile": "notes",
            "source": "dictation",
            "text": "Recovered launch notes",
            "segments": 2,
        }]
        self.completed = []

    def orphans(self):
        return list(self.records)

    def complete(self, session_id):
        if session_id not in {record["id"] for record in self.records}:
            return False
        self.completed.append(session_id)
        self.records = [record for record in self.records if record["id"] != session_id]
        return True


class FakeDelivery:
    def __init__(self):
        self.records = [{
            "id": "20260712-095000-fedcba98",
            "timestamp": "2026-07-12T09:50:00",
            "text": "Protected queued text",
            "target": {"hwnd": 42, "process": "notepad.exe", "title": "Notes"},
            "profile": "notes",
            "source": "dictation",
            "reason": "OSError: blocked",
        }]
        self.completed = []

    def read(self):
        return list(self.records)

    def complete(self, record_id):
        if record_id not in {record["id"] for record in self.records}:
            return False
        self.completed.append(record_id)
        self.records = [record for record in self.records if record["id"] != record_id]
        return True


class ImmediateThread:
    def __init__(self, *, target, daemon):
        self.target = target

    def start(self):
        self.target()


def buttons(widget):
    found = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Button):
            found.append(child)
        found.extend(buttons(child))
    return found


class HubControlTests(unittest.TestCase):
    PAGE_BUTTONS = {
        "history": {"Copy", "Play", "Retry", "Reprocess", "Save correction", "Delete"},
        "recovery": {"Copy text", "Retry delivery", "Remove..."},
        "delivery": {"Copy text", "Retry delivery", "Remove..."},
        "dictionary": {"Add word", "Add", "Delete"},
        "accuracy": {"Review history"},
        "general": set(),
        "dictation": set(),
        "audio": {"Test microphone"},
        "appearance": set(),
        "privacy": {"Clear history...", "Clear learned corrections..."},
        "files": {"Choose WAV..."},
        "stats": set(),
    }

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.root.withdraw()
        self.patches = [
            mock.patch.object(flow, "BASE_DIR", self.temp.name),
            mock.patch.object(flow, "DICT", SimpleNamespace(path=str(Path(self.temp.name) / "dictionary.txt"))),
            mock.patch.object(flow, "HISTORY", FakeHistory()),
            mock.patch.object(flow, "CORRECTIONS", FakeCorrections()),
            mock.patch.object(flow, "RECOVERY", FakeRecovery()),
            mock.patch.object(flow, "DELIVERY", FakeDelivery()),
            mock.patch.object(flow, "get_autostart", return_value=False),
            mock.patch.object(flow, "available_microphones", return_value=[]),
            mock.patch.object(flow, "save_settings"),
            mock.patch.object(flow, "set_autostart"),
            mock.patch.object(flow, "find_delivery_target", return_value=42),
            mock.patch.object(Hub, "test_microphone"),
            mock.patch.object(Hub, "clear_history"),
            mock.patch.object(Hub, "clear_corrections"),
            mock.patch.object(Hub, "choose_wav"),
            mock.patch.object(Hub, "copy_recovery"),
            mock.patch.object(Hub, "retry_recovery"),
            mock.patch.object(Hub, "delete_recovery"),
            mock.patch.object(Hub, "copy_delivery"),
            mock.patch.object(Hub, "retry_delivery"),
            mock.patch.object(Hub, "delete_delivery"),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.root.destroy)
        self.hub = Hub(self.root, flow)
        self.addCleanup(cancel_tk_callbacks, self.root, self.hub.top)
        self.root.update_idletasks()


    def test_every_page_renders_and_every_command_button_invokes(self):
        for page, expected in self.PAGE_BUTTONS.items():
            with self.subTest(page=page):
                self.hub.show_page(page)
                self.root.update_idletasks()
                visible = {
                    button.cget("text"): button
                    for button in buttons(self.hub.page)
                }
                self.assertEqual(set(visible), expected)
                for button in visible.values():
                    button.invoke()

        footer = {button.cget("text"): button for button in buttons(self.hub.footer)}
        self.assertEqual(set(footer), {"Save changes", "Reset page"})
        footer["Save changes"].invoke()
        flow.save_settings.assert_called_once()
        saved = flow.save_settings.call_args.args[0]
        self.assertEqual(saved["UNDO_HOTKEY"], flow.UNDO_HOTKEY)
        self.assertEqual(saved["REDO_HOTKEY"], flow.REDO_HOTKEY)
        self.assertEqual(saved["CORRECTION_MODE"], "always_review")
        flow.set_autostart.assert_called_once()
        footer["Reset page"].invoke()

    def test_appearance_uses_the_real_icon_family(self):
        self.hub.show_page("appearance")
        self.root.update_idletasks()
        labels = []
        pending = [self.hub.page]
        while pending:
            widget = pending.pop()
            pending.extend(widget.winfo_children())
            if isinstance(widget, tk.Label):
                labels.append(widget.cget("text"))
        self.assertIn("Desktop + Hub", labels)
        self.assertIn("Tray", labels)
        self.assertEqual(len(self.hub._appearance_images), 2)

    def test_history_correction_creates_reviewable_pair_without_overwriting_final(self):
        flow.HISTORY.records = [{
            "id": "record-1",
            "timestamp": "2026-07-14T12:00:00",
            "original": "floor state is ready",
            "final": "Floor state is ready.",
            "audio_path": "",
        }]
        self.hub.show_page("history")
        self.hub.history_list.selection_set(0)
        self.hub.select_history()
        self.hub.history_correction.delete("1.0", "end")
        self.hub.history_correction.insert("1.0", "Flow State is ready.")
        self.hub.save_history_correction()

        saved = flow.HISTORY.records[0]
        self.assertEqual(saved["final"], "Floor state is ready.")
        self.assertEqual(saved["corrected"], "Flow State is ready.")
        self.assertEqual(flow.CORRECTIONS.records[0]["spoken"], "Floor state")
        self.assertEqual(flow.CORRECTIONS.records[0]["replacement"], "Flow State")
        self.assertEqual(flow.CORRECTIONS.records[0]["status"], "pending")

    def test_repeat_mode_keeps_first_observation_hidden_and_pending(self):
        flow.CORRECTIONS.records = [{
            "id": "pair-1",
            "spoken": "pair a key",
            "replacement": "Parakeet",
            "status": "pending",
            "matches": 1,
        }]
        self.hub.correction_mode_var.set("Review after 2 matches")
        self.hub.show_page("accuracy")
        self.root.update_idletasks()
        labels = {button.cget("text") for button in buttons(self.hub.page)}
        self.assertNotIn("Approve", labels)
        self.assertEqual(flow.CORRECTIONS.records[0]["status"], "pending")
    def test_accuracy_page_approves_pending_pair(self):
        flow.CORRECTIONS.records = [{
            "id": "pair-1",
            "spoken": "pair a key",
            "replacement": "Parakeet",
            "status": "pending",
            "matches": 2,
        }]
        self.hub.show_page("accuracy")
        self.root.update_idletasks()
        approve = next(
            button for button in buttons(self.hub.page)
            if button.cget("text") == "Approve"
        )
        approve.invoke()
        self.assertEqual(flow.CORRECTIONS.records[0]["status"], "approved")
    def test_history_actions_fit_supported_window_widths(self):
        for geometry in ("800x560", "940x680"):
            with self.subTest(geometry=geometry):
                self.hub.top.geometry(geometry)
                self.hub.show_page("history")
                self.hub.top.update()
                left = self.hub.top.winfo_rootx()
                right = left + self.hub.top.winfo_width()
                action_buttons = [
                    button for button in buttons(self.hub.page)
                    if button.cget("text") in self.PAGE_BUTTONS["history"]
                ]
                self.assertEqual(len(action_buttons), 6)
                for button in action_buttons:
                    self.assertGreaterEqual(button.winfo_rootx(), left)
                    self.assertLessEqual(
                        button.winfo_rootx() + button.winfo_width(), right
                    )

    def test_native_standard_edit_snapshot_and_password_exclusion(self):
        user32 = flow.ctypes.windll.user32
        create = user32.CreateWindowExW
        create.argtypes = [
            flow.wintypes.DWORD,
            flow.wintypes.LPCWSTR,
            flow.wintypes.LPCWSTR,
            flow.wintypes.DWORD,
            flow.ctypes.c_int,
            flow.ctypes.c_int,
            flow.ctypes.c_int,
            flow.ctypes.c_int,
            flow.wintypes.HWND,
            flow.wintypes.HMENU,
            flow.wintypes.HINSTANCE,
            flow.wintypes.LPVOID,
        ]
        create.restype = flow.wintypes.HWND
        self.hub.top.deiconify()
        self.hub.top.lift()
        self.hub.top.update()
        parent = self.hub.top.winfo_id()
        base_style = 0x40000000 | 0x10000000 | 0x00010000 | 0x00800000

        def make_edit(style):
            control = int(create(
                0, "EDIT", "abc", base_style | style,
                20, 20, 180, 28, parent, 0, 0, None,
            ) or 0)
            self.assertTrue(control)
            user32.SetForegroundWindow(parent)
            user32.SetFocus(control)
            flow._send_message_timeout(control, 0x00B1, 3, 3)
            self.hub.top.update()
            return control

        edit = make_edit(0x0080)
        try:
            snapshot = flow._edit_snapshot(parent, edit)
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot["text"], "abc")
            self.assertEqual(snapshot["selection_end"], 3)
        finally:
            user32.DestroyWindow(edit)

        password = make_edit(0x0020)
        try:
            self.assertIsNone(flow._edit_snapshot(parent, password))
        finally:
            user32.DestroyWindow(password)
    def test_reprocess_lab_copy_and_back_buttons_invoke(self):
        record = {
            "id": "saved-audio",
            "final": "Launch notes",
            "original": "raw launch notes",
            "audio_path": str(Path(self.temp.name) / "saved.wav"),
        }
        previews = {
            "Verbatim": "raw launch notes",
            "Light": "Launch notes.",
            "Notes": "- Launch notes",
            "Email": "Hi team,\n\nLaunch notes.",
            "Coding": "Launch scope: launch notes",
        }
        with (
            mock.patch.object(flow, "reprocess_previews", return_value=previews),
            mock.patch("flow_hub.pyperclip.copy") as copy,
        ):
            self.hub.show_reprocess_lab(record)
            self.root.update_idletasks()
            lab_buttons = buttons(self.hub.page)
            self.assertEqual(
                [button.cget("text") for button in lab_buttons].count("Copy"), 5
            )
            for button in lab_buttons:
                if button.cget("text") == "Copy":
                    button.invoke()
            self.assertEqual(copy.call_count, 5)
            back = next(
                button for button in lab_buttons
                if button.cget("text") == "Back to history"
            )
            back.invoke()
            self.assertEqual(self.hub.title.cget("text"), "History")

    def test_stats_labels_completed_recoveries(self):
        self.hub.show_page("stats")
        self.root.update_idletasks()

        def label_texts(widget):
            found = []
            for child in widget.winfo_children():
                if isinstance(child, tk.Label):
                    found.append(child.cget("text"))
                found.extend(label_texts(child))
            return found

        labels = label_texts(self.hub.page)
        self.assertIn("Recovered sessions", labels)
        self.assertNotIn("Recoverable sessions", labels)


class RecoveryInboxBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.root.withdraw()
        self.recovery = FakeRecovery()
        self.patches = [
            mock.patch.object(flow, "BASE_DIR", self.temp.name),
            mock.patch.object(
                flow, "DICT",
                SimpleNamespace(path=str(Path(self.temp.name) / "dictionary.txt")),
            ),
            mock.patch.object(flow, "HISTORY", FakeHistory()),
            mock.patch.object(flow, "CORRECTIONS", FakeCorrections()),
            mock.patch.object(flow, "RECOVERY", self.recovery),
            mock.patch.object(flow, "get_autostart", return_value=False),
            mock.patch.object(flow, "available_microphones", return_value=[]),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.root.destroy)
        self.hub = Hub(self.root, flow)
        self.addCleanup(cancel_tk_callbacks, self.root, self.hub.top)
        self.hub.show_page("recovery")
        self.root.update_idletasks()


    def test_copy_uses_selected_recovered_text(self):
        with mock.patch("flow_hub.pyperclip.copy") as copy:
            self.hub.copy_recovery()
        copy.assert_called_once_with("Recovered launch notes")

    def test_confirmed_remove_uses_guarded_recovery_delete(self):
        with mock.patch("flow_hub.messagebox.askyesno", return_value=True):
            self.hub.delete_recovery()
        self.assertEqual(
            self.recovery.completed,
            ["20260712-094200-abcdef12"],
        )
        self.assertEqual(self.recovery.records, [])

    def test_successful_retry_delivers_then_removes_recovery_copy(self):
        with (
            mock.patch("flow_hub.messagebox.askyesno", return_value=True),
            mock.patch("flow_hub.threading.Thread", ImmediateThread),
            mock.patch.object(self.hub.top, "after", side_effect=lambda _delay, callback: callback()),
            mock.patch.object(self.hub, "show"),
            mock.patch.object(self.hub, "flash"),
            mock.patch.object(flow, "deliver_text", return_value={"id": "history"}) as deliver,
        ):
            self.hub.retry_recovery()
        deliver.assert_called_once_with(
            "Recovered launch notes",
            trailing_space=False,
            original="Recovered launch notes",
            profile="notes",
            source="recovery",
        )
        self.assertEqual(
            self.recovery.completed,
            ["20260712-094200-abcdef12"],
        )

    def test_failed_retry_keeps_recovery_copy(self):
        with (
            mock.patch("flow_hub.messagebox.askyesno", return_value=True),
            mock.patch("flow_hub.threading.Thread", ImmediateThread),
            mock.patch.object(self.hub.top, "after", side_effect=lambda _delay, callback: callback()),
            mock.patch.object(self.hub, "show"),
            mock.patch.object(self.hub, "flash"),
            mock.patch.object(flow, "deliver_text", side_effect=RuntimeError("locked")),
        ):
            self.hub.retry_recovery()
        self.assertEqual(self.recovery.completed, [])
        self.assertEqual(len(self.recovery.records), 1)

    def test_audio_retry_retranscribes_instead_of_redelivering_old_text(self):
        audio_path = Path(self.temp.name) / "recovered.wav"
        audio_path.write_bytes(b"demo")
        self.recovery.records[0]["audio_path"] = str(audio_path)
        self.hub.show_page("recovery")
        self.root.update_idletasks()
        with (
            mock.patch.object(flow, "runtime_ready", True),
            mock.patch("flow_hub.messagebox.askyesno", return_value=True),
            mock.patch("flow_hub.threading.Thread", ImmediateThread),
            mock.patch.object(self.hub.top, "after", side_effect=lambda _delay, callback: callback()),
            mock.patch.object(self.hub, "show"),
            mock.patch.object(self.hub, "flash"),
            mock.patch.object(flow, "transcribe_wav_path", return_value={"id": "history"}) as transcribe,
            mock.patch.object(flow, "deliver_text") as deliver,
        ):
            self.hub.retry_recovery()
        transcribe.assert_called_once_with(str(audio_path), "recovery")
        deliver.assert_not_called()
        self.assertEqual(
            self.recovery.completed,
            ["20260712-094200-abcdef12"],
        )

    def test_retry_keeps_recovery_copy_when_history_save_fails(self):
        with (
            mock.patch("flow_hub.messagebox.askyesno", return_value=True),
            mock.patch("flow_hub.threading.Thread", ImmediateThread),
            mock.patch.object(self.hub.top, "after", side_effect=lambda _delay, callback: callback()),
            mock.patch.object(self.hub, "show"),
            mock.patch.object(self.hub, "flash"),
            mock.patch.object(flow, "deliver_text", return_value=None),
        ):
            self.hub.retry_recovery()
        self.assertEqual(self.recovery.completed, [])
        self.assertEqual(len(self.recovery.records), 1)


class DeliveryQueueBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = tk.Tk()
        self.root.withdraw()
        self.delivery = FakeDelivery()
        self.patches = [
            mock.patch.object(flow, "BASE_DIR", self.temp.name),
            mock.patch.object(
                flow, "DICT",
                SimpleNamespace(path=str(Path(self.temp.name) / "dictionary.txt")),
            ),
            mock.patch.object(flow, "HISTORY", FakeHistory()),
            mock.patch.object(flow, "CORRECTIONS", FakeCorrections()),
            mock.patch.object(flow, "RECOVERY", FakeRecovery()),
            mock.patch.object(flow, "DELIVERY", self.delivery),
            mock.patch.object(flow, "get_autostart", return_value=False),
            mock.patch.object(flow, "available_microphones", return_value=[]),
            mock.patch.object(flow, "find_delivery_target", return_value=42),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.root.destroy)
        self.hub = Hub(self.root, flow)
        self.addCleanup(cancel_tk_callbacks, self.root, self.hub.top)
        self.hub.show_page("delivery")
        self.root.update_idletasks()


    def test_copy_uses_selected_queued_text(self):
        with mock.patch("flow_hub.pyperclip.copy") as copy:
            self.hub.copy_delivery()
        copy.assert_called_once_with("Protected queued text")

    def test_confirmed_remove_deletes_only_selected_queue_record(self):
        with mock.patch("flow_hub.messagebox.askyesno", return_value=True):
            self.hub.delete_delivery()
        self.assertEqual(self.delivery.completed, ["20260712-095000-fedcba98"])
        self.assertEqual(self.delivery.records, [])

    def test_successful_retry_removes_queue_record(self):
        record = self.delivery.records[0]
        with (
            mock.patch("flow_hub.messagebox.askyesno", return_value=True),
            mock.patch("flow_hub.threading.Thread", ImmediateThread),
            mock.patch.object(self.hub.top, "after", side_effect=lambda _delay, callback: callback()),
            mock.patch.object(self.hub, "show"),
            mock.patch.object(self.hub, "flash"),
            mock.patch.object(flow, "retry_queued_delivery", return_value=True) as retry,
        ):
            self.hub.retry_delivery()
        retry.assert_called_once_with(record)
        self.assertEqual(self.delivery.completed, ["20260712-095000-fedcba98"])

    def test_failed_retry_keeps_queue_record(self):
        with (
            mock.patch("flow_hub.messagebox.askyesno", return_value=True),
            mock.patch("flow_hub.threading.Thread", ImmediateThread),
            mock.patch.object(self.hub.top, "after", side_effect=lambda _delay, callback: callback()),
            mock.patch.object(self.hub, "show"),
            mock.patch.object(self.hub, "flash"),
            mock.patch.object(flow, "retry_queued_delivery", return_value=False),
        ):
            self.hub.retry_delivery()
        self.assertEqual(self.delivery.completed, [])
        self.assertEqual(len(self.delivery.records), 1)

    def test_closed_target_disables_retry(self):
        with mock.patch.object(flow, "find_delivery_target", return_value=0):
            self.hub.select_delivery()
        self.assertEqual(str(self.hub.delivery_retry_button.cget("state")), "disabled")


if __name__ == "__main__":
    unittest.main()
