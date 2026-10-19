"""Regression: a connected dashboard must not block server shutdown (real uvicorn process)."""
import asyncio
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

BACKEND = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_sigterm_with_connected_websocket_exits_promptly(tmp_path):
    port = free_port()
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "OMNI_DATABASE_URL": f"sqlite:///{tmp_path/'s.db'}",
           "OMNI_MEDIA_DIR": str(tmp_path / "media")}
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=BACKEND,
                         env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.25)

        async def go() -> float:
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
                await ws.recv()
                t = time.time()
                p.terminate()
                await asyncio.get_running_loop().run_in_executor(None, lambda: p.wait(timeout=10))
                return time.time() - t

        assert asyncio.run(go()) < 10
    finally:
        if p.poll() is None:
            p.kill()
