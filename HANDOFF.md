# 开发交接：Antigravity Launcher

更新：2026-11-05（Asia/Shanghai）。**已完成本轮实现、模块提交和本机验收。**
最新发布：GitHub 仓库已公开，匿名 API 请求返回 200/private=false。全部改动按用户要求合并为一个发布提交；原模块记录保留在本地 codex/pre-publication-20261105 分支，公开分支以 git log 为准。
发布 CI 发现英文 Windows 的 WSH 中文路径保存失败；已改用 IShellLinkW/IPersistFile，界面测试使用独立 Tk 进程。修复版远端 Python 3.11、3.14 两组检查均通过。
详细设计见 [实施计划](docs/IMPLEMENTATION_PLAN.md)，验证证据见 [VALIDATION.md](docs/VALIDATION.md)。

## 接手须知

- 工作目录：D:\coding-space\Gemini\antigravity-launcher；分支 master；初始基线 c43cc1c。
- 用户要求每完成一个模块验证后提交。先看 git status、git log，保留后续未提交差异，禁止 reset/clean。
- Python 使用 .venv\Scripts\python.exe；最低 3.11，本机 3.14.6。Node 24 仅用于测试和图标生成。
- 网络不稳定使用 http://127.0.0.1:7897；应用代理以当前 config.json 为准，不用历史验收地址覆盖用户后续设置。
- 不打印代理凭据、用户页面正文或认证信息。
- 11-04 的关机授权当时已执行，不代表今后完成任务时可以再次关机。

## 用户已确定的产品行为

- 保留 Python/Tkinter；关闭面板后继续后台汉化，再次打开管理快捷方式显示已有面板。
- 应用退出后回收监视；面板隐藏时工具退出，可见时待命。
- 保存仅保存并标记待应用；发起启动时发现配置变化或未知运行参数，自动正常关闭并重启。
- 正常关闭最多等待 10 秒；失败不强杀、不循环重启。
- 启动最多等待 30 秒确认 CDP 和汉化；部分可用保留应用并后台退避重试。
- SOCKS5 检测采用代理端 DNS，应用收到原生 SOCKS5 地址；不增加协议转发模块。
- 用户后来要求 Apple/macOS 风格界面，以及任务栏/界面图标；两项均已完成。
- 图标为蓝色悬浮球体与轨道，替换字母 A，管理工具有独立 AppUserModelID。
- 后续新增：按钮显示“添加到列表”；启动成功后面板自动收进系统托盘，点击图标恢复，右键可打开面板或退出管理工具。启动失败/托盘不可用保留面板。
- 最新默认代理为 socks5://127.0.0.1:7897、https://127.0.0.1:7897、http://127.0.0.1:7897；socks:// 是 SOCKS5 别名。
- 新配置的默认 NO_PROXY 增加 10.0.0.0/8、172.16.0.0/12、192.168.0.0/16；当前本机配置也已按明确请求更新，旧配置有备份。

## 提交记录

| 提交 | 内容 |
|---|---|
| 94e8719 | 配置校验、原子保存、代理协议和锁定依赖 |
| 98e7257 | 统一启动状态、进程身份、CDP、单实例和后台监视 |
| 4a2d560 | 汉化增量扫描、缓存、分批与清理 |
| 9a5d38e | Apple 风格 Tkinter 面板与圆角控件 |
| 44059da | Windows 快捷方式、解释器选择、脚本转义和回读 |
| 076861e | SVG/PNG/多尺寸 ICO、窗口/任务栏/管理快捷方式图标 |
| 73d94aa | 初始化取消和停止后无效配置边界 |
| 最新文档提交 | README、Windows CI、统一检查脚本、本交接和验收记录；hash 看 git log |

上表是合并前的模块提交记录；发布合并后从本地备份分支可追溯。用户 config.json、日志、.venv、node_modules、真实桌面文件均不进 Git。

## 验证结论

- 最新统一入口 scripts/check.ps1：48 项 pytest、6 项 Node 测试通过，0 跳过；Python/JS 语法和 pip check 通过。
- 发布前新增默认预设、socks 别名、私网 CIDR 边界和中文分隔符回归；已更新本机配置并保留有效备份。
- 托盘模块使用 Shell_NotifyIconW，不增加依赖。真实 Windows 验证图标注册、选择回调、TaskbarCreated 重注册及退出资源释放；GUI 回归验证成功后隐藏、失败保留、恢复和退出。
- 本轮真实界面已查看“添加到列表”。尝试随后点击启动时窗口已被正常关闭，因此未把该次鼠标操作记为成功；收起逻辑由 GUI 回归和真实托盘测试分别覆盖。
- 实机 Antigravity 2.29.0：冷启动就绪，1 个应用页面汉化初始化完成。
- 关闭面板后刷新主页面仍能重新汉化，随后可显示原面板。
- 真实桌面静默快捷方式启动成功，再次启动复用原应用 PID。
- 原生 SOCKS5 启动达到 ready，官方语言服务继承 SOCKS5，观察到 8 条至选定代理端口的 ESTABLISHED 连接。
- 正常关闭应用成功，监视变为 stopped。之后已用原配置恢复应用和管理面板。
- 原用户配置哈希在原生 SOCKS5 临时配置测试前后保持一致，当前代理仍为 7891。
- 中文/空格/单引号/$/!/%PATH% 临时路径下 .lnk、BAT、VBS 均实际执行通过。
- 真实窗口已查看，新图标和布局无重叠；Windows 类小图标与任务栏大图标句柄均存在。
- 同一 100 个未知英文 DOM 节点、10 轮补扫：原版 translate 调用 1000 次，新版 0 次（不计初次扫描）。
- 不把这些结果等同于模型对话、所有应用版本兼容或真实渲染帧率测试。远端 Windows CI 已验证 Python 3.11 和 3.14，本机为 Python 3.14.6。

## 重要文件与运行入口

- launcher.py：GUI/静默入口，日志、AppUserModelID、单实例协调。
- core/app_launcher.py：start/restart/status/stop_monitoring，结构化 LaunchResult。
- core/process_backend.py：规范化路径 + PID + 创建时间识别、WM_CLOSE、端口归属。
- core/single_instance.py：当前用户 DACL 的 Windows 互斥锁与命名管道，有限 JSON 指令。
- core/cdp_injector.py：本机直连、页面来源/界面验证、连接复用和初始化验证。
- core/config_manager.py / proxy_checker.py：配置快照、原子保存、备份、代理与 TLS。
- ui/main_window.py / components.py：主线程队列、后台生命周期、圆角面板和开关。
- ui/tray_icon.py：独立 Win32 消息循环、通知区域图标、恢复/退出菜单和 Explorer 重启重注册；回调仅写主线程队列。
- core/shortcut_helper.py：Known Folder、.lnk 回读、路径编码、BAT/VBS。
- core/windows_shortcut.py：IShellLinkW/IPersistFile 的 Unicode 保存与读回，避免受系统 ANSI 代码页影响。
- assets/antigravity-hans-overlay.js：增量翻译、WeakMap/LRU、代码区保护。
- assets/launcher-icon.svg：图标唯一源文件，npm run icons 重建 PNG/ICO。
- tests/：本地端点/模拟进程/真实临时 Windows 快捷方式/jsdom 验证。
- .runtime/launcher-preview.png：本机新版界面截图，忽略文件，不作为构建依赖。

~~~powershell
Set-Location 'D:\coding-space\Gemini\antigravity-launcher'
.\run.bat
.\.venv\Scripts\python.exe launcher.py --create-shortcut
.\scripts\check.ps1
npm.cmd run icons
~~~

依赖恢复：
~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm.cmd ci --ignore-scripts
~~~

## 维护时注意

- 坏 JSON 原件保留并阻止启动；修复或移走后重新打开面板。可修复的结构错误会备份至 config.json.invalid-*。
- 保存候选校验失败不应留下假“已保存”状态；旧部分字段配置需要与默认值合并后验证备份。
- CDP 主界面当前为官方语言服务提供的 https://127.0.0.1:动态端口/，并非只有 workbench.html。
- data: 加载遮罩和第三方预览不能无条件注入；端口和页面必须经过身份验证。
- Windows ShellExecute 会展开 .lnk 参数中的 %NAME%；引导参数编码用于保留合法字面路径。
- .ico 含 16/24/32/48/64/128/256；修改 SVG 后运行 npm run icons 和 npm test，保持资源同步。
- 桌面静默入口保留 Antigravity 官方应用图标；“Antigravity 启动管理工具”使用本项目新图标。
- 日志为 UTF-8，当前 + 2 份轮转，各 2MiB；新日志字段也必须脱敏。
- 原辅助工作的保留草稿已完成并验证，无待接管任务。
