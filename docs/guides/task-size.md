# How to choose a task size

Sizes are ordinal effort levels, never hours. Each size is about twice the
previous one.

| Size | When | Example |
|------|------|---------|
| XS | Trivial change in one place, no decision. | Fix a typo or a label, change a config value. |
| S | Small change you already understand, in one layer, with its test. | Add a field to a form; an MCP tool wrapping an existing service. |
| M | Feature across several layers (model, service, page, tests), or with a small design decision. Clear path. | Add a project setting and its form. |
| L | New concept or open questions: needs design and several work sessions. | A new entity with its migration, service, pages and docs. |

## Rules

- When you hesitate between two sizes, take the bigger one.
- A task bigger than L is split.
- A task mixing defining and doing is split too.

## In the app

The same table and rules are shown at `/sizes`. Their text comes from
`SIZE_GUIDE` and `SIZE_RULES` in `src/services/sizes.py`: change the wording
in both places.
