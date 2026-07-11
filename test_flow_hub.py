import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import flow
from flow_hub import Hub


class FakeHistory:
    def read(self):
        return []

    def stats(self):
        return {
            "dictations": 0,
            "words": 0,
            "minutes": 0.0,
            "average_latency": 0.0,
            "top_profile": "default",
        }

    def prune(self, _days):
        return 0

    def clear(self):
        return 0

    def delete(self, _record_id):
        return False


def buttons(widget):
    found = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Button):
            found.append(child)
        found.extend(buttons(child))
    return found


class HubControlTests(unittest.TestCase):
    PAGE_BUTTONS = {
        "history": {"Copy", "Play", "Retry", "Delete"},
        "dictionary": {"Add word", "Add", "Delete"},
        "general": set(),
        "dictation": set(),
        "audio": {"Test microphone"},
        "appearance": set(),
        "privacy": {"Clear history..."},
        "files": {"Choose WAV..."},
        "stats": set(),
    }

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.patches = [
            mock.patch.object(flow, "BASE_DIR", self.temp.name),
            mock.patch.object(flow, "DICT", SimpleNamespace(path=str(Path(self.temp.name) / "dictionary.txt"))),
            mock.patch.object(flow, "HISTORY", FakeHistory()),
            mock.patch.object(flow, "get_autostart", return_value=False),
            mock.patch.object(flow, "available_microphones", return_value=[]),
            mock.patch.object(flow, "save_settings"),
            mock.patch.object(flow, "set_autostart"),
            mock.patch.object(Hub, "test_microphone"),
            mock.patch.object(Hub, "clear_history"),
            mock.patch.object(Hub, "choose_wav"),
        ]
        for patcher in self.patches:
            patcher.start()
        self.hub = Hub(self.root, flow)
        self.root.update_idletasks()

    def tearDown(self):
        self.hub.top.destroy()
        self.root.destroy()
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp.cleanup()

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
        flow.set_autostart.assert_called_once()
        footer["Reset page"].invoke()


if __name__ == "__main__":
    unittest.main()
