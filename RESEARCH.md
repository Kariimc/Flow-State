# Research: How Wispr Flow Works & What Flow State Needs

*Compiled 2026-07-02 from four parallel research passes (product docs, technical
architecture, open-source landscape, hardware feasibility) plus community
feedback mining. Source links inline; items marked (unverified) could not be
confirmed against primary sources.*

This is the original research snapshot, not a live competitor tracker. Current
implementation status and later validation live in `DIFFERENTIATORS.md` and
`PROGRESS.md`.

## 1. How Wispr Flow actually works

**Interaction model.** Hold a key to dictate (Windows default `Ctrl+Win`),
release to finish; double-tap or `Ctrl+Win+Space` for hands-free toggle.
Audio + context stream to the cloud *while you speak*, and the finished text
is pasted at the cursor via clipboard + simulated `Ctrl+V` (`Shift+Insert` in
IDE terminals). Sessions cap at 20 minutes.
[Hotkeys](https://docs.wisprflow.ai/articles/2612050838-supported-unsupported-keyboard-hotkey-shortcuts) ·
[Paste behavior](https://docs.wisprflow.ai/articles/7971211038-fix-text-not-pasting-after-dictation)

**Pipeline.** Nothing runs locally except context reading. Audio goes over
gRPC to custom ASR models hosted on Baseten, then a **fine-tuned Llama**
(TensorRT-LLM, 100+ tokens in <250 ms) applies formatting, filler removal,
tone, and dictionary — the whole round trip targets p99 < 700 ms.
[Baseten case study](https://www.baseten.co/resources/customers/wispr-flow/) ·
[Their latency post](https://wisprflow.ai/post/technical-challenges) ·
[Data controls](https://wisprflow.ai/data-controls)

**Feature set.** Smart formatting (punctuation, capitalization, fillers),
Backtrack ("scratch that" / restating yourself fixes the text), Command Mode
(voice-edit selected text, paid tier), personal dictionary + text
replacements, snippets (60-char trigger → 4,000-char expansion), per-app tone
(Flow Styles: formal email vs casual Slack), context awareness (reads text
near your cursor, app name, Slack conversation history via accessibility
APIs), 100+ languages with auto-detect, whisper-quiet mode, history/notes hub.
[Smart formatting](https://docs.wisprflow.ai/articles/5373093536-how-do-i-use-smart-formatting-and-backtrack) ·
[Command Mode](https://docs.wisprflow.ai/articles/4816967992-how-to-use-command-mode) ·
[Context awareness](https://docs.wisprflow.ai/articles/4678293671-feature-context-awareness)

**Privacy reality.** By default audio/transcripts may be used for training;
an independent investigation found local SQLite storage of raw audio,
screenshots and URLs, a system-wide keystroke hook, and hourly metadata
uploads even when sharing is off.
[Investigation](https://www.wensenwu.com/thoughts/wispr-flow-investigation) ·
[HN discussion](https://news.ycombinator.com/item?id=47781148)

## 2. What the community asks for (top 10)

1. **Offline/local processing** — #1 by far; a whole ecosystem of local clones exists ([277-point HN thread](https://news.ycombinator.com/item?id=47040375))
2. **Privacy** — no screenshots, no app/URL tracking, no idle phoning home
3. **Reliability** — cloud outages; "works 60% of the time" complaints ([outage log](https://www.getvoibe.com/resources/is-wispr-flow-reliable/))
4. **Lower resource usage** — Electron app idles at ~800 MB RAM
5. **Verbatim mode** — the AI "over-edits" what people actually said
6. **Real-time streaming text** — words while you speak (why users switch to Aqua Voice)
7. **Custom dictionary / replacements**
8. **One-time price** — $144/yr, no lifetime option
9. **BYOK / local-LLM cleanup** (e.g. Ollama)
10. **Deeper voice commands** — editing, hands-free control

## 3. Open-source table stakes (from surveying 12+ projects)

Table stakes: local whisper.cpp/faster-whisper engine, hold **and** toggle on
one hotkey, tray icon + recording overlay, VAD, **clipboard-paste injection
with keystroke fallback**, model picker, record-then-transcribe at 16 kHz.
Differentiators: per-app profiles (VoiceInk "Power Mode"), pre-roll buffer,
Ollama cleanup, voice commands. Notable: all four biggest apps (Handy,
Whispering, OpenWhispr, VoiceInk) added **Parakeet/Moonshine** as CPU-fast
alternatives to Whisper.
[Handy](https://github.com/cjpais/Handy) ·
[whisper-writer](https://github.com/savbell/whisper-writer) ·
[whisper-local](https://github.com/drajb/whisper-local) ·
[VoiceInk](https://github.com/Beingpax/VoiceInk)

## 4. Our hardware constraints (measured on this PC)

Pentium Gold 5405U: 2 cores/4 threads, 2.3 GHz, **no AVX/AVX2** (SSE4.2 only),
3.8 GB RAM (<1 GB typically free), no usable GPU.

- faster-whisper (CTranslate2) falls back to its generic SSE path without
  AVX2 — measured **~35 s to transcribe 4 s of audio** (base, int8) here.
- **Moonshine base int8 via sherpa-onnx: ~1–2.5 s for the same clip, same
  output** — better published WER than Whisper base, 58 MB model, no AVX
  requirement, variable-length audio (no 30 s padding penalty).
  [Moonshine paper](https://arxiv.org/abs/2410.15608) ·
  [sherpa-onnx models](https://k2-fsa.github.io/sherpa/onnx/moonshine/index.html)
- Whole app measured at ~316 MB RAM with Moonshine loaded — fits the budget.
- Whisper `small`, large-v3-turbo, Parakeet 0.6B: too big/slow for this RAM.
- Streaming (word-by-word) transcription needs faster-than-real-time
  inference; not realistic here except via Vosk (lower accuracy).

## 5. Local-model path (LLM cleanup later)

A local LLM for Wispr-style rewriting is **not viable on this machine**
(Qwen2.5-0.5B Q4 ≈ 5–12 tok/s estimated → 5–20 s per dictation, competing
with the ASR for the same 2 cores). The plan that keeps the door open:

- **Now**: rule-based cleanup (fillers, spoken punctuation) — implemented.
  Same interface an LLM would have: `clean_text(raw) -> text`.
- **Later / better hardware**: swap `clean_text` for a call to a small local
  model (Qwen2.5-0.5B/1.5B via llama.cpp or Ollama) doing Backtrack-style
  edits, tone, and dictionary application. llama.cpp runs without AVX2, so
  even this PC could offer it as an optional slow "deep clean".
- Engine abstraction (`MoonshineEngine` / `WhisperEngine`) means new ASR
  models (Parakeet, Canary, multilingual Moonshine) are drop-in.

## 6. Feature roadmap outcome

The approved roadmap is now shipped on `main`: the full Hub settings workspace,
per-app profiles, selected-text commands, file transcription, local statistics,
and the ten guarded reliability features in `DIFFERENTIATORS.md`. Durable JSONL
history, saved audio, Recovery Inbox, and Delivery queue now supersede the
original `history.txt`-only design described in this research snapshot.

Future candidates need a new product decision: optional local-LLM deep clean,
true word-level streaming preview, and installer packaging. The earlier idea of
adding voice commands is complete; selected-text commands and scoped spoken
undo/redo are already in the app.
