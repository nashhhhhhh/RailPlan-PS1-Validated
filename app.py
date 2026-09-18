"""One-command local launcher for the RailPlan dashboard.

This launcher intentionally starts the frontend-only demonstration. PostgreSQL and
Docker are optional and are only required for saved records and server-side history.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser


ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5173


def command(name: str) -> str | None:
    """Resolve a command, including Windows command shims."""
    return shutil.which(name) or (shutil.which(f"{name}.cmd") if os.name == "nt" else None)


def run_checked(args: list[str]) -> None:
    printable = " ".join(args)
    print(f"\n> {printable}", flush=True)
    try:
        subprocess.run(args, cwd=ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Command failed with exit code {exc.returncode}: {printable}") from exc


def ensure_dependencies(corepack: str) -> None:
    if (ROOT / "node_modules" / "vinext").is_dir():
        return
    print("RailPlan packages are not installed yet; installing them now.", flush=True)
    print("This one-time step needs an internet connection.", flush=True)
    run_checked([corepack, "pnpm", "install", "--frozen-lockfile"])


def port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def open_when_ready(url: str, process: subprocess.Popen[bytes], should_open: bool) -> None:
    for _ in range(120):
        if process.poll() is not None:
            return
        try:
            with urllib.request.urlopen(url, timeout=1):
                if should_open:
                    webbrowser.open(url)
                return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)


def stop_server(process: subprocess.Popen[bytes]) -> None:
    """Stop the development server and any worker processes it created."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the local RailPlan dashboard without Docker.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Address to bind (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to use (default: 5173).")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically.")
    parser.add_argument("--install", action="store_true", help="Refresh packages before starting.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")

    node = command("node")
    corepack = command("corepack")
    if not node:
        raise SystemExit("Node.js 22.13 or newer is required. Install it from https://nodejs.org/ and retry.")
    if not corepack:
        raise SystemExit("Corepack was not found. Reinstall a current Node.js release and retry.")

    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    version_parts = version.removeprefix("v").split(".")
    try:
        node_version = tuple(int(part) for part in version_parts[:2])
    except ValueError:
        node_version = (0, 0)
    if node_version < (22, 13):
        raise SystemExit(f"Node.js 22.13 or newer is required; found {version}.")

    if args.install:
        run_checked([corepack, "pnpm", "install", "--frozen-lockfile"])
    else:
        ensure_dependencies(corepack)

    if not port_available(args.host, args.port):
        raise SystemExit(f"Port {args.port} is already in use. Try: python app.py --port 5174")

    # The source bundle may be replaced by a newer dashboard release. A stale
    # Next development cache can then leave an already-open browser requesting
    # chunk names that no longer exist after a hard refresh.
    shutil.rmtree(ROOT / ".next" / "dev", ignore_errors=True)

    url = f"http://{args.host}:{args.port}"
    print("\nStarting RailPlan (local demonstration mode)", flush=True)
    print(f"Dashboard: {url}", flush=True)
    print("Press Ctrl+C to stop it. Docker is not required.\n", flush=True)

    environment = os.environ.copy()
    environment.pop("NODE_ENV", None)
    environment["NEXT_TELEMETRY_DISABLED"] = "1"
    next_cli = ROOT / "node_modules" / "next" / "dist" / "bin" / "next"
    process = subprocess.Popen(
        [node, str(next_cli), "dev", "--hostname", args.host, "--port", str(args.port)],
        cwd=ROOT,
        env=environment,
    )
    opener = threading.Thread(
        target=open_when_ready,
        args=(url, process, not args.no_browser),
        daemon=True,
    )
    opener.start()

    try:
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping RailPlan...", flush=True)
        stop_server(process)
        return 0


if __name__ == "__main__":
    sys.exit(main())
