"""Configuration manager for Antigravity Launcher."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_APP_PATHS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe"),
    os.path.expandvars(r"%ProgramFiles%\antigravity\Antigravity.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\antigravity\Antigravity.exe"),
    r"C:\Users\mingg\AppData\Local\Programs\antigravity\Antigravity.exe",
]

DEFAULT_PROXIES = [
    "http://127.0.0.1:60808",
    "http://127.0.0.1:7891",
    "http://127.0.0.1:10809",
    "http://127.0.0.1:7890",
]


def detect_app_path() -> str:
    """Detect Antigravity.exe location."""
    for path in DEFAULT_APP_PATHS:
        if path and os.path.exists(path):
            return path
    return DEFAULT_APP_PATHS[0]


class ConfigManager:
    """Manages persistent settings in config.json."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            self.config_dir = Path(__file__).resolve().parent.parent
            self.config_path = self.config_dir / "config.json"
        else:
            self.config_path = Path(config_path)

        self.defaults: Dict[str, Any] = {
            "app_path": detect_app_path(),
            "enable_proxy": True,
            "current_proxy": "http://127.0.0.1:60808",
            "proxy_list": list(DEFAULT_PROXIES),
            "no_proxy": "localhost,127.0.0.1,::1",
            "enable_hans": True,
            "debugging_port": 58321,
            "auto_minimize": False,
        }
        self.config: Dict[str, Any] = self.load()

    def load(self) -> Dict[str, Any]:
        """Load configuration from disk, falling back to defaults."""
        data = dict(self.defaults)
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        data.update(saved)
            except Exception as e:
                print(f"[ConfigManager] Error reading {self.config_path}: {e}")

        # Ensure current proxy is in the list
        if data["current_proxy"] and data["current_proxy"] not in data["proxy_list"]:
            data["proxy_list"].insert(0, data["current_proxy"])

        return data

    def save(self) -> bool:
        """Persist current configuration to disk."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ConfigManager] Error saving {self.config_path}: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.config[key] = value

    def add_proxy(self, proxy_str: str) -> None:
        proxy_str = proxy_str.strip()
        if not proxy_str:
            return
        if not (proxy_str.startswith("http://") or proxy_str.startswith("socks5://") or proxy_str.startswith("https://")):
            proxy_str = f"http://{proxy_str}"
        proxies: List[str] = self.config.get("proxy_list", [])
        if proxy_str not in proxies:
            proxies.insert(0, proxy_str)
            self.config["proxy_list"] = proxies
            self.save()

    def remove_proxy(self, proxy_str: str) -> None:
        proxies: List[str] = self.config.get("proxy_list", [])
        if proxy_str in proxies:
            proxies.remove(proxy_str)
            self.config["proxy_list"] = proxies
            if self.config.get("current_proxy") == proxy_str:
                self.config["current_proxy"] = proxies[0] if proxies else ""
            self.save()
