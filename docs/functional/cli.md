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

- Subprojects, features and tasks have a short immutable **ref**: `s-4k2`,
  `f-4k2`, `t-4k2` (case-insensitive). A task turned into a feature keeps
  its code: `t-4k2` and `f-4k2` both find it. Refs are shown in the web UI
  and in every CLI table.
- Projects are named by their **key**. Keys that look like a ref, or equal a
  command word (`add`, `help`, `import`, `projects`, `tasks`, `version`,
  `versions`), are refused when creating a project.

## Commands

| Command | Result |
|---|---|
| `nexus version` | App version |
| `nexus tasks` / `projects` | Table of all rows, `(none)` if empty |
| `nexus <project>` | Project detail and its subprojects |
| `nexus <s-ref>` | Subproject detail |
| `nexus <f-ref>` / `<t-ref>` | Feature or task detail |
| `nexus add task <project> [-t T] [-b B] [-c C] [-s SIZE]` | Create a task in the project's inbox |
| `nexus "<description>"` | Capture into the inbox |
| `nexus import <file\|->` | Bulk import, see below |

`--size` is `XS`, `S`, `M` or `L`. Without `--title`, `add task` prompts on
a terminal and fails otherwise. A lone argument that is blank or contains
whitespace is a capture.

```bash
nexus add task NX -t "Write the CLI page" -s S
nexus "buy a USB-C cable"
nexus NX
nexus f-4k2
```

Everything the CLI creates or changes is logged with actor `cli`
([0002](../architecture/adr/0002-append-only-event-log.md)).

## Import

`nexus import <file|-> [--dry-run] [--text]`; `-` reads stdin.
Design: [0007](../architecture/adr/0007-importer-mcp-entry-point.md), format
[0015](../architecture/adr/0015-tree-import-format.md).

```json
{"projects": [{"key": "NX", "name": "Nexus", "description": "...",
   "items": [{"kind": "feature", "title": "Docs",
              "children": [{"title": "Write docs", "body": "...",
                            "context": "@ordi", "size": "S"}]}],
   "subprojects": [{"key": "NX-WEB", "name": "Web UI",
                    "items": [{"title": "Fix the header"}]}]}],
 "tasks": [{"title": "Loose idea"},
           {"title": "Attached", "project": "NX"}]}
```

- Projects and subprojects match by `key`. An existing one is **reused,
  never overwritten** (its `name`, `description` are ignored) but its items
  are still created. It can't change place (root vs subproject, or parent).
- A new project needs `name`.
- An item's `kind` is `feature` or `task` (default); only a feature takes
  `children`, at any depth. Items in a project tree are created refined.
- Top-level `tasks` go to the inbox; `project` attaches them.
- Tasks are always created: importing the same file twice duplicates them.
- Unknown fields are errors. Refs and ids are not part of the format.
- **All-or-nothing**: all problems are listed at once (each names its
  entry), and nothing is written if there is any.
- `--dry-run` runs everything, rolls back and prints what would be created
  (no refs).
- `--text` reads one task title per line into the inbox.

The JSON export (`/export.json`) is a backup format and can't be imported.

## Not in scope

The CLI cannot edit or change a task's state. Those are available to an AI
assistant through the [MCP server](mcp.md).
