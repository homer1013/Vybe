# Contributing to Vybe

Thanks for helping make Vybe better.

## Quick start (dev)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
vybe --help
python -m vybe --help
```

## Guidelines
- Keep dependencies at **zero** (stdlib only) unless a dependency is truly unavoidable.
- Prefer small, composable subcommands with predictable output.
- Be mindful of clipboard behavior across X11/Wayland.
- If you add a command, update:
  - `vybe --help`
  - completions files in `completions/`
  - README examples

## Testing (manual smoke)
Run:
```bash
vybe run echo hello
vybe run --tag smoke echo hello
vybe r echo hello
vybe retry --tag smoke
vybe rr
vybe last
vybe l
vybe snip
vybe s
vybe sc --redact
vybe errors
vybe export --last --json --snip
vybe ll
vybe ls --tag smoke
vybe diff
vybe share --redact --errors
vybe share --json --errors --redact
vybe prompt debug --redact
vybe doctor
vybe self-check
vybe cfg
vybe init --force
vybe completion install zsh
vybe md bash
```

Automated checks:
```bash
python -m py_compile src/vybe/cli.py
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Stability contract
- Keep `docs/CLI_CONTRACT.md` updated when changing command names, flags, or JSON output contracts.
