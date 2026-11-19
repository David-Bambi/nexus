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
  command word (`add`, `help`, `import`, `projects`, `tasks`, `version`),
  are refused when creating a project.

## Commands

| Command | Result |
|---|---|
| `nexus version` | App version |
| `nexus tasks` | Table of all features and tasks, `(none)` if empty |
| `nexus projects` | `KEY REF VERSION STATUS NAME`; each active subproject follows its root, key indented |
| `nexus <project> [--all]` / `<s-ref> [--all]` | Project detail, see below |
| `nexus <f-ref>` / `<t-ref>` | Feature or task detail, see below |
| `nexus add task\|feature <project> [-p f-ref] [-t T] [-b B] [-c C] [-s SIZE]` | Add to the project's tree, refined |
| `nexus "<description>"` | Capture into the inbox |
| `nexus import <file\|->` | Bulk import, see below |

Project detail: fields (with `Version`), "Criteria for N+1.0" (`[x] 1.
text`, if any), a Subprojects table (with `VERSION`), then "Work": the
tree, two spaces of indent per level, one line per item `ref  STATE
title`, plus `(vX.Y)` for a shipped feature; `(none)` if empty. Done and
cancelled items only with `--all`.

Feature or task detail: fields (with `Released`, `vX.Y`, for a shipped
feature); a feature adds "Children", its whole subtree, closed items
included.

`add` puts the item at the end of the project's top level, or under
`--parent` (`-p`), already refined. The parent must belong to the project:
otherwise exit `1` and nothing is created. `--size` is `XS`, `S`, `M` or
`L`. Without `--title`, `add` prompts on a terminal and fails otherwise. A
lone argument that is blank or contains whitespace is a capture.

```bash
nexus add feature NX -t "CLI page"
nexus add task NX -p f-9ab -t "Write the CLI page" -s S
# Created task t-4k2 (refined, NX > f-9ab): Write the CLI page
nexus "buy a USB-C cable"
# Created task t-7xq (inbox): buy a USB-C cable
nexus NX --all
nexus f-9ab
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

The CLI cannot edit, clarify, move or reorder an item, change its kind or
state, edit criteria or release a major version. Use the web UI, or an AI
assistant through the [MCP server](mcp.md).
