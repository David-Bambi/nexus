import pytest

from src.services import projects
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