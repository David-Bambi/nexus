# Functional

Visual mockups of the application's screens, kept alongside the rest of
the documentation so UI intent stays traceable next to the spec it
implements.

No mockups yet — this section is scaffolding for the increment that
introduces the first screens (see spec §9/§12 in
`artifacts/specs/milestone-app-v1.md`).

## Conventions

- One page per screen or flow, named `kebab-case.md` (e.g. `inbox.md`,
  `task-detail.md`).
- Each page embeds the mockup image and a short caption of what it shows
  and which task states/transitions it covers.
- Mockup image files live under `docs/functional/assets/`.

## Web screens

Routes and templates: [Architecture overview](../architecture/overview.md#web-pages).

- **Projects** (`/projects`): root projects with their subprojects indented
  below (with their `s-…` ref), each showing its computed version `vX.Y`.
  Archived projects are hidden.
- **Project** (`/projects/<key>`): key, status and version in the header;
  a refused action's error at the top. Sections:
    - *Work*: the tree of features (collapsible) and tasks in sibling
      order, with ref, state and, for a shipped feature, its released
      version. Done and cancelled items are hidden unless "Show closed".
      "Add" (title, task or feature) at the top level and under each
      feature; the item is created refined. ↑ / ↓ on each item move it
      one place among its open siblings (closed siblings are skipped).
    - *Next major version*: the major criteria (check / uncheck, edit,
      delete, add) and "Release N+1.0", enabled once every criterion is
      checked.
    - *Edit*: name and description (the key can't change).
    - *New subproject* (root projects only).
    - *Status*: Archive / Restore.
    - *Danger zone*: delete, once the key is typed.
- **Item** (`/tasks/<id>`): for a feature, its *Children* (whole subtree,
  closed items included, with ↑ / ↓) and an Add form, and "Released in" in the side
  panel. For every item, *Place*: "Move to" (project key and/or parent
  feature ref) and "Change to feature / task" (a feature with children
  can't become a task).
- **Inbox** and the clarify form: *Kind* (task / feature) and *Parent
  feature ref*; with no project key, the parent's project is used.

A refused move (already first / last) shows the item page with the reason.

## Pages

- [Command line](cli.md): the `nexus` CLI, refs and the import format.
- [MCP server](mcp.md): the tools an AI assistant can call, and how to register them.
