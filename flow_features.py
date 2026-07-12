"""Pure, testable features for Flow State.

The live microphone and Tkinter UI stay in flow.py.  This module owns text
processing and local history so those paths can be verified without hooks,
audio devices, or a display.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
import wave
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np


PROFILE_PRESETS = {
    "default": {
        "name": "Default",
        "description": "Balanced punctuation and paragraphing.",
    },
    "messages": {
        "name": "Messages",
        "description": "Short, conversational messages without a trailing period.",
    },
    "email": {
        "name": "Email",
        "description": "Professional email spacing and sign-off formatting.",
    },
    "notes": {
        "name": "Notes",
        "description": "Readable notes with automatic list formatting.",
    },
    "coding": {
        "name": "Coding",
        "description": "Minimal rewriting for prompts, code, and technical terms.",
    },
}

CORRECTION_MARKER = re.compile(
    r"\s*\b(?:no,\s*wait|no\s+wait|scratch\s+that|correction)\b[:,]?\s*(?:actually\b[:,]?\s*)?",
    re.I,
)
FILLER_PHRASES = re.compile(
    r"\s*\b(?:you\s+know|i\s+mean|kind\s+of|sort\s+of|basically|literally)\b[,.]?",
    re.I,
)
NUMBERED_ITEM = re.compile(r"(?:^|\s)(?:item\s+)?(\d+|one|two|three|four|five)[,.:]\s+", re.I)
BULLET_ITEM = re.compile(r"(?:^|\s)(?:bullet|next\s+item)[,.:]?\s+", re.I)


def apply_spoken_correction(text: str) -> str:
    """Remove the most recent clause when the speaker explicitly backtracks."""
    match = None
    for match in CORRECTION_MARKER.finditer(text):
        pass
    if match is None:
        return text
    before = text[: match.start()].rstrip()
    after = text[match.end() :].lstrip()
    boundary = max(before.rfind("."), before.rfind("?"), before.rfind("!"), before.rfind("\n"))
    prefix = before[: boundary + 1].rstrip() if boundary >= 0 else ""
    return (prefix + (" " if prefix and after else "") + after).strip()


def _format_lists(text: str) -> str:
    if BULLET_ITEM.search(text):
        parts = [p.strip(" ,.;") for p in BULLET_ITEM.split(text) if p.strip(" ,.;")]
        if len(parts) > 1:
            return "\n".join("- " + part[:1].upper() + part[1:] for part in parts)
    matches = list(NUMBERED_ITEM.finditer(text))
    if len(matches) >= 2:
        intro = text[: matches[0].start()].strip()
        items = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            item = text[match.end() : end].strip(" ,.;")
            if item:
                items.append(item[:1].upper() + item[1:])
        result = "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))
        return (intro.rstrip(".") + ":\n" + result) if intro else result
    return text


def _format_email(text: str) -> str:
    text = re.sub(r"^(hi|hello|hey)\s+([^,\n]+),?\s+", r"\1 \2,\n\n", text, flags=re.I)
    text = re.sub(
        r"\s+(best|thanks|thank you|regards|sincerely),?\s+([^,\n]+)[.!]?$",
        r"\n\n\1,\n\2",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(\n\n)([a-z])",
        lambda match: match.group(1) + match.group(2).upper(),
        text,
    )
    return text


def polish_text(text: str, profile: str = "default") -> str:
    """Apply deterministic cleanup and a lightweight per-app writing profile."""
    if not text:
        return ""
    text = apply_spoken_correction(text)
    text = FILLER_PHRASES.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:?!])", r"\1", text)
    text = _format_lists(text)
    if profile == "email":
        text = _format_email(text)
    elif profile == "messages":
        text = text.strip()
        if text.endswith(".") and not text.endswith("..."):
            text = text[:-1]
    elif profile == "notes":
        text = _format_lists(text)
    elif profile == "coding":
        text = re.sub(r"\n{3,}", "\n\n", text)
    if text:
        text = text[0].upper() + text[1:]
    return text.strip()


def transform_selected_text(text: str, command: str) -> str | None:
    """Run safe local command-mode transforms.

    Returns None for commands that need a language model, allowing the caller
    to leave the user's selected text untouched.
    """
    source = text.strip()
    cmd = command.strip().lower()
    if not source or not cmd:
        return None
    if any(phrase in cmd for phrase in ("uppercase", "all caps")):
        return source.upper()
    if "lowercase" in cmd:
        return source.lower()
    if "title case" in cmd or "make this a title" in cmd:
        return source.title()
    if "bullet" in cmd:
        pieces = [p.strip(" -") for p in re.split(r"[\n;,]+", source) if p.strip(" -")]
        return "\n".join("- " + p for p in pieces)
    if "numbered" in cmd or "number list" in cmd:
        pieces = [p.strip(" -") for p in re.split(r"[\n;,]+", source) if p.strip(" -")]
        return "\n".join(f"{i}. {p}" for i, p in enumerate(pieces, 1))
    if "shorter" in cmd or "concise" in cmd:
        sentences = re.split(r"(?<=[.!?])\s+", source)
        compact = re.sub(r"\b(?:very|really|just|actually|basically)\b\s*", "", sentences[0], flags=re.I)
        return re.sub(r"[ \t]{2,}", " ", compact).strip()
    replace = re.search(r"replace\s+(.+?)\s+with\s+(.+)$", command, re.I)
    if replace:
        old, new = replace.groups()
        if old.lower() not in source.lower():
            return None
        return re.sub(re.escape(old), new, source, flags=re.I)
    if cmd.startswith("add ") and cmd.endswith(" at the end"):
        addition = command[4 : -11].strip()
        return source + (" " if source else "") + addition
    if "fix" in cmd or "polish" in cmd or "clean" in cmd:
        return polish_text(source)
    return None


def choose_profile(process_name: str, overrides: dict | None = None) -> str:
    process = (process_name or "").lower()
    if overrides:
        for needle, profile in overrides.items():
            if needle.lower() in process and profile in PROFILE_PRESETS:
                return profile
    known = {
        "slack": "messages",
        "discord": "messages",
        "whatsapp": "messages",
        "teams": "messages",
        "outlook": "email",
        "thunderbird": "email",
        "notion": "notes",
        "onenote": "notes",
        "obsidian": "notes",
        "code": "coding",
        "cursor": "coding",
        "pycharm": "coding",
        "devenv": "coding",
        "terminal": "coding",
        "powershell": "coding",
    }
    for needle, profile in known.items():
        if needle in process:
            return profile
    return "default"


def apply_vocabulary(text: str, path: str | os.PathLike) -> str:
    """Normalize known words and phrases to the exact casing saved by the user."""
    try:
        entries = [
            line.strip()
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except OSError:
        return text
    for entry in sorted(entries, key=len, reverse=True):
        text = re.sub(r"\b%s\b" % re.escape(entry), entry, text, flags=re.I)
    return text


def write_wav(path: str | os.PathLike, audio: np.ndarray, sample_rate: int = 16000) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(str(target), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm.tobytes())
    return str(target)


def read_wav(path: str | os.PathLike, target_rate: int = 16000) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        raw = source.readframes(source.getnframes())
    if width != 2:
        raise ValueError("Only 16-bit PCM WAV files are supported")
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != target_rate and len(audio):
        old_x = np.linspace(0.0, 1.0, len(audio), endpoint=False)
        new_len = max(1, int(round(len(audio) * target_rate / rate)))
        new_x = np.linspace(0.0, 1.0, new_len, endpoint=False)
        audio = np.interp(new_x, old_x, audio).astype(np.float32)
    return audio


class HistoryStore:
    """Append-only local history with guarded audio retention."""

    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        self.path = self.root / "history.jsonl"
        self.audio_dir = self.root / "recordings"

    def add(
        self,
        *,
        original: str,
        final: str,
        duration: float = 0.0,
        latency: float = 0.0,
        engine: str = "",
        profile: str = "default",
        audio: np.ndarray | None = None,
        sample_rate: int = 16000,
        source: str = "dictation",
    ) -> dict:
        now = datetime.now()
        record_id = now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        audio_path = ""
        if audio is not None and len(audio):
            audio_path = write_wav(self.audio_dir / f"{record_id}.wav", audio, sample_rate)
        record = {
            "id": record_id,
            "timestamp": now.isoformat(timespec="seconds"),
            "original": original,
            "final": final,
            "duration": round(float(duration), 3),
            "latency": round(float(latency), 3),
            "engine": engine,
            "profile": profile,
            "audio_path": audio_path,
            "source": source,
            "words": len(final.split()),
        }
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as out:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            os.fsync(out.fileno())
        return record

    def read(self) -> list[dict]:
        records = []
        try:
            with open(self.path, encoding="utf-8") as source:
                for line in source:
                    try:
                        record = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(record, dict) and record.get("id"):
                        records.append(record)
        except OSError:
            pass
        records.reverse()
        return records

    def find(self, record_id: str) -> dict | None:
        return next((item for item in self.read() if item.get("id") == record_id), None)

    def _safe_audio_path(self, value: str) -> Path | None:
        if not value:
            return None
        candidate = Path(value).resolve()
        try:
            candidate.relative_to(self.audio_dir.resolve())
        except ValueError:
            return None
        return candidate

    def rewrite(self, records: list[dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="history-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                for record in reversed(records):
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def delete(self, record_id: str) -> bool:
        records = self.read()
        victim = next((r for r in records if r.get("id") == record_id), None)
        if victim is None:
            return False
        audio_path = self._safe_audio_path(victim.get("audio_path", ""))
        self.rewrite([r for r in records if r.get("id") != record_id])
        if audio_path and audio_path.exists():
            audio_path.unlink()
        return True

    def prune(self, days: int) -> int:
        if days <= 0:
            return 0
        cutoff = datetime.now() - timedelta(days=days)
        removed = 0
        keep = []
        for record in self.read():
            try:
                timestamp = datetime.fromisoformat(record["timestamp"])
            except (KeyError, TypeError, ValueError):
                keep.append(record)
                continue
            if timestamp >= cutoff:
                keep.append(record)
                continue
            audio_path = self._safe_audio_path(record.get("audio_path", ""))
            if audio_path and audio_path.exists():
                audio_path.unlink()
            removed += 1
        if removed:
            self.rewrite(keep)
        return removed

    def clear(self) -> int:
        records = self.read()
        for record in records:
            audio_path = self._safe_audio_path(record.get("audio_path", ""))
            if audio_path and audio_path.exists():
                audio_path.unlink()
        self.rewrite([])
        return len(records)

    def stats(self) -> dict:
        records = self.read()
        words = sum(int(r.get("words") or len(r.get("final", "").split())) for r in records)
        seconds = sum(float(r.get("duration") or 0) for r in records)
        latencies = [float(r.get("latency") or 0) for r in records if float(r.get("latency") or 0) > 0]
        profiles = Counter(r.get("profile", "default") for r in records)
        return {
            "dictations": len(records),
            "words": words,
            "minutes": round(seconds / 60.0, 1),
            "average_latency": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            "top_profile": profiles.most_common(1)[0][0] if profiles else "default",
        }


class RecoveryJournal:
    """Durable partial transcripts that survive an interrupted session."""

    SESSION_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$")

    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        self.directory = self.root / "recovery"

    def _path(self, session_id: str) -> Path | None:
        if not self.SESSION_ID.fullmatch(str(session_id)):
            return None
        candidate = (self.directory / f"{session_id}.jsonl").resolve()
        try:
            candidate.relative_to(self.directory.resolve())
        except ValueError:
            return None
        return candidate

    def _append_event(self, path: Path, event: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as out:
            out.write(json.dumps(event, ensure_ascii=False) + "\n")
            out.flush()
            os.fsync(out.fileno())

    def begin(self, *, profile: str = "default", source: str = "dictation") -> str:
        now = datetime.now()
        session_id = now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        path = self._path(session_id)
        if path is None:
            raise ValueError("Could not create a valid recovery session id")
        self._append_event(path, {
            "event": "start",
            "timestamp": now.isoformat(timespec="seconds"),
            "profile": profile,
            "source": source,
        })
        return session_id

    def append(self, session_id: str, text: str) -> bool:
        path = self._path(session_id)
        cleaned = " ".join(str(text).split())
        if path is None or not path.exists() or not cleaned:
            return False
        self._append_event(path, {
            "event": "partial",
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "text": cleaned,
        })
        return True

    def complete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if path is None or not path.exists():
            return False
        path.unlink()
        return True

    def orphans(self) -> list[dict]:
        sessions = []
        try:
            paths = sorted(
                self.directory.glob("*.jsonl"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return sessions
        for path in paths:
            start = {}
            pieces = []
            try:
                with open(path, encoding="utf-8") as source:
                    for line in source:
                        try:
                            event = json.loads(line)
                        except (TypeError, ValueError):
                            continue
                        if event.get("event") == "start" and not start:
                            start = event
                        elif event.get("event") == "partial" and event.get("text"):
                            pieces.append(" ".join(str(event["text"]).split()))
            except OSError:
                continue
            sessions.append({
                "id": path.stem,
                "started": start.get("timestamp", ""),
                "profile": start.get("profile", "default"),
                "source": start.get("source", "dictation"),
                "text": " ".join(pieces),
                "segments": len(pieces),
            })
        return sessions
