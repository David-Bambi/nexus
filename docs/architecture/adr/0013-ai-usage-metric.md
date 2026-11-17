---
status: accepted
date: 2026-11-16
---

# 0013 — AI usage metric

## Status

Accepted.

## Decision

Each task records how the AI took part in it; each project compares the
result with its own targets. Code: `models/ai.py`, `services/ai.py`,
migration `c5e2d8a1f034`. Usage: [AI usage](../../functional/ai-usage.md).

**AI mode.** `Task.ai_mode` (nullable enum `AiMode`):

| Mode | Symbol | Defined by | Done by |
|---|---|---|---|
| `AUTONOMOUS` | ✋ | David | David |
| `LEARNED` | 📚 | David | David, with AI explanations |
| `DELEGATED` | ✅ | David | AI |
| `GUIDED` | ⚠️ | AI | David |
| `DEPENDENT` | 🔴 | AI | AI |

Set by `tasks.set_ai_mode(session, task_id, mode)` (`None` clears it).

**Domain = context.** A task's domain is stored in its existing `context`
field, one of 16 fixed slugs (`services/ai.DOMAINS`, listed in
[AI usage](../../functional/ai-usage.md#domains)). Every new or changed
value is validated (`ValidationError`): `tasks.create`,
`create_in_version`, `clarify`, `update` (`_require_domain_context`) and
the importer. A legacy free tag (`@ordi`) is kept while unchanged; `None`
is always accepted.

**Nature.** Each domain has a default nature (`FOUNDING`, `REPETITIVE`,
`PERIPHERAL`). A project overrides it in `project_ai_domain` (one row per
domain, only when different from the default; setting the default back
deletes the row).

**Targets.** Per project and nature, in `project_ai_target`: two optional
bounds, `min_own_pct` (min % of ✋ + 📚) and `max_dependent_pct` (max % of
🔴). A row exists only while at least one bound is set.

**Profile.** `ai.profile(session, key)` is computed on read, never stored:

- Only `DONE` tasks of the project count; a task needs a mode and a known
  domain.
- Weight by size: XS = 1, S = 2, M = 4, L = 8, no size = M
  ([task size guide](../../guides/task-size.md)).
- Per nature: share of each mode, `own_pct`, `dependent_pct`, gaps
  (`own_pct - min`, `max - dependent_pct`; negative when missed) and `met`
  (`None` without a target or without counted tasks).
- Reports done tasks left out (no mode, unknown domain) and counted ones
  without a size.

**Events** ([0002](0002-append-only-event-log.md)):

- Mode change: task `updated` `{ai_mode: {from, to}}`.
- Settings: project `ai_settings_updated`, either
  `{domain, nature: {from, to}}` or
  `{target: <NATURE>, min_own_pct / max_dependent_pct: {from, to}}`
  (changed bounds only). No event when nothing changes.

Exposed in the web UI (task and project pages) and the MCP server (`ai_mode`
on `update_task`, tools `get_ai_settings`, `ai_profile`,
`set_domain_nature`, `set_ai_target`). The CLI only validates `--context`.

## Why

- The owner wants to see whether AI help stays where it should: little on
  founding work, free on peripheral work. Mode × nature, weighted by size,
  measures that per project.
- Computing on read keeps one source (the tasks): changing a nature, a
  target or a task's size updates the profile with no recomputation.
- Override rows only for differences: the default list can evolve without
  rewriting every project.
- Strict slugs make the domain countable; free text would split one domain
  over spellings. Trade-off, accepted by the owner: GTD context tags
  (`@ordi`, `@achat`) can no longer be set. Old ones stay until edited and
  are reported as "unknown domain". The Refine filter stays free text.

## Alternative rejected

A separate `domain` column next to `context`: keeps GTD contexts, but adds
a second classification to fill on every task. Rejected by the owner.
