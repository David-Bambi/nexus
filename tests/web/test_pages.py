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
