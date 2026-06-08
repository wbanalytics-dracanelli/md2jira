# AI Agent Guidelines for md2jira Project

This document provides critical guidance for AI assistants working with the md2jira project to prevent common errors and ensure proper Markdown formatting for JIRA issue creation.

## Critical: Markdown Header Syntax vs. Lists

### ⚠️ NEVER USE `#` FOR LISTS

The `#` symbol in Markdown is **ONLY** for headers, not lists. Using `#` for list items will create extraneous JIRA Epic issues, which is absolutely not desirable.

### Correct Syntax

**Headers (Issue Creation):**
```markdown
# Epic Title                  → Creates JIRA Epic
## Story Title                → Creates JIRA Story  
### Sub-task Title            → Creates JIRA Sub-task
```

**Lists (Content within issues):**
```markdown
* Bullet point item          → Bulleted list (CORRECT)
- Bullet point item          → Bulleted list (not currently supported by md2jira, but valid JIRA)
1. Numbered item             → Numbered list (if supported)
```

### ❌ WRONG - DO NOT DO THIS:
```markdown
# User clicks the button      → Would create an unwanted Epic!
# System processes request    → Would create another unwanted Epic!
```

### ✅ CORRECT:
```markdown
* User clicks the button      → Bulleted list item
* System processes request    → Bulleted list item
```

## JIRA-Specific Formatting

### Headers within Issue Descriptions

Use JIRA's `h3.` syntax for section headers within issue descriptions:

```markdown
h3. Summary
h3. Technical Details
h3. Acceptance Criteria
```

### Code Blocks

Use JIRA's code block syntax with language specification:

```markdown
{code:python}
def example():
    return "Hello"
{code}

{code:javascript}
const example = () => "Hello";
{code}

{code:sql}
SELECT * FROM users;
{code}
```

### Inline Code

For inline code spans, JIRA uses monospace syntax `{{...}}` (double curly
braces), NOT Markdown backticks. JIRA wiki markup renders single backticks
literally, so `` `foo` `` shows up with visible backtick characters.

md2jira now auto-converts Markdown inline code to monospace, so either form is
accepted in source files:

```markdown
Use the `foo` helper.     → converted to {{foo}}
Use the {{foo}} helper.   → already JIRA-native, passes through unchanged
```

Writing `{{...}}` directly is the most explicit and renders correctly even if
the conversion is ever disabled.

### Checklists

Use checkbox syntax for checklists within issues:

```markdown
* [ ] Pending task
* [>] In-progress task
* [x] Completed task
```

**Note:** Do NOT add `h3. Checklist` headers before checklists. The checkbox formatting alone creates the checklist in JIRA.

**Instance-specific note:** The `wbagora` Jira instance does NOT have the Checklist plugin. For tickets targeting wbagora (project prefixes: ES), always use plain bulleted lists (`* item`) instead of checkbox syntax (`* [ ] item`).

### Tables

Use pipe syntax for tables:

```markdown
| Column 1 | Column 2 | Column 3 |
| --- | --- | --- |
| Value A | Value B | Value C |
| Value D | Value E | Value F |
```

### Links

Use JIRA link syntax:

```markdown
[Link Text|https://example.com/url]
```

### Text Formatting

```markdown
*bold text*
_italic text_
```

## Issue Hierarchy

The md2jira tool creates JIRA issues based on Markdown header levels:

- **H1 (`#`)**: Creates an Epic
- **H2 (`##`)**: Creates a Story by default (linked to the preceding Epic)
- **H3 (`###`)**: Creates a Sub-task (linked to the preceding Story)

### H2 Issue Type: Story (default) vs. Task

By default, `##` headers create JIRA **Story** issues. To create **Task** issues
instead, pass the `--task` / `-t` flag:

```bash
python main.py -i tickets.md -p PROJ --task   # H2 items become Tasks
python main.py -i tickets.md -p PROJ          # H2 items become Stories (default)
```

The H2 issue type can also be set per project in `.md2jira.toml` via the
`h2_issue_type` key (e.g. `h2_issue_type = "Task"`). The CLI `--task` flag takes
precedence over the TOML value, which in turn overrides the built-in `Story`
default. Regardless of the chosen JIRA type, H2 items are tracked internally as
the same hierarchy level, so epic-linking and update detection behave
identically.

### Explicit Parent Assignment

Issues can be linked to existing Epics, Stories, or Tasks using the `{parent:KEY}` annotation at the end of a header line. The annotation is stripped from the issue summary.

```markdown
## Story Title {parent:EPIC-123}
### Sub-task Title {parent:STORY-456}
```

Without explicit parents, the default sequential behavior applies (each H2 links to the preceding H1, each H3 links to the preceding H2).

CLI flags `--epic` / `-e` and `--parent` can also set default parents for all H2 and H3 issues respectively.

### Example Structure

```markdown
# Epic: User Authentication System

Epic description and business value...

## Story: User Registration

Story description...

### Sub-task: Backend API

Sub-task details...

### Sub-task: Frontend Form

Sub-task details...

## Story: User Login

Story description...

### Sub-task: Authentication Token

Sub-task details...
```

## Multi-Instance Configuration

md2jira supports multiple Jira instances via an optional `.md2jira.toml` config file. Each instance can define multiple projects with independent custom field mappings.

See `.md2jira.toml.example` for the full schema. When a config file is present, select an instance with `-n <name>`. Custom field IDs (epic name, epic link, team, checklist, parent) are configured per project within each instance.

Without a config file, md2jira falls back to `.env` environment variables (fully backward-compatible).

## Content Guidelines

### What to Include in Each Issue Type

**Epics (H1):**
- High-level business objective
- Business value and goals
- Overall acceptance criteria
- Scope and timeline

**Stories (H2):**
- User-facing feature or requirement
- Detailed acceptance criteria
- Technical requirements
- API endpoints, database schemas
- Security requirements
- User stories ("As a user, I want...")

**Sub-tasks (H3):**
- Specific implementation tasks
- Technical approach and code examples
- Task checklists with `* [ ]`, `* [>]`, `* [x]`
- Dependencies and prerequisites
- Testing requirements

## Common Mistakes to Avoid

### 1. Using `#` for Lists ❌
```markdown
# This creates an Epic, not a list item!
```

### 2. Adding Unnecessary Headers ❌
```markdown
h3. Checklist   ← Not needed; checkboxes create the checklist automatically
* [ ] Task 1
* [ ] Task 2
```

### 3. Mixing Markdown and JIRA Syntax ❌
```markdown
### h3. Section Title   ← Don't mix; use one or the other
```

### 4. Using Markdown Code Blocks (now auto-converted)
```markdown
\`\`\`python          ← Auto-converted to {code:python}
code here
\`\`\`
```

Becomes:
```markdown
{code:python}
code here
{code}
```

md2jira now converts Markdown fenced blocks to `{code:lang}` automatically, but
writing JIRA syntax directly is still preferred for clarity.

### 5. Using Markdown Inline Backticks (now auto-converted)
```markdown
Use the `foo` helper.   ← Auto-converted to {{foo}}
```

Becomes:
```markdown
Use the {{foo}} helper.
```

Single backticks render literally in JIRA, so without conversion they appear as
visible backtick characters. md2jira now converts `` `text` `` to `{{text}}`,
but writing `{{text}}` directly is preferred.

## Pre-Creation Checklist

Before creating or modifying md2jira Markdown files, verify:

- [ ] All headers use correct levels (# for Epic, ## for Story, ### for Sub-task)
- [ ] No `#` symbols used for list items
- [ ] Code blocks use `{code:language}` syntax (Markdown fences are auto-converted)
- [ ] Inline code uses `{{...}}` monospace (Markdown backticks are auto-converted)
- [ ] Checklists use `* [ ]`, `* [>]`, `* [x]` without extra headers
- [ ] Links use `[text|url]` JIRA syntax
- [ ] Section headers within issues use `h3.` prefix
- [ ] Tables use pipe `|` syntax
- [ ] Text formatting uses `*bold*` and `_italic_`

## Testing New Content

When creating example or test files:

1. Prefix all titles with a test identifier (e.g., `TESTING 2025-11-20 -- `)
2. Keep hierarchy consistent (Epic → Stories → Sub-tasks)
3. Include diverse formatting examples to demonstrate capabilities
4. Verify no unintended issue creation before running md2jira

## Additional Resources

- Review `example.md` for basic usage patterns
- Review `example-full.md` for comprehensive formatting examples
- Check the main README for project-specific requirements
- Consult JIRA documentation for supported text formatting

---

## Summary: The Golden Rules

1. **`#` is ONLY for headers (issue creation), NEVER for lists**
2. **Use `*` for bulleted lists within issue descriptions**
3. **Use JIRA syntax (`h3.`, `{code}`, `[text|url]`) for formatting within issues**
4. **Follow strict hierarchy: H1=Epic, H2=Story, H3=Sub-task**
5. **Test content before creating real JIRA issues**

Following these guidelines will ensure proper JIRA issue creation without unwanted artifacts or structural problems.

