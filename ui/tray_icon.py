"""Windows notification-area icon. Callbacks only enqueue UI commands."""
import ctypes
from ctypes import wintypes as w
import logging
import os
import threading
import uuid

logger = logging.getLogger('antigravity_launcher.tray')
CALLBACK_MESSAGE = 0x8000 + 41
UPDATE_MESSAGE = 0x8000 + 42
WM_CLOSE = 0x0010
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


class WindowClass(ctypes.Structure):
    _fields_ = [('style', w.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int), ('hInstance', w.HINSTANCE), ('hIcon', w.HICON),
                ('hCursor', w.HANDLE), ('hbrBackground', w.HBRUSH),
                ('lpszMenuName', w.LPCWSTR), ('lpszClassName', w.LPCWSTR)]


class Guid(ctypes.Structure):
    _fields_ = [('Data1', w.DWORD), ('Data2', w.WORD), ('Data3', w.WORD), ('Data4', ctypes.c_ubyte * 8)]


class NotifyIconData(ctypes.Structure):
    _fields_ = [('cbSize', w.DWORD), ('hWnd', w.HWND), ('uID', w.UINT), ('uFlags', w.UINT),
                ('uCallbackMessage', w.UINT), ('hIcon', w.HICON), ('szTip', w.WCHAR * 128),
                ('dwState', w.DWORD), ('dwStateMask', w.DWORD), ('szInfo', w.WCHAR * 256),
                ('uVersion', w.UINT), ('szInfoTitle', w.WCHAR * 64), ('dwInfoFlags', w.DWORD),
                ('guidItem', Guid), ('hBalloonIcon', w.HICON)]


class TrayIcon:
    def __init__(self, icon_path, on_command):
        self.icon_path = str(icon_path)
        self.on_command = on_command
        self.hwnd = None
        self.available = False
        self._icon = None
        self._ready = threading.Event()
        self._thread = None
        self._error = None
        self._tip = 'Antigravity 启动管理工具'
        self._stop = threading.Event()
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.shell = ctypes.WinDLL('shell32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self._declare()

    def _declare(self):
        signatures = {
            'RegisterClassW': ([ctypes.POINTER(WindowClass)], w.ATOM),
            'UnregisterClassW': ([w.LPCWSTR, w.HINSTANCE], w.BOOL),
            'CreateWindowExW': ([w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, ctypes.c_void_p], w.HWND),
            'DefWindowProcW': ([w.HWND, w.UINT, w.WPARAM, w.LPARAM], ctypes.c_ssize_t),
            'DestroyWindow': ([w.HWND], w.BOOL),
            'PostMessageW': ([w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.BOOL),
            'GetMessageW': ([ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT], ctypes.c_int),
            'TranslateMessage': ([ctypes.POINTER(w.MSG)], w.BOOL),
            'DispatchMessageW': ([ctypes.POINTER(w.MSG)], ctypes.c_ssize_t),
            'PostQuitMessage': ([ctypes.c_int], None),
            'RegisterWindowMessageW': ([w.LPCWSTR], w.UINT),
            'LoadImageW': ([w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int, ctypes.c_int, w.UINT], w.HANDLE),
            'DestroyIcon': ([w.HICON], w.BOOL),
            'CreatePopupMenu': ([], w.HMENU),
            'AppendMenuW': ([w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR], w.BOOL),
            'TrackPopupMenu': ([w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, ctypes.c_void_p], w.UINT),
            'DestroyMenu': ([w.HMENU], w.BOOL),
            'SetForegroundWindow': ([w.HWND], w.BOOL),
            'GetCursorPos': ([ctypes.POINTER(w.POINT)], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.user, name)
            function.argtypes, function.restype = args, result
        self.kernel.GetModuleHandleW.argtypes = [w.LPCWSTR]
        self.kernel.GetModuleHandleW.restype = w.HMODULE
        self.shell.Shell_NotifyIconW.argtypes = [w.DWORD, ctypes.POINTER(NotifyIconData)]
        self.shell.Shell_NotifyIconW.restype = w.BOOL

    def start(self):
        self._thread = threading.Thread(target=self._run, name='tray-icon', daemon=True)
        self._thread.start()
        if not self._ready.wait(3) or self._error:
            self.close()
            raise OSError(f'无法创建系统托盘图标: {self._error or "初始化超时"}')

    def _data(self):
        data = NotifyIconData()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd, data.uID = self.hwnd, 1
        data.uFlags = 1 | 2 | 4 | 0x80  # MESSAGE, ICON, TIP, SHOWTIP
        data.uCallbackMessage = CALLBACK_MESSAGE
        data.hIcon = self._icon
        data.szTip = self._tip[:127]
        data.uVersion = 4
        return data

    def _add_icon(self):
        data = self._data()
        self.available = bool(self.shell.Shell_NotifyIconW(0, ctypes.byref(data)))
        if not self.available:
            # A repeated shell notification may arrive before the old icon is removed.
            self.available = bool(self.shell.Shell_NotifyIconW(1, ctypes.byref(data)))
        if not self.available:
            raise OSError('Windows 通知区域暂不可用')
        if not self.shell.Shell_NotifyIconW(4, ctypes.byref(data)):
            self.shell.Shell_NotifyIconW(2, ctypes.byref(data))
            self.available = False
            raise OSError('Windows 通知区域版本设置失败')

    def _menu(self):
        menu = self.user.CreatePopupMenu()
        if not menu:
            return
        try:
            self.user.AppendMenuW(menu, 0, 1, '打开管理面板')
            self.user.AppendMenuW(menu, 0x800, 0, None)
            self.user.AppendMenuW(menu, 0, 2, '退出管理工具')
            point = w.POINT()
            self.user.GetCursorPos(ctypes.byref(point))
            self.user.SetForegroundWindow(self.hwnd)
            chosen = self.user.TrackPopupMenu(menu, 0x100 | 0x2, point.x, point.y, 0, self.hwnd, None)
            if chosen:
                self.on_command('show' if chosen == 1 else 'exit')
            self.user.PostMessageW(self.hwnd, 0, 0, 0)
        finally:
            self.user.DestroyMenu(menu)

    def _window_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == self._taskbar_created:
                self._add_icon()
                return 0
            if message == CALLBACK_MESSAGE:
                event = lparam & 0xffff  # NOTIFYICON_VERSION_4 packs the event here.
                if event in (0x400, 0x401, 0x203):  # select, keyboard-select, double click
                    self.on_command('show')
                elif event == 0x7b:  # WM_CONTEXTMENU
                    self._menu()
                return 0
            if message == UPDATE_MESSAGE:
                data = self._data()
                if not self.shell.Shell_NotifyIconW(1, ctypes.byref(data)):
                    self._add_icon()
                return 0
            if message == WM_CLOSE:
                self.user.DestroyWindow(hwnd)
                return 0
            if message == 0x0002:  # WM_DESTROY
                self.user.PostQuitMessage(0)
                return 0
        except Exception:
            logger.exception('托盘操作失败')
            self.on_command('unavailable')
        return self.user.DefWindowProcW(hwnd, message, wparam, lparam)

    def _run(self):
        name = 'AntigravityLauncherTray-' + uuid.uuid4().hex
        module = self.kernel.GetModuleHandleW(None)
        registered = False
        try:
            self._taskbar_created = self.user.RegisterWindowMessageW('TaskbarCreated')
            self._callback = WNDPROC(self._window_proc)
            window_class = WindowClass(lpfnWndProc=self._callback, hInstance=module, lpszClassName=name)
            if not self.user.RegisterClassW(ctypes.byref(window_class)):
                raise ctypes.WinError(ctypes.get_last_error())
            registered = True
            self.hwnd = self.user.CreateWindowExW(0, name, 'AntigravityLauncherTray', 0, 0, 0, 0, 0,
                                                  None, None, module, None)
            if not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            self._icon = self.user.LoadImageW(None, self.icon_path, 1, 32, 32, 0x10)
            if not self._icon:
                raise ctypes.WinError(ctypes.get_last_error())
            self._add_icon()
            self._ready.set()
            message = w.MSG()
            while not self._stop.is_set():
                result = self.user.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    if result < 0: raise ctypes.WinError(ctypes.get_last_error())
                    break
                self.user.TranslateMessage(ctypes.byref(message))
                self.user.DispatchMessageW(ctypes.byref(message))
        except Exception as exc:
            self._error = exc
            logger.exception('托盘初始化或消息循环失败')
            self.on_command('unavailable')
        finally:
            if self.hwnd:
                data = self._data()
                self.shell.Shell_NotifyIconW(2, ctypes.byref(data))
                self.user.DestroyWindow(self.hwnd)
            if self._icon:
                self.user.DestroyIcon(self._icon)
            if registered:
                self.user.UnregisterClassW(name, module)
            self.available = False
            self.hwnd = self._icon = None
            self._ready.set()

    def update(self, text):
        self._tip = f'Antigravity 启动器 · {text}'[:127]
        if self.hwnd:
            self.user.PostMessageW(self.hwnd, UPDATE_MESSAGE, 0, 0)

    def close(self):
        self._stop.set()
        if self.hwnd:
            self.user.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)
