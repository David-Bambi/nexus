# MCP server

Nexus exposes its data to an AI assistant (Claude Code) through the Model
Context Protocol. It is an endpoint of the running service, not a separate
process. Design and security: [0008](../architecture/adr/0008-mcp-over-http-on-the-service.md).

```bash
claude mcp add --transport http nexus http://127.0.0.1:8765/mcp
```

Read-only tools can be auto-allowed in Claude Code; write tools prompt for
approval. That is the write safeguard: the server has no read-only mode.
After a redeploy of the service, reconnect (`/mcp` in Claude Code).

Servers added with `claude mcp add` are only loaded when a Claude Code
session starts: restart Claude Code (open a fresh session) before the tools
appear. `claude mcp list` shows the connection status.

Transport: `POST /mcp`, JSON-RPC 2.0, one JSON reply per POST, no sessions.
Only requests from the machine itself are accepted (no authentication).

## Tools

30 tools. The server's `instructions` (sent on `initialize`) summarize the
2.0 model: the tree, keys vs refs, capture vs add vs clarify, the computed
version. A test checks that every tool they name exists.

Read tools (`readOnlyHint`):

| Tool | Purpose |
|---|---|
| `list_projects` | Projects and subprojects, each with its `version` (`include_archived`) |
| `list_tasks` | Features and tasks, filtered by `state`, `project`; `limit` |
| `get_project` | `version`, `criteria`, `subprojects` (with `version`) and `tree`; closed items only with `include_closed` |
| `get_task` | All fields plus event history; a feature adds its direct `children` (closed included) |
| `inbox` | Captured tasks to triage |
| `search` | Substring of title or body; `limit` |
| `dashboard` | Doing/waiting items, inbox and refine counts |

Item write tools:

| Tool | Purpose |
|---|---|
| `capture_task` | Title into the inbox |
| `add_task` | Into a project's tree, refined: `project` and/or `parent` (only a parent: its project), `title`, `kind` (`task` default, `feature`), `body`, `context`, `size` |
| `clarify_task` | Inbox or someday item to refined: `title`, `project`, `parent`, `kind`, `body`, `context`, `size`; omitted fields keep their value |
| `update_task` | Change title, body, context, size; blank body/context/size clears it, blank title refused |
| `move_task` | To a project's top level and/or under a feature (`project`, `parent`); keeps its state, a feature takes its subtree |
| `change_kind` | Task to feature, or empty feature to task; the ref letter follows (`t-` / `f-`) |
| `reorder_task` | `direction` `up` or `down` among siblings; an open item skips closed ones |
| `start_task` | Refined to doing |
| `complete_task` | Doing to done; a feature only once its children are done or cancelled |
| `block_task` | Doing to waiting, `reason` required |
| `unblock_task` | Waiting to doing |
| `reopen_task` | Done to doing; a feature keeps its `released_in` |
| `cancel_task` | Open item to cancelled; a feature only once its children are closed |
| `restore_task` | Cancelled to refined |
| `defer_task` | Inbox or refined to someday |
| `import_data` | Bulk import a `document` or a `text` list; `dry_run` (same rules as the [CLI import](cli.md#import)) |

Project and version write tools:

| Tool | Purpose |
|---|---|
| `create_project` | `key`, `name`, `description`; `parent` (a root key) makes a subproject |
| `update_project` | `name` and/or `description`; blank description clears it |
| `add_criterion` | Append a criterion for the next major version (`text`) |
| `update_criterion` | Change criterion `number`'s `text` |
| `set_criterion_done` | Check or uncheck criterion `number` (`done`) |
| `delete_criterion` | Remove criterion `number`; later numbers shift down |
| `release_major` | MAJOR + 1, MINOR 0, list emptied; refused unless it has criteria, all checked |

Criterion tools and `release_major` return `{project, version, criteria}`.
MINOR is never set by a tool: it rises when a feature is completed
([0016](../architecture/adr/0016-computed-version.md)).

Hints: write tools have `destructiveHint: false` except `delete_criterion`
(`true`). `idempotentHint` on `update_task`, `update_project`,
`update_criterion`, `set_criterion_done`.

Not exposed, use the web UI: deleting items or projects, archiving and
restoring projects, arbitrary state changes.

## Identification

- Project or subproject: its key.
  Feature or task: its ref (`f-4k2`, `t-4k2`); a task turned into a
  feature answers to both.
- Serialized items carry `kind`, `parent` and `released_in` (the
  version a feature shipped in, else null). In `tree`, each item also has
  nested `children`.
- Criteria are identified by `number`, counted from 1 in list order
  (`criteria`: `{number, text, done}`).
- Results never contain integer ids.
- Each tool has a strict JSON Schema; unknown arguments are refused and
  strings are stripped.

## Results and errors

- A result carries `content` (JSON text) and `structuredContent`.
- A refusal by validation or by a service (unknown ref, invalid transition,
  feature with open children...) is a tool result with `isError: true` and the
  message; HTTP status stays 200 and the change is rolled back.
- An unexpected exception becomes an `isError` result "internal error, see
  the server log"; the traceback is in `app.log`.
- An unknown tool is JSON-RPC error `-32602`.
- HTTP-level refusals (wrong Host, Origin, Content-Type, oversized body)
  return `421`, `403`, `415`, `413`.
- `MCP-Protocol-Version`: on every message except `initialize`, a header
  naming a version the server does not speak (it speaks `2025-11-25`,
  `2025-06-18`, `2025-03-26`, `2024-11-05`) is refused with `400`.
  `initialize` may name any version and is answered with the client's own
  if supported, else the newest. Claude Code probes with a newer version,
  takes the `400`, then retries `initialize` with `2025-11-25`; this is
  normal.

Everything written through the tools is logged with actor `mcp`
([0002](../architecture/adr/0002-append-only-event-log.md)).

## Limits

- No authentication: loopback plus an Origin/Host guard only.
- Not available while the service is down.
- `limit` defaults to 100, max 500; no further pagination.
- Two simultaneous writers can, very rarely (about 1 in 46,000), collide on
  a ref and get the internal-error result; retry.
- Log: one line per call, without arguments.
