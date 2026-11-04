#!/usr/bin/env python3
"""Main entry point for Antigravity Launcher."""

import argparse
import sys
import time

from core.app_launcher import AntigravityLauncher
from core.config_manager import ConfigManager
from ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="Antigravity Launcher & Localization Manager")
    parser.add_argument(
        "--silent-launch",
        action="store_true",
        help="Launch Antigravity directly using saved configuration without opening GUI window",
    )
    args = parser.parse_args()

    config_mgr = ConfigManager()

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
            # Keep injector alive if localization is enabled
            if config_mgr.get("enable_hans", True) and launcher.injector:
                try:
                    while launcher.process and launcher.process.poll() is None:
                        time.sleep(1.0)
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
