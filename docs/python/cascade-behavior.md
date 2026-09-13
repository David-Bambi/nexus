# Cascade behavior: what happens to children on delete

`session.delete(parent)` doesn't have one universal effect on the parent's
children — SQLAlchemy does exactly what each `relationship()` declares,
and `src/models/` deliberately declares two different things.

## `cascade="all, delete-orphan"` deletes children

`Project.versions` and `Version.definition_of_done` both carry this:

```python
# src/models/project.py
versions: Mapped[list["Version"]] = relationship(
    back_populates="project", cascade="all, delete-orphan"
)
```

```python
# src/models/version.py
definition_of_done: Mapped[list["DefinitionOfDoneCriterion"]] = relationship(
    back_populates="version", cascade="all, delete-orphan"
)
```

Deleting a `Project` deletes all its `Version` rows in the same
transaction; deleting a `Version` deletes its `DefinitionOfDoneCriterion`
rows. The child rows have no meaning once detached from the parent, so
SQLAlchemy removes them rather than leaving them behind.

## No cascade + nullable FK = orphan, not delete

`Project.tasks` and `Version.tasks` carry no cascade at all:

```python
# src/models/project.py
# Not cascaded: a task can outlive its project (e.g. unassigned later).
tasks: Mapped[list["Task"]] = relationship(back_populates="project")
```

`Task.project_id`/`Task.version_id` are nullable FK columns. When the
parent is deleted, SQLAlchemy doesn't delete the `Task` rows and doesn't
leave a dangling reference either — it sets the FK to `NULL` on the
surviving rows to keep referential integrity.

## Empirical check

Created a `Project`, a `Version` under it, and a `Task` with both
`project_id` and `version_id` set. Called `projects.delete(session, key)`
(`src/services/projects.py`), which is a plain `session.delete(project)` +
`session.commit()`. Result:

- `Version` count → 0 (cascaded).
- `Task` count → still 1, but `project_id` and `version_id` are both
  `None` (nulled, not deleted).

Both behaviors come from the same `session.delete()` call, in the same
transaction — the difference is entirely in how each relationship was
declared, not in how it's deleted.

## Open gap: orphaned tasks look like fresh captures

Per the spec (§4.2), `project_id IS NULL` means "raw capture" — an
un-triaged inbox item. A task orphaned by a project deletion falls into
that same state, even though it may have real work behind it (e.g. still
sitting in a `doing` state per the task state machine in
`docs/architecture/overview.md`). Nothing currently forces it back to
`inbox` on orphaning. Not a bug to fix now — `services/tasks.py` doesn't
exist yet — but a rule to decide when task deletion/orphaning is
implemented there.

## Rule of thumb

- `cascade="all, delete-orphan"` — for children with no meaning without
  their parent (a version's DoD criteria can't exist without the version).
- No cascade + nullable FK — for children that should survive their
  parent's deletion in a detached state (a task is meaningful on its own,
  just no longer linked to a project/version).
