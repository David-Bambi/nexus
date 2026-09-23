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

Read tools (`readOnlyHint`):

| Tool | Purpose |
|---|---|
| `list_projects` | Projects (`include_archived`) |
| `list_versions` | Versions of one project (`project`) or of all |
| `list_tasks` | Tasks, filtered by `state`, `project`, `version`; `limit` |
| `get_project` | A project and its versions |
| `get_version` | Tasks and definition of done, criteria numbered from 1 |
| `get_task` | All fields plus event history |
| `inbox` | Captured tasks to triage |
| `search` | Substring of title or body; `limit` |
| `dashboard` | In-progress versions, doing/waiting tasks, inbox and refine counts |

Write tools (all `destructiveHint: false`; `idempotentHint` on
`update_task` and `set_criterion_done`):

| Tool | Purpose |
|---|---|
| `capture_task` | Title into the inbox |
| `add_task` | Create in a project, in the inbox or planned into a `version`; `body`, `context`, `size` |
| `import_data` | Bulk import a `document` or a `text` list; `dry_run` (same rules as the [CLI import](cli.md#import)) |
| `update_task` | Change title, body, context, size; blank body/context/size clears it, blank title refused |
| `plan_task` | Refined task into a version |
| `unplan_task` | Planned task back to refined |
| `start_task` | Planned to doing |
| `complete_task` | Doing to done |
| `block_task` | Doing to waiting, `reason` required |
| `unblock_task` | Waiting to doing |
| `set_criterion_done` | Check or uncheck a DoD criterion by its number |
| `start_version` | Planned to in progress; returns the version like `get_version` |
| `release_version` | In progress to released; refused while a task is unfinished (cancelled ones don't count) or a criterion is unchecked |

Not exposed, use the web UI: deleting tasks or projects, archiving,
adding/editing/deleting DoD criteria, and arbitrary state changes.

## Identification

- Project: its key. Task: its ref (`t-4k2`). Version: its ref (`v-9xa`), or
  its number together with `project`.
- Results never contain integer ids.
- Each tool has a strict JSON Schema; unknown arguments are refused and
  strings are stripped.

## Results and errors

- A result carries `content` (JSON text) and `structuredContent`.
- A refusal by validation or by a service (unknown ref, invalid transition,
  released version...) is a tool result with `isError: true` and the
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
