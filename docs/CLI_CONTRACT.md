# Vybe CLI v1 Contract

This file defines the stability contract for human users, scripts, and coding agents.

## Scope
- Applies to `1.0.0` and later until an explicit breaking-change note is published.
- Contract covers command names, core flags, and primary output shapes.

## Stable commands and aliases
- Core run: `run`, `retry`, `last`, `snip`, `snipclip`, `cmdcopy`, `ls`, `grep`, `md`, `clip`, `fail`
- Clipboard: `cmdcopy`, `history`, `select`
- Capture mgmt: `errors`, `diff`, `clean`, `stats`, `tags`, `pane`
- LLM/Export: `export`, `share`, `prompt`
- Workflow: `watch`, `cwd`, `flow`, `link`
- System: `doctor`, `project`, `self-check`, `cfg`, `init`, `completion`, `man`, `version`
- Aliases: `r`, `rr`, `l`, `s`, `sc`, `cc`, `o`, `ll`, `proj`

## Stable flags
- `run`: `--tag <name>`, `--tty`
- `retry`: `--cwd`, `--tag <name>`
- `snip`, `snipclip`: `--redact`
- `ls`: `--tag <name>`
- `history`: `[N]`, `--redact`, `--json`
- `export`: `--last --json [--snip] [--redact]`
- `diff`: `--full`, `--tag <name>`
- `share`: `--full`, `--redact`, `--errors`, `--smart`, `--json`, `--clip`
- `prompt`: `<debug|review|explain>`, `--redact`
- `clean`: `--keep N`, `--before <days>`
- `cwd`: `set`, `run`
- `flow`: `list`, `save`, `run`
- `doctor`: `--json`, `--explain`
- `project`: `--json`
- `self-check`: `--json`
- `cfg`: `--json`
- `init`: `--force`
- `completion`: `install <zsh|bash|fish>`

## Stable output contracts
- `export --last --json` is machine-readable JSON and will remain backward-compatible.
- `share --json` is machine-readable JSON with the same compatibility rule (includes `smart` and `context` keys if applicable).
- `share --smart` adds `smart: true` and `context` object to JSON output; backward-compatible.
- `history` outputs Markdown (default) or JSON (`--json`).
- `doctor --json` is backward-compatible JSON; `--explain` flag only affects human-readable output.
- `doctor --explain` adds plain-English diagnostics (human-readable only).
- `project --json` outputs project metadata (human-readable output is informational).
- `self-check --json`, `cfg --json` are all backward-compatible JSON.
- Human-readable outputs may gain extra lines, but command meaning remains stable.

## Auto-Detection Features (v1.1.0+)
- `run` detects GUI apps (Tkinter, Qt, Wx) and shows informational warnings.
- `run` detects sudo and suggests `--tty` flag for interactive prompts.
- `run` detects FileNotFoundError and suggests similar files if available.
- `share --smart` auto-gathers pwd, ls, python version, git status, venv status.

## Compatibility policy
- No breaking flag/command removals in patch releases.
- Breaking changes require:
  - a minor/major version bump,
  - README note,
  - migration note in release description.
