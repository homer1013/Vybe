# Vybe CLI v1 Contract

This file defines the stability contract for human users, scripts, and coding agents.

## Scope
- Applies to `0.6.x` and later until an explicit breaking-change note is published.
- Contract covers command names, core flags, and primary output shapes.

## Stable commands and aliases
- Core: `run`, `retry`, `last`, `snip`, `snipclip`, `ls`, `grep`, `md`, `clip`, `fail`
- Agent/support: `errors`, `export`, `diff`, `share`, `doctor`, `pane`
- Aliases: `r`, `rr`, `l`, `s`, `sc`, `o`, `ll`

## Stable flags
- `run`: `--tag <name>`
- `retry`: `--cwd`, `--tag <name>`
- `snip`, `snipclip`: `--redact`
- `ls`: `--tag <name>`
- `export`: `--last --json [--snip] [--redact]`
- `diff`: `--full`, `--tag <name>`
- `share`: `--full`, `--redact`, `--errors`, `--json`, `--clip`
- `doctor`: `--json`

## Stable output contracts
- `export --last --json` is machine-readable JSON and will remain backward-compatible:
  - Existing keys are not removed in patch/minor releases.
  - New keys may be added.
- `share --json` is machine-readable JSON with the same compatibility rule.
- `doctor --json` is machine-readable JSON with the same compatibility rule.
- Human-readable outputs may gain extra lines, but command meaning remains stable.

## Compatibility policy
- No breaking flag/command removals in patch releases.
- Breaking changes require:
  - a minor/major version bump,
  - README note,
  - migration note in release description.
