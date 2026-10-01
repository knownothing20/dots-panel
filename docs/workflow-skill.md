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

## 接收、单主题派发与续做

协调者先复用目标活动，通过 `receive` 用稳定 request-id 原子创建 `waiting_external` 待派发运行，再把 task_id/run_id/request-id 交给执行者。执行者核验并续写传入 run；同一请求的并发重试不会重复建 run。真实派发成功后立即关联友好档案、记录观察并读回；失败同样记录，不等长任务完成才补写。`start` 保留旧行为，仅用于已经开始的执行；旧版两步兼容路径不是原子操作。

一个执行会话同时间一个主题。同目标实现、测试、修复、交付复用活动；完成 run 不重开。旧执行者正忙于别的目标时，用可用的新执行者读取交接摘要；资源不足就明确等待。`dispatch-check` 只是窄证据冲突提示，不是平台锁，`unverified` 也不代表空闲。独立审核者不参与制作被审作品。

阶段摘要保留用户可见目标、约束、成果、验证、限制与下一步，不保存原始内部记录或运行路径。长期上下文没有固定保证。界面保留每个 run 的已分派身份，观察过期只改变状态可信度；不能让旧等待 run 的参与者冒充当前 run 的负责人。

`receive` 的事务和重试去重属于本地命令强制检查；接收时机、派发前平台核查、单主题及独立审核属于执行者 workflow。安装 Skill 不保证平台每次自动触发，也不会创建自动派发器。精确命令与兼容边界见 [工具契约](../skills/manage-development-activities/references/tool-contract.md)。
