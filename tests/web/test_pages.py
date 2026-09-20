import pytest


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


def test_inbox_empty_returns_200(client):
    """The inbox page responds successfully when there's nothing to triage."""
    response = client.get("/inbox")
    assert response.status_code == 200
    assert b"Inbox is empty" in response.data


def test_inbox_shows_next_item(client):
    """The inbox page shows the oldest captured task."""
    client.post("/tasks", data={"title": "Write the docs"})

    response = client.get("/inbox")
    assert response.status_code == 200
    assert b"Write the docs" in response.data


@pytest.mark.parametrize(
    "action, data",
    [("clarify", {"title": "First"}), ("defer", {}), ("delete", {})],
)
def test_inbox_action_advances_to_next_item(client, action, data):
    """Clarifying, deferring or deleting the current inbox item advances the queue."""
    client.post("/tasks", data={"title": "First"})
    client.post("/tasks", data={"title": "Second"})

    response = client.post(f"/inbox/1/{action}", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Second" in response.data
    assert b"First" not in response.data


def test_refine_filters_by_context(client):
    """The refine queue filtered by context only shows the matching task."""
    client.post("/tasks", data={"title": "At the computer"})
    client.post("/tasks/1/clarify", data={"title": "At the computer", "context": "@ordi"})
    client.post("/tasks", data={"title": "At the store"})
    client.post("/tasks/2/clarify", data={"title": "At the store", "context": "@achat"})

    response = client.get("/refine?context=@ordi")
    assert response.status_code == 200
    assert b"At the computer" in response.data
    assert b"At the store" not in response.data


def test_refine_filters_by_project_key(client):
    """The refine queue filtered by project key only shows that project's task."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects", data={"key": "other", "name": "Other"})
    client.post("/tasks", data={"title": "Nexus task"})
    client.post("/tasks/1/clarify", data={"title": "Nexus task", "project_key": "nexus"})
    client.post("/tasks", data={"title": "Other task"})
    client.post("/tasks/2/clarify", data={"title": "Other task", "project_key": "other"})

    response = client.get("/refine?project_key=nexus")
    assert response.status_code == 200
    assert b"Nexus task" in response.data
    assert b"Other task" not in response.data


def test_search_finds_captured_task_by_title(client):
    """Searching for a substring of a task's title finds it."""
    client.post("/tasks", data={"title": "Write the docs"})

    response = client.get("/search?q=docs")
    assert response.status_code == 200
    assert b"Write the docs" in response.data


def test_capture_from_another_page_redirects_back_to_it(client):
    """Capturing via the global form from a non-tasks page stays on that page."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})

    response = client.post(
        "/capture", data={"title": "Captured elsewhere", "next": "/projects/nexus"}
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/projects/nexus"


def test_capture_rejects_protocol_relative_next(client):
    """A protocol-relative next value is rejected rather than followed off-site."""
    response = client.post(
        "/capture", data={"title": "Captured elsewhere", "next": "//evil.example"}
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/tasks"


def _planned_task_in_started_version(client):
    """Create project 'nexus' with started version 0.1.0 and task 1 planned into it."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post(
        "/projects/nexus/versions",
        data={"number": "0.1.0", "title": "First version", "dod": "Ships"},
    )
    client.post("/projects/nexus/versions/0.1.0/start")
    client.post("/capture", data={"title": "Write the docs"})
    client.post("/tasks/1/clarify", data={"title": "Write the docs"})
    client.post("/tasks/1/plan", data={"version_id": "1"})


def test_dashboard_shows_work_in_progress(client):
    """The dashboard lists the started version, doing and waiting tasks, and the counters."""
    _planned_task_in_started_version(client)
    client.post("/tasks/1/start")
    client.post("/capture", data={"title": "Second task"})
    client.post("/capture", data={"title": "Blocked task"})
    client.post("/tasks/3/clarify", data={"title": "Blocked task"})
    client.post("/tasks/3/plan", data={"version_id": "1"})
    client.post("/tasks/3/start")
    client.post("/tasks/3/block", data={"reason": "Waiting for review"})

    response = client.get("/")
    assert response.status_code == 200
    assert b"First version" in response.data
    assert b"0/2 done" in response.data
    assert b"Write the docs" in response.data
    assert b"Waiting for review" in response.data
    assert b"Inbox: 1" in response.data


def test_dashboard_counters_link_to_queues(client):
    """The inbox and refine counters link to their pages."""
    response = client.get("/")
    assert b'href="/inbox"' in response.data
    assert b'href="/refine"' in response.data


def test_task_detail_shows_history(client):
    """A task's page lists each transition it went through, in order."""
    _planned_task_in_started_version(client)
    client.post("/tasks/1/start")

    response = client.get("/tasks/1")
    assert response.status_code == 200
    body = response.data.decode()
    positions = [body.index(action) for action in ("created", "clarified", "planned", "started")]
    assert positions == sorted(positions)


def test_task_transition_response_shows_new_history_entry(client):
    """The page returned after a transition already includes its event."""
    _planned_task_in_started_version(client)

    response = client.post("/tasks/1/start")
    assert response.status_code == 200
    assert b"started" in response.data


def test_version_detail_shows_changelog(client):
    """A version's page lists its own events and its tasks' events, linking each task."""
    _planned_task_in_started_version(client)
    client.post("/tasks/1/start")
    client.post("/tasks/1/complete")

    response = client.get("/projects/nexus/versions/0.1.0")
    assert response.status_code == 200
    assert b"Changelog" in response.data
    assert b"completed" in response.data
    assert b'href="/tasks/1"' in response.data


def test_export_json_is_an_attachment_with_all_tables(client):
    """The export downloads as a JSON file holding every table."""
    _planned_task_in_started_version(client)

    response = client.get("/export.json")
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert response.headers["Content-Disposition"].startswith("attachment; filename=")

    data = response.get_json()
    assert set(data) == {"exported_at", "projects", "versions", "tasks", "tags", "events"}
    assert [p["key"] for p in data["projects"]] == ["nexus"]
    assert [t["title"] for t in data["tasks"]] == ["Write the docs"]
    assert data["events"]


def test_nav_links_to_dashboard_and_export(client):
    """Every page's navigation links to the dashboard and the export."""
    response = client.get("/projects")
    assert b'href="/"' in response.data
    assert b'href="/export.json"' in response.data


def _capture_many(client, count, refined=False):
    """Create count tasks named 'Docs <n>' straight through the services, oldest first.

    Args:
        client: The Flask test client, whose app holds the database.
        count: Number of tasks to create.
        refined: If true, clarify each task so it lands in the refine queue.
    """
    from src.services import tasks
    session = client.application.extensions["db_session"]()
    for n in range(count):
        task = tasks.capture(session, f"Docs {n}")
        if refined:
            tasks.clarify(session, task.id, task.title, None, None, None, None)


def test_search_cuts_a_long_result_list_and_says_so(client):
    """A search with more than 100 matches shows 100 and a note."""
    _capture_many(client, 101)

    response = client.get("/search?q=docs")
    assert response.data.count(b'href="/tasks/') == 100
    assert b"Showing the first 100 results" in response.data


def test_search_under_the_limit_has_no_note(client):
    """A search with few matches shows all of them and no note."""
    _capture_many(client, 3)

    response = client.get("/search?q=docs")
    assert response.data.count(b'href="/tasks/') == 3
    assert b"Showing the first" not in response.data


def test_tasks_page_shows_the_most_recent_and_says_so(client):
    """The task list with more than 100 tasks shows the newest 100 and a note."""
    _capture_many(client, 101)

    response = client.get("/tasks")
    body = response.data
    assert body.count(b'href="/tasks/') == 100
    assert b"Showing the 100 most recent tasks" in body
    assert b"Docs 100" in body
    assert b"Docs 0<" not in body


def test_refine_cuts_a_long_queue_and_says_so(client):
    """The refine queue with more than 100 tasks shows the oldest 100 and a note."""
    _capture_many(client, 101, refined=True)

    response = client.get("/refine")
    assert response.data.count(b'href="/tasks/') == 100
    assert b"Showing the 100 oldest tasks" in response.data
