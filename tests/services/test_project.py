import pytest

from src.services import events, projects
from src.models.project import ProjectStatus
from src.services.errors import ConflictError, NotFoundError

# Create ------------------------------------------------------------------------------------------

def test_create_returns_project(session):
    """Create a project returns a project
    Given a session database
    When create a project nexus with 'nexus' key
    Then project is create in database and his key is 'nexus'
    """
    project = projects.create(session, "nexus", "Nexus", "A project manager")
    assert project.id is not None
    assert project.key == "nexus"

def test_create_rejects_duplicate_key(session):
    """Create a project with duplicate key raises a ConflictError
    Given a project with key nexus
    When creating a project with key nexus
    Then a conflict error is raises
    """
    projects.create(session, "nexus", "Nexus", "")
    with pytest.raises(ConflictError):
        projects.create(session, "nexus", "Nexus 2", "")


# Get ---------------------------------------------------------------------------------------------

def test_get_project_not_found(session):
    """Get a non existing project raises a NotFoundError
    Given a database without a project with 'nexus' key
    When getting the project
    Then the project is not found.
    """
    with pytest.raises(NotFoundError):
        projects.get(session, "nexus")

def test_get_project_found(session):
    """Get a existing project returns that project
    Given a project
    When getting that project
    Then the project is returned.
    """
    projects.create(session, "nexus", "Nexus", "")
    project = projects.get(session, "nexus")
    assert project.id is not None
    assert project.key == "nexus"


# List --------------------------------------------------------------------------------------------

def test_list_no_project(session):
    """ List empty project database
    Given no project in database
    When listing the project
    Then resulting list is empty
    """
    project_list = projects.list(session)
    assert not project_list

def test_list_with_project(session):
    """ List project in database
    Given project 'nexus' in database
    When listing the project
    Then resulting list contain project with key 'nexus'
    """
    projects.create(session, "nexus", "Nexus", "A project manager")
    project_list = projects.list(session)
    assert project_list
    assert project_list[0].key == "nexus"

def test_list_including_archived_project(session):
    """ List project including archived project
    Given archived project 'nexus' in database
    When listing the project including archived
    Then resulting list contains archived project with key 'nexus'
    """
    projects.create(session, "nexus", "Nexus", "A project manager")
    projects.archive(session, "nexus")
    project_list_including_archived = projects.list(session, include_archived=True)
    assert project_list_including_archived
    assert project_list_including_archived[0].key == "nexus"

def test_list_excluding_archived_one(session):
    """ List project excluding archived project
    Given archived project 'nexus' in database
    When listing the project excluding archived
    Then resulting list is empty
    """
    projects.create(session, "nexus", "Nexus", "A project manager")
    projects.archive(session, "nexus")
    project_list_excluding_archived = projects.list(session, include_archived=False)
    assert not project_list_excluding_archived
    

# Archive -----------------------------------------------------------------------------------------

def test_archive_project(session):
    """Archive project update the status of object
    Given a project 'nexus'
    When archiving the project
    Then the project status is now 'ARCHIVED'
    """
    projects.create(session, "nexus", "Nexus", "A project manager")
    project = projects.archive(session, "nexus")
    assert project.status is ProjectStatus.ARCHIVED


# Delete --------------------------------------------------------------------------------------------

def test_delete_project(session):
    """Delete a project removes it from the database
    Given a project 'nexus'
    When deleting the project
    Then getting it afterward raises a NotFoundError
    """
    projects.create(session, "nexus", "Nexus", "A project manager")
    projects.delete(session, "nexus")
    with pytest.raises(NotFoundError):
        projects.get(session, "nexus")

def test_delete_project_not_found(session):
    """Delete a non existing project raises a NotFoundError
    Given a database without a project with 'nexus' key
    When deleting the project
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        projects.delete(session, "nexus")


# Events ------------------------------------------------------------------------------------------

def _history(session, project_id):
    """Return a project's logged (action, payload) pairs, oldest first."""
    return [(e.action, e.payload) for e in events.history(session, "project", project_id)]

def test_create_logs_created(session):
    """Create logs a created event
    Given a session database
    When creating a project with the 'nexus' key
    Then its history holds a created event carrying key and name
    """
    project = projects.create(session, "nexus", "Nexus", "")
    assert _history(session, project.id) == [("created", {"key": "nexus", "name": "Nexus"})]

def test_create_conflict_logs_nothing(session):
    """A refused create logs no event
    Given a project with the 'nexus' key
    When creating another with the same key
    Then a conflict error is raised and only one event exists
    """
    projects.create(session, "nexus", "Nexus", "")
    with pytest.raises(ConflictError):
        projects.create(session, "nexus", "Duplicate", "")

    assert session.query(events.Event).count() == 1

def test_archive_logs_archived(session):
    """Archive logs an archived event
    Given an active project
    When archiving it
    Then its history ends with an archived event from active to archived
    """
    project = projects.create(session, "nexus", "Nexus", "")
    projects.archive(session, "nexus")

    assert _history(session, project.id)[-1] == ("archived", {"from": "ACTIVE", "to": "ARCHIVED"})

def test_delete_logs_deleted_and_keeps_history(session):
    """Delete logs a deleted event and leaves the project's history readable
    Given a project
    When deleting it
    Then its history holds the created and deleted events
    """
    project = projects.create(session, "nexus", "Nexus", "")
    project_id = project.id
    projects.delete(session, "nexus")

    assert [action for action, _ in _history(session, project_id)] == ["created", "deleted"]
