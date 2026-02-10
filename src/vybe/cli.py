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

# ---------- commands ----------

def _run_capture(args: List[str], cwd: Optional[str] = None, tag: Optional[str] = None) -> int:
    ensure_dirs()
    stamp = now_stamp()
    outfile = VYBE_DIR / f"vybe_{stamp}.log"
    cmd_str = shell_quote_cmd(args)
    outfile.write_text(f"$ {cmd_str}\n---\n", encoding="utf-8")

    start = time.time()
    interrupted = False
    proc: Optional[subprocess.Popen[str]] = None
    run_cwd = cwd if cwd is not None else str(Path.cwd())

    try:
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
    if args[:1] == ["--tag"]:
        if len(args) < 3:
            print("Usage: vybe run [--tag <name>] <command...>", file=sys.stderr)
            return 2
        tag = args[1]
        args = args[2:]
    if not args:
        print("Usage: vybe run [--tag <name>] <command...>", file=sys.stderr)
        return 2
    return _run_capture(args, tag=tag)

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
        print(f"  {name}: {path or 'missing'}")
    if git_root:
        print("git:")
        print(f"  root: {git_root}")
        print(f"  branch: {git_branch or '-'}")
        print(f"  commit: {git_commit or '-'}")
        print(f"  dirty: {'yes' if git_dirty else 'no'}")
    else:
        print("git: not a repository")
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
    lines.extend(["", "### Output", "```text", body_text.rstrip("\n"), "```"])

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
  vybe export --last --json [--snip] [--redact]
                           Export latest capture in machine-readable JSON
  vybe diff [--full] [--tag <name>]
                           Unified diff: latest capture vs previous capture
  vybe share [--full] [--redact] [--errors] [--json] [--clip]
                           Build a Markdown share bundle from latest capture
  vybe doctor [--json]     Print environment/debug snapshot
  vybe cfg [--json]        Print current config and effective paths
  vybe init [--force]      Initialize ~/.config/vybe defaults
  vybe completion install <zsh|bash|fish>
                           Install shell completion
  vybe tags                List known tags and usage counts
  vybe pane [LINES]        (tmux) capture pane scrollback (default 2000)
  vybe version             Print version

Flags:
  -h, --help               Show help
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

    if not argv or argv[0] in ("-h", "--help", "help"):
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
        "export": cmd_export,
        "diff": cmd_diff,
        "share": cmd_share,
        "doctor": cmd_doctor,
        "cfg": cmd_cfg,
        "init": cmd_init,
        "completion": cmd_completion,
        "tags": cmd_tags,
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
