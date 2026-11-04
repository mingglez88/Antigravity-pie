"""CDP (Chrome DevTools Protocol) dynamic injector for Antigravity localization.

This module replicates the functionality of yuexps/Antigravity-Hans purely in Python:
1. Connects to Antigravity's remote debugging port (default: 58321).
2. Discovers targets via http://127.0.0.1:<port>/json/list.
3. Injects assets/antigravity-hans-overlay.js dynamically via WebSocket using CDP commands:
   - Page.enable
   - Page.addScriptToEvaluateOnNewDocument (ensures refreshed & new pages are translated)
   - Runtime.evaluate (immediately translates currently opened document)
"""

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

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
        self.injected_target_ids: Set[str] = set()

        if overlay_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            self.overlay_path = base_dir / "assets" / "antigravity-hans-overlay.js"
        else:
            self.overlay_path = Path(overlay_path)

        self.overlay_source = self._load_overlay_source()
        self.fingerprint = hashlib.sha256(self.overlay_source.encode("utf-8")).hexdigest()[:16]

    def _load_overlay_source(self) -> str:
        """Read translation script from assets."""
        if not self.overlay_path.exists():
            raise FileNotFoundError(f"Overlay script not found: {self.overlay_path}")
        with open(self.overlay_path, "r", encoding="utf-8") as f:
            return f.read()

    def _log(self, message: str) -> None:
        logger.info(message)
        self.on_status(message)

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

    def inject_target(self, target: Dict[str, Any]) -> bool:
        """Inject overlay into a single target via WebSocket."""
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
            with ws_connect(ws_url, open_timeout=2.0, close_timeout=1.0) as ws:
                # 1. Page.enable
                ws.send(json.dumps({"id": 1, "method": "Page.enable", "params": {}}))
                resp1 = json.loads(ws.recv(timeout=2.0))

                # 2. Page.addScriptToEvaluateOnNewDocument (for page navigation/reload)
                ws.send(
                    json.dumps(
                        {
                            "id": 2,
                            "method": "Page.addScriptToEvaluateOnNewDocument",
                            "params": {"source": self.overlay_source},
                        }
                    )
                )
                resp2 = json.loads(ws.recv(timeout=2.0))

                # 3. Runtime.evaluate (immediate execution on existing DOM)
                ws.send(
                    json.dumps(
                        {
                            "id": 3,
                            "method": "Runtime.evaluate",
                            "params": {
                                "expression": self.overlay_source,
                                "awaitPromise": False,
                                "returnByValue": True,
                            },
                        }
                    )
                )
                resp3 = json.loads(ws.recv(timeout=3.0))

                self.injected_target_ids.add(target_id)
                self._log(f"[CDP] 成功汉化页面: {title or target_id} ({target_type})")
                return True
        except Exception as e:
            # Silent on transient socket disconnects during navigation
            logger.debug(f"Target injection failed: {e}")
            return False

    def start_monitoring(self) -> None:
        """Start the background monitor loop to keep injecting targets as they appear."""
        if self.running:
            return
        self.running = True
        self.injected_target_ids.clear()
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
        """Polling loop for CDP targets."""
        retry_count = 0
        while self.running:
            targets = self.fetch_targets()
            if not targets:
                retry_count += 1
                time.sleep(0.8)
                continue

            retry_count = 0
            for t in targets:
                t_id = t.get("id", "")
                if t_id and t_id not in self.injected_target_ids:
                    self.inject_target(t)

            time.sleep(1.0)
