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
the Hub: history, dictionary, shortcuts, dictation behavior, audio, appearance,
privacy, file transcription, and stats.

1. Double-click `run.bat`, or open the Desktop shortcut.
2. Wait until Flow State says **Ready**.
3. Click into any app where you want text to appear.
4. Dictate either way:
   - **Hold Ctrl+Win**: speak, release to finish.
   - **Tap Ctrl+Win**: speak, then let silence stop it.
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
- `COMMAND_HOTKEY` - selected-text command mode. Select text, press the
  command shortcut, speak an instruction like "make this shorter", then press
  again to replace the selection.
- `ENGINE` - `"moonshine"` for fast English or `"whisper"` for broader
  language support.
- `INJECTION` - `"paste"` for speed or `"type"` for apps that block paste.
- `POLISH`, `VERBATIM`, and `PROFILE` - cleanup and writing behavior.
- `MICROPHONE`, `SOUND_CUES`, `SAVE_AUDIO`, `HISTORY_DAYS`, and `THEME`.

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

## Reinstall From Scratch

Delete `.venv` and `models/`, then run `setup.ps1` again. For contributor
notes and architecture, see `HANDOFF.md`; for research, see `RESEARCH.md`.
