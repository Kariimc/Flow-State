import sys
import unittest
from unittest import mock

import flow


class DeliveryTests(unittest.TestCase):
    def test_import_does_not_eagerly_load_audio_backend(self):
        self.assertNotIn("sounddevice", sys.modules)

    def test_overlay_event_poll_ceiling_is_25ms(self):
        self.assertLessEqual(flow.Overlay.POLL_MS, 25)

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
            mock.patch.object(flow, "ui_events") as events,
        ):
            flow.deliver_text("Hello", trailing_space=False, source="test")

        self.assertEqual(calls[0], ("inject", "Hello", False))
        self.assertEqual(calls[1], ("history",))
        events.put.assert_called_once_with(("notice", "Text inserted; history save failed"))

    def test_clipboard_shield_does_not_overwrite_newer_clipboard_data(self):
        """BITE-PROOF: removing the sequence check restores stale clipboard data."""
        with (
            mock.patch.object(flow.keyboard, "is_pressed", return_value=False),
            mock.patch.object(flow.keyboard, "send"),
            mock.patch.object(flow.pyperclip, "paste", return_value="before"),
            mock.patch.object(flow.pyperclip, "copy") as copy,
            mock.patch.object(flow, "clipboard_sequence", side_effect=[20, 21]),
            mock.patch.object(flow.time, "sleep"),
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
        ):
            flow.inject("dictated", trailing_space=False)

        self.assertEqual(
            copy.call_args_list,
            [mock.call("dictated"), mock.call("before")],
        )

    def test_clipboard_failure_falls_back_to_typing(self):
        with (
            mock.patch.object(flow.keyboard, "is_pressed", return_value=False),
            mock.patch.object(flow.keyboard, "write") as write,
            mock.patch.object(flow.pyperclip, "paste", return_value="before"),
            mock.patch.object(flow.pyperclip, "copy", side_effect=OSError("locked")),
        ):
            flow.inject("dictated", trailing_space=False)

        write.assert_called_once_with("dictated", delay=flow.TYPE_DELAY)


if __name__ == "__main__":
    unittest.main()
