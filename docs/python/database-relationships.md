# Database relationships: FK column vs. junction table

Two ways to link two tables show up in `src/models/`: a plain foreign-key
column, and a separate junction table. Which one to use isn't a style
choice — it follows directly from the cardinality of the relationship.

## Foreign-key column = one-to-many

A column in the "many" table holding the primary key of the "one" table.
Every row on the many side points at exactly one row on the one side; the
one side can be pointed at by any number of rows.

```python
# src/models/version.py
project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
```

```python
# src/models/task.py — nullable FKs, but still one-to-many
project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("project.id"))
version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("version.id"))
```

One project has many versions; one project/version has many tasks (`Task`'s
FKs are nullable because a task with neither is a raw GTD capture, not an
edge case — see `docs/architecture/overview.md`). In both cases, no
junction table is needed: the "many" row simply carries a column pointing
at its one parent.

The newest example, `DefinitionOfDoneCriterion` (`src/models/definition_of_done.py`):

```python
version_id: Mapped[int] = mapped_column(ForeignKey("version.id"), nullable=False)
```

One version has many DoD criteria; each criterion belongs to exactly one
version. Same shape as `Version.project_id`, so the same plain FK column
applies.

## Junction table = many-to-many

When a row on **each** side can relate to multiple rows on the other
side, neither table can hold a single FK column for it — SQL columns
don't repeat. The pair of foreign keys instead lives in its own table,
one row per (A, B) pairing. `src/models/tag.py`:

```python
task_tag_table = Table(
    "task_tag",
    Base.metadata,
    Column("task_id", ForeignKey("task.id"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id"), primary_key=True),
)
```

One task can carry many tags, and one tag can label many tasks. `task_tag`
holds nothing but the two FKs (its primary key is the pair itself) and
SQLAlchemy's `secondary=task_tag_table` on `Tag.tasks` hides the join
behind a normal `relationship`.

## The rule of thumb

Ask: can a row on side A relate to only one row on side B, or to many?

- At most one → plain FK column, placed on the "many" table.
- Many-to-many in both directions → junction table.

A junction table for a relationship that's actually one-to-many is
overhead with no relational benefit: an extra join, an extra table to
keep in sync, for something a single column already expresses.

## Worked example: `DefinitionOfDoneCriterion`

This table was initially considered as a junction between `Version` and
some shared pool of criteria — plausible if criteria were reusable
templates. But the actual requirement is that each checklist item belongs
to exactly one version's checklist; nothing is shared across versions.
That's one-to-many, not many-to-many, so the junction idea was dropped in
favor of the plain `version_id` FK column shown above — the model's own
docstring records the reasoning.
