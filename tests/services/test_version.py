import pytest

from src.services import projects, versions
from src.models.version import VersionStatus
from src.models.task import Task, TaskState
from src.services.errors import ConflictError, NotFoundError, ValidationError

# Create ------------------------------------------------------------------------------------------

def test_create_returns_version(session):
    """Create a version returns a version
    Given a project 'nexus'
    When creating a version '0.1.0' with a definition of done
    Then the version is created with that number
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    assert version.id is not None
    assert version.number == "0.1.0"
    assert version.status is VersionStatus.PLANNED

def test_create_project_not_found(session):
    """Create a version under a non existing project raises a NotFoundError
    Given no project with 'nexus' key
    When creating a version under 'nexus'
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])

def test_create_rejects_empty_dod(session):
    """Create a version without a definition of done raises a ValidationError
    Given a project 'nexus'
    When creating a version with an empty definition of done
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    with pytest.raises(ValidationError):
        versions.create(session, "nexus", "0.1.0", "First version", [])

def test_create_rejects_duplicate_number(session):
    """Create a version with a duplicate number raises a ConflictError
    Given a project 'nexus' with version '0.1.0'
    When creating another version '0.1.0' under 'nexus'
    Then a conflict error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    with pytest.raises(ConflictError):
        versions.create(session, "nexus", "0.1.0", "First version again", ["Ships"])


# Get ---------------------------------------------------------------------------------------------

def test_get_version_found(session):
    """Get an existing version returns that version
    Given a project 'nexus' with version '0.1.0'
    When getting version '0.1.0' of 'nexus'
    Then the version is returned
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    version = versions.get(session, "nexus", "0.1.0")
    assert version.number == "0.1.0"

def test_get_version_not_found(session):
    """Get a non existing version raises a NotFoundError
    Given a project 'nexus' without version '0.1.0'
    When getting version '0.1.0' of 'nexus'
    Then a not found error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    with pytest.raises(NotFoundError):
        versions.get(session, "nexus", "0.1.0")

def test_get_version_project_not_found(session):
    """Get a version under a non existing project raises a NotFoundError
    Given no project with 'nexus' key
    When getting version '0.1.0' of 'nexus'
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        versions.get(session, "nexus", "0.1.0")


# List --------------------------------------------------------------------------------------------

def test_list_no_version(session):
    """List a project without versions returns an empty list
    Given a project 'nexus' without versions
    When listing the versions of 'nexus'
    Then the resulting list is empty
    """
    projects.create(session, "nexus", "Nexus", "")
    assert not versions.list(session, "nexus")

def test_list_with_version(session):
    """List a project's versions returns them
    Given a project 'nexus' with version '0.1.0'
    When listing the versions of 'nexus'
    Then the resulting list contains version '0.1.0'
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    version_list = versions.list(session, "nexus")
    assert len(version_list) == 1
    assert version_list[0].number == "0.1.0"


# Start ---------------------------------------------------------------------------------------------

def test_start_planned_version(session):
    """Start a planned version moves it to in progress
    Given a planned version '0.1.0'
    When starting that version
    Then its status is 'IN_PROGRESS'
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    started = versions.start(session, version.id)
    assert started.status is VersionStatus.IN_PROGRESS

def test_start_not_found(session):
    """Start a non existing version raises a NotFoundError
    Given no version with id 1
    When starting version 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        versions.start(session, 1)

def test_start_already_started(session):
    """Start an already started version raises a ValidationError
    Given a version already in progress
    When starting that version again
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    with pytest.raises(ValidationError):
        versions.start(session, version.id)


# Release -------------------------------------------------------------------------------------------

def test_release_in_progress_version(session):
    """Release an in progress version with no unfinished tasks releases it
    Given a version in progress with no tasks
    When releasing that version
    Then its status is 'RELEASED' and released_at is set
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    released = versions.release(session, version.id)
    assert released.status is VersionStatus.RELEASED
    assert released.released_at is not None

def test_release_not_found(session):
    """Release a non existing version raises a NotFoundError
    Given no version with id 1
    When releasing version 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        versions.release(session, 1)

def test_release_not_in_progress(session):
    """Release a planned version raises a ValidationError
    Given a planned version '0.1.0'
    When releasing that version
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    with pytest.raises(ValidationError):
        versions.release(session, version.id)

def test_release_with_unfinished_tasks(session):
    """Release a version with unfinished tasks raises a ValidationError
    Given a version in progress with an unfinished task
    When releasing that version
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    task = Task(title="Write the docs", project_id=version.project_id,
                version_id=version.id, state=TaskState.PLANNED)
    session.add(task)
    session.commit()
    with pytest.raises(ValidationError):
        versions.release(session, version.id)


# Reorder -------------------------------------------------------------------------------------------

def test_reorder_versions(session):
    """Reorder a project's versions updates their position
    Given a project 'nexus' with versions '0.1.0' and '0.2.0'
    When reordering with '0.2.0' before '0.1.0'
    Then '0.2.0' has position 0 and '0.1.0' has position 1
    """
    projects.create(session, "nexus", "Nexus", "")
    v1 = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    v2 = versions.create(session, "nexus", "0.2.0", "Second version", ["Ships"])
    versions.reorder(session, "nexus", [v2.id, v1.id])
    assert v2.position == 0
    assert v1.position == 1

def test_reorder_project_not_found(session):
    """Reorder versions of a non existing project raises a NotFoundError
    Given no project with 'nexus' key
    When reordering versions of 'nexus'
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        versions.reorder(session, "nexus", [])

def test_reorder_mismatched_ids(session):
    """Reorder with ids not matching the project's versions raises a ValidationError
    Given a project 'nexus' with version '0.1.0'
    When reordering with an id that doesn't belong to 'nexus'
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    with pytest.raises(ValidationError):
        versions.reorder(session, "nexus", [999])
