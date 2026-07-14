# Continuing Flow State

Use this guide to resume the project on this laptop or move it to another
Windows PC. The private repository is `github.com/Kariimc/Flow-State`.

## Current Snapshot

The reliability bundle and waveform text fix are on `main`. The app is split
across `flow.py` (runtime), `flow_features.py` (durable data and text features),
and `flow_hub.py` (Hub UI). The verified suite contains 97 tests, including 14
native Tk page/button tests. `PROGRESS.md` is the live source of truth for the
exact commit, measurements, and current next action.

## Set Up Another Windows PC

Install Git plus either `uv` or Python 3.12, then:

```powershell
git clone https://github.com/Kariimc/Flow-State.git
cd Flow-State
powershell -File setup.ps1
.\run.bat
```

`setup.ps1` creates `.venv`, installs `requirements.txt`, downloads the speech
and VAD models, and creates the Desktop shortcut. The first launch generates
sound cues, the desktop icon, and the separate microphone tray icon. Autostart
is controlled from General settings in the Hub.

The Desktop shortcut opens the Hub. `run.bat` and `run.vbs` start the resident
tray app quietly; launching the shortcut while it is already running sends a
`hub` message to that one resident instance.

## Move Personal Data

The repository intentionally excludes runtime data and generated assets:

- `data/` - JSONL history, saved recordings, recovery journals, and delivery queue
- `settings.json` - shortcuts, theme, microphone, retention, and behavior
- `overlay_pos.txt` - floating waveform position
- `models/` - downloaded models plus generated icon and sound files

`dictionary.txt` and `vocabulary.txt` are tracked starter files. Review them
before pushing if they contain personal replacements, names, or contact details.
Copy personal runtime data only from a backup you trust, and never replace a
newer `data/` folder blindly.

## Resume Development

1. Read `PROGRESS.md` and `HANDOFF.md` before editing.
2. Confirm `git status --short --branch` and compare it with `PROGRESS.md`.
3. Run the full suite from the repository root:

```powershell
.venv\Scripts\python.exe -m unittest -v
.venv\Scripts\python.exe -m py_compile flow.py flow_features.py flow_hub.py `
  test_flow_features.py test_flow_hub.py test_flow_runtime.py `
  benchmark_flow.py native_delivery_benchmark.py
```

4. Launch one instance and verify `--hub` reaches it through IPC.
5. For runtime changes, finish with a real Notepad insertion and the focused
   native UI check described in `HANDOFF.md`.

## Current Next Action

No repository work remains from the ten-feature reliability bundle. Do not
install competitor desktop apps unless Kariim explicitly chooses a same-machine
desktop comparison. The completed no-install comparison is browser-only
evidence and must not be described as desktop-app superiority.
