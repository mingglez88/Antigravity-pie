#!/usr/bin/env python3
"""Main entry point for Antigravity Launcher."""

import argparse
import sys
import time

from core.app_launcher import AntigravityLauncher, is_process_running
from core.config_manager import ConfigManager
from core.shortcut_helper import create_all_desktop_shortcuts
from ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="Antigravity Launcher & Localization Manager")
    parser.add_argument(
        "--silent-launch",
        action="store_true",
        help="Launch Antigravity directly using saved configuration without opening GUI window",
    )
    parser.add_argument(
        "--create-shortcut",
        action="store_true",
        help="Generate desktop shortcuts and startup scripts, then exit",
    )
    args = parser.parse_args()

    config_mgr = ConfigManager()

    if args.create_shortcut:
        ok, msgs = create_all_desktop_shortcuts(app_path=config_mgr.get("app_path", ""))
        print("[Shortcut]")
        for m in msgs:
            print(f"  - {m}")
        sys.exit(0 if ok else 1)

    if args.silent_launch:
        # Silent one-click launch from shortcut
        launcher = AntigravityLauncher(config_mgr, on_log=lambda msg: print(msg))
        success, msg = launcher.launch()
        print(f"[Launcher] {msg}")
        if not success:
            # If launch fails, fallback to opening GUI
            app = MainWindow(config_mgr)
            app.append_log(f"[静默启动失败] {msg}，正在打开主界面...")
            app.mainloop()
        else:
            # Keep injector alive while Antigravity is running
            if config_mgr.get("enable_hans", True) and launcher.injector:
                try:
                    time.sleep(2.0)
                    while is_process_running("Antigravity.exe"):
                        time.sleep(1.5)
                except KeyboardInterrupt:
                    pass
                finally:
                    launcher.stop_injector()
        sys.exit(0)

    # Standard interactive GUI mode
    app = MainWindow(config_mgr)
    app.mainloop()


if __name__ == "__main__":
    main()
