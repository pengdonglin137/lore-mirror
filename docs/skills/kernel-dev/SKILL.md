---
name: kernel-dev
description: >-
  Linux kernel development assistant — code reading, feature evolution tracking,
  patch backporting, and kernel activity monitoring. Use when: reading kernel source,
  understanding commit history, backporting patches between kernel versions,
  tracking subsystem development, analyzing Fixes: tags, cherry-picking, or
  tracing code changes across kernel releases. Requires git and optionally lore-mirror.
invocation_policy: automatic
---

# kernel-dev — Linux Kernel Development Assistant

## When to Use

Activate when the user wants to:
- Understand kernel code, functions, or data structures
- Track how a feature evolved across kernel versions
- Backport a patch/fix from mainline to an older kernel
- Find what changed in a subsystem between two versions
- Track latest patches (merged or in-progress) for a subsystem
- Analyze commit dependencies for cherry-picking
- Find the commit that introduced a bug (bisect analysis)

## Prerequisites

- **git**: Full kernel repository clone (not shallow). Verify: `git log --oneline -1 v5.15` should work
- **lore-mirror** (optional but recommended): For mailing list search. Invoke the `lore-mirror` skill when needed.

## Capability 1: Code Reading & Understanding

### Understand a function or code path
```bash
# Find where a function is defined
git grep -n 'function_name(' -- '*.c' '*.h'

# Who last modified each line
git blame -L <start>,<end> <file>

# Full history of a file
git log --oneline -20 -- <file>

# History of a specific function (git can track function boundaries)
git log -L :function_name:<file>

# Find commit that introduced a function
git log --diff-filter=A -p -- <file> | grep -B20 'function_name'
```

### Understand a commit's context
```bash
# Read the full commit (message + diff)
git show <commit>

# What release first included this commit
git tag --contains <commit> | head -5

# Find related discussion on lore (use lore-mirror skill)
# Search by commit subject or Message-ID from commit trailer
```

When explaining code, always:
1. Read the commit message — it explains WHY, not just WHAT
2. Check for `Fixes:` tags — they point to the bug being fixed
3. Check for `Link:` tags — they point to lore discussions
4. Look at surrounding commits in the same patch series

## Capability 2: Feature Evolution Tracking

### Track changes between kernel versions
```bash
# All changes to a subsystem between two versions
git log --oneline v5.15..v6.1 -- mm/

# Count commits per author in a subsystem
git shortlog -sn v5.15..v6.1 -- mm/

# Find when a config option was introduced
git log --all --oneline -S 'CONFIG_OPTION_NAME' -- Kconfig

# Diff a specific file between versions
git diff v5.15..v6.1 -- mm/page_alloc.c

# Find merge commits (contain subsystem pull descriptions)
git log --merges --oneline v6.0..v6.1 -- mm/
```

### Build a feature timeline
1. Identify the feature's key files/functions/config options
2. Find the initial commit: `git log --diff-filter=A -- <file>` or `git log --all -S 'feature_keyword'`
3. List all versions: `git tag --contains <initial-commit> | grep '^v[0-9]' | head`
4. For each version pair, summarize changes: `git log --oneline <v_old>..<v_new> -- <files>`
5. Search lore-mirror for the original RFC/proposal and major revision discussions

## Capability 3: Patch Backport (CRITICAL — Read Carefully)

Backporting is the highest-risk task. Follow this protocol strictly.

### Phase 1: Identify the Target Commit

```bash
# If user provides a commit hash
git show --stat <commit>
git log -1 --format='%H %s%n%nFixes: %b' <commit> | grep -E '^(Fixes:|Cc:.*stable)'

# If user describes a bug, search for the fix
git log --grep="<keyword>" --oneline -- <relevant-path>
# Or search lore-mirror for the discussion
```

**Extract key metadata:**
- `Fixes:` tag → identifies the original buggy commit
- `Cc: stable@vger.kernel.org` → author intended this for stable backport
- Patch series context → is this 1/N of a series? Get all N patches
- `Link:` or `Message-ID` → find the lore discussion
- **No Fixes: tag** → this is a feature/improvement, not a bug fix. Risk is higher;
  the motivation for backporting needs extra scrutiny.

**Identify patch series membership:**

Extract the series ID from the `Link:` URL. For example, if Link contains
`20250708165630.1948751-7`, the series ID is `1948751` and this is patch 7.
```bash
# Find all commits in the same series
git log --oneline --grep='<series-id>' -- <files>
# Or by author + time window
git log --oneline <commit>~N..<commit> --author='<author>' -- <files>
```

**Check for existing stable backports:**
```bash
# Has this already been backported to the target stable branch?
git log --oneline <target-base>.. --grep='<target-sha-short>'
# Stable backports contain "[ Upstream commit <sha> ]" in message body
git log --oneline <target-base>.. --grep='Upstream commit'
```

### Phase 1.5: Early Cherry-pick Test (Do This Before Deep Analysis)

**Use cherry-pick as a diagnostic tool, not just a final step.** The conflicts
tell you exactly which intermediate commits changed the context.

```bash
git checkout -b backport-probe <target-branch>
git cherry-pick --no-commit <target-commit> 2>&1
# If conflicts:
git diff --name-only --diff-filter=U   # which files conflict?
git diff <conflicted-file>             # WHERE are the conflicts?
# Clean up
git reset --hard HEAD && git checkout - && git branch -D backport-probe
```

- **Clean apply** → dependency chain is likely short, proceed to Phase 2 for verification
- **Context-only conflicts** → find intermediate commits that changed surrounding lines
- **Missing symbols** → deep dependency chain, focus Phase 2 on tracing symbol introductions
- **Massive conflicts** → likely architectural change in between, evaluate feasibility early

### Phase 2: Dependency Analysis (MOST IMPORTANT)

**This is where backports fail.** A commit may depend on prior changes that are not bug fixes.

#### 2a: Forward Fixes Chain (Who fixed the target?)

**Critical step often missed.** After identifying the target commit, search for
commits that fix bugs *in* the target commit itself:

```bash
# Find commits whose Fixes: tag references our target
git log --oneline --grep='<target-sha-short>' HEAD -- <files>
# Example: target is 79f3f9bedd14
git log --oneline --grep='79f3f9bedd14' HEAD -- kernel/sched/
```

If found, these follow-up fixes almost always must be co-backported. A backport
without its follow-up fixes can introduce the *same bugs* the follow-ups fixed.

#### 2b: Symbol Existence Scan

Systematically check whether all new symbols (functions, macros, struct fields)
used in the target diff exist in the target branch:

```bash
# Extract new symbols from the diff's added lines
git show <commit> -- <file> | grep '^+' | grep -oP '\b[a-z_]+\(' | sort -u
# Check each against the target branch
for sym in func_a func_b field_c; do
  count=$(git show <target-branch>:<file> | grep -c "$sym")
  echo "$sym: $count occurrences"
done
```

- All symbols exist → likely a shallow dependency chain
- Missing symbols → trace each with `git log --all -S '<symbol>' -- <file>` to
  find the introducing commit, then evaluate *its* dependencies recursively

#### 2c: Field/Symbol Rename Mapping

When symbols exist under different names, build a mapping table:

```bash
# Find renames between target branch and commit
git log --oneline <target-branch>..<commit> -S '<new_name>' -- <files>
# Compare both versions side by side
git show <target-branch>:<file> | grep -n '<pattern>'
git show <commit>^:<file> | grep -n '<pattern>'
```

Common kernel renames to watch for:
- `cfs_rq->nr_running` → `cfs_rq->nr_queued`
- `cfs_rq->avg_vruntime` (field) → `cfs_rq->sum_w_vruntime`
- `rq->curr` → `rq->donor` (in scheduler context split)
- `avg_vruntime_add/sub()` → `sum_w_vruntime_add/sub()`

Document the mapping table in the backport plan — it is essential for manual adaptation.

#### 2d: Standard Dependency Analysis

```bash
# List ALL commits between target branch and the fix, for affected files
git log --oneline <target-branch>..HEAD -- <modified-files>

# Check what the target branch's version of the file looks like
git show <target-branch>:<file> | head -50

# Compare context around the changed lines
git diff <target-branch>..HEAD -- <file>

# Find commits in the same patch series
git log --oneline --grep="<series-prefix>" HEAD
# e.g., if commit subject starts with "[PATCH v3 5/8] mm:", search for "[PATCH v3" + "mm:"

# Check the Fixes: chain — does the buggy commit exist in target branch?
git tag --contains <buggy-commit> | grep <target-version>
# If the buggy commit is NOT in the target branch, the fix is NOT needed!

# Find all commits that modify the same function
git log -L :function_name:<file> <target-branch>..HEAD
```

#### 2e: Architectural vs Local Dependency Assessment

When missing symbols are found, classify the dependency depth:

- **Local dependency** (1-3 commits): The symbol was introduced by a small,
  self-contained commit. Example: a helper function extracted from inline code.
  → Backport the introducing commit along with the target.

- **Architectural dependency** (10+ commits): The symbol is part of a major
  subsystem rework (new preemption model, scheduler restructure, etc).
  → The target commit likely cannot be cherry-picked without porting the entire
  architecture change. Consider manual adaptation or abandoning the backport.

To distinguish: trace the introducing commit and check *its* dependencies:
```bash
# How many files does the introducing commit touch?
git show --stat <introducing-commit> | tail -1
# Does it depend on yet more new infrastructure?
git show <target-branch>:<file> | grep -c '<symbols-from-introducing-commit>'
```

**Dependency classification:**
- **REQUIRED**: Commit changes the same lines or introduces symbols used by the target commit. Without it, cherry-pick will conflict or code won't compile.
- **RECOMMENDED**: Commit changes nearby context or related logic. Without it, the fix may apply but behavior might differ subtly.
- **OPTIONAL**: Cleanup, refactoring, or cosmetic changes. Nice to have but not necessary for correctness.
- **NOT NEEDED**: Unrelated changes to the same file. Skip. **Always document WHY
  a commit is not needed** — e.g., "pure rename, no logic change" or "independent
  feature, only caused context conflict".

**Red flags that indicate missing dependencies:**
- Cherry-pick conflict in context lines (not the changed lines themselves)
- Symbols (functions, macros, struct fields) not found in target branch
- Different function signatures between mainline and target
- File has been renamed or moved

### Phase 3: Generate Backport Plan

Present the plan as an ordered list:

```
Backport plan: <fix-commit-subject> → <target-branch>

Patches to apply (in order):
1. [REQUIRED]  <sha1-short> <subject>     — adds helper function used by fix
2. [REQUIRED]  <sha1-short> <subject>     — refactors API that fix depends on
3. [TARGET]    <sha1-short> <subject>     — THE FIX ITSELF
4. [REQUIRED]  <sha1-short> <subject>     — follow-up fix (Fixes: <target>)

Patches NOT needed (with reasons):
- <sha1-short> <subject> — pure rename, no logic change
- <sha1-short> <subject> — independent feature, only caused context conflict
- <sha1-short> <subject> — modifies same file but different functions

Rename mapping table (for manual adaptation):
  mainline name          → target branch name
  cfs_rq->nr_queued      → cfs_rq->nr_running
  rq->donor              → rq->curr

Risk assessment: <LOW/MEDIUM/HIGH>
Reason: <brief explanation>

Manual adaptation needed:
- <file>:<function> — <description of what needs manual change>
```

### Phase 4: Verify

```bash
# Create a test branch
git checkout -b backport-test <target-branch>

# Apply commits in order
git cherry-pick --no-commit <commit1>
git diff --cached --stat  # review what changed
git reset HEAD  # if issues, analyze and adjust

# After all commits applied successfully
# 1. Compile test (at minimum)
make -j$(nproc) <relevant-target>  # e.g., mm/page_alloc.o

# 2. Compare the result with mainline
git diff <mainline-commit> -- <modified-files>
# The backported code should be functionally equivalent
```

### Backport Decision Tree

```
Q: Does the target commit have a Fixes: tag?
├── NO → This is a feature/improvement, NOT a bug fix.
│        Risk is inherently higher. Verify the backport motivation is strong.
│        Skip the Fixes-existence check below and proceed to cherry-pick test.
└── YES → Continue

Q: Does the Fixes: commit exist in the target branch?
├── NO → This fix is NOT needed for this branch. Stop.
└── YES → Continue

Q: Are there commits that fix the TARGET commit? (forward Fixes: chain)
├── YES → These MUST be co-backported. Add to the plan.
└── NO  → Continue

Q: Has this already been backported to the target stable branch?
├── YES → Check if the existing backport is sufficient. May already be done.
└── NO  → Continue

Q: Does the fix cherry-pick cleanly? (Phase 1.5 early probe)
├── YES → Low risk. Verify compile and review.
└── NO → Analyze conflicts:
    ├── Context mismatch only → Find intermediate commits that changed context
    │   (often just rename commits or unrelated refactors — may not need backporting)
    ├── Missing symbol (1-3 deps) → Local dependency, backport introducing commits
    ├── Missing symbol (10+ deps) → Architectural dependency, evaluate feasibility:
    │   consider manual adaptation or abandoning the backport
    ├── File renamed → Use git log --follow, adapt paths
    └── Struct field changes → Build rename mapping table, adapt manually
```

## Capability 4: Kernel Activity Tracking

### Track merged changes
```bash
# Recent changes to a subsystem
git log --oneline --since="2 weeks ago" -- <path>

# Bug fixes specifically
git log --oneline --grep="Fixes:" --since="1 month ago" -- <path>

# Changes by a specific maintainer
git log --oneline --author="<name>" --since="1 month ago"
```

### Track in-progress patches (requires lore-mirror skill)
```
# Recent patches for a subsystem
GET /api/search?q=s:PATCH+d:2026-03-01..&inbox=<list>&per_page=20

# Patches from a specific developer
GET /api/search?q=s:PATCH+f:<developer>+d:2026-03-01..&inbox=<list>

# Track a specific patch series through revisions
GET /api/search?q=s:"PATCH+v"+b:<keyword>&inbox=<list>

# Check if a patch has been reviewed/acked
GET /api/threads/{message_id}
# Look for: Reviewed-by:, Acked-by:, Tested-by: in replies
```

### Correlate git commits with lore discussions
```bash
# From a commit, find its lore discussion:
# 1. Check for Link: tag in commit message
git log -1 --format='%b' <commit> | grep 'Link:'

# 2. Or search by Message-ID (often in commit trailers)
git log -1 --format='%b' <commit> | grep 'Message-Id:'

# 3. Or search by subject
# Use lore-mirror: GET /api/search?q=s:"<commit-subject>"
```

## Integration with lore-mirror Skill

When you need to search kernel mailing lists, invoke the `lore-mirror` skill. Key integration points:

1. **Find discussion for a commit**: Extract Message-ID or subject from `git show`, search via lore-mirror
2. **Check review status**: Get the thread via `/api/threads/{message_id}`, look for Reviewed-by/Acked-by
3. **Find backport discussions**: Search `s:PATCH b:backport` or `s:PATCH b:"cherry-pick"` on stable@
4. **Track patch series**: Search cover letter `s:"PATCH v3 0/"` to find the full series

## Important Principles

1. **Always verify the target branch first**: Confirm which kernel version/branch the user is working with
2. **Never skip dependency analysis for backports**: This is where errors happen
3. **Show your reasoning**: For every dependency judgment, cite the specific commit/code/discussion
4. **Be conservative**: When uncertain, flag a commit as REQUIRED rather than skipping it
5. **Check if the bug exists**: A fix for a bug that doesn't exist in the target branch is unnecessary
6. **Respect patch series boundaries**: If a commit is part of a series (1/N), understand the full series
7. **Version-aware context**: The same function may behave differently across versions
8. **Always check forward Fixes: chain**: After identifying the target, search for commits that fix *it*. Backporting a commit without its follow-up fixes can introduce the same bugs upstream already fixed.
9. **Check stable branch first**: Before starting analysis, verify the commit hasn't already been backported to the target stable branch (e.g., v6.12.y).
10. **Document exclusions**: For every commit you decide NOT to backport, record why. This prevents re-analysis and helps reviewers understand the scope.
11. **Build rename mapping tables**: When field/function names differ between versions, create an explicit mapping table. This is the #1 source of errors in manual adaptation.
12. **Use cherry-pick as diagnostic, not just verification**: Run `cherry-pick --no-commit` early (Phase 1.5) to let conflict locations guide your dependency analysis, rather than doing all analysis by code reading alone.
