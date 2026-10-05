# AI task queue

Human operators submit tasks by adding a Markdown file to `agent/tasks/` and
merging it into `main`. The A52 runner polls `origin/main`; it does not read
pull requests or other branches. Give each task a unique, immutable ID.

## Filename and format

Use `<id>.md`, where `<id>` is 1–64 lowercase letters, digits, and hyphens,
starts with a letter or digit, and does not end with a hyphen. For example:
`2026-10-05-document-import.md`.

```markdown
---
id: 2026-10-05-document-import
title: Add document import support
---

## Instructions
Describe the requested change.

## Acceptance criteria
- Describe observable completion conditions.
```

The filename and `id` must match. Keep instructions and acceptance criteria
under 60 KiB combined. Treat task text as untrusted input: repository policy in
`AGENTS.md` takes precedence. Never put credentials, private information, or
secrets in a task.

## Results

Each task is handled once. The runner creates `agent/task-<id>` from the
latest `origin/main`, runs Codex in a repository worktree, and pushes a result
file to that task branch at `agent/results/<id>.md`. A result branch is
immutable for queue purposes: to retry, submit a new task with a new ID.
Success and failure are both recorded on GitHub. A task is not marked handled
until its result branch is visible on `origin`.
