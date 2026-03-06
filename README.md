# lore-mirror

本地镜像 [lore.kernel.org](https://lore.kernel.org) 的内核邮件列表归档系统。

支持选择性镜像、全文搜索、邮件线程浏览、diff 高亮，以及通过 REST API 供 AI 工具访问。

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+ (仅前端开发需要)
- Git
- Docker + Docker Compose (可选，容器化部署)

### 方式一：裸机安装

```bash
git clone git@github.com:pengdonglin137/lore-mirror.git
cd lore-mirror

# 安装 Python 依赖
pip3 install -r requirements.txt

# 安装前端依赖并构建
cd frontend && npm install && npx vite build && cd ..
```

### 方式二：Docker 部署

```bash
git clone git@github.com:pengdonglin137/lore-mirror.git
cd lore-mirror
docker compose up -d
```

详见下方 [Docker 部署](#docker-部署) 章节。

### 配置

编辑 `config.yaml`，取消注释需要镜像的 inbox：

```yaml
inboxes:
  - name: lkml
    description: "The Linux Kernel Mailing List — the main general-purpose..."
  - name: linux-mm
    description: "Linux Memory Management — page allocator, slab/slub..."
  # 取消注释更多... (~200 个可选)
```

每个 inbox 都有详细的话题描述，方便 AI 工具精确匹配。

路径配置（默认使用相对路径，相对于项目根目录）：

```yaml
mirror:
  repos_dir: "repos"       # git 仓库存放目录
database:
  dir: "db"                # SQLite 数据库存放目录
```

如需使用绝对路径（例如数据放在外部磁盘）：

```yaml
mirror:
  repos_dir: "/data/lore/repos"
database:
  dir: "/data/lore/db"
```

### 下载数据

```bash
# 下载所有已配置 inbox 的 git 仓库
python3 scripts/mirror.py

# 或只下载指定 inbox
python3 scripts/mirror.py --inbox lkml

# 查看下载状态
python3 scripts/mirror.py --status
```

### 导入邮件到数据库

```bash
# 导入所有已配置 inbox（从新到旧）
python3 scripts/import_mail.py

# 或只导入指定 inbox
python3 scripts/import_mail.py --inbox lkml

# 查看导入统计
python3 scripts/import_mail.py --stats
```

导入支持断点续传和优雅退出（Ctrl+C 或 `kill` 后保存进度）。

### 启动 Web 服务

```bash
# 生产模式（推荐，需先构建前端）
./start.sh --build
# 访问 http://localhost:8000

# 开发模式（前端热更新）
./start.sh
# 前端 http://localhost:3000，API http://localhost:8000
```

## 搜索

支持 lore.kernel.org 兼容的前缀语法：

```
s:PATCH f:torvalds                   Torvalds 的 patch
s:"memory leak" d:2026-01-01..       2026 年以来的 memory leak 补丁
b:"use after free"                   正文包含 use after free
f:torvalds d:2026-01-01..2026-03-01  日期范围内 Torvalds 的邮件
a:stable@vger.kernel.org             发给 stable 的邮件
m:message-id@example.com             按 Message-ID 精确查找
```

完整前缀列表：`s:` (主题), `f:` (发件人), `b:` (正文), `d:` (日期), `t:` (To), `c:` (Cc), `a:` (所有地址), `m:` (Message-ID), `bs:` (主题+正文), `tc:` (To+Cc)

直接粘贴 Message-ID（含 `@`）会自动识别。搜索页面点击 `?` 按钮查看完整语法帮助。

## 日常维护

### 同步更新

同步 = git fetch + 增量导入新邮件：

```bash
# 同步所有 inbox
python3 scripts/sync.py

# 同步指定 inbox
python3 scripts/sync.py --inbox lkml

# 并行同步不同 inbox
python3 scripts/sync.py --inbox lkml &
python3 scripts/sync.py --inbox linux-mm &

# 查看同步状态
python3 scripts/sync.py --status

# 停止正在运行的同步
python3 scripts/sync.py --stop
python3 scripts/sync.py --stop --inbox lkml
```

设置定时同步：

```bash
crontab -e
# 每 6 小时同步
0 */6 * * * cd /path/to/lore-mirror && python3 scripts/sync.py >> sync.log 2>&1
```

### 健康检查

```bash
python3 scripts/healthcheck.py           # 检查
python3 scripts/healthcheck.py --repair  # 检查并修复
```

### 添加/删除 inbox

```bash
# 添加
# 1. 编辑 config.yaml 取消注释
# 2. python3 scripts/mirror.py --inbox <name>
# 3. python3 scripts/import_mail.py --inbox <name>

# 删除
# 1. 注释掉 config.yaml 中对应条目
# 2. rm -rf repos/<name>/ db/<name>.db
```

## Docker 部署

```bash
# 首次设置
docker compose run --rm sync python3 scripts/mirror.py --inbox lkml
docker compose run --rm sync python3 scripts/import_mail.py --inbox lkml

# 启动（web + 定时同步）
docker compose up -d

# 仅启动 web
docker compose up -d web

# 查看日志
docker compose logs -f sync

# 手动操作
docker compose exec sync python3 scripts/sync.py --status
docker compose exec sync python3 scripts/sync.py --stop
```

自定义配置（通过环境变量或 `.env` 文件）：

```bash
LORE_PORT=9000                     # Web 端口（默认 8000）
LORE_SYNC_SCHEDULE="0 */2 * * *"  # 同步频率（默认每 6 小时）
LORE_REPOS_DIR=/data/lore/repos   # 自定义数据目录
LORE_DB_DIR=/data/lore/db
```

从裸机迁移：现有的 `repos/` 和 `db/` 直接被 Docker 卷挂载复用。

## API

详细的 API 文档见 [docs/API.md](docs/API.md)。

| 端点 | 说明 |
|------|------|
| `GET /api/inboxes` | 列出所有邮件列表（含详细描述） |
| `GET /api/locate?q=keyword` | 模糊搜索邮件列表 |
| `GET /api/inboxes/{name}?page=1` | 浏览某个列表的邮件 |
| `GET /api/search?q=keyword&inbox=name` | 全文搜索 |
| `GET /api/messages/{message_id}` | 查看单封邮件 |
| `GET /api/threads/{message_id}` | 查看完整讨论线程 |
| `GET /api/raw?id={message_id}` | 下载原始邮件 |
| `GET /api/stats` | 全局统计 |
| `GET /api/sync/status` | 同步状态 |

## AI 集成（Claude Code Skills）

提供两个 Claude Code Skills，安装后 AI 自动知道如何使用：

```bash
mkdir -p ~/.claude/skills/lore-mirror ~/.claude/skills/kernel-dev
cp docs/skills/lore-mirror/SKILL.md ~/.claude/skills/lore-mirror/
cp docs/skills/kernel-dev/SKILL.md ~/.claude/skills/kernel-dev/
```

| Skill | 用途 |
|-------|------|
| **lore-mirror** | 搜索内核邮件列表 API — inbox 发现、搜索语法、邮件/线程读取 |
| **kernel-dev** | 内核开发辅助 — 代码阅读、特性演进、补丁回移 (backport)、动态跟踪 |

### kernel-dev skill 核心能力

- **代码阅读**: `git blame`, `git log -L`, 函数历史追踪，关联 lore 讨论
- **特性演进**: 跨版本 diff, 时间线构建, merge commit 分析
- **补丁回移 (Backport)**: 依赖分析（REQUIRED/RECOMMENDED/OPTIONAL 分类）、风险评估、cherry-pick 验证
- **动态跟踪**: 已合入变更 (git log) + 正在 review 的 patch (lore-mirror)

详见 [docs/skills/kernel-dev/DESIGN.md](docs/skills/kernel-dev/DESIGN.md)。

## API 测试

```bash
python3 scripts/test_api.py                        # 测试本地
python3 scripts/test_api.py --url http://host:8000  # 测试远程
```

35 个测试用例覆盖所有端点，零外部依赖。

## 项目结构

```
lore-mirror/
├── config.yaml              # 配置文件（inbox 列表 + 详细描述）
├── requirements.txt         # Python 依赖
├── start.sh                 # 启动脚本（裸机）
├── Dockerfile               # 多阶段构建 (Node → Python)
├── docker-compose.yml       # web + sync 服务编排
├── repos/                   # git mirror 仓库 (数据)
├── db/                      # SQLite 数据库 (数据)
├── sync_status/             # 同步状态 (per-inbox)
├── scripts/
│   ├── mirror.py            # git 仓库下载
│   ├── import_mail.py       # 邮件导入（优雅退出 + per-inbox 锁）
│   ├── sync.py              # 同步（并行 + --stop + 优雅退出）
│   ├── database.py          # 数据库 schema
│   ├── healthcheck.py       # 完整性检查与修复
│   ├── config_utils.py      # 配置加载
│   └── test_api.py          # API 自动化测试
├── server/
│   └── app.py               # FastAPI 后端（缓存 + 查询超时保护）
├── frontend/                # Vue 3 + Vite SPA
└── docs/
    ├── API.md               # REST API 文档
    ├── skills/              # Claude Code Skills
    │   ├── lore-mirror/     # 邮件列表搜索 skill
    │   └── kernel-dev/      # 内核开发辅助 skill (含设计文档)
    └── plans/               # 设计文档
```

## 技术栈

- **后端**: Python 3, FastAPI, SQLite3 + FTS5
- **前端**: Vue 3, Vite
- **容器**: Docker, Docker Compose
- **数据来源**: lore.kernel.org public-inbox git 仓库

## 数据规模参考

以 lkml (Linux Kernel Mailing List) 为例：
- 19 个 epoch，约 600 万封邮件
- Git 仓库约 20 GB
- 数据库约 140 GB (含原始邮件)
- 导入速率约 80 封/秒，全量导入约 20 小时
