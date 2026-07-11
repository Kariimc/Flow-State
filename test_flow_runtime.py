import unittest
from unittest import mock

import flow


class DeliveryTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
