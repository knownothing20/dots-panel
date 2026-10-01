# 任务与项目活动接入

面板是只读展示端；通过本机 CLI 主动写入少量经过筛选的信息。没有远程执行接口、定时器或自动任务扫描。不要把用户聊天、内部代理工作记录或 shell 原始输出直接倾倒到数据库。

```sh
SOURCE=/absolute/path/to/dots-panel
DATA=/absolute/path/to/dots-panel-data
panel() { sh "$SOURCE/scripts/start.sh" --data-dir "$DATA" "$@"; }
panel register example-check --name '示例检查' --project '示例项目'
RUN=$(panel start example-check --note '执行已授权检查')
panel log "$RUN" '校验输入完成'
panel heartbeat "$RUN"
# 新运行成功前，先记录实际产出、检查范围、依据与限制
panel closeout-record "$RUN" --summary '实际产出' --scope '实际检查范围' --verification passed --evidence '实际检查依据' --limits '未覆盖部分' --no-artifact-reason '本任务无需文件产出的真实理由'
panel closeout "$RUN" --record '上一步返回的-record_id' 
panel status
```

`register` 的 ID 唯一，不会默默覆盖；同一个任务可以有多次运行。`start` 只能引用已登记任务。`log` 也更新心跳。结束状态可选 succeeded / failed / cancelled；结束后不允许继续改写运行。面板最近显示 500 个任务、100 次运行和100条步骤，数据库保留全部；当前不提供自动清理策略。

## 活动与开发阶段

每个事件是一条主动记录的项目摘要，不代表完整 ChatGPT / Codex 聊天同步。界面标注这一限制。父助手可把用户已见的需求、决策、阶段进度、测试结果和交付地址记录下来，不能复制隐藏指令、内部笔记、账号资料或密钥。

```sh
panel activity --project '示例项目' --task-id example-check --role user --stage planned --state planned '需求：检查示例输入并给出结果'
panel activity --project '示例项目' --task-id example-check --role assistant --stage implementation --state in_progress '正在实现校验逻辑'
panel activity --project '示例项目' --task-id example-check --role assistant --stage testing --state verified '测试通过；结果已经核对'
```

标准阶段：planned / implementation / testing / review / delivered。状态：planned（尚未开始）、in_progress（进行中）、verified（已验证）。role 为 user / assistant / system。task-id 可省略，此时记录归项目总览。点任务行或下拉选择即可过滤该活动的沟通摘要和阶段。未记录阶段保持未知，不能自动补为完成。

交付链接可写入消息文本，但只能填写确实存在、用户有权打开的地址；界面按纯文本显示，不自动访问、不执行 HTML。尚未迁移的外部工作流不要登记成已运行。默认 register 使用 --tracking-mode manual，按任务最近真实进度摘要或运行更新判断记录新鲜度；超过120秒只显示“进度更新较久，执行状态待确认”，不表示工作停止。明确由程序报告心跳的任务可用 --tracking-mode heartbeat，其心跳过期按120秒判断；项目活动时间是记录时间，非任何未接入外部系统的实时状态。

写入都是本地 SQLite 事务。消息最长 4,000 字符，步骤最长 2,000 字符。CLI 参数可能被同机用户从进程列表短暂看到，不能传入秘密；数据目录也不是密码保险箱。

## v0.2 计划与软件登记

这两个登记表也是运行数据，只通过本地 CLI 写入。计划登记不会创建、启动、暂停或恢复任何真实定时器；state 仅为录入元数据。未有明确外部接入证据时使用 disconnected，next-run 留空。

```sh
panel schedule-register sample-plan --name '示例计划' --project '示例项目' --source manual --state disconnected
panel software-register panel --name 'dots-panel' --description '本地资源与任务面板' --kind dots-panel
```

计划 state 仅允许 disconnected / planned / paused；可选 --next-run 必须是带时区 ISO 时间，只用于展示。没有 running / connected 状态，避免伪造实际调度。source 为主动填写的来源标签，不会被访问。

软件 kind 只允许 dots-panel / python / git；只读检查本项目文件或已知程序是否可用，不扫描目录、不执行注册条目的自定义命令、不暴露可执行文件路径。available 不等于 running，进程运行状态保持未知。原生软件页可以关闭当前面板窗口，重新打开使用本机快捷方式。Web 页明确禁用启动 / 停止，所有 HTTP 仍只读。

四页导航：总览汇总可见资源、活跃记录与计划计数；活动按已登记 task_id 分组并能返回列表；定时任务展示明确登记的元数据与未接入标记；软件展示可用性检查时间、介绍和能力边界。

总览“工作区”展示每个登记任务的最新生命周期状态，可按全部 / 待开始 / 进行中 / 已完成 / 已取消 / 失败筛选。筛选保持到用户再次切换，自动刷新不重置。记录新鲜度是独立辅助提示，不能把 running 改显示成“停止”或其他终态。最近100次运行窗口之外的任务仍使用数据库真实最新状态，不会错误降为待开始；没有运行记录的任务才显示待开始。

## 活动不是新聊天线程

界面“活动 / Activities”指显式登记的开发目标及其进度记录，不代表已创建或绑定原生任务会话。一个开发目标只登记一项活动；设计、实现、测试、审查、交付是同一 task_id 下的里程碑事件，不应拆成多个看似独立聊天的卡片。只有明确验证过绑定链接时才能称为真实会话入口；当前版本可记录已经真实创建的会话绑定并手动接入摘要；不代替官方平台创建 / 读取 / 发送，也不提供完整实时聊天同步。

后端 tasks / activity、task_id 字段与 conversations 路由保留兼容性名称，展示术语不改变数据身份。真实需求和进度摘要始终保存在运行数据目录。

## 真实会话绑定与增量摘要

先由调用方通过当前可用的官方工具创建或读取真实会话，取得实际 thread ID 和确认的环境信息，再把同一开发目标已有的活动绑定到它。这里的 CLI 只校验格式与一致性，不能独立验证远端会话是否存在；创建失败或环境不可用时应保持未绑定。不要使用内部 worker 路径、随机 ID、猜测地址或虚拟任务冒充真实会话。

```sh
panel bind "$TASK_ID" --source-type cloud_thread --thread-id "$ACTUAL_THREAD_ID" --environment-kind cloud --observed-status running --observed-at "$OBSERVED_AT"
panel ingest "$TASK_ID" '面向用户的简短进度摘要' --source-event-id "$ACTUAL_EVENT_ID" --role assistant --stage implementation --state in_progress --observed-at "$SOURCE_EVENT_TIME" --observed-status running
```

变量均由调用方从真实创建 / 读取结果取得，不是可直接使用的示例 ID。observed-at 必须是带时区 ISO 时间，也记录为 UTC epoch；UI 按查看机器当地时间显示。environment-id 仅在确认存在实际 ID 时传入，保存于私有运行数据。source-type 允许 cloud_thread / codex_thread；environment-kind 允许 cloud / desktop / remote，但不能因此切换到用户未授权的环境。

可选 --url 只接受官方工具实际返回、已确认用户可打开的 HTTPS 地址，限定平台域名 chatgpt.com / chat.openai.com / codex.openai.com。没有返回可分享链接时留空，不能拼接 ID 猜链接。Web 不展示或打开 codex:// 深链，不显示私人环境 ID。

同一真实会话仅绑定一项活动；已有活动不允许静默改绑到另一个会话。连续开发继续使用既有 task_id/thread_id，里程碑追加到其时间线。ingest 按 task_id + source-event-id 唯一去重，重复调用返回 duplicate:true、不覆盖既有内容；旧事件不会把最近观察状态倒退。source_observed_at 保留来源时间，ingested_at 记录本机接收时间。

binding 的 observed_status（created / running / completed / failed / interrupted / unknown）是调用方最近观察到的远端状态；不要把一个 turn completed 自动当成整个开发目标完成。同步摘要不会创建或结束本地运行，也不会启动后台同步。sync_mode 始终 manual，UI 明确标注“手动同步摘要，非实时聊天”。

只接入用户可见的需求、决策、进度、检查结果和交付说明；不得复制隐藏指令、内部推理、私人笔记或未经筛选的原始日志。HTTP 接口仍然只读，面板不直接调用平台聊天 API。可用 `panel bind --help` 与 `panel ingest --help` 查看完整参数。

## 等待、交付与验证

`transition` 支持 waiting_user、waiting_external、paused、awaiting_review，并要求原因、依据和下一步。不要用 idle 代表任务完成。

正式输出由 `artifact-add` 归档；`artifact-designate` 标记草稿或最终稿，`artifact-delivery` 只记录有依据的发送、打开或验收观察，不会实际发送文件。`closeout-record` 与 `closeout` 为新运行检查完成依据；历史导入记录保留原状态，并明确标识恢复来源及缺口。

`doctor` 只读显示本机检查和分别登记的账户安装、定时器配置/执行观察，不会自动配置服务。

## External result snapshots (read-only)

`schedule-result-import SCHEDULE_ID` reads one bounded JSON observation from standard input.
It never fetches upstream, signs in, creates a scheduler, or changes any platform task.
The caller must first read the exact result files through an authorized connector and
record their returned blob hashes and verified URLs. A local refresh only rereads DATA.

The normalized `dots-panel.external-result.v1` envelope has exactly these fields:

- `schema_version`, `repository` (`owner/repository`), `ref`, `status_path`, `index_path`
- `checked_at`: explicit timezone ISO timestamp of the upstream check
- `fetch_error`: null on success, otherwise a bounded sanitized error description
- `observation`: null on failure; on success an object containing:
  - `latest`: `calendar_date`, `run_id`, `collected_at`, `status`, `selected_count`, `stale`
  - `index`: `generated_at`, `entry_count`, `latest_date` (null for an empty index)
  - `evidence`: `status_sha`, `index_sha`, `status_url`, `index_url`

`stale` preserves the source's explicit boolean, or null if no flag was supplied.
Never infer that a source without a stale flag is fresh. Result dates and the local
check timestamp remain separate. The newest attempt can be newer than the accepted
history index; a degraded attempt may be omitted from that index by the producer.

The import rejects unknown schema/fields, duplicate JSON keys, oversized input,
unsafe repository paths/URLs, future checks, older checks, and silent reassociation.
A failed check preserves the last good snapshot with an explicit error; invalid
input performs no write. To record a failed fetch, provide the same reference and a
new check timestamp with `observation:null` and a sanitized `fetch_error`.

Only reference metadata and the normalized observation are saved in private DATA.
No raw reports, credentials, platform prompts, or account IDs are imported. Successful
result linkage is displayed separately from platform configuration. Without a separately
imported official platform observation, task identity, enabled state, schedule, and
next due time remain unknown. A result file is never evidence of scheduled execution.
The underlying manual registry row is preserved and is not treated as scheduler truth.
There is no background upstream polling and no network dependency in either viewer.

For reinstall/restore, retain both SOURCE and private DATA (including the SQLite
file using a consistent stopped-service copy or SQLite backup). Restoring DATA
restores references and observed snapshots, not the real platform task. Reinstalling
this viewer does not overwrite, clone, create, pause or resume the platform schedule.
A fresh installation without DATA starts without these private associations.


## Platform scheduler observations (read-only)

`schedule-platform-import SCHEDULE_ID` imports one `dots-panel.platform-schedule.v1`
JSON object from standard input after an authorized official platform read. This
local CLI never calls a platform, configures a scheduler, or changes a task prompt.
Register the local metadata row first. The exact fields are:

- `schema_version`: `dots-panel.platform-schedule.v1`
- `platform`: `dot`; `task_id`: the actual returned platform identity
- `title`, `enabled` (boolean or null), `timezone` (valid IANA name)
- `timing_mode`: `exact_schedule`, `flexible_schedule` or `condition_watch`
- `schedule`: original bounded VEVENT string or null when unavailable
- `last_run_at`, `next_run_at`: original timezone ISO timestamps or null
- `observed_at`: timezone ISO timestamp when the official read was performed

A supported VEVENT has exactly BEGIN:VEVENT, DTSTART, RRULE and END:VEVENT lines.
The validator accepts a conservative recurrence subset; unsupported syntax must be
reported rather than silently rewritten. It rejects duplicate recurrence fields,
invalid date/time ranges, timezone mismatch and unrelated VEVENT properties.

Imports reject older observations, conflicting same-time observations and silent
identity replacement. Exact retries are idempotent and preserve import time. A
platform identity can be associated with only one local row. The existing local
registry metadata and external result snapshot remain unchanged. Snapshot output
adds `platform_observation`, with epoch `observed_at` and `synced_at`, `sync_mode`
`manual`, and `first_scheduled_execution` `unverified`. A platform last-run timestamp
is not proof that the work or delivery succeeded. In particular, a manual trial
result must not be treated as the first scheduled execution of a newly created task.

Display next run as unknown when the official tool did not return it, even if the
recurrence appears calculable. UI refreshes reread local data only. A fresh official
read and explicit import are necessary for a newer observation; no credentials,
account prompts, poller, timer or authentication server are part of this adapter.

Consistent private DATA backups preserve both platform associations and result
references. Restoring them only restores observations, never creates or clones
a real platform task. Recovery must recheck current official state before claiming
it is enabled or its next execution is known.
