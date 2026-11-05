# 本轮验证记录

日期：2026-11-05。范围：启动可靠性、后台监视、代理、汉化性能、Windows 快捷方式、新版界面与图标。

## 自动检查

执行统一入口 scripts/check.ps1：

| 项目 | 结果 |
|---|---|
| Python compileall | 通过 |
| pip check | 通过，无依赖冲突 |
| pytest | 48 项通过，0 跳过（含托盘、默认代理和私网直连变更） |
| node --check | 通过 |
| Node node:test | 6 项通过，0 跳过 |

本机：Windows、Python 3.14.6、Tk 8.6、Node 24.18.0。
依赖见 requirements.txt / requirements-dev.txt / package-lock.json。
GitHub Windows CI 的 Python 3.11/3.14 两组均已通过：[兼容性修复验证](https://github.com/mingglez88/Antigravity-pie/actions/runs/42029655893)。
初次远端运行发现英文 Windows 的 WSH 将中文快捷方式文件名转为问号；改用 IShellLinkW/IPersistFile 后通过。GUI 测试改为每个场景独立进程，与产品单个 Tk 实例的运行方式一致。

Python 回归覆盖：
- 部分旧配置、原子保存、有效备份、坏配置保留、失败后内存回滚。
- 真实本地 HTTP/HTTPS 代理、HTTP CONNECT、SOCKS5 远端 DNS、非法地址和代理环境清理。
- HTTPS 代理对 HTTP 目标同样强制 TLS 验证，临时 CA 仅在测试中信任。
- 启动复用、配置改变、关闭失败、端口占用、汉化超时、初始化取消。
- 当前用户单实例命名管道、重复竞争、指令转交、释放后重新获取。
- CDP WebSocket 复用、异步消息、脚本异常、来源过滤和关闭。
- PID 复用、不同安装路径、主/子进程和歧义端口。
- 滚动日志、凭据脱敏。
- 真实临时 .lnk/BAT/VBS 执行，GUI 主线程队列、隐藏/恢复/退出。
- 启动成功后自动收进托盘、失败保留面板、托盘恢复/退出、通知区域不可用的回退。
- 原生 Shell_NotifyIconW 注册、选择回调、TaskbarCreated 重注册、图标和线程清理。
- 7897 三协议默认预设、socks:// → socks5://、RFC 1918 私网边界及 NO_PROXY 中文/英文分隔符。

JavaScript 回归覆盖：
- UI 翻译与代码/输入/会话名/回复正文保护。
- 动态属性、data-placeholder、容器身份延迟变化。
- 未命中英文缓存、无固定周期整页扫描。
- 大 DOM 分批、代码子树剪枝、重复注入及 cleanup。
- 权限目标/项目名的幂等保护。
- ICO 7 个尺寸与 SVG 渲染逐字节一致，48px UI PNG 同步。

## 实机验收

本机安装的 Antigravity package.json 版本为 2.29.0。

| 场景 | 实际结果 |
|---|---|
| 冷启动 | ready；确认端口所属进程；1 个应用页面已完成汉化 |
| 面板关闭 | 发送 WM_CLOSE 后面板隐藏，IPC 状态仍 ready |
| 页面刷新 | Page.reload 后 installed=true、document.lang=zh-CN，重新注入成功 |
| 面板重开 | IPC show / 管理快捷方式显示原面板 |
| 重复静默快捷方式 | 复用原应用 PID，没有重复重启 |
| 当前 HTTP 代理 | 检测通过；官方语言服务继承代理，观察到至端口的连接 |
| 原生 SOCKS5 | 临时内存配置直接传 SOCKS5 地址，ready；官方后台有 8 条至代理端口的 ESTABLISHED 连接 |
| 正常退出 | 正常关闭返回成功，监视随后 stopped、pid=None |
| 用户配置 | SOCKS5 验证前后原 config.json 哈希一致，仍使用 7891 |
| 桌面文件 | 已生成并回读实际桌面快捷方式；静默入口真实启动通过 |
| 新界面 | 真实 Windows 截图核对，圆角卡片/滚动内容无重叠 |
| 新图标 | 管理界面与标题栏显示轨道图标，窗口类小/大图标句柄均存在，独立 AppUserModelID 已设置 |

最终保留管理面板与应用运行，状态为 ready、1 个页面正常汉化。
以上为首轮实机记录。后续增加系统托盘时，管理面板已被正常关闭；新的鼠标启动验收未完成，不将先前结果重复计为托盘实测。最新托盘行为有 GUI 回归和真实 Windows 通知区域测试覆盖。
没有执行模型对话或发送无关请求；原生 SOCKS5 结果不代表所有内部功能均已逐一验收。

## 性能证据

同一 jsdom fixture：100 个未知英文节点，初次扫描后再处理 10 轮。

| 实现 | 额外 translate 调用 |
|---|---:|
| 原版 c43cc1c | 1000 |
| 新版 | 0 |

另外，同一未知文本直接调用翻译 1000 次，新版仅执行 1 次未缓存规则计算。
这些是 DOM/规则计算证据，不是实际 Electron 帧率、CPU 常驻占用或模型响应速度。

## 支持范围与限制

- 本机运行时验证覆盖 Windows 和 Antigravity 2.29.0；未来版本 DOM 变化可能要求调整来源识别和翻译规则。
- 当前原生 SOCKS5 地址直传，没有协议桥接，也没有全局系统代理修改。
- Python 3.11 是锁定依赖支持的最低版本；本机版本为 3.14.6，远端已验证 3.11.9 和 3.14.10。
- Linux/macOS 不属于当前 GUI/单实例/快捷方式支持范围。
- TLS 测试需要 OpenSSL；本机使用 Git for Windows 自带版本，全部测试实际执行。
- 安全软件是否告警未作保证；本工具保持源代码和标准本地调试接口可审查。

托盘实现参考 [Microsoft Shell_NotifyIconW 文档](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shell_notifyiconw)，使用 NOTIFYICON_VERSION_4 和当前项目图标。
