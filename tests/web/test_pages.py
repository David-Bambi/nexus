def test_home_page_returns_200(client):
    """The empty home page responds successfully."""
    response = client.get("/")
    assert response.status_code == 200


def test_projects_list_returns_200(client):
    """The projects list page responds successfully."""
    response = client.get("/projects")
    assert response.status_code == 200


def test_create_project_then_view_it(client):
    """Creating a project via the form makes it visible on its detail page."""
    response = client.post(
        "/projects",
        data={"key": "nexus", "name": "Nexus", "description": "A project manager"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"nexus" in response.data

    response = client.get("/projects/nexus")
    assert response.status_code == 200
    assert b"Nexus" in response.data


def test_project_detail_missing_returns_404(client):
    """A project detail page for an unknown key returns 404."""
    response = client.get("/projects/does-not-exist")
    assert response.status_code == 404


def test_delete_project_removes_it(client):
    """Deleting a project via its form makes the detail page 404 afterward."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})

    response = client.post("/projects/nexus/delete", follow_redirects=True)
    assert response.status_code == 200

    response = client.get("/projects/nexus")
    assert response.status_code == 404


def test_delete_project_get_not_allowed(client):
    """The delete route only accepts POST, not GET."""
    response = client.get("/projects/nexus/delete")
    assert response.status_code == 405


def test_versions_list_project_missing_returns_404(client):
    """The versions list page for an unknown project returns 404."""
    response = client.get("/projects/does-not-exist/versions")
    assert response.status_code == 404


def test_create_version_then_view_it(client):
    """Creating a version via the form makes it visible on its detail page."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})

    response = client.post(
        "/projects/nexus/versions",
        data={"number": "0.1.0", "title": "First version", "dod": "Ships"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"0.1.0" in response.data

    response = client.get("/projects/nexus/versions/0.1.0")
    assert response.status_code == 200
    assert b"First version" in response.data


def test_create_version_without_dod_shows_error(client):
    """Creating a version without a definition of done shows an error, not a 500."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})

    response = client.post(
        "/projects/nexus/versions",
        data={"number": "0.1.0", "title": "First version", "dod": ""},
    )
    assert response.status_code == 200
    assert b"Definition of done" in response.data


def test_version_detail_missing_returns_404(client):
    """A version detail page for an unknown number returns 404."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    response = client.get("/projects/nexus/versions/0.1.0")
    assert response.status_code == 404


def test_start_and_release_version(client):
    """Starting then releasing a version updates its displayed status."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post(
        "/projects/nexus/versions",
        data={"number": "0.1.0", "title": "First version", "dod": "Ships"},
    )

    response = client.post("/projects/nexus/versions/0.1.0/start")
    assert response.status_code == 200
    assert b"IN_PROGRESS" in response.data

    response = client.post("/projects/nexus/versions/0.1.0/release")
    assert response.status_code == 200
    assert b"RELEASED" in response.data


def test_start_version_twice_shows_error(client):
    """Starting an already started version shows an error, not a 500."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post(
        "/projects/nexus/versions",
        data={"number": "0.1.0", "title": "First version", "dod": "Ships"},
    )
    client.post("/projects/nexus/versions/0.1.0/start")

    response = client.post("/projects/nexus/versions/0.1.0/start")
    assert response.status_code == 200
    assert b"already started" in response.data


def test_tasks_list_returns_200(client):
    """The tasks list page responds successfully."""
    response = client.get("/tasks")
    assert response.status_code == 200


def test_capture_task_then_view_it(client):
    """Capturing a task via the form makes it visible on its detail page."""
    response = client.post("/tasks", data={"title": "Write the docs"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Write the docs" in response.data

    response = client.get("/tasks/1")
    assert response.status_code == 200
    assert b"Write the docs" in response.data


def test_task_detail_missing_returns_404(client):
    """A task detail page for an unknown id returns 404."""
    response = client.get("/tasks/1")
    assert response.status_code == 404


def test_clarify_plan_start_complete_task(client):
    """Clarifying, planning, starting then completing a task updates its state."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post(
        "/projects/nexus/versions",
        data={"number": "0.1.0", "title": "First version", "dod": "Ships"},
    )
    client.post("/tasks", data={"title": "Write the docs"})

    response = client.post(
        "/tasks/1/clarify",
        data={"title": "Write the docs", "project_key": "nexus"},
    )
    assert response.status_code == 200
    assert b"REFINED" in response.data

    response = client.post("/tasks/1/plan", data={"version_id": "1"})
    assert response.status_code == 200
    assert b"PLANNED" in response.data

    response = client.post("/tasks/1/start")
    assert response.status_code == 200
    assert b"DOING" in response.data

    response = client.post("/tasks/1/complete")
    assert response.status_code == 200
    assert b"DONE" in response.data


def test_start_task_not_planned_shows_error(client):
    """Starting a task that isn't planned shows an error, not a 500."""
    client.post("/tasks", data={"title": "Write the docs"})

    response = client.post("/tasks/1/start")
    assert response.status_code == 200
    assert b"isn&#39;t planned" in response.data


def test_delete_task_removes_it(client):
    """Deleting a task via its form makes the detail page 404 afterward."""
    client.post("/tasks", data={"title": "Write the docs"})

    response = client.post("/tasks/1/delete", follow_redirects=True)
    assert response.status_code == 200

    response = client.get("/tasks/1")
    assert response.status_code == 404
