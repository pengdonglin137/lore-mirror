# lore-mirror

本地镜像 [lore.kernel.org](https://lore.kernel.org) 的内核邮件列表归档系统。

支持选择性镜像、全文搜索、邮件线程浏览、diff 高亮，以及通过 REST API 供 AI 工具访问。

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+ (仅前端开发需要)
- Git

### 安装

```bash
git clone git@gitee.com:pengdonglin137/lore-mirror.git
cd lore-mirror

# 安装 Python 依赖
pip3 install -r requirements.txt

# 安装前端依赖并构建
cd frontend && npm install && npx vite build && cd ..
```

### 配置

编辑 `config.yaml`，取消注释需要镜像的 inbox：

```yaml
inboxes:
  - name: lkml
    description: "The Linux Kernel Mailing List"
  - name: netdev
    description: "Netdev List"
  # 取消注释更多...
```

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
# 导入所有已配置 inbox
python3 scripts/import_mail.py

# 或只导入指定 inbox
python3 scripts/import_mail.py --inbox lkml

# 查看导入统计
python3 scripts/import_mail.py --stats
```

导入支持断点续传，中断后再次运行会从上次位置继续。

### 启动 Web 服务

```bash
# 生产模式（推荐，需先构建前端）
./start.sh --build
# 访问 http://localhost:8000

# 开发模式（前端热更新）
./start.sh
# 前端 http://localhost:3000，API http://localhost:8000
```

## 日常维护

### 同步更新

同步 = git fetch + 增量导入新邮件。仅通过命令行触发：

```bash
# 同步所有 inbox
python3 scripts/sync.py

# 同步指定 inbox
python3 scripts/sync.py --inbox lkml

# 查看同步状态
python3 scripts/sync.py --status
```

设置定时同步：

```bash
crontab -e
# 每 6 小时同步
0 */6 * * * cd /path/to/lore-mirror && python3 scripts/sync.py >> sync.log 2>&1
```

### 健康检查

```bash
# 检查 git 仓库和数据库完整性
python3 scripts/healthcheck.py

# 检查并自动修复
python3 scripts/healthcheck.py --repair
```

修复操作：重新 clone 损坏的 git 仓库，重建损坏的数据库。

### 添加新 inbox

1. 编辑 `config.yaml` 取消注释
2. `python3 scripts/mirror.py --inbox <name>`
3. `python3 scripts/import_mail.py --inbox <name>`
4. 刷新浏览器

### 删除 inbox

1. 注释掉 `config.yaml` 中对应条目
2. `rm -rf repos/<name>/ db/<name>.db`

## API

详细的 API 文档见 [docs/API.md](docs/API.md)。

常用端点：

| 端点 | 说明 |
|------|------|
| `GET /api/inboxes` | 列出所有邮件列表 |
| `GET /api/inboxes/{name}?page=1` | 浏览某个列表的邮件 |
| `GET /api/search?q=keyword` | 全文搜索 |
| `GET /api/messages/{message_id}` | 查看单封邮件 |
| `GET /api/threads/{message_id}` | 查看完整讨论线程 |
| `GET /api/raw?id={message_id}` | 下载原始邮件 |

## 项目结构

```
lore-mirror/
├── config.yaml              # 配置文件
├── requirements.txt         # Python 依赖
├── start.sh                 # 启动脚本
├── repos/                   # git mirror 仓库 (数据，不入 git)
├── db/                      # SQLite 数据库 (数据，不入 git)
├── scripts/
│   ├── config_utils.py      # 配置加载
│   ├── mirror.py            # git 仓库下载
│   ├── import_mail.py       # 邮件导入
│   ├── database.py          # 数据库 schema
│   ├── sync.py              # 同步 (fetch + import)
│   └── healthcheck.py       # 完整性检查与修复
├── server/
│   └── app.py               # FastAPI 后端
├── frontend/                # Vue 3 前端
└── docs/
    ├── API.md               # API 文档 (供 AI 工具参考)
    └── plans/               # 设计文档
```

## 技术栈

- **后端**: Python 3, FastAPI
- **数据库**: SQLite3 + FTS5 (每个 inbox 独立文件，零配置)
- **前端**: Vue 3, Vite
- **数据来源**: lore.kernel.org public-inbox git 仓库

## 数据规模参考

以 lkml (Linux Kernel Mailing List) 为例：
- 19 个 epoch，约 600 万封邮件
- Git 仓库约 20 GB
- 数据库约 140 GB (含原始邮件)
- 导入速率约 80 封/秒，全量导入约 20 小时
