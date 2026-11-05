"""Antigravity launcher: GUI and silent mode share one user-owned controller."""
import argparse
import os
from pathlib import Path
import queue
import sys


def main():
    parser = argparse.ArgumentParser(description="Antigravity Launcher")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--silent-launch", action="store_true")
    group.add_argument("--create-shortcut", action="store_true")
    args = parser.parse_args()
    try:
        from core.config_manager import ConfigManager
        from core.diagnostics import configure_logging
        from core.shortcut_helper import create_all_desktop_shortcuts
        from core.single_instance import SingleInstance
        from ui.main_window import MainWindow
    except ImportError as exc:
        message = f"缺少运行依赖: {exc}\n请运行 .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        if sys.stderr:
            print(message, file=sys.stderr)
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "Antigravity Launcher", 0x10)
        return 1
    configure_logging()
    if os.name == "nt":
        import ctypes
        # Keep taskbar grouping and icons distinct from other Python applications.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AntigravityLauncher.Desktop")
    config = ConfigManager()
    if args.create_shortcut:
        ok, messages = create_all_desktop_shortcuts(config.get("app_path", ""))
        if sys.stdout:
            for message in messages:
                print(message)
        return 0 if ok else 1

    events = queue.Queue()
    bindings = []
    window = None
    def dispatch(command):
        if command == "status":
            from dataclasses import asdict
            return asdict(window.launcher.status()) if window else {"status": "initializing"}
        events.put(("ipc", command))
        return "queued"

    def bind(path, initial=False):
        canonical = os.path.normcase(os.path.realpath(path or str(Path(__file__).parent)))
        if bindings and bindings[-1][0] == canonical:
            return True
        candidate = SingleInstance(canonical, dispatch)
        if not candidate.acquire():
            candidate.send("start" if initial and args.silent_launch else "show")
            candidate.close()
            return False
        # Keep the previous binding until the prior app has stopped; this prevents
        # another launcher from managing that app during a path-changing restart.
        bindings.append((canonical, candidate))
        return True

    def release():
        for _, instance in bindings:
            instance.close()
        bindings.clear()

    def applied(path):
        canonical = os.path.normcase(os.path.realpath(path))
        for key, instance in list(bindings):
            if key != canonical:
                instance.close()
                bindings.remove((key, instance))

    try:
        if not bind(config.get("app_path", ""), initial=True):
            return 0
        window = MainWindow(config, events=events, hidden=args.silent_launch,
                            ensure_instance=bind, on_exit=release, on_applied=applied)
        window.mainloop()
        return 0
    except Exception as exc:
        import logging
        logging.getLogger("antigravity_launcher").exception("启动器入口失败")
        from tkinter import messagebox
        from core.proxy_checker import redact
        messagebox.showerror("启动器错误", redact(exc))
        return 1
    finally:
        if window:
            window.launcher.stop_monitoring()
        release()


if __name__ == "__main__":
    sys.exit(main())
