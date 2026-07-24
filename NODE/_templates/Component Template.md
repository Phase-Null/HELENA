---
tags: [template, component]
date: 2026-03-05
status: active
---

# Component Template

Use this template when documenting a new HELENA component in the Architecture section.

---

## Template

```markdown
---
tags: [architecture, {component_tag}]
date: {date}
status: {active | deprecated | planned | stub}
component: {path to source file}
bugs: [{list of bug IDs affecting this component}]
---

# {Component Name} — {Brief Description}

{One-paragraph overview of what this component does and its role in HELENA's architecture.}

> [!info] Quick Facts
> - **File**: `{source_path}`
> - **Class**: `{main_class_name}`
> - **Init order**: {when this component is initialized relative to others}
> - **Dependencies**: {list of other components it depends on}

---

## Architecture

{Describe the internal structure: classes, methods, data flow. Include actual class names, method signatures, and parameter names from the source code.}

### Key Methods

| Method | Signature | Purpose |
|--------|-----------|---------|
| `{method_name}` | `({params})` → `{return_type}` | {description} |

### Key Data Structures

| Structure | Type | Purpose |
|-----------|------|---------|
| `{field_name}` | `{type}` | {description} |

---

## Configuration

| Config Key | Default | Purpose |
|-----------|---------|---------|
| `{key}` | `{default}` | {description} |

---

## Known Bugs

> [!warning] Bug #{ID}: {Title}
> {Brief description. Link to full details.}
> See [[Bug Fixes Registry#Bug {ID}]].

---

## Related Notes

- [[{Parent Component}]] — where this is initialized
- [[{Sibling Component}]] — related component
- [[{Config Reference}]] — configuration details
- [[Bug Fixes Registry]] — bugs affecting this component
```

---

## Section Guidelines

| Section | What to Include |
|---------|----------------|
| Overview | 1-2 sentences about purpose and role |
| Architecture | Actual class names, method signatures, data flow diagrams |
| Key Methods | Table with method name, signature, and purpose |
| Key Data Structures | Table with field name, type, and purpose |
| Configuration | Config keys that affect this component |
| Known Bugs | Wikilinks to Bug Fixes Registry entries |
| Related Notes | Wikilinks to connected components |

> [!tip] Source Code Accuracy
> All content should be derived from **actual source code** — include real class names, method signatures, parameter names, line numbers, and implementation details. Never use generic placeholder text.
