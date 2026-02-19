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
- System: `doctor`, `self-check`, `cfg`, `init`, `completion`, `man`, `version`
- Aliases: `r`, `rr`, `l`, `s`, `sc`, `cc`, `o`, `ll`

## Stable flags
- `run`: `--tag <name>`
- `retry`: `--cwd`, `--tag <name>`
- `snip`, `snipclip`: `--redact`
- `ls`: `--tag <name>`
- `history`: `[N]`, `--redact`, `--json`
- `export`: `--last --json [--snip] [--redact]`
- `diff`: `--full`, `--tag <name>`
- `share`: `--full`, `--redact`, `--errors`, `--json`, `--clip`
- `prompt`: `<debug|review|explain>`, `--redact`
- `clean`: `--keep N`, `--before <days>`
- `cwd`: `set`, `run`
- `flow`: `list`, `save`, `run`
- `doctor`: `--json`
- `self-check`: `--json`
- `cfg`: `--json`
- `init`: `--force`
- `completion`: `install <zsh|bash|fish>`

## Stable output contracts
- `export --last --json` is machine-readable JSON and will remain backward-compatible.
- `share --json` is machine-readable JSON with the same compatibility rule.
- `history` outputs Markdown (default) or JSON (`--json`).
- `doctor --json`, `self-check --json`, `cfg --json` are all backward-compatible JSON.
- Human-readable outputs may gain extra lines, but command meaning remains stable.

## Compatibility policy
- No breaking flag/command removals in patch releases.
- Breaking changes require:
  - a minor/major version bump,
  - README note,
  - migration note in release description.
