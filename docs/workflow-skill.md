# 配套工作流 Skill

端到端安装和账户验收步骤见 [Agent 安装与接入 Runbook](agent-setup.md#2-配套-skill源码账户安装会话加载分别验收)。

规范文件位于 `skills/manage-development-activities/`，仅包含通用任务管理流程及三个参考文件。它们不是本机执行器，也不会自动安装到任何账户。

检查文件及 SHA-256：

```sh
python3 scripts/workflow-skill.py
```

导出到源码目录之外的新 ZIP，已有文件会被拒绝覆盖：

```sh
python3 scripts/workflow-skill.py --export /absolute/path/to/new-workflow-skill.zip
```

使用目标账户当前受支持的 Skill 安装入口，按平台要求操作并核验保存内容及可用性。面板的 `skill-upsert` 仅登记用途和观察；账户安装、Skill 触发、定时器配置及真实执行是不同事实。`doctor` 不读取账户，不创建定时器，不修复权限，不使用凭据。没有观察依据时保持未核验。

个人规则和独立 X 阅读器不随本项目发布；实际管理链接和账户 ID 只存私有 DATA。不要把运行库、日志、任务截图或账户信息放入源码包。
