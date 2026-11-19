import json

from src.models.tag import Tag
from src.models.task import TaskKind
from src.services import export, projects, tasks

# Dump ---------------------------------------------------------------------------------------------

def test_dump_empty_database(session):
    """Dump of an empty database has every section, all empty
    Given no data
    When dumping the database
    Then every table is present as an empty list
    """
    result = export.dump_json(session)

    assert result["exported_at"]
    for section in ("projects", "tasks", "tags", "events"):
        assert "versions" not in result
        assert result[section] == []

def test_dump_is_json_serialisable(session):
    """Dump can be written as JSON as is
    Given a project, a subproject, a feature, a task and their events
    When dumping the database
    Then json.dumps accepts the result
    """
    projects.create(session, "nexus", "Nexus", "")
    projects.create(session, "v2", "Nexus 2", parent_key="nexus")
    tasks.create(session, "Tree", "v2", kind=TaskKind.FEATURE)
    tasks.capture(session, "Write the docs")

    assert json.dumps(export.dump_json(session))

def test_dump_serialises_enums_and_dates(session):
    """Dump gives enums by name and dates in ISO 8601
    Given a project and a task
    When dumping the database
    Then the states are names and the creation times are strings
    """
    projects.create(session, "nexus", "Nexus", "")
    tasks.capture(session, "Write the docs")

    result = export.dump_json(session)
    assert result["projects"][0]["status"] == "ACTIVE"
    assert result["tasks"][0]["state"] == "INBOX"
    assert isinstance(result["tasks"][0]["created_at"], str)
    assert result["tasks"][0]["closed_at"] is None

def test_dump_includes_every_table(session):
    """Dump holds the rows of every table
    Given a project, a tagged task and their events
    When dumping the database
    Then each section has its rows
    """
    projects.create(session, "nexus", "Nexus", "")
    task = tasks.capture(session, "Write the docs")
    task.tags.append(Tag(name="docs"))
    session.commit()

    result = export.dump_json(session)
    assert [p["key"] for p in result["projects"]] == ["nexus"]
    assert [t["title"] for t in result["tasks"]] == ["Write the docs"]
    assert [t["name"] for t in result["tags"]] == ["docs"]
    assert [(e["entity_type"], e["action"]) for e in result["events"]] == [
        ("project", "created"), ("task", "created")]

def test_dump_gives_the_tree_and_tags(session):
    """Dump gives each item's kind and parent, each subproject's parent, and tag names
    Given a subproject with a feature holding a tagged task
    When dumping the database
    Then the rows carry ref, parent_id, kind and tag names
    """
    root = projects.create(session, "nexus", "Nexus", "")
    sub = projects.create(session, "v2", "Nexus 2", parent_key="nexus")
    feature = tasks.create(session, "Tree", "v2", kind=TaskKind.FEATURE)
    task = tasks.create(session, "Model", parent_ref=feature.ref)
    task.tags.extend([Tag(name="writing"), Tag(name="docs")])
    session.commit()

    result = export.dump_json(session)
    by_key = {p["key"]: p for p in result["projects"]}
    assert by_key["v2"]["parent_id"] == root.id and by_key["v2"]["ref"] == sub.ref
    by_ref = {t["ref"]: t for t in result["tasks"]}
    assert by_ref[feature.ref]["kind"] == "FEATURE"
    assert by_ref[task.ref]["kind"] == "TASK"
    assert by_ref[task.ref]["parent_id"] == feature.id
    assert by_ref[task.ref]["tags"] == ["docs", "writing"]

def test_dump_includes_archived_projects_and_done_tasks(session):
    """Dump leaves nothing out
    Given an archived project and a completed task
    When dumping the database
    Then both are in the export
    """
    projects.create(session, "nexus", "Nexus", "")
    projects.archive(session, "nexus")
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    tasks.start(session, task.id)
    tasks.complete(session, task.id)

    result = export.dump_json(session)
    assert result["projects"][0]["status"] == "ARCHIVED"
    assert result["tasks"][0]["state"] == "DONE"
    assert result["tasks"][0]["closed_at"]


# Queries ------------------------------------------------------------------------------------------

def _count_queries(session, action):
    """Run action() and return how many SQL statements it issued."""
    from sqlalchemy import event
    statements = []
    engine = session.get_bind()
    listener = lambda *args: statements.append(1)
    event.listen(engine, "before_cursor_execute", listener)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(statements)

def _tagged_task(session, title, tag):
    """Capture a task carrying a tag."""
    task = tasks.capture(session, title)
    task.tags.append(tag)
    session.commit()

def test_dump_query_count_does_not_grow_with_the_data(session):
    """Dump issues the same number of queries however many tasks exist
    Given a database with one tagged task
    When dumping it, then adding many more tagged tasks and dumping again
    Then the number of SQL statements is unchanged
    """
    projects.create(session, "nexus", "Nexus", "")
    tag = Tag(name="docs")
    _tagged_task(session, "Write the docs", tag)
    small = _count_queries(session, lambda: export.dump_json(session))

    for i in range(20):
        _tagged_task(session, f"Task {i}", tag)
    large = _count_queries(session, lambda: export.dump_json(session))

    assert large == small
