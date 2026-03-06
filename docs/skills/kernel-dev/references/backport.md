# Backport Protocol — Full Reference

This document contains the complete backport workflow: evaluation ("should we?"),
dependency analysis, execution, and verification. Read this when performing a
backport task.

## Table of Contents

1. [Evaluation: Should We Backport?](#evaluation-should-we-backport)
2. [Mechanics: How to Backport](#mechanics-how-to-backport)
3. [Decision Tree](#decision-tree)

---

## Evaluation: Should We Backport?

Before doing the mechanical work of backporting, evaluate whether a commit
**should** be backported. This is a separate decision from "can we backport it."

### Metadata Signals

```bash
git log -1 --format='%s%n%b' <commit> | grep -E 'Fixes:|Cc:.*stable|Reported-by:|Tested-by:'
```

| Signal | Interpretation |
|--------|---------------|
| `Fixes:` + `Cc: stable` | Strong signal: author intended stable backport |
| `Fixes:` only | Bug fix, but author had concerns (size? risk?). Evaluate further. |
| Neither present | Feature/improvement. Higher risk. Need strong justification. |
| `Cc: stable` without `Fixes:` | Unusual but possible. Treat as intentional. |

**When `Cc: stable` is absent on a bug fix**, reason about why:
- Large diffstat (net deletions can still seem "big" to reviewers)
- Depends on recent infrastructure not in stable
- Author was unsure about side effects
- Check if follow-up fixes carry `Cc: stable` — if so, upstream implicitly endorses
  backporting the original

### Bug Existence Verification

Don't just check "does the Fixes: target commit exist." Verify the **buggy code path**
is reachable on the target branch:

```bash
# 1. Does the buggy function/code exist?
git show <target-branch>:<file> | grep -n '<buggy-function-or-pattern>'

# 2. What are the trigger paths?
git show <target-branch>:<file> | grep -n '<callers-of-buggy-function>'

# 3. Are enabling conditions met? (feature flags, config options)
git show <target-branch>:<relevant-config-file> | grep '<relevant-feature>'
```

### Trigger Probability Assessment

Not all bugs are equal. Assess how likely real users will hit this:

| Factor | Low Probability | High Probability |
|--------|----------------|------------------|
| Trigger path | Manual admin action | Automatic (every tick/request) |
| Enabling features | Disabled by default / rare config | Enabled by default |
| Workload | Exotic corner case | Common (containers, multi-tenant) |
| Accumulation | One-shot error | Cumulative (gets worse over time) |

### Cross-Stable-Branch Audit

Check **all** active stable branches in one pass:

```bash
for tag in v6.12 v6.13 v6.14 v6.15; do
  latest=$(git tag -l "${tag}.*" | sort -V | tail -1)
  if [ -n "$latest" ]; then
    count=$(git log --oneline $tag..$latest --grep='<target-sha-short>' 2>/dev/null | wc -l)
    echo "$latest: $count"
  fi
done
```

Patterns:
- Backported to newer stable but not older → may need manual adaptation for older
- Not in any stable → either too new, or intentionally skipped
- In target stable already → check if follow-up fixes are also present

### Existing Backport Completeness Audit (CRITICAL)

**When a commit is already backported, the analysis is NOT done.** Check whether
its follow-up fixes are also present:

```bash
# Step 1: Find the backported commit in stable
git log --oneline <target-base>..<latest-stable> --grep='<target-sha-short>'

# Step 2: Find ALL follow-up fixes (forward Fixes: chain)
git log --oneline --grep='<target-sha-short>' HEAD -- <files>

# Step 3: Check if each follow-up is in stable
for fix_sha in <follow-up-shas>; do
  short=$(echo $fix_sha | cut -c1-12)
  in_stable=$(git log --oneline <target-base>..<latest-stable> --grep="$short" | wc -l)
  echo "$short: in_stable=$in_stable — $(git log -1 --format='%s' $fix_sha)"
done
```

**Danger pattern: "backported without follow-up"** — the original commit is in
stable but its critical fix-of-fix is missing. Stable users are running with a
**known bug introduced by the backport itself**. Requires urgent action: either
backport the follow-up fix or revert the original from stable.

### Verdict Template

```
Backport evaluation: <commit-sha> → <target-branch>

Bug exists in target:     YES/NO  (cite specific code path)
Trigger probability:      LOW/MEDIUM/HIGH  (cite trigger paths + enabling conditions)
Cc: stable:               YES/NO  (if NO, reason: ...)
Already in stable:        YES (v6.12.N) / NO
Follow-up fixes complete: YES / NO — missing: <sha> <subject>
Dependency chain:         N patches, risk: LOW/MEDIUM/HIGH

Verdict: SHOULD BACKPORT / SHOULD NOT / ALREADY DONE (but needs follow-up)
```

---

## Mechanics: How to Backport

Backporting is the highest-risk task. Follow this protocol strictly.

### Phase 1: Identify the Target Commit

```bash
# If user provides a commit hash
git show --stat <commit>
git log -1 --format='%H %s%n%nFixes: %b' <commit> | grep -E '^(Fixes:|Cc:.*stable)'

# If user describes a bug, search for the fix
git log --grep="<keyword>" --oneline -- <relevant-path>
```

**Extract key metadata:**
- `Fixes:` tag → identifies the original buggy commit
- `Cc: stable@vger.kernel.org` → author intended this for stable backport
- Patch series context → is this 1/N of a series? Get all N patches
- `Link:` or `Message-ID` → find the lore discussion
- **No Fixes: tag** → feature/improvement, not a bug fix. Risk is higher.

**Identify patch series membership:**

Extract the series ID from the `Link:` URL (e.g., `20250708165630.1948751-7`
→ series `1948751`, patch 7):
```bash
git log --oneline --grep='<series-id>' -- <files>
```

**Check for existing stable backports:**
```bash
git log --oneline <target-base>.. --grep='<target-sha-short>'
git log --oneline <target-base>.. --grep='Upstream commit'
```

### Phase 1.5: Early Cherry-pick Test

**Use cherry-pick as a diagnostic tool, not just a final step.** Conflicts
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

- **Clean apply** → dependency chain is likely short
- **Context-only conflicts** → find intermediate commits that changed surrounding lines
- **Missing symbols** → deep dependency chain, focus on tracing symbol introductions
- **Massive conflicts** → likely architectural change, evaluate feasibility early

### Phase 2: Dependency Analysis

**This is where backports fail.** A commit may depend on prior changes that
aren't bug fixes.

#### Forward Fixes Chain

After identifying the target, search for commits that fix bugs *in* the target:

```bash
git log --oneline --grep='<target-sha-short>' HEAD -- <files>
```

These follow-up fixes almost always must be co-backported. A backport without
them can introduce the *same bugs* the follow-ups fixed.

#### Symbol Existence Scan

Check whether all new symbols in the diff exist in the target branch:

```bash
# Extract new symbols from added lines
git show <commit> -- <file> | grep '^+' | grep -oP '\b[a-z_]+\(' | sort -u
# Check each against target branch
for sym in func_a func_b field_c; do
  count=$(git show <target-branch>:<file> | grep -c "$sym")
  echo "$sym: $count occurrences"
done
```

- All exist → shallow dependency chain
- Missing → trace with `git log --all -S '<symbol>' -- <file>` to find the
  introducing commit, then evaluate *its* dependencies recursively

#### Field/Symbol Rename Mapping

When symbols exist under different names, build a mapping table:

```bash
git log --oneline <target-branch>..<commit> -S '<new_name>' -- <files>
git show <target-branch>:<file> | grep -n '<pattern>'
git show <commit>^:<file> | grep -n '<pattern>'
```

Document the mapping table in the backport plan — it is the #1 source of errors
in manual adaptation.

#### Standard Dependency Analysis

```bash
# All commits between target branch and the fix for affected files
git log --oneline <target-branch>..HEAD -- <modified-files>

# Target branch version of the file
git show <target-branch>:<file> | head -50

# Context diff
git diff <target-branch>..HEAD -- <file>

# Check Fixes: chain — does the buggy commit exist in target branch?
git tag --contains <buggy-commit> | grep <target-version>
# If NOT in target branch → fix is NOT needed!

# All commits that modify the same function
git log -L :function_name:<file> <target-branch>..HEAD
```

#### Architectural vs Local Dependency

When missing symbols are found, classify the dependency depth:

- **Local dependency** (1-3 commits): Symbol introduced by a small, self-contained
  commit (e.g., a helper extracted from inline code). → Backport the introducing
  commit along with the target.

- **Architectural dependency** (10+ commits): Symbol is part of a major subsystem
  rework. → Consider manual adaptation or abandoning the backport.

To distinguish:
```bash
git show --stat <introducing-commit> | tail -1
git show <target-branch>:<file> | grep -c '<symbols-from-introducing-commit>'
```

**Dependency classification:**
- **REQUIRED**: Changes same lines or introduces symbols used by target. Without it,
  cherry-pick will conflict or code won't compile.
- **RECOMMENDED**: Changes nearby context or related logic. Without it, the fix may
  apply but behavior might differ subtly.
- **OPTIONAL**: Cleanup, refactoring, cosmetic. Not necessary for correctness.
- **NOT NEEDED**: Unrelated changes to the same file. **Always document WHY** —
  e.g., "pure rename, no logic change" or "independent feature, only caused
  context conflict".

**Red flags indicating missing dependencies:**
- Cherry-pick conflict in context lines (not the changed lines)
- Symbols not found in target branch
- Different function signatures between mainline and target
- File has been renamed or moved

### Phase 3: Generate Backport Plan

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

Rename mapping table (for manual adaptation):
  mainline name          → target branch name
  new_func_name()        → old_func_name()
  struct->new_field      → struct->old_field

Risk assessment: <LOW/MEDIUM/HIGH>
Reason: <brief explanation>

Manual adaptation needed:
- <file>:<function> — <description of what needs manual change>
```

### Phase 4: Verify

```bash
git checkout -b backport-test <target-branch>

# Apply commits in order
git cherry-pick --no-commit <commit1>
git diff --cached --stat  # review
git reset HEAD            # if issues, analyze and adjust

# After all commits applied:
# 1. Compile test
make -j$(nproc) <relevant-target>  # e.g., mm/page_alloc.o

# 2. Compare result with mainline
git diff <mainline-commit> -- <modified-files>
# Backported code should be functionally equivalent
```

---

## Decision Tree

```
Q: Does the target commit have a Fixes: tag?
├── NO → Feature/improvement, NOT a bug fix.
│        Risk is inherently higher. Verify motivation is strong.
│        Skip Fixes-existence check, proceed to cherry-pick test.
└── YES → Continue

Q: Does the Fixes: commit exist in the target branch?
├── NO → Fix is NOT needed for this branch. Stop.
└── YES → Continue

Q: Are there commits that fix the TARGET commit? (forward Fixes: chain)
├── YES → These MUST be co-backported. Add to the plan.
└── NO  → Continue

Q: Has this already been backported to the target stable branch?
├── YES → Run Completeness Audit:
│         Check if ALL follow-up fixes are also present.
│         ├── Present → Already done. Stop.
│         └── MISSING → Dangerous! Backport missing follow-ups urgently.
└── NO  → Continue

Q: Does the fix cherry-pick cleanly?
├── YES → Low risk. Verify compile and review.
└── NO → Analyze conflicts:
    ├── Context mismatch only → Find intermediate commits that changed context
    ├── Missing symbol (1-3 deps) → Local dep, backport introducing commits
    ├── Missing symbol (10+ deps) → Architectural dep, evaluate feasibility
    ├── File renamed → git log --follow, adapt paths
    └── Struct field changes → Build rename mapping table, adapt manually
```
