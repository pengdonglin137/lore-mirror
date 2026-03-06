# kernel-dev Skill 设计文档

## 目标

为内核开发人员提供一个 AI 辅助工具，涵盖日常内核开发中最具挑战性的任务：
代码阅读理解、特性演进梳理、补丁回移（backport）决策与执行、回归分析、以及内核动态跟踪。

## 核心能力概览

| 能力 | 说明 | Skill 中的章节 |
|------|------|---------------|
| 1. 代码阅读与理解 | 函数追踪、blame、commit 上下文 | Capability 1 |
| 2. 特性演进梳理 | 跨版本 diff、时间线、Fixes 图谱、回归周期 | Capability 2 |
| 3. Backport 评估 | **是否应该 backport** — 元数据信号、bug 存在性、触发概率 | Capability 3 |
| 4. Backport 执行 | **如何 backport** — 依赖分析、计划生成、验证 | Capability 4 |
| 5. 回归与影响分析 | 回归周期追踪、真实用户影响、热点代码识别 | Capability 5 |
| 6. 内核动态跟踪 | 已合入变更 + 进行中 patch (lore-mirror) | Capability 6 |

## 能力详细设计

### 1. 代码阅读与理解

**场景**: 开发者需要理解某段内核代码的逻辑、设计意图和历史背景。

**信息源**:
- `git blame` — 每行代码的最后修改者和 commit
- `git log -L :func:file` — 函数级别的修改历史
- `git log -p -- <file>` — 文件的完整修改历史
- `git show <commit>` — 单个 commit 的详细内容
- lore-mirror — 原始 patch 提交时的讨论和 review

**工作流**:
1. 定位代码：找到用户关心的函数/结构体/文件
2. 追溯历史：`git log` + `git blame` 找到关键 commit
3. 理解上下文：读取 commit message（Fixes: / Link: tags）、查找相关讨论
4. 构建知识图：梳理代码间的调用关系和依赖

### 2. 特性演进梳理

**场景**: 追踪一个内核特性从提出到合入的完整过程，或分析某个子系统在不同版本间的变化。

**关键技术** (从实际使用中总结):

- **多策略 commit 发现**: 单一搜索策略会遗漏。需要组合三种方式：
  1. `git log --grep` — commit message 搜索
  2. `git log -S` — 代码内容搜索（添加/删除特定字符串的 commit）
  3. 宽泛正则搜索 — 捕获间接相关的 commit

- **批量元数据提取**: 对大量 commit 一次性提取版本标签、日期、Fixes tag，生成版本标注时间线

- **Forward Fixes 图谱**: 不只是"这个 commit 修复了什么"，还要反向查"什么 commit 修复了这个 commit"。揭示：
  - 热点路径（被修复 3+ 次的 commit = 脆弱代码）
  - 修复链（fix-of-fix 链 = 原始设计有隐含缺陷）
  - 稳定收敛（跨 2+ 版本无 forward fix = 已稳定）

- **按主题分阶段组织**: 将 commit 按主题（bug 类别、功能区域、代码路径）分组，标注回归/revert 周期，目标是构建"为什么变化"的叙事，而非仅列出变化。

### 3. Backport 评估（"是否应该 backport"）

**这是 Capability 4（机械执行）之前的决策步骤。** 从实际 backport 经验中提炼出的评估框架：

#### 3a: 元数据信号解读

| Fixes + Cc:stable | 解读 |
|---|---|
| 都有 | 强信号：作者明确意图回移 |
| 有 Fixes，无 Cc:stable | Bug fix，但作者有顾虑（体积？风险？依赖？） |
| 无 Fixes，无 Cc:stable | Feature/improvement，风险更高，需要强理由 |
| 有 Cc:stable，无 Fixes | 少见但合理，视为故意 |

**Cc:stable 缺失时要分析原因**：可能是 diffstat 大、依赖新基础设施、不确定副作用。如果后续 fix 带有 Cc:stable，说明上游间接认可了原始 commit 的回移。

#### 3b: Bug 存在性深度验证

不只是检查 Fixes: target 是否存在，而是验证**有 bug 的代码路径在目标分支上是否可达**：
- 有 bug 的函数是否存在？
- 触发路径是否可达？
- 使能条件是否满足（feature flags、config options）？

#### 3c: 触发概率评估

| 因素 | 低概率 | 高概率 |
|------|--------|--------|
| 触发路径 | 手动管理操作 | 自动（每个 tick/每个 cgroup） |
| 使能特性 | 默认关闭/罕见配置 | 默认开启 |
| 工作负载 | 极端边界情况 | 常见（容器、多租户） |
| 累积性 | 一次性错误 | 随时间累积恶化 |

#### 3d: 跨 stable 分支审计

一次检查所有活跃 stable 分支，发现模式：已在新 stable 回移但未在旧 stable 回移 → 可能需要手动适配。

### 4. Backport 执行（"如何 backport"）

**这是整个 skill 中风险最高、技术最复杂的部分。**

**工作流**（从实践中不断完善的 6 个 Phase）:

```
Phase 1:   识别目标 commit + 提取元数据
Phase 1.5: 早期 cherry-pick 探测（用冲突引导分析方向）
Phase 2:   依赖分析（最关键）
  ├── 2a: Forward Fixes 链（修复目标 commit 的 commit 必须一起回移）
  ├── 2b: 符号存在性扫描（系统性检查新符号是否在目标分支存在）
  ├── 2c: 重命名映射表（字段/函数重命名是手动适配的 #1 错误源）
  ├── 2d: 标准依赖分析（中间 commit 遍历、context diff）
  └── 2e: 架构 vs 局部依赖评估（1-3 deps vs 10+ deps 的不同策略）
Phase 3:   生成 Backport 计划
  ├── 有序 commit 清单（REQUIRED/RECOMMENDED/OPTIONAL）
  ├── 排除清单+理由（NOT NEEDED + WHY）
  ├── 重命名映射表
  └── 风险评估
Phase 4:   验证（cherry-pick + 编译 + 代码比对）
```

**关键设计决策**:

- **Phase 1.5 是从实践中新增的**: cherry-pick 冲突本身是最精确的依赖信号——冲突位置直接告诉你哪些中间 commit 改了上下文。把它提前到 Phase 2 之前，用冲突结果引导分析方向，比纯靠代码阅读高效得多。

- **Forward Fixes 链（2a）经常被忽略**: 人类工程师容易只看目标 commit 本身，忘记检查"有没有 commit 修复了我要回移的这个 commit"。不带这些 follow-up fix 回移，等于引入上游已知的 bug。

- **重命名映射表（2c）是手动适配的核心**: 内核跨版本重构经常重命名字段和函数。映射表是手动 resolve 冲突的关键参考。

- **排除列表+理由**: 不只记录"要回移什么"，还要记录"不回移什么以及为什么"。这防止重复分析，也帮助 reviewer 理解 scope。

### 5. 回归与影响分析

**场景**: 追踪特性引入后的回归报告、评估真实用户影响。

**关键技术**:
- **回归周期追踪**: feature merge → 用户报告 → 分析 → revert/fix 的完整闭环
- **真实影响评估**: 通过 lore-mirror 搜索 backport 请求、性能回归报告、benchmark 数据
- **热点代码识别**: 累积 3+ 次 Fixes: 引用的代码 = 设计脆弱 / 测试不足 / 理解不充分

### 6. 内核动态跟踪

**已合入的变更**: `git log` 按时间/版本/作者/Fixes: 过滤

**正在进行中的**: lore-mirror 搜索最近的 PATCH 提交、review 状态

**关联分析**: commit ↔ lore 讨论（通过 Link: tag、Message-ID、subject 匹配）

## 工具集成

### 必需工具
- **git** — 代码仓库分析的基础（需要完整 clone，不能是 shallow）
- **lore-mirror API** — 内核邮件列表搜索（通过 lore-mirror skill 调用）

### 可选工具
- **cscope/ctags** — 代码交叉引用（函数调用关系）
- **scripts/get_maintainer.pl** — 查找文件/子系统的维护者
- **scripts/decode_stacktrace.sh** — 解析内核 oops/panic 堆栈

## 设计原则

1. **信息充分再决策**: 特别是 backport，必须收集足够信息后再给出建议
2. **保守优于激进**: 宁可多列一个可能的依赖，也不要遗漏
3. **透明推理过程**: 每个判断都应说明依据（哪个 commit、哪行代码、哪个讨论）
4. **版本意识**: 始终明确当前分析的是哪个内核版本/分支
5. **渐进式完善**: 这个 skill 会随着使用经验不断更新
6. **先评估再执行**: Backport 先做 Capability 3（是否应该），再做 Capability 4（如何执行）
7. **Forward Fixes 必查**: 回移目标 commit 后，必须检查有没有修复它的后续 commit
8. **排除要有理由**: 每个不回移的 commit 都要记录原因
9. **重命名映射是核心**: 跨版本字段/函数名差异是手动适配错误的 #1 来源
10. **cherry-pick 是诊断工具**: 不只是最终验证步骤，更是引导依赖分析的信号源

## 后续演进方向

- [x] 早期 cherry-pick 探测作为诊断工具 (Phase 1.5)
- [x] Forward Fixes 链分析
- [x] 符号存在性扫描
- [x] 重命名映射表
- [x] 架构 vs 局部依赖评估
- [x] Backport 评估框架（Capability 3）
- [x] 回归与影响分析（Capability 5）
- [x] 多策略 commit 发现
- [x] Forward Fixes 图谱构建
- [ ] 自动生成 backport patch 系列（带适配修改）
- [ ] 与 CI/编译测试集成（验证 backport 可编译）
- [ ] subsystem maintainer 风格识别（不同子系统有不同的 review 习惯）
- [ ] CVE 到 commit 的映射和影响范围分析
- [ ] 自动识别 "stable 候选" — 未标记 Cc: stable 但应该回移的 bug 修复
