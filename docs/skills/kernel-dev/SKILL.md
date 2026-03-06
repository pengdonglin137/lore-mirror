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

### Phase 2: Dependency Analysis (MOST IMPORTANT)

**This is where backports fail.** A commit may depend on prior changes that are not bug fixes.

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

**Dependency classification:**
- **REQUIRED**: Commit changes the same lines or introduces symbols used by the target commit. Without it, cherry-pick will conflict or code won't compile.
- **RECOMMENDED**: Commit changes nearby context or related logic. Without it, the fix may apply but behavior might differ subtly.
- **OPTIONAL**: Cleanup, refactoring, or cosmetic changes. Nice to have but not necessary for correctness.
- **NOT NEEDED**: Unrelated changes to the same file. Skip.

**Red flags that indicate missing dependencies:**
- Cherry-pick conflict in context lines (not the changed lines themselves)
- Symbols (functions, macros, struct fields) not found in target branch
- Different function signatures between mainline and target
- File has been renamed or moved

### Phase 3: Generate Backport Plan

Present the plan as an ordered list:

```
Backport plan: <fix-commit-subject> → <target-branch>

1. [REQUIRED]  <sha1-short> <subject>     — adds helper function used by fix
2. [REQUIRED]  <sha1-short> <subject>     — refactors API that fix depends on
3. [TARGET]    <sha1-short> <subject>     — THE FIX ITSELF
4. [RECOMMENDED] <sha1-short> <subject>  — follow-up fix for edge case

Risk assessment: <LOW/MEDIUM/HIGH>
Reason: <brief explanation>

Manual adaptation needed:
- <file>:<line> — <description of what needs manual change>
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
Q: Does the Fixes: commit exist in the target branch?
├── NO → This fix is NOT needed for this branch. Stop.
└── YES → Continue

Q: Does the fix cherry-pick cleanly?
├── YES → Low risk. Verify compile and review.
└── NO → Analyze conflicts:
    ├── Context mismatch → Find intermediate commits that changed context
    ├── Missing symbol → Find commit that introduced the symbol
    ├── File renamed → Use git log --follow, adapt paths
    └── Major refactor → Manual adaptation needed (HIGH risk)
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
