"""One proxy representation for configuration, requests and child processes."""
import os
import re
import socket
import ssl
import time
import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import requests

LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
PRIVATE_IPV4_NETWORKS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
DEFAULT_NO_PROXY = ",".join(LOOPBACK_HOSTS + PRIVATE_IPV4_NETWORKS)


class VerifiedProxyAdapter(requests.adapters.HTTPAdapter):
    """Keep HTTPS proxy verification enabled even for an HTTP target URL."""
    def __init__(self, ca_bundle):
        self.proxy_context = ssl.create_default_context(cafile=ca_bundle)
        super().__init__()

    def proxy_manager_for(self, proxy, **kwargs):
        kwargs["proxy_ssl_context"] = self.proxy_context
        return super().proxy_manager_for(proxy, **kwargs)


def redact(value: object) -> str:
    return re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^\s/]*@", r"\1***@", str(value))


@dataclass(frozen=True)
class ProxyAddress:
    url: str
    scheme: str
    host: str
    port: int

    @property
    def request_url(self) -> str:
        return self.url.replace("socks5://", "socks5h://", 1)


def normalize_proxy(value: str) -> ProxyAddress:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("代理地址不能为空")
    value = value.strip()
    if any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise ValueError("代理地址包含空白或控制字符")
    if "://" not in value:
        value = "http://" + value
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ("http", "https", "socks", "socks5", "socks5h"):
            raise ValueError("仅支持 HTTP、HTTPS 和 SOCKS5 代理")
        if not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("代理地址必须为 协议://主机:端口")
        port = parsed.port
        if port is None or not 1 <= port <= 65535:
            raise ValueError("请填写 1–65535 范围内的代理端口")
        scheme = parsed.scheme.lower()
        if scheme == "socks":
            scheme = "socks5"
        return ProxyAddress(urlunsplit((scheme, parsed.netloc, "", "", "")), scheme, parsed.hostname, port)
    except ValueError as exc:
        raise ValueError(redact(exc)) from None


def parse_proxy(proxy_str: str) -> tuple[str, int]:
    proxy = normalize_proxy(proxy_str)
    return proxy.host, proxy.port


def normalize_no_proxy(value: str) -> str:
    items = list(LOOPBACK_HOSTS)
    for raw in re.split(r"[,;；，]", value):
        item = raw.strip()
        if not item:
            continue
        if "/" in item:
            try:
                item = str(ipaddress.ip_network(item, strict=False))
            except ValueError:
                raise ValueError("直连列表包含无效的 CIDR 网段") from None
        items.append(item)
    return ",".join(dict.fromkeys(items))


def build_environment(enabled: bool, proxy_url: str, no_proxy: str, inherited=None) -> dict[str, str]:
    env = dict(os.environ if inherited is None else inherited)
    for key in list(env):
        if key.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy", "ws_proxy", "wss_proxy", "electron_run_as_node"}:
            del env[key]
    env["NO_PROXY"] = normalize_no_proxy(no_proxy)
    if enabled:
        proxy = normalize_proxy(proxy_url)
        env.update(HTTP_PROXY=proxy.url, HTTPS_PROXY=proxy.url, ALL_PROXY=proxy.url)
    return env


def check_tcp_port(host: str, port: int, timeout: float = 2.0) -> tuple[bool, float, str]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = (time.monotonic() - started) * 1000
            return True, elapsed, f"端口连通 ({elapsed:.1f}ms)"
    except OSError as exc:
        return False, 0.0, f"代理端口连接失败: {redact(exc)}"


def check_proxy_http(proxy_url: str, test_url="https://www.google.com", timeout=4.0) -> tuple[bool, float, str]:
    started = time.monotonic()
    try:
        proxy = normalize_proxy(proxy_url)
        with requests.Session() as session:
            session.trust_env = False
            if proxy.scheme == "https":
                ca_bundle = session.verify if isinstance(session.verify, str) else requests.certs.where()
                session.mount("http://", VerifiedProxyAdapter(ca_bundle))
                session.mount("https://", VerifiedProxyAdapter(ca_bundle))
            session.proxies = {"http": proxy.request_url, "https": proxy.request_url}
            with session.get(test_url, timeout=(timeout, timeout), stream=True,
                             headers={"User-Agent": "AntigravityLauncher/2.0"}) as response:
                elapsed = (time.monotonic() - started) * 1000
                if 200 <= response.status_code < 400:
                    return True, elapsed, f"检测请求通过代理成功 ({elapsed:.1f}ms)"
                return False, elapsed, f"检测请求返回 HTTP {response.status_code}"
    except (ValueError, requests.RequestException, OSError) as exc:
        return False, 0.0, f"代理检测失败: {redact(exc)}"
