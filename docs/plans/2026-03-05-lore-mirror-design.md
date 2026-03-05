# 本地 lore.kernel.org 镜像系统设计文档

## 目标

在本地完整复刻 lore.kernel.org 的邮件归档功能，支持：
- 选择性镜像指定的内核邮件列表
- 通过 Web 界面浏览、搜索邮件
- AI/LLM 分析、patch 追踪
- 定期自动同步更新

## 架构

```
浏览器 → Vue 3 前端 → FastAPI 后端 → SQLite3 + FTS5 (邮件数据 + 全文搜索)
                                     ↕
                              Git 数据仓库层 (/vol_8t/lore/repos/)
```

## 模块

### 模块 1: Git 仓库下载 (Phase 1) ✅
- `config.yaml`: inbox 列表、下载参数
- `scripts/mirror.py`: 自动发现 epoch、并行下载、断点续传
- 目录: `repos/{inbox}/git/{epoch}.git`

### 模块 2: 邮件导入 SQLite (Phase 2) ✅
- `scripts/database.py`: 数据库 schema 和连接管理
- `scripts/import_mail.py`: 从 git 提取邮件、解析、导入
- 增量导入：`import_progress` 表记录每个 epoch 的导入断点
- FTS5 全文搜索索引，通过触发器自动同步

### 模块 3: FastAPI 后端 (Phase 3) ✅
- `server/app.py`: REST API (7 个端点)
- 端点: /api/inboxes, /api/inboxes/{name}, /api/messages/{id}, /api/messages/{id}/raw, /api/threads/{id}, /api/search, /api/stats
- 全文搜索: FTS5 MATCH + snippet 高亮
- 生产模式: 同时 serve Vue SPA 静态文件

### 模块 4: Vue 3 前端 (Phase 4) ✅
- 5 个页面: Home, Inbox, Message, Thread, Search
- 功能: inbox 列表、邮件分页浏览、线程树视图、全文搜索、diff 高亮
- 支持暗色模式, 响应式布局
- `start.sh`: 一键启动 (开发/生产模式)

### 模块 4: 定期同步 (Phase 5)
- git fetch 更新仓库
- 增量导入新邮件到数据库
- systemd timer 或 cron 调度

## 数据库设计 (SQLite3)

### inboxes 表
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | |
| name | TEXT UNIQUE | inbox 名称如 'lkml' |
| description | TEXT | 描述 |

### messages 表
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | |
| inbox_id | FK → inboxes | |
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
- content 表: messages
- tokenizer: unicode61

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
| inbox_id | FK → inboxes | PK 之一 |
| epoch | INTEGER | PK 之一 |
| last_commit | TEXT | 最后处理的 commit |
| commit_count | INTEGER | 已处理 commit 数 |
| updated_at | TEXT | 更新时间 |

## 技术栈
- 后端: Python 3, FastAPI
- 数据库: SQLite3 + FTS5 (零配置，内置全文搜索)
- 前端: Vue 3, Vite
- 邮件解析: Python email 标准库
- 定时任务: systemd timer / cron

## 目录结构
```
/vol_8t/lore/
├── config.yaml
├── requirements.txt
├── lore.db                 # SQLite 数据库
├── repos/                  # git mirror 仓库
├── scripts/
│   ├── mirror.py           # 下载/同步脚本
│   ├── database.py         # 数据库 schema
│   └── import_mail.py      # 邮件导入脚本
├── start.sh                # 一键启动脚本
├── server/
│   └── app.py              # FastAPI 后端 + SPA serving
├── frontend/
│   ├── src/views/          # Vue 页面组件
│   ├── src/components/     # 可复用组件
│   ├── src/api.js          # API 客户端
│   ├── src/router.js       # 路由配置
│   └── dist/               # 生产构建产物
├── docs/plans/             # 设计文档
└── ref/                    # 参考网页
```

## 数据规模 (lkml)
- 19 个 epoch, ~593 万封邮件
- Git 仓库: 20 GB
- SQLite 数据库(含原始邮件): 预估 80-120 GB

## 实施阶段
| 阶段 | 状态 |
|------|------|
| Phase 1: 项目骨架 + git 下载脚本 | ✅ 完成 |
| Phase 2: SQLite + 邮件导入 | ✅ 完成 |
| Phase 3: FastAPI 后端 | ✅ 完成 |
| Phase 4: Vue 前端 | ✅ 完成 |
| Phase 5: 定期同步 | 待开始 |
