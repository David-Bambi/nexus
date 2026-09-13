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
