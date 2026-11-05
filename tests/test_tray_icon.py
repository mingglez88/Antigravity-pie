import ctypes
import os
from pathlib import Path
import queue
import time

import pytest


@pytest.mark.skipif(os.name != 'nt', reason='Windows notification area')
def test_native_tray_add_restore_and_cleanup():
    from ui.tray_icon import TrayIcon, CALLBACK_MESSAGE
    commands = queue.Queue()
    tray = TrayIcon(Path(__file__).resolve().parents[1] / 'assets/launcher-icon.ico', commands.put)
    try:
        tray.start()
        assert tray.available and tray.hwnd
        tray.user.PostMessageW(tray.hwnd, CALLBACK_MESSAGE, 0, (1 << 16) | 0x400)
        assert commands.get(timeout=2) == 'show'
        tray.update('汉化监视正常')
        # Explorer restart broadcasts TaskbarCreated. Re-register without restarting Explorer.
        tray.user.PostMessageW(tray.hwnd, tray._taskbar_created, 0, 0)
        time.sleep(0.1)
        assert tray.available
    finally:
        tray.close()
    assert not tray.available
    assert tray.hwnd is None
    assert not tray._thread.is_alive()
