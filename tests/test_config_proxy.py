import json
import socket
import struct
import threading
import ipaddress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from core.config_manager import ConfigManager, DEFAULT_PROXIES
from core.proxy_checker import DEFAULT_NO_PROXY, PRIVATE_IPV4_NETWORKS, build_environment, check_proxy_http, normalize_no_proxy, normalize_proxy, redact


def test_partial_config_and_backup(tmp_path):
    path = tmp_path / 'config.json'
    original = b'{"current_proxy":"http://127.0.0.1:7891", "custom":17}'
    path.write_bytes(original)
    config = ConfigManager(path)
    assert config.save({'enable_hans': False})
    assert config.get('custom') == 17
    assert config.get('current_proxy').endswith(':7891')
    assert path.with_suffix('.json.bak').read_bytes() == original
    assert 'http://127.0.0.1:7897' in config.get('proxy_list')


def test_atomic_failure_rolls_back_disk_and_memory(tmp_path, monkeypatch):
    config = ConfigManager(tmp_path / 'config.json')
    assert config.save()
    original = config.config_path.read_bytes()
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(config, '_atomic_write', fail)
    assert not config.save({'current_proxy': 'http://localhost:1234'})
    assert config.config_path.read_bytes() == original
    assert config.get('current_proxy') == DEFAULT_PROXIES[0]
    with pytest.raises(ValueError):
        config.add_proxy('http://localhost:1234')
    assert 'http://localhost:1234' not in config.get('proxy_list')


def test_invalid_json_preserved(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{broken', encoding='utf8')
    config = ConfigManager(path)
    with pytest.raises(ValueError):
        config.snapshot()
    assert not config.save()
    assert path.read_text() == '{broken'


def test_invalid_field_can_be_repaired(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"proxy_list":null}', encoding='utf8')
    config = ConfigManager(path)
    assert config.save({'proxy_list': []})
    assert list(tmp_path.glob('config.json.invalid-*'))


@pytest.mark.parametrize('value', ['', 'http://:80', 'http://localhost', 'http://localhost:0',
    'http://localhost:65536', 'http://localhost:bad', 'http://localhost:80/path', 'ftp://localhost:80',
    'http://localhost:80?secret=1', 'http://local host:80'])
def test_invalid_proxies(value):
    with pytest.raises(ValueError):
        normalize_proxy(value)


def test_environment_isolated_and_redacted():
    inherited = {'Path': 'keep', 'http_proxy': 'old', 'ALL_PROXY': 'old', 'WS_PROXY': 'old', 'ELECTRON_RUN_AS_NODE': '1'}
    env = build_environment(True, 'socks5://name:pass@127.0.0.1:1234', 'example.test', inherited)
    assert env['HTTP_PROXY'].startswith('socks5://')
    assert env['NO_PROXY'] == 'localhost,127.0.0.1,::1,example.test'
    assert 'http_proxy' not in env and 'WS_PROXY' not in env
    assert inherited['ALL_PROXY'] == 'old'
    assert build_environment(False, '', '', inherited) == {'Path': 'keep', 'NO_PROXY': 'localhost,127.0.0.1,::1'}
    assert 'pass' not in redact(env['HTTP_PROXY'])
    assert normalize_proxy('http://[::1]:1234').host == '::1'


def test_http_proxy_receives_request(monkeypatch):
    seen = []
    class Proxy(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(204)
            self.end_headers()
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:1')
        assert check_proxy_http(f'http://127.0.0.1:{server.server_port}', 'http://nonexistent.invalid/check')[0]
        assert seen == ['http://nonexistent.invalid/check']
    finally:
        server.shutdown(); server.server_close(); worker.join()


def test_socks_remote_dns():
    seen = []
    server = socket.socket()
    server.bind(('127.0.0.1', 0)); server.listen(); server.settimeout(3)
    def read(sock, n):
        data = b''
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk: raise EOFError()
            data += chunk
        return data
    def serve():
        with server.accept()[0] as sock:
            sock.settimeout(3)
            header = read(sock, 2); read(sock, header[1])
            sock.sendall(b'\x05\x00')
            request = read(sock, 4)
            assert request == b'\x05\x01\x00\x03'
            host = read(sock, read(sock, 1)[0]).decode()
            seen.append((host, struct.unpack('!H', read(sock, 2))[0]))
            sock.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x50')
            sock.recv(8192)
            sock.sendall(b'HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n')
    thread = threading.Thread(target=serve, daemon=True); thread.start()
    try:
        assert check_proxy_http(f'socks5://127.0.0.1:{server.getsockname()[1]}', 'http://remote-dns.invalid/check')[0]
        assert seen == [('remote-dns.invalid', 80)]
    finally:
        thread.join(4); server.close()


def test_bad_proxy_does_not_escape_check():
    assert not check_proxy_http('http://localhost:bad')[0]


def test_new_defaults_and_socks_alias(tmp_path):
    config = ConfigManager(tmp_path / 'config.json')
    assert config.get('proxy_list') == [
        'socks5://127.0.0.1:7897', 'https://127.0.0.1:7897', 'http://127.0.0.1:7897']
    assert config.get('current_proxy') == DEFAULT_PROXIES[0]
    assert config.get('no_proxy') == DEFAULT_NO_PROXY
    proxy = normalize_proxy('socks://127.0.0.1:7897')
    assert proxy.url == 'socks5://127.0.0.1:7897'
    assert proxy.request_url == 'socks5h://127.0.0.1:7897'
    assert build_environment(True, proxy.url, DEFAULT_NO_PROXY)['NO_PROXY'] == DEFAULT_NO_PROXY


def test_private_ranges_are_exact_rfc1918_networks():
    expected = [('10.0.0.0', '10.255.255.255'), ('172.16.0.0', '172.31.255.255'),
                ('192.168.0.0', '192.168.255.255')]
    assert [(str(ipaddress.ip_network(net).network_address), str(ipaddress.ip_network(net).broadcast_address))
            for net in PRIVATE_IPV4_NETWORKS] == expected
    from requests.utils import should_bypass_proxies
    for address in ['10.0.0.1', '10.255.255.254', '172.16.0.1', '172.31.255.254', '192.168.1.2']:
        assert should_bypass_proxies('http://' + address, no_proxy=DEFAULT_NO_PROXY)
    for address in ['9.255.255.255', '11.0.0.0', '172.15.255.255', '172.32.0.0', '192.169.0.1']:
        assert not should_bypass_proxies('http://' + address, no_proxy=DEFAULT_NO_PROXY)


def test_direct_list_separators_and_validation():
    value = '10.0.0.0/8；172.16.0.0/12;192.168.0.0/16，localhost'
    assert normalize_no_proxy(value) == DEFAULT_NO_PROXY
    with pytest.raises(ValueError, match='CIDR'):
        normalize_no_proxy('172.16.0.0/99')
