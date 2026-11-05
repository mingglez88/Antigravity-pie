"""Shortcut creation helper for Antigravity Launcher."""

import base64
import ctypes
import os
import sys
from typing import Tuple
from uuid import UUID


def get_pythonw_path() -> str:
    """Find pythonw.exe corresponding to current Python executable."""
    project_pythonw = os.path.join(os.path.dirname(__file__), "..", ".venv", "Scripts", "pythonw.exe")
    if os.path.isfile(project_pythonw):
        return os.path.abspath(project_pythonw)
    py_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(py_dir, "pythonw.exe")
    if os.path.isfile(pythonw):
        return pythonw
    return sys.executable


def get_desktop_path() -> str:
    """Resolve the user's desktop, including Windows folder redirection."""
    if sys.platform != "win32":
        raise OSError("桌面快捷方式仅支持 Windows")
    from ctypes import wintypes

    shell32 = ctypes.WinDLL("shell32")
    ole32 = ctypes.WinDLL("ole32")
    get_known_folder = shell32.SHGetKnownFolderPath
    get_known_folder.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    get_known_folder.restype = ctypes.c_long
    free_memory = ole32.CoTaskMemFree
    free_memory.argtypes = [ctypes.c_void_p]
    free_memory.restype = None
    # FOLDERID_Desktop, passed in the native GUID byte order.
    folder_id = ctypes.create_string_buffer(
        UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641").bytes_le
    )
    desktop = wintypes.LPWSTR()
    try:
        result = get_known_folder(folder_id, 0, None, ctypes.byref(desktop))
        if result != 0 or not desktop.value:
            raise OSError(f"无法读取 Windows 桌面目录 (HRESULT: {result})")
        return desktop.value
    finally:
        if desktop:
            free_memory(ctypes.cast(desktop, ctypes.c_void_p))


def _launcher_arguments(launcher_py, silent=False):
    # ShellExecute expands %NAME% even inside quoted .lnk arguments. Encode only
    # the ordinary Python bootstrap so literal paths survive that expansion.
    arguments = [launcher_py] + (["--silent-launch"] if silent else [])
    code = ("import os, runpy, sys\n"
            f"os.chdir({os.path.dirname(launcher_py)!r})\n"
            f"sys.argv = {arguments!r}\n"
            f"runpy.run_path({launcher_py!r}, run_name='__main__')\n")
    payload = base64.b64encode(code.encode("utf-8")).decode("ascii")
    return f'-c "import base64;exec(base64.b64decode(\'{payload}\'))"'


def create_windows_shortcut(
    shortcut_path: str,
    target_path: str,
    arguments: str = "",
    working_dir: str = "",
    icon_location: str = "",
    description: str = "",
) -> Tuple[bool, str]:
    """Save and reload Unicode .lnk fields via IShellLinkW/IPersistFile."""
    if sys.platform != "win32":
        return False, "桌面快捷方式仅支持 Windows"
    try:
        from core.windows_shortcut import save_verified_shortcut
        shortcut_path = os.path.abspath(shortcut_path)
        target_path = os.path.abspath(target_path)
        working_dir = os.path.abspath(working_dir) if working_dir else ""
        save_verified_shortcut(shortcut_path, target_path, arguments, working_dir, icon_location, description)
        if not os.path.isfile(shortcut_path):
            raise OSError("快捷方式文件未生成")
        return True, f"成功创建快捷方式: {shortcut_path}"
    except Exception as exc:
        return False, f"创建或校验快捷方式失败: {exc}"



def create_all_desktop_shortcuts(
    app_path: str = "",
    launcher_dir: str = "",
) -> Tuple[bool, list]:
    """Create both .lnk shortcuts and .bat launcher on the user's Desktop."""
    try:
        desktop = get_desktop_path()
    except OSError as e:
        return False, [str(e)]
    if not os.path.isdir(desktop):
        return False, [f"桌面目录不存在: {desktop}"]

    if not launcher_dir:
        launcher_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    launcher_dir = os.path.abspath(launcher_dir)
    launcher_py = os.path.join(launcher_dir, "launcher.py")
    pythonw_exe = get_pythonw_path()
    silent_arguments = _launcher_arguments(launcher_py, silent=True)
    gui_arguments = _launcher_arguments(launcher_py)
    shell_directory = os.path.dirname(pythonw_exe)
    for required_path in (launcher_py, pythonw_exe):
        if not os.path.isfile(required_path):
            return False, [f"启动所需文件不存在: {required_path}"]

    icon_location = f"{os.path.abspath(app_path)},0" if app_path and os.path.isfile(app_path) else ""
    manager_icon = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "launcher-icon.ico"))
    manager_icon_location = f"{manager_icon},0" if os.path.isfile(manager_icon) else icon_location
    results = []
    statuses = []

    # 1. Direct one-click launcher shortcut (.lnk with Antigravity icon)
    silent_lnk = os.path.join(desktop, "Antigravity (汉化代理版).lnk")
    ok1, msg1 = create_windows_shortcut(
        shortcut_path=silent_lnk,
        target_path=pythonw_exe,
        arguments=silent_arguments,
        working_dir=shell_directory,
        icon_location=icon_location,
        description="启动 Antigravity（自动加载网络代理与中文汉化）",
    )
    results.append(msg1)
    statuses.append(ok1)

    # 2. GUI management tool shortcut (.lnk)
    gui_lnk = os.path.join(desktop, "Antigravity 启动管理工具.lnk")
    ok2, msg2 = create_windows_shortcut(
        shortcut_path=gui_lnk,
        target_path=pythonw_exe,
        arguments=gui_arguments,
        working_dir=shell_directory,
        icon_location=manager_icon_location,
        description="Antigravity 启动与汉化管理平台（代理切换与状态监控）",
    )
    results.append(msg2)
    statuses.append(ok2)

    # 3. .bat script on Desktop
    bat_path = os.path.join(desktop, "启动Antigravity(汉化代理版).bat")
    try:
        # Percent signs expand even in quoted cmd.exe arguments; exclamation
        # marks are preserved by disabling delayed expansion in the script.
        bat_dir = launcher_dir.replace("%", "%%")
        bat_python = pythonw_exe.replace("%", "%%")
        bat_launcher = launcher_py.replace("%", "%%")
        bat_content = f"""@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
title Antigravity Launcher
cd /d "{bat_dir}"
if errorlevel 1 goto failed
if not exist "{bat_python}" goto failed
if not exist "{bat_launcher}" goto failed
start "" "{bat_python}" {silent_arguments}
if errorlevel 1 goto failed
exit /b 0
:failed
echo [ERROR] Unable to start Antigravity Launcher. Check its location and Python installation.
pause
exit /b 1
"""
        with open(bat_path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(bat_content)
        statuses.append(True)
        results.append(f"成功创建桌面启动批处理脚本: {bat_path}")
    except Exception as e:
        statuses.append(False)
        results.append(f"创建批处理脚本失败: {e}")

    # 4. .vbs silent script in launcher directory
    vbs_path = os.path.join(launcher_dir, "启动Antigravity(无窗口静默版).vbs")
    try:
        vbs_python = pythonw_exe.replace('"', '""')
        vbs_arguments = silent_arguments.replace('"', '""')
        vbs_dir = shell_directory.replace('"', '""')
        vbs_content = f"""Option Explicit
Dim shell
Set shell = CreateObject("Shell.Application")
On Error Resume Next
shell.ShellExecute "{vbs_python}", "{vbs_arguments}", "{vbs_dir}", "open", 0
If Err.Number <> 0 Then
    WScript.Echo "Unable to start Antigravity Launcher: " & Err.Description
    WScript.Quit 1
End If
"""
        # Windows Script Host supports UTF-16 with a BOM, but not UTF-8 VBS.
        with open(vbs_path, "w", encoding="utf-16", newline="\r\n") as f:
            f.write(vbs_content)
        statuses.append(True)
        results.append(f"成功创建无窗口静默 VBS 脚本: {vbs_path}")
    except Exception as e:
        statuses.append(False)
        results.append(f"创建 VBS 脚本失败: {e}")

    return all(statuses), results
