"""Windows application identity, graceful close and local endpoint ownership."""
import ctypes
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psutil


def canonical(path):
    return os.path.normcase(os.path.realpath(path))


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    created: float
    path: str


class ProcessBackend:
    def __init__(self):
        self._listeners = {}
        self._children = []

    def find(self, app_path):
        found = []
        for proc in psutil.process_iter(["pid", "exe", "create_time", "cmdline"]):
            try:
                if proc.info["exe"] and canonical(proc.info["exe"]) == canonical(app_path):
                    if not any(arg.startswith("--type=") for arg in (proc.info["cmdline"] or [])):
                        found.append(ProcessIdentity(proc.pid, proc.info["create_time"], app_path))
            except (psutil.Error, OSError):
                continue
        return sorted(found, key=lambda item: item.created)

    def alive(self, identity):
        if identity is None:
            return False
        try:
            process = psutil.Process(identity.pid)
            return process.is_running() and process.create_time() == identity.created and canonical(process.exe()) == canonical(identity.path)
        except (psutil.Error, OSError):
            return False

    def spawn(self, settings, env):
        args = [settings.app_path]
        if settings.enable_hans:
            args += [f"--remote-debugging-port={settings.debugging_port}", "--remote-debugging-address=127.0.0.1"]
        process = subprocess.Popen(args, cwd=str(Path(settings.app_path).parent), env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._children = [child for child in self._children if child.poll() is None]
        self._children.append(process)
        try:
            return ProcessIdentity(process.pid, psutil.Process(process.pid).create_time(), settings.app_path)
        except psutil.NoSuchProcess:
            return None

    def close(self, identities, timeout=10.0):
        if not identities:
            return True
        if os.name != "nt":
            raise RuntimeError("正常关闭应用仅支持 Windows")
        pids = {item.pid for item in identities if self.alive(item)}
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_ssize_t)
        user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        user32.EnumWindows.argtypes = [callback_type, ctypes.c_ssize_t]
        user32.EnumWindows.restype = ctypes.c_bool
        @callback_type
        def close_window(hwnd, _):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE, never TerminateProcess.
            return True
        user32.EnumWindows(close_window, 0)
        deadline = time.monotonic() + timeout
        while any(self.alive(item) for item in identities):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)
        return True

    def refresh_connections(self):
        listeners = {}
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == psutil.CONN_LISTEN:
                listeners.setdefault(conn.laddr.port, set()).add(conn.pid)
        self._listeners = listeners

    def listener(self, port):
        owners = self._listeners.get(port, set())
        return next(iter(owners)) if len(owners) == 1 else (-1 if owners else None)

    def owns_debug_port(self, identity, port):
        return self.alive(identity) and self.listener(port) == identity.pid

    def owns_page(self, identity, url):
        if not self.alive(identity):
            return False
        try:
            parsed = urlsplit(url)
            if parsed.scheme in ("file", "vscode-file"):
                path = canonical(unquote(parsed.path).lstrip("/"))
                root = canonical(Path(identity.path).parent)
                return os.path.commonpath([root, path]) == root and path.endswith(("workbench.html", "index.html"))
            if parsed.scheme not in ("http", "https") or parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                return False
            pid = self.listener(parsed.port or (443 if parsed.scheme == "https" else 80))
            if not pid:
                return False
            process = psutil.Process(pid)
            expected = canonical(Path(identity.path).parent / "resources" / "bin" / "language_server.exe")
            return canonical(process.exe()) == expected and any(p.pid == identity.pid and p.create_time() == identity.created for p in process.parents())
        except (ValueError, OSError, psutil.Error):
            return False
