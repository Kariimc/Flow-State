"""Pure, testable features for Flow State.

The live microphone and Tkinter UI stay in flow.py.  This module owns text
processing and local history so those paths can be verified without hooks,
audio devices, or a display.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import statistics
import tempfile
import threading
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


_TOKEN = re.compile(r"\w+(?:['’-]\w+)*|[^\w\s]", re.UNICODE)


def _tokens(text: str) -> list[re.Match]:
    return list(_TOKEN.finditer(text or ""))


def _join_tokens(values: list[str]) -> str:
    text = " ".join(values)
    text = re.sub(r"\s+([,.;:?!%)\]}])", r"\1", text)
    text = re.sub(r"([(\[{])\s+", r"\1", text)
    return text.strip()


def extract_correction_pairs(
    before: str,
    after: str,
    changed_start: int = 0,
    changed_end: int | None = None,
    max_tokens: int = 8,
) -> list[tuple[str, str]]:
    """Return small replacement pairs overlapping a trusted character range.

    Insertions and deletions are intentionally ignored: they are more likely to
    be ordinary rewriting than speech-recognition corrections.
    """
    old_matches = _tokens(before)
    new_matches = _tokens(after)
    old_values = [match.group(0) for match in old_matches]
    new_values = [match.group(0) for match in new_matches]
    changed_end = len(before) if changed_end is None else max(changed_start, changed_end)
    pairs = []
    matcher = difflib.SequenceMatcher(a=old_values, b=new_values, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace" or i1 == i2 or j1 == j2:
            continue
        if i2 - i1 > max_tokens or j2 - j1 > max_tokens:
            continue
        old_start = old_matches[i1].start()
        old_end = old_matches[i2 - 1].end()
        if old_start < changed_start or old_end > changed_end:
            continue
        spoken = _join_tokens(old_values[i1:i2])
        replacement = _join_tokens(new_values[j1:j2])
        if (
            spoken
            and replacement
            and spoken != replacement
            and re.search(r"\w", spoken)
            and re.search(r"\w", replacement)
        ):
            pairs.append((spoken, replacement))
    return pairs


class CorrectionStore:
    """Atomic local store for reviewable speech-correction pairs."""

    VALID_STATUSES = {"pending", "approved", "rejected"}

    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        self.path = self.root / "corrections.json"
        self._lock = threading.RLock()

    def _read_unlocked(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        return [
            item for item in data
            if isinstance(item, dict)
            and item.get("id")
            and item.get("spoken")
            and item.get("replacement")
            and item.get("status") in self.VALID_STATUSES
        ]

    def read(self, status: str | None = None) -> list[dict]:
        with self._lock:
            records = self._read_unlocked()
        if status is not None:
            records = [item for item in records if item.get("status") == status]
        return sorted(records, key=lambda item: item.get("last_seen", ""), reverse=True)

    def _write_unlocked(self, records: list[dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="corrections-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(records, out, ensure_ascii=False, indent=2)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _ensure_writable_unlocked(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError:
            raise
        except (TypeError, ValueError) as exc:
            raise ValueError("Correction memory is damaged; original file kept") from exc
        if not isinstance(data, list) or len(self._read_unlocked()) != len(data):
            raise ValueError("Correction memory is damaged; original file kept")

    def observe(
        self,
        spoken: str,
        replacement: str,
        *,
        source_id: str = "",
    ) -> dict | None:
        spoken = " ".join(str(spoken or "").split()).strip()
        replacement = " ".join(str(replacement or "").split()).strip()
        if (
            not spoken
            or not replacement
            or spoken == replacement
            or len(spoken) > 200
            or len(replacement) > 200
        ):
            return None
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._ensure_writable_unlocked()
            records = self._read_unlocked()
            match = next(
                (
                    item for item in records
                    if item["spoken"].casefold() == spoken.casefold()
                    and item["replacement"] == replacement
                ),
                None,
            )
            if match is None:
                match = {
                    "id": uuid.uuid4().hex[:12],
                    "spoken": spoken,
                    "replacement": replacement,
                    "status": "pending",
                    "matches": 1,
                    "first_seen": now,
                    "last_seen": now,
                    "sources": [source_id] if source_id else [],
                }
                records.append(match)
            elif not source_id or source_id not in match.get("sources", []):
                match["matches"] = int(match.get("matches", 1)) + 1
                match["last_seen"] = now
                if source_id:
                    match.setdefault("sources", []).append(source_id)
                    match["sources"] = match["sources"][-12:]

            self._write_unlocked(records)
            return dict(match)

    def set_status(self, correction_id: str, status: str) -> bool:
        if status not in self.VALID_STATUSES:
            raise ValueError("Unknown correction status")
        with self._lock:
            self._ensure_writable_unlocked()
            records = self._read_unlocked()
            match = next((item for item in records if item.get("id") == correction_id), None)
            if match is None:
                return False
            match["status"] = status
            match["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
            self._write_unlocked(records)
        return True

    def apply(self, text: str) -> str:
        rules = sorted(
            self.read("approved"),
            key=lambda item: len(item["spoken"]),
            reverse=True,
        )
        replacements = {}
        for item in rules:
            replacements.setdefault(item["spoken"].casefold(), item["replacement"])
        if not replacements:
            return text
        alternatives = "|".join(
            re.escape(spoken)
            for spoken in sorted(replacements, key=len, reverse=True)
        )
        pattern = re.compile(r"(?<!\w)(?:%s)(?!\w)" % alternatives, re.IGNORECASE)
        return pattern.sub(
            lambda match: replacements.get(
                match.group(0).casefold(),
                match.group(0),
            ),
            text,
        )

    def clear(self) -> int:
        with self._lock:
            records = self._read_unlocked()
            self._write_unlocked([])
        return len(records)

    def hotwords(self) -> str:
        values = []
        for item in self.read("approved"):
            value = item["replacement"]
            if value not in values:
                values.append(value)
        return ", ".join(values)

    def stats(self) -> dict:
        records = self.read()
        return {
            "pending": sum(item["status"] == "pending" for item in records),
            "approved": sum(item["status"] == "approved" for item in records),
            "rejected": sum(item["status"] == "rejected" for item in records),
        }


class HistoryStore:
    """Append-only local history with guarded audio retention."""

    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        self.path = self.root / "history.jsonl"
        self.audio_dir = self.root / "recordings"
        self._lock = threading.RLock()

    def add(
        self,
        *,
        original: str,
        final: str,
        duration: float = 0.0,
        latency: float = 0.0,
        delivery_latency: float = 0.0,
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
            "delivery_latency": round(float(delivery_latency), 3),
            "engine": engine,
            "profile": profile,
            "audio_path": audio_path,
            "source": source,
            "words": len(final.split()),
        }
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as out:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                os.fsync(out.fileno())
        return record

    def _read_unlocked(self, strict: bool = False) -> list[dict]:
        records = []
        try:
            with open(self.path, encoding="utf-8") as source:
                for line in source:
                    try:
                        record = json.loads(line)
                    except (TypeError, ValueError) as exc:
                        if strict:
                            raise ValueError(
                                "History contains unreadable data; original file kept"
                            ) from exc
                        continue
                    if isinstance(record, dict) and record.get("id"):
                        records.append(record)
                    elif strict:
                        raise ValueError(
                            "History contains unreadable data; original file kept"
                        )
        except FileNotFoundError:
            pass
        except OSError:
            if strict:
                raise
        records.reverse()
        return records

    def read(self) -> list[dict]:
        with self._lock:
            return self._read_unlocked()

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

    def _rewrite_unlocked(self, records: list[dict]) -> None:
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

    def rewrite(self, records: list[dict]) -> None:
        with self._lock:
            self._rewrite_unlocked(records)

    def save_correction(self, record_id: str, corrected: str) -> dict | None:
        corrected = str(corrected or "").strip()
        if not corrected:
            raise ValueError("Corrected text cannot be empty")
        with self._lock:
            records = self._read_unlocked(strict=True)
            record = next((item for item in records if item.get("id") == record_id), None)
            if record is None:
                return None
            record["corrected"] = corrected
            record["corrected_at"] = datetime.now().isoformat(timespec="seconds")
            self._rewrite_unlocked(records)
            return dict(record)

    def delete(self, record_id: str) -> bool:
        with self._lock:
            records = self._read_unlocked()
            victim = next((r for r in records if r.get("id") == record_id), None)
            if victim is None:
                return False
            audio_path = self._safe_audio_path(victim.get("audio_path", ""))
            self._rewrite_unlocked(
                [r for r in records if r.get("id") != record_id]
            )
            if audio_path and audio_path.exists():
                audio_path.unlink()
            return True

    def prune(self, days: int) -> int:
        if days <= 0:
            return 0
        with self._lock:
            cutoff = datetime.now() - timedelta(days=days)
            removed = 0
            keep = []
            for record in self._read_unlocked():
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
                self._rewrite_unlocked(keep)
            return removed

    def clear(self) -> int:
        with self._lock:
            records = self._read_unlocked()
            for record in records:
                audio_path = self._safe_audio_path(record.get("audio_path", ""))
                if audio_path and audio_path.exists():
                    audio_path.unlink()
            self._rewrite_unlocked([])
            return len(records)

    def stats(self, max_record: float = 0.0) -> dict:
        records = self.read()
        words = sum(int(r.get("words") or len(r.get("final", "").split())) for r in records)
        seconds = sum(float(r.get("duration") or 0) for r in records)
        latencies = [float(r.get("latency") or 0) for r in records if float(r.get("latency") or 0) > 0]
        delivery_latencies = sorted(
            float(r.get("delivery_latency") or 0)
            for r in records
            if float(r.get("delivery_latency") or 0) > 0
        )
        p95_index = max(0, int(np.ceil(len(delivery_latencies) * 0.95)) - 1)
        cutoff_warnings = sum(
            1 for r in records
            if max_record > 0
            and r.get("source", "dictation") == "dictation"
            and float(r.get("duration") or 0) >= max_record
        )
        recovered_sessions = sum(
            1 for r in records if r.get("source") == "recovery"
        )
        profiles = Counter(r.get("profile", "default") for r in records)
        return {
            "dictations": len(records),
            "words": words,
            "minutes": round(seconds / 60.0, 1),
            "average_latency": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            "median_delivery_latency": round(statistics.median(delivery_latencies), 3)
            if delivery_latencies else 0.0,
            "p95_delivery_latency": round(delivery_latencies[p95_index], 3)
            if delivery_latencies else 0.0,
            "timed_deliveries": len(delivery_latencies),
            "cutoff_warnings": cutoff_warnings,
            "recovered_sessions": recovered_sessions,
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

    def _audio_path(self, session_id: str) -> Path | None:
        if not self.SESSION_ID.fullmatch(str(session_id)):
            return None
        candidate = (self.directory / f"{session_id}.wav").resolve()
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

    def attach_audio(
        self,
        session_id: str,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> str:
        journal_path = self._path(session_id)
        audio_path = self._audio_path(session_id)
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if journal_path is None or audio_path is None or not journal_path.exists() or not len(samples):
            return ""
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{session_id}-", suffix=".wav.tmp", dir=self.directory,
        )
        os.close(fd)
        try:
            write_wav(temp_name, samples, sample_rate)
            with open(temp_name, "rb+") as source:
                os.fsync(source.fileno())
            os.replace(temp_name, audio_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return str(audio_path)

    def complete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if path is None or not path.exists():
            return False
        path.unlink()
        audio_path = self._audio_path(session_id)
        if audio_path and audio_path.exists():
            audio_path.unlink()
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
                "audio_path": str(audio_path)
                if (audio_path := self._audio_path(path.stem)) and audio_path.exists()
                else "",
            })
        return sessions


class DeliveryQueue:
    """Durable text that could not be inserted into its intended app."""

    RECORD_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$")

    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        self.path = self.root / "delivery-queue.jsonl"
        self._lock = threading.RLock()

    def add(
        self,
        text: str,
        *,
        target: dict | None = None,
        profile: str = "default",
        source: str = "dictation",
        reason: str = "delivery failed",
    ) -> dict:
        cleaned = str(text).strip()
        if not cleaned:
            raise ValueError("Queued delivery text cannot be empty")
        now = datetime.now()
        record = {
            "id": now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8],
            "timestamp": now.isoformat(timespec="seconds"),
            "text": cleaned,
            "target": {
                "process": str((target or {}).get("process", "")),
                "title": str((target or {}).get("title", "")),
                "hwnd": int((target or {}).get("hwnd", 0) or 0),
            },
            "profile": str(profile or "default"),
            "source": str(source or "dictation"),
            "reason": str(reason or "delivery failed"),
        }
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as out:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                os.fsync(out.fileno())
        return record

    def read(self) -> list[dict]:
        with self._lock:
            records = []
            try:
                with open(self.path, encoding="utf-8") as source:
                    for line in source:
                        try:
                            record = json.loads(line)
                        except (TypeError, ValueError):
                            continue
                        if (
                            isinstance(record, dict)
                            and self.RECORD_ID.fullmatch(str(record.get("id", "")))
                            and record.get("text")
                        ):
                            records.append(record)
            except OSError:
                pass
            records.reverse()
            return records

    def _rewrite(self, records: list[dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="delivery-", suffix=".tmp", dir=self.root)
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

    def complete(self, record_id: str) -> bool:
        if not self.RECORD_ID.fullmatch(str(record_id)):
            return False
        with self._lock:
            records = self.read()
            if not any(record.get("id") == record_id for record in records):
                return False
            self._rewrite([
                record for record in records
                if record.get("id") != record_id
            ])
        return True
