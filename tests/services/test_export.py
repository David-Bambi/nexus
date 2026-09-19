import json

from src.models.tag import Tag
from src.services import export, projects, tasks, versions

# Dump ---------------------------------------------------------------------------------------------

def test_dump_empty_database(session):
    """Dump of an empty database has every section, all empty
    Given no data
    When dumping the database
    Then every table is present as an empty list
    """
    result = export.dump_json(session)

    assert result["exported_at"]
    for section in ("projects", "versions", "tasks", "tags", "events"):
        assert result[section] == []

def test_dump_is_json_serialisable(session):
    """Dump can be written as JSON as is
    Given a project, a version, a task and its events
    When dumping the database
    Then json.dumps accepts the result
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
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
    Given a project, a version, a tagged task and their events
    When dumping the database
    Then each section has its rows
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    task.tags.append(Tag(name="docs"))
    session.commit()

    result = export.dump_json(session)
    assert [p["key"] for p in result["projects"]] == ["nexus"]
    assert [v["number"] for v in result["versions"]] == ["0.1.0"]
    assert [t["title"] for t in result["tasks"]] == ["Write the docs"]
    assert [t["name"] for t in result["tags"]] == ["docs"]
    assert [(e["entity_type"], e["action"]) for e in result["events"]] == [
        ("project", "created"), ("version", "created"), ("task", "created")]

def test_dump_nests_definition_of_done_and_tags(session):
    """Dump attaches criteria to their version and tag names to their task
    Given a version with two criteria and a task with two tags
    When dumping the database
    Then the version lists its criteria in order and the task lists its tag names
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships", "Documented"])
    task = tasks.capture(session, "Write the docs")
    task.tags.extend([Tag(name="writing"), Tag(name="docs")])
    session.commit()

    result = export.dump_json(session)
    assert result["versions"][0]["definition_of_done"] == ["Ships", "Documented"]
    assert result["tasks"][0]["tags"] == ["docs", "writing"]

def test_dump_includes_archived_projects_and_done_tasks(session):
    """Dump leaves nothing out
    Given an archived project and a completed task
    When dumping the database
    Then both are in the export
    """
    projects.create(session, "nexus", "Nexus", "")
    projects.archive(session, "nexus")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    tasks.plan(session, task.id, version.id)
    tasks.start(session, task.id)
    tasks.complete(session, task.id)

    result = export.dump_json(session)
    assert result["projects"][0]["status"] == "ARCHIVED"
    assert result["tasks"][0]["state"] == "DONE"
    assert result["tasks"][0]["closed_at"]
