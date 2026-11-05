import os
import time
import uuid
from dataclasses import replace

import pytest

from core.app_launcher import AntigravityLauncher
from core.cdp_injector import InjectionStatus
from core.config_manager import ConfigManager
from core.process_backend import ProcessIdentity
from core.single_instance import SingleInstance, decode_message


class Backend:
    def __init__(self):
        self.current = None; self.starts = 0; self.closes = 0; self.port = None; self.can_close = True
    def find(self, path): return [self.current] if self.current else []
    def alive(self, item): return item is not None and item == self.current
    def refresh_connections(self): pass
    def listener(self, port): return self.port
    def owns_debug_port(self, item, port): return self.alive(item)
    def owns_page(self, item, url): return True
    def spawn(self, settings, env):
        self.starts += 1
        self.env = env
        self.current = ProcessIdentity(100 + self.starts, self.starts, settings.app_path)
        return self.current
    def close(self, items, timeout=10):
        self.closes += 1
        if self.can_close: self.current = None
        return self.can_close


class Injector:
    result = InjectionStatus(True, 1)
    def __init__(self, **kwargs): self.stopped = False
    def scan(self, **kwargs): return self.result
    def stop_monitoring(self): self.stopped = True


def make_controller(tmp_path, **kw):
    exe = tmp_path / 'Antigravity.exe'; exe.touch()
    config = ConfigManager(tmp_path / 'config.json')
    config.set('app_path', str(exe))
    backend = Backend()
    controller = AntigravityLauncher(config, backend=backend, injector_factory=Injector,
                                    startup_timeout=0.06, poll_interval=0.01, **kw)
    return controller, backend, config


def test_start_reuse_configuration_and_exit(tmp_path):
    controller, backend, config = make_controller(tmp_path)
    try:
        assert controller.start().status == 'ready'
        assert controller.start().status == 'ready'
        assert backend.starts == 1 and backend.closes == 0
        config.set('current_proxy', 'socks5://127.0.0.1:7898')
        assert controller.configuration_saved().pending_config
        assert controller.start().status == 'ready'
        assert backend.starts == 2 and backend.closes == 1
        assert backend.env['HTTPS_PROXY'] == 'socks5://127.0.0.1:7898'
        backend.current = None
        deadline = time.monotonic() + 2
        while controller.status().status != 'stopped' and time.monotonic() < deadline:
            time.sleep(0.02)
        assert controller.status().status == 'stopped'
    finally: controller.stop_monitoring()


def test_unknown_instance_and_close_failure(tmp_path):
    controller, backend, config = make_controller(tmp_path)
    backend.current = ProcessIdentity(3, 1, config.get('app_path'))
    backend.can_close = False
    assert controller.start().status == 'failed'
    assert backend.starts == 0 and backend.closes == 1
    controller.stop_monitoring()


def test_port_collision(tmp_path):
    controller, backend, _ = make_controller(tmp_path)
    backend.port = 999
    assert controller.start().status == 'failed'
    assert backend.starts == 0


def test_partial_success_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(Injector, 'result', InjectionStatus(True, 0, 'not installed'))
    controller, backend, _ = make_controller(tmp_path)
    try:
        assert controller.start().status == 'degraded'
        assert backend.current is not None
    finally: controller.stop_monitoring()


def test_cancel_initialization_stays_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(Injector, 'result', InjectionStatus(True, 0))
    controller, backend, _ = make_controller(tmp_path)
    controller.on_state = lambda state: controller.stop_monitoring() if state.status == 'injecting' else None
    assert controller.start().status == 'stopped'
    assert backend.current is not None
    assert controller._monitor is None


def test_invalid_configuration_after_stop_is_still_an_error(tmp_path):
    controller, _, config = make_controller(tmp_path)
    controller.stop_monitoring()
    config.set('debugging_port', 'invalid')
    assert controller.start().status == 'failed'


@pytest.mark.parametrize('data', [b'{}', b'[]', b'{"version":1,"command":"exec"}', b'x' * 4097])
def test_invalid_ipc(data):
    with pytest.raises(ValueError): decode_message(data)


@pytest.mark.skipif(os.name != 'nt', reason='Windows IPC')
def test_named_pipe_single_owner_and_recovery(tmp_path):
    path = str(tmp_path / (uuid.uuid4().hex + '.exe'))
    seen = []
    owner = SingleInstance(path, lambda cmd: seen.append(cmd) or 'accepted')
    other = SingleInstance(path, lambda cmd: None)
    try:
        assert owner.acquire()
        assert not other.acquire()
        assert other.send('show')['result'] == 'accepted'
        assert seen == ['show']
        assert other.send('start')['ok']
    finally:
        other.close(); owner.close()
    recovered = SingleInstance(path, lambda cmd: None)
    try: assert recovered.acquire()
    finally: recovered.close()
