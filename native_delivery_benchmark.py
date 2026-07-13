"""Measure saved-audio stop-to-cursor latency through a real Notepad window."""

from __future__ import annotations

import argparse
import ctypes
import json
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

import flow
from flow_features import read_wav


SW_RESTORE = 9
WM_CLOSE = 0x0010


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def summarize(samples: list[float]) -> dict:
    ordered = sorted(samples)
    p95 = ordered[max(0, int(len(ordered) * 0.95 + 0.999999) - 1)]
    return {
        "rounds": len(ordered),
        "median_ms": round(statistics.median(ordered), 1),
        "p95_ms": round(p95, 1),
        "max_ms": round(ordered[-1], 1),
    }


def window_title(hwnd: int) -> str:
    length = int(ctypes.windll.user32.GetWindowTextLengthW(hwnd) or 0)
    if not length:
        return ""
    value = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, value, length + 1)
    return value.value


def find_window(title_token: str) -> int:
    matches: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
    )

    @callback_type
    def collect(hwnd, _data):
        if (
            ctypes.windll.user32.IsWindowVisible(hwnd)
            and title_token.casefold() in window_title(hwnd).casefold()
        ):
            matches.append(int(hwnd))
        return True

    ctypes.windll.user32.EnumWindows(collect, 0)
    return matches[0] if matches else 0


def wait_for_window(title_token: str, timeout: float = 10.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = find_window(title_token)
        if hwnd:
            return hwnd
        time.sleep(0.05)
    raise TimeoutError("Notepad test window did not appear")


def wait_for_window_closed(hwnd: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not ctypes.windll.user32.IsWindow(hwnd):
            return True
        time.sleep(0.05)
    return False


def focus_window(hwnd: int, timeout: float = 3.0) -> None:
    user32 = ctypes.windll.user32
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current_thread = int(ctypes.windll.kernel32.GetCurrentThreadId())
        foreground = int(user32.GetForegroundWindow() or 0)
        foreground_thread = int(
            user32.GetWindowThreadProcessId(foreground, None) or 0
        )
        target_thread = int(user32.GetWindowThreadProcessId(hwnd, None) or 0)
        attached = []
        try:
            for thread_id in {foreground_thread, target_thread}:
                if (
                    thread_id
                    and thread_id != current_thread
                    and user32.AttachThreadInput(current_thread, thread_id, True)
                ):
                    attached.append(thread_id)
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            for thread_id in attached:
                user32.AttachThreadInput(current_thread, thread_id, False)
        if int(user32.GetForegroundWindow() or 0) == hwnd:
            break
        # A synthetic Alt transition is Windows' documented foreground-lock
        # release signal. It carries no text and is used only for this window.
        user32.keybd_event(0x12, 0, 0, 0)
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(0x12, 0, 0x0002, 0)
        if int(user32.GetForegroundWindow() or 0) == hwnd:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("Notepad test window could not receive focus")

    original_cursor = Point()
    client = Rect()
    user32.GetCursorPos(ctypes.byref(original_cursor))
    if not user32.GetClientRect(hwnd, ctypes.byref(client)):
        raise RuntimeError("Notepad client area was unavailable")
    editor_point = Point(
        max(20, (client.right - client.left) // 2),
        max(120, (client.bottom - client.top) // 2),
    )
    if not user32.ClientToScreen(hwnd, ctypes.byref(editor_point)):
        raise RuntimeError("Notepad editor coordinates were unavailable")
    try:
        user32.SetCursorPos(editor_point.x, editor_point.y)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
    finally:
        user32.SetCursorPos(original_cursor.x, original_cursor.y)


def wait_for_saved_text(path: Path, expected: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    actual = "<unreadable>"
    while time.monotonic() < deadline:
        try:
            actual = path.read_text(encoding="utf-8-sig")
            if actual == expected:
                return
        except (OSError, UnicodeError):
            pass
        time.sleep(0.03)
    raise AssertionError(
        "Notepad saved different text: expected=%r actual=%r"
        % (expected[:160], actual[:160])
    )


def benchmark(audio_paths: list[str], model_dir: str, rounds: int) -> dict:
    if rounds < 1:
        raise ValueError("rounds must be positive")
    flow.MOONSHINE_DIR = str(Path(model_dir).resolve())
    engine = flow.MoonshineEngine()
    engine.transcribe(flow.np.zeros(flow.SAMPLE_RATE // 2, dtype=flow.np.float32))
    original_injection = flow.INJECTION
    flow.INJECTION = "paste"
    results = []
    all_samples: list[float] = []
    all_recognition: list[float] = []
    all_delivery: list[float] = []

    with tempfile.TemporaryDirectory(prefix="flow-state-native-") as temp:
        token = "flow-state-native-" + Path(temp).name.rsplit("-", 1)[-1]
        target = Path(temp) / (token + ".txt")
        target.write_text("", encoding="utf-8")
        process = subprocess.Popen(["notepad.exe", str(target)])
        hwnd = 0
        try:
            hwnd = wait_for_window(token)
            for file_index, raw_path in enumerate(audio_paths, 1):
                path = Path(raw_path).resolve()
                audio = read_wav(path)[-int(3.5 * flow.SAMPLE_RATE):]
                samples = []
                recognition_samples = []
                delivery_samples = []
                expected = ""
                for round_index in range(1, rounds + 1):
                    focus_window(hwnd)
                    flow.send_keys("ctrl+a")
                    flow.send_keys("backspace")
                    started = time.perf_counter()
                    expected = flow.finish_text(engine.transcribe(audio), "default")
                    if not expected:
                        raise ValueError(f"No text recognized from {path.name}")
                    recognition_finished = time.perf_counter()
                    payload = f"[Flow State {file_index}.{round_index}] {expected}"
                    flow.inject(payload, trailing_space=False)
                    delivered = time.perf_counter()
                    recognition_samples.append((recognition_finished - started) * 1000)
                    delivery_samples.append((delivered - recognition_finished) * 1000)
                    samples.append((delivered - started) * 1000)
                    flow.send_keys("ctrl+s")
                    wait_for_saved_text(target, payload)
                all_samples.extend(samples)
                all_recognition.extend(recognition_samples)
                all_delivery.extend(delivery_samples)
                results.append({
                    "path": str(path),
                    "audio_seconds": round(len(audio) / flow.SAMPLE_RATE, 3),
                    "recognized_characters": len(expected),
                    "stop_to_cursor": summarize(samples),
                    "recognition": summarize(recognition_samples),
                    "delivery": summarize(delivery_samples),
                })
            time.sleep(1.3)
        finally:
            flow.INJECTION = original_injection
            if hwnd and ctypes.windll.user32.IsWindow(hwnd):
                ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                if not wait_for_window_closed(hwnd):
                    raise RuntimeError("The temporary Notepad window did not close")
            if process.poll() is None:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=3)

    return {
        "overall": {
            "stop_to_cursor": summarize(all_samples),
            "recognition": summarize(all_recognition),
            "delivery": summarize(all_delivery),
        },
        "files": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", action="append", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.audio, args.model_dir, args.rounds), indent=2))
