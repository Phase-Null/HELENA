---
tags: [template, bugfix]
date: 2026-03-05
status: active
---

# Bug Fix Template

Use this template when documenting a new bug fix in the [[Bug Fixes Registry]] or in a component-specific note like [[AEGIS/Bug Fixes]].

---

## Template

```markdown
---
tags: [bugfix, {category}]
date: {date}
status: {needs_fix | already_fixed | phantom_file | no_action}
---

# Bug {ID}: {Title}

## Overview

| Field | Value |
|-------|-------|
| **Bug ID** | {number} |
| **Severity** | {CRITICAL | HIGH | MEDIUM | LOW} |
| **Priority** | {P0 | P1 | P2 | P3} |
| **File** | {path to affected file} |
| **Lines** | {affected line numbers} |
| **Category** | {desktop | kernel | ml | aegis | security | runtime | training | core | integration | scripts} |
| **Status** | {needs_fix | already_fixed | phantom_file | no_action} |

## Description

{What went wrong. Include the observed behavior and expected behavior.}

## Root Cause

{Why it happened. Trace the code path that leads to the bug.}

## Fix Summary

{Brief description of the fix approach.}

## Fix Code

```{language}
{The actual code change. Include before/after if applicable.}
```

## Fix Type

{replace | add | delete | rewrite | none}

## Affected Lines

{Specific line numbers that need modification.}

## Cross-References

- Related component: [[{Component Note}]]
- Related bugs: [[Bug Fixes Registry#Bug {ID}]]
- Related files: [[{File Note}]]
```

---

## Field Definitions

| Field | Description |
|-------|------------|
| Bug ID | Sequential number from HELENA_FULL_FIXES.md |
| Severity | CRITICAL (crash/security bypass), HIGH (data loss/functional), MEDIUM (incorrect behavior), LOW (cosmetic/style) |
| Priority | P0=Critical, P1=High, P2=Medium, P3=Low |
| Category | Which subsystem is affected |
| Status | Current fix state |
| Fix Type | What kind of code change is needed |

---

## Example Entry

> [!example] Bug 10: Emotion Modulation Is a No-Op
> 
> | Field | Value |
> |-------|-------|
> | **Bug ID** | 10 |
> | **Severity** | HIGH |
> | **File** | `helena_core/kernel/personality.py` lines 425-492 |
> | **Category** | kernel |
> | **Status** | needs_fix (re-audit fix applied) |
> | **Fix Type** | rewrite |
> 
> Three bugs make ALL emotion modulation non-functional: (1) intensity always 0.0, (2) case mismatch, (3) commentary same bug. See [[Personality System]].
