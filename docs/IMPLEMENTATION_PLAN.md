# Antigravity 启动器可靠性与性能：详细实施计划

日期：2026-11-04；2026-11-05 用户要求恢复实施，并要求每完成一个模块验证后提交。
新增范围：管理界面采用 Apple/macOS 风格重设计，保留 Tkinter；覆盖下文原先“布局只增加必要状态”的限制。
**本文是目标规格，不是完工证明。当前实际进度以 ../HANDOFF.md 为准。**
2026-11-05 更新：本轮实现和本机验收已完成，具体通过项与限制见 VALIDATION.md。下方清单保留为原计划记录，不代表还有待执行任务。
后续需求已落实：启动成功后自动收进 Windows 系统托盘，图标可恢复面板并提供退出菜单；代理按钮文案改为“添加到列表”。
最新需求：7897 端口的 SOCKS5/HTTPS/HTTP 三个默认预设，直连默认增加 RFC 1918 私网网段；补齐安装/使用 README，合并未推送提交并将 GitHub 仓库公开。
公开发布 CI 的兼容性修复：快捷方式直接使用 IShellLinkW/IPersistFile 进行 Unicode 持久化，取代旧 PowerShell/WSH 保存路径；Python 3.11/3.14 检查已通过。

## 一、目标、范围和约束

解决启动误报、运行配置不生效、面板关闭导致监视中断、汉化重复扫描和配置/快捷方式脆弱的问题。
保留 Python/Tkinter 和源码运行方式，布局只增加必要状态，不增加安装包、系统服务、开机启动或代理转发模块。

已锁定：
- 关闭面板后台继续汉化；应用退出时回收监视，隐藏面板时退出启动器。
- 需要重启才能生效的配置，在用户发起启动/应用时自动正常退出并重启。
- 保存只保存并标记待应用，不自动中断任务。
- 关闭超时 10 秒，启动验证 30 秒；不自动强杀或无限重启。
- SOCKS5 地址直接传给应用，检测采用 requests[socks]，DNS 由代理端解析。
- 配置留在项目目录，兼容现有字段；保留 7891 当前选择，7897 作为额外预设。
- 不修改官方安装包，不把安装目录中的 app.asar 或二进制复制入仓库。
- 依赖通过官方包管理器安装；仅在临时目录做自动快捷方式测试。

## 二、模块划分和接口

### 2.1 统一启动控制：core/app_launcher.py

保留 AntigravityLauncher 名称，使它成为 GUI 与静默模式唯一的应用控制入口。
封装配置快照、进程身份、状态转换、注入器和监视生命周期，UI 不直接 taskkill/Popen。

目标方法：
- start() -> LaunchResult：按当前有效配置启动、复用或自动重启。
- restart() -> LaunchResult：显式正常关闭目标实例并重新启动。
- status() -> LaunchResult：返回线程安全的当前快照，不触发启动或网络请求。
- stop_monitoring()：仅停止本工具监视、关闭相关连接，不关闭 Antigravity。
- 为旧调用保留 launch()/stop_injector() 兼容包装，统一转到上述实现后逐步调整调用方。

LaunchResult 至少包含：
- status：idle / starting / waiting_cdp / injecting / ready / degraded / failed / stopped。
- pid：int 或 None；实际识别的主进程。
- cdp_ready：bool。
- injected_targets：int，当前已验证的应用页面数。
- error：安全可展示的字符串或 None。
- message：面向用户的当前阶段说明。
- pending_config：bool，已保存快照与已应用快照是否不同。

LaunchSettings 为不可变快照，已有草稿字段：
app_path、enable_proxy、current_proxy、no_proxy、enable_hans、debugging_port。
启动相关快照比较忽略代理列表排序等不影响应用进程的字段；停用的代理地址变动不应无谓重启。

启动操作用一把操作锁串行化。UI 重复点击和重复快捷方式都不得并发重启。
后台事件是结构化结果/日志，不直接访问 Tk。测试使用注入的进程 adapter、注入器工厂、时钟/等待方式。

### 2.2 进程模块：core/process_backend.py

现有草稿 ProcessIdentity(pid, created, path) 和 ProcessBackend 可继续使用。

必须支持：
- find(app_path)：匹配规范化可执行文件路径，区分主进程和 --type= 子进程。
- alive(identity)：核对 PID、创建时间、路径，避免 PID 复用误判。
- spawn(settings, env)：不通过 shell 拼命令；保持必要句柄并可靠处理 Electron 进程转交。
- close(identities, timeout=10)：向目标正常窗口发送 WM_CLOSE，确认退出；超时返回失败。
- 调试端口所属进程验证；必要时识别同安装目录的官方后台语言服务。
- 每轮复用进程/监听快照，不为每个页面反复扫描全机连接。

只管理所选安装路径的实例，不按名称误关另一份安装。
应用拒绝关闭、无权限或无法确认退出时停止重启操作并报告，禁止 /F 或 TerminateProcess。
不得仅凭某端口返回 JSON 就把它当作 Antigravity。

### 2.3 单实例：新增 core/single_instance.py

采用 Windows 命名互斥锁及当前用户命名管道，避免多次启动形成多个汉化监视器。
标识由当前用户身份和规范化目标应用路径导出；IPC 限于当前用户。
允许的控制意图仅为显示面板、启动、重启、查询状态、停止本工具监视；不接受任意命令或 Python 对象执行。
采用有界、版本化 JSON 消息；如使用 multiprocessing.connection，使用 send_bytes/recv_bytes，不用自动 pickle 反序列化。
所有有效指令进入控制器/GUI 队列，管道线程不直接操作 Tk。

重复 GUI 快捷方式显示并聚焦现有面板。
重复静默快捷方式请求已有控制器执行 start，操作锁避免并行。
首次实例初始化中，后续实例短时有界重试；锁持有者已退出时允许重新取得。
另一仓库副本已有相同应用监视时转交已有面板，不静默覆盖其配置。
应用路径变更需在旧身份释放后重新绑定单实例标识，不同时留下两个监视器。
退出必须关闭管道和锁；模拟崩溃后可恢复，不能长期被陈旧状态文件卡住。

### 2.4 GUI 和入口：launcher.py / ui/main_window.py

保留现有 CLI：无参数 GUI、--silent-launch、--create-shortcut。
GUI 和静默共用同一控制器；静默模式可以创建隐藏 Tk 主窗口维持事件循环。
缺少依赖时清楚提示正确的安装/解释器命令，不能只有无声退出。

UI 规则：
- 所有 Tk 调用只在主线程，后台线程只向 Queue 写事件，主线程用 after 周期消费。
- WM_DELETE_WINDOW 在应用仍运行/操作处理中时隐藏，不销毁；无活动应用和操作时清理后退出。
- 关闭面板后不弹出成功窗口；静默失败或需要用户处理时显示面板和原因。
- 应用退出：停止注入器；隐藏状态退出工具，可见状态回 idle。
- 启动期间禁用冲突按钮，结果返回后恢复；异常路径同样恢复。
- 保存失败禁止以“已保存”继续启动；代理增删 ValueError 转可理解提示。
- 代理检测任务有唯一代次，忽略已过期结果，防止旧检测覆盖新选中地址。
- 日志展示有行数上限，长时间运行不能无界增长。
- 增加状态行显示阶段、已汉化页面数、待应用配置；不再无条件弹“启动成功”。

### 2.5 CDP：core/cdp_injector.py

HTTP /json/list 使用显式 ProxyHandler({})；WebSocket 显式 proxy=None。
URL 必须为 loopback 且端口与已验证调试端口一致；检查 /devtools 页面连接格式。
先核验调试端口进程，再校验目标页面来源，再检查页面的应用界面特征。
只翻译应用 UI，排除外部浏览页面、用户预览页和第三方 webview。
本机当前 2.29.0 可能使用语言服务本地 HTTPS 页面，不能只允许 workbench.html；恢复时读取实际目标进行验证。

每个 target 复用一个 WebSocket：
- 请求按 id 匹配，异步通知单独处理，超时用 monotonic 时钟。
- 目标消失、document/context 变化或连接断开时释放对应状态并重连。
- Page.addScriptToEvaluateOnNewDocument 注册避免重复，更新时移除旧注册或明确替换。
- Runtime.evaluate 的 protocol error 和 exceptionDetails 都必须视为失败。
- 检查实际初始化完成、document 身份、词库 fingerprint；不能只看脚本一开始写下的 installed=true。
- 连接和扫描等待可取消；stop 后关闭连接并结束线程，不出现“日志说停止但线程还在跑”。
- 初次等待超时且应用存在：degraded，并以 1/2/4/8/10 秒上限退避继续恢复；成功后恢复正常监视周期。
- 建议正常发现周期 2 秒；避免稳定页面每轮建两次 WebSocket。

## 三、配置、代理和日志规格

### 3.1 配置

兼容现有字段并保留未知字段；读入合并默认值，再做结构校验。
字段：布尔值类型严格；端口必须为非 bool 的 int 且 1..65535；代理列表为字符串列表；应用路径为实际 exe 文件。
配置读取不应主动改写磁盘。无效 JSON 保留原件并提示，不静默用默认值启动。
对可修复字段错误提供明确修复入口；不要因备份校验逻辑使用户永远无法保存有效修复。

保存流程：
候选数据验证 → 如原文件有效，写最后一份有效备份 → 同目录临时文件写入、flush、fsync → os.replace。
失败时原主文件保持有效，内存状态不应假装已持久化；清理本次临时文件。
保护损坏文件，不把它覆盖成“最后有效备份”。
RLock 保护内存读写，get 返回副本，启动使用不可变 snapshot。
需要为旧“仅有部分字段”的配置测试备份兼容。
7897 加入预设但不修改用户 current_proxy；默认新增配置仍保留已有默认方案。

### 3.2 代理

统一 normalize_proxy 用于保存、检测、启动。
接受 http/https/socks5/socks5h；无协议输入按 http；必须有主机与有效端口。
禁止路径、查询串、片段、空白/控制字符；认证信息支持 URL 百分号编码。
UI/日志脱敏，不能打印 user:password。

环境：
- 仅复制并修改子进程环境，不 setx、不改变系统代理。
- 清理大小写代理变量、WS/WSS 代理及 ELECTRON_RUN_AS_NODE。
- 开启时设置 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY；关闭时清除继承代理。
- NO_PROXY 始终包含 localhost、127.0.0.1、::1 并合并用户项。
- 本工具的 CDP 显式直连，不依赖环境 NO_PROXY 恰好正确。

检测：
requests.Session(trust_env=False)，显式代理映射，TLS 校验保持开启，有连接/读取超时，流式响应后关闭。
SOCKS5 检测内部用 socks5h 实现代理端 DNS；应用收到用户所选的原生代理协议。
分别报告端口不通、认证失败、协议错误、TLS/HTTP 失败和超时，不误报成功。
检测成功只说明该检测请求；实机验证单独确认官方进程的代理连接。
官方网络模块若不支持某种原生 SOCKS5，记录具体版本与受限链路，不偷偷改成协议转发。

参考：
- https://requests.readthedocs.io/en/latest/user/advanced/#socks
- https://pkg.go.dev/net/http#Transport
Go 官方 Transport 支持 SOCKS，不足以证明 Antigravity 所有内部模块都正确使用它。

### 3.3 日志

%LOCALAPPDATA%\AntigravityLauncher\logs\launcher.log，UTF-8。
每份最多 2MiB，总共 3 份（当前 + 2 份备份）。
统一 logger 前缀 antigravity_launcher；启动阶段、耗时、重试和失败原因进入日志。
记录目标 ID/类型，不收集用户对话文本；凭据脱敏覆盖异常堆栈和请求 URL。
入口安装 sys/threading 异常 hook，Tk 回调异常也汇入同一机制。
重复初始化不得重复添加 handler；日志目录不可写时提供可见错误或安全降级。

## 四、汉化脚本性能和正确性

现有脚本：assets/antigravity-hans-overlay.js；基线 2401 行、1476 唯一词条。

### 4.1 工作调度

- 初次扫描后依赖 MutationObserver 的增量节点，不再每两秒全 document/body 遍历。
- visibilitychange 从隐藏转可见时安排一次补扫；相同时间段只保留一个任务。
- 使用 Set 去重待处理节点；父节点已在队列时消除子节点重复任务，丢弃脱离文档节点。
- 遍历可中断并保存 walker 位置；每批用 performance.now 检查约 8ms 预算，再用 requestIdleCallback 或 setTimeout 继续。
- 大批变更期间不不断重开计时器，不因自身翻译变更形成无限观察循环。

### 4.2 缓存

- WeakMap 保存每个文本节点的输入/输出、身份失效代次，未命中英文也标记“已处理”。
- Map/LRU 最多 2048 条缓存纯翻译结果，超过上限淘汰最早使用项。
- class/id/role/data-testid 等变化可能让此前非目标容器变成目标，必须使该子树重新判定；不能因为文本没变永久漏翻。
- 词库 fingerprint 变化清空缓存并重扫，避免旧词库结果残留。
- 对属性分别按值缓存，覆盖 aria-label/title/placeholder/data-placeholder/alt；观察属性列表与处理列表一致。

### 4.3 正确性保护

- TreeWalker 使用 FILTER_REJECT 对代码/输入正文等保护子树剪枝，不只是 continue 单节点。
- 去掉过宽 [class*=\"monaco\"]，保留明确编辑器代码区域；工作台菜单/状态栏仍可翻译。
- 代码、终端内容、用户输入、会话名、路径、命令、项目名和回复正文不得被通用词库改写。
- 只保护“正文”时仍允许内部明确按钮/状态/元数据翻译，避免整棵历史列表剪枝导致功能退化。
- 翻译组合句时保留链接节点、事件绑定与嵌套 DOM 身份。
- 已翻译结果二次处理保持幂等，权限极性（允许/拒绝）不能反转。

### 4.4 注入标记和清理

installed 标记只能在初始化/监听器确实完成后置为 true；异常保留可诊断信息，不伪装完成。
初始分批扫描和安装状态需要区分，CDP ready 应等待初始化可靠完成。
cleanup 断开 observer，取消全部 timeout/idle task/visibility listener，清空队列和缓存。
同 fingerprint 再注入不叠加任务；不同 fingerprint 替换前完整清理上一版。
不要将内部实现细节暴露到普通产品用户流程。

## 五、快捷方式和批处理

保持 create_windows_shortcut 和 create_all_desktop_shortcuts 公开参数兼容。
通过 SHGetKnownFolderPath(FOLDERID_Desktop) 识别 OneDrive/重定向桌面。
PowerShell 参数正确字面量传递；Python repr 不能作为 PowerShell quoting。
创建后重新读回 lnk 的 TargetPath、Arguments、WorkingDirectory、IconLocation、Description 并核对。
lnk、GUI lnk、BAT、VBS 各自产物分别记录成功；任一失败汇总不能返回整体成功。
静默解释器优先项目可用的 .venv pythonw，与主入口使用相同依赖。
run.bat 优先 .venv python，找不到再走已说明的系统环境；保留退出码与参数。
ASCII 控制文本；中文路径、空格、单引号、$、!、% 的转义和编码逐项验证。
VBS 使用 Windows Script Host 支持的编码；不能仅确认写了文件就宣称能启动。
所有自动验证使用临时桌面/临时目录，不覆盖用户真实桌面；最终实机确认另做。
当前辅助草稿已含 UTF-16LE EncodedCommand 和 UTF-16 VBS，仍需审查可维护性并测试；这是编码传递，不用于绕过安全拦截。

## 六、测试矩阵和通过条件

### Python：pytest（允许收集 unittest）

建议文件：
- tests/test_config_manager.py：默认/部分旧配置、未知字段、错类型、坏 JSON、原子替换失败、备份、内存回滚。
- tests/test_proxy_checker.py：协议/认证/IPv6/非法端口、远端 DNS、关闭代理遗留变量、本地 HTTP/HTTPS/SOCKS 实际协议测试。
- tests/test_process_backend.py：PID 复用、多安装、主子进程、启动即退、退出超时、端口属于其他进程。
- tests/test_app_launcher.py：冷启动、复用、参数变化重启、未知参数重启、30 秒超时、部分成功、重入串行。
- tests/test_cdp_injector.py：无代理连接、目标过滤、异步消息、脚本异常、连接复用、重载、取消/释放。
- tests/test_single_instance.py：两实例竞争、指令转交、当前用户隔离、未知消息、崩溃恢复。
- tests/test_shortcut_helper.py：真实临时 lnk 回读、重定向桌面替身、BAT/VBS、部分失败及参数。
- tests/test_diagnostics.py：滚动上限、凭据脱敏、重复初始化、线程异常。
- GUI 重点验证队列消费、隐藏/显示、晚到事件、保存错误，避免只测试实现内部细节。

本地模拟端点不依赖 Google/GitHub 或真实账号。
HTTPS 使用测试自签证书与测试 CA，仅该测试信任；禁止产品全局关闭证书校验。
SOCKS fixture 记录目的主机类型，证明检测端没有先本地解析目标域名。

### JavaScript：node:test + jsdom

tests/overlay.test.cjs 直接加载实际脚本，使用真实 DOM fixture，勿把实现复制进测试。
覆盖菜单、动态属性、容器身份延迟补齐、代码区、历史名称/元数据、回复按钮、链接保留、权限文本、重复注入和 cleanup。
用受控调度/clock 验证预算与任务取消，并统计实际 translate 调用数。
同一稳定 DOM 的重复翻译调用较旧基线减少至少 90%；不得只用 wall-clock 噪声代替计数证据。
大 DOM 下任务按约 8ms 分段；真实浏览器长任务需单独测，不把 jsdom 当真实渲染性能。
无固定周期全页扫描；多次切换词库/刷新后 observer/timer/连接数量不累积。
上游 upstream/Antigravity-Hans/tools/overlay.test.mjs 可参考已有语义案例，但该目录被忽略，不能让主测试依赖它。

### 统一检查和 CI

补 scripts/check.ps1：选择 .venv Python，执行 Python 语法/pytest、node --check、npm test，任一失败返回非零。
补 requirements.txt 与 requirements-dev.txt 精确锁版本，保留 .in 作为范围来源，记录生成方式。
Windows CI 使用受支持的 Python 最低版本及当前版本、Node 24，先安装锁定依赖再执行同一检查入口。
先核对依赖 Requires-Python，不盲目声称支持 3.10；最低版本不兼容时选支持的锁版本并记录。
源码运行环境不要求 Node；Node/jsdom 仅用于开发检查。

## 七、实施顺序与阶段完成定义

### 阶段 A：收口已有草稿

- [ ] 核对当前 git diff 和 HANDOFF.md，保留配置/代理/快捷方式现有改动。
- [ ] 修复上述配置兼容、持久化失败回滚和 GUI 错误处理接入问题。
- [ ] 补配置/代理测试；校验新增依赖与解释器选择。
- [ ] 评审 process_backend / diagnostics 草稿，建立可替换 adapter 测试接口。

### 阶段 B：P0 启动及后台

- [ ] 新启动状态机接入配置快照、环境、进程 backend 和 CDP 验证。
- [ ] 完成 CDP 显式直连、页面来源检查、连接生命周期。
- [ ] 完成单实例命名互斥锁/管道和队列。
- [ ] 完成 GUI 隐藏后存活、静默模式错误回退、重复启动/重启串行。
- [ ] 离线回归覆盖所有成功/失败状态；阶段通过后提交。

### 阶段 C：P1 汉化

- [ ] 修剪代码区域 selector、真实 DOM 回归先建立。
- [ ] 增量队列/8ms 时间片/缓存/失效。
- [ ] 清理与安装标记正确性。
- [ ] 功能与性能基线同时通过后提交。

### 阶段 D：P2 工程质量

- [ ] 快捷方式完整测试，含 BAT/VBS 与虚拟环境。
- [ ] 日志与异常传播接入。
- [ ] 精确依赖锁、统一检查、Windows CI。
- [ ] README 更新：支持范围、已知限制、后台行为、代理/日志/排错。
- [ ] 去掉“绝对安全、零误报、永久兼容”等无法证明承诺。

### 阶段 E：实机验收

- [ ] 本机当前版本冷启动/静默启动/GUI 启动。
- [ ] 连点快捷方式只有一个监视实例。
- [ ] 关闭面板后应用刷新/新窗口仍汉化，再次打开显示原面板。
- [ ] 保存代理显示待应用，发起启动后自动正常重启并使用新环境。
- [ ] 退出失败不强杀；应用退出后后台回收。
- [ ] HTTP/HTTPS/SOCKS 的检测与应用实际网络路径分别记录。
- [ ] 代码、用户输入、会话名、回复不被误翻；菜单/设置正常。
- [ ] 实际桌面快捷方式可启动正确解释器。
- [ ] 所有测试通过，git diff 复核，更新交接/README 并分阶段提交。

实机涉及用户登录或模型请求时只做用户已授权、可明确归因的动作；不要发送无关内容或制造消耗。
无法验证的项目记录“未验证”和原因；客户端原生 SOCKS5 不兼容不能标记通过。
如果实机运行显示与静态假设不同，先记录证据、修改对应实现和测试，不扩大代理/注入范围来掩盖问题。

## 八、版本管理、回滚与交付

当前所有实现都未提交，不能把 c43cc1c 当成包含新改动的版本。
每阶段通过后再提交；用户自己的 config.json、venv、node_modules、日志/认证信息不进 Git。
不因失败整仓 reset/clean；按明确文件和差异修复。
若需要切回旧版本验证，使用独立工作树或临时副本，保留本目录草稿。
最终交付给用户：做了什么、自动检查结果、实机证据、剩余限制、使用正确解释器的入口。
本轮已由用户于 2026-11-05 恢复并完成；以后按新请求继续维护，先读 HANDOFF.md 的最新证据与提交记录。
