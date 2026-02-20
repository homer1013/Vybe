# Vybe

```text
  ____   ____       _
  \   \ /   /__ __ | |__   ____
   \   Y   /|  |  ||  _  \/ __ \
    \     / _\    || |_)  |  __/
     \___/ (_____/ |_____/\____)  
```

Vybe is a **vibe coding terminal toolkit**: run a command, capture its output, and instantly reuse it —
copy to clipboard, wrap in Markdown, search errors, jump to the last failure, or grab tmux scrollback.

## Why Vybe?
Without Vybe:
- Run command
- Scroll/copy terminal output manually
- Redact secrets by hand
- Reformat for LLM/issue tracker
- Repeat after each retry

With Vybe:
- `vybe r ...` run + capture
- `vybe errors` isolate failures
- `vybe sc --redact` copy safe output fast
- `vybe prompt debug --redact` generate LLM-ready prompt
- `vybe rr` retry quickly

## Highlights

**Core Capture & Replay:**
- **`vybe run ...`** streams output live *and* saves it.
- **`vybe retry`** / **`vybe rr`** reruns your last command.
- **`vybe snipclip`** / **`vybe sc`** copies output only (perfect for issues/LLM chats).
- **`vybe snipclip --redact`** masks common secrets automatically.

**Interactive Commands (v1.1.0+):**
- **`vybe run --tty ...`** allocate TTY for sudo and password prompts.
- Auto-detects sudo usage and GUI apps (Tkinter, Qt, Wx) with helpful warnings.
- File error detection: fuzzy-suggests similar files when command not found.

**LLM Workflow (v1.0.0+):**
- **`vybe cc`** copy just the command to clipboard (for tweaking).
- **`vybe history [N]`** bulk grab last N runs for LLM handoff.
- **`vybe select`** interactive fzf picker for multi-select captures.
- **`vybe share --smart`** (v1.1.0+) auto-bundle full context: pwd, ls, git status, venv.

**Better Diagnostics (v1.1.0+):**
- **`vybe doctor --explain`** human-readable environment checks with actionable guidance.
- **`vybe project`** / **`vybe proj`** show project structure and metadata.

**Analysis & Discovery:**
- **`vybe errors`** extracts likely error blocks from latest capture.
- **`vybe stats`** show success rates, most-run commands, slowest runs.
- **`vybe fail`** jump back to most recent failing run.
- **`vybe diff`** show what changed between latest two captures.

**Advanced Workflows:**
- **`vybe flow`** save and replay command sequences.
- **`vybe watch`** auto-rerun on file changes.
- **`vybe cwd`** remember/restore working directory.
- **`vybe clean`** cleanup old captures by age/count.
- **`vybe man`** comprehensive 601-line manual with all commands.

**Export & Share:**
- **`vybe export --last --json`** machine-readable context for agents.
- **`vybe share`** builds Markdown-ready report for issues.
- **`vybe prompt`** generates LLM-ready prompts (debug/review/explain).
- **`vybe doctor`** fast environment snapshot.
- Works great on Kali (zsh) and supports tmux scrollback capture.

## Demo
Quick terminal demo recording (asciinema):
```bash
asciinema rec docs/demo.cast
# run a loop like:
# vybe r pytest -q
# vybe errors
# vybe prompt debug --redact
# vybe rr
```

You can convert to GIF with `agg` or share the cast directly.

## Install (dev / from source)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
vybe --help
python -m vybe --help
```

## Install (recommended on Kali/Ubuntu)
Use `pipx` to avoid PEP 668 "externally-managed-environment" issues:
```bash
sudo apt install pipx
pipx ensurepath
pipx install vybe
```

From a local checkout:
```bash
cd ~/dev/Vybe
pipx install . --force
```

Check install/update guidance:
```bash
vybe self-check
vybe self-check --json
```

## Publishing (maintainers)
Vybe publishes to PyPI from GitHub tags via Trusted Publishing.

One-time setup in PyPI project settings:
- Add a Trusted Publisher for repo `homer1013/Vybe`
- Workflow file: `.github/workflows/publish.yml`
- Environment: `pypi`

Release flow:
```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

GitHub Actions will build and publish automatically.

## Usage
```bash
# Capture & replay
vybe run pytest -q
vybe r pytest -q
vybe run --tty sudo systemctl restart nginx    # Interactive/sudo
vybe retry
vybe rr
vybe rr --cwd

# Output & clipboard
vybe snip
vybe snipclip
vybe snipclip --redact
vybe clip            # Copy entire last capture (command + output)
vybe cc              # Copy just command
vybe history 3       # Bulk grab 3 runs for LLM
vybe select          # Interactive picker (fzf)

# Smart context bundling (v1.1.0+)
vybe share --smart --redact --clip   # Auto-gather pwd, ls, git, venv
vybe share --smart --json

# Analysis
vybe fail
vybe errors
vybe stats           # Success rates, patterns
vybe tail 50
vybe grep "Traceback|ERROR" --i

# Navigation & filtering
vybe ls
vybe ll 5
vybe ls --tag auth
vybe open

# Project & diagnostics (v1.1.0+)
vybe project         # Show structure, venv, requirements
vybe proj --json
vybe doctor --explain    # Human-readable environment checks

# Workflows
vybe flow save test-run      # Save sequence
vybe flow list
vybe flow run test-run
vybe watch pytest -q         # Auto-rerun on changes
vybe cwd set                 # Save working dir
vybe cwd run                 # Restore & run
vybe clean --keep 10         # Cleanup old

# Diff & tagging
vybe diff
vybe diff --tag auth
vybe run --tag auth pytest -q

# Export & share
vybe export --last --json --snip --redact
vybe share --redact --errors --clip
vybe share --smart --redact --clip    # Auto-bundle context (v1.1.0+)
vybe share --json
vybe prompt debug --redact

# System & help
vybe man             # Read comprehensive manual
vybe doctor --explain                # Human-readable diagnostics (v1.1.0+)
vybe project                         # Project snapshot (v1.1.0+)
vybe self-check
vybe cfg
vybe init
vybe completion install zsh
vybe md bash
```

## Speed aliases
- `vybe r <cmd>` → `vybe run <cmd>`
- `vybe rr [--cwd] [--tag <name>]` → `vybe retry [--cwd] [--tag <name>]`
- `vybe l` → `vybe last`
- `vybe s` → `vybe snip`
- `vybe sc` → `vybe snipclip`
- `vybe cc` → `vybe cmdcopy`
- `vybe o` → `vybe open`
- `vybe ll [N]` → `vybe ls [N]`
- `vybe proj [--json]` → `vybe project [--json]` (v1.1.0+)
- Full commands remain the canonical docs and are recommended in scripts/automation

## Quick recipes

Fast debug loop:
```bash
vybe r pytest -q
vybe errors
vybe share --redact --errors --clip
vybe rr
```

LLM Handoff with full context (v1.1.0+):
```bash
vybe r pytest -q
vybe share --smart --redact --clip  # Auto-bundle pwd, ls, git, venv
# Or bulk multiple runs:
vybe history 3 --redact             # Grab last 3 runs
vybe prompt debug --redact          # Generate LLM prompt
```

LLM Handoff (v1.0.0+):
```bash
vybe r pytest -q
vybe history 3 --redact     # Grab last 3 runs
vybe prompt debug --redact  # Generate LLM prompt
```

Interactive multi-run selection:
```bash
vybe r pytest test1
vybe r pytest test2
vybe r pytest test3
vybe select                 # Pick which ones to copy
```

Tagged task loop:
```bash
vybe run --tag auth pytest -q
vybe rr --tag auth
vybe ls --tag auth
vybe diff --tag auth
```

Agent handoff loop:
```bash
vybe export --last --json --snip --redact
vybe share --json --errors --redact
vybe prompt debug --redact
vybe doctor --json
```

## LLM-friendly JSON export
Use this to hand structured context to coding agents.
```bash
vybe export --last --json
vybe export --last --json --snip
vybe export --last --json --snip --redact
```

## Tagging and diffs
Use tags to keep one debugging thread grouped:
```bash
vybe run --tag auth pytest -q
vybe rr --tag auth
vybe ls --tag auth
vybe tags
```

See exactly what changed between your latest two captures:
```bash
vybe diff
vybe diff --tag auth
vybe diff --full
```

## Share bundles and doctor
Generate a ready-to-paste Markdown bundle:
```bash
vybe share
vybe share --redact --errors
vybe share --clip
vybe share --json
vybe share --json --errors --redact
vybe prompt debug --redact
vybe prompt review --redact
vybe prompt explain --redact
```

Get quick environment diagnostics:
```bash
vybe doctor              # Quick snapshot
vybe doctor --explain    # Human-readable with guidance (v1.1.0+)
vybe doctor --json
vybe project             # Show project structure (v1.1.0+)
vybe self-check
vybe self-check --json
vybe cfg --json
vybe init
```

## CLI stability
Vybe keeps a stable v1 CLI contract for humans, scripts, and agents:
- See `docs/CLI_CONTRACT.md`
- Machine-readable JSON outputs are additive: existing keys remain, new keys may be added

## Examples
See `examples/` for real workflows:
- `examples/pytest-debug-loop.md`
- `examples/frontend-build-failure.md`
- `examples/serial-monitor-nonutf8.md`

## Agent quickstart (human + LLM loop)
Use this when pairing with ChatGPT/Codex/Claude during debugging.

1) Run and capture
```bash
vybe r pytest -q
```

2) Copy output-only to clipboard for your LLM
```bash
vybe sc
```

3) Apply changes, then retry quickly
```bash
vybe rr
```

4) If you moved directories, retry in the original working dir
```bash
vybe rr --cwd
```

5) Check recent attempts fast
```bash
vybe ll 8
```

Failure-first loop:
```bash
vybe fail
vybe s
vybe sc
```

Tip for agents and scripts:
- Prefer full commands in automation (`vybe run`, `vybe retry`) for clarity.
- Use aliases interactively for speed.

### Command reference
Run:
```bash
vybe --help
```

## Clipboard support
Vybe auto-detects clipboard tools:
- X11: `xclip` or `xsel`
- Wayland: `wl-copy`

## Shell completion install
Install directly from the CLI:
```bash
vybe completion install zsh
vybe completion install bash
vybe completion install fish
```

## tmux scrollback capture
```bash
vybe pane 4000
vybe open
```

## Environment variables
- `VYBE_DIR` log dir (default `~/.cache/vybe`)
- `VYBE_STATE` state file (default `~/.config/vybe/state.json`)
- `VYBE_INDEX` index file (default `~/.cache/vybe/index.jsonl`)
- `VYBE_CONFIG` config file (default `~/.config/vybe/config.json`)
- `VYBE_MAX_INDEX` max index entries (default `2000`)

## Shell completions
See `completions/`:
- bash: `completions/vybe.bash`
- zsh: `completions/_vybe`
- fish: `completions/vybe.fish`

Use `vybe completion install <shell>` instead of copying files manually.

## License
MIT
