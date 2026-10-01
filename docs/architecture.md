# 架构

Python 标准库 `ThreadingHTTPServer` 提供固定静态资源、GET /health、GET /api/state。SQLite 保存 opt-in tasks、runs、events、activity、schedules、software、task_bindings。写入只允许本机 CLI，不调用任意 shell，也不替用户执行登记任务。

浏览器每 5 秒拉取快照；防止请求重叠，4 秒超时后显示离线并保留最后采样时间。CPU 使用率来自 `/proc/stat` 两次请求间差分；内存来自 `/proc/meminfo`；磁盘通过 `shutil.disk_usage(DATA)`；系统信息仅系统类别、架构与 Python 版本。cgroup v2 的 cpu.max / memory.max 仅按当前命名空间可读值报告，不宣称发现所有嵌套上限。

阶段状态来自显式 activity 事件，不根据消息含义猜测完成。任务列表点击选择以 task_id 过滤阶段事件；未关联的项目摘要仍可在总览看到。运行 stale 是记录新鲜度判断，与终态分开。tasks.tracking_mode 默认 manual，progress_updated 取运行更新与关联任务最新摘要时间中的较新者；只有显式 heartbeat 模式才仅看运行心跳。运行状态有限状态机：running → succeeded / failed / cancelled。已终结运行不可重开。

无依赖安装、构建工具、容器镜像、Redis 或数据库服务。静态页面保存在 web，Python 在 src/dots_panel，运行数据严格在仓库外。启动脚本只设定本项目 PYTHONPATH。数据目录 config/tmp 预留，不扫描或自动填充。

局限：没有分布式采集、权限账户、自动运行器、完整聊天同步、分页 UI 或自动数据清理。仅适合受信任的个人本地轻量记录场景。服务与数据可用性随宿主云运行环境生命周期变化。

原生桌面视图使用 Tkinter，直接读取本地 SQLite（mode=ro），不发送 HTTP 请求。选择任务后展示运行、阶段与项目沟通摘要。它不是网络代理，不改变浏览器策略。Web 视图和原生视图共用数据结构，各自展示环境采样。

v0.2 Web 使用七个 hash 路由与独立页面容器；不会把全部功能堆到一个滚动页。计划 registry 不接任何调度执行器；软件 registry 仅允许固定 kind 的只读可用性探测，没有可写 HTTP 动作端点。

## 轻盈卡片视觉与交互

Web 采用任务卡优先的双列布局，资源与计划以紧凑卡片放在下方；活动列表与其他登记页保持相同视觉体系，详情使用轻量阶段标识和事件卡片。暖白、浅薄荷、白色内容面板与低强度静态阴影提供层次，只有侧栏使用轻度 backdrop blur；不支持 blur 时退回实色。正文不通过容器 opacity 降低可读性，无永远运行的动画，并尊重 prefers-reduced-motion。

筛选按钮和搜索均只在本地快照上工作，不产生 HTTP 写入。卡片阶段条仅表示“已验证 / 已记录阶段”比例，不能作为整体任务完成度估计。生命周期标识始终独立于进度新鲜度警告。自动刷新保留筛选与搜索，已聚焦筛选按钮恢复焦点。

滚动条使用浏览器原生滚动行为：Firefox thin、WebKit 透明轨道与圆角浅色 thumb，悬停时提高可见度；保留滚轮、触摸、键盘操作，不使用脚本隐藏或替换滚动。强制高对比模式恢复系统颜色与标准宽度。

SQLite 连接由显式上下文管理器持有：正常退出提交，异常退出回滚，finally 总是关闭连接。原生只读连接同样及时关闭；回归测试覆盖正常 / 异常退出与连续50次快照，避免长期刷新堆积连接或文件描述符。

会话绑定只是一对一的真实 ID 元数据映射，保存在 task_bindings；不持有平台凭据或调用远端 API。增量摘要使用 activity_source_event 唯一索引去重，来源时间和入库时间分开保存。所有状态都是最近一次显式观察，手动摘要同步不会替代真实执行状态或创建会话。
