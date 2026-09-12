# Architecture overview

## Domain model

`Project → Version → Task`, one-to-many at each level. `Task.project_id`
and `Task.version_id` are independently nullable — this is the mechanism
behind the GTD workflow, not an edge case:

- `project_id IS NULL` → raw capture, not yet attached to a project
- `version_id IS NULL` → not yet planned (needs refining)
- both set → planned into a milestone

```mermaid
erDiagram
    PROJECT ||--o{ VERSION : has
    PROJECT ||--o{ TASK : "has (optional)"
    VERSION ||--o{ TASK : "has (optional)"
    TASK }o--o{ TAG : has
```

`Tag` is a free-form label, many-to-many with `Task` via a plain
association table. The `Event` table (append-only mutation log) isn't
shown here: it has no foreign keys by design, referencing any entity by
`entity_type` + `entity_id` so a log entry survives deletion — see
[0002](adr/0002-append-only-event-log.md).

## Task lifecycle

```mermaid
stateDiagram-v2
    [*] --> inbox
    inbox --> refined
    refined --> planned
    planned --> doing
    doing --> waiting
    waiting --> doing
    doing --> done
    inbox --> someday
    refined --> someday
    planned --> someday
    someday --> refined
```

`waiting` requires a non-empty `blocked_reason`. Transition rules are
enforced in the services layer — see [0001](adr/0001-services-ignore-http.md).

## Decisions

See [Decisions](adr/0001-services-ignore-http.md) for the full ADR journal.
