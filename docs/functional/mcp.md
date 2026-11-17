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
| `get_ai_settings` | A project's nature per domain (with its default) and target per nature |
| `ai_profile` | A project's AI usage profile, see below |

Write tools (`destructiveHint: false` except `delete_criterion`;
`idempotentHint` on `update_task`, `set_criterion_done`, `set_domain_nature`
and `set_ai_target`):

| Tool | Purpose |
|---|---|
| `capture_task` | Title into the inbox |
| `add_task` | Create in a project, in the inbox or planned into a `version`; `body`, `context` (a [domain slug](ai-usage.md#domains)), `size` |
| `import_data` | Bulk import a `document` or a `text` list; `dry_run` (same rules as the [CLI import](cli.md#import)) |
| `update_task` | Change title, body, `context` (a [domain slug](ai-usage.md#domains)), size, `ai_mode` (`AUTONOMOUS`, `LEARNED`, `DELEGATED`, `GUIDED`, `DEPENDENT`); blank body/context/size/ai_mode clears it, blank title refused |
| `plan_task` | Refined task into a version |
| `unplan_task` | Planned task back to refined |
| `start_task` | Planned to doing |
| `complete_task` | Doing to done |
| `block_task` | Doing to waiting, `reason` required |
| `unblock_task` | Waiting to doing |
| `set_criterion_done` | Check or uncheck a DoD criterion by its number |
| `add_criterion` | Append a DoD criterion (`description`) |
| `update_criterion` | Reword criterion number `index` (`description`) |
| `delete_criterion` | Delete criterion number `index`; refused for the last one, later numbers shift down |
| `start_version` | Planned to in progress; returns the version like `get_version` |
| `release_version` | In progress to released; refused while a task is unfinished (cancelled ones don't count) or a criterion is unchecked |
| `set_domain_nature` | Set a domain's `nature` in a `project`; the default nature removes the override |
| `set_ai_target` | Set a `project`'s target for one `nature`: `min_own_pct`, `max_dependent_pct` (0–100); an omitted bound means no bound, omit both to remove the target |

Version and criterion tools return the version like `get_version`. Criteria
of a released version can't be changed; blank text is refused
([0010](../architecture/adr/0010-dod-editing-in-cli-and-mcp.md)).

`set_domain_nature` and `set_ai_target` return the settings like
`get_ai_settings`. `ai_profile` returns, per nature (percentages rounded to
one decimal, gaps negative when missed, `met` null without target or
counted tasks):

```json
{"project": "NX",
 "natures": [{"nature": "FOUNDING", "weight": 12,
              "shares": {"AUTONOMOUS": 66.7, "LEARNED": 0.0, "DELEGATED": 33.3,
                         "GUIDED": 0.0, "DEPENDENT": 0.0},
              "own_pct": 66.7, "dependent_pct": 0.0,
              "target": {"min_own_pct": 80, "max_dependent_pct": null},
              "own_gap": -13.3, "dependent_gap": null, "met": false}, "..."],
 "without_mode": 2, "unknown_domain": 1, "without_size": 0,
 "by_size": [{"size": "XS", "count": 3, "weight": 3, "share": 15.0}, "...",
             {"size": null, "count": 0, "weight": 0, "share": 0.0}]}
```

`by_size` lists XS, S, M, L then `null` (no size, weighed as M): counted
done tasks, their weight, and their share (%) of the total counted weight.

Rules: [0013](../architecture/adr/0013-ai-usage-metric.md).

Not exposed, use the web UI: deleting tasks, versions or projects, archiving, and
arbitrary state changes.

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
