#!/usr/bin/env python3
import os, sys, json, time, re, shlex, subprocess, shutil
from pathlib import Path

APP = "vybe"
HOME = Path.home()

VYBE_DIR = Path(os.environ.get("VYBE_DIR", str(HOME / ".cache" / APP)))
VYBE_STATE = Path(os.environ.get("VYBE_STATE", str(HOME / ".config" / APP / "state.json")))
VYBE_INDEX = Path(os.environ.get("VYBE_INDEX", str(HOME / ".cache" / APP / "index.jsonl")))
MAX_INDEX = int(os.environ.get("VYBE_MAX_INDEX", "2000"))

def now_stamp():
    return time.strftime("%Y%m%d_%H%M%S")

def ensure_dirs():
    VYBE_DIR.mkdir(parents=True, exist_ok=True)
    VYBE_STATE.parent.mkdir(parents=True, exist_ok=True)
    VYBE_INDEX.parent.mkdir(parents=True, exist_ok=True)

def load_state():
    try:
        return json.loads(VYBE_STATE.read_text())
    except Exception:
        return {}

def save_state(state):
    VYBE_STATE.write_text(json.dumps(state, indent=2))

def append_index(record: dict):
    ensure_dirs()
    with VYBE_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    trim_index()

def trim_index():
    try:
        if not VYBE_INDEX.exists():
            return
        lines = VYBE_INDEX.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) <= MAX_INDEX:
            return
        VYBE_INDEX.write_text("\n".join(lines[-MAX_INDEX:]) + "\n", encoding="utf-8")
    except Exception:
        pass

def latest_file():
    st = load_state()
    p = st.get("last_file")
    return Path(p) if p else None

def set_latest_file(path: Path, cmd=None, rc=None, t=None):
    st = load_state()
    st["last_file"] = str(path)
    if cmd is not None:
        st["last_cmd"] = cmd
    if rc is not None:
        st["last_rc"] = rc
    if t is not None:
        st["last_time"] = t
    save_state(st)

def shell_quote_cmd(args):
    return " ".join(shlex.quote(a) for a in args)

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def strip_header(text: str) -> str:
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("$ ") and lines[1].strip() == "---":
        return "\n".join(lines[2:]).lstrip("\n")
    return text

def cmd_run(args):
    if not args:
        print("Usage: vybe run <cmd...>", file=sys.stderr)
        return 2
    ensure_dirs()
    stamp = now_stamp()
    out = VYBE_DIR / f"vybe_{stamp}.log"
    out.write_text(f"$ {shell_quote_cmd(args)}\n---\n", encoding="utf-8")
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    with out.open("a", encoding="utf-8", errors="replace") as f:
        for line in proc.stdout:
            sys.stdout.write(line)
            f.write(line)
    rc = proc.wait()
    t = time.time()
    set_latest_file(out, cmd=args, rc=rc, t=t)
    append_index({"time": t, "file": str(out), "cmd": args, "rc": rc, "kind": "run"})
    print(f"\nSaved: {out}")
    return rc

def cmd_last(_):
    p = latest_file()
    if not p: return 1
    print(read_text(p), end="")
    return 0

def cmd_snip(_):
    p = latest_file()
    if not p: return 1
    print(strip_header(read_text(p)), end="")
    return 0

def cmd_snipclip(_):
    p = latest_file()
    if not p: return 1
    text = strip_header(read_text(p)).encode()
    subprocess.run(["xclip","-selection","clipboard"], input=text)
    print("Copied snip to clipboard.")
    return 0

def cmd_fail(_):
    if not VYBE_INDEX.exists(): return 1
    for line in reversed(VYBE_INDEX.read_text().splitlines()):
        rec = json.loads(line)
        if rec.get("kind")=="run" and rec.get("rc",0)!=0:
            set_latest_file(Path(rec["file"]), rec["cmd"], rec["rc"], rec["time"])
            print(f"Selected failing capture: {rec['file']}")
            return 0
    return 1

def main():
    if len(sys.argv)<2:
        print("vybe run <cmd...> | vybe snip | vybe snipclip | vybe fail")
        return 0
    cmd,args=sys.argv[1],sys.argv[2:]
    return {
        "run":cmd_run,
        "last":cmd_last,
        "snip":cmd_snip,
        "snipclip":cmd_snipclip,
        "fail":cmd_fail,
    }.get(cmd,lambda _:1)(args)

if __name__=="__main__":
    sys.exit(main())
