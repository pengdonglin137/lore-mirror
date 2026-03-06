---
name: kernel-dev
description: >-
  Linux kernel development assistant for code reading, commit analysis, feature
  evolution tracking, patch backporting, regression analysis, and subsystem
  activity monitoring. Use this skill whenever the user: mentions a kernel
  commit hash or Fixes: tag; asks about kernel source code, functions, or data
  structures; wants to understand what changed between kernel versions; needs to
  backport or cherry-pick a patch to an older kernel; asks about stable/LTS
  kernel maintenance; wants to trace how a feature evolved; mentions kernel
  regressions, reverts, or bisect; discusses LKML patches or review status;
  pastes git log output from a kernel tree; or asks about kernel subsystem
  maintainers or development activity. Even if the user doesn't say "kernel"
  explicitly, trigger when the context involves Linux kernel source, git
  histories with kernel-style commit messages (Fixes:, Cc: stable, Signed-off-by),
  or references to kernel subsystem paths (mm/, net/, fs/, drivers/, kernel/sched/).
  Requires git with a full kernel clone; optionally uses lore-mirror for mailing
  list search.
invocation_policy: automatic
---

# kernel-dev — Linux Kernel Development Assistant

## When to Use

Activate for any kernel development task:
- Reading/understanding kernel code, functions, or data structures
- Tracking feature evolution across kernel versions
- Backporting patches from mainline to stable/older kernels
- Analyzing commit dependencies for cherry-picking
- Finding what changed in a subsystem between releases
- Tracking merged or in-progress patches for a subsystem
- Bisect analysis (finding the commit that introduced a bug)
- Regression cycle analysis (feature → regression → revert/fix)
- Assessing real-world impact of kernel changes via mailing list reports
- Identifying repeatedly-fixed "hot path" code areas

## Prerequisites

- **git**: Full kernel clone (not shallow). Verify: `git log --oneline -1 v5.15` should work.
- **lore-mirror** (optional): For mailing list search. Invoke the `lore-mirror` skill when needed.

## Capability 1: Code Reading & Understanding

### Find and understand code

```bash
# Find where a function is defined
git grep -n 'function_name(' -- '*.c' '*.h'

# Who last modified each line
git blame -L <start>,<end> <file>

# History of a specific function (git tracks function boundaries)
git log -L :function_name:<file>

# Find the commit that introduced a function
git log --diff-filter=A -p -- <file> | grep -B20 'function_name'

# Full history of a file
git log --oneline -20 -- <file>
```

### Understand a commit's context

```bash
git show <commit>                                  # full message + diff
git tag --contains <commit> | head -5              # first release
git log -1 --format='%b' <commit> | grep 'Link:'  # lore discussion
```

When explaining kernel code, commit messages are essential context — they explain
**why** a change was made. Always check for:
- `Fixes:` tag → points to the bug being fixed
- `Link:` tag → points to the lore discussion
- `Cc: stable` → author intended stable backport
- Surrounding commits in the same patch series

## Capability 2: Feature Evolution Tracking

### Track changes between versions

```bash
# All changes to a subsystem between two versions
git log --oneline v5.15..v6.1 -- mm/

# Count commits per author
git shortlog -sn v5.15..v6.1 -- mm/

# When a config option was introduced
git log --all --oneline -S 'CONFIG_OPTION_NAME' -- Kconfig

# Diff a specific file between versions
git diff v5.15..v6.1 -- mm/page_alloc.c

# Merge commits (contain subsystem pull descriptions)
git log --merges --oneline v6.0..v6.1 -- mm/
```

### Multi-strategy commit discovery

A single search strategy will miss commits. Combine all three:

```bash
# Strategy 1: Commit message search
git log --oneline --all --grep="FEATURE_NAME" -- path/to/subsystem/

# Strategy 2: Code content search (catches add/remove of the string)
git log --oneline --all -S "FEATURE_NAME" -- path/to/subsystem/

# Strategy 3: Broad regex for related concepts
git log --oneline --all --grep="concept_a\|concept_b\|related_func" -- path/to/subsystem/
```

Merge and deduplicate. Strategy 1 finds commits that *discuss* the feature;
Strategy 2 finds commits that *modify code* mentioning it; Strategy 3 catches
commits that affect the feature without naming it directly.

### Batch metadata extraction

When analyzing many commits, extract metadata in one pass:

```bash
for commit in <sha1> <sha2> ...; do
  tag=$(git tag --contains $commit 2>/dev/null | grep '^v[0-9]' | head -1)
  date=$(git log -1 --format='%ci' $commit | cut -d' ' -f1)
  subj=$(git log -1 --format='%s' $commit)
  fixes=$(git log -1 --format='%b' $commit | grep 'Fixes:' | head -1)
  echo "$date | $tag | $commit | $subj | $fixes"
done
```

### Build the forward Fixes: graph

This is one of the most powerful analysis techniques — finding not just "what
does this commit fix?" but "what commits later fixed THIS commit?":

```bash
for commit in <feature-commits>; do
  short=$(echo $commit | cut -c1-12)
  fixers=$(git log --oneline --grep="$short" -- path/to/subsystem/)
  [ -n "$fixers" ] && echo "=== $short ===" && echo "$fixers"
done
```

This reveals:
- **Hot paths**: 3+ fixes indicate fragile or poorly-understood code
- **Fix cascades**: fix-of-fix chains indicate a subtle design flaw
- **Stable convergence**: no forward fixes across 2+ versions = stabilized

### Organize into evolution phases

Group raw timelines into thematic phases for readability:

1. **Natural boundaries**: major version releases, large feature additions,
   subsystem-wide refactors
2. **Theme clusters**: group by bug category (data integrity, math errors, races),
   feature area, or code path
3. **Regression/revert cycles**: treat as one narrative arc:
   introduction → regression reports → analysis → revert/fix

The goal is a narrative that explains WHY changes happened, not just WHAT.

## Capability 3: Patch Backporting

Backporting is the highest-risk kernel development task. It involves two
distinct questions: "should we backport?" and "how do we backport?"

**For the complete backport protocol** — including evaluation checklist,
dependency analysis phases, decision tree, rename mapping, and verification
steps — read `references/backport.md`.

### Quick reference: Key backport principles

1. **Check stable first**: verify the commit hasn't already been backported
2. **Always check the forward Fixes: chain**: backporting without follow-up
   fixes can introduce the same bugs upstream already fixed
3. **Use cherry-pick as diagnostic** (Phase 1.5): run `cherry-pick --no-commit`
   early to let conflict locations guide dependency analysis
4. **Verify the bug exists**: a fix for a bug that doesn't exist in target is
   unnecessary — check the Fixes: target commit AND the buggy code path
5. **Classify dependencies**: REQUIRED / RECOMMENDED / OPTIONAL / NOT NEEDED,
   always documenting WHY for exclusions
6. **Build rename mapping tables**: when field/function names differ between
   versions, an explicit mapping is essential for manual adaptation
7. **Completeness audit**: when a commit IS already backported, check that its
   follow-up fixes are also present (the "backported without follow-up" pattern
   is a dangerous known-bug scenario)

### Backport evaluation quick check

```bash
# Metadata signals
git log -1 --format='%s%n%b' <commit> | grep -E 'Fixes:|Cc:.*stable|Reported-by:|Tested-by:'

# Check if Fixes: target exists in stable branch
git tag --contains <buggy-commit> | grep <target-version>

# Check if already backported
git log --oneline <target-base>.. --grep='<target-sha-short>'

# Forward Fixes: chain
git log --oneline --grep='<target-sha-short>' HEAD -- <files>
```

## Capability 4: Kernel Activity Tracking

### Track merged changes

```bash
# Recent subsystem changes
git log --oneline --since="2 weeks ago" -- <path>

# Bug fixes specifically
git log --oneline --grep="Fixes:" --since="1 month ago" -- <path>

# Changes by a specific developer
git log --oneline --author="<name>" --since="1 month ago"
```

### Track in-progress patches (requires lore-mirror skill)

```
# Recent patches for a subsystem
GET /api/search?q=s:PATCH+d:2026-03-01..&inbox=<list>&per_page=20

# Patches from a specific developer
GET /api/search?q=s:PATCH+f:<developer>+d:2026-03-01..&inbox=<list>

# Track a patch series through revisions
GET /api/search?q=s:"PATCH+v"+b:<keyword>&inbox=<list>

# Check review status (look for Reviewed-by, Acked-by, Tested-by in replies)
GET /api/threads/{message_id}
```

### Correlate commits with lore discussions

```bash
# From a commit, find its lore discussion:
git log -1 --format='%b' <commit> | grep -E 'Link:|Message-Id:'
# Or search by subject via lore-mirror
```

## Capability 5: Regression & Impact Analysis

### Track regression cycles

A regression cycle: feature merge → user reports → analysis → revert or fix.

```bash
# Find the feature commit
git show --oneline <feature-commit>

# Search for regression reports on lore
GET /api/search?q=s:REGRESSION+bs:<feature-keyword>&inbox=lkml&per_page=20

# Find the revert or fix
git log --oneline --grep="Revert.*<feature-subject>" -- <path>
git log --oneline --grep="Fixes:.*<feature-sha-short>" -- <path>

# Read the revert for root cause
git show <revert-commit>
```

Document the full cycle: who reported, platform/workload, what regressed
(throughput, latency, crash), and resolution (revert, targeted fix, redesign).

### Assess real-world impact via lore

```
# Backport requests (users hitting bugs on stable)
GET /api/search?q=s:backport+bs:<keyword>&inbox=lkml

# Performance regressions
GET /api/search?q=s:REGRESSION+bs:<subsystem>&inbox=lkml

# Benchmark results
GET /api/search?q=bs:<keyword>+bs:benchmark&inbox=lkml
```

Impact signals:
- **Backport requests to stable/LTS** → production users affected
- **Multiple independent reporters** → widespread, not edge case
- **Workload-specific regressions** (database, network) → scopes the problem
- **Platform-specific reports** (ARM, x86) → may be arch-dependent

### Identify hot paths

When a function accumulates 3+ Fixes: references, it deserves special attention:

```bash
git log --oneline --format='%b' -- path/to/subsystem/ | \
  grep 'Fixes:' | \
  sed 's/.*Fixes: \([0-9a-f]*\).*/\1/' | \
  sort | uniq -c | sort -rn | head -20
```

Hot paths indicate design fragility, incomplete understanding of invariants,
or testing gaps. Call them out explicitly in evolution analyses.

## Integration with lore-mirror

When you need to search kernel mailing lists, invoke the `lore-mirror` skill:

1. **Find discussion for a commit**: Extract Message-ID or subject from `git show`
2. **Check review status**: Get thread via `/api/threads/{message_id}`
3. **Find backport discussions**: Search `s:PATCH b:backport` on stable@
4. **Track patch series**: Search cover letter `s:"PATCH v3 0/"`

## Key Principles

- **Verify the target branch first**: confirm which kernel version the user works with
- **Show your reasoning**: cite specific commits, code, or discussions for every judgment
- **Be conservative with backports**: when uncertain, flag as REQUIRED rather than skip
- **Respect patch series boundaries**: if a commit is 1/N of a series, understand the full series
- **Version-aware context**: the same function may behave differently across versions
