# 私有备份与恢复展示

总览提供紧凑状态，设置展示目的地、可读路径和证据明细。此功能只读取显式配置的本机历史资料，不联网、不扫描备份目录、不上传、不恢复、不运行调度器。不存在配置时显示未配置，不创建空文件或推断某个默认目录。

## 显式私有配置

授权安装者在独立私有 `DATA/config/backup-status.json` 写入以下格式。这里全部是占位符，不能直接作为生产身份。真实目录、Library 文件身份、私有文件夹名称必须来自本安装已核验的实际配置，不能填其他用户的固定 ID。

```json
{
  "schema": "dots-panel.backup-status-config.v1",
  "state_dir": "/absolute/private/backup-state",
  "destination_label": "Your private backup folder",
  "destination_path": "/Your private backup folder",
  "index_library_file_id": "libfile_REPLACE_WITH_VERIFIED_ID",
  "stale_after_seconds": 7200
}
```

`state_dir` 是 SOURCE/DATA 外的独立绝对目录；不是远端存储。DATA、config、STATE、operations 目录应为当前用户私有目录，文件为私有普通文件（通常目录 0700、文件 0600）。读入口逐个目录组件拒绝符号链接，不自动 chmod、不跟随路径逃逸、不接受 FIFO 或设备文件。配置拒绝未知字段、重复 JSON 键、不受支持的版本、含控制符文本；输入字节上限固定。

目的地路径按原文只作可选择/复制文本展示，不生成自创 Library URL、不让配置成为任意外部链接。真实 IDs 仅存私有配置；不要把私有配置加入 GitHub 或演示截图。

## 已核验恢复点

只读取精确 `STATE/latest-committed.json`，不递归寻找任意 `committed-index.json` 或接管 guard。使用已安装备份协议的纯校验器验证：

1. v2 committed envelope 和 matching CAS receipt，包括固定 Library ID、版本、操作和候选原字节 SHA/大小
2. 完整 manifest、policy/runner 固定引用和完整对象依赖关系
3. 当前 DATA 的 `config/backup-identity.json` 与 manifest 安装身份一致
4. 完整恢复核验记录必须同时确认 bytes、policy、runner，并匹配 manifest SHA、逻辑内容 SHA、数据库元数据、文件计数及有效时区时间

缺失、不匹配、prepared/candidate_ready 或只有候选索引都不能提升为成功。页面仅检查保存的证据，**不重新下载远端数据，也不独立证明提供这些回执的平台事实**；当前远端状态始终为未实时查询。最后快照时间与恢复核验时间分开，使用面板的显示时区。较旧表示证据年龄，不自动意味着任务或备份失败。

快照逻辑体积仅为该核验 manifest 的完整成员字节和，与其快照时间、核验来源共同展示；它不是云端去重后的物理占用，更不是 Library 总配额或剩余容量。没有受支持的平台容量证据时，配额与剩余量保持未知，不用本机磁盘或清单大小推算。

受支持的 `hydrate-index` 可从真实远端回读重建本机 envelope；UI 标明该来源，不能把它宣称为原历史提交过程已独立证明。不得为了让状态变绿而手工伪造 envelope 或回执。

## 最近尝试观察

这个可选文件是经过授权的备份执行者保存的最少观察，不由 UI 生成：`STATE/operations/backup-observation.json`。没有它时“最近尝试”保持未知，旧的通知去重文件不能被猜成此格式。

```json
{
  "schema": "dots-panel.backup-observation.v1",
  "checked_at": "2026-01-01T00:00:00Z",
  "result": "failed",
  "stage": "prepare",
  "error_type": "source_busy",
  "recovery_point_sha256": null
}
```

- result：failed / unavailable / running / committed / unchanged
- stage：preflight / prepare / verify / upload / readback / index / commit
- checked_at：真实观察时间，必须含时区，不能捏造新的观察时间
- error_type：小写稳定错误类别或 null，不接受原始报错、私人对话、路径、凭据
- recovery_point_sha256：已知恢复点 SHA-256 或 null，不是成功凭证

执行者仅在有真实变化时原子写入（同目录临时文件、完成后替换）；不改变数据库或平台计划。failed/unavailable 显示受阻并保留上个核验点；running 仅表示未完成尝试被记录，不表示执行者当前仍活跃。旧于最新恢复核验的失败不会覆盖较新点。committed/unchanged 观察本身不能建立“已核验恢复点”，也不会刷新旧快照时间。无效观察只标记不可核验，不覆盖已核验历史。

此观察文件与通知去重文件职责不同；写观察不代表消息已接受，也不重置通知去重。不要把日志或完整会话写进观察。

## 独立的任务巡检健康记录

任务停滞检查与备份是两个独立结果。总览与设置分别显示，不从备份快照时间、UI 五秒刷新、心跳或执行者待命推断监控有效。

只读入口另外读取 `STATE/operations/task-watch-observation.json`。该文件仅由实际完成任务只读检查的执行者原子保存，不由 UI 写入；缺失显示未核验，访问不到 STATE 显示巡检记录不可用。格式严格，不接受额外字段或私人任务文本：

```json
{
  "schema": "dots-panel.task-watch-observation.v1",
  "status": "checked",
  "checked_at": "2026-01-01T00:00:00Z",
  "last_success_at": "2026-01-01T00:00:00Z",
  "error_type": null
}
```

status 为 checked / failed / unavailable；checked_at 是真实尝试结束时间。只有实际只读任务检查成功时，status 才能为 checked，last_success_at 必须等于该真实检查时间，且 error_type 为 null。失败/不可用保留已有可核实的 last_success_at；没有证据则为 null，不填当前时间。错误仅记录小写稳定类别，不包含完整报错、任务内容或会话。

超过私有配置中的 stale_after_seconds（默认两小时）显示旧观察，不自动断言监控永久停止。较新的失败不抹掉最后成功时间；备份成功也不清除巡检失败。每轮真实只读检查完成后可以更新此 STATE 观察以反映监控新鲜度，但不能写 DATA 心跳或把它算成任务工作进展，避免自触发数据库备份。此本机历史观察不证明调度器以后必定触发。

## 恢复与持久性

本机状态/cache 不是异地备份。界面没有恢复/删除/重新运行按钮；备份包、依赖、恢复索引只按备份协议处理。真正恢复只能先写全新私有目录，核对每个文件、SQLite 完整性/外键/表计数，并核对备份之后的变更缺口，再按用户授权切换。GitHub 仅保存通用源码；DATA、索引、包、截图和真实私有路径不得公开。

云电脑可以保留状态，但原工作区目录曾出现不可用，原因未确认。这不是“每天重置”的证据，也不是任何路径永久保存的保证。可恢复范围截至最后成功且经过核验的快照；平台会话、账户技能和调度器均不自动复制。

## 测试与验收

`tests/test_backup_status.py` 覆盖未知、失败保留上个成功点、较旧、错误身份/索引、未提交、回执与恢复核验缺失、符号链接、宽权限、FIFO、超大/重复键、无网络与无写入。

原生与 Web 应核验：中/英文、显示时区、窄屏长路径换行、复制路径、配置缺失/有效/失败三态、五秒增量刷新不丢设置输入焦点或滚动位置、不能据刷新时间把远端标成实时成功。UI 自动测试不代替实际桌面/浏览器截图验收。
