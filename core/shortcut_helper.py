"""Shortcut creation helper for Antigravity Launcher."""

import os
import subprocess
import sys
from typing import Optional, Tuple


def get_pythonw_path() -> str:
    """Find pythonw.exe corresponding to current Python executable."""
    py_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(py_dir, "pythonw.exe")
    if os.path.exists(pythonw):
        return pythonw
    return sys.executable


def create_windows_shortcut(
    shortcut_path: str,
    target_path: str,
    arguments: str = "",
    working_dir: str = "",
    icon_location: str = "",
    description: str = "",
) -> Tuple[bool, str]:
    """Create a Windows .lnk shortcut using a temporary PowerShell script."""
    try:
        # Build PowerShell command to create shortcut
        ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut({repr(shortcut_path)})
$Shortcut.TargetPath = {repr(target_path)}
$Shortcut.Arguments = {repr(arguments)}
$Shortcut.WorkingDirectory = {repr(working_dir)}
if ({repr(icon_location)}) {{
    $Shortcut.IconLocation = {repr(icon_location)}
}}
if ({repr(description)}) {{
    $Shortcut.Description = {repr(description)}
}}
$Shortcut.Save()
"""
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode == 0 and os.path.exists(shortcut_path):
            return True, f"成功创建快捷方式: {shortcut_path}"
        return False, f"PowerShell 返回错误: {res.stderr or res.stdout}"
    except Exception as e:
        return False, f"创建快捷方式异常: {e}"


def create_all_desktop_shortcuts(
    app_path: str = "",
    launcher_dir: str = "",
) -> Tuple[bool, list]:
    """Create both .lnk shortcuts and .bat launcher on the user's Desktop."""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.exists(desktop):
        return False, [f"桌面目录不存在: {desktop}"]

    if not launcher_dir:
        launcher_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    launcher_py = os.path.join(launcher_dir, "launcher.py")
    pythonw_exe = get_pythonw_path()

    icon_location = f"{app_path},0" if app_path and os.path.exists(app_path) else ""
    results = []

    # 1. Direct one-click launcher shortcut (.lnk with Antigravity icon)
    silent_lnk = os.path.join(desktop, "Antigravity (汉化代理版).lnk")
    ok1, msg1 = create_windows_shortcut(
        shortcut_path=silent_lnk,
        target_path=pythonw_exe,
        arguments=f'"{launcher_py}" --silent-launch',
        working_dir=launcher_dir,
        icon_location=icon_location,
        description="启动 Antigravity（自动加载网络代理与中文汉化）",
    )
    results.append(msg1)

    # 2. GUI management tool shortcut (.lnk)
    gui_lnk = os.path.join(desktop, "Antigravity 启动管理工具.lnk")
    ok2, msg2 = create_windows_shortcut(
        shortcut_path=gui_lnk,
        target_path=pythonw_exe,
        arguments=f'"{launcher_py}"',
        working_dir=launcher_dir,
        icon_location=icon_location,
        description="Antigravity 启动与汉化管理平台（代理切换与状态监控）",
    )
    results.append(msg2)

    # 3. .bat script on Desktop
    bat_path = os.path.join(desktop, "启动Antigravity(汉化代理版).bat")
    try:
        bat_content = f"""@echo off
chcp 65001 >nul
title Antigravity Launcher
cd /d "{launcher_dir}"
start "" "{pythonw_exe}" "{launcher_py}" --silent-launch
exit /b 0
"""
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        results.append(f"成功创建桌面启动批处理脚本: {bat_path}")
    except Exception as e:
        results.append(f"创建批处理脚本失败: {e}")

    # 4. .vbs silent script in launcher directory
    vbs_path = os.path.join(launcher_dir, "启动Antigravity(无窗口静默版).vbs")
    try:
        vbs_content = f"""Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = "{launcher_dir}"
ws.Run chr(34) & "{pythonw_exe}" & chr(34) & " " & chr(34) & "{launcher_py}" & chr(34) & " --silent-launch", 0, False
"""
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(vbs_content)
        results.append(f"成功创建无窗口静默 VBS 脚本: {vbs_path}")
    except Exception as e:
        results.append(f"创建 VBS 脚本失败: {e}")

    all_ok = ok1 and ok2
    return all_ok, results
