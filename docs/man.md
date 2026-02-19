# Vybe Manual

Vybe is a vibe coding terminal capture toolkit for developers who pair with LLMs, debug iteratively, and need fast context handoff.

## Quick Start

```bash
# Capture a run
vybe r pytest -q

# Copy output to clipboard
vybe sc

# Extract errors
vybe errors

# Generate LLM-ready prompt
vybe prompt debug --redact

# Retry
vybe rr
```

## Core Commands

### `vybe run [--tag <name>] <cmd...>` / `vybe r`

Run a command, show output live, and save to a log file. The output appears in your terminal exactly as it would without Vybe, but it's also persisted for later access.

**Examples:**
```bash
vybe r pytest -q
vybe run --tag auth-tests pytest tests/auth/ -q
vybe r npm run build
```

**Output:** Saves to `~/.cache/vybe/vybe_TIMESTAMP.log`

**State:** Updates "last" state so other commands can access it.

### `vybe retry` / `vybe rr`

Re-run your last command. Useful for quick iterations—change code, then retry.

**Flags:**
- `--cwd` — Run in the original working directory (in case you've cd'd elsewhere)
- `--tag <name>` — Assign a new tag to this run

**Examples:**
```bash
vybe rr
vybe rr --cwd
vybe rr --tag attempt-2
```

### `vybe last` / `vybe l`

Print the full last capture (command + output).

```bash
vybe l | head -50
```

### `vybe snip [--redact]` / `vybe s`

Print output only (strip the `$ cmd` header). Useful for piping or inspection.

**Flags:**
- `--redact` — Mask common secrets (API keys, tokens, passwords)

**Examples:**
```bash
vybe s | grep ERROR
vybe s --redact | pbcopy
```

### `vybe snipclip [--redact]` / `vybe sc`

Copy output only to clipboard. Fastest way to grab output for pasting into issues or LLM chats.

**Flags:**
- `--redact` — Mask secrets before copying

**Examples:**
```bash
vybe sc
vybe sc --redact
# Now paste in ChatGPT
```

## Clipboard Commands

### `vybe cmdcopy` / `vybe cc`

Copy **only the last command** to clipboard. Useful for tweaking and re-running.

```bash
vybe cc
# Edit command in terminal, then paste and modify
```

### `vybe clip`

Copy the entire last capture (command + output) to clipboard as-is.

### `vybe history [N] [--redact] [--json]`

Copy last N commands with outputs together. Default is 3. Perfect for sending your last few attempts to an LLM.

**Examples:**
```bash
vybe history
vybe history 5
vybe history 5 --redact
vybe history 3 --json
```

**Output:**
- Markdown bundle with all selected captures
- Or JSON if `--json` is specified

### `vybe select`

Interactively pick which captures to copy (requires `fzf`).

```bash
vybe select
# fzf opens, pick multiple with Tab, press Enter
```

## Navigation & Search

### `vybe ls [N] [--tag <name>]` / `vybe ll`

List last N captures (default 12). Shows metadata: time, exit code, duration, command.

**Examples:**
```bash
vybe ll
vybe ls 20
vybe ls --tag auth
```

### `vybe grep <pattern> [--i]`

Search the last capture with regex.

**Flags:**
- `--i` — Case-insensitive

**Examples:**
```bash
vybe grep ERROR
vybe grep "Traceback|ValueError" --i
```

### `vybe tail [N]`

Print the last N lines of the last capture (default 80).

```bash
vybe tail 20
```

### `vybe open` / `vybe o`

Open last capture in `$PAGER` (usually `less`).

### `vybe fail`

Jump to the most recent failing run (non-zero exit code). Sets it as "last".

```bash
vybe fail
vybe s
```

### `vybe errors`

Extract likely error blocks (tracebacks, pytest failures, etc.) from the last capture.

```bash
vybe errors
```

## LLM & Export

### `vybe export --last --json [--snip] [--redact]`

Export capture in machine-readable JSON for agents/tools.

**Flags:**
- `--snip` — Output only (exclude command header)
- `--redact` — Mask secrets

**Output keys:**
```json
{
  "tool": "vybe",
  "version": "1.0.0",
  "file": "/path/to/capture",
  "cmd": ["pytest", "-q"],
  "cmd_str": "pytest -q",
  "rc": 1,
  "cwd": "/home/user/project",
  "tag": "auth",
  "time": 1234567890,
  "time_human": "2026-02-19 10:30:45",
  "text": "... full output ...",
  "redacted": false,
  "output_only": false
}
```

### `vybe share [--full] [--redact] [--errors] [--json] [--clip]`

Build a shareable bundle (Markdown or JSON) from the last capture.

**Flags:**
- `--full` — Include command header (default: output only)
- `--redact` — Mask secrets
- `--errors` — Extract error blocks
- `--json` — Output as JSON instead of Markdown
- `--clip` — Copy to clipboard instead of printing

**Examples:**
```bash
vybe share --redact --errors --clip
vybe share --json | curl -X POST https://my-tool.com/api/share
```

### `vybe prompt <debug|review|explain> [--redact] [extra request...]`

Generate an LLM-ready prompt. Includes context (time, command, exit code, cwd) plus your output and a structured format request.

**Modes:**
- `debug` — "Find root cause and propose the smallest safe fix"
- `review` — "Review this and suggest risks/regressions/tests"
- `explain` — "Explain what happened and what to do next"

**Examples:**
```bash
vybe prompt debug --redact
vybe prompt review --redact
vybe r pytest -q
vybe errors
vybe prompt debug --redact "focus on the auth module"
```

## Advanced Workflows

### `vybe diff [--full] [--tag <name>]`

Show unified diff between latest capture and the previous one.

**Flags:**
- `--full` — Include headers (default: output only)
- `--tag <name>` — Diff only within a tagged group

**Example:**
```bash
vybe r npm run build
vybe rr  # Fix and retry
vybe diff  # See what changed
```

### `vybe watch <cmd...>`

Watch for file changes and auto-rerun command (experimental). Uses tag `watch-session`.

**Requires:**  `watchdog` package for auto-trigger
```bash
pip install watchdog
watchmedo shell-command --patterns='*.py' --recursive --command='vybe r pytest' .
```

### `vybe cwd <set|run>`

Remember and restore working directory across commands.

**Examples:**
```bash
cd /path/to/project
vybe cwd set

# Later, after changing directory:
cd /
vybe cwd run  # Re-runs last command in /path/to/project
```

### `vybe clean [--keep N] [--before <days>]`

Clean up old captures to reclaim disk space.

**Flags:**
- `--keep N` — Keep only the N newest captures (default 100)
- `--before <days>` — Delete captures older than N days

**Examples:**
```bash
vybe clean --keep 50
vybe clean --before 30  # Delete captures > 30 days old
```

### `vybe stats`

Show statistics: success rate, most-run commands, slowest runs.

```bash
vybe stats
```

**Output:**
```
=== Vybe Stats ===
Total runs: 47
Succeeded: 43
Failed: 4
Success rate: 91.5%

Top commands:
  12x pytest tests/ -q
  8x npm run build
  7x git status

Slowest runs:
  1. 34.2s - npm run build (2026-02-19 09:12:45)
  2. 12.1s - pytest tests/ -q (2026-02-19 09:05:30)
  ...
```

### `vybe flow <list|save|run>`

Save and replay common command sequences.

**Examples:**
```bash
# Save a sequence
vybe flow save auth-debug "pytest tests/auth/ -q" "echo Done"

# List flows
vybe flow list

# Run a flow
vybe flow run auth-debug
```

Flows are stored in `~/.config/vybe/config.json` under the `flows` key.

### `vybe link [PORT]`

Start a local web server to share captures (experimental/dev-only for now).

Use `vybe export`, `vybe share`, or `vybe prompt` for production sharing.

## Metadata & Config

### `vybe tags`

List all tags and their usage counts.

```bash
vybe tags

# Output:
# auth	5
# smoke	3
# perf	1
```

### `vybe ls --tag <name>`

List only captures with a specific tag.

```bash
vybe ls --tag auth
vybe ls 20 --tag smoke
```

### `vybe md [lang]`

Wrap last capture in Markdown code fences.

**Examples:**
```bash
vybe md bash
vybe md python
vybe md
```

## System & Setup

### `vybe doctor [--json]`

Print environment snapshot: Python version, platform, tmux, git status, clipboard tools, etc.

**Useful for:** Diagnosing setup issues, generating environment reports.

**Examples:**
```bash
vybe doctor
vybe doctor --json | curl -X POST https://my-support.com/diagnostics
```

### `vybe self-check [--json]`

Check if Vybe is installed correctly and print update guidance.

**Checks:**
- Python environment (system vs venv vs externally-managed)
- pipx availability
- Vybe's actual path
- Recommendations for upgrading

**Examples:**
```bash
vybe self-check
vybe self-check --json
```

### `vybe cfg [--json]`

Print current config and effective paths (environment variables).

**Examples:**
```bash
vybe cfg
vybe cfg --json
```

### `vybe init [--force]`

Initialize Vybe config defaults. Auto-detects clipboard tools.

```bash
vybe init
vybe init --force  # Overwrite existing config
```

### `vybe completion install <zsh|bash|fish>`

Install shell completion for faster command discovery.

**Examples:**
```bash
vybe completion install zsh
vybe completion install bash
vybe completion install fish
```

After install, you may need to reload your shell:
```bash
exec zsh  # for zsh
exec bash  # for bash
```

### `vybe pane [LINES]`

(tmux only) Capture tmux pane scrollback to a file.

**Requires:** tmux must be running (`TMUX` env var set)

**Examples:**
```bash
vybe pane       # Last 2000 lines
vybe pane 5000  # Last 5000 lines
```

## Help & Version

### `vybe --help` / `vybe -h` / `vybe help` / etc.

Show quick help. All variants work:
- `-h`, `--help`, `-H`, `-Help`, `-HELP`, `help`, `HELP`

### `vybe man`

Show this manual (if viewing online/in pager).

### `vybe version`

Print Vybe version.

## Environment Variables

- `VYBE_DIR` — Where captures are stored (default: `~/.cache/vybe`)
- `VYBE_STATE` — Where state is persisted (default: `~/.config/vybe/state.json`)
- `VYBE_INDEX` — Where the index of all captures is kept (default: `~/.cache/vybe/index.jsonl`)
- `VYBE_CONFIG` — Where config and flows are saved (default: `~/.config/vybe/config.json`)
- `VYBE_MAX_INDEX` — Max entries in the index before trimming (default: 2000)
- `PAGER` — Which pager to use for `vybe open` (default: `less`)

**Example:**
```bash
export VYBE_DIR=/tmp/vybe-debug
export VYBE_MAX_INDEX=500
vybe r echo test
```

## Speed Aliases

| Alias | Command |
|-------|---------|
| `r` | `run` |
| `rr` | `retry` |
| `l` | `last` |
| `s` | `snip` |
| `sc` | `snipclip` |
| `cc` | `cmdcopy` |
| `o` | `open` |
| `ll` | `ls` |

Use aliases interactively for speed; use full commands in scripts for clarity.

## Common Workflows

### Debug Loop (Human + LLM)

```bash
vybe r pytest -q
vybe errors
vybe prompt debug --redact
# Paste output in ChatGPT/Claude
# Make change...
vybe rr
```

### Batch LLM Handoff

```bash
vybe history 5 --redact
# Copies all 5 runs to clipboard
# Paste entire batch in LLM chat
```

### Interactive Selection

```bash
vybe select
# fzf opens, pick specific captures with Tab
# Copies selected to clipboard
```

### Tag-based Groups

```bash
vybe run --tag auth pytest tests/auth/ -q
vybe rr --tag auth
vybe ls --tag auth
vybe diff --tag auth
```

### Environment Diagnostics

```bash
vybe doctor --json | jq .
vybe self-check
vybe cfg
```

### Cleanup

```bash
vybe stats
vybe clean --keep 100
vybe ls 10  # Verify
```

## Secrets & Redaction

Vybe auto-redacts common patterns in `--redact` mode:
- API keys: `api_key=...`, `API_KEY=...`
- Tokens: `token=...`, Bearer tokens, GitHub tokens
- Passwords: `password=...`, `passwd=...`, `pwd=...`
- AWS: `AKIA...` patterns
- JWT: `eyJ...` patterns
- OpenAI: `sk-...` patterns

**Always use `--redact` before sharing output with others.**

```bash
vybe sc --redact
vybe share --redact --errors
vybe history 3 --redact
vybe prompt debug --redact
```

## Tips & Tricks

1. **Copy just the command:** `vybe cc` then paste to tweak.
2. **Grab multiple attempts:** `vybe history 5 --redact` for bulk LLM handoff.
3. **Interactive pick:** `vybe select` with fzf for surgical multi-select.
4. **Remember your dir:** `vybe cwd set` then `vybe cwd run` later.
5. **Use tags:** `vybe run --tag feature-x pytest` then `vybe rr --tag feature-x`.
6. **Diff iterations:** `vybe r cmd && vybe rr && vybe diff`.
7. **Export for agents:** `vybe export --last --json | your-agent-tool`.
8. **Cleanup periodically:** `vybe clean --keep 100`.

## License

MIT. See LICENSE file.
