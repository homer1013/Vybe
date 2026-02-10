#!/usr/bin/env python3
"""
Vybe - vibe coding terminal capture toolkit.

Design goals:
- Zero deps (stdlib only)
- Fast "run → capture → reuse" loop
- Works great in Kali/zsh, Linux, tmux

See `vybe --help`.
"""
import os
import sys
import json
import time
import re
import shlex
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any

from . import __version__

APP = "vybe"
HOME = Path.home()

VYBE_DIR = Path(os.environ.get("VYBE_DIR", str(HOME / ".cache" / APP)))
VYBE_STATE = Path(os.environ.get("VYBE_STATE", str(HOME / ".config" / APP / "state.json")))
VYBE_INDEX = Path(os.environ.get("VYBE_INDEX", str(HOME / ".cache" / APP / "index.jsonl")))
MAX_INDEX = int(os.environ.get("VYBE_MAX_INDEX", "2000"))

# ---------- helpers ----------

def now_stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")

def ensure_dirs() -> None:
    VYBE_DIR.mkdir(parents=True, exist_ok=True)
    VYBE_STATE.parent.mkdir(parents=True, exist_ok=True)
    VYBE_INDEX.parent.mkdir(parents=True, exist_ok=True)

def load_state() -> Dict[str, Any]:
    try:
        return json.loads(VYBE_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_state(state: Dict[str, Any]) -> None:
    ensure_dirs()
    VYBE_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")

def append_index(record: Dict[str, Any]) -> None:
    ensure_dirs()
    with VYBE_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    trim_index()

def trim_index() -> None:
    try:
        if not VYBE_INDEX.exists():
            return
        lines = VYBE_INDEX.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) <= MAX_INDEX:
            return
        VYBE_INDEX.write_text("\n".join(lines[-MAX_INDEX:]) + "\n", encoding="utf-8")
    except Exception:
        # best-effort only
        pass

def latest_file() -> Optional[Path]:
    st = load_state()
    p = st.get("last_file")
    return Path(p) if p else None

def set_latest_file(path: Path, cmd=None, rc=None, t=None) -> None:
    st = load_state()
    st["last_file"] = str(path)
    if cmd is not None:
        st["last_cmd"] = cmd
    if rc is not None:
        st["last_rc"] = rc
    if t is not None:
        st["last_time"] = t
    save_state(st)

def human_ts(epoch: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))

def shell_quote_cmd(args: List[str]) -> str:
    return " ".join(shlex.quote(a) for a in args)

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def strip_header(text: str) -> str:
    """
    Logs start like:
      $ cmd ...
      ---
      output...
    """
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("$ ") and lines[1].strip() == "---":
        return "\n".join(lines[2:]).lstrip("\n")
    return text

def _clipboard_cmd() -> Optional[List[str]]:
    # Prefer X11 tools first; wl-copy fallback.
    for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["wl-copy"]):
        if shutil.which(cmd[0]):
            return cmd
    return None

def _clipboard_write_bytes(data: bytes) -> int:
    cmd = _clipboard_cmd()
    if not cmd:
        print("No clipboard tool found. Install: xclip OR xsel (X11) or wl-clipboard (Wayland).", file=sys.stderr)
        return 1
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    proc.stdin.write(data)
    proc.stdin.close()
    return proc.wait()

# ---------- commands ----------

def cmd_run(args: List[str]) -> int:
    if not args:
        print("Usage: vybe run <command...>", file=sys.stderr)
        return 2

    ensure_dirs()
    stamp = now_stamp()
    outfile = VYBE_DIR / f"vybe_{stamp}.log"
    cmd_str = shell_quote_cmd(args)
    outfile.write_text(f"$ {cmd_str}\n---\n", encoding="utf-8")

    start = time.time()
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    with outfile.open("a", encoding="utf-8", errors="replace") as f:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            f.write(line)

    rc = proc.wait()
    end = time.time()

    set_latest_file(outfile, cmd=args, rc=rc, t=end)
    append_index({
        "time": end,
        "stamp": stamp,
        "file": str(outfile),
        "cmd": args,
        "rc": rc,
        "dur_s": round(end - start, 3),
        "kind": "run",
        "cwd": str(Path.cwd()),
    })

    print(f"\nSaved: {outfile}")
    return rc

def cmd_last(_args: List[str]) -> int:
    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    sys.stdout.write(read_text(p))
    return 0

def cmd_snip(_args: List[str]) -> int:
    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    text = strip_header(read_text(p))
    sys.stdout.write(text + ("" if text.endswith("\n") or text == "" else "\n"))
    return 0

def cmd_snipclip(_args: List[str]) -> int:
    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    text = strip_header(read_text(p))
    rc = _clipboard_write_bytes(text.encode("utf-8", errors="replace"))
    if rc == 0:
        print("Copied snip (output only) to clipboard.")
    return rc

def cmd_tail(args: List[str]) -> int:
    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    n = 80
    if args:
        try:
            n = int(args[0])
        except ValueError:
            pass
    lines = read_text(p).splitlines()
    out = "\n".join(lines[-n:])
    sys.stdout.write(out + ("\n" if out else ""))
    return 0

def cmd_open(_args: List[str]) -> int:
    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    pager = os.environ.get("PAGER", "less")
    return subprocess.call([pager, str(p)])

def cmd_ls(args: List[str]) -> int:
    n = 12
    if args:
        try:
            n = int(args[0])
        except ValueError:
            pass
    if not VYBE_INDEX.exists():
        print("No index yet. Run: vybe run <cmd...>", file=sys.stderr)
        return 1
    lines = VYBE_INDEX.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in reversed(lines[-n:]):
        try:
            rec = json.loads(line)
            t = human_ts(rec.get("time", 0))
            rc = rec.get("rc", "?")
            dur = rec.get("dur_s", "?")
            kind = rec.get("kind", "run")
            cmd = shell_quote_cmd(rec.get("cmd", []))
            cwd = rec.get("cwd", "")
            file = rec.get("file", "")
            print(f"[{kind}] {t} rc={rc} dur={dur}s")
            print(f"  $ {cmd}")
            if cwd:
                print(f"  cwd: {cwd}")
            print(f"  {file}")
        except Exception:
            continue
    return 0

def cmd_grep(args: List[str]) -> int:
    if not args:
        print("Usage: vybe grep <pattern> [--i]", file=sys.stderr)
        return 2
    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1

    flags = 0
    parts: List[str] = []
    for a in args:
        if a == "--i":
            flags |= re.IGNORECASE
        else:
            parts.append(a)
    pattern = " ".join(parts).strip()
    if not pattern:
        print("Usage: vybe grep <pattern> [--i]", file=sys.stderr)
        return 2

    rx = re.compile(pattern, flags)
    for i, line in enumerate(read_text(p).splitlines(), start=1):
        if rx.search(line):
            print(f"{i}:{line}")
    return 0

def cmd_md(args: List[str]) -> int:
    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    lang = args[0] if args else ""
    content = read_text(p).rstrip("\n")
    print(f"```{lang}" if lang else "```")
    print(content)
    print("```")
    return 0

def cmd_clip(_args: List[str]) -> int:
    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    rc = _clipboard_write_bytes(p.read_bytes())
    if rc == 0:
        print("Copied last capture to clipboard.")
    return rc

def cmd_fail(_args: List[str]) -> int:
    if not VYBE_INDEX.exists():
        print("No index yet. Run: vybe run <cmd...>", file=sys.stderr)
        return 1
    lines = VYBE_INDEX.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        try:
            rec = json.loads(line)
            if rec.get("kind") != "run":
                continue
            rc = int(rec.get("rc", 0))
            if rc == 0:
                continue
            f = Path(rec.get("file", ""))
            if f.exists():
                set_latest_file(f, cmd=rec.get("cmd", []), rc=rc, t=rec.get("time", time.time()))
                print(f"Selected failing capture: {f}")
                return 0
        except Exception:
            continue
    print("No failing captures found.", file=sys.stderr)
    return 1

def cmd_pane(args: List[str]) -> int:
    if "TMUX" not in os.environ:
        print("vybe pane requires tmux (TMUX env var not set).", file=sys.stderr)
        return 1
    ensure_dirs()
    stamp = now_stamp()
    outfile = VYBE_DIR / f"vybe_pane_{stamp}.log"
    lines = args[0] if args else "2000"
    try:
        with outfile.open("w", encoding="utf-8") as f:
            subprocess.check_call(["tmux", "capture-pane", "-p", "-S", f"-{lines}"], stdout=f)
    except subprocess.CalledProcessError as e:
        print("tmux capture-pane failed.", file=sys.stderr)
        return e.returncode

    end = time.time()
    set_latest_file(outfile, cmd=["tmux", "capture-pane", "-p", "-S", f"-{lines}"], rc=0, t=end)
    append_index({
        "time": end,
        "stamp": stamp,
        "file": str(outfile),
        "cmd": ["tmux", "capture-pane", "-p", "-S", f"-{lines}"],
        "rc": 0,
        "dur_s": 0,
        "kind": "pane",
        "cwd": str(Path.cwd()),
    })
    print(f"Saved: {outfile}")
    return 0

def cmd_version(_args: List[str]) -> int:
    print(__version__)
    return 0

# ---------- help / dispatch ----------

def help_text() -> str:
    return f"""vybe - vibe coding terminal capture toolkit (v{__version__})

Commands:
  vybe run <cmd...>        Run command, show output live, save to log
  vybe last                Print most recent capture (header + output)
  vybe snip                Print output only (strip `$ cmd` header)
  vybe snipclip            Copy output only to clipboard
  vybe tail [N]            Print last N lines of most recent capture (default 80)
  vybe open                Open most recent capture in $PAGER
  vybe ls [N]              List last N captures (default 12)
  vybe grep <pat> [--i]    Search the most recent capture (regex)
  vybe md [lang]           Wrap last capture in Markdown fences
  vybe clip                Copy last capture to clipboard
  vybe fail                Select most recent failing run as "last"
  vybe pane [LINES]        (tmux) capture pane scrollback (default 2000)
  vybe version             Print version

Flags:
  -h, --help               Show help
  --version                Print version

Env:
  VYBE_DIR        log dir (default ~/.cache/vybe)
  VYBE_STATE      state file (default ~/.config/vybe/state.json)
  VYBE_INDEX      index file (default ~/.cache/vybe/index.jsonl)
  VYBE_MAX_INDEX  max index entries (default 2000)
"""

def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help", "help"):
        print(help_text())
        return 0
    if argv[0] == "--version":
        return cmd_version([])

    cmd = argv[0]
    args = argv[1:]

    dispatch = {
        "run": cmd_run,
        "last": cmd_last,
        "snip": cmd_snip,
        "snipclip": cmd_snipclip,
        "tail": cmd_tail,
        "open": cmd_open,
        "ls": cmd_ls,
        "grep": cmd_grep,
        "md": cmd_md,
        "clip": cmd_clip,
        "fail": cmd_fail,
        "pane": cmd_pane,
        "version": cmd_version,
    }

    fn = dispatch.get(cmd)
    if not fn:
        print(f"Unknown command: {cmd}\n", file=sys.stderr)
        print(help_text(), file=sys.stderr)
        return 2
    return fn(args)

if __name__ == "__main__":
    raise SystemExit(main())
