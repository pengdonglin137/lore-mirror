# 本地 lore.kernel.org 镜像系统设计文档

## 目标

在本地完整复刻 lore.kernel.org 的邮件归档功能，支持：
- 选择性镜像指定的内核邮件列表
- 通过 Web 界面浏览、搜索邮件
- AI/LLM 分析、patch 追踪
- 定期自动同步更新

## 架构

```
浏览器 → Vue 3 前端 → FastAPI 后端 → SQLite3 + FTS5 (每个 inbox 独立数据库)
                                     ↕
                              Git 数据仓库层 (/vol_8t/lore/repos/)
```

## 模块

### 模块 1: Git 仓库下载 (Phase 1) ✅
- `config.yaml`: inbox 列表（~200 个，按类别分组）、下载参数
- `scripts/mirror.py`: 自动发现 epoch、并行下载、断点续传
- 目录: `repos/{inbox}/git/{epoch}.git`

### 模块 2: 邮件导入 SQLite (Phase 2) ✅
- `scripts/database.py`: 数据库 schema（每 inbox 独立 .db 文件）
- `scripts/import_mail.py`: 从 git 提取邮件、解析、导入
- 增量导入：`import_progress` 表记录每个 epoch 的导入断点
- FTS5 全文搜索索引，通过触发器自动同步

### 模块 3: FastAPI 后端 (Phase 3) ✅
- `server/app.py`: REST API
- 端点: /api/inboxes, /api/locate, /api/inboxes/{name}, /api/messages/{id}, /api/raw, /api/threads/{id}, /api/search, /api/stats, /api/sync/status
- 跨 inbox 搜索：遍历所有 inbox 数据库
- 生产模式: 同时 serve Vue SPA 静态文件

### 模块 4: Vue 3 前端 (Phase 4) ✅
- 5 个页面: Home, Inbox, Message, Thread, Search
- 功能: locate inbox、search all inboxes、邮件分页浏览、线程树视图、全文搜索、diff 高亮
- 支持暗色模式

### 模块 5: 同步与维护 (Phase 5) ✅
- `scripts/sync.py`: git fetch + 增量导入（仅通过 CLI/cron 触发）
- `scripts/healthcheck.py`: git 仓库和数据库完整性检查与修复
- 前端仅显示同步状态（只读）

## 数据库设计 (SQLite3，每 inbox 独立)

每个 inbox 有独立的数据库文件: `db/{inbox_name}.db`

### messages 表
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | |
| message_id | TEXT UNIQUE | Message-ID 头 |
| subject | TEXT | 主题 |
| sender | TEXT | From |
| date | TEXT | ISO 8601 日期 |
| in_reply_to | TEXT | 父邮件 Message-ID |
| references_ids | TEXT | JSON 数组 |
| body_text | TEXT | 纯文本正文 |
| body_html | TEXT | HTML 正文 |
| raw_email | BLOB | 原始邮件 |
| headers | TEXT | JSON 对象 |
| git_commit | TEXT | 来源 commit hash |
| epoch | INTEGER | 来源 epoch |

### messages_fts (FTS5 虚表)
- 索引字段: subject, sender, body_text
- tokenizer: unicode61
- 通过触发器与 messages 表自动同步

### attachments 表
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | |
| message_id | FK → messages | |
| filename | TEXT | 文件名 |
| content_type | TEXT | MIME 类型 |
| content | BLOB | 内容 |

### import_progress 表
| 列 | 类型 | 说明 |
|----|------|------|
| epoch | INTEGER PK | |
| last_commit | TEXT | 最后处理的 commit |
| commit_count | INTEGER | 已处理 commit 数 |
| updated_at | TEXT | 更新时间 |

## 技术栈
- 后端: Python 3, FastAPI
- 数据库: SQLite3 + FTS5（零配置，每 inbox 独立文件）
- 前端: Vue 3, Vite
- 邮件解析: Python email 标准库
- 定时任务: cron

## 目录结构
```
/vol_8t/lore/
├── config.yaml                 # 配置（inbox 列表、下载参数）
├── requirements.txt            # Python 依赖
├── start.sh                    # 一键启动脚本
├── repos/                      # git mirror 仓库
│   └── {inbox}/git/{N}.git
├── db/                         # 每 inbox 独立 SQLite 数据库
│   └── {inbox}.db
├── scripts/
│   ├── mirror.py               # 首次下载 git 仓库
│   ├── database.py             # 数据库 schema
│   ├── import_mail.py          # 邮件导入
│   ├── sync.py                 # 同步（fetch + 增量导入）
│   └── healthcheck.py          # 完整性检查与修复
├── server/
│   └── app.py                  # FastAPI 后端
├── frontend/
│   ├── src/views/              # Vue 页面组件
│   ├── src/components/         # 可复用组件
│   ├── src/api.js              # API 客户端
│   ├── src/router.js           # 路由配置
│   └── dist/                   # 生产构建产物
├── docs/plans/                 # 设计文档
└── ref/                        # 参考网页
```

## 数据规模 (lkml)
- 19 个 epoch, ~593 万封邮件
- Git 仓库: 20 GB
- SQLite 数据库(含原始邮件): 预估 80-140 GB
- 导入速率: ~80 commits/s，全量导入约 20 小时

## 实施阶段
| 阶段 | 状态 |
|------|------|
| Phase 1: 项目骨架 + git 下载脚本 | ✅ 完成 |
| Phase 2: SQLite + 邮件导入 | ✅ 完成 |
| Phase 3: FastAPI 后端 | ✅ 完成 |
| Phase 4: Vue 前端 | ✅ 完成 |
| Phase 5: 同步 + 健康检查 | ✅ 完成 |

---

## 使用说明

### 1. 配置要镜像的 inbox

编辑 `config.yaml`，取消注释需要的 inbox：

```yaml
inboxes:
  - name: lkml
    description: "The Linux Kernel Mailing List"
  - name: netdev
    description: "Netdev List"
  # 取消注释更多...
```

配置中已按类别（Core、Networking、Filesystems、GPU、Arch 等）组织了 lore 全部 ~200 个 inbox。

### 2. 首次下载 git 仓库

```bash
# 下载所有已配置的 inbox
python3 scripts/mirror.py

# 只下载指定 inbox
python3 scripts/mirror.py --inbox lkml

# 查看下载状态
python3 scripts/mirror.py --status
```

大型 inbox（如 lkml 有 19 个 epoch, 20GB）建议在 tmux/screen 中运行。

### 3. 首次导入邮件到数据库

```bash
# 导入所有已配置的 inbox
python3 scripts/import_mail.py

# 只导入指定 inbox
python3 scripts/import_mail.py --inbox lkml

# 查看导入统计
python3 scripts/import_mail.py --stats
```

导入支持断点续传，可以随时中断并恢复。每个 inbox 的数据库独立存放在 `db/` 目录下。

### 4. 启动 Web 服务

```bash
# 开发模式（前端 :3000 + 后端 :8000）
./start.sh

# 生产模式（构建前端，仅后端 :8000）
./start.sh --build
```

访问 http://localhost:3000（开发）或 http://localhost:8000（生产）。

### 5. 日常同步

同步 = git fetch 更新仓库 + 增量导入新邮件。

```bash
# 手动同步所有 inbox
python3 scripts/sync.py

# 同步指定 inbox
python3 scripts/sync.py --inbox lkml

# 查看上次同步状态
python3 scripts/sync.py --status
```

**设置定时同步（推荐）：**

```bash
crontab -e
# 添加以下行（每 6 小时同步一次）：
0 */6 * * * cd /vol_8t/lore && python3 scripts/sync.py >> sync.log 2>&1
```

同步状态会实时写入 `sync_status.json`，前端首页可查看。

### 6. 健康检查与修复

```bash
# 检查所有 inbox 的 git 仓库和数据库完整性
python3 scripts/healthcheck.py

# 只检查指定 inbox
python3 scripts/healthcheck.py --inbox lkml

# 检查并自动修复问题（重新 clone 损坏的 git 仓库，重建损坏的数据库）
python3 scripts/healthcheck.py --repair
```

检查内容：
- Git 仓库: 是否存在、`git fsck` 验证
- 数据库: `PRAGMA integrity_check`、表结构完整性

修复操作：
- 缺失/损坏的 git epoch: 自动重新 `git clone --mirror`
- 损坏的数据库: 从 git 仓库重新导入重建（原文件备份为 `.bak`）

**推荐定期运行：**

```bash
crontab -e
# 每周日凌晨检查：
0 3 * * 0 cd /vol_8t/lore && python3 scripts/healthcheck.py >> healthcheck.log 2>&1
```

### 7. 添加新 inbox

1. 在 `config.yaml` 中取消注释或添加新的 inbox
2. 下载: `python3 scripts/mirror.py --inbox <name>`
3. 导入: `python3 scripts/import_mail.py --inbox <name>`
4. 刷新浏览器即可看到新 inbox

### 8. 删除 inbox

1. 在 `config.yaml` 中注释掉该 inbox
2. 删除 git 仓库: `rm -rf repos/<name>/`
3. 删除数据库: `rm db/<name>.db`
