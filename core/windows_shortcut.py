"""Unicode Shell Link persistence without Windows Script Host ANSI conversion."""
import ctypes
from ctypes import wintypes as w
import os
from uuid import UUID


class Guid(ctypes.Structure):
    _fields_ = [('Data1', w.DWORD), ('Data2', w.WORD), ('Data3', w.WORD), ('Data4', ctypes.c_ubyte * 8)]


def guid(value):
    return Guid.from_buffer_copy(UUID(value).bytes_le)


def checked(result):
    if result < 0:
        raise OSError(f'Windows Shell Link 返回 HRESULT 0x{result & 0xffffffff:08X}')


def method(pointer, index, *argument_types, result=ctypes.c_long):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *argument_types)(table[index])


def save_verified_shortcut(path, target, arguments='', directory='', icon='', description=''):
    ole = ctypes.WinDLL('ole32', use_last_error=True)
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, w.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(Guid), ctypes.c_void_p, w.DWORD,
                                   ctypes.POINTER(Guid), ctypes.POINTER(ctypes.c_void_p)]
    ole.CoCreateInstance.restype = ctypes.c_long
    initialized = ole.CoInitializeEx(None, 2)
    # RPC_E_CHANGED_MODE means this thread already has another valid COM apartment.
    if initialized < 0 and (initialized & 0xffffffff) != 0x80010106:
        checked(initialized)
    link, persist = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        clsid = guid('00021401-0000-0000-C000-000000000046')
        iid_link = guid('000214F9-0000-0000-C000-000000000046')  # IShellLinkW
        checked(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid_link), ctypes.byref(link)))
        for slot, value in [(20, target), (11, arguments), (9, directory), (7, description)]:
            checked(method(link, slot, w.LPCWSTR)(link, value))
        icon_path, icon_index = icon, 0
        if icon and ',' in icon:
            candidate, suffix = icon.rsplit(',', 1)
            try:
                icon_index = int(suffix)
                icon_path = candidate
            except ValueError:
                pass
        checked(method(link, 17, w.LPCWSTR, ctypes.c_int)(link, icon_path, icon_index))
        iid_file = guid('0000010b-0000-0000-C000-000000000046')  # IPersistFile
        checked(method(link, 0, ctypes.POINTER(Guid), ctypes.POINTER(ctypes.c_void_p))(
            link, ctypes.byref(iid_file), ctypes.byref(persist)))
        checked(method(persist, 6, w.LPCWSTR, w.BOOL)(persist, path, True))
        # Reload from disk rather than trusting the fields we just assigned.
        checked(method(persist, 5, w.LPCWSTR, w.DWORD)(persist, path, 0))
        buffer = ctypes.create_unicode_buffer(32768)
        checked(method(link, 3, w.LPWSTR, ctypes.c_int, ctypes.c_void_p, w.DWORD)(
            link, buffer, len(buffer), None, 4))
        if os.path.normcase(buffer.value) != os.path.normcase(target):
            raise OSError('快捷方式目标回读不一致')
        for slot, expected, is_path in [(10, arguments, False), (8, directory, True), (6, description, False)]:
            checked(method(link, slot, w.LPWSTR, ctypes.c_int)(link, buffer, len(buffer)))
            actual = buffer.value
            if (os.path.normcase(actual) if is_path else actual) != (os.path.normcase(expected) if is_path else expected):
                raise OSError('快捷方式参数、目录或描述回读不一致')
        if icon:
            index = ctypes.c_int()
            checked(method(link, 16, w.LPWSTR, ctypes.c_int, ctypes.POINTER(ctypes.c_int))(
                link, buffer, len(buffer), ctypes.byref(index)))
            if os.path.normcase(buffer.value) != os.path.normcase(icon_path) or index.value != icon_index:
                raise OSError('快捷方式图标回读不一致')
    finally:
        for pointer in (persist, link):
            if pointer:
                method(pointer, 2, result=w.ULONG)(pointer)
        if initialized >= 0:
            ole.CoUninitialize()
