"""Antigravity process launcher with proxy and debugging port injection."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.cdp_injector import CDPInjector
from core.config_manager import ConfigManager


def is_process_running(exe_name: str = "Antigravity.exe") -> bool:
    """Check if Antigravity is already running via tasklist."""
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"],
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return exe_name.lower() in output.lower()
    except Exception:
        return False


def terminate_running_instances(exe_name: str = "Antigravity.exe") -> bool:
    """Gracefully terminate running Antigravity processes."""
    try:
        subprocess.run(
            ["taskkill", "/IM", exe_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True
    except Exception:
        return False


class AntigravityLauncher:
    """Handles launching Antigravity.exe with proxy environment variables and CDP injection."""

    def __init__(self, config_manager: ConfigManager, on_log: Optional[Callable[[str], None]] = None):
        self.config_manager = config_manager
        self.on_log = on_log or (lambda msg: None)
        self.injector: Optional[CDPInjector] = None
        self.process: Optional[subprocess.Popen] = None

    def _log(self, message: str) -> None:
        self.on_log(message)

    def launch(self) -> Tuple[bool, str]:
        """Launch Antigravity based on current configuration."""
        app_path = self.config_manager.get("app_path", "").strip()
        if not app_path or not os.path.exists(app_path):
            return False, f"未找到 Antigravity 应用程序路径:\n{app_path}\n请点击【浏览】选择正确的 Antigravity.exe。"

        # Stop existing injector if any
        if self.injector:
            self.injector.stop_monitoring()
            self.injector = None

        # Build environment variables
        env = dict(os.environ)

        # 1. Clear ELECTRON_RUN_AS_NODE (critical for avoiding node mode exit)
        env.pop("ELECTRON_RUN_AS_NODE", None)

        # 2. Configure Proxy
        enable_proxy = self.config_manager.get("enable_proxy", True)
        current_proxy = self.config_manager.get("current_proxy", "").strip()
        no_proxy = self.config_manager.get("no_proxy", "localhost,127.0.0.1,::1")

        if enable_proxy and current_proxy:
            env["HTTP_PROXY"] = current_proxy
            env["HTTPS_PROXY"] = current_proxy
            env["NO_PROXY"] = no_proxy
            self._log(f"[启动器] 已配置网络代理: {current_proxy}")
            self._log(f"[启动器] 绕过代理地址: {no_proxy}")
        else:
            env.pop("HTTP_PROXY", None)
            env.pop("HTTPS_PROXY", None)
            env.pop("NO_PROXY", None)
            self._log("[启动器] 处于直连模式（未启用网络代理）")

        # 3. Command-line arguments
        args = [app_path]
        enable_hans = self.config_manager.get("enable_hans", True)
        port = int(self.config_manager.get("debugging_port", 58321))

        if enable_hans:
            # Add Chrome remote debugging port for CDP injection
            args.append(f"--remote-debugging-port={port}")
            args.append("--remote-debugging-address=127.0.0.1")
            self._log(f"[启动器] 已开启调试注入端口: {port}（中文汉化模式）")

            # Initialize CDP Injector
            self.injector = CDPInjector(port=port, on_status=self.on_log)
            self.injector.start_monitoring()
        else:
            self._log("[启动器] 原生模式启动（未开启中文汉化）")

        # 4. Spawn child process
        app_dir = os.path.dirname(app_path)
        try:
            self.process = subprocess.Popen(
                args,
                cwd=app_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            self._log(f"[启动器] Antigravity 启动成功 (PID: {self.process.pid})")
            return True, f"启动成功 (PID: {self.process.pid})"
        except Exception as e:
            if self.injector:
                self.injector.stop_monitoring()
                self.injector = None
            self._log(f"[启动器错误] 启动进程失败: {e}")
            return False, f"启动失败: {e}"

    def stop_injector(self) -> None:
        """Stop localization watcher if running."""
        if self.injector:
            self.injector.stop_monitoring()
            self.injector = None
