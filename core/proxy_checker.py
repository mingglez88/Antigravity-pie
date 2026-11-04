"""Proxy connectivity and latency testing utility."""

import socket
import time
import urllib.parse
import urllib.request
from typing import Tuple


def parse_proxy(proxy_str: str) -> Tuple[str, int]:
    """Parse proxy string into host and port."""
    proxy_str = proxy_str.strip()
    if not (proxy_str.startswith("http://") or proxy_str.startswith("https://") or proxy_str.startswith("socks5://")):
        proxy_str = f"http://{proxy_str}"
    parsed = urllib.parse.urlparse(proxy_str)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (7890 if "socks" in parsed.scheme else 8080)
    return host, port


def check_tcp_port(host: str, port: int, timeout: float = 2.0) -> Tuple[bool, float, str]:
    """Check if the proxy TCP port is open and listening."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency_ms = (time.perf_counter() - start) * 1000.0
            return True, latency_ms, f"端口连通正常 ({latency_ms:.1f}ms)"
    except socket.timeout:
        return False, 0.0, "连接超时"
    except ConnectionRefusedError:
        return False, 0.0, "连接被拒绝（代理软件未启动或端口错误）"
    except Exception as e:
        return False, 0.0, f"连接失败: {e}"


def check_proxy_http(proxy_url: str, test_url: str = "https://www.google.com", timeout: float = 4.0) -> Tuple[bool, float, str]:
    """Test actual HTTP request through the specified proxy."""
    if not (proxy_url.startswith("http://") or proxy_url.startswith("https://")):
        proxy_url = f"http://{proxy_url}"

    host, port = parse_proxy(proxy_url)
    tcp_ok, latency, tcp_msg = check_tcp_port(host, port, timeout=2.0)
    if not tcp_ok:
        return False, 0.0, tcp_msg

    start = time.perf_counter()
    try:
        proxy_handler = urllib.request.ProxyHandler({
            "http": proxy_url,
            "https": proxy_url,
        })
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(
            test_url,
            headers={"User-Agent": "AntigravityLauncher/1.0"},
        )
        with opener.open(req, timeout=timeout) as response:
            latency_ms = (time.perf_counter() - start) * 1000.0
            if response.status in (200, 204, 301, 302):
                return True, latency_ms, f"代理测试成功！网络延迟: {latency_ms:.1f}ms"
            return True, latency_ms, f"代理响应状态码: {response.status} ({latency_ms:.1f}ms)"
    except urllib.error.URLError as e:
        return False, 0.0, f"外网测试失败: {e.reason}"
    except Exception as e:
        return False, 0.0, f"测试出错: {e}"
