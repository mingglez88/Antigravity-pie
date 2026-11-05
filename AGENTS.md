# 接手本项目

- 继续开发前先读根目录 HANDOFF.md，再读 docs/IMPLEMENTATION_PLAN.md。
- 用户已批准优化方案；2026-11-05 要求继续实施。不要把计划或未验证草稿当成已完成。
- 用户要求继续优化时，按已批准选择推进，不重复询问这些决策：保留 Python/Tkinter、关闭面板后继续汉化、需要应用配置时自动正常关闭并重启、SOCKS5 直接传给应用、不增加协议转发模块。
- 检查 git status 和现有差异，保留未提交修改；不得 reset/clean 或覆盖其他人的工作。
- 使用 .venv\Scripts\python.exe；run.bat 已优先使用此虚拟环境。
- 网络超时或不稳定时使用本地代理 http://127.0.0.1:7897。应用默认预设为 7897 的 SOCKS5、HTTPS、HTTP；后续自定义配置不得被网络工具的代理配置覆盖。
- Python/PowerShell 输出与文件读写显式使用 UTF-8；批处理控制文本使用 ASCII。
- 不把代理凭据写入日志、文档、测试快照或提交。
- 自动测试优先使用模拟进程、CDP 和本地代理；实机代理链路和汉化效果需要单独验证。
- 每完成一阶段更新 HANDOFF.md 的进度和证据；测试通过前不要声称优化完成。
- 用户要求每完成一个模块，验证通过后就提交；不要将未完成模块混入已完成模块提交。
- 用户新增要求：管理界面改成 Apple/macOS 风格，保留 Tkinter；此要求覆盖原计划仅小改布局的限制。
- 统一图标源为 assets/launcher-icon.svg；界面和 Windows ICO 用 npm run icons 生成，运行 npm test 确认同步。
- 默认直连列表包含 localhost、127.0.0.1、::1，以及 RFC 1918 的三个私网网段。socks:// 输入按 socks5:// 规范化。
