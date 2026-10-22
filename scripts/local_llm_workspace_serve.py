"""Launch FastAPI + Next.js for M1.7B, local development only.

No key is written to files or passed in a command-line argument. One-shot
paid requests only occur after a browser button click; session budget is four.
"""
from __future__ import annotations

import getpass
from hashlib import sha256
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "FRP_LOCAL_SOURCE_PDF_600276": (
        Path.home() / ".cache/frp-cn-table-pilot/sources/600276/2026H1/source.pdf",
        "ff6910663a9726acb889aa061a8bab1433f58890d81ebea013b8c637a097a7aa",
    ),
    "FRP_LOCAL_SOURCE_PDF_600760": (
        ROOT / "data/raw/600760/2026H1/source.pdf",
        "d53ee98c091fdcbb8df3ebcc3f8d9bef87f61b374615dc3165dadb594f637d99",
    ),
}


def main() -> int:
    if not (ROOT / ".git").is_dir() or not (ROOT / ".venv/bin/python").is_file():
        print("STOP: WRONG_REPOSITORY_OR_MISSING_VENV")
        return 2
    for env, (path, expected_hash) in SOURCES.items():
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected_hash:
            print(f"STOP: ORIGINAL_SOURCE_UNAVAILABLE_OR_CHANGED ({env})")
            return 2
    # Ports must be vacant; do not start two accidental paid backends.
    import socket
    for port in (8000, 3000):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                print(f"STOP: PORT_{port}_IN_USE. Stop the old dev server first.")
                return 2
    key = getpass.getpass("DeepSeek key (hidden; backend process only): ").strip()
    if not key:
        print("STOP: EMPTY_KEY")
        return 2
    secret = secrets.token_urlsafe(48)
    base = os.environ.copy()
    base.pop("DEEPSEEK_API_KEY", None)
    base.update({"FRP_LOCAL_SOURCE_WORKSPACE": "1", "FRP_LOCAL_LLM_UI": "1",
                 "FRP_LOCAL_LLM_ACCESS_TOKEN": secret})
    for name, (path, _) in SOURCES.items():
        base[name] = str(path)
    api_env = dict(base, DEEPSEEK_API_KEY=key)
    key = ""  # Best-effort only; Python cannot guarantee secure memory erasure.
    web_env = dict(base, RESEARCH_API_BASE_URL="http://127.0.0.1:8000")
    children: list[subprocess.Popen] = []
    try:
        api_cmd = [str(ROOT / ".venv/bin/python"), "-m", "uvicorn", "app.main:app",
                   "--app-dir", "services/api", "--host", "127.0.0.1", "--port", "8000"]
        web_cmd = ["npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3000"]
        children.append(subprocess.Popen(api_cmd, cwd=ROOT, env=api_env, start_new_session=True))
        children.append(subprocess.Popen(web_cmd, cwd=ROOT / "apps/web", env=web_env, start_new_session=True))
        del api_env
        print("M17B_LOCAL_SERVERS_STARTED", flush=True)
        print("OPEN: http://127.0.0.1:3000/research/source-workspace/ask", flush=True)
        print("PAID CALL LIMIT: 4 per API process. No automatic retries.", flush=True)
        while True:
            for proc in children:
                if proc.poll() is not None:
                    print("STOP: DEV_SERVER_EXITED", flush=True)
                    return 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("STOPPING LOCAL RESEARCH SERVERS", flush=True)
        return 0
    finally:
        for proc in children:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
        for proc in children:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
