"""Modern Tkinter GUI for Antigravity Launcher."""

import os
import sys
import threading
import time
import queue
import logging
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from core.app_launcher import AntigravityLauncher
from core.config_manager import ConfigManager
from core.proxy_checker import check_proxy_http, redact
from core.shortcut_helper import create_all_desktop_shortcuts


class MainWindow(tk.Tk):
    """Main launcher interface."""

    def __init__(self, config_manager: ConfigManager, events=None, hidden=False, ensure_instance=None, on_exit=None, on_applied=None, tray_factory=None):
        super().__init__()
        self.withdraw()
        self.events = events if events is not None else queue.Queue()
        self.hidden = hidden
        self.busy = False
        self.closed = False
        self.exit_when_idle = False
        self.tray = None
        self._pump_job = None
        self._startup_job = None
        self.proxy_generation = 0
        self.ensure_instance = ensure_instance or (lambda path: True)
        self.on_exit = on_exit or (lambda: None)
        self.on_applied = on_applied or (lambda path: None)
        self.config_manager = config_manager
        self.launcher = AntigravityLauncher(config_manager, on_log=self.append_log,
                                           on_state=lambda state: self.events.put(("state", state)))

        self.title("Antigravity 启动与汉化管理工具")
        icon_dir = Path(__file__).resolve().parent.parent / "assets"
        self.iconbitmap(default=str(icon_dir / "launcher-icon.ico"))
        self._brand_icon = tk.PhotoImage(file=str(icon_dir / "launcher-icon-48.png"))
        self.geometry("1040x820")
        self.minsize(940, 700)

        # Style configuration
        self._init_style()

        # Build UI layout
        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._close_panel)
        try:
            if tray_factory is None:
                from ui.tray_icon import TrayIcon
                tray_factory = TrayIcon
            self.tray = tray_factory(icon_dir / "launcher-icon.ico",
                                     lambda command: self.events.put(("tray", command)))
            self.tray.start()
        except Exception as exc:
            self.append_log(f"托盘不可用，管理面板将保持显示: {redact(exc)}")
            if self.tray:
                self.tray.close()
            self.tray = None

        # Load initial values
        self._load_from_config()

        # Initial check
        self._update_app_status()
        self._pump_job = self.after(50, self._pump)
        if not hidden or not self.tray:
            self.show_panel()
        if hidden:
            self._startup_job = self.after(0, lambda: self._launch_app(save=False))

    def _init_style(self):
        self.colors = {"bg": "#f5f5f7", "card_bg": "#ffffff", "primary": "#007aff",
                       "primary_active": "#0069da", "success": "#248a3d", "danger": "#d70015",
                       "text": "#1d1d1f", "secondary_text": "#86868b", "border": "#e5e5ea"}
        self.configure(bg=self.colors["bg"])
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TEntry", padding=8, borderwidth=1, relief="flat",
                        fieldbackground="#f5f5f7", bordercolor="#e5e5ea", lightcolor="#e5e5ea", darkcolor="#e5e5ea")
        style.configure("TCombobox", padding=8, fieldbackground="#f5f5f7",
                        background="#f5f5f7", bordercolor="#e5e5ea", arrowcolor="#86868b")
        style.map("TCombobox", fieldbackground=[("disabled", "#f5f5f7")])
        style.configure("Vertical.TScrollbar", background="#d1d1d6", troughcolor="#f5f5f7",
                        borderwidth=0, arrowsize=12)

    def _create_widgets(self):
        from ui.components import Card, PillButton, Toggle
        bg = self.colors["bg"]
        self.status_text = tk.StringVar(value="等待启动")
        shell = tk.Frame(self, bg=bg)
        shell.pack(fill=tk.BOTH, expand=True)
        sidebar = tk.Frame(shell, bg="#ececf0", width=180)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        logo = tk.Canvas(sidebar, width=48, height=48, bg="#ececf0", highlightthickness=0)
        logo.pack(anchor="w", padx=24, pady=(28, 10))
        logo.create_image(24, 24, image=self._brand_icon)
        tk.Label(sidebar, text="Antigravity", bg="#ececf0", fg="#1d1d1f",
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=24)
        tk.Label(sidebar, text="LAUNCHER", bg="#ececf0", fg="#8e8e93",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=25, pady=(2, 34))
        nav = tk.Frame(sidebar, bg="#ececf0")
        nav.pack(fill=tk.X, padx=14)
        PillButton(nav, text="启动台", primary=True, width=150,
                   command=lambda: self.content_canvas.yview_moveto(0)).pack(fill=tk.X, pady=5)
        PillButton(nav, text="运行记录", width=150,
                   command=lambda: self.content_canvas.yview_moveto(1)).pack(fill=tk.X, pady=5)
        footer = tk.Frame(sidebar, bg="#ececf0")
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=23, pady=26)
        tk.Label(footer, text="轻一点，专注一点。", bg="#ececf0", fg="#636366",
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        tk.Label(footer, text="代理 · 中文界面 · 后台守护", bg="#ececf0", fg="#8e8e93",
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(8, 0))

        pane = tk.Frame(shell, bg=bg)
        pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.content_canvas = tk.Canvas(pane, bg=bg, highlightthickness=0)
        scroll = ttk.Scrollbar(pane, orient="vertical", command=self.content_canvas.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 3))
        self.content_canvas.pack(fill=tk.BOTH, expand=True)
        self.content_canvas.configure(yscrollcommand=scroll.set)
        content = tk.Frame(self.content_canvas, bg=bg)
        window = self.content_canvas.create_window(0, 0, window=content, anchor="nw")
        content.bind("<Configure>", lambda e: self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all")))
        self.content_canvas.bind("<Configure>", lambda e: self.content_canvas.itemconfigure(window, width=e.width))
        def wheel(event):
            self.content_canvas.yview_scroll(int(-event.delta / 120), "units")
        self.bind("<MouseWheel>", wheel)

        header = tk.Frame(content, bg=bg)
        header.pack(fill=tk.X, padx=28, pady=(26, 18))
        title = tk.Frame(header, bg=bg)
        title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(title, text="准备好，开始创造。", font=("Microsoft YaHei UI", 22, "bold"),
                 bg=bg, fg="#1d1d1f").pack(anchor="w")
        tk.Label(title, text="让连接与语言，回到顺手的状态。", font=("Microsoft YaHei UI", 10),
                 bg=bg, fg="#86868b").pack(anchor="w", pady=(6, 0))
        self.btn_launch = PillButton(header, text="启动 Antigravity", primary=True, width=174, command=self._launch_app)
        self.btn_launch.pack(side=tk.RIGHT, padx=(14, 0), pady=8)

        status = tk.Frame(content, bg=bg)
        status.pack(fill=tk.X, padx=30, pady=(0, 14))
        self.lbl_state_dot = tk.Label(status, text="●", fg="#8e8e93", bg=bg, font=("Segoe UI", 10))
        self.lbl_state_dot.pack(side=tk.LEFT)
        tk.Label(status, textvariable=self.status_text, fg="#636366", bg=bg,
                 font=("Microsoft YaHei UI", 9), wraplength=620, justify="left").pack(side=tk.LEFT, padx=8)

        def card(title_text, subtitle=None):
            box = Card(content)
            box.pack(fill=tk.X, padx=28, pady=6)
            head = tk.Frame(box.body, bg="white")
            head.pack(fill=tk.X, pady=(0, 12))
            label = tk.Frame(head, bg="white")
            label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(label, text=title_text, bg="white", fg="#1d1d1f",
                     font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
            if subtitle:
                tk.Label(label, text=subtitle, bg="white", fg="#86868b",
                         font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(4, 0))
            return box.body, head

        app, app_head = card("应用", "选择本机的 Antigravity")
        row = tk.Frame(app, bg="white")
        row.pack(fill=tk.X)
        self.var_app_path = tk.StringVar()
        self.entry_app_path = ttk.Entry(row, textvariable=self.var_app_path, font=("Segoe UI", 10))
        self.entry_app_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.entry_app_path.bind("<KeyRelease>", lambda e: self._update_app_status())
        PillButton(row, text="选择…", width=80, command=self._browse_app_path).pack(side=tk.RIGHT)
        self.lbl_app_status = tk.Label(app, bg="white", fg="#86868b", font=("Microsoft YaHei UI", 8))
        self.lbl_app_status.pack(anchor="w", pady=(8, 0))

        proxy, proxy_head = card("网络连接", "让应用通过你选择的代理连接")
        self.var_enable_proxy = tk.BooleanVar(value=True)
        Toggle(proxy_head, self.var_enable_proxy, self._on_proxy_toggle).pack(side=tk.RIGHT)
        row = tk.Frame(proxy, bg="white")
        row.pack(fill=tk.X)
        self.var_current_proxy = tk.StringVar()
        self.combo_proxies = ttk.Combobox(row, textvariable=self.var_current_proxy, font=("Consolas", 10))
        self.combo_proxies.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        PillButton(row, text="测试连接", width=100, command=self._test_proxy_connection).pack(side=tk.RIGHT)
        lower = tk.Frame(proxy, bg="white")
        lower.pack(fill=tk.X, pady=(8, 0))
        self.lbl_proxy_test = tk.Label(lower, text="支持 HTTP、HTTPS 与 SOCKS5", bg="white",
                                      fg="#86868b", font=("Microsoft YaHei UI", 8), wraplength=420, justify="left", anchor="w")
        self.lbl_proxy_test.pack(side=tk.LEFT, fill=tk.X, expand=True)
        PillButton(lower, text="添加到列表", width=98, command=self._add_current_proxy).pack(side=tk.LEFT, padx=3)
        PillButton(lower, text="移除", width=62, command=self._delete_current_proxy).pack(side=tk.RIGHT)
        bypass = tk.Frame(proxy, bg="white")
        bypass.pack(fill=tk.X, pady=(10, 0))
        tk.Label(bypass, text="直连地址", bg="white", fg="#86868b", font=("Microsoft YaHei UI", 8)).pack(side=tk.LEFT, padx=(0, 12))
        self.var_no_proxy = tk.StringVar()
        ttk.Entry(bypass, textvariable=self.var_no_proxy, font=("Consolas", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True)

        hans, hans_head = card("中文界面", "启动后收起到系统托盘，仍会在后台保持汉化")
        self.var_enable_hans = tk.BooleanVar(value=True)
        Toggle(hans_head, self.var_enable_hans).pack(side=tk.RIGHT)
        port_row = tk.Frame(hans, bg="white")
        port_row.pack(fill=tk.X)
        tk.Label(port_row, text="本地调试端口", bg="white", fg="#86868b", font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)
        self.var_debug_port = tk.StringVar()
        ttk.Entry(port_row, textvariable=self.var_debug_port, width=8, font=("Consolas", 9)).pack(side=tk.RIGHT)

        actions = tk.Frame(content, bg=bg)
        actions.pack(fill=tk.X, padx=28, pady=(12, 8))
        self.btn_restart = PillButton(actions, text="重新启动", width=110, command=self._restart_app)
        self.btn_restart.pack(side=tk.LEFT)
        PillButton(actions, text="创建快捷方式", width=130, command=self._create_desktop_shortcut).pack(side=tk.LEFT, padx=8)
        PillButton(actions, text="保存设置", width=110, command=self._save_to_config).pack(side=tk.RIGHT)

        logs, _ = card("运行记录", "连接与启动的进展，都在这里")
        self.txt_log = tk.Text(logs, height=5, wrap="word", font=("Consolas", 9),
                               bg="#fafafa", fg="#636366", relief="flat", padx=10, pady=10,
                               highlightthickness=0, insertbackground="#007aff")
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        tk.Label(content, text="配置保存后，点击启动应用。需要重启时会先尝试正常关闭。", bg=bg,
                 fg="#86868b", font=("Microsoft YaHei UI", 8)).pack(pady=(8, 22))


    def _load_from_config(self):
        for name, var in (("app_path", self.var_app_path), ("current_proxy", self.var_current_proxy),
                          ("no_proxy", self.var_no_proxy), ("debugging_port", self.var_debug_port)):
            value = self.config_manager.get(name, self.config_manager.defaults[name])
            var.set(value if isinstance(value, (str, int)) else self.config_manager.defaults[name])
        for name, var in (("enable_proxy", self.var_enable_proxy), ("enable_hans", self.var_enable_hans)):
            value = self.config_manager.get(name, True)
            var.set(value if type(value) is bool else True)
        proxies = self.config_manager.get("proxy_list", [])
        self.combo_proxies["values"] = proxies if isinstance(proxies, list) else []
        self._on_proxy_toggle()
        self.append_log(self.config_manager.load_error or "配置已加载；保存配置后点击启动以应用。")

    def _save_to_config(self, show_prompt=True):
        try:
            updates = {
                "app_path": self.var_app_path.get().strip(),
                "current_proxy": self.var_current_proxy.get().strip(),
                "enable_proxy": self.var_enable_proxy.get(),
                "enable_hans": self.var_enable_hans.get(),
                "no_proxy": self.var_no_proxy.get().strip(),
                "debugging_port": int(self.var_debug_port.get()),
            }
            if not self.config_manager.save(updates):
                raise ValueError(self.config_manager.last_error)
            self.launcher.configuration_saved()
            self.append_log("配置已保存；如与运行中配置不同，下次点击启动时自动正常重启。")
            if show_prompt:
                messagebox.showinfo("配置", "配置已保存。点击启动以应用。")
            return True
        except (ValueError, TypeError) as exc:
            self.append_log(f"保存失败: {redact(exc)}")
            messagebox.showerror("配置无效", redact(exc))
            return False

    def _on_proxy_toggle(self):
        self.combo_proxies.configure(state="normal" if self.var_enable_proxy.get() else "disabled")

    def _update_app_status(self):
        path = self.var_app_path.get().strip()
        exists = os.path.isfile(path)
        self.lbl_app_status.configure(text="已找到应用文件" if exists else "请选择有效的 Antigravity.exe",
                                      foreground=self.colors["success"] if exists else self.colors["danger"])

    def _browse_app_path(self):
        chosen = filedialog.askopenfilename(title="选择 Antigravity.exe", filetypes=[("应用程序", "*.exe")])
        if chosen:
            self.var_app_path.set(chosen)
            self._update_app_status()

    def _add_current_proxy(self):
        try:
            proxy = self.config_manager.add_proxy(self.var_current_proxy.get())
            self.var_current_proxy.set(proxy)
            self.combo_proxies["values"] = self.config_manager.get("proxy_list")
            self.append_log("代理已添加到列表")
        except ValueError as exc:
            messagebox.showerror("代理配置", redact(exc))

    def _delete_current_proxy(self):
        try:
            self.config_manager.remove_proxy(self.var_current_proxy.get())
            self.combo_proxies["values"] = self.config_manager.get("proxy_list")
            self.var_current_proxy.set(self.config_manager.get("current_proxy"))
            self.var_enable_proxy.set(self.config_manager.get("enable_proxy"))
            self.launcher.configuration_saved()
        except ValueError as exc:
            messagebox.showerror("代理配置", redact(exc))

    def _test_proxy_connection(self):
        self.proxy_generation += 1
        generation = self.proxy_generation
        proxy = self.var_current_proxy.get().strip()
        self.lbl_proxy_test.configure(text="正在检测代理请求…")
        def worker():
            result = check_proxy_http(proxy)
            def done():
                if generation != self.proxy_generation or proxy != self.var_current_proxy.get().strip():
                    return
                self.lbl_proxy_test.configure(text=result[2], foreground=self.colors["success" if result[0] else "danger"])
                self.append_log(result[2])
            self.events.put(("callback", done))
        threading.Thread(target=worker, name="proxy-check", daemon=True).start()

    def _launch_app(self, save=True, restart=False):
        if self.busy or (save and not self._save_to_config(False)):
            return
        try:
            settings = self.config_manager.snapshot()
            if not self.ensure_instance(settings.app_path):
                return
        except Exception as exc:
            self.show_panel()
            self.append_log(redact(exc))
            messagebox.showerror("无法启动", redact(exc))
            return
        self.busy = True
        self.btn_launch.configure(state="disabled")
        self.btn_restart.configure(state="disabled")
        def worker():
            try:
                result = self.launcher.restart() if restart else self.launcher.start()
                self.events.put(("finished", result))
            except Exception as exc:
                self.append_log(redact(exc))
                self.events.put(("finished", None))
        threading.Thread(target=worker, name="launcher-operation", daemon=True).start()

    def _restart_app(self):
        self._launch_app(restart=True)

    def _create_desktop_shortcut(self):
        if not self._save_to_config(False):
            return
        app_path = self.config_manager.get("app_path")
        def worker():
            ok, messages = create_all_desktop_shortcuts(app_path=app_path)
            def done():
                for message in messages:
                    self.append_log(message)
                (messagebox.showinfo if ok else messagebox.showwarning)("快捷方式", "\n".join(messages))
            self.events.put(("callback", done))
        threading.Thread(target=worker, name="shortcut-create", daemon=True).start()

    def append_log(self, text):
        safe = redact(text)
        logging.getLogger("antigravity_launcher.ui").info(safe)
        self.events.put(("log", safe))

    def show_panel(self):
        self.hidden = False
        self.deiconify()
        self.lift()
        self.focus_force()

    def _hide_to_tray(self):
        if not self.tray or not self.tray.available:
            self.show_panel()
            self.append_log("托盘图标不可用，已保留管理面板。")
            return False
        self.hidden = True
        self.withdraw()
        return True

    def _close_panel(self):
        state = self.launcher.status()
        if self.busy or (state.pid and state.status != "stopped"):
            self._hide_to_tray()
        else:
            self._exit()

    def _exit(self):
        if self.closed:
            return
        self.closed = True
        for job in (self._pump_job, self._startup_job):
            if job:
                self.after_cancel(job)
        try:
            self.launcher.stop_monitoring()
        finally:
            if self.tray:
                self.tray.close()
            self.on_exit()
            self.destroy()

    def _request_exit(self):
        if self.busy:
            self.exit_when_idle = True
            self.launcher.stop_monitoring()
        else:
            self._exit()

    def _pump(self):
        if self.closed:
            return
        if self._pump_job:
            self.after_cancel(self._pump_job)
            self._pump_job = None
        for _ in range(200):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.txt_log.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {value}\n")
                if int(self.txt_log.index("end-1c").split(".")[0]) > 1500:
                    self.txt_log.delete("1.0", "200.0")
                self.txt_log.see(tk.END)
            elif kind == "callback":
                value()
            elif kind == "state":
                if self.tray:
                    self.tray.update(value.message)
                self.lbl_state_dot.configure(fg={"ready": "#34c759", "failed": "#ff3b30", "degraded": "#ff9500",
                    "starting": "#007aff", "injecting": "#007aff", "waiting_cdp": "#007aff"}.get(value.status, "#8e8e93"))
                self.status_text.set(value.message + (f" · 已汉化 {value.injected_targets} 页" if value.cdp_ready else "") +
                                     (" · 配置待应用" if value.pending_config else ""))
                if value.status == "stopped" and value.pid is None and self.hidden and not self.busy:
                    self._exit()
                    return
            elif kind == "finished":
                self.busy = False
                if self.exit_when_idle:
                    self._exit()
                    return
                self.btn_launch.configure(state="normal")
                self.btn_restart.configure(state="normal")
                if value and value.status in ("ready", "degraded") and self.launcher.applied:
                    self.on_applied(self.launcher.applied.app_path)
                if value is None or value.status in ("failed", "degraded"):
                    self.show_panel()
                    self.append_log(value.message if value else "启动失败，请查看日志")
                elif value.status == "ready":
                    self._hide_to_tray()
            elif kind == "tray":
                if value == "show":
                    self.show_panel()
                elif value == "exit":
                    self._request_exit()
                    if self.closed: return
                elif value == "unavailable":
                    self.show_panel()
                    self.append_log("系统托盘暂不可用，已恢复管理面板。")
            elif kind == "ipc":
                if value == "show": self.show_panel()
                elif value == "start": self._launch_app(save=False)
                elif value == "restart": self._launch_app(save=False, restart=True)
                elif value == "stop_monitoring":
                    self.launcher.stop_monitoring()
                    if self.hidden: self._exit(); return
        if not self.closed:
            self._pump_job = self.after(50, self._pump)

    def report_callback_exception(self, exc_type, exc_value, tb):
        logging.getLogger("antigravity_launcher.ui").error("界面回调异常", exc_info=(exc_type, exc_value, tb))
        self.append_log(f"操作失败: {redact(exc_value)}")
