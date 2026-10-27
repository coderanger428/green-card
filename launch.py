"""Single launcher for scraper + dashboard.

Commands:
  run    (default)  scraper + dashboard; UI at :8007
  watch             live reload (Vite :5173 + uvicorn --reload)
  stop              stop a previous launch from this project
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from scrapers import PLATFORMS

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
DIST_INDEX = FRONTEND / "dist" / "index.html"
PID_FILE = ROOT / "launch.pids"
REQUIREMENTS = ROOT / "requirements.txt"
BACKFILL_SCRIPT = ROOT / "backfill_locations.py"
DASHBOARD_PORT = 8007
VITE_PORT = 5173
IS_WIN = sys.platform == "win32"


def _print(msg: str) -> None:
    print(msg, flush=True)


def npm_bin() -> str:
    found = shutil.which("npm.cmd" if IS_WIN else "npm") or shutil.which("npm")
    if not found:
        sys.exit("npm not found. Install Node.js 18+.")
    return found


def pip_install() -> None:
    _print("Ensuring Python dependencies (requirements.txt)...")
    code = subprocess.call(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=ROOT,
    )
    if code != 0:
        sys.exit(f"pip install failed (exit {code}).")


def npm_install() -> None:
    _print("Installing frontend dependencies...")
    code = subprocess.call([npm_bin(), "install"], cwd=FRONTEND)
    if code != 0:
        sys.exit(f"npm install failed (exit {code}).")


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def dist_is_stale() -> bool:
    if not DIST_INDEX.is_file():
        return True
    dist_mtime = _mtime(DIST_INDEX)
    watch = [
        FRONTEND / "index.html",
        FRONTEND / "package.json",
        FRONTEND / "package-lock.json",
        FRONTEND / "vite.config.js",
        FRONTEND / "src",
    ]
    for root in watch:
        if root.is_file() and _mtime(root) > dist_mtime:
            return True
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and _mtime(path) > dist_mtime:
                    return True
    return False


def build_frontend() -> None:
    npm_install()
    _print("Building frontend (frontend/dist)...")
    code = subprocess.call([npm_bin(), "run", "build"], cwd=FRONTEND)
    if code != 0:
        sys.exit(f"Frontend build failed (exit {code}).")
    if not DIST_INDEX.is_file():
        sys.exit(f"Frontend build failed: {DIST_INDEX} still missing.")
    _print(f"Frontend build OK: {DIST_INDEX.parent}")


def listening_pids(port: int) -> set[int]:
    pids: set[int] = set()
    if IS_WIN:
        try:
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"],
                text=True,
                errors="replace",
            )
        except (OSError, subprocess.CalledProcessError):
            return pids
        needle = f":{port}"
        for line in out.splitlines():
            if "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if len(parts) < 5 or needle not in parts[1]:
                continue
            try:
                pids.add(int(parts[-1]))
            except ValueError:
                pass
        return pids

    if shutil.which("lsof"):
        try:
            out = subprocess.check_output(
                ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                text=True,
                errors="replace",
                stderr=subprocess.DEVNULL,
            )
            for tok in out.split():
                try:
                    pids.add(int(tok))
                except ValueError:
                    pass
        except subprocess.CalledProcessError:
            pass
        return pids

    if shutil.which("fuser"):
        try:
            out = subprocess.check_output(
                ["fuser", f"{port}/tcp"],
                text=True,
                errors="replace",
                stderr=subprocess.STDOUT,
            )
            for tok in out.replace(":", " ").split():
                try:
                    pids.add(int(tok))
                except ValueError:
                    pass
        except subprocess.CalledProcessError:
            pass
    return pids


def kill_pid(pid: int) -> None:
    if pid <= 0 or pid == os.getpid():
        return
    if IS_WIN:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _normalize_cmd(text: str) -> str:
    return text.replace("\\", "/").lower()


def _list_processes() -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    try:
        if IS_WIN:
            ps = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { $_.CommandLine } | "
                    "ForEach-Object { '{0}`t{1}' -f $_.ProcessId, $_.CommandLine }",
                ],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
            )
            for line in ps.stdout.splitlines():
                pid_s, sep, cmdline = line.partition("\t")
                if not sep:
                    continue
                try:
                    rows.append((int(pid_s), cmdline))
                except ValueError:
                    pass
        else:
            ps = subprocess.run(
                ["ps", "-eo", "pid=,args="],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=10,
            )
            for line in ps.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                pid_s, _, cmdline = line.partition(" ")
                try:
                    rows.append((int(pid_s), cmdline.strip()))
                except ValueError:
                    pass
    except (OSError, subprocess.TimeoutExpired):
        return rows
    return rows


def kill_stray_project_processes() -> None:
    """Kill leftover scraper/dashboard/vite from this repo (old launchers too)."""
    root_key = _normalize_cmd(str(ROOT))
    main_py = _normalize_cmd(str(ROOT / "main.py"))
    venv_key = _normalize_cmd(str(ROOT / ".venv"))
    me = os.getpid()
    for pid, cmdline in _list_processes():
        if pid == me:
            continue
        cmd = _normalize_cmd(cmdline)
        from_this_venv = venv_key in cmd
        is_scraper = (
            ("main.py" in cmd and (main_py in cmd or from_this_venv))
            or any(
                f"scrapers.{name}" in cmd or f"scrapers/{name}" in cmd
                for name in PLATFORMS
            )
        )
        if is_scraper:
            kill_pid(pid)
            continue
        if "uvicorn" in cmd and "dashboard:app" in cmd and (
            root_key in cmd or from_this_venv
        ):
            kill_pid(pid)
            continue
        if "vite" in cmd and _normalize_cmd(str(FRONTEND)) in cmd:
            kill_pid(pid)
            continue
        if "backfill_locations.py" in cmd and (root_key in cmd or from_this_venv):
            kill_pid(pid)


def read_pid_file() -> dict[str, int]:
    if not PID_FILE.is_file():
        return {}
    try:
        data = json.loads(PID_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, int] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            try:
                out[str(key)] = int(value)
            except (TypeError, ValueError):
                pass
    return out


def write_pid_file(pids: dict[str, int]) -> None:
    PID_FILE.write_text(json.dumps(pids, indent=2), encoding="utf-8")


def stop_previous() -> None:
    recorded = read_pid_file()
    for pid in recorded.values():
        kill_pid(pid)
    for port in (DASHBOARD_PORT, VITE_PORT):
        for pid in listening_pids(port):
            kill_pid(pid)
    kill_stray_project_processes()
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except OSError:
            pass
    # Let sockets release.
    deadline = time.time() + 5
    while time.time() < deadline:
        if not listening_pids(DASHBOARD_PORT) and not listening_pids(VITE_PORT):
            break
        time.sleep(0.2)


def stop_backfill(proc: subprocess.Popen | None) -> None:
    if proc is not None and proc.poll() is None:
        kill_pid(proc.pid)


def start_backfill() -> subprocess.Popen | None:
    """Resume the one-off location backfill while its script is still on disk.

    The script deletes itself after the last row, so later launches do nothing.
    It is not part of the wait set: finishing the backfill must not stop the app.
    On Windows it gets its own console so the progress line stays intact.
    """
    if not BACKFILL_SCRIPT.is_file():
        return None
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    argv = [sys.executable, "-u", str(BACKFILL_SCRIPT)]
    kwargs: dict = {"cwd": str(ROOT), "env": env}
    if IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        _print("Resuming location backfill in its own window.")
    else:
        _print("Resuming location backfill.")
    _print(f"Starting backfill: {' '.join(argv)}")
    return subprocess.Popen(argv, **kwargs)


def spawn(title: str, argv: list[str], cwd: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    _print(f"Starting {title}: {' '.join(argv)}")
    return subprocess.Popen(argv, cwd=str(cwd), env=env)


def wait_port(port: int, timeout: float = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if listening_pids(port):
            return True
        time.sleep(0.2)
    return False


def wait_on(procs: list[tuple[str, subprocess.Popen]]) -> int:
    try:
        while True:
            for title, proc in procs:
                code = proc.poll()
                if code is not None:
                    _print(f"{title} exited (code {code}).")
                    return code or 1
            time.sleep(0.4)
    except KeyboardInterrupt:
        _print("\nStopping...")
        return 0


def terminate_children(procs: list[tuple[str, subprocess.Popen]]) -> None:
    for _, proc in procs:
        if proc.poll() is None:
            kill_pid(proc.pid)
    for _, proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            kill_pid(proc.pid)


def cmd_stop() -> int:
    _print("Stopping scraper / dashboard / Vite from this project...")
    stop_previous()
    _print("Stopped.")
    return 0


def cmd_run(watch: bool) -> int:
    os.chdir(ROOT)
    pip_install()
    _print("Restarting any previous instance...")
    stop_previous()

    if watch:
        npm_install()
    elif dist_is_stale():
        _print("Frontend build missing or stale — rebuilding.")
        build_frontend()
    else:
        _print(f"Frontend build OK: {DIST_INDEX.parent}")

    scrapers = [
        (name, spawn(name, [sys.executable, "-m", f"scrapers.{name}"], ROOT))
        for name in PLATFORMS
    ]
    dashboard_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "server.dashboard:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(DASHBOARD_PORT),
    ]
    if watch:
        dashboard_cmd.append("--reload")
    dashboard = spawn("dashboard", dashboard_cmd, ROOT)

    procs: list[tuple[str, subprocess.Popen]] = [
        *scrapers,
        ("dashboard", dashboard),
    ]
    pids = {title: proc.pid for title, proc in procs}

    if watch:
        vite = spawn("vite", [npm_bin(), "run", "dev"], FRONTEND)
        procs.append(("vite", vite))
        pids["vite"] = vite.pid

    backfill = start_backfill()
    if backfill is not None:
        pids["backfill"] = backfill.pid

    write_pid_file(pids)

    if not wait_port(DASHBOARD_PORT):
        _print(f"Dashboard did not bind :{DASHBOARD_PORT} in time.")
        stop_backfill(backfill)
        terminate_children(procs)
        return 1
    if watch and not wait_port(VITE_PORT):
        _print(f"Vite did not bind :{VITE_PORT} in time.")
        stop_backfill(backfill)
        terminate_children(procs)
        return 1

    _print("")
    _print("=" * 52)
    if watch:
        _print("  Watch mode (live reload)")
        _print(f"  UI:  http://127.0.0.1:{VITE_PORT}")
        _print(f"  API: http://127.0.0.1:{DASHBOARD_PORT}")
    else:
        _print("  Scraper + dashboard")
        _print(f"  Open http://127.0.0.1:{DASHBOARD_PORT}")
    if backfill is not None:
        _print("  Location backfill: separate window")
    _print("  Stop: Ctrl+C   or   stop.bat / ./stop.sh")
    _print("=" * 52)
    _print("")

    try:
        return wait_on(procs)
    finally:
        stop_backfill(backfill)
        terminate_children(procs)
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start the Dev.to scraper and mail dashboard."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=("run", "watch", "stop"),
        help="run = daily use (default); watch = UI live reload; stop = shut down",
    )
    args = parser.parse_args(argv)
    if args.command == "stop":
        return cmd_stop()
    return cmd_run(watch=args.command == "watch")


if __name__ == "__main__":
    sys.exit(main())
