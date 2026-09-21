# Command line

`nexus` reads and creates data on the same database as the web service (see
[0006](../architecture/adr/0006-cli-shares-the-database.md)).

```bash
scripts/install_cli.sh install     # bare `nexus` command, from any directory
scripts/install_cli.sh uninstall   # remove it
uv run nexus <command>             # no-install alternative (after `uv sync`)
```

`install` runs `uv tool install --editable --force .`, which places a `nexus`
executable in uv's tool bin dir (`~/.local/bin`; add it to `PATH` if
missing). It is editable, so it follows the checkout: no reinstall after code
changes, only after moving the repo. `uninstall` runs `uv tool uninstall
nexus`. `python -m src.cli <command>` also works.

Exit codes: `0` ok, `1` a rule of the data refused the request, `2` wrong
command line. Errors go to stderr.

## References

- Tasks and versions have a short immutable **ref**: `t-4k2`, `v-9xa`
  (case-insensitive). It is shown in the web UI and in every CLI table.
- Projects are named by their **key**. Keys that look like a ref, or equal a
  command word (`add`, `help`, `import`, `projects`, `tasks`, `version`,
  `versions`), are refused when creating a project.
- A version is named by its number or its `v-` ref.

## Commands

| Command | Result |
|---|---|
| `nexus version` | App version |
| `nexus tasks` / `versions` / `projects` | Table of all rows, `(none)` if empty |
| `nexus <project>` | Project detail and its versions |
| `nexus <project> <version>` | Version detail, its tasks, definition of done as `[x]` / `[ ]` with a count |
| `nexus <t-ref>` | Task detail |
| `nexus <v-ref>` | Version detail |
| `nexus add task <project> [<version>] [-t T] [-b B] [-c C] [-s SIZE]` | Create a task |
| `nexus "<description>"` | Capture into the inbox |
| `nexus import <file\|->` | Bulk import, see below |

`add task` without a version creates an inbox task attached to the project;
with a version it creates a task already planned. `--size` is `XS`, `S`,
`M` or `L`. Without `--title`, it prompts on a terminal and fails otherwise.
A lone argument that is blank or contains whitespace is a capture.

```bash
nexus add task NX 1.0 -t "Write the CLI page" -s S
nexus "buy a USB-C cable"
nexus NX 1.0
```

Everything the CLI creates is logged with actor `cli`
([0002](../architecture/adr/0002-append-only-event-log.md)).

## Import

`nexus import <file|-> [--dry-run] [--text]`; `-` reads stdin.
Design: [0007](../architecture/adr/0007-importer-mcp-entry-point.md).

```json
{"projects": [{"key": "NX", "name": "Nexus", "description": "...",
   "versions": [{"number": "1.0", "title": "First", "goal": "...",
                 "dod": ["Docs written"],
                 "tasks": [{"title": "Write docs", "body": "...",
                            "context": "@ordi", "size": "S"}]}]}],
 "tasks": [{"title": "Loose idea"},
           {"title": "Attached", "project": "NX"},
           {"title": "Planned", "project": "NX", "version": "1.0"}]}
```

- Projects match by `key`, versions by `number` within the project. An
  existing one is **reused, never overwritten** (its `title`, `goal`, `dod`
  are ignored) but its nested tasks are still created.
- A new project needs `name`; a new version needs `title` and a non-empty
  `dod`.
- Tasks are always created: importing the same file twice duplicates them.
- Top-level tasks go to the inbox; `project` attaches them; `project` +
  `version` plans them. `version` alone is an error. New tasks in a released
  version are refused.
- Unknown fields are errors. Refs and ids are not part of the format.
- **All-or-nothing**: all problems are listed at once (each names its
  entry), and nothing is written if there is any.
- `--dry-run` runs everything, rolls back and prints what would be created
  (no refs).
- `--text` reads one task title per line into the inbox.

The JSON export (`/export.json`) is a backup format and can't be imported.

## Not in scope

The CLI cannot edit, change a task's state or toggle a DoD criterion, and
there is no MCP server yet.
