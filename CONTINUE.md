# Continuing on a new machine

Everything needed to pick this project up on another Windows PC. The code is on
GitHub (private): **github.com/Kariimc/whisper-flow-clone**.

## 1. Install the prerequisites

- **Git** — https://git-scm.com/download/win
- **GitHub CLI** — https://cli.github.com  (or `winget install GitHub.cli`)
- **uv** (Python manager) — `winget install astral-sh.uv`
  (setup.ps1 falls back to the `py` launcher + a Python 3.12 install if uv
  is absent)

## 2. Get the code and run it

```powershell
gh auth login                              # sign in as Kariimc
gh repo clone Kariimc/whisper-flow-clone
cd whisper-flow-clone
powershell -ExecutionPolicy Bypass -File setup.ps1   # builds .venv, downloads models
.\run.bat
```

Autostart, the desktop icon, sound cues, and the app icon all regenerate on
first launch. Your old `history.txt`, `settings.json`, and personal dictionary
rules are NOT in the repo (git-ignored) — they stay on the old laptop. Copy
`dictionary.txt` over by hand if you want your rules.

## 3. Resume with Claude Code

Open Claude Code in the `whisper-flow-clone` folder and paste the kickoff prompt
below. It's written to make the agent orient itself, prove the app actually
works on this machine before touching anything, and only then move on to
features — in that order, so nothing gets built on a broken base.

> I'm picking up **Flow State** (`flow.py`) on a **new Windows
> laptop**. It's a local, fully-offline voice-dictation app. Do the following
> in order and stop to tell me if any step fails before moving on.
>
> **1 — Orient.** Read `HANDOFF.md` (engineering brief: architecture,
> threading, gotchas — read §6 "Gotchas" carefully), `PROGRESS.md` (working
> log / current state), and skim `RESEARCH.md` (cited design rationale + the
> roadmap table). Give me a 3-4 sentence summary of where the project stands so
> I know you've loaded the context, then proceed.
>
> **2 — Profile this machine.** The whole engine choice is driven by hardware,
> and the laptop just changed. Report: CPU model, core count, **whether it
> supports AVX2** (`Get-CimInstance Win32_Processor` / check flags), total RAM,
> and any usable GPU. The old box was a Pentium Gold 5405U (2 cores, *no* AVX2,
> 3.8 GB RAM) — tell me how this one compares.
>
> **3 — Set up and launch.** Run `powershell -ExecutionPolicy Bypass -File
> setup.ps1` (creates `.venv`, downloads the ~275 MB of models), then
> `.\run.bat`. Wait for "Ready". If setup fails, diagnose it (common causes:
> `uv` missing, Python version, model download blocked) before continuing.
>
> **4 — Prove it works end-to-end.** Verify a real dictation: hold **Ctrl+Win**,
> speak a test sentence into Notepad, release, and confirm the text is inserted.
> Then check tap-mode (auto-stop) and that the waveform overlay appears. Follow
> the repo's testing approach (HANDOFF.md §7) — drive the real components, don't
> just assert on strings. Report timing: how long from release to text.
>
> **5 — Tune the engine to this hardware.** Moonshine (int8, sherpa-onnx) is the
> safe default and stays correct everywhere. But *if this box has AVX2 and more
> headroom*, tell me what's now viable that wasn't on the old machine —
> faster-whisper `small`/`distil-large` for better accuracy / other languages,
> and especially a **local-LLM "deep clean" pass** dropped into the `clean_text`
> seam (see HANDOFF.md §2 and RESEARCH.md §5). Recommend a config; change
> `ENGINE` only with my sign-off.
>
> **6 — Restore my personal data.** `history.txt`, `settings.json`, and my
> personal dictionary rules are git-ignored, so they did NOT come over with the
> clone. If I've copied any of them into the folder, wire them up; otherwise
> remind me to bring my `dictionary.txt` rules from the old laptop and confirm
> the app picks them up live.
>
> **7 — Then let's work.** Walk me through the roadmap in **HANDOFF.md §8** /
> the RESEARCH.md roadmap table and recommend the highest-value next feature for
> this hardware. Separately, help me set up the **MCP servers** for my broader
> Claude Code setup — run `claude mcp list`, then we'll add and authorize each
> one I use (§4 below).
>
> Keep `PROGRESS.md` updated as we go, and flag anything in the gotchas list
> that this hardware change might affect.

Why this prompt is shaped this way: it forces the agent to *verify before it
builds* (steps 3-4), front-loads the one fact the whole architecture hinges on
(AVX2, step 2), and calls out the git-ignored personal data (step 6) that the
naïve "just clone and run" path silently drops. HANDOFF.md is the engineering
brief, PROGRESS.md is the live working log, and RESEARCH.md is the cited design
rationale.

## 4. MCP servers (the setup we'll do together)

This app itself needs no MCP servers — `git` and the `gh` CLI cover the whole
workflow. The MCP work is about your broader Claude Code setup. On the new
laptop, in an interactive Claude Code session:

- `claude mcp list` — see what's configured.
- `claude mcp add <name> -- <command>` — add a local/stdio server.
- `/mcp` — inside a session, authorize the OAuth-based connectors (GitHub,
  Notion, Slack, etc.). Those can't be authorized from a non-interactive run.

Bring the list of MCPs you actually use and we'll get each one connected and
verified.

## 5. What's left to build

See **HANDOFF.md §8**. Short version: per-app tone profiles, optional local-LLM
"deep clean", streaming partial text in continuous mode, Hub usage stats, and a
Nuitka/Inno installer so it runs without the Python setup.
