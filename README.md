# Vybe

Vybe is a **vibe coding terminal toolkit**: run a command, capture its output, and instantly reuse it —
copy to clipboard, wrap in Markdown, search errors, jump to the last failure, or grab tmux scrollback.

## Highlights
- **`vybe run ...`** streams output live *and* saves it.
- **`vybe snipclip`** copies *output only* (perfect for issues/ChatGPT).
- **`vybe fail`** jumps back to the most recent failing run.
- Works great on Kali (zsh) and supports tmux scrollback capture.

## Install (dev / from source)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
vybe --help
```

## Usage
```bash
vybe run pytest -q
vybe fail
vybe snipclip
vybe md bash
vybe grep "Traceback|ERROR" --i
```

### Command reference
Run:
```bash
vybe --help
```

## Clipboard support
Vybe auto-detects clipboard tools:
- X11: `xclip` (preferred) or `xsel`
- Wayland: `wl-copy`

## tmux scrollback capture
```bash
vybe pane 4000
vybe open
```

## Environment variables
- `VYBE_DIR` log dir (default `~/.cache/vybe`)
- `VYBE_STATE` state file (default `~/.config/vybe/state.json`)
- `VYBE_INDEX` index file (default `~/.cache/vybe/index.jsonl`)
- `VYBE_MAX_INDEX` max index entries (default `2000`)

## Shell completions
See `completions/`:
- bash: `completions/vybe.bash`
- zsh: `completions/_vybe`
- fish: `completions/vybe.fish`

### zsh (Kali)
```bash
mkdir -p ~/.zsh/completions
cp completions/_vybe ~/.zsh/completions/
echo 'fpath=(~/.zsh/completions $fpath)' >> ~/.zshrc
autoload -Uz compinit && compinit
exec zsh -l
```

## License
MIT
