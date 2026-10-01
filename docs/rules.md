# 项目规则

规则单一来源为 `src/dots_panel/project_rules.json`。原生和Web通过同一snapshot读取，双语内容和规则版本在此文件维护。修改规范时同时核对代码、文档、测试和任务skill引用，不在两个界面复制一套规则。

- enforced（程序校验）：仅指对应面板CLI已经实施的检查，不是操作系统全局强制策略
- workflow（执行约定）：需要执行者遵循，页面本身不会强制执行
- planned（待落地）：尚未实现，不得展示为已创建目录或已接入功能

此规范仅涵盖项目文件归档、软件和任务流程，不展示助手内部指令，不授予账户权限，不覆盖平台安全要求。收件箱、共享资料区、可移植软件统一安装、通用软件发现仍为规划，不自动移动旧文件或执行程序。

私有部署可登记经过核验的个人任务skill链接：

`sh scripts/start.sh --data-dir "$DATA" rules-skill --url "$VERIFIED_SKILL_URL"`

仅允许官方ChatGPT技能详情链接，存储于私有DATA，源码不预置用户的skill ID。该操作只登记链接，不安装skill、改变其权限或后台联网。

每个页面可手动刷新，原生和Web默认每5秒读取面板状态；切换页面也重新读取。最近刷新时间表示读取本地记录成功，不代表任务执行器刚上报或平台实时连接。手动刷新不叠加定时器。

一次性HTML代码作品可作为other归档，但面板不会渲染、运行或HTTP提供HTML。用户须经正常文件交付后自行在可信浏览器打开。PNG和纯文本预览的安全白名单保持独立。

## 用户安装的 Skill 清单 / User-installed Skill catalog

规则页在项目规范上方展示紧凑双语清单：名称、用途、使用场景、可选管理入口、最近人工观察时间、可读取状态与保存内容核验说明。仅主动登记用户安装、用户编写的 Skill；不枚举或展示系统 Skill、内部指令、原始 Skill 文本或私有操作记录。所有账户特定资料存放在独立 DATA 的 SQLite user_skills 表，源码不预置账号链接或实际条目。

```sh
sh scripts/start.sh --data-dir "$DATA" skill-upsert example-skill \
  --user-installed --name '示例 Skill' --name-en 'Example Skill' \
  --purpose '示例用途' --purpose-en 'Example purpose' \
  --when-used '示例使用场景' --when-used-en 'Example situation' \
  --observed-at '2026-01-01T00:00:00Z' --status unknown
```

- `--user-installed` 是调用方对用户安装/编写范围的明确确认，不是自动身份验证；先核实范围再登记。CLI 无法判断一段文字的真实来源，禁止录入系统或内部内容
- 同 id 完整替换记录，不新建重复卡片。更新须带更晚的真实观察时间；同时间同内容重试幂等，同时间冲突与倒退时间拒绝。时间必须明确时区，不得超过当前时间5分钟
- `--name`、`--purpose`、`--when-used` 必填；对应 `--name-en`、`--purpose-en`、`--when-used-en` 可选。英文缺失回退原文，不请求外部翻译
- `--status unknown|available|unavailable` 只描述所标时间的人工可读取观察，不表示已启用、始终触发或正在运行
- `--version-status unverified|saved_verified` 默认未核验。saved_verified 必须同时是 available，并带事实性 `--version-note`；可附 `--version-note-en`。它仅表示保存内容已经检查，绝不表示最新版本、自动同步或当前会话已重载。没有版本号就不编造版本号
- `--url` 可选，只接受调用方已核验的 `https://chatgpt.com/skills?skill_id=…` 管理链接。禁止凭据、额外参数、端口、片段与其他域名。界面再次检查；Web使用noopener/noreferrer，仅点击时访问。CLI格式通过本身不证明远端存在
- 更新是完整记录替换：省略英文、版本说明或URL会清空旧值，避免残留过时观察；更新前读取 status.rules.skills 并显式保留仍有效字段
- 老数据库只读时缺表显示空清单；运行已授权CLI会创建空表，不自动导入旧规则链接。原 rules-skill 兼容，未被卡片覆盖的旧链接仍显示
- 两个界面沿用每5秒读取和手动刷新；刷新只读取本地登记，不接入账号、不查询网络。此清单不安装、更新或删除Skill，不更改权限

Verify after changes: `PYTHONPATH=src python3 -m unittest discover -s tests -v`, `node --check web/app.js`, `node tests/test_skills_web.js`, and the existing locale/workspace JavaScript tests. Check compact rows and Chinese/English switching in the actual native desktop; Web rendering tests do not substitute for browser visual QA.

### 开源安装边界

下载或安装本开源项目只得到清单功能和空表，不会携带任何账户的 Skill、管理链接、自动化任务或账户授权。`skill-upsert` 只登记展示元数据，既不安装 Skill，也不创建或启用自动化；`schedule-register` 同样只登记计划信息。接收者需在自己的账户中分别安装所需 Skill、授权或创建自动化，再手动登记经核实的摘要；复制源码不能代替这些步骤。
