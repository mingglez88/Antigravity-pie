"""Validated configuration with atomic persistence and a last-good backup."""
import copy
import json
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from core.proxy_checker import DEFAULT_NO_PROXY, normalize_no_proxy, normalize_proxy, redact

DEFAULT_APP_PATHS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe"),
    os.path.expandvars(r"%ProgramFiles%\antigravity\Antigravity.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\antigravity\Antigravity.exe"),
]
DEFAULT_PROXIES = [f"{scheme}://127.0.0.1:7897" for scheme in ("socks5", "https", "http")]


def detect_app_path() -> str:
    return next((path for path in DEFAULT_APP_PATHS if Path(path).is_file()), "")


@dataclass(frozen=True)
class LaunchSettings:
    app_path: str
    enable_proxy: bool
    current_proxy: str
    no_proxy: str
    enable_hans: bool
    debugging_port: int


class ConfigManager:
    def __init__(self, config_path=None):
        self.config_path = Path(config_path) if config_path else Path(__file__).resolve().parent.parent / "config.json"
        self.config_dir = self.config_path.parent
        self.defaults = dict(app_path=detect_app_path(), enable_proxy=True,
                             current_proxy=DEFAULT_PROXIES[0], proxy_list=list(DEFAULT_PROXIES),
                             no_proxy=DEFAULT_NO_PROXY, enable_hans=True,
                             debugging_port=58321, auto_minimize=False)
        self.lock = threading.RLock()
        self.load_error = ""
        self.last_error = ""
        self.config = self.load()
        self._saved = copy.deepcopy(self.config)

    def load(self):
        data = copy.deepcopy(self.defaults)
        self.load_error = ""
        if self.config_path.exists():
            try:
                saved = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
                if not isinstance(saved, dict):
                    raise ValueError("配置根节点必须是对象")
                data.update(saved)
            except (OSError, ValueError) as exc:
                self.load_error = f"配置读取失败，原文件已保留: {redact(exc)}"
        if isinstance(data.get("proxy_list"), list) and all(isinstance(p, str) for p in data["proxy_list"]):
            current = data.get("current_proxy")
            if isinstance(current, str) and current and current not in data["proxy_list"]:
                data["proxy_list"].insert(0, current)
            for proxy in DEFAULT_PROXIES:
                if proxy not in data["proxy_list"]:
                    data["proxy_list"].append(proxy)
        return data

    def _validated(self, data, check_path=False):
        if not isinstance(data, dict):
            raise ValueError("配置根节点必须是对象")
        data = {**copy.deepcopy(self.defaults), **copy.deepcopy(data)}
        for name in ("enable_proxy", "enable_hans", "auto_minimize"):
            if type(data.get(name)) is not bool:
                raise ValueError(f"{name} 必须是布尔值")
        for name in ("app_path", "current_proxy", "no_proxy"):
            if not isinstance(data.get(name), str):
                raise ValueError(f"{name} 必须是字符串")
            data[name] = data[name].strip()
        port = data.get("debugging_port")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("调试端口必须是 1–65535 范围内的整数")
        proxies = data.get("proxy_list")
        if not isinstance(proxies, list) or not all(isinstance(p, str) for p in proxies):
            raise ValueError("proxy_list 必须是代理地址列表")
        data["proxy_list"] = list(dict.fromkeys(normalize_proxy(p).url for p in proxies))
        if data["current_proxy"]:
            data["current_proxy"] = normalize_proxy(data["current_proxy"]).url
        elif data["enable_proxy"]:
            raise ValueError("启用代理时必须填写代理地址")
        data["no_proxy"] = normalize_no_proxy(data["no_proxy"])
        if check_path and (not Path(data["app_path"]).is_file() or Path(data["app_path"]).suffix.lower() != ".exe"):
            raise ValueError("请指定有效的 Antigravity.exe 文件")
        return data

    def snapshot(self) -> LaunchSettings:
        with self.lock:
            if self.load_error:
                raise ValueError(self.load_error)
            data = self._validated(self.config, check_path=True)
            return LaunchSettings(**{key: data[key] for key in LaunchSettings.__dataclass_fields__})

    def _atomic_write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as file:
                name = file.name
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)

    def save(self, updates=None) -> bool:
        with self.lock:
            try:
                if self.load_error:
                    raise ValueError("原配置无法读取，请先修复或移走该文件，避免覆盖损坏的原件")
                candidate = {**self.config, **(updates or {})}
                valid = self._validated(candidate)
                if self.config_path.exists():
                    old = self.config_path.read_bytes()
                    try:
                        self._validated(json.loads(old.decode("utf-8-sig")))
                    except (ValueError, TypeError, KeyError):
                        # Preserve an invalid original separately, never replace a good backup.
                        recovery = self.config_path.with_name(self.config_path.name + ".invalid-" + uuid.uuid4().hex)
                        self._atomic_write(recovery, old)
                    else:
                        self._atomic_write(self.config_path.with_suffix(".json.bak"), old)
                self._atomic_write(self.config_path, json.dumps(valid, ensure_ascii=False, indent=2).encode("utf-8"))
                self.config = valid
                self._saved = copy.deepcopy(valid)
                self.last_error = ""
                return True
            except (OSError, ValueError, TypeError) as exc:
                self.last_error = redact(exc)
                self.config = copy.deepcopy(self._saved)
                return False

    def get(self, key, default=None):
        with self.lock:
            return copy.deepcopy(self.config.get(key, default))

    def set(self, key, value):
        with self.lock:
            self.config[key] = copy.deepcopy(value)

    def add_proxy(self, proxy_str):
        proxy = normalize_proxy(proxy_str).url
        with self.lock:
            proxies = copy.deepcopy(self.config.get("proxy_list"))
            if not isinstance(proxies, list):
                raise ValueError("proxy_list 配置无效")
            if proxy not in proxies:
                proxies.insert(0, proxy)
            if not self.save({"proxy_list": proxies}):
                raise ValueError(self.last_error)
        return proxy

    def remove_proxy(self, proxy_str):
        with self.lock:
            proxies = copy.deepcopy(self.config.get("proxy_list"))
            if not isinstance(proxies, list):
                raise ValueError("proxy_list 配置无效")
            if proxy_str in proxies:
                proxies.remove(proxy_str)
                changes = {"proxy_list": proxies}
                if self.config.get("current_proxy") == proxy_str:
                    changes["current_proxy"] = proxies[0] if proxies else ""
                    if not proxies:
                        changes["enable_proxy"] = False
                if not self.save(changes):
                    raise ValueError(self.last_error)
