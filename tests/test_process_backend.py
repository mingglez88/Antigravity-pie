from types import SimpleNamespace
from unittest.mock import Mock

from core.process_backend import ProcessBackend, ProcessIdentity


def test_identity_rejects_recycled_pid(monkeypatch, tmp_path):
    path = str(tmp_path/'Antigravity.exe')
    process = Mock()
    process.is_running.return_value = True
    process.create_time.return_value = 8.0
    process.exe.return_value = path
    monkeypatch.setattr('core.process_backend.psutil.Process', lambda pid: process)
    assert not ProcessBackend().alive(ProcessIdentity(2, 7.0, path))
    assert ProcessBackend().alive(ProcessIdentity(2, 8.0, path))


def test_only_selected_install_main_processes(monkeypatch, tmp_path):
    wanted = str(tmp_path/'selected'/'Antigravity.exe')
    processes = [SimpleNamespace(pid=index, info={'pid': index, 'exe': path,
        'create_time': 1.0, 'cmdline': args}) for index, path, args in [
            (1, wanted, [wanted]), (2, wanted, [wanted, '--type=renderer']),
            (3, str(tmp_path/'other'/'Antigravity.exe'), [])]]
    monkeypatch.setattr('core.process_backend.psutil.process_iter', lambda *args: processes)
    assert [p.pid for p in ProcessBackend().find(wanted)] == [1]


def test_ambiguous_listener_is_not_an_owned_port(monkeypatch):
    connections = [SimpleNamespace(status='LISTEN', laddr=SimpleNamespace(port=58321), pid=pid) for pid in [2, 3]]
    monkeypatch.setattr('core.process_backend.psutil.net_connections', lambda **kw: connections)
    backend = ProcessBackend(); backend.refresh_connections()
    monkeypatch.setattr(backend, 'alive', lambda identity: True)
    assert backend.listener(58321) == -1
    assert not backend.owns_debug_port(ProcessIdentity(2, 1, 'x'), 58321)


def test_page_origin_requires_app_backend(monkeypatch):
    backend = ProcessBackend()
    monkeypatch.setattr(backend, 'alive', lambda identity: True)
    identity = ProcessIdentity(2, 1, 'C:/Apps/Antigravity.exe')
    assert not backend.owns_page(identity, 'https://example.com/')
    assert not backend.owns_page(identity, 'http://127.0.0.1:1234/')
    assert not backend.owns_page(identity, 'data:text/html,hello')
