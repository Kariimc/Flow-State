"""Repeatable local performance benchmark for Flow State."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent


def summarize(samples, digits=1):
    ordered = sorted(float(value) for value in samples)
    p95_index = max(0, int(np.ceil(len(ordered) * 0.95)) - 1)
    return {
        "rounds": len(ordered),
        "min_ms": round(ordered[0], digits),
        "median_ms": round(statistics.median(ordered), digits),
        "p95_ms": round(ordered[p95_index], digits),
        "max_ms": round(ordered[-1], digits),
    }


def timed(callable_, rounds, digits=1):
    samples = []
    for _ in range(rounds):
        started = time.perf_counter()
        callable_()
        samples.append((time.perf_counter() - started) * 1000)
    return summarize(samples, digits=digits)


def startup_import(rounds):
    return timed(
        lambda: subprocess.run(
            [sys.executable, "-c", "import flow"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
        rounds,
    )


def delivery_return_latency(rounds=500):
    import flow

    class DeferredThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            pass

    sequence = [0]

    def copy(_text):
        sequence[0] += 1

    original = (
        flow.INJECTION,
        flow.keyboard.is_pressed,
        flow.keyboard.send,
        flow.pyperclip.paste,
        flow.pyperclip.copy,
        flow.clipboard_sequence,
        flow.threading.Thread,
        flow._clipboard_restore_original,
        flow._clipboard_restore_token,
        flow._clipboard_last_sequence,
    )
    try:
        flow.INJECTION = "paste"
        flow.keyboard.is_pressed = lambda _key: False
        flow.keyboard.send = lambda _combo: None
        flow.pyperclip.paste = lambda: "original clipboard"
        flow.pyperclip.copy = copy
        flow.clipboard_sequence = lambda: sequence[0]
        flow.threading.Thread = DeferredThread
        flow._clipboard_restore_original = None
        flow._clipboard_restore_token = 0
        flow._clipboard_last_sequence = None
        return timed(
            lambda: flow.inject("benchmark delivery", trailing_space=False),
            rounds,
            digits=4,
        )
    finally:
        (
            flow.INJECTION,
            flow.keyboard.is_pressed,
            flow.keyboard.send,
            flow.pyperclip.paste,
            flow.pyperclip.copy,
            flow.clipboard_sequence,
            flow.threading.Thread,
            flow._clipboard_restore_original,
            flow._clipboard_restore_token,
            flow._clipboard_last_sequence,
        ) = original


def saved_audio_stop_to_text(
    engine, paths, rounds=5, max_audio_seconds=None
):
    import flow
    from flow_features import read_wav

    all_samples = []
    files = []
    for raw_path in paths:
        path = Path(raw_path).resolve()
        audio = read_wav(path)
        if max_audio_seconds is not None:
            if max_audio_seconds <= 0:
                raise ValueError("max_audio_seconds must be positive")
            max_samples = max(1, int(max_audio_seconds * flow.SAMPLE_RATE))
            audio = audio[-max_samples:]
        samples = []
        final = ""
        for _ in range(rounds):
            started = time.perf_counter()
            final = flow.finish_text(engine.transcribe(audio), "default")
            samples.append((time.perf_counter() - started) * 1000)
        all_samples.extend(samples)
        files.append({
            "path": str(path),
            "audio_seconds": round(len(audio) / flow.SAMPLE_RATE, 3),
            "output_characters": len(final),
            "output": final,
            **summarize(samples),
        })
    return {"overall": summarize(all_samples), "files": files}


def run(
    include_engine=False,
    moonshine_dir=None,
    audio_paths=(),
    audio_rounds=5,
    max_audio_seconds=None,
):
    report = {"startup_import": startup_import(5)}

    import flow
    from flow_features import HistoryStore, RecoveryJournal

    if moonshine_dir:
        flow.MOONSHINE_DIR = str(Path(moonshine_dir).resolve())

    phrase = (
        "um actually bullet startup speed bullet reliable insertion "
        "bullet private local history"
    )
    report["text_finish"] = timed(lambda: flow.finish_text(phrase, "notes"), 500)
    report["delivery_return_without_os_clipboard_wait"] = delivery_return_latency()
    report["overlay_event_ceiling_ms"] = flow.Overlay.POLL_MS

    with tempfile.TemporaryDirectory() as temp:
        store = HistoryStore(temp)
        audio = np.zeros(flow.SAMPLE_RATE * 10, dtype=np.float32)
        report["history_text"] = timed(
            lambda: store.add(original="test", final="Test."), 10
        )
        report["history_with_10s_audio"] = timed(
            lambda: store.add(original="test", final="Test.", audio=audio), 10
        )
        recovery = RecoveryJournal(temp)
        recovery_id = recovery.begin(profile="notes", source="benchmark")
        report["recovery_append"] = timed(
            lambda: recovery.append(recovery_id, "Recoverable segment"), 20
        )
        recovery.complete(recovery_id)

    if include_engine or audio_paths:
        started = time.perf_counter()
        audio_loader = threading.Thread(target=flow.load_audio_backend)
        audio_loader.start()
        engine = flow.load_engine()
        engine.transcribe(np.zeros(flow.SAMPLE_RATE // 2, dtype=np.float32))
        audio_loader.join()
        report["engine_audio_warm_ms"] = round(
            (time.perf_counter() - started) * 1000, 1
        )
        if audio_paths:
            report["saved_audio_stop_to_text"] = saved_audio_stop_to_text(
                engine,
                audio_paths,
                rounds=audio_rounds,
                max_audio_seconds=max_audio_seconds,
            )

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--engine",
        action="store_true",
        help="also load and warm the configured speech engine",
    )
    parser.add_argument(
        "--moonshine-dir",
        help="use a specific installed Moonshine model directory",
    )
    parser.add_argument(
        "--audio",
        action="append",
        default=[],
        help="benchmark a saved WAV after engine warm-up; repeat for more files",
    )
    parser.add_argument(
        "--audio-rounds",
        type=int,
        default=5,
        help="transcription rounds per saved WAV (default: 5)",
    )
    parser.add_argument(
        "--max-audio-seconds",
        type=float,
        help="measure only the final N seconds, matching the live VAD segment cap",
    )
    args = parser.parse_args()
    print(json.dumps(run(
        include_engine=args.engine,
        moonshine_dir=args.moonshine_dir,
        audio_paths=args.audio,
        audio_rounds=args.audio_rounds,
        max_audio_seconds=args.max_audio_seconds,
    ), indent=2))
