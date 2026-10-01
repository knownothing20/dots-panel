# Agent 安装与接入 Runbook

给接手安装的 Agent：按本页从空环境安装、接入和验收。先读 [AGENTS.md](../AGENTS.md)、[隐私边界](privacy.md) 与 `src/dots_panel/project_rules.json`。本页的演练使用**合成数据与独立 TESTDATA**；不能把示例身份、结果或交付证明写进正式 DATA。

## 复制给 Agent 的安装提示词

把下面整段发送给要执行安装的 Agent。默认只接入本次安装活动；如需导入已有任务或定时计划，请另外明确指定范围。

```text
请在你当前可用的 OpenAI dot 云电脑上安装 dots-panel 和配套的 manage-development-activities Skill：
https://github.com/knownothing20/dots-panel

1. 先确认实际执行环境；不要改用我的本地电脑或另一台云环境。读取仓库当前版本的 AGENTS.md、docs/agent-setup.md、docs/install.md、docs/privacy.md 和项目规则，再开始操作。
2. 检查是否已有安装，为源码 SOURCE 与私有数据 DATA 选两个独立目录并告诉我。已有数据先备份，保留修改；不要覆盖、清空或伪造历史记录。
3. 通过已连接的 GitHub 插件取得项目，按文档安装面板与桌面入口。不使用 GitHub 账户密码登录、凭据回退或 Actions/Workflows；能力不足时明确报告。新增依赖、权限或其他需确认的操作按平台要求处理。
4. 通过当前账户支持的 Skill 安装流程安装配套 Skill，核对保存内容与实际可用状态。不要把仓库里有 SKILL.md、导出 ZIP 或面板里有一行记录当作已安装。保留我其他 Skill 与个人规则。
5. 先在匹配活动登记待派发 run，再真正派发；成功后立即登记实际 Agent 与该 run 关联并读回，失败也及时记录。协调者唯一接收，执行者沿用传入 run，不重复 start。只导入我明确指定的已有活动、执行者和定时任务；不要扫描全部会话，不新建或重复创建平台定时任务。
6. 在独立的合成 TESTDATA 中验证 Agent→活动→进度→文件→交付→收尾，以及平台配置和结果导入。合成数据不能写入正式 DATA；实际发送、读取和验收分别记录，不能伪造证明。
7. 实际打开界面，检查文字、语言/时区、活动排序和文件入口；关闭后从快捷方式重开。没有图形桌面时明确说明未验收，不用测试通过代替实机检查。
8. 最后汇报源码版本、安装位置、面板和账户 Skill 的各自状态、已接入范围、测试结果、私有备份与恢复方法、剩余限制。不要声称能自动发现所有任务、保证 Skill 每次触发或保证云磁盘永久保存。只把公开源码和合成示例用于分享，不公开我的任务记录、数据库、账号资料或备份。
```

完整参数、可执行隔离示例与恢复检查，继续按安装接入指南执行。仅复制提示词不代表这些步骤已经完成。

## 0. 先确定授权、环境和完成条件

- 确认用户指定的是哪台 dot 云电脑；shell、图形桌面、浏览器可能分属不同环境，路径相同不证明同机
- 询问或确认 SOURCE、DATA、是否安装桌面入口、是否安装账户 Skill、哪些真实活动/平台计划/结果来源允许接入。只安装面板不授权扫描账户或全部聊天
- 已有安装先读状态，保留源码改动与 DATA。源码更新与恢复前备份；不覆盖未知文件、不重建平台定时任务
- GitHub 操作仅使用已连接插件；能力不足就报告并保留已准备内容。不使用 GitHub 账户/密码登录、CLI 认证或凭据回退，不操作 Actions / Workflows
- 完成条件分别记录：源码测试、目标桌面、账户 Skill、任务闭环、平台配置观察、首次真实定时执行。某项不可核验就明确留空，不能合并宣称“全部已接入”

## 1. 安装路径与运行时

由安装者把下列两个占位路径替换为确认的绝对路径。两者应彼此独立，任何一个都不要包含另一个。DATA 不进公开仓库；不要默认使用他人账户路径。

```sh
SOURCE=/absolute/path/to/dots-panel
DATA=/absolute/path/to/dots-panel-data
cd "$SOURCE"
python3 --version
python3 -c 'import sys; assert sys.version_info >= (3, 10); print(sys.executable)'
python3 -c 'import tkinter; print(tkinter.TkVersion)'
PYTHONPATH=src python3 -m unittest discover -s tests -v
sh "$SOURCE/scripts/start.sh" --help
sh "$SOURCE/scripts/start.sh" --data-dir "$DATA" doctor
```

Python 3.10+；Tkinter 是可选标准库组件，原生视图要求它和实际图形桌面。没有 Tk 时不要声称原生安装可用，也不要擅自安装系统依赖。`doctor` 只读，不初始化 DATA；初装时 missing 正常。`status` 和其他本地 CLI 会初始化/迁移表，因此旧 DATA 应先备份。

在**目标桌面自己的终端**核对 `id -u`、`printf '%s\n' "$HOME" "$DISPLAY"`、解释器和 SOURCE 可见性，仅用于私下确认，不抄到公开报告。默认安装器优先已有且可用的系统 Python/Tk；需要时用经过核验的 `--python`。详细字体检查见 [安装文档](install.md)。

以下是实际部署步骤，会写目标用户的应用快捷方式，需在已授权的目标桌面执行：

```sh
sh "$SOURCE/scripts/install-desktop.sh" --data-dir "$DATA"
python3 "$SOURCE/scripts/desktop.py" open --data-dir "$DATA"
```

安装器不会补装依赖、创建自启动或平台计划。原生界面只读任务 SQLite，但会将显示偏好存到 DATA/config/ui.json。必须截图确认实际窗口、中文/英文、导航和文件入口，再关闭并从快捷方式重新打开。仅通过测试、导入 Tk 或发现 `.desktop` 文件都不能代替桌面验收。无法访问实际桌面时交付“源码/CLI 已核验，桌面待验收”。

可选 Web：仅同机 IPv4 loopback，HTTP 只读；无需 Web 服务也能用原生视图。

```sh
python3 "$SOURCE/scripts/desktop.py" start --data-dir "$DATA" --port 8765
python3 "$SOURCE/scripts/desktop.py" health --data-dir "$DATA" --port 8765
# 从同机浏览器打开 http://127.0.0.1:8765
python3 "$SOURCE/scripts/desktop.py" stop --data-dir "$DATA" --port 8765
```

健康检查通过只证明 HTTP 可达；仍需浏览器实际验收。若平台明确拒绝 loopback，不建代理、隧道或公开端口绕过。无平台永久保存、自动唤醒或后台持续运行保证。

## 2. 配套 Skill：源码、账户安装、会话加载分别验收

```sh
python3 "$SOURCE/scripts/workflow-skill.py"
```

输出列出四个文件及 SHA-256。`bundled_source: available` 仅证明源码可用；账户状态仍可能 `not_verified`。需要移交安装包时导出到源码之外的新文件：

```sh
python3 "$SOURCE/scripts/workflow-skill.py" --export "$DATA/workflow-skill.zip"
```

先通过安装/初始化创建 DATA；导出拒绝覆盖已有 ZIP。导出也不等于安装。

**账户安装操作清单（不是固定账户路径脚本）：**

1. 取得用户对安装 `manage-development-activities` 的明确授权，将导出的 ZIP 或这四个源码文件提供给目标账户的 Agent
2. 请求：“请将这个 manage-development-activities Skill 安装到我的个人 Skills，并核验保存内容；不要创建任何定时任务。”目标 Agent 应读取当时平台提供的 skill-creator/Skill 安装说明，使用该账户当前支持的个人 Skill 保存安装流程；不要照抄另一个账户的目录、ID 或管理链接
3. 核验保存后的 Skill 名称、正文及三个 references，与导出哈希对应；若平台规范化 frontmatter，逐文件检查有无实质规则差异。只检查本 Skill，不上传 DATA、私有规则或第三方 Skill
4. 通过平台当前 Skills 列表/读取或界面确认可用且启用；回报**实际返回**的管理链接。显示尚未刷新时刷新或重新打开 Skills 页面，不假造成功
5. 在后续任务明确引用该 Skill，核验该轮实际读取及按第 3 节完成登记；“安装成功”不证明本轮已加载，已加载也不保证任何未来任务必定触发

如果当前产品没有受支持的安装入口或权限，停止在“可移植源码/ZIP 已准备”，说明缺少哪一步。仓库没有跨账户安装器；`skill-upsert`、`skill-origin`、`installation-observe` 都只写面板元数据，不能替代账户安装。实际安装后，按各命令 `--help` 记录真实 Skill 来源、可用性和人工检查依据，再用 `doctor` 复核。未核验不要填 `saved_verified` / `verified`。账户个人规则与项目 bundled Skill 分开管理。

## 3. 接入 Agent、活动、进度与文件

### 真实任务的决策顺序

先通过 `status` 查看 tasks、bindings、open_runs、current_runs、agents、agent_run_assignments。读取已绑定真实会话的当前结果，比较目标后再决定：

- 同一目标的实现、测试、修复、交付沿用一个 task_id；同一已接收请求的阶段与补充继续已有 run；新可执行请求用新 request-id接收为新run。已结束 run 不重开，后续工作仍在同一 task_id 下
- 新目标才 `register`。登记失败先查是否已经成功，不重复派发执行者
- 协调者先用 receive 与稳定 request-id 原子登记 waiting_external 待派发 run，并把 run_id/request-id 交给执行者；同请求重试幂等重用。实际派发前核对单主题占用，实际派发后立即登记友好稳定 profile、run关联并读回。执行者不得自行重复 start。人工记录观察时间。profile 不创建执行者；pending 初始化填 unknown，结束本轮填 idle
- `agent-assign` 表示主负责人；`agent-run-assign` 为具体 run 增加参与者。并行多个执行者可关联同一 run，或同一活动中的各自 run；不要为了显示新参与者替换原负责人
- 仅实际返回持久会话 ID 才用 `bind`；没有持久会话保持无绑定。禁止写内部 native worker 标识、运行路径、原始对话或隐藏推理
- `ingest` 仅导入经过筛选的用户可见事件；稳定 source-event-id 保证重试去重。绑定和观察不能证明实时同步。精确参数及边界见 [任务接入](task-integration.md#真实会话绑定与增量摘要)

### 可执行的隔离闭环演练

以下代码块按顺序在同一个 shell 中执行。只改 SOURCE；`mktemp` 创建独立 TESTROOT，不使用正式 DATA。这些是合成流程观察，并非真实平台任务或真实用户收件证明。

```sh
set -eu
umask 077
TESTROOT=$(mktemp -d)
TESTDATA="$TESTROOT/data"
export TESTROOT TESTDATA
panel() { sh "$SOURCE/scripts/start.sh" --data-dir "$TESTDATA" "$@"; }
now() { python3 -c 'from datetime import datetime,timezone; print(datetime.now(timezone.utc).isoformat())'; }
jsonfield() { python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"; }
panel register setup-demo --name '合成安装验收' --project 'Synthetic setup'
RUN=$(panel start setup-demo --note '隔离的CLI流程演练')
panel agent-register setup-worker --name '示例执行者' --name-en 'Example worker'
panel agent-observe setup-worker --status running --observed-at "$(now)" --note '合成测试：CLI流程正在执行'
panel agent-assign setup-demo setup-worker --work-type testing
panel agent-run-assign "$RUN" setup-worker --work-type testing
panel task-init setup-demo
printf 'Synthetic check: input A passed\nSynthetic check: input B passed\n' > "$TESTDATA/tasks/setup-demo/tmp/report.txt"
COUNT=$(python3 -c 'import pathlib,os; print(len((pathlib.Path(os.environ["TESTDATA"])/"tasks/setup-demo/tmp/report.txt").read_text().splitlines()))')
panel progress-update "$RUN" --current-step '核对合成报告' --result '报告已生成' --next-step '登记正式文件' --evidence '逐行读取合成报告' --completed "$COUNT" --total 2 --unit checks --source-event-id setup-report-v1
# 完全相同的重试应返回 deduplicated:true，而非再造一条里程碑
panel progress-update "$RUN" --current-step '核对合成报告' --result '报告已生成' --next-step '登记正式文件' --evidence '逐行读取合成报告' --completed "$COUNT" --total 2 --unit checks --source-event-id setup-report-v1
ARTIFACT=$(panel artifact-add setup-demo "$TESTDATA/tasks/setup-demo/tmp/report.txt" --title '合成验收报告' --kind report --slug setup-report | jsonfield id)
panel artifact-designate "$ARTIFACT" --designation final --evidence '合成测试已逐行检查两条结果'
# 仅合成测试模拟交付记录；真实任务必须先通过授权渠道完成发送并取得依据
panel artifact-delivery "$ARTIFACT" --status sent --evidence '合成夹具：模拟发送成功；未向真实用户发送' --observed-at "$(now)"
RECORD=$(panel closeout-record "$RUN" --summary '合成流程完成' --scope '两条报告记录与归档' --verification passed --evidence '本隔离CLI演练已执行并核对' --limits '不证明桌面、账户Skill或真实交付' --artifact "$ARTIFACT" | jsonfield record_id)
panel closeout "$RUN" --record "$RECORD"
panel agent-observe setup-worker --status idle --observed-at "$(now)" --note '合成测试流程结束'
panel status > "$TESTROOT/status.json"
python3 - <<'PY'
import json, os
s=json.load(open(os.environ['TESTROOT']+'/status.json'))
assert s['tasks'][0]['id']=='setup-demo'
assert s['runs'][0]['status']=='succeeded'
assert len(s['progress_updates'])==1
assert len(s['artifacts'])==1
assert s['agents'][0]['status']=='idle'
print('Synthetic activity, progress deduplication, artifact and closeout verified')
PY
```

真实任务不得照抄测试结论。进度要写当前步骤、已得到的结果、下一步和证据；只有工具实际测得数量时才填 completed/total/unit，不根据耗时估算百分比。普通步骤无需计数；heartbeat 仅代表一次心跳，不代替实际进展。

文件先核验再 `artifact-add`；返回的 ID、relative_path、size、sha256 用于复核。输出在 `DATA/tasks/<task-id>/outputs`，输入与草稿分别在 inputs / tmp。面板归档不发送文件。必须实际交付后才记录 sent；用户打开和接受分别需要证据。需交付但尚未发送时用 `transition --status awaiting_review` 等合适等待状态，并填写原因、证据、下一步，不伪造 sent 来通过 closeout。

`closeout-record` 应引用该任务已核验的 artifact；仅确实无需文件时用 `--no-artifact-reason`，不能拿它绕过未发送文件。closeout 校验最新记录、文件内容哈希、final 指定和交付记录。failed 验证不能成功收尾；untested 虽是可记录状态，也必须如实披露未验收范围。终结本 run 后，核对同活动其他未结束 run，不能把一名执行者 idle 或最新 run 成功当成整个目标完成。

## 4. 平台定时任务配置与结果数据接入

**两条独立链：**平台官方读取 → 配置观察；获授权的来源文件读取 → 结果快照。面板不读取平台、不自动发现 Agent/活动/计划/结果，不轮询、不执行任务、不创建计划。仅本地展示登记和手动导入结果。

真实接入前：

1. 用当前官方工具读取用户选定的计划，记录实际 task ID、标题、enabled、IANA timezone、timing_mode、原始 schedule、官方返回的 last/next run 与观察时间；工具未返回的可空字段填 null，不自行推算 next_run_at
2. 若用户确实要求新计划，单独通过平台受支持的调度操作完成授权与核验；**安装或恢复不构成创建计划授权**。已有计划只读核验，禁止重复创建
3. 通过已授权连接器读取用户选定仓库/ref/status/index 文件，检查最新尝试与已接受历史索引是否一致；保留工具返回 blob SHA 与已核验文件 URL。无 stale 字段填 null，不能假设 fresh
4. 将筛选后的值写成以下完整 JSON 格式，再导入；所有字段必须存在，无额外字段。凭据、平台 prompt、完整报告和账户配置不进入 JSON

下面是可运行的**合成夹具**；伪造 SHA/URL/task_id 只用于隔离 validator 测试，不能用于生产、公开当作已验证来源或拿来建立真实账户关联。日期故意是过去的测试日期。

```sh
panel schedule-register synthetic-schedule --name '合成计划' --project 'Synthetic setup' --source manual --state disconnected
cat > "$TESTROOT/platform.json" <<'JSON'
{
  "schema_version": "dots-panel.platform-schedule.v1",
  "platform": "dot",
  "task_id": "synthetic-platform-task",
  "title": "Synthetic schedule",
  "enabled": true,
  "timezone": "Etc/UTC",
  "timing_mode": "exact_schedule",
  "schedule": "BEGIN:VEVENT\nDTSTART:20260101T080000Z\nRRULE:FREQ=DAILY\nEND:VEVENT",
  "last_run_at": null,
  "next_run_at": null,
  "observed_at": "2026-01-02T09:00:00Z"
}
JSON
panel schedule-platform-import synthetic-schedule < "$TESTROOT/platform.json"
# 完全一致的重试保留原 synced_at；不同身份/旧观察/同时间冲突会被拒绝
panel schedule-platform-import synthetic-schedule < "$TESTROOT/platform.json"
cat > "$TESTROOT/result.json" <<'JSON'
{
  "schema_version": "dots-panel.external-result.v1",
  "repository": "example/synthetic-results",
  "ref": "main",
  "status_path": "data/status.json",
  "index_path": "data/index.json",
  "checked_at": "2026-01-02T09:00:00Z",
  "fetch_error": null,
  "observation": {
    "latest": {
      "calendar_date": "2026-01-02",
      "run_id": "synthetic-result-run",
      "collected_at": "2026-01-02T08:01:00Z",
      "status": "succeeded",
      "selected_count": 2,
      "stale": null
    },
    "index": {
      "generated_at": "2026-01-02T08:02:00Z",
      "entry_count": 1,
      "latest_date": "2026-01-02"
    },
    "evidence": {
      "status_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "index_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "status_url": "https://github.com/example/synthetic-results/blob/main/data/status.json",
      "index_url": "https://github.com/example/synthetic-results/blob/main/data/index.json"
    }
  }
}
JSON
panel schedule-result-import synthetic-schedule < "$TESTROOT/result.json"
panel schedule-result-import synthetic-schedule < "$TESTROOT/result.json"
# 模拟后续读取失败：保留最后成功快照，另记较新的失败时间与错误
python3 - <<'PY'
import json, os, pathlib
p=pathlib.Path(os.environ['TESTROOT'])
v=json.loads((p/'result.json').read_text())
v.update(checked_at='2026-01-02T10:00:00Z', observation=None, fetch_error='Synthetic source unavailable')
(p/'result-failure.json').write_text(json.dumps(v))
PY
panel schedule-result-import synthetic-schedule < "$TESTROOT/result-failure.json"
panel status > "$TESTROOT/imported-status.json"
python3 - <<'PY'
import json, os
s=json.load(open(os.environ['TESTROOT']+'/imported-status.json'))['schedules'][0]
assert s['platform_observation']['first_scheduled_execution']=='unverified'
assert s['platform_observation']['next_run_at'] is None
assert s['external_result']['observation']['latest']['selected_count']==2
assert s['external_result']['fetch_error']=='Synthetic source unavailable'
print('Separate platform/result observations and retained last-good snapshot verified')
PY
```

Schema 约束以 `platform_schedules.py`、`result_links.py` 为准。输入上限 256 KiB；重复键、额外字段、无时区时间、未来/过旧观察、错误路径及关联替换被拒绝。schedule 支持保守的四行 VEVENT 子集；不能为通过校验悄悄改写真实规则。平台暂不兼容的规则保留原文在私有核验材料中，并报告无法导入；若官方本来没返回 schedule 才填 null。结果 SHA 接受 40 或 64 位小写十六进制，URL 必须与 repo/ref/path 一致。结果导入不是通用 JSON 文件导入器。

**三个独立事实：**平台计划存在/启用；面板已有某时刻的配置观察；首次真实定时执行及预期交付成功。手动试跑、结果文件、last_run_at 或配置导入都不能证明第三项。平台 snapshot 的 `first_scheduled_execution` 当前固定为 unverified。若另用 `installation-observe --component scheduler_execution` 记录经过核验的实际执行证据，它属于 doctor 的独立人工观察，不会改变该字段或调度器。配置变更后要重新核验执行。无需新建计划来“修复”展示。

## 5. 导入已有资料、备份与恢复

### 显式选择来源

当前 CLI **没有通用 import、backup、restore 命令，也没有自动全盘扫描、聊天导入或通用历史库合并**。只有上述两种 schedule 导入和绑定会话的 `ingest`。其他资料先列出用户明确选定的来源、用途、目标 task_id 和文件清单，核对授权再复制到 inputs，成果走 artifact-add。不要为了迁移数据直接拼写 SQL 或重写历史时间线。

存在受支持的原备份格式/清单时先读取并按原格式校验；不存在时不得虚构旧索引或保证完整恢复。源码版本/提交、DATA 快照、文件数量与 SHA-256、创建时间、验证范围、已知缺失应组成私有恢复清单。该清单是部署者备份记录，**不是本产品自带的导入格式**。

### 一致性备份操作顺序

1. 暂停所有对此 DATA 的 CLI 写入/归档，关闭查看器并停止本面板 Web 服务，核验没有继续写入。平台计划与其他软件无需停止或改动
2. 选择源码外新的私有备份目录，不覆盖旧备份；拒绝符号链接/异常权限，保留目录 0700 与文件 0600
3. 复制完整 DATA 的任务文件、配置、日志和其他私有元数据；SQLite 使用标准库 `sqlite3.Connection.backup()` 得到一致性副本，不能运行中只复制主库而忽略 WAL
4. 给备份逐文件建立相对路径、大小和 SHA-256 清单；验证 SQLite `PRAGMA integrity_check`、文件数量、归档 artifact 哈希。源码另存版本记录，不把 DATA 放进源码包
5. 恢复到**新的私有目录**，先核验清单和哈希，再 doctor/status、任务/Agent/关联/结果观察、归档文件、closeout 记录；不覆盖当前唯一可用数据。不要使用恢复出的旧 PID 文件操作进程
6. 重新核对平台任务与执行者当前状态；旧 running/idle 都只是历史观察。恢复不复制、创建、暂停或恢复平台计划。获得授权并完成验收后才将启动入口指向恢复目录

以下只演示一致性 SQLite 副本校验（**不是完整 DATA 备份**），沿用本页 TESTDATA；目标不应已存在：

```sh
python3 - <<'PY'
import hashlib, os, pathlib, sqlite3
root=pathlib.Path(os.environ['TESTROOT'])
source=pathlib.Path(os.environ['TESTDATA'])/'db/panel.sqlite3'
backup=root/'sqlite-check.sqlite3'
assert not backup.exists()
with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as src:
    with sqlite3.connect(backup) as dst:
        src.backup(dst)
        assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert dst.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]==1
        assert dst.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0]==1
backup.chmod(0o600)
print('Synthetic SQLite backup verified:', hashlib.sha256(backup.read_bytes()).hexdigest())
PY
```

保存文件清单仍不能代替恢复演练；数据库中的输出相对路径需要对应 tasks 文件树。备份存储平台/Library 的上传与共享也要遵循用户授权，只分享给确认收件人，禁止公开。

## 6. 最终验收与常见恢复点

- [ ] SOURCE/DATA 分离，所有测试在 TESTDATA，生产无合成夹具
- [ ] Python/Tk 检查、完整测试、CLI schema 示例与去重断言通过
- [ ] 目标桌面实际截图和快捷方式重新打开通过；可选 Web 健康与同机浏览器另行核验
- [ ] Skill 源文件哈希可核对；账户安装/可用与会话加载分别有证据，未知部分未伪填
- [ ] 同一目标只用一个活动，稳定 profile 与 run 参与者关联正确；并行工作不覆盖主负责人
- [ ] 真正步骤/测量进度、已验证 artifact、实际交付证据与当前 run closeout 相互一致
- [ ] 平台原始配置、官方 next run、结果来源和首次真实执行分别核验；未返回数据保留未知
- [ ] 一致性私有备份与恢复文件哈希已核对；恢复未重复创建平台计划
- [ ] 公开变更仅源码、说明与合成示例，无私有账号/目录、原始对话、日志、数据库、凭据或工作截图

常见问题：

- **Already registered**：先查 status；同一活动/profile 复用，禁止换随机 ID 绕过重复检查
- **Unknown run / finished run**：读回当前 run；新工作在同一 task_id 新建 run，不能继续写已结束 run
- **Closeout 缺交付或哈希不符**：核对真实文件和发送结果，修复或登记新版本；不要伪造交付依据
- **旧观察或关联冲突**：回原始官方来源重新读取；保持现有关联，不静默覆盖、删除或重建
- **Unsafe permissions / symlink**：让所有者检查具体路径，不扩大权限、不递归 chmod 未知目录、不绕过拒绝
- **窗口不出现**：查看私有 DATA/logs/desktop.log，核对实际桌面 HOME、DISPLAY 与 Tk 解释器，不反复启动隐藏实例
- **展示没有更新**：界面 5 秒刷新只重读 DATA；需要真实执行者主动登记或新的官方读取与显式导入，刷新不触发平台同步
- **恢复后仍显示旧状态**：先验旧记录来源，再实际观察新状态；无法读取的身份保留 unknown，不声明已恢复执行

结束交接时给出：版本、检查通过项、未完成项、实际入口、私有备份位置、下一步和谁需要操作。不要把界面显示的“已登记”概括成“自动接入全部任务”。
