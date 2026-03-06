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
- 搜索: lore 兼容前缀语法 (s: f: b: d: t: c: a: m: bs: tc:)，Message-ID 自动检测
- 跨 inbox 搜索：遍历所有 inbox 数据库
- 日期排序：过滤异常日期（Y2K、未来时间戳、non-ISO 格式）
- 性能优化：索引友好查询 + 内存缓存（5 分钟 TTL）+ 30 秒查询超时保护
- 生产模式: 同时 serve Vue SPA 静态文件
- `scripts/test_api.py`: 自动化 API 测试（38 个用例，零外部依赖，支持 `--url` 远程测试）

### 模块 4: Vue 3 前端 (Phase 4) ✅
- 5 个页面: Home, Inbox, Message, Thread, Search
- 功能: locate inbox、search all inboxes（带 inbox 选择器和搜索语法帮助）
- 导航栏搜索语法帮助按钮（`?`）
- 邮件分页浏览、线程树视图、diff 高亮
- 左对齐布局，亮色/暗色主题切换（localStorage 持久化，首次访问跟随系统偏好）

### 模块 5: 同步与维护 (Phase 5) ✅
- `scripts/sync.py`: git fetch + 增量导入（仅通过 CLI/cron 触发）
  - 仅导入有更新的 epoch（避免全 epoch 扫描）
  - 按从新到旧的顺序导入（最新邮件优先可用）
  - per-inbox 锁（fcntl.flock）：不同 inbox 可并行同步，同一 inbox 互斥
  - 优雅退出：SIGTERM/SIGINT 保存进度后退出
  - `--stop` 停止正在运行的同步/导入进程
- `scripts/import_mail.py`: 邮件导入，共享 per-inbox 锁
- `scripts/healthcheck.py`: git 仓库和数据库完整性检查与修复
- `scripts/config_utils.py`: 统一配置加载，支持相对/绝对路径
- 前端仅显示同步状态（只读）

### 模块 6: 容器化部署 ✅
- `Dockerfile`: 多阶段构建（Node 20 → Python 3.12-slim）
- `docker-compose.yml`: web + sync 两服务编排
- 共享卷: repos/ db/ sync_status/
- 环境变量自定义: `LORE_PORT`, `LORE_SYNC_SCHEDULE`, `LORE_REPOS_DIR`, `LORE_DB_DIR`

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
- 容器化: Docker / Docker Compose（可选）

## 技术选型与理由

每个技术选择背后都有具体的原因，不是"因为流行"而是"因为适合这个场景"。

### REST API — 为什么不用 GraphQL 或 gRPC？

REST (Representational State Transfer) 把服务器数据抽象为"资源"，用 URL 定位、用 HTTP 方法操作：

| HTTP 方法 | URL | 含义 |
|-----------|-----|------|
| GET | `/api/inboxes` | 获取所有邮件列表（资源集合） |
| GET | `/api/inboxes/lkml` | 获取 lkml 列表中的邮件（单个资源） |
| GET | `/api/search?q=keyword` | 搜索（带查询参数） |

**选择 REST 的理由**:
- **AI 工具兼容性**: REST 是最通用的接口风格。任何能发 HTTP 请求的工具（curl、Python requests、浏览器、AI agent）都能直接调用，无需特殊客户端库。GraphQL 需要构造查询语句，gRPC 需要 protobuf 客户端，对 AI 集成来说都多了一层障碍。
- **只读场景**: 邮件归档是纯只读的（只有 GET），不需要 GraphQL 的"按需选字段"能力，也不需要 gRPC 的双向流。
- **可调试性**: 浏览器地址栏输入 URL 就能看结果，开发和排错极其简单。

### SQLite + FTS5 — 为什么不用 PostgreSQL 或 Elasticsearch？

**选择 SQLite 的理由**:
- **零配置部署**: 不需要安装数据库服务器，不需要管理连接池、用户权限、端口。一个 `.db` 文件就是整个数据库，`cp` 就能备份。
- **Per-inbox 隔离**: 每个邮件列表一个独立文件（`db/lkml.db`, `db/linux-mm.db`）。导入、删除、备份都是文件级操作，不同 inbox 完全互不影响。用 PostgreSQL 的话，所有数据在一个实例里，隔离需要靠 schema 或多个实例。
- **嵌入式 = 低延迟**: SQLite 在同一进程内直接读文件，没有网络往返。对于"打开 inbox 列表"这种高频操作，延迟从 PostgreSQL 的 ~5ms 降到 ~0.1ms。
- **FTS5 全文搜索**: SQLite 自带的 FTS5 扩展提供了 BM25 排序的全文搜索，无需引入 Elasticsearch。对于邮件归档这种"写少读多"的场景，FTS5 的性能足够（百万级邮件搜索 <1s）。
- **实际约束**: 开发环境的 PostgreSQL 14 不可访问，Docker registry 也不通。SQLite 是唯一不需要额外基础设施的选择。

**SQLite 的局限** (知道但可接受):
- 并发写入受限（WAL 模式下读不阻塞，但写是串行的）→ 通过 per-inbox fcntl.flock 锁解决
- 单个数据库文件很大（lkml ~140GB）→ 文件系统能处理，不是问题
- 没有内置复制/集群 → 这是单机部署的本地镜像，不需要

### FastAPI — 为什么不用 Flask 或 Django？

**选择 FastAPI 的理由**:
- **自动生成 API 文档**: FastAPI 内置 Swagger UI（`/docs`），开发时可以直接在浏览器测试每个端点。
- **类型提示 = 自动验证**: `page: int = Query(1, ge=1)` 同时定义了类型、默认值和验证规则，不需要手写验证逻辑。Flask 需要额外的 marshmallow 或 WTForms。
- **异步支持**: 虽然当前用同步模式（SQLite 不支持 async），但 FastAPI 的 ASGI 架构允许将来平滑迁移。
- **轻量**: 比 Django 轻得多。这不是一个需要 ORM、admin panel、认证系统的项目，只需要一个高效的 API 层。

### Vue 3 + Vite — 为什么不用 React 或服务端渲染？

**选择 Vue 3 的理由**:
- **SPA 适合邮件浏览**: 在 inbox → message → thread 之间频繁跳转，SPA 的客户端路由比整页刷新流畅。
- **简单直接**: Vue 的模板语法比 React JSX 更接近 HTML，对于这种以文本展示为主的界面，开发效率高。
- **生产模式一键构建**: `vite build` 生成静态文件，FastAPI 直接 serve。不需要 Node.js 运行时。不需要 SSR。
- **极简前端**: 整个 SPA 只有 5 个视图 + 1 个组件，不需要 Redux/Vuex 状态管理。Vue 3 的 Composition API + `ref()` 就够了。

### public-inbox Git 仓库 — 为什么不直接抓网页？

lore.kernel.org 基于 [public-inbox](https://public-inbox.org/) 项目，每个邮件列表都有对应的 git 仓库。

**选择 git clone 而非爬虫的理由**:
- **完整性**: git 仓库包含该列表的全部邮件，不会漏掉。爬网页容易遗漏、被限流、或格式变化。
- **增量更新**: `git fetch` 只拉取新 commit，带宽和时间极少。爬虫要重新遍历页面才知道有没有新邮件。
- **原始数据**: 每个 commit 的 `m` 文件就是完整的 RFC 2822 原始邮件，包含所有 headers。网页只展示部分内容。
- **离线完整性**: 一旦 clone 完成，整个归档可以完全离线使用，不依赖 lore.kernel.org 的可用性。

### Docker — 为什么提供但不强制？

**可选容器化的理由**:
- 裸机部署更简单（`pip install` + `./start.sh`），适合开发者日常使用
- Docker 适合服务器/团队部署，提供环境一致性和 cron 集成（sync 容器）
- 数据卷挂载让裸机和 Docker 之间可以无缝切换，不需要重新下载或导入

## 目录结构
```
lore-mirror/
├── config.yaml                 # 配置（inbox 列表、路径、下载参数）
├── requirements.txt            # Python 依赖
├── start.sh                    # 一键启动脚本（裸机部署）
├── Dockerfile                  # 多阶段构建（Node→Python）
├── docker-compose.yml          # web + sync 两服务编排
├── .dockerignore               # 构建排除规则
├── CLAUDE.md                   # AI 助手项目上下文
├── repos/                      # git mirror 仓库（Docker 卷挂载）
│   └── {inbox}/git/{N}.git
├── db/                         # 每 inbox 独立 SQLite 数据库（Docker 卷挂载）
│   └── {inbox}.db
├── sync_status/                # 同步状态（per-inbox .json + .lock 文件）
├── scripts/
│   ├── config_utils.py         # 统一配置加载（相对/绝对路径解析）
│   ├── mirror.py               # 首次下载 git 仓库
│   ├── database.py             # 数据库 schema
│   ├── import_mail.py          # 邮件导入（含日期修复、优雅退出）
│   ├── sync.py                 # 同步（fetch + 增量导入、per-inbox 锁）
│   ├── healthcheck.py          # 完整性检查与修复
│   └── test_search.py          # 搜索功能测试用例
├── server/
│   └── app.py                  # FastAPI 后端（搜索前缀解析 + SPA 服务）
├── frontend/
│   ├── src/views/              # Vue 页面：Home, Inbox, Message, Thread, Search
│   ├── src/components/         # 可复用组件：ThreadNode
│   ├── src/api.js              # API 客户端
│   ├── src/router.js           # 路由配置
│   └── dist/                   # 生产构建产物
├── docs/
│   ├── API.md                  # REST API 文档（供 AI 工具参考）
│   └── plans/                  # 设计文档
└── ref/                        # 参考网页（lore 原站数据）
```

## 部署架构

### 裸机部署
```
┌──────────────────────────────────┐
│         ./start.sh --build       │
│  ┌────────────┐                  │
│  │  FastAPI    │ :8000           │
│  │  + Vue SPA  │────────────┐    │
│  └────────────┘             │    │
│                       ┌─────┴──┐ │
│  cron → sync.py ────→ │ SQLite │ │
│                       │ repos/ │ │
│                       └────────┘ │
└──────────────────────────────────┘
```

### 容器化部署
```
┌─ docker compose ─────────────────────────────┐
│                                               │
│  ┌─ web ──────────┐   ┌─ sync ─────────────┐ │
│  │ FastAPI + SPA   │   │ cron → sync.py     │ │
│  │ :8000           │   │ (首次启动立即同步) │ │
│  └────┬────────────┘   └──────┬─────────────┘ │
│       │                       │               │
│  ─────┴───────────────────────┴─────────      │
│  │  volumes: repos/ db/ sync_status/  │       │
│  ──────────────────────────────────────       │
└───────────────────────────────────────────────┘
```

**容器设计要点**:
- **两个服务**: `web`（API + SPA）和 `sync`（定时同步 cron daemon）
- **共享卷**: `repos/` `db/` `sync_status/` 在两个容器间共享
- **多阶段构建**: Node 20 构建前端 → Python 3.12 运行后端（镜像体积最小化）
- **数据安全**: SQLite per-inbox 锁（fcntl.flock）防止 web 和 sync 并行写同一 DB
- **环境变量**: `LORE_PORT` `LORE_SYNC_SCHEDULE` `LORE_REPOS_DIR` `LORE_DB_DIR` 可自定义
- **优雅退出**: `docker compose stop` 发送 SIGTERM，sync 容器保存进度后退出

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
| Phase 6: 容器化部署 | ✅ 完成 |

## 性能优化

| 优化项 | 措施 | 效果 |
|--------|------|------|
| Inbox 列表排序 | `ORDER BY CASE` → `ORDER BY date DESC`（索引扫描） | 30s(500) → 60ms |
| Inbox 统计查询 | `MIN/MAX(CASE)` → `ORDER BY LIMIT 1`（索引扫描） | 1.2s → 69ms |
| 热点端点缓存 | /api/inboxes, /api/stats, COUNT 缓存 5 分钟 | 首次 60ms → 重复 <2ms |
| 慢查询保护 | sqlite3 progress_handler 30 秒超时 | 避免无限等待 |
| f: 发件人搜索 | SQL LIKE → FTS5 sender 列（倒排索引） | lkml 全表扫描挂起 → 0.001s |
| 搜索 COUNT 优化 | COUNT 子查询 LIMIT 10001 封顶 + 纯 FTS 跳过 JOIN | 避免大结果集计数超时 |
| 跨 inbox 搜索 | 已有足够结果时跳过后续 inbox 的 SELECT | f:torvalds 15s → 0.02s |
| 同步仅更新 epoch | fetch 后只 import 有新 commit 的 epoch | 9.5h → 1.5min |

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

### 5. 搜索

搜索支持 lore.kernel.org 兼容的前缀语法：

| 前缀 | 说明 | 示例 |
|------|------|------|
| `s:` | 搜索主题 | `s:PATCH` `s:"memory leak"` |
| `f:` | 搜索发件人 | `f:torvalds` |
| `b:` | 搜索正文 | `b:kasan` |
| `bs:` | 搜索主题+正文 | `bs:regression` |
| `d:` | 日期范围 | `d:2026-01-01..2026-03-01` `d:2026-01-01..` |
| `t:` | 搜索 To 头 | `t:linux-mm@kvack.org` |
| `c:` | 搜索 Cc 头 | `c:stable@vger.kernel.org` |
| `a:` | 搜索所有地址 | `a:torvalds` |
| `tc:` | 搜索 To+Cc | `tc:netdev` |
| `m:` | 搜索 Message-ID | `m:20260110-can@pengutronix.de` |

操作符：AND（默认）、OR、NOT、`"exact phrase"`、`prefix*`

直接在搜索框粘贴 Message-ID（含 `@`）会自动识别并精确查找。

搜索页面可通过下拉框选择特定 inbox 或搜索全部。点击 `[search help]` 查看完整语法帮助。

### 6. 日常同步

同步 = git fetch 更新仓库 + 增量导入新邮件。

```bash
# 手动同步所有 inbox
python3 scripts/sync.py

# 同步指定 inbox
python3 scripts/sync.py --inbox lkml

# 并行同步不同 inbox（不同 inbox 可同时运行）
python3 scripts/sync.py --inbox lkml &
python3 scripts/sync.py --inbox linux-mm &

# 查看同步状态
python3 scripts/sync.py --status

# 停止同步
python3 scripts/sync.py --stop              # 停止所有正在运行的同步
python3 scripts/sync.py --stop --inbox lkml # 只停止指定 inbox 的同步
```

停止操作会发送 SIGTERM 信号，sync 进程会保存当前进度后优雅退出，下次同步会从断点继续。

**设置定时同步（推荐）：**

```bash
crontab -e
# 添加以下行（每 6 小时同步一次）：
0 */6 * * * cd /vol_8t/lore && python3 scripts/sync.py >> sync.log 2>&1
```

同步状态会实时写入 `sync_status/` 目录（每 inbox 独立状态文件），前端首页可查看。

### 7. 健康检查与修复

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

### 8. 添加新 inbox

1. 在 `config.yaml` 中取消注释或添加新的 inbox
2. 下载: `python3 scripts/mirror.py --inbox <name>`
3. 导入: `python3 scripts/import_mail.py --inbox <name>`
4. 刷新浏览器即可看到新 inbox

### 9. 删除 inbox

1. 在 `config.yaml` 中注释掉该 inbox
2. 删除 git 仓库: `rm -rf repos/<name>/`
3. 删除数据库: `rm db/<name>.db`

### 10. 安装 Claude Code Skills（AI 集成）

项目提供两个 Claude Code Skills：

| Skill | 用途 | 文件 |
|-------|------|------|
| **lore-mirror** | 搜索内核邮件列表 API | `docs/skills/lore-mirror/SKILL.md` |
| **kernel-dev** | 内核开发辅助（代码阅读、特性演进、backport、动态跟踪） | `docs/skills/kernel-dev/SKILL.md` |

```bash
# 安装到当前用户的 Claude Code skills 目录
mkdir -p ~/.claude/skills/lore-mirror ~/.claude/skills/kernel-dev
cp docs/skills/lore-mirror/SKILL.md ~/.claude/skills/lore-mirror/SKILL.md
cp docs/skills/kernel-dev/SKILL.md ~/.claude/skills/kernel-dev/SKILL.md
```

**lore-mirror skill**: 自动调用 lore-mirror API 搜索内核邮件列表，包含完整的 API 用法和搜索语法。

**kernel-dev skill**: 辅助内核开发的核心任务：
- 代码阅读与理解（git blame, git log -L, 函数追踪）
- 特性演进梳理（跨版本 diff, 时间线构建）
- **补丁回移 (Backport)**（依赖分析、风险评估、验证流程）
- 内核动态跟踪（已合入变更 + 进行中的 patch review）
- 与 lore-mirror 联动：将 git commit 关联到邮件列表讨论

kernel-dev 的设计文档见 `docs/skills/kernel-dev/DESIGN.md`，后续演进方向在其中记录。

如果 lore-mirror API 基础 URL 不是 `http://localhost:8000`，需要编辑 `lore-mirror/SKILL.md` 中的 Base URL。

### 11. API 测试

```bash
# 测试本地服务
python3 scripts/test_api.py

# 测试远程/Docker 部署
python3 scripts/test_api.py --url http://your-host:8000

# 详细模式
python3 scripts/test_api.py -v
```

35 个测试用例覆盖所有 API 端点，零外部依赖，失败时 exit 1 可用于 CI。

---

## Docker 部署

### 快速开始

```bash
# 1. 编辑 config.yaml，选择要镜像的 inbox

# 2. 首次下载 git 仓库
docker compose run --rm sync python3 scripts/mirror.py --inbox lkml

# 3. 首次导入邮件
docker compose run --rm sync python3 scripts/import_mail.py --inbox lkml

# 4. 启动服务（web + 定时同步）
docker compose up -d
```

访问 http://localhost:8000

### 常用命令

```bash
# 启动/停止
docker compose up -d           # 启动 web + sync
docker compose up -d web       # 仅启动 web（不自动同步）
docker compose down            # 停止所有服务

# 查看日志
docker compose logs -f web     # web 服务日志
docker compose logs -f sync    # sync 服务日志

# 手动操作
docker compose exec sync python3 scripts/sync.py --status
docker compose exec sync python3 scripts/sync.py --inbox lkml
docker compose exec sync python3 scripts/mirror.py --inbox netdev
docker compose exec sync python3 scripts/import_mail.py --inbox netdev
docker compose exec sync python3 scripts/healthcheck.py --repair

# 重新构建（代码更新后）
docker compose build
docker compose up -d
```

### 自定义配置

通过环境变量或 `.env` 文件自定义：

```bash
# .env 文件（放在项目根目录）
LORE_PORT=9000                     # Web 端口（默认 8000）
LORE_SYNC_SCHEDULE=0 */2 * * *    # 同步频率（默认每 6 小时）
LORE_REPOS_DIR=/data/lore/repos   # 自定义数据目录
LORE_DB_DIR=/data/lore/db
```

或直接在命令行设置：

```bash
LORE_PORT=9000 docker compose up -d
```

### 数据持久化

Docker 卷映射（默认使用项目内相对路径）：

| 容器路径 | 宿主机默认路径 | 环境变量 | 说明 |
|----------|---------------|----------|------|
| `/app/repos` | `./repos` | `LORE_REPOS_DIR` | Git 仓库（大，lkml ~20GB） |
| `/app/db` | `./db` | `LORE_DB_DIR` | SQLite 数据库（大，lkml ~140GB） |
| `/app/sync_status` | `./sync_status` | `LORE_SYNC_STATUS_DIR` | 同步状态文件 |
| `/app/config.yaml` | `./config.yaml` | — | 只读挂载 |

**磁盘空间建议**: lkml 单个 inbox 需要约 160GB（repos + db）。建议将数据卷指向大容量磁盘。

### 从裸机迁移到 Docker

如果已有裸机部署的 `repos/` 和 `db/` 数据，直接启动容器即可复用：

```bash
# 停止裸机服务
pkill -f 'uvicorn server.app'

# 启动 Docker（自动使用现有 repos/ 和 db/）
docker compose up -d
```

### 注意事项

- **SQLite 并发**: web 和 sync 容器共享数据库文件，通过 fcntl.flock 保证同一 inbox 不会被并行写入
- **sync 容器启动行为**: 首次启动会立即执行一次全量同步，之后按 cron 定时执行
- **优雅停止**: `docker compose stop` 发送 SIGTERM，sync 进程会保存当前进度再退出
- **不同 inbox 可并行同步**: 可运行多个 `docker compose exec sync python3 scripts/sync.py --inbox <name>` 并行同步不同 inbox
