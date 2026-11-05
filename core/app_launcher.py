"""One lifecycle controller for GUI, silent entry and repeated launch requests."""
import logging
import threading
import time
from dataclasses import dataclass, replace

from core.cdp_injector import CDPInjector
from core.process_backend import ProcessBackend, canonical
from core.proxy_checker import build_environment, redact

logger = logging.getLogger("antigravity_launcher.controller")


@dataclass(frozen=True)
class LaunchResult:
    status: str = "idle"
    pid: int | None = None
    cdp_ready: bool = False
    injected_targets: int = 0
    error: str | None = None
    message: str = "等待启动"
    pending_config: bool = False


def effective(settings):
    return (canonical(settings.app_path), settings.enable_proxy,
            settings.current_proxy if settings.enable_proxy else "",
            settings.no_proxy, settings.enable_hans,
            settings.debugging_port if settings.enable_hans else 0)


class AntigravityLauncher:
    def __init__(self, config_manager, on_log=None, on_state=None, backend=None,
                 injector_factory=CDPInjector, startup_timeout=30.0, poll_interval=0.25):
        self.config_manager = config_manager
        self.on_log = on_log or (lambda message: None)
        self.on_state = on_state or (lambda state: None)
        self.backend = backend or ProcessBackend()
        self.injector_factory = injector_factory
        self.startup_timeout = startup_timeout
        self.poll_interval = poll_interval
        self.injector = None
        self.identity = None
        self.applied = None
        self._state = LaunchResult()
        self._lock = threading.RLock()
        self._operation = threading.Lock()
        self._cancel = threading.Event()
        self._monitor = None

    def _publish(self, **changes):
        with self._lock:
            state = replace(self._state, **changes)
            changed = state != self._state
            self._state = state
        if changed:
            logger.info("%s pid=%s pages=%s %s", state.status, state.pid, state.injected_targets, redact(state.message))
            self.on_state(state)
        return state

    def status(self):
        with self._lock:
            return self._state

    def configuration_saved(self):
        try:
            pending = self.applied is not None and effective(self.config_manager.snapshot()) != effective(self.applied)
        except ValueError:
            pending = True
        return self._publish(pending_config=pending)

    def _stop_worker(self):
        self._cancel.set()
        if self.injector:
            self.injector.stop_monitoring()
        if self._monitor and self._monitor is not threading.current_thread():
            self._monitor.join(timeout=8)
            if self._monitor.is_alive():
                raise RuntimeError("汉化监视尚未停止，请稍后再试")
        self._monitor = None
        self.injector = None

    def start(self):
        return self._start(False)

    def restart(self):
        return self._start(True)

    def _start(self, force_restart):
        # A concurrent request observes the ongoing operation; it never queues another restart.
        if not self._operation.acquire(blocking=False):
            return self.status()
        started = time.monotonic()
        operation_started = False
        try:
            settings = self.config_manager.snapshot()
            self._stop_worker()
            self._cancel = threading.Event()
            operation_started = True
            self._publish(status="starting", error=None, message="正在检查应用与配置", injected_targets=0, cdp_ready=False)
            existing = self.backend.find(settings.app_path)
            previous = self.identity
            previous_settings = self.applied
            if previous and self.backend.alive(previous) and canonical(previous.path) != canonical(settings.app_path):
                existing += [previous]
            reuse = (not force_restart and len(existing) == 1 and previous == existing[0] and
                     previous_settings is not None and effective(settings) == effective(previous_settings))
            if reuse and settings.enable_hans:
                self.backend.refresh_connections()
                reuse = self.backend.owns_debug_port(previous, settings.debugging_port)
            if existing and not reuse:
                self.on_log("配置需要重新应用，正在请求应用正常退出（最多等待 10 秒）")
                if not self.backend.close(existing, timeout=10):
                    self.identity = existing[0]
                    self._publish(status="failed", pid=existing[0].pid, pending_config=True,
                                  error="应用未能正常退出，请完成应用内提示后重试", message="重启取消：未强制关闭应用")
                    return self.status()
            if not reuse:
                if settings.enable_hans:
                    self.backend.refresh_connections()
                    if self.backend.listener(settings.debugging_port) is not None:
                        raise RuntimeError(f"调试端口 {settings.debugging_port} 已被其他进程占用")
                env = build_environment(settings.enable_proxy, settings.current_proxy, settings.no_proxy)
                self.identity = self.backend.spawn(settings, env)
                self.applied = None
            deadline = time.monotonic() + self.startup_timeout
            while not self._cancel.is_set():
                if not self.backend.alive(self.identity):
                    candidates = self.backend.find(settings.app_path)
                    self.identity = candidates[0] if candidates else None
                if self.identity:
                    self.applied = settings
                    self._publish(pid=self.identity.pid, pending_config=False)
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("应用进程未能保持运行")
                self._cancel.wait(self.poll_interval)
            if self._cancel.is_set():
                return self._publish(status="stopped", message="启动已取消")
            if settings.enable_hans:
                self.injector = self.injector_factory(port=settings.debugging_port, on_status=self.on_log,
                    port_owner=lambda: self.backend.owns_debug_port(self.identity, settings.debugging_port),
                    target_owner=lambda url: self.backend.owns_page(self.identity, url))
                self._publish(status="waiting_cdp", message="应用已运行，等待汉化接口")
                while time.monotonic() < deadline and not self._cancel.is_set():
                    if not self.backend.alive(self.identity):
                        raise RuntimeError("应用在初始化过程中退出")
                    self.backend.refresh_connections()
                    result = self.injector.scan(deadline=deadline)
                    self._publish(status="injecting" if result.cdp_ready else "waiting_cdp",
                                  cdp_ready=result.cdp_ready, injected_targets=result.injected_targets,
                                  message="正在初始化汉化" if result.cdp_ready else "等待应用调试端口")
                    if result.injected_targets:
                        self._publish(status="ready", message="应用已运行，汉化初始化完成", error=None)
                        break
                    self._cancel.wait(self.poll_interval)
                else:
                    if self._cancel.is_set():
                        return self._publish(status="stopped", message="汉化监视已停止", error=None)
                    self._publish(status="degraded", message="应用已运行，汉化暂未就绪，后台继续检查",
                                  error="汉化初始化等待超时")
            else:
                # Give early crashes a chance to surface instead of treating Popen as readiness.
                self._cancel.wait(min(1.0, self.startup_timeout))
                if not self.backend.alive(self.identity):
                    raise RuntimeError("应用启动后退出")
                self._publish(status="ready", message="应用进程已运行（原生界面）", error=None)
            if not self._cancel.is_set():
                self._monitor = threading.Thread(target=self._monitor_loop, name="app-monitor", daemon=True)
                self._monitor.start()
            logger.info("启动验证耗时 %.2fs", time.monotonic() - started)
            return self.status()
        except Exception as exc:
            if operation_started and self._cancel.is_set():
                return self._publish(status="stopped", message="汉化监视已停止", error=None)
            message = redact(exc)
            return self._publish(status="failed", error=message, message=message,
                                 pid=self.identity.pid if self.backend.alive(self.identity) else None)
        finally:
            if (not self._cancel.is_set() and self.backend.alive(self.identity) and
                    (self._monitor is None or not self._monitor.is_alive())):
                self._monitor = threading.Thread(target=self._monitor_loop, name="app-monitor", daemon=True)
                self._monitor.start()
            self._operation.release()

    def _monitor_loop(self):
        delay = 1.0
        try:
            while not self._cancel.wait(delay):
                if not self.backend.alive(self.identity):
                    if self.injector:
                        self.injector.stop_monitoring()
                    self.applied = None
                    self.identity = None
                    self._publish(status="stopped", pid=None, cdp_ready=False, injected_targets=0,
                                  message="应用已退出", error=None, pending_config=False)
                    return
                if self.injector:
                    self.backend.refresh_connections()
                    result = self.injector.scan()
                    ready = result.injected_targets > 0
                    self._publish(status="ready" if ready else "degraded",
                                  cdp_ready=result.cdp_ready, injected_targets=result.injected_targets,
                                  error=None if ready else result.error or "等待应用页面",
                                  message="汉化监视正常" if ready else "应用仍运行，正在恢复汉化")
                    delay = 2.0 if ready else min(delay * 2, 10.0)
        except Exception as exc:
            if self._cancel.is_set():
                return
            logger.exception("监视异常")
            self._publish(status="degraded", error=redact(exc), message="监视异常，请重新启动监视")

    def stop_monitoring(self):
        self._stop_worker()
        return self._publish(status="stopped", message="汉化监视已停止", cdp_ready=False, injected_targets=0)

    def launch(self):
        result = self.start()
        return result.status == "ready", result.message

    def stop_injector(self):
        return self.stop_monitoring()


def is_process_running(exe_name="Antigravity.exe"):
    from core.config_manager import detect_app_path
    return bool(ProcessBackend().find(detect_app_path()))


def terminate_running_instances(exe_name="Antigravity.exe"):
    from core.config_manager import detect_app_path
    backend = ProcessBackend()
    return backend.close(backend.find(detect_app_path()))
