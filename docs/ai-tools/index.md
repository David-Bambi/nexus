# AI tools

How Claude Code is configured to work in this repository.

## CLAUDE.md files

Instructions that load automatically into context, scoped by directory:

- `CLAUDE.md` (root) — project overview, stack, architecture constraints
  (ADR-001 to ADR-004), domain model, increment plan.
- `docs/CLAUDE.md` — rules specific to editing the documentation tree.

## Subagents (`.claude/agents/`)

| Agent | Purpose |
| --- | --- |
| `docs-manager` | Reads `docs/` for context before changes, writes/updates it after a task, builds/serves the MkDocs site. Never edits `artifacts/specs/` or hand-writes `docs/reference/`. |

## Conventions Claude follows here

- **Source of truth is `docs/`.** `artifacts/specs/` is background only; on
  conflict `docs/` wins.
- **Generated artifacts** (specs, exploratory output) go in `artifacts/`,
  never committed as authoritative documentation.
- **`docs/reference/`** is generated at build time from `src/` docstrings —
  never hand-edited.
- Every task that changes behavior is expected to update `docs/` in the
  same pass, per the root `CLAUDE.md`.
