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


def summarize(samples):
    ordered = sorted(float(value) for value in samples)
    p95_index = max(0, int(np.ceil(len(ordered) * 0.95)) - 1)
    return {
        "rounds": len(ordered),
        "min_ms": round(ordered[0], 1),
        "median_ms": round(statistics.median(ordered), 1),
        "p95_ms": round(ordered[p95_index], 1),
        "max_ms": round(ordered[-1], 1),
    }


def timed(callable_, rounds):
    samples = []
    for _ in range(rounds):
        started = time.perf_counter()
        callable_()
        samples.append((time.perf_counter() - started) * 1000)
    return summarize(samples)


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


def run(include_engine=False):
    report = {"startup_import": startup_import(5)}

    import flow
    from flow_features import HistoryStore, RecoveryJournal

    phrase = (
        "um actually bullet startup speed bullet reliable insertion "
        "bullet private local history"
    )
    report["text_finish"] = timed(lambda: flow.finish_text(phrase, "notes"), 500)
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

    if include_engine:
        started = time.perf_counter()
        audio_loader = threading.Thread(target=flow.load_audio_backend)
        audio_loader.start()
        engine = flow.load_engine()
        engine.transcribe(np.zeros(flow.SAMPLE_RATE // 2, dtype=np.float32))
        audio_loader.join()
        report["engine_audio_warm_ms"] = round(
            (time.perf_counter() - started) * 1000, 1
        )

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--engine",
        action="store_true",
        help="also load and warm the configured speech engine",
    )
    args = parser.parse_args()
    print(json.dumps(run(args.engine), indent=2))
