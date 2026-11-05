"""Offline TLS/CONNECT tests; certificate trust is restricted to each test."""
import os
from pathlib import Path
import select
import shutil
import socket
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from core.proxy_checker import check_proxy_http


@pytest.fixture(scope='module')
def certificate(tmp_path_factory):
    openssl = shutil.which('openssl') or r'C:\Program Files\Git\usr\bin\openssl.exe'
    if not Path(openssl).is_file():
        pytest.skip('OpenSSL required for ephemeral test CA')
    folder = tmp_path_factory.mktemp('tls')
    cert, key = folder/'cert.pem', folder/'key.pem'
    subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
                    '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1',
                    '-keyout', str(key), '-out', str(cert)], capture_output=True, check=True, timeout=15)
    return cert, key


class OK(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(204); self.end_headers()
    def log_message(self, *args): pass


def tls_server(handler, certificate):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(*map(str, certificate))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    return server, thread


def trust_fixture(monkeypatch, certificate):
    original = requests.Session
    def session():
        result = original(); result.verify = str(certificate[0]); return result
    monkeypatch.setattr('core.proxy_checker.requests.Session', session)


def test_https_proxy_and_certificate_verification(certificate, monkeypatch):
    server, thread = tls_server(OK, certificate)
    try:
        proxy = f'https://127.0.0.1:{server.server_port}'
        assert not check_proxy_http(proxy, 'http://unresolvable.invalid/')[0]
        trust_fixture(monkeypatch, certificate)
        assert check_proxy_http(proxy, 'http://unresolvable.invalid/')[0]
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_http_connect_to_https_target(certificate, monkeypatch):
    target, target_thread = tls_server(OK, certificate)
    seen = []
    class Connect(BaseHTTPRequestHandler):
        def do_CONNECT(self):
            seen.append(self.path)
            with socket.create_connection(('127.0.0.1', target.server_port)) as upstream:
                self.send_response(200); self.end_headers()
                peers = [self.connection, upstream]
                while True:
                    readable, _, _ = select.select(peers, [], [], 3)
                    if not readable: return
                    for source in readable:
                        data = source.recv(65536)
                        if not data: return
                        (upstream if source is self.connection else self.connection).sendall(data)
        def log_message(self, *args): pass
    proxy = ThreadingHTTPServer(('127.0.0.1', 0), Connect)
    worker = threading.Thread(target=proxy.serve_forever, daemon=True); worker.start()
    try:
        trust_fixture(monkeypatch, certificate)
        assert check_proxy_http(f'http://127.0.0.1:{proxy.server_port}', f'https://localhost:{target.server_port}/')[0]
        assert seen == [f'localhost:{target.server_port}']
    finally:
        proxy.shutdown(); proxy.server_close(); worker.join()
        target.shutdown(); target.server_close(); target_thread.join()
