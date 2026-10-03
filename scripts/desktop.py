#!/usr/bin/env python3
"""Install a local shortcut or launch the server. No external network traffic."""
import argparse
import json
import os
from pathlib import Path
import signal
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import webbrowser

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "src"))
from dots_panel.app import Store
from dots_panel.desktop_view import ReadOnlyStore


def private_file(path, mode):
    if path.is_symlink():
        raise ValueError("Runtime file must not be a symlink")
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_APPEND if "a" in mode else 0
    fd = os.open(path, flags, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        os.close(fd)
        raise ValueError("Existing runtime file is not private; owner review required")
    if "w" in mode:
        os.ftruncate(fd, 0)
    return os.fdopen(fd, mode)


def health(port):
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f"http://127.0.0.1:{port}/health", timeout=1) as response:
            return json.load(response) == {"status": "ok"}
    except (OSError, ValueError):
        return False


def native_python(explicit=None):
    """Prefer the distribution Tk runtime when available, without installing anything."""
    candidates = [explicit] if explicit else ["/usr/bin/python3", sys.executable]
    for candidate in candidates:
        resolved = shutil.which(candidate) if candidate else None
        if not resolved:
            continue
        try:
            probe = subprocess.run([resolved, "-c", "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
            if probe.returncode == 0:
                return resolved
        except (OSError, subprocess.TimeoutExpired):
            continue
    raise SystemExit("No compatible Python 3.10+ with Tkinter found; specify --python with a verified interpreter")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "open", "start", "stop", "health"))
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--web", action="store_true", help="Use the web browser instead of the default local native viewer")
    parser.add_argument("--python", dest="native_interpreter", help="Explicit Python 3.10+ interpreter for the native desktop viewer")
    args = parser.parse_args()
    if args.action == "health":
        print("healthy" if health(args.port) else "offline")
        return
    store = Store(args.data_dir) if args.action == "install" else ReadOnlyStore(args.data_dir)
    if args.action != "install":
        store.snapshot()  # Validate the complete existing schema before logs or execution.
    pidfile = store.directory / "run/server.json"
    command = [sys.executable, "-m", "dots_panel", "--data-dir", str(store.directory), "serve", "--port", str(args.port)]
    if args.action == "install":
        applications = Path.home() / ".local/share/applications"
        applications.mkdir(parents=True, exist_ok=True)
        def desktop_quote(value):
            return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
        interpreter = native_python(args.native_interpreter)
        launch = [interpreter, str(SOURCE / "scripts/desktop.py"), "open", "--data-dir", str(store.directory), "--port", str(args.port), "--python", interpreter]
        content = "[Desktop Entry]\nType=Application\nName=dots panel\nComment=Private local machine and task panel\nExec=" + " ".join(desktop_quote(x) for x in launch) + "\nIcon=" + str(SOURCE / "web/icon.svg") + "\nTerminal=false\nStartupWMClass=Dotspanel\nCategories=Utility;\n"
        target = applications / "dots-panel.desktop"
        target.write_text(content)
        desktop = Path.home() / "Desktop"
        if desktop.is_dir():
            copy = desktop / "dots-panel.desktop"
            copy.write_text(content)
            copy.chmod(0o755)
        print("Installed application shortcut; desktop copy added when Desktop directory exists")
        return
    if args.action == "open" and not args.web:
        env = dict(os.environ, PYTHONPATH=str(SOURCE / "src"))
        interpreter = native_python(args.native_interpreter)
        with private_file(store.directory / "logs/desktop.log", "ab") as log:
            os.dup2(log.fileno(), 1)
            os.dup2(log.fileno(), 2)
        os.execvpe(interpreter, [interpreter, "-m", "dots_panel.desktop_view", "--data-dir", str(store.directory)], env)
    if args.action == "health":
        print("healthy" if health(args.port) else "offline")
        return
    if args.action == "stop":
        if not pidfile.exists():
            print("No managed process recorded")
            return
        saved = json.loads(pidfile.read_text())
        pid = int(saved["pid"])
        actual = Path(f"/proc/{pid}/cmdline")
        if not actual.exists():
            print("Recorded process already stopped")
            return
        if actual.read_bytes().decode().split('\0')[:-1] != command:
            raise SystemExit("Process identity differs; refusing to stop another process")
        os.kill(pid, signal.SIGTERM)
        print("Stop requested; data preserved")
        return
    alive = health(args.port)
    if alive:
        if not pidfile.exists():
            raise SystemExit("Port already has an unmanaged service; refusing to reuse its data")
        saved = json.loads(pidfile.read_text())
        actual = Path(f"/proc/{int(saved['pid'])}/cmdline")
        if not actual.exists() or actual.read_bytes().decode().split('\0')[:-1] != command:
            raise SystemExit("Port is not owned by this recorded runtime; refusing to reuse it")
    if not alive:
        env = dict(os.environ, PYTHONPATH=str(SOURCE / "src"))
        with private_file(store.directory / "logs/server.log", "ab") as log:
            process = subprocess.Popen(command, env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            for _ in range(30):
                if process.poll() is not None:
                    raise RuntimeError("Server exited; inspect runtime logs/server.log")
                if health(args.port):
                    with private_file(pidfile, "w") as file:
                        json.dump({"pid": process.pid, "port": args.port}, file)
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("Server did not become healthy; inspect runtime logs/server.log")
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise
    print(f"http://127.0.0.1:{args.port}")
    if args.action == "open":
        webbrowser.open(f"http://127.0.0.1:{args.port}")


if __name__ == "__main__":
    main()
