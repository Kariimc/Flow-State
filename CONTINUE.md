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

Open Claude Code in the `whisper-flow-clone` folder and paste this kickoff prompt:

> I'm continuing the Whisper Flow clone on a new laptop. Read HANDOFF.md,
> PROGRESS.md, and RESEARCH.md, then confirm the app runs here (`.\run.bat`,
> dictate a test line into Notepad). The machine changed — re-check the CPU
> for AVX2 and adjust the engine choice if this box is more capable (Moonshine
> is the safe default; on an AVX2 CPU, faster-whisper `small`/`distil` or a
> local-LLM cleanup pass in the `clean_text` seam become viable). Then let's
> work through the roadmap in HANDOFF.md §8, and set up the MCP servers I need.

HANDOFF.md is the engineering brief (architecture, threading, gotchas).
PROGRESS.md is the live working log. RESEARCH.md is the cited design rationale.

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
