"""Modern Tkinter GUI for Antigravity Launcher."""

import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from core.app_launcher import AntigravityLauncher, is_process_running, terminate_running_instances
from core.config_manager import ConfigManager
from core.proxy_checker import check_proxy_http


class MainWindow(tk.Tk):
    """Main launcher interface."""

    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.launcher = AntigravityLauncher(config_manager, on_log=self.append_log)

        self.title("Antigravity 启动与汉化管理工具")
        self.geometry("720x680")
        self.minsize(650, 600)

        # Style configuration
        self._init_style()

        # Build UI layout
        self._create_widgets()

        # Load initial values
        self._load_from_config()

        # Initial check
        self._update_app_status()

    def _init_style(self) -> None:
        """Configure ttk styling."""
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Color palette
        self.colors = {
            "bg": "#f8f9fa",
            "card_bg": "#ffffff",
            "primary": "#1a73e8",
            "primary_active": "#1557b0",
            "success": "#1e8e3e",
            "danger": "#d93025",
            "text": "#202124",
            "secondary_text": "#5f6368",
            "border": "#dadce0",
        }
        self.configure(bg=self.colors["bg"])

        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Card.TFrame", background=self.colors["card_bg"], relief="solid", borderwidth=1)
        style.configure("TLabelframe", background=self.colors["bg"])
        style.configure("TLabelframe.Label", background=self.colors["bg"], foreground=self.colors["text"], font=("Microsoft YaHei UI", 10, "bold"))

        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"], font=("Microsoft YaHei UI", 9))
        style.configure("Secondary.TLabel", background=self.colors["bg"], foreground=self.colors["secondary_text"], font=("Microsoft YaHei UI", 8))
        style.configure("TCheckbutton", background=self.colors["bg"], foreground=self.colors["text"], font=("Microsoft YaHei UI", 9))

        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=8)
        style.configure("Action.TButton", font=("Microsoft YaHei UI", 9), padding=4)

    def _create_widgets(self) -> None:
        """Construct all UI sections."""
        main_container = ttk.Frame(self, padding="15")
        main_container.pack(fill=tk.BOTH, expand=True)

        # 1. Header Banner
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        title_lbl = ttk.Label(
            header_frame,
            text="🚀 Antigravity 启动与汉化管理平台",
            font=("Microsoft YaHei UI", 14, "bold"),
            foreground=self.colors["primary"],
        )
        title_lbl.pack(anchor=tk.W)

        subtitle_lbl = ttk.Label(
            header_frame,
            text="支持一键代理切换/编辑、本地 CDP 动态免杀汉化注入及状态监控",
            style="Secondary.TLabel",
        )
        subtitle_lbl.pack(anchor=tk.W, pady=(2, 0))

        # 2. Application Path Card
        app_box = ttk.LabelFrame(main_container, text="1. 应用程序路径 (Antigravity.exe)", padding="10")
        app_box.pack(fill=tk.X, pady=5)

        app_row = ttk.Frame(app_box)
        app_row.pack(fill=tk.X)

        self.var_app_path = tk.StringVar()
        self.entry_app_path = ttk.Entry(app_row, textvariable=self.var_app_path)
        self.entry_app_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.entry_app_path.bind("<KeyRelease>", lambda e: self._update_app_status())

        btn_browse = ttk.Button(app_row, text="浏览...", style="Action.TButton", command=self._browse_app_path)
        btn_browse.pack(side=tk.LEFT, padx=(0, 5))

        self.lbl_app_status = ttk.Label(app_box, text="", font=("Microsoft YaHei UI", 8))
        self.lbl_app_status.pack(anchor=tk.W, pady=(4, 0))

        # 3. Proxy Settings Card
        proxy_box = ttk.LabelFrame(main_container, text="2. 网络代理配置 (Proxy Settings)", padding="10")
        proxy_box.pack(fill=tk.X, pady=5)

        self.var_enable_proxy = tk.BooleanVar(value=True)
        chk_proxy = ttk.Checkbutton(
            proxy_box,
            text="启用网络代理环境变量 (HTTP_PROXY / HTTPS_PROXY)",
            variable=self.var_enable_proxy,
            command=self._on_proxy_toggle,
        )
        chk_proxy.pack(anchor=tk.W, pady=(0, 6))

        proxy_input_row = ttk.Frame(proxy_box)
        proxy_input_row.pack(fill=tk.X, pady=2)

        ttk.Label(proxy_input_row, text="代理地址:").pack(side=tk.LEFT, padx=(0, 5))

        self.var_current_proxy = tk.StringVar()
        self.combo_proxies = ttk.Combobox(proxy_input_row, textvariable=self.var_current_proxy, width=32)
        self.combo_proxies.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        btn_test = ttk.Button(proxy_input_row, text="⚡ 测试连通", style="Action.TButton", command=self._test_proxy_connection)
        btn_test.pack(side=tk.LEFT, padx=2)

        btn_save_proxy = ttk.Button(proxy_input_row, text="➕ 保存至列表", style="Action.TButton", command=self._add_current_proxy)
        btn_save_proxy.pack(side=tk.LEFT, padx=2)

        btn_del_proxy = ttk.Button(proxy_input_row, text="🗑️ 删除", style="Action.TButton", command=self._delete_current_proxy)
        btn_del_proxy.pack(side=tk.LEFT, padx=2)

        # Proxy test result label
        self.lbl_proxy_test = ttk.Label(proxy_box, text="", style="Secondary.TLabel")
        self.lbl_proxy_test.pack(anchor=tk.W, pady=(3, 2))

        # NO_PROXY Row
        noproxy_row = ttk.Frame(proxy_box)
        noproxy_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(noproxy_row, text="绕过列表 (NO_PROXY):", style="Secondary.TLabel").pack(side=tk.LEFT, padx=(0, 5))
        self.var_no_proxy = tk.StringVar(value="localhost,127.0.0.1,::1")
        entry_noproxy = ttk.Entry(noproxy_row, textvariable=self.var_no_proxy, font=("Consolas", 8))
        entry_noproxy.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 4. Localization Settings Card
        hans_box = ttk.LabelFrame(main_container, text="3. 汉化选项 (Antigravity-Hans 动态方案)", padding="10")
        hans_box.pack(fill=tk.X, pady=5)

        self.var_enable_hans = tk.BooleanVar(value=True)
        chk_hans = ttk.Checkbutton(
            hans_box,
            text="启用界面简体中文汉化 (基于 Chrome DevTools Protocol 动态注入)",
            variable=self.var_enable_hans,
        )
        chk_hans.pack(anchor=tk.W)

        hans_desc = ttk.Label(
            hans_box,
            text="💡 原理说明：在应用启动时开启本地调试端口，通过内存注入汉化脚本。不修改任何原程序文件，火绒/杀毒零报警，且升级后不损坏原程序。",
            style="Secondary.TLabel",
            wraplength=660,
        )
        hans_desc.pack(anchor=tk.W, pady=(4, 0))

        # 5. Launch Buttons Card
        btn_card = ttk.Frame(main_container, padding="8")
        btn_card.pack(fill=tk.X, pady=8)

        self.btn_launch = tk.Button(
            btn_card,
            text="🚀 立即启动 Antigravity",
            font=("Microsoft YaHei UI", 12, "bold"),
            bg=self.colors["primary"],
            fg="white",
            activebackground=self.colors["primary_active"],
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            padx=20,
            pady=8,
            command=self._launch_app,
        )
        self.btn_launch.pack(side=tk.LEFT, padx=(0, 10))

        btn_restart = ttk.Button(btn_card, text="🔄 终止已有进程并重新启动", style="Action.TButton", command=self._restart_app)
        btn_restart.pack(side=tk.LEFT, padx=5)

        btn_shortcut = ttk.Button(btn_card, text="📌 生成桌面快捷方式", style="Action.TButton", command=self._create_desktop_shortcut)
        btn_shortcut.pack(side=tk.LEFT, padx=5)

        btn_save_cfg = ttk.Button(btn_card, text="💾 保存当前配置", style="Action.TButton", command=self._save_to_config)
        btn_save_cfg.pack(side=tk.RIGHT)

        # 6. Log Console
        log_box = ttk.LabelFrame(main_container, text="4. 运行日志与状态输出", padding="6")
        log_box.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        self.txt_log = tk.Text(log_box, wrap="word", height=8, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4")
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_box, orient=tk.VERTICAL, command=self.txt_log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_log.config(yscrollcommand=scrollbar.set)

    def _load_from_config(self) -> None:
        """Load values from config_manager."""
        self.var_app_path.set(self.config_manager.get("app_path", ""))
        self.var_enable_proxy.set(self.config_manager.get("enable_proxy", True))
        self.var_no_proxy.set(self.config_manager.get("no_proxy", "localhost,127.0.0.1,::1"))
        self.var_enable_hans.set(self.config_manager.get("enable_hans", True))

        proxy_list = self.config_manager.get("proxy_list", [])
        self.combo_proxies["values"] = proxy_list
        current_proxy = self.config_manager.get("current_proxy", "")
        if current_proxy:
            self.var_current_proxy.set(current_proxy)
        elif proxy_list:
            self.var_current_proxy.set(proxy_list[0])

        self._on_proxy_toggle()
        self.append_log("[初始化] 配置加载完毕。")

    def _save_to_config(self, show_prompt: bool = True) -> None:
        """Save form state back to config manager."""
        self.config_manager.set("app_path", self.var_app_path.get().strip())
        self.config_manager.set("enable_proxy", self.var_enable_proxy.get())
        self.config_manager.set("current_proxy", self.var_current_proxy.get().strip())
        self.config_manager.set("no_proxy", self.var_no_proxy.get().strip())
        self.config_manager.set("enable_hans", self.var_enable_hans.get())

        if self.config_manager.save():
            self.append_log("[配置] 设置已成功保存至 config.json。")
            if show_prompt:
                messagebox.showinfo("提示", "配置已成功保存！")
        else:
            self.append_log("[错误] 保存配置失败。")

    def _on_proxy_toggle(self) -> None:
        """Enable or disable proxy widgets."""
        state = "normal" if self.var_enable_proxy.get() else "disabled"
        self.combo_proxies.configure(state=state)

    def _update_app_status(self) -> None:
        """Check if selected Antigravity.exe is present."""
        path = self.var_app_path.get().strip()
        if not path:
            self.lbl_app_status.configure(text="⚠️ 请指定 Antigravity.exe 路径", foreground=self.colors["danger"])
        elif os.path.exists(path):
            self.lbl_app_status.configure(text=f"✅ 找到可执行文件 ({path})", foreground=self.colors["success"])
        else:
            self.lbl_app_status.configure(text=f"❌ 文件不存在: {path}", foreground=self.colors["danger"])

    def _browse_app_path(self) -> None:
        """File dialog to choose Antigravity.exe."""
        initial_dir = os.path.dirname(self.var_app_path.get().strip()) or os.environ.get("LOCALAPPDATA", "")
        chosen = filedialog.askopenfilename(
            title="选择 Antigravity.exe",
            initialdir=initial_dir,
            filetypes=[("Antigravity 应用程序", "*.exe"), ("所有文件", "*.*")],
        )
        if chosen:
            self.var_app_path.set(chosen)
            self._update_app_status()
            self._save_to_config(show_prompt=False)

    def _add_current_proxy(self) -> None:
        """Add input proxy to saved list."""
        proxy = self.var_current_proxy.get().strip()
        if not proxy:
            messagebox.showwarning("警告", "代理地址不能为空！")
            return
        self.config_manager.add_proxy(proxy)
        self.combo_proxies["values"] = self.config_manager.get("proxy_list", [])
        self.append_log(f"[代理] 已添加代理地址: {proxy}")
        messagebox.showinfo("成功", f"代理 {proxy} 已添加到快捷列表！")

    def _delete_current_proxy(self) -> None:
        """Remove current proxy from list."""
        proxy = self.var_current_proxy.get().strip()
        if not proxy:
            return
        if messagebox.askyesno("确认", f"确定从保存列表中移除代理 {proxy} 吗？"):
            self.config_manager.remove_proxy(proxy)
            self.combo_proxies["values"] = self.config_manager.get("proxy_list", [])
            self.var_current_proxy.set(self.config_manager.get("current_proxy", ""))
            self.append_log(f"[代理] 已移除代理地址: {proxy}")

    def _test_proxy_connection(self) -> None:
        """Run connectivity check in a separate thread."""
        proxy = self.var_current_proxy.get().strip()
        if not proxy:
            messagebox.showwarning("提示", "请先输入或选择代理地址")
            return

        self.lbl_proxy_test.configure(text="⏳ 正在测试代理连通性及网络延迟...", foreground=self.colors["primary"])
        self.append_log(f"[测试] 开始检测代理连通性: {proxy}")

        def worker():
            success, latency, msg = check_proxy_http(proxy, test_url="https://www.google.com", timeout=4.0)
            if not success:
                # Fallback test with github
                success, latency, msg = check_proxy_http(proxy, test_url="https://github.com", timeout=4.0)

            def update_ui():
                if success:
                    self.lbl_proxy_test.configure(text=f"🟢 {msg}", foreground=self.colors["success"])
                    self.append_log(f"[测试结果] 成功: {msg}")
                else:
                    self.lbl_proxy_test.configure(text=f"🔴 {msg}", foreground=self.colors["danger"])
                    self.append_log(f"[测试结果] 失败: {msg}")

            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _launch_app(self) -> None:
        """Launch Antigravity."""
        self._save_to_config(show_prompt=False)
        self.btn_launch.configure(state="disabled")

        def task():
            success, msg = self.launcher.launch()
            self.after(0, lambda: self.btn_launch.configure(state="normal"))
            if success:
                self.after(0, lambda: messagebox.showinfo("启动成功", f"Antigravity 已成功启动！\n{msg}"))
            else:
                self.after(0, lambda: messagebox.showerror("启动失败", msg))

        threading.Thread(target=task, daemon=True).start()

    def _restart_app(self) -> None:
        """Terminate existing instances and launch cleanly."""
        if messagebox.askyesno("重启确认", "将关闭当前运行的所有 Antigravity 实例并重新启动，是否继续？"):
            self.append_log("[启动器] 正在请求关闭已有的 Antigravity 进程...")
            terminate_running_instances()
            time.sleep(1.0)
            self._launch_app()

    def _create_desktop_shortcut(self) -> None:
        """Generate a one-click launcher shortcut on the user's Desktop."""
        self._save_to_config(show_prompt=False)
        try:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            bat_path = os.path.join(desktop, "启动Antigravity(汉化代理版).bat")
            script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "launcher.py"))
            python_exe = sys.executable

            content = f"""@echo off
chcp 65001 >nul
title Antigravity Launcher
start "" "{python_exe}" "{script_path}" --silent-launch
exit /b 0
"""
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(content)

            self.append_log(f"[快捷方式] 桌面启动脚本已创建: {bat_path}")
            messagebox.showinfo("成功", f"已在桌面创建一键启动脚本：\n{bat_path}\n日常双击即可自动应用配置！")
        except Exception as e:
            self.append_log(f"[错误] 创建桌面快捷方式失败: {e}")
            messagebox.showerror("错误", f"创建快捷方式失败: {e}")

    def append_log(self, text: str) -> None:
        """Add line to log console safely from any thread."""
        def _insert():
            timestamp = time.strftime("%H:%M:%S")
            self.txt_log.insert(tk.END, f"[{timestamp}] {text}\n")
            self.txt_log.see(tk.END)

        self.after(0, _insert)
