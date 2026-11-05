"""Verified, direct CDP connections with one reusable socket per app page."""
import hashlib
import json
import logging
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from dataclasses import dataclass

from websockets.sync.client import connect

from core.proxy_checker import redact

logger = logging.getLogger("antigravity_launcher.cdp")
FEATURE_CHECK = """Boolean(document.querySelector(
'[data-testid="conversation-row-sidebar"],[data-testid="sidebar"],[class*="antigravity"],[class*="jetski"],.monaco-workbench'
) || (document.title.includes('Antigravity') && document.querySelector('#root, #app')))"""


@dataclass(frozen=True)
class InjectionStatus:
    cdp_ready: bool = False
    injected_targets: int = 0
    error: str = ""


class CDPInjector:
    def __init__(self, port=58321, overlay_path=None, on_status=None, port_owner=None, target_owner=None):
        self.port = port
        self.port_owner = port_owner or (lambda: False)
        self.target_owner = target_owner or (lambda url: False)
        self.on_status = on_status or (lambda message: None)
        self.overlay_path = Path(overlay_path) if overlay_path else Path(__file__).resolve().parent.parent / "assets/antigravity-hans-overlay.js"
        source = self.overlay_path.read_text(encoding="utf-8")
        self.fingerprint = hashlib.sha256(source.encode()).hexdigest()[:16]
        self.overlay_source = f"window.__antigravityZhPatchRequestedFingerprint = '{self.fingerprint}';\n" + source
        self._connections = {}
        self._registrations = {}
        self._counter = 0
        self._deadline = None
        self._stop = threading.Event()
        self._guard = threading.RLock()
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def fetch_targets(self):
        if not self.port_owner():
            return []
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/list")
        with self._opener.open(request, timeout=1.0) as response:
            data = json.loads(response.read(1024 * 1024))
        if not isinstance(data, list):
            raise ValueError("调试端口返回了无效页面列表")
        return data

    def _call(self, ws, method, params=None):
        if self._stop.is_set():
            raise InterruptedError("CDP monitoring stopped")
        self._counter += 1
        request_id = self._counter
        ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        deadline = time.monotonic() + 2.0
        if self._deadline is not None:
            deadline = min(deadline, self._deadline)
        while not self._stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{method} timed out")
            message = json.loads(ws.recv(timeout=remaining))
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"CDP {method}: {message['error'].get('message', 'failed')}")
            result = message.get("result", {})
            if result.get("exceptionDetails"):
                # Don't log arbitrary page text (may contain conversation content).
                raise RuntimeError(f"{method}: 页面脚本执行异常")
            return result
        raise InterruptedError("CDP monitoring stopped")

    def _evaluate(self, ws, expression):
        result = self._call(ws, "Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return result.get("result", {}).get("value")

    def _valid_target(self, target):
        if not isinstance(target, dict) or target.get("type") not in ("page", "webview", "app"):
            return False
        try:
            ws = urlsplit(target.get("webSocketDebuggerUrl", ""))
            return (ws.scheme == "ws" and ws.hostname in ("127.0.0.1", "localhost", "::1") and
                    ws.port == self.port and not ws.username and not ws.password and
                    ws.path.startswith("/devtools/page/") and
                    bool(target.get("id")) and self.target_owner(target.get("url", "")))
        except (ValueError, OSError):
            return False

    def _drop(self, key):
        with self._guard:
            ws = self._connections.pop(key, None)
            self._registrations.pop(key, None)
        if ws:
            try:
                ws.close()
            except Exception:
                pass

    def scan(self, deadline=None):
        self._deadline = deadline or time.monotonic() + 6.0
        if self._stop.is_set():
            return InjectionStatus(error="汉化监视已停止")
        verified = 0
        ready = False
        errors = []
        try:
            targets = self.fetch_targets()
            ready = bool(targets)
            accepted = [target for target in targets if self._valid_target(target)]
            keys = {t["webSocketDebuggerUrl"] for t in accepted}
            for key in list(self._connections):
                if key not in keys:
                    self._drop(key)
            for target in accepted:
                if self._stop.is_set() or time.monotonic() >= self._deadline:
                    break
                key = target["webSocketDebuggerUrl"]
                try:
                    ws = self._connections.get(key)
                    if ws is None:
                        ws = connect(key, proxy=None, open_timeout=1, close_timeout=0.3, max_size=1024 * 1024)
                        with self._guard:
                            if self._stop.is_set():
                                ws.close()
                                break
                            self._connections[key] = ws
                    if not self._evaluate(ws, FEATURE_CHECK):
                        self._drop(key)
                        continue
                    check = ("window.__antigravityZhPatchInstalled === true && "
                             "window.__observedDocument === document && "
                             f"window.__antigravityZhPatchFingerprint === '{self.fingerprint}'")
                    if self._evaluate(ws, check) is True:
                        verified += 1
                        continue
                    if key not in self._registrations:
                        self._call(ws, "Page.enable")
                        result = self._call(ws, "Page.addScriptToEvaluateOnNewDocument", {
                            "source": f"if ({FEATURE_CHECK}) {{\n{self.overlay_source}\n}}"})
                        self._registrations[key] = result.get("identifier")
                    # Avoid restarting an initial asynchronous scan on each inspection.
                    pending = self._evaluate(ws, f"window.__antigravityZhPatchInitializing === '{self.fingerprint}'")
                    if pending is not True:
                        self._evaluate(ws, self.overlay_source)
                    if self._evaluate(ws, check) is True:
                        verified += 1
                        self.on_status(f"汉化初始化完成: {target['id'][:12]}")
                except Exception as exc:
                    errors.append(redact(exc))
                    self._drop(key)
            if not accepted and ready:
                errors.append("等待可确认身份的应用界面")
        except Exception as exc:
            errors.append(redact(exc))
        message = "; ".join(dict.fromkeys(errors))
        if message:
            logger.debug("CDP inspection: %s", message)
        return InjectionStatus(ready, verified, message)

    def stop_monitoring(self):
        self._stop.set()
        for key in list(self._connections):
            self._drop(key)
