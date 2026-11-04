"""CDP (Chrome DevTools Protocol) dynamic injector for Antigravity localization.

Replicates the robust injection & inspection logic of yuexps/Antigravity-Hans in pure Python:
1. Regularly polls Antigravity's remote debugging port (default: 58321).
2. For every active page / webview target, checks if `window.__antigravityZhPatchInstalled`
   and `window.__observedDocument === document` are present.
3. Automatically injects on startup, document reload, URL navigation, and new sub-views.
4. Robust CDP message routing that correctly filters asynchronous notifications.
"""

import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from websockets.sync.client import connect as ws_connect
    HAS_WEBSOCKETS_LIB = True
except ImportError:
    HAS_WEBSOCKETS_LIB = False

logger = logging.getLogger("CDPInjector")


class CDPInjector:
    """Monitors running Antigravity Electron process and injects translation overlay."""

    def __init__(
        self,
        port: int = 58321,
        overlay_path: Optional[str] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ):
        self.port = port
        self.on_status = on_status or (lambda msg: None)
        self.running = False
        self.worker_thread: Optional[threading.Thread] = None
        self._msg_counter = 0
        self._counter_lock = threading.Lock()

        if overlay_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            self.overlay_path = base_dir / "assets" / "antigravity-hans-overlay.js"
        else:
            self.overlay_path = Path(overlay_path)

        self.raw_overlay = self._load_overlay_source()
        self.fingerprint = hashlib.sha256(self.raw_overlay.encode("utf-8")).hexdigest()[:16]
        self.overlay_source = (
            f"window.__antigravityZhPatchRequestedFingerprint = '{self.fingerprint}';\n"
            + self.raw_overlay
        )

    def _next_id(self) -> int:
        with self._counter_lock:
            self._msg_counter += 1
            return self._msg_counter

    def _load_overlay_source(self) -> str:
        """Read translation script from assets."""
        if not self.overlay_path.exists():
            raise FileNotFoundError(f"Overlay script not found: {self.overlay_path}")
        with open(self.overlay_path, "r", encoding="utf-8") as f:
            return f.read()

    def _log(self, message: str) -> None:
        logger.info(message)
        self.on_status(message)

    def _cdp_call(self, ws, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 4.0) -> Dict[str, Any]:
        """Send a CDP command and wait for the response matching the request id."""
        req_id = self._next_id()
        payload = {"id": req_id, "method": method, "params": params or {}}
        ws.send(json.dumps(payload))
        deadline = time.time() + timeout

        while time.time() < deadline:
            raw = ws.recv(timeout=max(0.1, deadline - time.time()))
            msg = json.loads(raw)
            if msg.get("id") == req_id:
                if "error" in msg:
                    err_info = msg["error"]
                    err_msg = err_info.get("message", str(err_info)) if isinstance(err_info, dict) else str(err_info)
                    raise RuntimeError(f"CDP error in {method}: {err_msg}")
                return msg
        raise TimeoutError(f"CDP call timeout for {method} (id={req_id})")

    def fetch_targets(self) -> List[Dict[str, Any]]:
        """Query http://127.0.0.1:<port>/json/list for debuggable targets."""
        url = f"http://127.0.0.1:{self.port}/json/list"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AntigravityLauncher/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except Exception:
            return []

    def is_target_injected(self, ws_url: str) -> bool:
        """Check if target's current document has the overlay installed."""
        try:
            with ws_connect(ws_url, open_timeout=2.0, close_timeout=1.0) as ws:
                check_expr = (
                    f"window.__antigravityZhPatchInstalled === true && "
                    f"window.__observedDocument === document && "
                    f"window.__antigravityZhPatchFingerprint === '{self.fingerprint}'"
                )
                resp = self._cdp_call(ws, "Runtime.evaluate", {"expression": check_expr, "returnByValue": True}, timeout=2.0)
                return bool(resp.get("result", {}).get("result", {}).get("value") is True)
        except Exception:
            return False

    def inject_target(self, target: Dict[str, Any]) -> bool:
        """Inject overlay into a single target via WebSocket with document verification."""
        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            return False

        target_id = target.get("id", "")
        title = target.get("title", "")
        target_type = target.get("type", "")

        # Only inject page and webview types
        if target_type not in ("page", "webview", "app", ""):
            return False

        if not HAS_WEBSOCKETS_LIB:
            self._log("[CDP] 缺少 websockets 库，无法注入")
            return False

        try:
            with ws_connect(ws_url, open_timeout=3.0, close_timeout=1.5) as ws:
                # 1. Quick check on connection
                check_expr = (
                    f"window.__antigravityZhPatchInstalled === true && "
                    f"window.__observedDocument === document && "
                    f"window.__antigravityZhPatchFingerprint === '{self.fingerprint}'"
                )
                resp = self._cdp_call(ws, "Runtime.evaluate", {"expression": check_expr, "returnByValue": True}, timeout=2.0)
                if resp.get("result", {}).get("result", {}).get("value") is True:
                    return True

                # 2. Page.enable
                try:
                    self._cdp_call(ws, "Page.enable", {}, timeout=2.0)
                except Exception:
                    pass

                # 3. Page.addScriptToEvaluateOnNewDocument (for future navigation & reload)
                try:
                    self._cdp_call(
                        ws,
                        "Page.addScriptToEvaluateOnNewDocument",
                        {"source": self.overlay_source},
                        timeout=3.0,
                    )
                except Exception as e:
                    logger.debug(f"addScriptToEvaluateOnNewDocument: {e}")

                # 4. Runtime.evaluate (immediate execution on existing DOM)
                self._cdp_call(
                    ws,
                    "Runtime.evaluate",
                    {
                        "expression": self.overlay_source,
                        "awaitPromise": False,
                        "returnByValue": True,
                    },
                    timeout=4.0,
                )

                # 5. Verify installation
                verify_resp = self._cdp_call(
                    ws,
                    "Runtime.evaluate",
                    {"expression": check_expr, "returnByValue": True},
                    timeout=2.0,
                )
                verified = bool(verify_resp.get("result", {}).get("result", {}).get("value") is True)
                if verified:
                    clean_title = (title[:30] if title else target_id[:8])
                    self._log(f"[CDP] 成功汉化页面: {clean_title} ({target_type})")
                    return True
                return False
        except Exception as e:
            logger.debug(f"Target injection error for {target_id}: {e}")
            return False

    def start_monitoring(self) -> None:
        """Start the background monitor loop to keep injecting targets as they appear."""
        if self.running:
            return
        self.running = True
        self.worker_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.worker_thread.start()
        self._log(f"[CDP] 汉化监视服务已启动，正在监听调试端口 {self.port}...")

    def stop_monitoring(self) -> None:
        """Stop background monitor loop."""
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
        self._log("[CDP] 汉化监视服务已停止")

    def _monitor_loop(self) -> None:
        """Polling loop for CDP targets with continuous health inspection."""
        consecutive_empty = 0
        while self.running:
            try:
                targets = self.fetch_targets()
                if not targets:
                    consecutive_empty += 1
                    time.sleep(1.0)
                    continue

                consecutive_empty = 0
                for t in targets:
                    if not self.running:
                        break
                    t_type = t.get("type", "")
                    if t_type not in ("page", "webview", "app", ""):
                        continue
                    ws_url = t.get("webSocketDebuggerUrl")
                    if not ws_url:
                        continue

                    # If not injected or page was reloaded / navigated, inject it!
                    if not self.is_target_injected(ws_url):
                        self.inject_target(t)

                time.sleep(1.2)
            except Exception as e:
                logger.debug(f"Monitor loop error: {e}")
                time.sleep(1.5)
