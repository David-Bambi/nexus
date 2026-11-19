from src.models.task import TaskKind
from src.mcp_server import serialize
from src.services import projects, tasks, versioning, views


def test_project_gives_its_version(session):
    """A project's dict carries its MAJOR.MINOR version."""
    project = projects.create(session, "nx", "Nexus")
    versioning.set_version(session, "nx", 1, 4)
    assert serialize.project(project)["version"] == "1.4"


def test_criteria_are_numbered_from_one(session):
    """Criteria are identified by their number in the list, not by a raw id."""
    project = projects.create(session, "nx", "Nexus")
    versioning.add_criterion(session, "nx", "Tests green")
    second = versioning.add_criterion(session, "nx", "Docs built")
    versioning.set_criterion_done(session, second.id, True)
    assert serialize.criteria(project.criteria) == [
        {"number": 1, "text": "Tests green", "done": False},
        {"number": 2, "text": "Docs built", "done": True}]


def test_tree_nests_children_and_task_brief_gives_released_in(session):
    """
    Given a feature holding a task, the feature completed
    When serialising the project tree
    Then the feature carries its released version and its child, nested
    """
    project = projects.create(session, "nx", "Nexus")
    feature = tasks.add_to_tree(session, "Auth", project_key="nx", kind=TaskKind.FEATURE)
    child = tasks.add_to_tree(session, "Login", parent_ref=feature.ref)
    tasks.cancel(session, child.id)
    tasks.start(session, feature.id)
    tasks.complete(session, feature.id)

    (node,) = serialize.tree(views.project_tree(project, include_closed=True))
    assert (node["ref"], node["released_in"]) == (feature.ref, "0.1")
    assert [(c["ref"], c["children"], c["released_in"]) for c in node["children"]] == [(child.ref, [], None)]
