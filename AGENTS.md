<!-- Recovery integration: retained baseline guidance with current GitHub boundary corrected. -->
# Agent 安装和修改指南

先读 README.md、docs/agent-setup.md、docs/install.md 与 docs/privacy.md。遵循用户最新授权；不访问用户未请求的其他机器或项目。

1. 明确用户要安装的实际 dot 云桌面，区分执行 shell 和桌面；不要把“我的电脑”替换成云电脑
2. 先确认 SOURCE 和独立 DATA 两个目录规划，避免散放；保留既有文件和修改
3. 运行标准库测试；在实际桌面终端安装入口，确认 HOME 与桌面身份正确
4. 仅 loopback 启动，检查 /health 并截图验证实际界面。平台拒绝本地访问时不得绕过；准确报告限制
5. 仅为显式授权的任务写入摘要和步骤，真实内容只存 DATA；不要导入助手内部记录或扫描其他任务
6. verified 必须有已完成检查的证据，未接入工作流不得展示为已运行
7. 发布前审核 Git 跟踪文件：禁止 DATA、日志、数据库、身份、环境私有路径、秘密、真实对话与工作截图
8. 用户授权发布才推送；仅使用已连接 GitHub 插件，检查实际远端 commit；不操作 GitHub Actions/Workflows，不使用账户登录或凭据回退

代码用 Python 3.10+ 标准库和原生浏览器 API。避免 npm / Docker / 第三方 Python 依赖。测试命令：`PYTHONPATH=src python3 -m unittest discover -s tests -v`。修改后重跑相关测试和全套测试。不要新增自动启动、网络公开、认证凭据或系统安全配置。
