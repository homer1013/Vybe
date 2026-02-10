# Contributing to Vybe

Thanks for helping make Vybe better.

## Quick start (dev)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
vybe --help
```

## Guidelines
- Keep dependencies at **zero** (stdlib only) unless a dependency is truly unavoidable.
- Prefer small, composable subcommands with predictable output.
- Be mindful of clipboard behavior across X11/Wayland.
- If you add a command, update:
  - `vybe --help`
  - completions files in `completions/`
  - README examples

## Testing (manual for now)
Run:
```bash
vybe run echo hello
vybe last
vybe snip
vybe md bash
```
