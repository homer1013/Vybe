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
import signal
import difflib
import subprocess
import shutil
import sysconfig
from pathlib import Path
from typing import Optional, List, Dict, Any

from . import __version__

APP = "vybe"
HOME = Path.home()

VYBE_DIR = Path(os.environ.get("VYBE_DIR", str(HOME / ".cache" / APP)))
VYBE_STATE = Path(os.environ.get("VYBE_STATE", str(HOME / ".config" / APP / "state.json")))
VYBE_INDEX = Path(os.environ.get("VYBE_INDEX", str(HOME / ".cache" / APP / "index.jsonl")))
VYBE_CONFIG = Path(os.environ.get("VYBE_CONFIG", str(HOME / ".config" / APP / "config.json")))
MAX_INDEX = int(os.environ.get("VYBE_MAX_INDEX", "2000"))
_UNSET = object()

# ---------- helpers ----------

def now_stamp() -> str:
    ns = time.time_ns()
    sec = ns // 1_000_000_000
    micros = (ns // 1_000) % 1_000_000
    return time.strftime("%Y%m%d_%H%M%S", time.localtime(sec)) + f"_{micros:06d}"

def ensure_dirs() -> None:
    VYBE_DIR.mkdir(parents=True, exist_ok=True)
    VYBE_STATE.parent.mkdir(parents=True, exist_ok=True)
    VYBE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    VYBE_CONFIG.parent.mkdir(parents=True, exist_ok=True)

def load_state() -> Dict[str, Any]:
    try:
        return json.loads(VYBE_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_state(state: Dict[str, Any]) -> None:
    ensure_dirs()
    VYBE_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")

def load_config() -> Dict[str, Any]:
    try:
        return json.loads(VYBE_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_config(cfg: Dict[str, Any]) -> None:
    ensure_dirs()
    VYBE_CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

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

def set_latest_file(path: Path, cmd=None, rc=None, t=None, cwd=None, kind=None, tag=_UNSET) -> None:
    st = load_state()
    st["last_file"] = str(path)
    if cmd is not None:
        st["last_cmd"] = cmd
    if rc is not None:
        st["last_rc"] = rc
    if t is not None:
        st["last_time"] = t
    if cwd is not None:
        st["last_cwd"] = cwd
    if kind is not None:
        st["last_kind"] = kind
    if tag is not _UNSET:
        st["last_tag"] = tag
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

def redact_text(text: str) -> str:
    redacted = text
    patterns = [
        # Common key/value style secrets.
        (re.compile(r'(?i)\b(api[_-]?key|token|secret|password|passwd|pwd)\b(\s*[:=]\s*)([^\s]+)'), r"\1\2[REDACTED]"),
        # Bearer tokens.
        (re.compile(r'(?i)\b(bearer\s+)([A-Za-z0-9._\-=/+]+)'), r"\1[REDACTED]"),
        # AWS Access Key ID.
        (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), "[REDACTED_AWS_KEY]"),
        # OpenAI-style secret keys.
        (re.compile(r'\bsk-[A-Za-z0-9]{20,}\b'), "[REDACTED_API_KEY]"),
        # GitHub tokens.
        (re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}\b'), "[REDACTED_GITHUB_TOKEN]"),
        # JWT-like tokens.
        (re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{10,}\.[A-Za-z0-9._-]{10,}\b'), "[REDACTED_JWT]"),
    ]
    for rx, repl in patterns:
        redacted = rx.sub(repl, redacted)
    return redacted

def extract_error_blocks(text: str, max_blocks: int = 8) -> List[str]:
    lines = strip_header(text).splitlines()
    blocks: List[str] = []
    n = len(lines)
    i = 0

    while i < n and len(blocks) < max_blocks:
        line = lines[i]

        if line.startswith("Traceback (most recent call last):"):
            j = i + 1
            while j < n and lines[j].strip() != "":
                j += 1
            block = "\n".join(lines[i:j]).strip()
            if block:
                blocks.append(block)
            i = j + 1
            continue

        if re.match(r"^=+ FAILURES =+$", line):
            j = i + 1
            while j < n and not re.match(r"^=+ .+ =+$", lines[j]):
                j += 1
            block = "\n".join(lines[i:j]).strip()
            if block:
                blocks.append(block)
            i = j
            continue

        if re.search(r"(?i)\b(error|exception|fatal|panic|failed)\b", line):
            start = max(0, i - 2)
            end = min(n, i + 3)
            block = "\n".join(lines[start:end]).strip()
            if block:
                blocks.append(block)
            i += 1
            continue

        i += 1

    # De-duplicate while preserving order.
    uniq: List[str] = []
    seen = set()
    for b in blocks:
        if b in seen:
            continue
        seen.add(b)
        uniq.append(b)
    return uniq

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

def load_index_records() -> List[Dict[str, Any]]:
    if not VYBE_INDEX.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in VYBE_INDEX.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out

def _run_quiet(args: List[str], cwd: Optional[str] = None) -> Optional[str]:
    try:
        out = subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True, cwd=cwd)
        return out.strip()
    except Exception:
        return None

def completion_sources_dir() -> Path:
    # Source tree layout: repo/src/vybe/cli.py -> repo/completions
    return Path(__file__).resolve().parents[2] / "completions"

def _is_externally_managed_python() -> bool:
    try:
        stdlib = sysconfig.get_path("stdlib")
        if not stdlib:
            return False
        return (Path(stdlib) / "EXTERNALLY-MANAGED").exists()
    except Exception:
        return False

def _in_virtualenv() -> bool:
    return bool(getattr(sys, "real_prefix", None)) or (sys.prefix != getattr(sys, "base_prefix", sys.prefix))

def _detect_gui(cmd_str: str) -> bool:
    """Detect if command likely runs a GUI app (checks for tkinter, qt, wx imports)."""
    gui_patterns = [
        r'\btkinter\b',
        r'\bPyQt\d\b',
        r'\bPySide\d\b',
        r'\bwx\b',
        r'import tk',
        r'from tk',
    ]
    for pat in gui_patterns:
        if re.search(pat, cmd_str):
            return True
    return False

def _detect_sudo(args: List[str]) -> bool:
    """Check if command starts with sudo."""
    return bool(args and args[0] == "sudo")

def _suggest_files(pattern: str) -> List[str]:
    """Suggest files that match pattern using fuzzy matching. Returns up to 3 suggestions."""
    try:
        cwd = Path.cwd()
        all_files = list(cwd.glob("*")) + list(cwd.glob("**/*"))
        # Deduplicate and filter to just filenames
        names = set(f.name for f in all_files if f.is_file())
        
        # Simple fuzzy match: files containing all chars in pattern (case-insensitive)
        pattern_lower = pattern.lower()
        candidates = []
        for name in names:
            if all(c in name.lower() for c in pattern_lower):
                # Score: prefer exact prefix matches, then length-based
                if name.lower().startswith(pattern_lower):
                    candidates.append((0, len(name), name))
                else:
                    candidates.append((1, len(name), name))
        
        # Sort by score, then by length (shorter is better)
        candidates.sort()
        return [name for _, _, name in candidates[:3]]
    except Exception:
        return []

def _gather_smart_context() -> Dict[str, str]:
    """Gather environmental context for --smart share: pwd, ls, python version, git status."""
    context: Dict[str, str] = {}
    
    # pwd
    try:
        context["pwd"] = str(Path.cwd())
    except Exception:
        context["pwd"] = "-"
    
    # ls -la output
    ls_out = _run_quiet(["ls", "-la"])
    if ls_out:
        context["ls"] = ls_out
    
    # python --version
    py_out = _run_quiet(["python", "--version"])
    if py_out:
        context["python"] = py_out
    
    # git status
    git_out = _run_quiet(["git", "status", "--short"], cwd=context.get("pwd"))
    if git_out:
        context["git_status"] = git_out
    
    # virtualenv check
    if _in_virtualenv():
        context["venv"] = "active"
    
    return context

# ---------- commands ----------

def _run_capture(args: List[str], cwd: Optional[str] = None, tag: Optional[str] = None, use_tty: bool = False) -> int:
    ensure_dirs()
    stamp = now_stamp()
    outfile = VYBE_DIR / f"vybe_{stamp}.log"
    cmd_str = shell_quote_cmd(args)
    outfile.write_text(f"$ {cmd_str}\n---\n", encoding="utf-8")

    start = time.time()
    interrupted = False
    proc: Optional[subprocess.Popen[str]] = None
    run_cwd = cwd if cwd is not None else str(Path.cwd())
    
    # Detect sudo and GUI warnings
    is_sudo = _detect_sudo(args)
    is_gui = _detect_gui(cmd_str)
    
    if is_gui and not use_tty:
        print("⚠️  Warning: Command may launch a GUI app. Close the window when done.", file=sys.stderr)
    if is_sudo and not use_tty:
        print("💡 Tip: Use `--tty` flag for interactive sudo. Example: vybe run --tty sudo <cmd>", file=sys.stderr)

    try:
        if use_tty:
            # For TTY mode, use stdin/stdout/stderr directly (inherit from parent)
            # This allows interactive input/output for sudo and other interactive commands
            proc = subprocess.Popen(
                args,
                stdin=None,  # Inherit stdin from parent
                stdout=None,  # Inherit stdout from parent
                stderr=None,  # Inherit stderr from parent
                cwd=cwd,
                start_new_session=False,
            )
            # Read output from file if needed - for now, we'll skip capture in TTY mode
            rc = proc.wait()
            end = time.time()
            set_latest_file(outfile, cmd=args, rc=rc, t=end, cwd=run_cwd, kind="run", tag=tag)
            append_index({
                "time": end,
                "stamp": stamp,
                "file": str(outfile),
                "cmd": args,
                "rc": rc,
                "dur_s": round(end - start, 3),
                "kind": "run",
                "cwd": run_cwd,
                "interrupted": False,
                "tag": tag,
                "tty_mode": True,
            })
            print(f"\nSaved: {outfile}")
            return rc
        else:
            # Regular mode with output capture
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=cwd,
                start_new_session=True,
            )
    except FileNotFoundError:
        msg = f"Command not found: {args[0]}"
        with outfile.open("a", encoding="utf-8", errors="replace") as f:
            f.write(msg + "\n")
        
        # Try to suggest alternatives
        suggestions = _suggest_files(args[0])
        if suggestions:
            print(msg + "\nDid you mean?", file=sys.stderr)
            for sugg in suggestions:
                print(f"  - {sugg}", file=sys.stderr)
        else:
            print(msg, file=sys.stderr)
        
        end = time.time()
        set_latest_file(outfile, cmd=args, rc=127, t=end, cwd=run_cwd, kind="run", tag=tag)
        append_index({
            "time": end,
            "stamp": stamp,
            "file": str(outfile),
            "cmd": args,
            "rc": 127,
            "dur_s": round(end - start, 3),
            "kind": "run",
            "cwd": run_cwd,
            "interrupted": False,
            "tag": tag,
        })
        print(f"\nSaved: {outfile}")
        return 127

    with outfile.open("a", encoding="utf-8", errors="replace") as f:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                sys.stdout.write(line)
                f.write(line)
        except KeyboardInterrupt:
            interrupted = True
            print("\nInterrupted. Stopping command...", file=sys.stderr)
            try:
                os.killpg(proc.pid, signal.SIGINT)
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except Exception:
                    proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except Exception:
                        proc.kill()
                    proc.wait()
            for line in proc.stdout:
                sys.stdout.write(line)
                f.write(line)

    rc = proc.wait()
    if interrupted and rc < 0:
        rc = 128 + (-rc)
    if interrupted and rc == 0:
        rc = 130
    end = time.time()

    set_latest_file(outfile, cmd=args, rc=rc, t=end, cwd=run_cwd, kind="run", tag=tag)
    append_index({
        "time": end,
        "stamp": stamp,
        "file": str(outfile),
        "cmd": args,
        "rc": rc,
        "dur_s": round(end - start, 3),
        "kind": "run",
        "cwd": run_cwd,
        "interrupted": interrupted,
        "tag": tag,
    })

    print(f"\nSaved: {outfile}")
    return rc

def cmd_run(args: List[str]) -> int:
    tag: Optional[str] = None
    use_tty = False
    
    # Parse flags: --tag <name>, --tty
    while args and args[0].startswith("--"):
        if args[0] == "--tag":
            if len(args) < 3:
                print("Usage: vybe run [--tag <name>] [--tty] <command...>", file=sys.stderr)
                return 2
            tag = args[1]
            args = args[2:]
        elif args[0] == "--tty":
            use_tty = True
            args = args[1:]
        else:
            break
    
    if not args:
        print("Usage: vybe run [--tag <name>] [--tty] <command...>", file=sys.stderr)
        return 2
    return _run_capture(args, tag=tag, use_tty=use_tty)

def cmd_retry(args: List[str]) -> int:
    use_original_cwd = False
    tag_override: Optional[str] = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--cwd":
            use_original_cwd = True
            i += 1
            continue
        if a == "--tag":
            if i + 1 >= len(args):
                print("Usage: vybe retry [--cwd] [--tag <name>]", file=sys.stderr)
                return 2
            tag_override = args[i + 1]
            i += 2
            continue
        i += 1
    st = load_state()
    last_cmd = st.get("last_cmd")
    last_kind = st.get("last_kind")
    if not isinstance(last_cmd, list) or not last_cmd:
        print("No previous command found. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    if last_kind != "run":
        print("Latest capture is not from `vybe run`. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    retry_cwd = st.get("last_cwd") if use_original_cwd else None
    retry_tag = tag_override if tag_override is not None else st.get("last_tag")
    return _run_capture(last_cmd, cwd=retry_cwd, tag=retry_tag)

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
    redact = "--redact" in _args
    text = strip_header(read_text(p))
    if redact:
        text = redact_text(text)
    sys.stdout.write(text + ("" if text.endswith("\n") or text == "" else "\n"))
    return 0

def cmd_snipclip(_args: List[str]) -> int:
    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    redact = "--redact" in _args
    text = strip_header(read_text(p))
    if redact:
        text = redact_text(text)
    rc = _clipboard_write_bytes(text.encode("utf-8", errors="replace"))
    if rc == 0:
        if redact:
            print("Copied redacted snip (output only) to clipboard.")
        else:
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
    tag_filter: Optional[str] = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--tag":
            if i + 1 >= len(args):
                print("Usage: vybe ls [N] [--tag <name>]", file=sys.stderr)
                return 2
            tag_filter = args[i + 1]
            i += 2
            continue
        try:
            n = int(a)
        except ValueError:
            pass
        i += 1

    records = load_index_records()
    if not records:
        print("No index yet. Run: vybe run <cmd...>", file=sys.stderr)
        return 1
    if tag_filter is not None:
        records = [r for r in records if r.get("tag") == tag_filter]
        if not records:
            print(f"No captures found for tag: {tag_filter}", file=sys.stderr)
            return 1

    for rec in reversed(records[-n:]):
        t = human_ts(rec.get("time", 0))
        rc = rec.get("rc", "?")
        dur = rec.get("dur_s", "?")
        kind = rec.get("kind", "run")
        cmd = shell_quote_cmd(rec.get("cmd", []))
        cwd = rec.get("cwd", "")
        file = rec.get("file", "")
        tag = rec.get("tag")
        print(f"[{kind}] {t} rc={rc} dur={dur}s")
        print(f"  $ {cmd}")
        if tag:
            print(f"  tag: {tag}")
        if cwd:
            print(f"  cwd: {cwd}")
        print(f"  {file}")
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
    records = load_index_records()
    if not records:
        print("No index yet. Run: vybe run <cmd...>", file=sys.stderr)
        return 1
    for rec in reversed(records):
        try:
            if rec.get("kind") != "run":
                continue
            rc = int(rec.get("rc", 0))
            if rc == 0:
                continue
            f = Path(rec.get("file", ""))
            if f.exists():
                set_latest_file(
                    f,
                    cmd=rec.get("cmd", []),
                    rc=rc,
                    t=rec.get("time", time.time()),
                    cwd=rec.get("cwd"),
                    kind=rec.get("kind"),
                    tag=rec.get("tag"),
                )
                print(f"Selected failing capture: {f}")
                return 0
        except Exception:
            continue
    print("No failing captures found.", file=sys.stderr)
    return 1

def cmd_errors(_args: List[str]) -> int:
    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    text = read_text(p)
    blocks = extract_error_blocks(text)
    if not blocks:
        print("No obvious error blocks found.")
        return 0
    for i, block in enumerate(blocks, start=1):
        if i > 1:
            print("\n" + ("-" * 60))
        print(f"[error:{i}]")
        print(block)
    return 0

def cmd_export(args: List[str]) -> int:
    as_json = "--json" in args
    use_last = "--last" in args or not args
    output_only = "--snip" in args
    redact = "--redact" in args

    if not use_last:
        print("Usage: vybe export [--last] --json [--snip] [--redact]", file=sys.stderr)
        return 2
    if not as_json:
        print("Usage: vybe export [--last] --json [--snip] [--redact]", file=sys.stderr)
        return 2

    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1

    st = load_state()
    full_text = read_text(p)
    out_text = strip_header(full_text)
    if redact:
        full_text = redact_text(full_text)
        out_text = redact_text(out_text)
    chosen_text = out_text if output_only else full_text

    payload = {
        "tool": APP,
        "version": __version__,
        "file": str(p),
        "kind": st.get("last_kind"),
        "time": st.get("last_time"),
        "time_human": human_ts(float(st.get("last_time", 0))) if st.get("last_time") else None,
        "cmd": st.get("last_cmd"),
        "rc": st.get("last_rc"),
        "cwd": st.get("last_cwd"),
        "tag": st.get("last_tag"),
        "output_only": output_only,
        "redacted": redact,
        "text": chosen_text,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0

def cmd_diff(args: List[str]) -> int:
    use_full = "--full" in args
    tag_filter: Optional[str] = None

    i = 0
    while i < len(args):
        if args[i] == "--tag":
            if i + 1 >= len(args):
                print("Usage: vybe diff [--full] [--tag <name>]", file=sys.stderr)
                return 2
            tag_filter = args[i + 1]
            i += 2
            continue
        i += 1

    records = load_index_records()
    if tag_filter is not None:
        records = [r for r in records if r.get("tag") == tag_filter]

    latest_two: List[Dict[str, Any]] = []
    for rec in reversed(records):
        p = Path(rec.get("file", ""))
        if p.exists():
            latest_two.append(rec)
        if len(latest_two) == 2:
            break

    if len(latest_two) < 2:
        print("Need at least two captures to diff.", file=sys.stderr)
        return 1

    new_rec = latest_two[0]
    old_rec = latest_two[1]
    new_file = Path(new_rec["file"])
    old_file = Path(old_rec["file"])

    old_text = read_text(old_file)
    new_text = read_text(new_file)
    if not use_full:
        old_text = strip_header(old_text)
        new_text = strip_header(new_text)

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff_lines = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=str(old_file),
        tofile=str(new_file),
        lineterm="",
    ))
    if not diff_lines:
        print("No differences between latest two captures.")
        return 0
    for line in diff_lines:
        print(line)
    return 0

def cmd_doctor(args: List[str]) -> int:
    as_json = "--json" in args
    explain = "--explain" in args

    git_root = _run_quiet(["git", "rev-parse", "--show-toplevel"])
    git_branch = _run_quiet(["git", "rev-parse", "--abbrev-ref", "HEAD"]) if git_root else None
    git_commit = _run_quiet(["git", "rev-parse", "--short", "HEAD"]) if git_root else None
    git_status = _run_quiet(["git", "status", "--porcelain"]) if git_root else None
    git_dirty = bool(git_status) if git_status is not None else None

    clip_tools = {
        "xclip": shutil.which("xclip"),
        "xsel": shutil.which("xsel"),
        "wl-copy": shutil.which("wl-copy"),
    }
    common_tools = {
        "tmux": shutil.which("tmux"),
        "less": shutil.which("less"),
        "git": shutil.which("git"),
        "python3": shutil.which("python3"),
    }

    payload: Dict[str, Any] = {
        "tool": APP,
        "version": __version__,
        "time": time.time(),
        "time_human": human_ts(time.time()),
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": sys.platform,
        "cwd": str(Path.cwd()),
        "shell": os.environ.get("SHELL"),
        "term": os.environ.get("TERM"),
        "tmux": "TMUX" in os.environ,
        "paths": {
            "VYBE_DIR": str(VYBE_DIR),
            "VYBE_STATE": str(VYBE_STATE),
            "VYBE_INDEX": str(VYBE_INDEX),
            "VYBE_MAX_INDEX": MAX_INDEX,
        },
        "clipboard_tools": clip_tools,
        "common_tools": common_tools,
        "git": {
            "repo_root": git_root,
            "branch": git_branch,
            "commit_short": git_commit,
            "dirty": git_dirty,
        },
    }

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"vybe doctor (v{__version__})")
    print(f"time: {payload['time_human']}")
    print(f"python: {payload['python_version']} ({payload['python_executable']})")
    print(f"platform: {payload['platform']}")
    print(f"cwd: {payload['cwd']}")
    print(f"shell: {payload['shell'] or '-'}")
    print(f"term: {payload['term'] or '-'}")
    print(f"tmux: {'yes' if payload['tmux'] else 'no'}")
    print("paths:")
    print(f"  VYBE_DIR: {payload['paths']['VYBE_DIR']}")
    print(f"  VYBE_STATE: {payload['paths']['VYBE_STATE']}")
    print(f"  VYBE_INDEX: {payload['paths']['VYBE_INDEX']}")
    print(f"  VYBE_MAX_INDEX: {payload['paths']['VYBE_MAX_INDEX']}")
    print("tools:")
    for name, path in {**common_tools, **clip_tools}.items():
        status = "✓" if path else "✗"
        print(f"  {name}: {path or 'missing'} {status}")
    if git_root:
        print("git:")
        print(f"  root: {git_root}")
        print(f"  branch: {git_branch or '-'}")
        print(f"  commit: {git_commit or '-'}")
        print(f"  dirty: {'yes' if git_dirty else 'no'}")
    else:
        print("git: not a repository")
    
    if explain:
        print("\n## Explanation")
        
        # Clipboard tools
        has_clipboard = any(clip_tools.values())
        if not has_clipboard:
            print("⚠️  Clipboard: No clipboard tool detected. Install xclip, xsel, or wl-clipboard to copy shares to clipboard.")
        else:
            print("✓ Clipboard: Detected. You can use `vybe share --clip` to copy to clipboard.")
        
        # Git
        if git_root:
            if git_dirty:
                print("⚠️  Git: You have uncommitted changes. Consider committing before sharing.")
            else:
                print("✓ Git: Repository is clean. Safe to share.")
        else:
            print("ℹ️  Git: Not in a git repository. Version control not available for this session.")
        
        # Terminal
        if os.environ.get("TERM"):
            print(f"✓ Terminal: {os.environ.get('TERM')} detected. Shell captures should work well.")
        else:
            print("⚠️  Terminal: TERM not set. Some shell features may not work correctly.")
        
        # Python
        if _in_virtualenv():
            print("✓ Python: Virtual environment detected. Package isolation intact.")
        else:
            print("ℹ️  Python: Not in a virtual environment. Consider using venv for project isolation.")
        
        # Vybe paths
        if VYBE_DIR.exists() and VYBE_STATE.exists():
            print("✓ Vybe: Configuration and state files exist. Vybe is properly initialized.")
        else:
            print("⚠️  Vybe: Missing config/state. Run `vybe init` to set up.")
    
    return 0

def cmd_cfg(args: List[str]) -> int:
    as_json = "--json" in args
    cfg = load_config()
    clip_cmd = _clipboard_cmd()
    payload = {
        "tool": APP,
        "version": __version__,
        "paths": {
            "VYBE_DIR": str(VYBE_DIR),
            "VYBE_STATE": str(VYBE_STATE),
            "VYBE_INDEX": str(VYBE_INDEX),
            "VYBE_CONFIG": str(VYBE_CONFIG),
            "VYBE_MAX_INDEX": MAX_INDEX,
        },
        "clipboard_detected": clip_cmd,
        "clipboard_tools": {
            "xclip": shutil.which("xclip"),
            "xsel": shutil.which("xsel"),
            "wl-copy": shutil.which("wl-copy"),
        },
        "config": cfg,
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"vybe cfg (v{__version__})")
    print("paths:")
    for k, v in payload["paths"].items():
        print(f"  {k}: {v}")
    print(f"clipboard_detected: {clip_cmd or 'none'}")
    print("clipboard_tools:")
    for k, v in payload["clipboard_tools"].items():
        print(f"  {k}: {v or 'missing'}")
    print("config:")
    if cfg:
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
    else:
        print("  {}")
    return 0

def cmd_project(args: List[str]) -> int:
    """Show project structure and metadata."""
    as_json = "--json" in args
    
    cwd = Path.cwd()
    
    # Gather project info
    info: Dict[str, Any] = {
        "tool": APP,
        "version": __version__,
        "cwd": str(cwd),
        "python_version": sys.version.split()[0],
    }
    
    # Check for pyproject.toml
    pyproject = cwd / "pyproject.toml"
    info["has_pyproject_toml"] = pyproject.exists()
    
    # Check for setup.py
    setup_py = cwd / "setup.py"
    info["has_setup_py"] = setup_py.exists()
    
    # Check for requirements files
    req_files = []
    for pattern in ["requirements.txt", "requirements*.txt", "Pipfile", "poetry.lock"]:
        req_files.extend(cwd.glob(pattern))
    info["requirement_files"] = sorted(set(str(f.name) for f in req_files))
    
    # Check for venv/virtualenv
    venv_dirs = []
    for d in [".venv", "venv", ".env", "env"]:
        vdir = cwd / d
        if vdir.exists() and (vdir / "bin" / "python").exists() or (vdir / "Scripts" / "python.exe").exists():
            venv_dirs.append(d)
    info["virtualenvs"] = venv_dirs
    info["in_virtualenv"] = _in_virtualenv()
    
    # Project structure (tree-like, limit depth)
    def tree(path: Path, prefix: str = "", depth: int = 0, max_depth: int = 2) -> List[str]:
        if depth > max_depth:
            return []
        lines = []
        try:
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            dirs = [i for i in items if i.is_dir() and not i.name.startswith(".")]
            files = [i for i in items if i.is_file() and not i.name.startswith(".")]
            
            # Limit to 10 items per directory
            items_to_show = (dirs + files)[:10]
            
            for i, item in enumerate(items_to_show):
                is_last = i == len(items_to_show) - 1
                current_prefix = "└── " if is_last else "├── "
                lines.append(f"{prefix}{current_prefix}{item.name}")
                
                if item.is_dir() and depth < max_depth:
                    next_prefix = prefix + ("    " if is_last else "│   ")
                    lines.extend(tree(item, next_prefix, depth + 1, max_depth))
        except (PermissionError, OSError):
            pass
        return lines
    
    tree_lines = [str(cwd.name)] + tree(cwd)
    info["structure"] = tree_lines[:30]  # Limit output
    
    if as_json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    
    print(f"Project: {cwd.name}")
    print(f"Path: {cwd}")
    print(f"Python: {info['python_version']}{' (venv)' if info['in_virtualenv'] else ''}")
    
    if info["has_pyproject_toml"]:
        print("✓ pyproject.toml found")
    if info["has_setup_py"]:
        print("✓ setup.py found")
    if info["requirement_files"]:
        print(f"✓ Requirements: {', '.join(info['requirement_files'])}")
    if info["virtualenvs"]:
        print(f"✓ Virtual environments: {', '.join(info['virtualenvs'])}")
    
    print("\nStructure:")
    for line in tree_lines:
        print(line)
    
    return 0

def cmd_self_check(args: List[str]) -> int:
    as_json = "--json" in args
    pipx_path = shutil.which("pipx")
    vybe_path = shutil.which("vybe")
    in_repo = (Path.cwd() / "pyproject.toml").exists() and (Path.cwd() / "src" / "vybe").exists()
    externally_managed = _is_externally_managed_python()
    in_venv = _in_virtualenv()

    recommendations: List[str] = []
    if externally_managed and not in_venv:
        recommendations.append("Detected externally-managed system Python (PEP 668).")
        if pipx_path:
            if in_repo:
                recommendations.append("Install/upgrade from this repo with: pipx install . --force")
            else:
                recommendations.append("Install with: pipx install vybe")
            recommendations.append("Upgrade later with: pipx upgrade vybe")
        else:
            recommendations.append("Install pipx first (e.g. apt install pipx), then use pipx install vybe.")
            if in_repo:
                recommendations.append("From this repo, use: pipx install . --force")
        recommendations.append("Alternative: use a virtualenv and install with pip inside that venv.")
    else:
        if in_venv:
            recommendations.append("Running inside a virtualenv. Install/update with: pip install -U vybe")
        else:
            recommendations.append("Python environment appears pip-installable. Install/update with: pip install -U vybe")

    payload = {
        "tool": APP,
        "version": __version__,
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "externally_managed": externally_managed,
        "in_virtualenv": in_venv,
        "pipx_available": bool(pipx_path),
        "pipx_path": pipx_path,
        "vybe_path": vybe_path,
        "cwd": str(Path.cwd()),
        "in_repo_checkout": in_repo,
        "recommendations": recommendations,
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"vybe self-check (v{__version__})")
    print(f"python: {payload['python_version']} ({payload['python_executable']})")
    print(f"externally_managed: {'yes' if externally_managed else 'no'}")
    print(f"in_virtualenv: {'yes' if in_venv else 'no'}")
    print(f"pipx: {pipx_path or 'missing'}")
    print(f"vybe_path: {vybe_path or 'not found'}")
    print("recommendations:")
    for rec in recommendations:
        print(f"  - {rec}")
    return 0

def cmd_init(args: List[str]) -> int:
    force = "--force" in args
    ensure_dirs()
    clip_cmd = _clipboard_cmd()
    cfg = load_config()
    if cfg and not force:
        print(f"Config already exists: {VYBE_CONFIG}")
        print("Use `vybe init --force` to overwrite detected defaults.")
        return 0
    cfg = {
        "created_at": time.time(),
        "created_at_human": human_ts(time.time()),
        "paths": {
            "VYBE_DIR": str(VYBE_DIR),
            "VYBE_STATE": str(VYBE_STATE),
            "VYBE_INDEX": str(VYBE_INDEX),
            "VYBE_CONFIG": str(VYBE_CONFIG),
        },
        "clipboard": {
            "preferred_cmd": clip_cmd,
            "tool": clip_cmd[0] if clip_cmd else None,
        },
    }
    save_config(cfg)
    print(f"Initialized: {VYBE_CONFIG}")
    if clip_cmd:
        print(f"Detected clipboard tool: {clip_cmd[0]}")
    else:
        print("No clipboard tool detected (install xclip/xsel or wl-clipboard).")
    return 0

def cmd_completion(args: List[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        print("Usage: vybe completion install <zsh|bash|fish>", file=sys.stderr)
        return 2
    sub = args[0]
    if sub != "install":
        print("Usage: vybe completion install <zsh|bash|fish>", file=sys.stderr)
        return 2
    if len(args) < 2:
        print("Usage: vybe completion install <zsh|bash|fish>", file=sys.stderr)
        return 2
    shell = args[1]
    src_dir = completion_sources_dir()
    mapping = {
        "zsh": ("_vybe", HOME / ".zsh" / "completions" / "_vybe"),
        "bash": ("vybe.bash", HOME / ".local" / "share" / "bash-completion" / "completions" / "vybe"),
        "fish": ("vybe.fish", HOME / ".config" / "fish" / "completions" / "vybe.fish"),
    }
    if shell not in mapping:
        print("Shell must be one of: zsh, bash, fish", file=sys.stderr)
        return 2
    src_name, dest = mapping[shell]
    src = src_dir / src_name
    if not src.exists():
        print(f"Completion source not found: {src}", file=sys.stderr)
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    print(f"Installed {shell} completion: {dest}")
    if shell == "zsh":
        print("If needed, ensure this in ~/.zshrc:")
        print("  fpath=(~/.zsh/completions $fpath)")
        print("  autoload -Uz compinit && compinit")
    elif shell == "bash":
        print("If not auto-loaded, add to your shell profile:")
        print(f"  source {dest}")
    else:
        print("Fish should auto-load completions from ~/.config/fish/completions.")
    return 0

def cmd_tags(_args: List[str]) -> int:
    records = load_index_records()
    if not records:
        print("No index yet. Run: vybe run <cmd...>", file=sys.stderr)
        return 1
    counts: Dict[str, int] = {}
    for rec in records:
        tag = rec.get("tag")
        if not tag:
            continue
        counts[tag] = counts.get(tag, 0) + 1
    if not counts:
        print("No tags found yet.")
        return 0
    for tag, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{tag}\t{count}")
    return 0

def cmd_share(args: List[str]) -> int:
    include_full = "--full" in args
    redact = "--redact" in args
    copy_clip = "--clip" in args
    include_errors = "--errors" in args
    as_json = "--json" in args
    smart = "--smart" in args

    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1

    st = load_state()
    full_text = read_text(p)
    body_text = full_text if include_full else strip_header(full_text)

    cmd = st.get("last_cmd") if isinstance(st.get("last_cmd"), list) else []
    cmd_str = shell_quote_cmd(cmd) if cmd else ""
    if redact:
        body_text = redact_text(body_text)
        cmd_str = redact_text(cmd_str)

    tag = st.get("last_tag")
    rc = st.get("last_rc")
    t = st.get("last_time")
    t_human = human_ts(float(t)) if t else "-"
    cwd = st.get("last_cwd") or "-"

    lines = [
        "## Vybe Share",
        f"- time: {t_human}",
        f"- rc: {rc}",
        f"- cwd: `{cwd}`",
        f"- file: `{p}`",
    ]
    if tag:
        lines.append(f"- tag: `{tag}`")
    if cmd_str:
        lines.append(f"- cmd: `{cmd_str}`")
    
    # Add smart context if requested
    smart_context: Dict[str, str] = {}
    if smart:
        smart_context = _gather_smart_context()
        if smart_context.get("python"):
            lines.append(f"- python: `{smart_context['python']}`")
        if smart_context.get("venv"):
            lines.append("- venv: `active`")
        if smart_context.get("git_status"):
            lines.append("")
            lines.append("### Git Status")
            lines.append("```text")
            lines.append(smart_context["git_status"])
            lines.append("```")
    
    lines.extend(["", "### Output", "```text", body_text.rstrip("\n"), "```"])

    # Add ls if smart mode
    if smart and smart_context.get("ls"):
        lines.insert(-2, "")
        lines.insert(-2, "### Directory Listing")
        lines.insert(-2, "```text")
        lines.insert(-2, smart_context["ls"])
        lines.insert(-2, "```")

    if include_errors:
        blocks = extract_error_blocks(full_text)
        if redact:
            blocks = [redact_text(b) for b in blocks]
        if as_json:
            payload = {
                "tool": APP,
                "version": __version__,
                "time": t,
                "time_human": t_human,
                "rc": rc,
                "cwd": cwd,
                "file": str(p),
                "cmd": cmd,
                "cmd_str": cmd_str,
                "tag": tag,
                "full": include_full,
                "redacted": redact,
                "errors_included": include_errors,
                "smart": smart,
                "context": smart_context if smart else {},
                "output": body_text,
                "error_blocks": blocks,
            }
            text_out = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        else:
            if blocks:
                lines.append("")
                lines.append("### Error Extract")
                for i, block in enumerate(blocks, start=1):
                    lines.append(f"#### error:{i}")
                    lines.append("```text")
                    lines.append(block.rstrip("\n"))
                    lines.append("```")
            text_out = "\n".join(lines) + "\n"
    else:
        if as_json:
            payload = {
                "tool": APP,
                "version": __version__,
                "time": t,
                "time_human": t_human,
                "rc": rc,
                "cwd": cwd,
                "file": str(p),
                "cmd": cmd,
                "cmd_str": cmd_str,
                "tag": tag,
                "full": include_full,
                "redacted": redact,
                "errors_included": include_errors,
                "smart": smart,
                "context": smart_context if smart else {},
                "output": body_text,
                "error_blocks": [],
            }
            text_out = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        else:
            text_out = "\n".join(lines) + "\n"

    if copy_clip:
        rc_clip = _clipboard_write_bytes(text_out.encode("utf-8", errors="replace"))
        if rc_clip == 0:
            if as_json:
                print("Copied share JSON to clipboard.")
            else:
                print("Copied share bundle to clipboard.")
        return rc_clip
    sys.stdout.write(text_out)
    return 0

def cmd_prompt(args: List[str]) -> int:
    if not args:
        print("Usage: vybe prompt <debug|review|explain> [--redact] [extra request...]", file=sys.stderr)
        return 2

    mode = args[0]
    rest = args[1:]
    redact = "--redact" in rest
    extra_parts = [a for a in rest if a != "--redact"]
    extra = " ".join(extra_parts).strip()

    if mode not in ("debug", "review", "explain"):
        print("Mode must be one of: debug, review, explain", file=sys.stderr)
        return 2

    p = latest_file()
    if not p or not p.exists():
        print("No previous capture. Use: vybe run <cmd...>", file=sys.stderr)
        return 1

    st = load_state()
    cmd = st.get("last_cmd") if isinstance(st.get("last_cmd"), list) else []
    cmd_str = shell_quote_cmd(cmd) if cmd else "-"
    rc = st.get("last_rc")
    cwd = st.get("last_cwd") or "-"
    tag = st.get("last_tag")
    t = st.get("last_time")
    t_human = human_ts(float(t)) if t else "-"

    output = strip_header(read_text(p))
    if redact:
        output = redact_text(output)
        cmd_str = redact_text(cmd_str)

    mode_prompts = {
        "debug": "Find root cause and propose the smallest safe fix.",
        "review": "Review this output and suggest risks, regressions, and missing tests.",
        "explain": "Explain what happened in plain language and what to do next.",
    }

    lines = [
        f"# Vybe Prompt ({mode})",
        "",
        "You are helping with a terminal capture from Vybe.",
        mode_prompts[mode],
    ]
    if extra:
        lines.append(f"Extra request: {extra}")
    lines.extend([
        "",
        "## Context",
        f"- time: {t_human}",
        f"- command: `{cmd_str}`",
        f"- exit code: {rc}",
        f"- cwd: `{cwd}`",
        f"- file: `{p}`",
    ])
    if tag:
        lines.append(f"- tag: `{tag}`")
    lines.extend([
        "",
        "## Output",
        "```text",
        output.rstrip("\n"),
        "```",
        "",
        "## Response format",
        "1. Diagnosis",
        "2. Most likely root cause",
        "3. Minimal fix",
        "4. Verification steps",
    ])
    print("\n".join(lines) + "\n")
    return 0

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
    set_latest_file(
        outfile,
        cmd=["tmux", "capture-pane", "-p", "-S", f"-{lines}"],
        rc=0,
        t=end,
        cwd=str(Path.cwd()),
        kind="pane",
        tag=None,
    )
    append_index({
        "time": end,
        "stamp": stamp,
        "file": str(outfile),
        "cmd": ["tmux", "capture-pane", "-p", "-S", f"-{lines}"],
        "rc": 0,
        "dur_s": 0,
        "kind": "pane",
        "cwd": str(Path.cwd()),
        "tag": None,
    })
    print(f"Saved: {outfile}")
    return 0

def cmd_version(_args: List[str]) -> int:
    print(__version__)
    return 0

def cmd_cmdcopy(_args: List[str]) -> int:
    """Copy only the last command to clipboard (useful for re-running with tweaks)."""
    st = load_state()
    cmd = st.get("last_cmd") if isinstance(st.get("last_cmd"), list) else []
    if not cmd:
        print("No previous command found. Use: vybe run <cmd...>", file=sys.stderr)
        return 1
    cmd_str = shell_quote_cmd(cmd)
    rc = _clipboard_write_bytes(cmd_str.encode("utf-8", errors="replace"))
    if rc == 0:
        print(f"Copied command: {cmd_str}")
    return rc

def cmd_history(args: List[str]) -> int:
    """Copy last N commands with outputs together for bulk LLM handoff."""
    redact = "--redact" in args
    as_json = "--json" in args
    print_only = "--print" in args  # For testing: print instead of copy
    n = 3
    
    for arg in args:
        if arg not in ("--redact", "--json", "--print"):
            try:
                n = int(arg)
                break
            except ValueError:
                pass
    
    records = load_index_records()
    if not records:
        print("No index yet. Run: vybe run <cmd...>", file=sys.stderr)
        return 1
    
    selected = [r for r in reversed(records) if r.get("kind") == "run"][-n:]
    if not selected:
        print(f"Need at least 1 capture. Found {len(records)} total.", file=sys.stderr)
        return 1
    
    if as_json:
        payload = {
            "tool": APP,
            "version": __version__,
            "time": time.time(),
            "time_human": human_ts(time.time()),
            "batch_size": len(selected),
            "redacted": redact,
            "captures": [],
        }
        for rec in selected:
            p = Path(rec.get("file", ""))
            if not p.exists():
                continue
            text = read_text(p)
            output = strip_header(text)
            if redact:
                text = redact_text(text)
                output = redact_text(output)
            cmd = rec.get("cmd", [])
            cmd_str = shell_quote_cmd(cmd) if cmd else "-"
            payload["captures"].append({
                "time": rec.get("time"),
                "time_human": human_ts(rec.get("time", 0)),
                "cmd": cmd,
                "cmd_str": cmd_str,
                "rc": rec.get("rc"),
                "output": output,
                "cwd": rec.get("cwd"),
            })
        text_out = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    else:
        lines = [
            f"# Vybe History ({len(selected)} captures)",
            "",
        ]
        for i, rec in enumerate(selected, start=1):
            p = Path(rec.get("file", ""))
            if not p.exists():
                continue
            text = read_text(p)
            output = strip_header(text)
            if redact:
                text = redact_text(text)
                output = redact_text(output)
            cmd = rec.get("cmd", [])
            cmd_str = shell_quote_cmd(cmd) if cmd else "-"
            rc = rec.get("rc", "?")
            t = human_ts(rec.get("time", 0))
            
            lines.extend([
                f"## [{i}] {t} (rc={rc})",
                f"```bash",
                f"$ {cmd_str}",
                f"```",
                "",
                "### Output",
                "```text",
                output.rstrip("\n"),
                "```",
                "",
            ])
        text_out = "\n".join(lines)
    
    if print_only:
        # For testing: just print to stdout
        print(text_out)
        return 0
    
    rc_clip = _clipboard_write_bytes(text_out.encode("utf-8", errors="replace"))
    if rc_clip == 0:
        if as_json:
            print(f"Copied {len(selected)} captures (JSON) to clipboard.")
        else:
            print(f"Copied {len(selected)} captures to clipboard.")
    return rc_clip

def cmd_select(_args: List[str]) -> int:
    """Interactively select and copy past captures (requires fzf)."""
    fzf_path = shutil.which("fzf")
    if not fzf_path:
        print("vybe select requires fzf. Install: apt install fzf", file=sys.stderr)
        return 1
    
    records = load_index_records()
    if not records:
        print("No captures yet. Run: vybe run <cmd...>", file=sys.stderr)
        return 1
    
    lines = []
    for rec in reversed(records):
        if rec.get("kind") != "run":
            continue
        t = human_ts(rec.get("time", 0))
        rc = rec.get("rc", "?")
        cmd = shell_quote_cmd(rec.get("cmd", []))
        f = rec.get("file", "")
        lines.append(f"{t} [rc={rc}] {cmd} | {f}")
    
    if not lines:
        print("No run captures found.", file=sys.stderr)
        return 1
    
    proc = subprocess.Popen(
        ["fzf", "-m", "--preview", "cat {-1}"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    stdout, _ = proc.communicate("\n".join(lines))
    
    if proc.returncode != 0 or not stdout.strip():
        return 1
    
    selected_files = []
    for line in stdout.strip().split("\n"):
        parts = line.split(" | ")
        if len(parts) > 1:
            selected_files.append(parts[-1])
    
    if not selected_files:
        return 1
    
    combined_text = []
    for i, fpath in enumerate(selected_files, start=1):
        p = Path(fpath)
        if p.exists():
            combined_text.append(f"--- [{i}] {p.name} ---")
            combined_text.append(read_text(p))
            combined_text.append("")
    
    text_out = "\n".join(combined_text)
    rc_clip = _clipboard_write_bytes(text_out.encode("utf-8", errors="replace"))
    if rc_clip == 0:
        print(f"Copied {len(selected_files)} selected captures to clipboard.")
    return rc_clip

def cmd_watch(args: List[str]) -> int:
    """Watch for file changes and auto-rerun command (requires watchmedo from watchdog)."""
    if not args:
        print("Usage: vybe watch <cmd...>", file=sys.stderr)
        return 2
    
    tag = "watch-session"
    print(f"Watching mode (tag: {tag}). Press Ctrl+C to stop.")
    print(f"Initial run: {shell_quote_cmd(args)}")
    
    rc = _run_capture(args, tag=tag)
    
    print(f"\nFor auto-rerun on file change, install watchdog:")
    print(f"  pip install watchdog")
    print(f"  watchmedo shell-command --patterns='*.py' --recursive --command='vybe r {shell_quote_cmd(args)}' .")
    
    return rc

def cmd_cwd(args: List[str]) -> int:
    """Remember current directory and re-run last command from it (useful after directory changes)."""
    st = load_state()
    
    if not args or args[0] == "set":
        cwd = str(Path.cwd())
        st["saved_cwd"] = cwd
        save_state(st)
        print(f"Saved working directory: {cwd}")
        return 0
    
    if args[0] == "run":
        saved_cwd = st.get("saved_cwd")
        if not saved_cwd:
            print("No saved working directory. Use: vybe cwd set", file=sys.stderr)
            return 1
        
        last_cmd = st.get("last_cmd")
        if not isinstance(last_cmd, list) or not last_cmd:
            print("No previous command found. Use: vybe run <cmd...>", file=sys.stderr)
            return 1
        
        print(f"Running in: {saved_cwd}")
        return _run_capture(last_cmd, cwd=saved_cwd, tag=st.get("last_tag"))
    
    print("Usage: vybe cwd <set|run>", file=sys.stderr)
    return 2

def cmd_clean(args: List[str]) -> int:
    """Clean up old captures to reclaim disk space."""
    keep = 100
    before_days = None
    
    i = 0
    while i < len(args):
        if args[i] == "--keep":
            if i + 1 < len(args):
                try:
                    keep = int(args[i + 1])
                    i += 2
                except ValueError:
                    i += 1
            else:
                i += 1
        elif args[i] == "--before":
            if i + 1 < len(args):
                try:
                    before_days = int(args[i + 1])
                    i += 2
                except ValueError:
                    i += 1
            else:
                i += 1
        else:
            i += 1
    
    records = load_index_records()
    if not records:
        print("No captures to clean.")
        return 0
    
    now = time.time()
    cutoff_time = now - (before_days * 86400) if before_days else 0
    deleted_count = 0
    
    sorted_recs = sorted(records, key=lambda r: r.get("time", 0))
    
    to_delete = sorted_recs[:-keep] if len(sorted_recs) > keep else []
    if before_days:
        to_delete = [r for r in sorted_recs if r.get("time", 0) < cutoff_time]
    
    for rec in to_delete:
        p = Path(rec.get("file", ""))
        if p.exists():
            try:
                p.unlink()
                deleted_count += 1
            except Exception:
                pass
    
    print(f"Deleted {deleted_count} old captures.")
    return 0

def cmd_stats(_args: List[str]) -> int:
    """Show statistics on runs: success rate, most-run commands, slowest runs."""
    records = load_index_records()
    if not records:
        print("No captures yet. Run: vybe run <cmd...>", file=sys.stderr)
        return 1
    
    runs = [r for r in records if r.get("kind") == "run"]
    if not runs:
        print("No run captures found.")
        return 0
    
    total = len(runs)
    failed = len([r for r in runs if r.get("rc", 0) != 0])
    success_rate = 100 * (total - failed) / total if total > 0 else 0
    
    cmd_counts: Dict[str, int] = {}
    for r in runs:
        cmd = shell_quote_cmd(r.get("cmd", []))
        cmd_counts[cmd] = cmd_counts.get(cmd, 0) + 1
    
    slowest = sorted(runs, key=lambda r: r.get("dur_s", 0), reverse=True)[:5]
    
    print(f"=== Vybe Stats ===")
    print(f"Total runs: {total}")
    print(f"Succeeded: {total - failed}")
    print(f"Failed: {failed}")
    print(f"Success rate: {success_rate:.1f}%")
    print()
    print("Top commands:")
    for cmd, count in sorted(cmd_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]:
        print(f"  {count}x {cmd}")
    print()
    print("Slowest runs:")
    for i, rec in enumerate(slowest, 1):
        t = human_ts(rec.get("time", 0))
        dur = rec.get("dur_s", "?")
        cmd = shell_quote_cmd(rec.get("cmd", []))
        print(f"  {i}. {dur}s - {cmd} ({t})")
    
    return 0

def cmd_link(args: List[str]) -> int:
    """Start local web server to share captures (useful for screenshots/links)."""
    port = 8765
    
    for arg in args:
        try:
            port = int(arg)
        except ValueError:
            pass
    
    print(f"Vybe web server would run on http://localhost:{port}")
    print("(Not yet implemented - use vybe export/share for now)")
    print()
    print("To share a specific capture, use:")
    print("  vybe share --clip")
    print("  vybe export --last --json")
    print("  vybe share --json | curl -X POST https://your-service.com/api/share")
    
    return 0

def cmd_flow(args: List[str]) -> int:
    """Save and replay common command sequences."""
    if not args or args[0] in ("list", "ls"):
        cfg = load_config()
        flows = cfg.get("flows", {})
        if not flows:
            print("No flows saved. Use: vybe flow save <name> <cmd...>")
            return 0
        print("Saved flows:")
        for name, data in flows.items():
            cmds = data.get("commands", [])
            print(f"  {name}: {' && '.join(cmds)}")
        return 0
    
    if args[0] == "save" and len(args) >= 3:
        name = args[1]
        cmds = args[2:]
        cfg = load_config()
        if "flows" not in cfg:
            cfg["flows"] = {}
        cfg["flows"][name] = {"commands": cmds, "created_at": time.time()}
        save_config(cfg)
        print(f"Saved flow: {name}")
        return 0
    
    if args[0] == "run" and len(args) >= 2:
        name = args[1]
        cfg = load_config()
        flows = cfg.get("flows", {})
        if name not in flows:
            print(f"Flow not found: {name}", file=sys.stderr)
            return 1
        
        cmds = flows[name].get("commands", [])
        print(f"Running flow: {name}")
        for cmd in cmds:
            print(f"\n$ {cmd}")
            parsed = shlex.split(cmd)
            _run_capture(parsed, tag=f"flow-{name}")
        return 0
    
    print("Usage: vybe flow <list|save <name> <cmd...>|run <name>>", file=sys.stderr)
    return 2

def cmd_man(_args: List[str]) -> int:
    """Display the full manual."""
    pager = os.environ.get("PAGER", "less")
    # Try multiple locations for the manual
    possible_paths = [
        Path(__file__).resolve().parent / "man.md",  # in package
        Path(__file__).resolve().parents[2] / "docs" / "man.md",  # dev mode
        Path("/usr/share/doc/vybe/man.md"),  # system install
        Path("/usr/local/share/doc/vybe/man.md"),  # local system install
    ]
    for man_path in possible_paths:
        if man_path.exists():
            return subprocess.call([pager, str(man_path)])
    print("Manual not found. Use `vybe --help` for quick help.", file=sys.stderr)
    return 1

# ---------- help / dispatch ----------

def help_text() -> str:
    return f"""vybe - vibe coding terminal capture toolkit (v{__version__})

Commands:
  vybe run [--tag <name>] <cmd...>
                           Run command, show output live, save to log
  vybe r <cmd...>          Alias for `vybe run`
  vybe retry [--cwd] [--tag <name>]
                           Re-run the last `vybe run` command
  vybe rr [--cwd] [--tag <name>]
                           Alias for `vybe retry`
  vybe last                Print most recent capture (header + output)
  vybe l                   Alias for `vybe last`
  vybe snip [--redact]     Print output only (strip `$ cmd` header)
  vybe s                   Alias for `vybe snip`
  vybe snipclip [--redact] Copy output only to clipboard
  vybe sc                  Alias for `vybe snipclip`
  vybe cmdcopy             Copy only the last command to clipboard
  vybe cc                  Alias for `vybe cmdcopy`
  vybe tail [N]            Print last N lines of most recent capture (default 80)
  vybe open                Open most recent capture in $PAGER
  vybe o                   Alias for `vybe open`
  vybe ls [N] [--tag <name>]
                           List last N captures (default 12)
  vybe ll [N]              Alias for `vybe ls`
  vybe grep <pat> [--i]    Search the most recent capture (regex)
  vybe md [lang]           Wrap last capture in Markdown fences
  vybe clip                Copy last capture to clipboard
  vybe fail                Select most recent failing run as "last"
  vybe errors              Extract likely error blocks from most recent capture
  vybe history [N] [--redact] [--json]
                           Copy last N commands+outputs together (default 3)
  vybe select              Interactively pick captures to copy (requires fzf)
  vybe export --last --json [--snip] [--redact]
                           Export latest capture in machine-readable JSON
  vybe diff [--full] [--tag <name>]
                           Unified diff: latest capture vs previous capture
  vybe share [--full] [--redact] [--errors] [--json] [--clip]
                           Build a Markdown share bundle from latest capture
  vybe prompt <debug|review|explain> [--redact] [extra request...]
                           Generate an LLM-ready prompt from latest capture
  vybe watch <cmd...>      Auto-rerun command on changes (tag: watch-session)
  vybe cwd <set|run>       Remember and restore working directory across commands
  vybe clean [--keep N] [--before <days>]
                           Clean up old captures to reclaim disk space
  vybe stats               Show success rate, most-run commands, slowest runs
  vybe link [PORT]         Start web server for sharing captures (dev mode)
  vybe flow <list|save|run>
                           Save and replay command sequences
  vybe doctor [--json]     Print environment/debug snapshot
  vybe self-check [--json]
                           Check install environment and print update guidance
  vybe cfg [--json]        Print current config and effective paths
  vybe init [--force]      Initialize ~/.config/vybe defaults
  vybe completion install <zsh|bash|fish>
                           Install shell completion
  vybe tags                List known tags and usage counts
  vybe pane [LINES]        (tmux) capture pane scrollback (default 2000)
  vybe version             Print version
  vybe man                 Show full manual

Flags:
  -h, --help, -H, -Help, -HELP, help, HELP
                           Show help (supports all variations)
  --version                Print version

Env:
  VYBE_DIR        log dir (default ~/.cache/vybe)
  VYBE_STATE      state file (default ~/.config/vybe/state.json)
  VYBE_INDEX      index file (default ~/.cache/vybe/index.jsonl)
  VYBE_CONFIG     config file (default ~/.config/vybe/config.json)
  VYBE_MAX_INDEX  max index entries (default 2000)
"""

def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help", "-H", "-Help", "-HELP", "help", "HELP"):
        print(help_text())
        return 0
    if argv[0] == "--version":
        return cmd_version([])

    cmd = argv[0]
    args = argv[1:]

    dispatch = {
        "run": cmd_run,
        "r": cmd_run,
        "retry": cmd_retry,
        "rr": cmd_retry,
        "last": cmd_last,
        "l": cmd_last,
        "snip": cmd_snip,
        "s": cmd_snip,
        "snipclip": cmd_snipclip,
        "sc": cmd_snipclip,
        "cmdcopy": cmd_cmdcopy,
        "cc": cmd_cmdcopy,
        "tail": cmd_tail,
        "open": cmd_open,
        "o": cmd_open,
        "ls": cmd_ls,
        "ll": cmd_ls,
        "grep": cmd_grep,
        "md": cmd_md,
        "clip": cmd_clip,
        "fail": cmd_fail,
        "errors": cmd_errors,
        "history": cmd_history,
        "select": cmd_select,
        "export": cmd_export,
        "diff": cmd_diff,
        "share": cmd_share,
        "prompt": cmd_prompt,
        "watch": cmd_watch,
        "cwd": cmd_cwd,
        "clean": cmd_clean,
        "stats": cmd_stats,
        "link": cmd_link,
        "flow": cmd_flow,
        "doctor": cmd_doctor,
        "project": cmd_project,
        "proj": cmd_project,
        "self-check": cmd_self_check,
        "cfg": cmd_cfg,
        "init": cmd_init,
        "completion": cmd_completion,
        "tags": cmd_tags,
        "pane": cmd_pane,
        "man": cmd_man,
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
