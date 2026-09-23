---
status: accepted
date: 2026-09-21
---

# 0008 — The MCP server is a Flask endpoint on the running service

## Status

Accepted

## Decision

The MCP server is `POST /mcp` on the service already running on
`127.0.0.1:8765`: stateless JSON-RPC 2.0 over Streamable HTTP in plain-JSON
mode (one POST, one JSON reply; no SSE, no sessions). It is a hand-written
Flask blueprint (`src/mcp_server/http.py`), registered by `create_app`.
Usage: [MCP server](../../functional/mcp.md).

- **Methods**: `initialize` (negotiates among `2025-11-25`, `2025-06-18`,
  `2025-03-26`, `2024-11-05`; returns short `instructions`), `ping`,
  `tools/list`, `tools/call`. Notifications and client replies get `202`;
  batches are refused; `GET` / `PUT` / `DELETE` get `405`.
- **Layering**: `tools.py` (20 tools) and `serialize.py` are
  transport-agnostic and call `services/` only; they must not import Flask.
  Only `http.py` may. `tests/test_architecture.py` enforces it. Same rule as
  [0001](0001-services-ignore-http.md), one level up.
- **Actor**: events written by the tools carry `events.ACTOR_MCP = "mcp"`.
  To allow it, `actor` (default `web`) is now a parameter of **every**
  mutating service, not only the creation ones (see
  [0002](0002-append-only-event-log.md), [0006](0006-cli-shares-the-database.md)).
- **Resolver**: `resolve.py` moved from `src/cli/` to `src/services/` so the
  tool layer does not import the CLI. `services/views.py` gained
  `list_tasks` for the `list_tasks` tool.
- **Scope**: 9 read tools and 11 write tools. Deleting, archiving,
  releasing or starting versions, DoD add/edit/delete and arbitrary state
  changes are deliberately not exposed; they stay in the web UI.
  Starting and releasing versions were later exposed by
  [0009](0009-version-lifecycle-in-cli-and-mcp.md) (13 write tools, 22 in all).
- **Write safety**: rely on the client's permissions (Claude Code prompts for
  write tools; read-only tools carry `readOnlyHint`). No server-side
  read-only mode.

## Spike: two routes tried

Both passed the official SDK client (initialize, list, call).

| | Official `mcp` SDK 2.x under waitress (via a2wsgi) | Hand-written Flask blueprint (chosen) |
|---|---|---|
| Works | Only if the ASGI lifespan is run by hand on the adapter's event loop | Yes, in Flask's own threads |
| Dependencies | About 30 new | None |
| Session | Separate from the app's per-request session | The app's per-request session |
| Odd behaviour | `GET` returned 500 | `405` |
| Origin / Host / Content-Type protection | Built in | Written and tested by us (about 100 lines plus guard) |

The real Claude Code client was not run during the spike (registering it
edits the user's Claude config). It was tested afterwards against the
running endpoint: it connected, listed the 20 tools, and read tools and a
dry-run `import_data` worked from a session.

## Security guard

There is no authentication ([0004](0004-localhost-only.md)), and a browser
on the machine can reach loopback, so `_guard()` runs before the body is
parsed:

| Check | Refusal |
|---|---|
| `Host` is `127.0.0.1`, `localhost` or `::1` (any port) | `421` |
| `Origin`, if present, equals the server's own host:port exactly | `403` |
| `Content-Type` is `application/json` | `415` |
| Body at most 1 MB | `413` |

The Host check stops DNS rebinding. The exact-Origin check blocks other sites
and even pages on other local ports; Claude Code sends no `Origin`. A
cross-site form cannot send `application/json` without a preflight, and no
CORS header is ever sent, so preflights fail.

### Protocol-version header

Not part of the pre-parse guard: `endpoint` checks `MCP-Protocol-Version`
after the body is parsed, on every message except `initialize`. After the
handshake, a header naming a version the server does not speak is refused
with `400`. `initialize` may name any version, even a newer one, and is
answered with the client's own version if supported, else the newest the
server speaks: that is what the handshake negotiates.

Observed with Claude Code (service log): it first probes with
`MCP-Protocol-Version: 2026-07-28` (newer than this server) and gets the
intended `400`, then falls back to a normal `initialize` asking for
`2025-11-25`, which is agreed; from then on it sends the agreed version. The
service logs each handshake (`MCP initialize: client asked … agreed …`) and
each refusal with the offending value.

## Why

The service is always up (autostart), so there is nothing extra to launch
and no second process opening the database. Reusing Flask keeps the
dependency list unchanged and the tools on the same session and services as
the web pages. The SDK route needed a workaround for its lifespan and ~30
packages for what is a handful of JSON-RPC methods.

## Consequences and known limits

- No authentication: the protection is loopback plus the guard above. The
  existing web form `POST` routes have no CSRF protection either; that is
  pre-existing and out of scope here.
- Unusable while the service is down; the connection drops during a
  redeploy and the client must reconnect.
- A ref collision between two simultaneous writers (about 1 in 46,000 per
  overlapping pair) would surface as the internal-error result.
- No pagination beyond `limit` (default 100, max 500).
- One log line per call (tool and ok/error), never the arguments.

## Alternative rejected

- **Official SDK under waitress**: see the spike table.
- **stdio subprocess (`nexus mcp`)**: the other standard transport. The user
  chose HTTP on the service so the server is always available and the
  client has nothing to spawn.
