# Antigravity-pie · Antigravity Launcher

Windows 桌面启动与中文界面管理工具。使用 Python/Tkinter，通过本机 CDP 接口加载汉化脚本，提供代理设置、启动状态、后台监视和桌面快捷方式。

界面采用浅灰底色、白色圆角卡片与侧栏。无需 Node.js 即可运行；Node.js 只用于开发测试。
管理工具使用统一的悬浮球体/轨道图标，覆盖界面、窗口、任务栏和管理快捷方式。

## 安装

需要 Windows 10/11、[Python 3.11 或以上](https://www.python.org/downloads/windows/)，以及已经安装的 [Antigravity](https://antigravity.google/download)。安装 Python 时勾选添加到 PATH；普通使用不需要 Node.js。

### 1. 获取项目

已安装 Git 时，在 PowerShell 执行：

~~~powershell
git clone https://github.com/mingglez88/Antigravity-pie.git
cd Antigravity-pie
~~~

也可以[下载 ZIP](https://github.com/mingglez88/Antigravity-pie/archive/refs/heads/master.zip)，解压后进入包含 launcher.py 和 run.bat 的目录，在该目录打开 PowerShell。

### 2. 安装依赖

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

网络超时且本机代理已在 7897 端口运行时，可执行：

~~~powershell
.\.venv\Scripts\python.exe -m pip install --proxy http://127.0.0.1:7897 -r requirements.txt
~~~

无需激活虚拟环境；上面的命令直接使用项目的 Python。

### 3. 打开管理面板

双击 run.bat，或者执行：

~~~powershell
.\run.bat
~~~

首次启动会尝试检测 Antigravity 的安装位置；未找到时点击“选择…”指定 Antigravity.exe。它是独立安装的官方应用，本项目不会代为下载或安装它。

## 启动方式

~~~powershell
# 打开管理面板
.\.venv\Scripts\python.exe launcher.py

# 根据已保存配置启动应用，正常情况下不显示管理面板
.\.venv\Scripts\pythonw.exe launcher.py --silent-launch

# 生成桌面快捷方式及备用启动脚本
.\.venv\Scripts\python.exe launcher.py --create-shortcut
~~~

run.bat 和生成的快捷方式优先使用项目 .venv。移动项目目录或重建虚拟环境后，请重新生成快捷方式。

## 日常使用

1. 在“应用”中确认 Antigravity.exe 路径。
2. 在“网络连接”中选择代理并点击“测试连接”。需要直连时关闭代理开关；自定义地址可通过“添加到列表”保存。
3. 按需开启“中文界面”，点击“保存设置”。
4. 点击“启动 Antigravity”。成功后面板自动收进右下角系统托盘，点击托盘图标恢复面板。
5. 日常使用可点击“创建快捷方式”，之后从桌面“Antigravity (汉化代理版)”直接启动；“Antigravity 启动管理工具”用于调整设置。

应用正在运行且启动参数发生变化时，会先尝试正常关闭，再重新启动。

保存配置本身不会重启应用。正常关闭最多等待 10 秒，应用阻止退出时停止操作并显示原因，不强制结束进程。

状态会区分“等待调试端口”“初始化汉化”“就绪”“部分可用”“失败”。创建了进程不代表汉化完成；首次等待 30 秒后仍未完成汉化，会保留应用并在后台重试。

关闭面板后继续监视；再次打开管理快捷方式会显示已有面板。应用退出后，隐藏的启动器自动退出，可见面板则回到待命。重复启动使用当前用户的命名互斥锁和命名管道协调。

点击启动并成功就绪后，管理面板自动收起到右下角系统托盘，后台汉化继续运行。点击托盘图标可恢复面板，右键可选择“打开管理面板”或“退出管理工具”。退出管理工具仅停止监视，不关闭 Antigravity。启动失败或托盘不可用时保留面板显示；图标是否直接显示或收在通知区域的展开菜单中，由 Windows 设置决定。

## 代理与配置

默认代理列表按下面顺序提供，首次安装默认选中 SOCKS5：

~~~text
socks5://127.0.0.1:7897
https://127.0.0.1:7897
http://127.0.0.1:7897
~~~

支持 HTTP、HTTPS、SOCKS5 和 SOCKS5H，以及 URL 编码的用户名/密码。输入 socks:// 会自动规范化为 socks5://；检测时使用代理端 DNS。本工具不提供协议转发，也不修改系统代理或全局环境变量。

https:// 表示“代理入口本身使用 TLS”，不是“通过代理访问 HTTPS 网站”。普通 HTTP/混合端口访问 HTTPS 网站仍可使用 http://；只有代理端确实提供 TLS 入口时才选择 https://。

默认直连列表为：

~~~text
localhost,127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
~~~

三个 IPv4 私网网段已按 [RFC 1918](https://www.rfc-editor.org/rfc/rfc1918.html) 核对：

| 网段 | 地址范围 |
|---|---|
| 10.0.0.0/8 | 10.0.0.0–10.255.255.255 |
| 172.16.0.0/12 | 172.16.0.0–172.31.255.255 |
| 192.168.0.0/16 | 192.168.0.0–192.168.255.255 |

直连列表支持英文/中文逗号、分号输入，保存时统一为逗号并校验 CIDR。localhost、127.0.0.1、::1 始终保留，工具的 CDP 连接显式直连。私网直连规则传入应用的 NO_PROXY；是否使用该变量取决于应用内部网络模块，不能把检测请求成功等同于所有内部请求已验证。

已有配置的当前代理、自定义列表和直连项会保留；更新代码会补入新的代理预设。首次配置使用上面全部默认值；已有用户可在面板把直连列表更新为上面的内容。

配置保存在项目目录的 config.json，不进入 Git。写入采用同目录临时文件和原子替换；上一份有效配置保存在 config.json.bak。坏 JSON 会保留原件并阻止启动，请修复该文件或将其移走后重新打开面板。结构错误配置在有效修复时保留为 config.json.invalid-*。

代理认证信息仍属于本地配置，日志输出会脱敏；请勿分享原始配置文件。

## 汉化原理与范围

汉化只处理经进程、页面来源和界面特征确认的应用页面，不修改官方安装包。界面更新由 MutationObserver 增量处理，采用分批调度和有限缓存；代码区、输入内容、会话名称和回复正文设有跳过规则。

新版本的 Antigravity 可能改变页面结构，存在漏翻或兼容性变化。脚本中的保护规则经过回归测试，但不能保证所有未来页面都被正确识别。任何安全软件是否告警也取决于具体环境。

## 日志与排错

日志位置：%LOCALAPPDATA%\AntigravityLauncher\logs\launcher.log。UTF-8 编码，每份最多 2 MiB，总共保留 3 份。

- 缺少依赖：使用上面的 .venv Python 安装 requirements.txt。
- 调试端口冲突：在面板调整“本地调试端口”，保存后重新启动。
- 应用未退出：处理应用自身的保存/确认提示，再重试启动。
- 应用运行但未汉化：检查状态和日志；工具会尝试恢复。不要把未知端口或任意浏览页面加入注入范围。
- 快捷方式无效：从当前项目虚拟环境重新生成，保持项目路径可用。

## 开发与验证

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm.cmd ci --ignore-scripts
.\scripts\check.ps1
~~~

requirements.in / requirements-dev.in 是依赖范围，两个 .txt 文件为已验证版本快照。更新依赖后需重新生成锁文件并运行检查。package-lock.json 锁定 jsdom、SVG 渲染工具及其依赖。

图标源文件为 assets/launcher-icon.svg；运行 npm run icons 重建界面 PNG 和 7 个尺寸的 Windows ICO，再运行 npm test 校验资源一致性。

Python 测试使用本地模拟进程、代理和 CDP；JavaScript 测试使用实际汉化脚本与 jsdom。Windows 特有测试会创建临时快捷方式并执行标记脚本，测试不发送模型请求。TLS 测试需要 Git for Windows 附带的 OpenSSL，缺失时该组测试明确跳过。

Windows CI 使用 Python 3.11/3.14 和 Node 24，两组检查均已通过。最新状态见 [GitHub Actions](https://github.com/mingglez88/Antigravity-pie/actions/workflows/checks.yml)，验证范围见 [VALIDATION.md](docs/VALIDATION.md)。

## 更新项目

关闭管理工具后，在项目目录执行以下命令，再双击 run.bat：

~~~powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

ZIP 安装用户可下载新 ZIP 并替换源码，保留自己的 config.json，然后重新安装依赖。项目目录发生变化时需重新生成快捷方式。

主要模块：

| 模块 | 职责 |
|---|---|
| core/app_launcher.py | 统一状态、启动、复用、重启和监视 |
| core/process_backend.py | 进程身份、正常退出和端口归属 |
| core/single_instance.py | 当前用户单实例与有界 JSON 指令 |
| core/cdp_injector.py | 页面来源验证、连接复用和注入确认 |
| core/config_manager.py / proxy_checker.py | 配置持久化、代理校验与检测 |
| core/shortcut_helper.py / windows_shortcut.py | Unicode 快捷方式生成、持久化与读回 |
| core/diagnostics.py | 日志和异常记录 |
| ui/ | Tkinter 面板、圆角控件及主线程事件队列 |
| assets/antigravity-hans-overlay.js | 词库、增量翻译、缓存与内容保护 |

接手开发前阅读 [HANDOFF.md](HANDOFF.md) 和 [实施计划](docs/IMPLEMENTATION_PLAN.md)，按模块测试并提交。

## 上游致谢

汉化词库和 CDP 方案参考 [yuexps/Antigravity-Hans](https://github.com/yuexps/Antigravity-Hans)，词条亦参考 [kdczyz/antigravity-chinese](https://github.com/kdczyz/antigravity-chinese)。本项目在其基础上实现 Python 启动控制、代理管理、后台生命周期及本地测试。

本项目为独立工具，不属于 Google 官方产品。请遵循应用本身的使用条款。
