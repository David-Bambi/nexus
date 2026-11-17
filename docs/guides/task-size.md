# How to choose a task size

Sizes are ordinal effort levels, never hours. Each size is about twice the
previous one: they weigh 1, 2, 4 and 8 in a project's AI usage profile. A
task with no size counts as M.

| Size | Weight | When | Example |
|------|--------|------|---------|
| XS | 1 | Trivial change in one place, no decision. | Fix a typo or a label, change a config value. |
| S | 2 | Small change you already understand, in one layer, with its test. | Add a field to a form; an MCP tool wrapping an existing service. |
| M | 4 | Feature across several layers (model, service, page, tests), or with a small design decision. Clear path. | Add a project setting and its form. |
| L | 8 | New concept or open questions: needs design and several work sessions. | A new entity with its migration, service, pages and docs. |

## Rules

- Hesitating between two sizes? Take the bigger one.
- A task bigger than L is split.
- A task mixing defining and doing is split too.
