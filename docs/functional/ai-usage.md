# AI usage

Each done task records its domain and how the AI took part in it; the
project page compares the result with the project's targets. Design and
rules: [0013](../architecture/adr/0013-ai-usage-metric.md).

## Domains

A task's domain is its `context` field. Only these slugs are accepted when
a context is set or changed (web, CLI `--context`, MCP, import). A project
can override the default nature of any domain.

| Slug | Label | Default nature |
|---|---|---|
| `exploration` | Exploration and brainstorming | Founding |
| `conception` | Design and architecture | Founding |
| `code-core` | Code: core logic | Founding |
| `code-repetitive` | Code: repetitive cases, glue | Repetitive |
| `tests-design` | Tests: what to test | Founding |
| `tests-variants` | Tests: writing variants | Repetitive |
| `debug` | Debugging | Founding |
| `comments` | Code comments | Founding |
| `examples` | Examples | Founding |
| `translation` | Translation | Peripheral |
| `docs` | Documentation and guides | Peripheral |
| `readme` | README | Peripheral |
| `project-mgmt` | Project management | Peripheral |
| `assets` | Graphic assets | Peripheral |
| `tools` | Tools (scripts, hooks) | Peripheral |
| `versioning` | Versioning and releases | Peripheral |

## AI modes

✋ Autonomous, 📚 Learned, ✅ Delegated, ⚠️ Guided, 🔴 Dependent; meaning in
[0013](../architecture/adr/0013-ai-usage-metric.md).

## Screens

- **Task page**, edit form: "Domain" list (labels; a legacy value such as
  `@ordi` stays selectable so saving keeps it), "Size" list with the meaning
  of each size and a "Size guide" link to `/sizes`, "AI mode" list
  (blank clears it). The details panel shows Domain (label, or the raw
  legacy value), Size and AI mode.
- **Inbox / clarify form**: same Domain and Size lists.
- **Version page**, add-task form: Domain list and a Size list with each
  size's meaning as a tooltip.
- **Project page**, "AI usage" section: one row per nature, the share of
  each mode (✋ 📚 ✅ ⚠️ 🔴), the target, and the result (✅ met / ❌
  missed, with the ✋ + 📚 share; "—" without target or counted tasks).
  The section's hint links to `/sizes`. Then "Weight by size": one row
  per size plus "No size" (weighed as M), with the weight each, the
  number of counted tasks, their weight and their share of the total
  weight ("—" when zero). Counted tasks are done, with a mode and a known
  domain. Below: counts of done tasks without mode, with an unknown
  domain, and without size.
- **Task sizes** (`/sizes`): table Size | Weight | When | Example and the
  rules ([task size guide](../guides/task-size.md)). Linked under the
  Size list of the task and clarify forms (not the version page's compact
  add form) and from the project's AI usage section.
- **Project page**, "AI settings" (collapsed): targets per nature (min
  ✋ + 📚 %, max 🔴 %, blank = no bound) and the nature of each domain
  (default marked). One "Save AI settings" button
  (`POST /projects/<key>/ai`); a value outside 0–100 saves nothing and
  shows the error.
- **Refine** filter: context stays a free-text field.

## MCP

`update_task` (`ai_mode`), `get_ai_settings`, `ai_profile`,
`set_domain_nature`, `set_ai_target`: see [MCP server](mcp.md).
