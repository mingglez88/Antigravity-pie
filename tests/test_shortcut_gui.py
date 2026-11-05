import os
from pathlib import Path
import subprocess
import time
import threading
import functools
import sys

import pytest

from core.config_manager import ConfigManager
from core.app_launcher import LaunchResult
from core import shortcut_helper as shortcuts


def isolated_tk(test):
    """The product owns one Tk interpreter; each GUI scenario gets its own process."""
    @functools.wraps(test)
    def run(*args, **kwargs):
        if os.environ.get('ANTIGRAVITY_GUI_CASE') == test.__name__:
            return test(*args, **kwargs)
        env = dict(os.environ, ANTIGRAVITY_GUI_CASE=test.__name__)
        result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'pytest',
                                 f'{__file__}::{test.__name__}', '-q'],
                                cwd=Path(__file__).resolve().parents[1], env=env,
                                capture_output=True, text=True, encoding='utf8', timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        assert result.returncode == 0, result.stdout + result.stderr
    return run


class FakeTray:
    def __init__(self, path, callback):
        self.callback = callback
        self.available = False
        self.closed = False
    def start(self): self.available = True
    def update(self, text): self.tip = text
    def close(self): self.available = False; self.closed = True


@pytest.mark.skipif(os.name != 'nt', reason='Windows shortcuts')
def test_actual_shortcut_and_scripts(tmp_path, monkeypatch):
    folder = tmp_path / "中文 user's $literal ! %PATH% space"
    folder.mkdir()
    desktop = tmp_path / 'redirected-desktop'; desktop.mkdir()
    marker = folder / 'ran.txt'
    (folder / 'launcher.py').write_text(
        "from pathlib import Path\nimport sys\nPath(__file__).with_name('ran.txt').write_text('|'.join(sys.argv[1:]), encoding='utf8')\n",
        encoding='utf8')
    monkeypatch.setattr(shortcuts, 'get_desktop_path', lambda: str(desktop))
    ok, messages = shortcuts.create_all_desktop_shortcuts(
        str(Path(os.environ['WINDIR']) / 'System32' / 'notepad.exe'), str(folder))
    if not ok:
        pytest.fail('\n'.join(messages), pytrace=False)
    assert len(messages) == 4
    for artifact in [desktop / 'Antigravity (汉化代理版).lnk', desktop / '启动Antigravity(汉化代理版).bat', folder / '启动Antigravity(无窗口静默版).vbs']:
        if marker.exists(): marker.unlink()
        if artifact.suffix == '.lnk':
            os.startfile(artifact)
        elif artifact.suffix == '.bat':
            result = subprocess.run(f'cmd.exe /d /s /c ""{artifact}""', timeout=10,
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode == 0, result.stderr
        else:
            result = subprocess.run(['cscript.exe', '//Nologo', str(artifact)], timeout=10,
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode == 0, result.stderr
        deadline = time.monotonic() + 6
        while not marker.exists() and time.monotonic() < deadline: time.sleep(0.05)
        assert marker.exists(), str(artifact)
        assert marker.read_text(encoding='utf8') == '--silent-launch'


def test_partial_shortcut_failure(tmp_path, monkeypatch):
    (tmp_path/'launcher.py').touch()
    monkeypatch.setattr(shortcuts, 'get_desktop_path', lambda: str(tmp_path))
    monkeypatch.setattr(shortcuts, 'create_windows_shortcut', lambda **kw: (False, 'simulated failure'))
    ok, messages = shortcuts.create_all_desktop_shortcuts(launcher_dir=str(tmp_path))
    assert not ok and len(messages) == 4


@isolated_tk
def test_gui_queue_hide_and_exit(tmp_path, monkeypatch):
    from ui.main_window import MainWindow
    config = ConfigManager(tmp_path/'config.json')
    monkeypatch.setattr(MainWindow, '_launch_app', lambda *args, **kw: None)
    app = MainWindow(config, hidden=True, tray_factory=FakeTray)
    try:
        app.update()
        thread = threading.Thread(target=lambda: app.append_log('thread log'))
        thread.start(); thread.join()
        app._pump()
        assert 'thread log' in app.txt_log.get('1.0', 'end')
        app.launcher._state = LaunchResult(status='ready', pid=123, message='ready')
        app.show_panel(); app._close_panel()
        assert app.hidden and app.winfo_exists()
        app.events.put(('ipc', 'show')); app._pump()
        assert not app.hidden
        app._close_panel()
        app.events.put(('state', LaunchResult(status='stopped', message='exited')))
        app._pump()
        assert app.closed
        assert app.tray.closed
    finally:
        if not app.closed: app._exit()


@isolated_tk
def test_success_moves_to_tray_and_menu_restores_or_exits(tmp_path, monkeypatch):
    from ui.main_window import MainWindow
    config = ConfigManager(tmp_path/'config.json')
    app = MainWindow(config, tray_factory=FakeTray)
    try:
        app.busy = True
        app.events.put(('finished', LaunchResult(status='ready', pid=123)))
        app._pump()
        assert app.hidden and app.state() == 'withdrawn'
        app.tray.callback('show'); app._pump()
        assert not app.hidden
        app.events.put(('finished', LaunchResult(status='failed', error='failed')))
        app._pump()
        assert not app.hidden
        app.tray.callback('exit'); app._pump()
        assert app.closed and app.tray.closed
    finally:
        if not app.closed: app._exit()


@isolated_tk
def test_unavailable_tray_keeps_panel_visible(tmp_path):
    from ui.main_window import MainWindow
    class BrokenTray(FakeTray):
        def start(self): raise OSError('tray unavailable')
    app = MainWindow(ConfigManager(tmp_path/'config.json'), tray_factory=BrokenTray)
    try:
        app.events.put(('finished', LaunchResult(status='ready', pid=123)))
        app._pump()
        assert not app.hidden
        assert app.tray is None
    finally: app._exit()
