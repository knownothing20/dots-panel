# 安装与交接

完整的 Agent 安装、Skill 账户验收、隔离任务闭环、计划与结果 JSON 接入及恢复清单，见 [Agent 安装与接入 Runbook](agent-setup.md)。

## 1. 先确认目标机器

用户指定的 dot 云电脑、用户自己的电脑和 shell 沙箱可能是不同执行环境。不要凭相同路径推断桌面可访问：在目标桌面终端验证源码目录与 Python。用平台支持的桌面截图确认应用实际可见。不要扫描其他私人目录。

要求 Python 3.10+、可写独立运行数据目录。桌面默认使用本地 Tkinter 视图直接只读 SQLite，不访问 HTTP；Web 视图另需支持 JavaScript 的浏览器。Tkinter 是 Python 的可选标准库组件，若缺失需报告环境依赖。Linux 的 `/proc`、cgroup v2 提供增强指标；无法读取时显示未知。云电脑生命周期由宿主平台控制，本项目不保证重启后服务持续、自动唤醒或永远在线。

## 2. 先规划两个目录

```text
SOURCE/                    # 克隆的 dots-panel 仓库，仅源代码
  src/dots_panel/
  web/
  tests/
  scripts/
  docs/
  README.md AGENTS.md LICENSE .gitignore
DATA/                      # SOURCE 的同级独立目录，不受 Git 管理
  config/ui.json           # 原生界面语言与时区偏好，首次选择后保存
  db/panel.sqlite3          # 任务、运行、步骤、项目沟通摘要
  logs/server.log           # Web 辅助启动输出；不记录 HTTP 请求路径
  logs/desktop.log          # 原生桌面诊断，不弹出终端
  run/server.json           # 本次启动 PID 与端口，仅用于本地管理
  tmp/                     # 预留临时文件
```

使用不带换行的绝对路径；不要把 DATA 放入 SOURCE 内。两个路径由安装者指定，不要把当前环境真实路径写回仓库。运行时目录按 0700、数据库按 0600 创建；拒绝符号链接与权限过宽的既存运行目录或数据库，需所有者核对处理。既存父目录权限由部署者负责。其他同系统账户或恶意本地进程不属于本项目能完全防护的范围。

## 3. 检查与启动

从用户指定仓库克隆 / 更新代码前检查已有改动和 AGENTS.md；保留用户文件。GitHub 认证用平台原有连接，不把令牌写进文件或命令。无需安装依赖。

```sh
SOURCE=/absolute/path/to/dots-panel
DATA=/absolute/path/to/dots-panel-data
cd "$SOURCE"
python3 --version
PYTHONPATH=src python3 -m unittest discover -s tests -v
sh scripts/start.sh --data-dir "$DATA" serve --port 8765
```

该命令前台运行，可用 Ctrl+C 停止。在同一目标机器访问 `http://127.0.0.1:8765`。不要假定另一云浏览器的 loopback 就是这台机器。若浏览器 / 平台明确拒绝访问，不要绕过限制；先报告并使用该平台明确支持的预览能力。

## 4. 桌面入口与后台管理

在真实桌面的终端执行，确保 HOME 是目标桌面用户：

```sh
sh "$SOURCE/scripts/install-desktop.sh" --data-dir "$DATA" --port 8765
python3 "$SOURCE/scripts/desktop.py" open --data-dir "$DATA" --port 8765
```

安装器写入 `~/.local/share/applications/dots-panel.desktop`；若 `~/Desktop` 已存在则放置同名副本。不创建桌面系统配置、不改变防火墙或安全策略，不安装自启动服务。桌面可能需要用户按平台正常流程信任该快捷方式。快捷方式默认打开原生 Tkinter 面板，直接只读数据库，每 5 秒刷新；不依赖 HTTP，也不会自动启动 Web 服务。首次安装由安装器初始化私有目录。原生视图以只读方式查看已有数据。可在传统、明确允许 loopback 的环境加 --web 打开 Web 版本。

```sh
python3 "$SOURCE/scripts/desktop.py" open --data-dir "$DATA" --port 8765 --web
python3 "$SOURCE/scripts/desktop.py" start --data-dir "$DATA" --port 8765
python3 "$SOURCE/scripts/desktop.py" health --data-dir "$DATA" --port 8765
python3 "$SOURCE/scripts/desktop.py" stop --data-dir "$DATA" --port 8765
```

停止操作仅在 Linux `/proc` 命令行匹配本应用、数据目录、端口时发送 SIGTERM，避免误杀其他进程。若当前系统没有 `/proc`，用前台服务或部署者自己的进程管理。`health` 不读取私有数据。更换端口时所有命令应保持一致。重复启动前先查看健康状态。

## 5. 必须完成的验收

- 单元测试通过；健康检查返回 healthy
- 在目标桌面真正打开原生面板，检查桌面入口能再次打开；Web 版本另行验收
- CPU / 内存 / 磁盘来自当前环境；不可见或不确定的配额明确标为未知
- 空任务时展示空状态，不伪造真实工作；只有用户批准的接入才写入任务
- 用临时 DATA 测试 register → start → log → heartbeat → finish，结束后不将测试数据复制到生产 DATA
- 为某任务写入 planned / implementation / testing / review / delivered 记录，选择该任务能看到对应阶段与时间；verified 只用于已经检查过的事实
- 刷新、重复点击、窄屏布局正常；Web 停止服务后页面标注连接中断，不假报仍在实时更新
- 检查 Git 跟踪清单，不包含 DATA、日志、身份信息、令牌、真实对话或截图

## 6. 升级与卸载

### 安装后的可选每小时巡检与私有备份

安装完成后，Agent 应按[每小时巡检与备份模板](hourly-backup-agent-template.md)询问是否启用；明确用户授权的活动巡检范围、备份范围、私有 Library 目的地、每小时时间安排和失败通知后再配置。安装面板不等于授权持续上传。先读取既有平台计划，复用用户选定的计划，避免重复创建；模板文件、数据库中的计划记录和实际平台执行是不同事实。

使用已验证版本的独立备份模块，先完成首个完整备份和下载后的隔离恢复验证，再保存真实平台计划身份及执行证据。普通周期执行禁止 bootstrap，发现 SOURCE/DATA 缺失不得初始化空库或覆盖最后成功索引。公开代码不得携带真实目录、Library 身份、计划身份和任务内容；私有配置由部署者保存。面板不自带云端调度器，不使用 GitHub Actions，也不保证宿主磁盘持久或每轮准时成功。

升级前停止服务，将 DATA 按用户要求备份到私有目录；查看源码改动后在原 SOURCE 更新，重跑测试再启动。SQLite 兼容字段升级在启动时完成。不要覆盖或清空运行库。

卸载只移除本项目的快捷方式和源码，删除前需有用户授权。默认保留 DATA；不要把“卸载应用”当作永久删除任务记录的授权。

## 常见问题

- 端口占用：检查已运行服务或选择空闲 loopback 端口；不扩大监听地址
- Python 缺失：报告缺少 Python，不私自安装大型环境
- 浏览器无法连接：确认浏览器与服务同机、服务健康、使用正确端口；尊重平台拒绝，不建代理或隧道
- 图标不存在：检查快捷方式 Icon 指向当前 SOURCE；源码移动后重新安装入口
- shell 能看到而桌面看不到：核对目标环境与 HOME，回到真实桌面终端运行安装器
- 记录较旧：默认 manual 模式只表示近期没有进度更新；明确 heartbeat 模式才显示心跳过期。两者都不等于失败或停止，不会自动重跑任务

## 界面语言

Web 视图提供 Auto / 中文 / English。Auto 跟随浏览器的系统语言；zh 开头使用中文，其他语言使用 English。选择只保存在当前浏览器 localStorage，不上传、不写入服务数据库。任务名称、项目名称、步骤与沟通摘要始终保持原始语言。浏览器禁止本地存储时仍可在当前页面切换。

## 原生界面字体与 Python / Tk 兼容性

桌面入口默认优先选择已经安装的 `/usr/bin/python3`（要求 Python 3.10+ 且能导入 Tkinter），否则尝试当前解释器。也可以显式指定经过验证的解释器：

```sh
sh "$SOURCE/scripts/install-desktop.sh" --data-dir "$DATA" --python /absolute/path/to/python3
python3 "$SOURCE/scripts/desktop.py" open --data-dir "$DATA" --python /absolute/path/to/python3
```

某些桌面组合中，打包的 Tk 9.0 与系统中文字体出现渲染兼容问题，而系统 Python / Tk 8.6 正常；这不是对所有 Tk 9.0 环境的结论。先在真实桌面运行 `python3 -c 'import tkinter; print(tkinter.TkVersion)'`，再用目标解释器运行 `PYTHONPATH="$SOURCE/src" /absolute/path/to/python3 -m dots_panel.desktop_view --font-diagnostics` 并截图检查。优先使用已有可正常显示的解释器；不要擅自安装字体或改变系统安全配置。重新安装快捷方式可更新其解释器选择。

原生桌面同样提供 Auto / 中文 / English。Auto 按 LC_ALL → LC_MESSAGES → LANG 读取系统语言，中文 locale 使用中文，其他使用 English。选择只保存在独立 DATA/config/ui.json（私有权限）；任务数据库保持只读，任务和沟通摘要原文不改变。也可直接启动模块时加 `--language auto|zh|en` 临时覆盖；存储不可用时仅当前会话生效并提示，不会修改源码。

v0.2 升级时先运行本地 CLI status 以创建 schedules/software 表和 tracking_mode 字段，再启动只读原生视图。旧任务默认迁移为 manual，不创建计划、不启动任何软件。验收八个导航页（总览、活动、Agent、定时任务、软件、规则、关于与版本、设置）、活动详情返回、空登记状态、未接入计划和软件动作限制。

桌面入口使用 Terminal=false，不弹出终端；原生进程标准输出和错误写入私有 DATA/logs/desktop.log。窗口没有出现时检查该日志，而不是反复启动隐藏实例。
