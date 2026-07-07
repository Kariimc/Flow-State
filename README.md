# Flow State

Local voice dictation for Windows. Hold or tap **Ctrl+Win**, speak, and the
text appears in whatever window you're using. Everything runs on your PC —
nothing is sent to the internet.

## First-time setup

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

This builds the Python environment and downloads the speech models (~60 MB).
Do it once. After that, use `run.bat`.

## Run it

It starts by itself when Windows boots (grey microphone in the system
tray). The **Flow State icon on your Desktop** opens the Hub — history,
dictionary, and an Options tab for tweaks (hotkey, engine, verbatim mode,
auto-stop timing, "start with Windows" on/off). Manual start:

1. Double-click `run.bat` in this folder.
2. Wait until the window says **Ready** (about 15 seconds).
3. Click into any app (email, doc, chat) where you want text to appear.
4. Dictate either way, with the same keys:
   - **Hold Ctrl+Win** like a walkie-talkie — speak, release to finish, or
   - **Tap Ctrl+Win** — speak, and it stops by itself after ~1.5 s of
     silence (or tap again to stop right away).
   A slim floating bar appears at the bottom-center of the screen, just
   above the taskbar (the same spot Wispr Flow uses). While it listens,
   six ink curves trace your voice on a paper-white pill — deep tones
   swell the slow vermilion wave, higher tones ripple the fast teal ones.
   An amber dot with a flowing wave means it's transcribing, then your
   words are pasted in.
   **Drag the bar** to move it — it snaps to the bottom-center,
   bottom-left, bottom-right, or top-center of the screen when dropped
   near one of those spots, parks exactly where you drop it otherwise,
   and remembers its place after a restart.
5. There's also a microphone icon in the system tray (bottom-right, near
   the clock — it may hide under the `^` arrow). Grey = ready, red =
   recording, orange = transcribing. Right-click it to open your
   dictionary, your history, or to quit.
6. To quit, press **Esc** twice quickly, use the tray menu, or close the
   black window.

## How to know it worked

After you stop, the black window shows the recognized text next to a `→`,
and the same text appears in the app you clicked into. Every dictation is
also saved to `history.txt` in this folder.

## What it does to your speech (unless you turn it off)

- Removes filler words: "um", "uh", "erm"…
- Spoken punctuation works: say "comma", "period", "question mark",
  "new line", "new paragraph".
- Keeps a 0.5-second pre-roll so your first word isn't cut off.

Want the exact words with no cleanup? Set `VERBATIM = True` (see below).

## Your personal dictionary

Open `dictionary.txt` in Notepad and add one rule per line:

```
kary => Karii
whisper flow => Wispr Flow
my email => kariimchiles@gmail.com
```

Left side = what you say, right side = what gets typed. Use it to fix names
the model mishears, or as spoken shortcuts that expand into anything (an
address, a link, a whole signature). Just save the file — changes apply on
your very next dictation, no restart needed.

## Settings

Open `flow.py` in Notepad — the block at the top lets you change:

- `HOTKEY` — the dictation key or combo (default `ctrl+windows`; a single
  key like `f8` works too. `fn` can't be used — laptops handle that key in
  hardware and Windows never sees it)
- `ENGINE` — `"moonshine"` (default: fast, English-only) or `"whisper"`
  (any language, but ~14× slower on this PC)
- `INJECTION` — `"paste"` (default: instant, restores your old clipboard)
  or `"type"` (types character by character; try this if pasting fails)
- `VERBATIM` — `True` for exact transcripts with zero cleanup
- `AUTO_STOP` — seconds of silence that end a tap-started dictation
  (`0` turns auto-stop off; holding the key is never auto-stopped)
- `LANGUAGE` — only for the whisper engine; `None` auto-detects

## If something goes wrong

- **Text doesn't appear but the window shows it** — some apps (admin
  windows, games) block pasting; set `INJECTION = "type"`, or copy it from
  `history.txt`. Test in Notepad to confirm the tool itself works.
- **"No audio captured"** — check your microphone is plugged in and is the
  Windows default input device (Settings → System → Sound).
- **First word missing** — increase `PRE_ROLL` to `1.0`.

## Reinstall from scratch

Delete `.venv` and `models/`, then run `setup.ps1` again. For contributors and
the full architecture, see [HANDOFF.md](HANDOFF.md); for the research behind the
design choices, [RESEARCH.md](RESEARCH.md).
