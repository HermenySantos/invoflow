"""Saving a deleted receipt twice at once does not hang the API, on Postgres 16 (GIL-207 B-1).

Postgres only. A real single-worker uvicorn serves the API, as in production.
An e-Fatura row is deleted, then each round sends three concurrent PATCHes
with a matched field (invoice number, NIF) to the deleted row, three to a live
row, and polls /health. Every deleted-row PATCH must be a prompt 404, every
live-row PATCH a 200, and /health must stay 200. A PATCH that takes the
account lock and leaves on a 404 without ending its transaction blocks the
next one; if that wait runs on the event loop, the whole server hangs.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_edited_at_rows as base  # noqa: E402

ROUNDS = 5
TIMEOUT = 8.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(url: str, port: int) -> subprocess.Popen:
    env = dict(
        os.environ,
        DATABASE_URL=url,
        AUTH_MOCK_MODE="true",
        MOCK_AUTH="1",
        STORAGE_MOCK_MODE="true",
        OCR_MOCK_MODE="true",
        APP_DEBUG="true",
        APP_ENV="development",
    )
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=base.BACKEND,
        env=env,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                return server
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    server.kill()
    raise SystemExit("uvicorn did not start")


def _timed(call):
    started = time.monotonic()
    try:
        return call().status_code, time.monotonic() - started
    except httpx.TimeoutException:
        return "timeout", time.monotonic() - started


def main() -> None:
    name = f"lock404_{uuid.uuid4().hex[:8]}"
    url = base._recreate(name)
    server = None
    try:
        os.environ["DATABASE_URL"] = url
        sys.path.insert(0, str(base.BACKEND))
        base._migrate(url)
        port = _free_port()
        server = _start_server(url, port)
        api = f"http://127.0.0.1:{port}"
        account = base.Account(url, httpx.Client(base_url=api, timeout=TIMEOUT))
        client = httpx.Client(base_url=api, headers=account.headers, timeout=TIMEOUT)
        deleted_id = account.pull(base._invoice("FT A/1", "2.30")).created[0]
        live_id = account.pull(base._invoice("FT A/2", "4.60")).created[0]
        removed = client.delete(f"/api/documents/{deleted_id}")
        assert removed.status_code == 204, removed.text

        matched = {"invoice_number": "FT A/1", "vendor_nif": base.NIF}
        live = {"invoice_number": "FT A/2", "vendor_nif": base.NIF}
        failures = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            for round_no in range(1, ROUNDS + 1):
                gone = [
                    pool.submit(_timed, lambda: client.patch(f"/api/documents/{deleted_id}", json=matched))
                    for _ in range(3)
                ]
                kept = [
                    pool.submit(_timed, lambda: client.patch(f"/api/documents/{live_id}", json=live))
                    for _ in range(3)
                ]
                time.sleep(0.5)
                health = _timed(lambda: httpx.get(f"{api}/health", timeout=TIMEOUT))
                results = {
                    "deleted": [f.result() for f in gone],
                    "live": [f.result() for f in kept],
                    "health": [health],
                }
                expected = {"deleted": 404, "live": 200, "health": 200}
                for kind, outcomes in results.items():
                    for status, seconds in outcomes:
                        if status != expected[kind] or seconds > TIMEOUT / 2:
                            failures.append(f"round {round_no} {kind}: {status} after {seconds:.2f}s")
                slowest = max(seconds for outcomes in results.values() for _, seconds in outcomes)
                print(f"round {round_no}: {results} slowest {slowest:.2f}s")
                if failures:
                    break
        assert not failures, failures
        print("Saving a deleted receipt twice at once passed")
    finally:
        if server is not None:
            # A hung server ignores SIGTERM while it waits on its requests.
            server.send_signal(signal.SIGKILL)
            server.wait()
        from app.core.database import engine

        engine.dispose()
        base._drop(name)


if __name__ == "__main__":
    main()
