# kernel-dev Skill 设计文档

## 目标

为内核开发人员提供一个 AI 辅助工具，涵盖日常内核开发中最具挑战性的任务：
代码阅读理解、特性演进梳理、补丁回移（backport）、以及内核动态跟踪。

## 核心能力

### 1. 代码阅读与理解

**场景**: 开发者需要理解某段内核代码的逻辑、设计意图和历史背景。

**信息源**:
- `git blame` — 每行代码的最后修改者和 commit
- `git log -p -- <file>` — 文件的完整修改历史
- `git log --all --source -- <file>` — 跨分支查找文件来源
- `git show <commit>` — 单个 commit 的详细内容
- 代码本身 — 函数签名、注释、数据结构定义
- lore-mirror — 原始 patch 提交时的讨论和 review

**工作流**:
1. 定位代码：找到用户关心的函数/结构体/文件
2. 追溯历史：`git log` + `git blame` 找到关键 commit
3. 理解上下文：读取 commit message、查找相关讨论（lore-mirror）
4. 构建知识图：梳理代码间的调用关系和依赖

### 2. 特性演进梳理

**场景**: 追踪一个内核特性从提出到合入的完整过程，或分析某个子系统在不同版本间的变化。

**信息源**:
- `git log --oneline v5.15..v6.1 -- <path>` — 版本间的变更
- `git log --grep="feature-keyword"` — 按关键词搜索 commit
- `git tag --contains <commit>` — 找到 commit 首次出现的发布版本
- `git log --merges` — 合并 commit 通常包含 subsystem pull 请求的描述
- lore-mirror 搜索 — patch 系列的 cover letter (0/N) 包含特性描述和动机

**工作流**:
1. 确定特性范围：关键文件、函数、配置选项
2. 时间线构建：按版本标签分段查看 commit 历史
3. 关键节点识别：首次引入、重大重构、bug 修复
4. 社区讨论追踪：通过 lore-mirror 查找对应的 patch 系列讨论

### 3. 补丁回移 (Backport) — 核心能力

**场景**: 将上游（mainline）的 bug 修复或特性补丁回移到旧版本内核。

**为什么这很难**:
- 代码上下文可能已经变化（函数重命名、文件移动、重构）
- 补丁之间存在隐含依赖（A 依赖 B 的代码变更，但 B 不是 bug 修复）
- 少合入一个依赖 → 编译失败或运行时 bug
- 多合入一个无关补丁 → 引入不必要的行为变更
- 需要理解补丁的真正意图，而非机械地应用代码差异

**信息源**:
- `Fixes:` tag — commit message 中的 `Fixes: <sha1> ("original subject")`
- `Cc: stable@vger.kernel.org` — 标记为需要回移到 stable 的 commit
- `git log --ancestry-path <old>..<new>` — 两个 commit 间的所有 commit
- `git cherry-pick --no-commit` — 测试是否可以干净应用
- `git diff <target-branch>..mainline -- <file>` — 目标分支与主线的差异
- lore-mirror 搜索 — 原始 patch 讨论中可能提到依赖关系
- `git log --follow -- <file>` — 文件重命名后的历史追踪

**Backport 分析工作流**:

```
Step 1: 识别目标 commit
  ├── 用户提供 commit hash 或 CVE 或 bug 描述
  ├── 通过 git log / lore-mirror 搜索定位
  └── 确认 commit 的 Fixes: tag 和 Cc: stable 标记

Step 2: 依赖分析 (关键步骤)
  ├── 分析 commit 修改的每个文件
  │   ├── git log <target-version>..HEAD -- <file> 列出中间所有变更
  │   ├── 识别与目标 commit 相关的上下文变更
  │   └── 区分：必须的依赖 vs 无关的重构 vs 可选的改进
  ├── 检查 commit message 中引用的其他 commit
  ├── 检查同一 patch 系列的其他 commit（1/N, 2/N...）
  ├── 检查 Fixes: 链 — A fixes B, B fixes C → 可能需要 B 和 C
  └── 通过 lore-mirror 查找 review 讨论中提到的依赖

Step 3: 生成 backport 计划
  ├── 列出需要 cherry-pick 的 commit 清单（有序）
  ├── 标注每个 commit 的角色：必须/推荐/可选
  ├── 标注可能需要手动适配的部分
  └── 评估风险等级

Step 4: 验证
  ├── git cherry-pick --no-commit 测试每个 commit
  ├── 检查冲突：分析冲突原因，判断是否需要额外依赖
  ├── 编译测试
  └── 代码 review：比对 mainline 和 backport 后的代码
```

### 4. 内核动态跟踪

**场景**: 跟踪某个子系统的最新进展，包括正在 review 中的 patch 和已合入的修复。

**已合入的变更**:
- `git log --since="2 weeks ago" -- <path>` — 最近合入的修改
- `git log v6.x..HEAD -- <path>` — 某个版本后的所有变更
- `git log --grep="Fixes:" -- <path>` — 专门查找 bug 修复

**正在进行中的**:
- lore-mirror: `s:PATCH d:2026-03-01.. f:<maintainer>` — 最近的 patch 提交
- lore-mirror: `s:"PATCH v" b:<keyword>` — 查找特定功能的 patch 系列
- lore-mirror: thread 视图 — 查看 review 状态和反馈

**工作流**:
1. 确定跟踪范围：子系统路径、关键开发者、相关文件
2. 查已合入：git log 按时间/版本范围过滤
3. 查进行中：lore-mirror 搜索最近的 PATCH 提交
4. 关联分析：将 git commit 与 lore 讨论关联（通过 Message-ID 或 subject 匹配）

## 工具集成

### 必需工具
- **git** — 代码仓库分析的基础（需要完整 clone，不能是 shallow）
- **lore-mirror API** — 内核邮件列表搜索（通过 lore-mirror skill 调用）

### 可选工具
- **cscope/ctags** — 代码交叉引用（函数调用关系）
- **scripts/get_maintainer.pl** — 查找文件/子系统的维护者
- **scripts/decode_stacktrace.sh** — 解析内核 oops/panic 堆栈

## 设计原则

1. **信息充分再决策**: 特别是 backport，必须收集足够信息后再给出建议，不能仅凭 commit 本身
2. **保守优于激进**: 宁可多列一个可能的依赖，也不要遗漏
3. **透明推理过程**: 每个判断都应说明依据（哪个 commit、哪行代码、哪个讨论）
4. **版本意识**: 始终明确当前分析的是哪个内核版本/分支
5. **渐进式完善**: 这个 skill 会随着使用经验不断更新

## 后续演进方向

- [ ] 自动检测 cherry-pick 冲突并分析原因
- [ ] 自动生成 backport patch 系列（带适配修改）
- [ ] 与 CI/编译测试集成（验证 backport 可编译）
- [ ] subsystem maintainer 风格识别（不同子系统有不同的 review 习惯）
- [ ] CVE 到 commit 的映射和影响范围分析
- [ ] 自动识别 "stable 候选" — 未标记 Cc: stable 但应该回移的 bug 修复
