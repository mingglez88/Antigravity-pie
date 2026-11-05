import json
import logging
from pathlib import Path

from core.cdp_injector import CDPInjector, FEATURE_CHECK
from core.diagnostics import configure_logging


class Socket:
    def __init__(self):
        self.commands = []; self.pending = []; self.installed = False; self.closed = False; self.exception = False
    def send(self, raw):
        request = json.loads(raw); self.commands.append(request)
        method = request['method']; expression = request.get('params', {}).get('expression', '')
        value = True
        if method == 'Runtime.evaluate':
            if expression == FEATURE_CHECK: value = True
            elif expression.startswith('window.__antigravityZhPatchInstalled'): value = self.installed
            elif expression.startswith('window.__antigravityZhPatchInitializing'): value = False
            else:
                self.installed = True
                if self.exception:
                    self.pending.append(json.dumps({'id': request['id'], 'result': {'exceptionDetails': {'text':'secret'}}}))
                    return
        self.pending += [json.dumps({'method': 'Runtime.consoleAPICalled'}),
                         json.dumps({'id': request['id'], 'result': {'result': {'value': value}, 'identifier': 'registered'}})]
    def recv(self, **kw): return self.pending.pop(0)
    def close(self): self.closed = True


def injector(monkeypatch, socket):
    cdp = CDPInjector(port_owner=lambda: True, target_owner=lambda url: url == 'https://127.0.0.1:1234/')
    target = {'id':'app-page', 'type':'page', 'url':'https://127.0.0.1:1234/',
              'webSocketDebuggerUrl':'ws://127.0.0.1:58321/devtools/page/app-page'}
    monkeypatch.setattr(cdp, 'fetch_targets', lambda: [target])
    calls = []
    def connect(url, **kw):
        calls.append(kw); return socket
    monkeypatch.setattr('core.cdp_injector.connect', connect)
    return cdp, target, calls


def test_connection_reuse_and_release(monkeypatch):
    socket = Socket(); cdp, target, calls = injector(monkeypatch, socket)
    assert cdp.scan().injected_targets == 1
    assert cdp.scan().injected_targets == 1
    assert len(calls) == 1 and calls[0]['proxy'] is None
    assert sum(c['method'] == 'Page.addScriptToEvaluateOnNewDocument' for c in socket.commands) == 1
    socket.installed = False
    assert cdp.scan().injected_targets == 1
    assert len(calls) == 1
    monkeypatch.setattr(cdp, 'fetch_targets', lambda: [])
    cdp.scan()
    assert socket.closed
    cdp.stop_monitoring()


def test_exception_not_reported_as_installed(monkeypatch):
    socket = Socket(); socket.exception = True
    cdp, _, _ = injector(monkeypatch, socket)
    result = cdp.scan()
    assert result.injected_targets == 0
    assert 'secret' not in result.error
    assert socket.closed


def test_untrusted_targets_never_connect(monkeypatch):
    socket = Socket(); cdp, target, calls = injector(monkeypatch, socket)
    target['url'] = 'https://example.com'
    assert cdp.scan().injected_targets == 0 and not calls
    target['url'] = 'https://127.0.0.1:1234/'
    target['webSocketDebuggerUrl'] = 'ws://example.com:58321/devtools/page/app'
    assert cdp.scan().injected_targets == 0 and not calls


def test_log_redaction_rotation_and_reinitialization(tmp_path):
    configure_logging(tmp_path); configure_logging(tmp_path)
    log = logging.getLogger('antigravity_launcher')
    assert len(log.handlers) == 1
    log.error('failure http://user:secret@127.0.0.1:1234')
    log.handlers[0].flush()
    assert 'secret' not in (tmp_path/'launcher.log').read_text(encoding='utf8')
    log.handlers[0].maxBytes = 100
    for _ in range(10): log.info('x' * 70)
    assert len(list(tmp_path.glob('launcher.log*'))) == 3
    for handler in list(log.handlers):
        handler.close(); log.removeHandler(handler)
