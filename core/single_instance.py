"""Current-user Windows mutex and bounded JSON named-pipe messages."""
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
import threading
import time

MAX_MESSAGE = 4096
COMMANDS = {"show", "start", "restart", "status", "stop_monitoring"}


def decode_message(data):
    if len(data) > MAX_MESSAGE:
        raise ValueError("IPC message too large")
    message = json.loads(data.decode("utf-8"))
    if not isinstance(message, dict) or message.get("version") != 1 or message.get("command") not in COMMANDS:
        raise ValueError("Unsupported IPC message")
    return message["command"]


class SecurityAttributes(ctypes.Structure):
    _fields_ = [("nLength", w.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p), ("bInheritHandle", w.BOOL)]


class SingleInstance:
    def __init__(self, app_path, on_command):
        if os.name != "nt":
            raise OSError("单实例控制需要 Windows")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        self._declare()
        self.sid = self._user_sid()
        digest = hashlib.sha256((self.sid + os.path.normcase(os.path.realpath(app_path))).encode()).hexdigest()[:32]
        self.name = "AntigravityLauncher-" + digest
        self.address = "\\\\.\\pipe\\" + self.name
        self.on_command = on_command
        self._mutex = None
        self._pipe = None
        self._thread = None
        self._stop = threading.Event()

    def _declare(self):
        specs = {
            "CreateMutexW": ([ctypes.POINTER(SecurityAttributes), w.BOOL, w.LPCWSTR], w.HANDLE),
            "CreateNamedPipeW": ([w.LPCWSTR, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, ctypes.POINTER(SecurityAttributes)], w.HANDLE),
            "ConnectNamedPipe": ([w.HANDLE, ctypes.c_void_p], w.BOOL),
            "DisconnectNamedPipe": ([w.HANDLE], w.BOOL),
            "ReadFile": ([w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p], w.BOOL),
            "WriteFile": ([w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p], w.BOOL),
            "CreateFileW": ([w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE], w.HANDLE),
            "SetNamedPipeHandleState": ([w.HANDLE, ctypes.POINTER(w.DWORD), ctypes.c_void_p, ctypes.c_void_p], w.BOOL),
            "CloseHandle": ([w.HANDLE], w.BOOL), "LocalFree": ([ctypes.c_void_p], ctypes.c_void_p),
            "GetCurrentProcess": ([], w.HANDLE),
        }
        for name, (args, result) in specs.items():
            fn = getattr(self.kernel, name); fn.argtypes = args; fn.restype = result
        self.advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
        self.advapi.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
        self.advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)]
        self.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]

    def _user_sid(self):
        token = w.HANDLE()
        if not self.advapi.OpenProcessToken(self.kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            size = w.DWORD()
            self.advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            if not self.advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
            text = w.LPWSTR()
            if not self.advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                return text.value
            finally:
                self.kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))
        finally:
            self.kernel.CloseHandle(token)

    def acquire(self):
        descriptor = ctypes.c_void_p()
        if not self.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                f"D:P(A;;GA;;;{self.sid})", 1, ctypes.byref(descriptor), None):
            raise ctypes.WinError(ctypes.get_last_error())
        attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
        try:
            handle = self.kernel.CreateMutexW(ctypes.byref(attributes), False, "Local\\" + self.name)
            error = ctypes.get_last_error()
            if not handle:
                raise ctypes.WinError(error)
            if error == 183:
                self.kernel.CloseHandle(handle)
                return False
            self._mutex = handle
            # Duplex, first instance; message mode, nonblocking, reject remote clients.
            self._pipe = self.kernel.CreateNamedPipeW(self.address, 3 | 0x80000, 4 | 2 | 1 | 8,
                                                     1, MAX_MESSAGE, MAX_MESSAGE, 0, ctypes.byref(attributes))
            if self._pipe == ctypes.c_void_p(-1).value:
                self._pipe = None
                raise ctypes.WinError(ctypes.get_last_error())
            self._thread = threading.Thread(target=self._serve, name="launcher-ipc", daemon=True)
            self._thread.start()
            return True
        except Exception:
            self.close()
            raise
        finally:
            self.kernel.LocalFree(descriptor)

    def _read(self, handle):
        buffer = ctypes.create_string_buffer(MAX_MESSAGE)
        count = w.DWORD()
        if self.kernel.ReadFile(handle, buffer, MAX_MESSAGE, ctypes.byref(count), None):
            return buffer.raw[:count.value]
        error = ctypes.get_last_error()
        if error in (232, 536):
            return None
        raise ctypes.WinError(error)

    def _write(self, handle, payload):
        count = w.DWORD()
        if not self.kernel.WriteFile(handle, payload, len(payload), ctypes.byref(count), None) or count.value != len(payload):
            raise ctypes.WinError(ctypes.get_last_error())

    def _serve(self):
        while not self._stop.is_set():
            connected = self.kernel.ConnectNamedPipe(self._pipe, None)
            if not connected and ctypes.get_last_error() not in (535, 0):
                self._stop.wait(0.05)
                continue
            deadline = time.monotonic() + 2
            try:
                while not self._stop.is_set() and time.monotonic() < deadline:
                    data = self._read(self._pipe)
                    if data:
                        command = decode_message(data)
                        result = self.on_command(command)
                        payload = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode("utf8")
                        self._write(self._pipe, payload[:MAX_MESSAGE])
                        # Wait for client to read and close before disconnecting.
                        while not self._stop.wait(0.02) and time.monotonic() < deadline:
                            self._read(self._pipe)
                        break
                    self._stop.wait(0.02)
            except (OSError, ValueError, TypeError):
                pass
            finally:
                self.kernel.DisconnectNamedPipe(self._pipe)

    def send(self, command, timeout=4.0):
        payload = json.dumps({"version": 1, "command": command}).encode()
        decode_message(payload)
        deadline = time.monotonic() + timeout
        handle = None
        while time.monotonic() < deadline:
            handle = self.kernel.CreateFileW(self.address, 0xC0000000, 0, None, 3, 0, None)
            if handle != ctypes.c_void_p(-1).value:
                break
            time.sleep(0.05)
        else:
            raise TimeoutError("已有启动器尚未响应，请稍后重试")
        try:
            mode = w.DWORD(2 | 1)
            if not self.kernel.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None):
                raise ctypes.WinError(ctypes.get_last_error())
            self._write(handle, payload)
            while time.monotonic() < deadline:
                data = self._read(handle)
                if data:
                    return json.loads(data.decode('utf8'))
                time.sleep(0.02)
            raise TimeoutError("已有启动器响应超时")
        finally:
            self.kernel.CloseHandle(handle)

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        for handle in (self._pipe, self._mutex):
            if handle:
                self.kernel.CloseHandle(handle)
        self._pipe = self._mutex = None
