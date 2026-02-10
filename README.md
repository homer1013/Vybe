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
- **`vybe run ...`** streams output live *and* saves it.
- **`vybe retry`** reruns your last `vybe run` command.
- **`vybe snipclip`** copies *output only* (perfect for issues/ChatGPT).
- **`vybe snipclip --redact`** copies output with common secrets masked.
- **`vybe errors`** extracts likely error blocks from latest capture.
- **`vybe export --last --json`** emits machine-readable context for agents.
- **`vybe run --tag <name>`** groups captures by task/session.
- **`vybe diff`** shows what changed between your latest two captures.
- **`vybe share`** builds a Markdown-ready report for issues/LLM chats.
- **`vybe prompt`** generates LLM-ready prompts for debug/review/explain workflows.
- **`vybe doctor`** prints a fast environment snapshot for debugging setup issues.
- **`vybe fail`** jumps back to the most recent failing run.
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
vybe run pytest -q
vybe retry
vybe r pytest -q
vybe run --tag auth pytest -q
vybe rr --cwd
vybe fail
vybe s
vybe sc
vybe sc --redact
vybe ll 5
vybe ls --tag auth
vybe snipclip
vybe errors
vybe export --last --json --snip
vybe diff
vybe share --redact --errors
vybe share --clip
vybe share --json
vybe share --json --errors --redact
vybe prompt debug --redact
vybe prompt review
vybe prompt explain
vybe doctor
vybe self-check
vybe cfg
vybe init
vybe completion install zsh
vybe md bash
vybe grep "Traceback|ERROR" --i
```

## Speed aliases
- `vybe r ...` is the same as `vybe run ...`
- `vybe rr` is the same as `vybe retry`
- `vybe rr --cwd` retries in the original working directory
- `vybe rr --tag <name>` retries and assigns a tag
- `vybe l` is the same as `vybe last`
- `vybe s` is the same as `vybe snip`
- `vybe sc` is the same as `vybe snipclip`
- `vybe o` is the same as `vybe open`
- `vybe ll [N]` is the same as `vybe ls [N]`
- Full commands remain the canonical docs and are recommended in scripts/automation

## Quick recipes
Fast debug loop:
```bash
vybe r pytest -q
vybe errors
vybe share --redact --errors --clip
vybe rr
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
vybe doctor
vybe doctor --json
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
