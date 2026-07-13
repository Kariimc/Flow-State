# Flow State

Local voice dictation for Windows. Hold or tap **Ctrl+Win**, speak, and the
text appears in whatever window you're using. Everything runs on your PC;
nothing is sent to the internet.

## First-time setup

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

This builds the Python environment and downloads the speech models. Do it
once. After that, use `run.bat` or the Desktop shortcut.

## Run It

It starts by itself when Windows boots. The **Flow State** Desktop icon opens
the Hub: history, recovery, dictionary, shortcuts, dictation behavior, audio, appearance,
privacy, file transcription, and stats.

1. Double-click `run.bat`, or open the Desktop shortcut.
2. Wait until Flow State says **Ready**.
3. Click into any app where you want text to appear.
4. Dictate either way:
   - **Hold Ctrl+Win**: speak, release to finish.
   - **Tap Ctrl+Win**: speak, then let silence stop it.
   - **Ctrl+Win+Space**: start or stop continuous dictation.
   - **Ctrl+Win+Shift+Space**: pause or resume that continuous session.
5. The slim floating pill shows recording/transcribing state. Drag it to move
   it; Flow State remembers the position.
6. Use the tray icon near the clock to open the Hub, restart, or quit.

To quit, press **Esc** twice quickly, use the tray menu, or close the console
window if one is open.

## How To Know It Worked

After you stop speaking, the transcript appears in the active app. The same
dictation is saved locally under `data/`.

While you speak, completed segments are also written to `data/recovery/`.
Successful dictations remove that temporary journal; an interrupted session
leaves it intact for the Recovery Inbox.

Open **Recovery** in the Hub to copy an interrupted transcript, retry delivery
to the app behind the Hub, or permanently remove it. Retry keeps the recovery
copy unless the delivered text is also saved successfully in History.
When a stopped recording has recoverable audio, the same page offers **Retry
transcription** and keeps the contained WAV until the new History item is safe.

Open **Delivery queue** when text could not be inserted. Each row keeps the
exact text and intended app. Retry is enabled only while Flow State can identify
that app; otherwise copy remains available and no other window receives the text.
Flow State also checks the foreground window again before every normal delivery;
switching apps while it transcribes holds the text here instead of misdirecting it.
Typing after recording stops also holds delivery, even if you stayed in the same
app, so your newer keyboard input is never overwritten by a late transcript.

## What It Does To Your Speech

- Removes filler words like "um", "uh", and "erm".
- Understands spoken punctuation: "comma", "period", "question mark",
  "new line", and "new paragraph".
- Keeps a 0.5-second pre-roll so your first word is less likely to be cut off.
- Can polish text into light local formats such as lists, email spacing, and
  app-aware writing profiles.

Turn on `VERBATIM` for exact transcripts with no cleanup.

## Dictionary And Vocabulary

Open `dictionary.txt` to add spoken replacements:

```text
kary => Karii
whisper flow => Wispr Flow
my email => kariimchiles@gmail.com
```

Left side = what you say. Right side = what Flow State types. Save the file;
changes apply on the next dictation.

Open `vocabulary.txt` to save product names, people, and acronyms whose
capitalization should be restored automatically.

## Settings

Open the Flow State Hub from the Desktop icon or tray menu. The Options screen
lets you change:

- `HOTKEY` - hold/tap dictation shortcut.
- `CONTINUOUS_HOTKEY` - continuous dictation shortcut.
- `PAUSE_HOTKEY` - pause/resume shortcut for the same continuous session.
- `COMMAND_HOTKEY` - selected-text command mode. Select text, press the
  command shortcut, speak an instruction like "make this shorter", then press
  again to replace the selection. With no selection, say "undo" or "redo".
- `UNDO_HOTKEY` and `REDO_HOTKEY` - scoped controls for the latest untouched
  Flow State insertion in the same target window.
- `ENGINE` - `"moonshine"` for fast English or `"whisper"` for broader
  language support.
- `INJECTION` - `"paste"` for speed or `"type"` for apps that block paste.
- `POLISH`, `VERBATIM`, and `PROFILE` - cleanup and writing behavior.
- `MICROPHONE`, `SOUND_CUES`, `SAVE_AUDIO`, `HISTORY_DAYS`, and `THEME`.

The tray also offers scoped Undo and Redo for the latest Flow State insertion.
They are available only while the same target window is active and no later
typing has occurred; Redo restores the exact saved text without retranscribing.

History items with saved audio include Reprocess Lab. It compares Verbatim,
Light, Notes, Email, and Coding previews from the saved raw transcript and lets
you copy any result without altering the original entry.

Statistics includes a local Reliability view with exact stop-to-insert median
and p95 for newly timed deliveries, pending Delivery count, completed recovery
count, and hard-cap cutoff warnings. Older records without exact paste timing
are excluded from those delivery percentiles.

The **Files & meetings** page can transcribe local WAV files now. System-audio
capture is available when Windows exposes a Stereo Mix input device.

## If Something Goes Wrong

- **Text does not appear but Flow State shows it** - some apps block paste.
  Try `INJECTION = "type"` or test in Notepad.
- **No audio captured** - check the microphone or choose an input device in
  the Hub.
- **First word missing** - increase `PRE_ROLL`.

## Performance Check

Run the repeatable local benchmark after changing startup, text cleanup,
history, or the overlay:

```powershell
.venv\Scripts\python.exe benchmark_flow.py
```

Add `--engine` to include loading and warming the configured speech model. The
report uses median and p95 timings so one unusually cold run stays visible
without distorting the typical result.

To measure the same bounded final segment used by live dictation, repeat
`--audio` for representative saved recordings and cap each sample to the
3.5-second VAD window:

```powershell
.venv\Scripts\python.exe benchmark_flow.py --engine `
  --moonshine-dir models\sherpa-onnx-moonshine-base-en-int8 `
  --audio data\recordings\example.wav --audio-rounds 5 `
  --max-audio-seconds 3.5
```

Flow State opens its overlay and Hub before the model finishes warming. The Hub
shows `Starting...`; WAV transcription and audio retry remain guarded until the
status changes to `Ready`. A startup failure is shown in the overlay and Hub.

For a real Windows delivery measurement, the native probe opens a uniquely
named temporary Notepad document, inserts through Flow State's production paste
path, verifies the exact saved payload, and closes only that test window:

```powershell
.venv\Scripts\python.exe native_delivery_benchmark.py `
  --model-dir models\sherpa-onnx-moonshine-base-en-int8 `
  --audio data\recordings\example.wav --rounds 5
```

Paste delivery returns immediately after `Ctrl+V`. Clipboard Shield waits 1.2
seconds on a background worker before restoring the original value, and skips
that restore if a person or another app changed the clipboard. Rapid Flow pastes
share the same original value instead of restoring an older transcript.

## Reinstall From Scratch

Delete `.venv` and `models/`, then run `setup.ps1` again. For contributor
notes and architecture, see `HANDOFF.md`; for research, see `RESEARCH.md`.
