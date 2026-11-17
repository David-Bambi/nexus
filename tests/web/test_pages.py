import re

import pytest


def test_home_page_returns_200(client):
    """The empty home page responds successfully."""
    response = client.get("/")
    assert response.status_code == 200


def test_pages_load_the_stylesheet_which_is_served(client):
    """
    Given the app
    When opening a page, then fetching its stylesheet
    Then the page links /static/app.css with a viewport meta, and the file is served as CSS with the tokens
    """
    html = client.get("/").get_data(as_text=True)
    assert '<link rel="stylesheet" href="/static/app.css">' in html
    assert '<meta name="viewport"' in html
    response = client.get("/static/app.css")
    assert response.status_code == 200 and response.mimetype == "text/css"
    assert b"--color-accent" in response.data and b"prefers-color-scheme: dark" in response.data
    response.close()


def test_pages_load_the_shared_script_instead_of_inlining_it(client):
    """
    Given the app
    When opening a page, then fetching its script
    Then the page loads /static/app.js deferred with no inline shortcut code, and the file holds the capture shortcut
    """
    html = client.get("/").get_data(as_text=True)
    assert '<script src="/static/app.js" defer></script>' in html and "keydown" not in html
    response = client.get("/static/app.js")
    assert response.status_code == 200 and b'getElementById("capture")' in response.data
    response.close()


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


def test_project_detail_lists_versions_with_status_and_progress(client):
    """
    Given a project with a released version and a planned one holding a task and a checked criterion
    When opening the project page
    Then both versions are listed in order, with their status, task and DOD progress, and link to their page
    """
    from src.services import projects, tasks, versions
    session = client.application.extensions["db_session"]()
    projects.create(session, "nx", "Nexus", "")
    old = versions.create(session, "nx", "1", "Old", ["Ships"])
    versions.start(session, old.id)
    versions.set_criterion_done(session, old.definition_of_done[0].id, True)
    versions.release(session, old.id)
    new = versions.create(session, "nx", "2", "New", ["Ships", "Docs"])
    tasks.create_in_version(session, new.id, "Work")
    versions.set_criterion_done(session, new.definition_of_done[0].id, True)

    html = client.get("/projects/nx").get_data(as_text=True)
    assert html.index("1 — Old") < html.index("2 — New")
    assert "RELEASED" in html and "PLANNED" in html
    assert "0/1 done" in html and "DOD 1/2" in html and "DOD 1/1" in html
    assert 'href="/projects/nx/versions/2"' in html


def test_project_detail_without_versions_says_so(client):
    """
    Given a project with no version
    When opening its page
    Then it says there is none and still links to the versions page
    """
    client.post("/projects", data={"key": "nx", "name": "Nexus"})
    html = client.get("/projects/nx").get_data(as_text=True)
    assert "No versions yet." in html and 'href="/projects/nx/versions"' in html


def test_projects_list_shows_unreleased_versions_with_progress(client):
    """
    Given a project with a released, an in-progress and a planned version, and a project with none
    When opening the projects list
    Then only the unreleased versions are shown under their project, with status and progress
    """
    from src.services import projects, tasks, versions
    session = client.application.extensions["db_session"]()
    projects.create(session, "nx", "Nexus", "")
    projects.create(session, "em", "Empty", "")
    old = versions.create(session, "nx", "1", "Old", ["Ships"])
    versions.start(session, old.id)
    versions.set_criterion_done(session, old.definition_of_done[0].id, True)
    versions.release(session, old.id)
    current = versions.create(session, "nx", "2", "Current", ["Ships", "Docs"])
    versions.start(session, current.id)
    tasks.create_in_version(session, current.id, "Work")
    versions.create(session, "nx", "3", "Next", ["Ships"])

    html = client.get("/projects").get_data(as_text=True)
    assert "1 — Old" not in html
    assert html.index("2 — Current") < html.index("3 — Next") < html.index("Empty")
    assert "IN_PROGRESS" in html and "0/1 done" in html and "DOD 0/2" in html
    assert 'href="/projects/nx/versions/3"' in html


def test_version_page_has_a_delete_form_locked_until_the_number_is_typed(client):
    """
    Given a version
    When opening its page
    Then it has a disabled delete button, posting to the delete route, unlocked by typing the number
    """
    from src.services import projects, versions
    session = client.application.extensions["db_session"]()
    projects.create(session, "nx", "Nexus", "")
    versions.create(session, "nx", "1.0", "First", ["Ships"])

    html = client.get("/projects/nx/versions/1.0").get_data(as_text=True)
    assert 'action="/projects/nx/versions/1.0/delete"' in html
    assert '<input type="text" aria-label="Version number" data-confirm="1.0">' in html
    assert '<button class="button-danger" type="submit" disabled>Delete version</button>' in html


def test_delete_version_keeps_its_tasks_and_returns_to_the_project(client):
    """
    Given a version with a planned task
    When posting to its delete route
    Then it redirects to the project page, the version is gone and the task is back to refined
    """
    from src.models.task import Task, TaskState
    from src.services import projects, tasks, versions
    session = client.application.extensions["db_session"]()
    projects.create(session, "nx", "Nexus", "")
    version = versions.create(session, "nx", "1.0", "First", ["Ships"])
    task_id = tasks.create_in_version(session, version.id, "Work").id

    response = client.post("/projects/nx/versions/1.0/delete")
    assert response.status_code == 302 and response.headers["Location"].endswith("/projects/nx")
    assert client.get("/projects/nx/versions/1.0").status_code == 404
    assert "No versions yet." in client.get("/projects/nx").get_data(as_text=True)
    task = client.application.extensions["db_session"]().get(Task, task_id)
    assert (task.state, task.version_id) == (TaskState.REFINED, None)


def test_delete_missing_version_returns_404_and_get_is_not_allowed(client):
    """
    Given a project without that version
    When posting to the delete route of an unknown version, or getting it
    Then it is 404, and 405 for GET
    """
    client.post("/projects", data={"key": "nx", "name": "Nexus"})
    assert client.post("/projects/nx/versions/9/delete").status_code == 404
    assert client.get("/projects/nx/versions/9/delete").status_code == 405


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

    client.post("/projects/nexus/versions/0.1.0/dod/1/toggle")
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
    html = response.get_data(as_text=True)
    assert re.search(r'href="/inbox">\s*<span class="stat-value">1</span>\s*<span class="stat-label">Inbox</span>', html)
    assert '<article class="card">' in html and 'href="/projects/nexus/versions/0.1.0">0.1.0</a>' in html


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


@pytest.mark.parametrize("path,current", [
    ("/", "Dashboard"), ("/projects", "Projects"), ("/projects/nx/versions", "Projects"),
    ("/tasks", "Tasks"), ("/inbox", "Inbox"), ("/refine", "Refine"), ("/search", "Search"),
])
def test_nav_marks_the_current_section(client, path, current):
    """
    Given a project
    When opening a page of each section, a nested project page included
    Then exactly one nav item, the section's, is marked as the current page, and the content is in <main>
    """
    client.post("/projects", data={"key": "nx", "name": "Nexus"})
    html = client.get(path).get_data(as_text=True)
    marked = re.findall(r'<a href="[^"]*" aria-current="page">([^<]+)</a>', html)
    assert marked == [current]
    assert '<main class="container" id="content"' in html


def test_pages_start_with_a_skip_link_to_the_content(client):
    """
    Given any page
    When reading it
    Then its first link skips to the main content, which can receive focus
    """
    html = client.get("/").get_data(as_text=True)
    body = html.split("<body>")[1]
    assert body.lstrip().startswith('<a class="skip-link" href="#content">Skip to content</a>')
    assert '<main class="container" id="content" tabindex="-1">' in html


def test_capture_shortcut_ignores_modifier_keys(client):
    """
    Given the shared script
    When reading the capture shortcut
    Then it skips key presses made with Ctrl, Cmd or Alt, so Ctrl+C still copies
    """
    script = client.get("/static/app.js").get_data(as_text=True)
    assert "event.ctrlKey || event.metaKey || event.altKey" in script and "!modified" in script


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


def _create_version(client, dod="Ships\nDocs"):
    """Create project 'nexus' with version '0.1.0' holding the given criteria."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post(
        "/projects/nexus/versions",
        data={"number": "0.1.0", "title": "First version", "dod": dod},
    )


def test_dod_add_criterion(client):
    """Adding a criterion shows it on the version page."""
    _create_version(client)
    response = client.post("/projects/nexus/versions/0.1.0/dod", data={"description": "Tests"})
    assert response.status_code == 200
    assert b'value="Tests"' in response.data


def test_dod_add_empty_criterion_shows_error(client):
    """Adding a blank criterion shows an error, not a 500."""
    _create_version(client)
    response = client.post("/projects/nexus/versions/0.1.0/dod", data={"description": " "})
    assert response.status_code == 200
    assert b"cannot be empty" in response.data


def test_dod_toggle_criterion(client):
    """Toggling a criterion checks it, then unchecks it."""
    _create_version(client)
    response = client.post("/projects/nexus/versions/0.1.0/dod/1/toggle")
    assert b"1/2 checked" in response.data
    response = client.post("/projects/nexus/versions/0.1.0/dod/1/toggle")
    assert b"0/2 checked" in response.data


def test_dod_edit_criterion(client):
    """Editing a criterion changes its description on the page."""
    _create_version(client)
    response = client.post("/projects/nexus/versions/0.1.0/dod/1/edit", data={"description": "Ships to prod"})
    assert b'value="Ships to prod"' in response.data


def test_dod_delete_criterion(client):
    """Deleting a criterion removes it from the page."""
    _create_version(client)
    response = client.post("/projects/nexus/versions/0.1.0/dod/1/delete")
    assert response.status_code == 200
    assert b'value="Ships"' not in response.data
    assert b'value="Docs"' in response.data


def test_dod_delete_last_criterion_shows_error(client):
    """Deleting the last criterion shows an error and keeps it."""
    _create_version(client, dod="Ships")
    response = client.post("/projects/nexus/versions/0.1.0/dod/1/delete")
    assert b"at least one entry" in response.data
    assert b"Ships" in response.data


def test_dod_unknown_criterion_returns_404(client):
    """A criterion id that is not in the version returns 404."""
    _create_version(client)
    response = client.post("/projects/nexus/versions/0.1.0/dod/99/toggle")
    assert response.status_code == 404


def test_dod_frozen_once_released(client):
    """A released version's DOD refuses changes with an error."""
    _create_version(client, dod="Ships")
    client.post("/projects/nexus/versions/0.1.0/start")
    client.post("/projects/nexus/versions/0.1.0/dod/1/toggle")
    client.post("/projects/nexus/versions/0.1.0/release")
    response = client.post("/projects/nexus/versions/0.1.0/dod/1/toggle")
    assert b"cannot change" in response.data


def test_release_with_unchecked_criterion_shows_error(client):
    """Releasing with an unchecked criterion shows an error, not a 500."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/start")
    response = client.post("/projects/nexus/versions/0.1.0/release")
    assert response.status_code == 200
    assert b"unchecked" in response.data


def test_create_version_with_repeated_dod_fields(client):
    """The creation form's repeated 'dod' fields each become a criterion."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post(
        "/projects/nexus/versions",
        data={"number": "0.1.0", "title": "First version", "dod": ["Ships", " ", "Docs"]},
    )
    response = client.get("/projects/nexus/versions/0.1.0")
    assert b'value="Ships"' in response.data
    assert b'value="Docs"' in response.data
    assert b"0/2 checked" in response.data


def test_released_version_page_has_no_dod_forms(client):
    """A released version shows its DOD read-only, without edit forms."""
    _create_version(client, dod="Ships")
    client.post("/projects/nexus/versions/0.1.0/start")
    client.post("/projects/nexus/versions/0.1.0/dod/1/toggle")
    client.post("/projects/nexus/versions/0.1.0/release")
    response = client.get("/projects/nexus/versions/0.1.0")
    assert "☑ Ships".encode() in response.data
    assert b"/dod/1/toggle" not in response.data


def test_version_task_add_shows_planned_task(client):
    """Adding a task from the version page lists it there, already planned."""
    _create_version(client)
    response = client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    assert response.status_code == 200
    assert b"Write the docs" in response.data
    assert b"PLANNED" in response.data
    assert b'href="/tasks/1"' in response.data


def test_version_task_add_keeps_optional_fields(client):
    """The optional context, size and body fields are stored on the new task."""
    _create_version(client)
    client.post(
        "/projects/nexus/versions/0.1.0/tasks/",
        data={"title": "Write the docs", "context": "@ordi", "size": "S", "body": "Details"},
    )
    response = client.get("/tasks/1")
    assert b"@ordi" in response.data
    assert b"Details" in response.data


def test_version_task_add_blank_title_shows_error(client):
    """A blank title shows an error, not a 500, and creates no task."""
    _create_version(client)
    response = client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": " "})
    assert response.status_code == 200
    assert b"title must be specified" in response.data
    assert client.get("/tasks/1").status_code == 404


def test_version_task_add_missing_version_returns_404(client):
    """Adding a task to an unknown version returns 404."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    response = client.post("/projects/nexus/versions/9.9.9/tasks/", data={"title": "Anything"})
    assert response.status_code == 404


def test_version_task_add_released_version_shows_error(client):
    """A released version refuses new tasks with an error."""
    _create_version(client, dod="Ships")
    client.post("/projects/nexus/versions/0.1.0/start")
    client.post("/projects/nexus/versions/0.1.0/dod/1/toggle")
    client.post("/projects/nexus/versions/0.1.0/release")
    response = client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Too late"})
    assert response.status_code == 200
    assert b"already released" in response.data
    assert client.get("/tasks/1").status_code == 404


def test_task_delete_returns_to_next_page(client):
    """Deleting a task opened from a version page brings back to that page."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    response = client.get("/projects/nexus/versions/0.1.0")
    assert b'href="/tasks/1?next=/projects/nexus/versions/0.1.0"' in response.data
    response = client.get("/tasks/1?next=/projects/nexus/versions/0.1.0")
    assert b'/tasks/1/delete?next=/projects/nexus/versions/0.1.0' in response.data
    response = client.post("/tasks/1/delete?next=/projects/nexus/versions/0.1.0")
    assert response.status_code == 302
    assert response.headers["Location"] == "/projects/nexus/versions/0.1.0"
    assert client.get("/tasks/1").status_code == 404


@pytest.mark.parametrize("target", ["https://evil.example", "//evil.example"])
def test_task_delete_ignores_unsafe_next(client, target):
    """An external "next" is ignored: the delete falls back to the task list."""
    client.post("/tasks", data={"title": "Write the docs"})
    response = client.post("/tasks/1/delete", query_string={"next": target})
    assert response.headers["Location"] == "/tasks"


def test_task_action_keeps_next_page(client):
    """An action on the task page keeps the page to return to."""
    client.post("/tasks", data={"title": "Write the docs"})
    response = client.post("/tasks/1/defer?next=/projects/nexus/versions/0.1.0")
    assert b'/delete?next=/projects/nexus/versions/0.1.0' in response.data


def test_task_state_select_moves_task(client):
    """The state form moves a task through the working states, waiting with a reason."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    response = client.get("/tasks/1")
    assert b'name="state"' in response.data
    response = client.post("/tasks/1/state", data={"state": "DOING"})
    assert _shown_field(response, "state") == "DOING"
    response = client.post("/tasks/1/state", data={"state": "WAITING", "reason": "Review"})
    assert _shown_field(response, "state") == "WAITING"
    assert b"Review" in response.data
    response = client.post("/tasks/1/state", data={"state": "DOING"})
    response = client.post("/tasks/1/state", data={"state": "DONE"})
    assert _shown_field(response, "state") == "DONE"


@pytest.mark.parametrize("data, message", [
    ({"state": "NOPE"}, b"unknown state"),
    ({"state": "DONE"}, b"isn&#39;t doing"),
])
def test_task_state_invalid_shows_error(client, data, message):
    """An unknown or not allowed state shows an error and keeps the task's state."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    response = client.post("/tasks/1/state", data=data)
    assert response.status_code == 200
    assert message in response.data
    assert _shown_field(response, "state") == "PLANNED"


def test_task_state_select_absent_for_inbox_task(client):
    """A captured task has no state select; clarifying comes first."""
    client.post("/tasks", data={"title": "Write the docs"})
    response = client.get("/tasks/1")
    assert b'name="state"' not in response.data


def test_task_state_unknown_task_returns_404(client):
    """Changing the state of an unknown task returns 404."""
    response = client.post("/tasks/9/state", data={"state": "DOING"})
    assert response.status_code == 404


def test_version_task_state_select_moves_task(client):
    """The version page's state form moves a task and re-renders the version page."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    page = client.get("/projects/nexus/versions/0.1.0")
    assert b"/versions/0.1.0/task/1/state" in page.data
    response = client.post("/projects/nexus/versions/0.1.0/task/1/state", data={"state": "DOING"})
    assert response.status_code == 200
    assert b"<h2>Tasks</h2>" in response.data
    assert "Write the docs" in _board_column(response, "DOING")
    response = client.post(
        "/projects/nexus/versions/0.1.0/task/1/state", data={"state": "WAITING", "reason": "Review"})
    assert "Write the docs" in _board_column(response, "WAITING")
    assert "Review" in _board_column(response, "WAITING")


@pytest.mark.parametrize("data, message", [
    ({"state": "NOPE"}, b"unknown state"),
    ({"state": "DONE"}, b"isn&#39;t doing"),
    ({"state": "DOING"}, b"can&#39;t go from DOING to DOING"),
])
def test_version_task_state_invalid_shows_error(client, data, message):
    """An unknown or not allowed state shows an error on the version page."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    if data["state"] == "DOING":
        client.post("/tasks/1/state", data={"state": "DOING"})
    response = client.post("/projects/nexus/versions/0.1.0/task/1/state", data=data)
    assert response.status_code == 200
    assert message in response.data


def test_version_task_state_other_version_returns_404(client):
    """A task can't be moved through another version's URL."""
    _create_version(client)
    client.post("/projects/nexus/versions", data={"number": "0.2.0", "title": "Second", "dod": "Ships"})
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    response = client.post("/projects/nexus/versions/0.2.0/task/1/state", data={"state": "DOING"})
    assert response.status_code == 404
    assert _shown_field(client.get("/tasks/1"), "state") == "PLANNED"


def test_version_task_state_released_version_refused(client):
    """A released version's tasks can't be moved; the select is gone from its page."""
    _create_version(client, dod="Ships")
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    client.post("/projects/nexus/versions/0.1.0/start")
    client.post("/tasks/1/state", data={"state": "DOING"})
    client.post("/tasks/1/state", data={"state": "DONE"})
    client.post("/projects/nexus/versions/0.1.0/dod/1/toggle")
    client.post("/projects/nexus/versions/0.1.0/release")
    page = client.get("/projects/nexus/versions/0.1.0")
    assert b"/task/1/state" not in page.data
    response = client.post("/projects/nexus/versions/0.1.0/task/1/state", data={"state": "DOING"})
    assert b"already released" in response.data
    assert _shown_field(client.get("/tasks/1"), "state") == "DONE"


def test_version_page_shows_task_progress(client):
    """The version page shows how many of its tasks are done, with a progress bar."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "First"})
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Second"})
    page = client.get("/projects/nexus/versions/0.1.0")
    assert b"0/2 done" in page.data
    assert b'<progress value="0" max="2">' in page.data
    client.post("/tasks/1/state", data={"state": "DOING"})
    client.post("/tasks/1/state", data={"state": "DONE"})
    page = client.get("/projects/nexus/versions/0.1.0")
    assert b"1/2 done" in page.data
    assert b'<progress value="1" max="2">' in page.data


def test_task_cancel_and_restore(client):
    """A task can be cancelled from its page, then restored to refined."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    assert b'action="/tasks/1/cancel"' in client.get("/tasks/1").data
    response = client.post("/tasks/1/cancel")
    assert _shown_field(response, "state") == "CANCELLED"
    assert b'action="/tasks/1/cancel"' not in response.data
    assert b'action="/tasks/1/restore"' in response.data
    response = client.post("/tasks/1/restore")
    assert _shown_field(response, "state") == "REFINED"


def test_task_cancel_done_task_shows_error(client):
    """Cancelling a done task shows an error and keeps it done."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    client.post("/tasks/1/state", data={"state": "DOING"})
    client.post("/tasks/1/state", data={"state": "DONE"})
    response = client.post("/tasks/1/cancel")
    assert b"already done or cancelled" in response.data
    assert _shown_field(response, "state") == "DONE"


def test_version_page_cancelled_task_leaves_progress_total(client):
    """A task cancelled from the version page's select isn't counted in the progress bar."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "First"})
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Second"})
    response = client.post("/projects/nexus/versions/0.1.0/task/2/state", data={"state": "CANCELLED"})
    assert "First" in _board_column(response, "PLANNED")
    assert "Second" in _board_column(response, "CANCELLED")
    assert b"0/1 done" in response.data


def _shown_field(response, field):
    """The text of one field of a task page's details panel, tags stripped (e.g. "DOING" for the state)."""
    page = response.get_data(as_text=True)
    cell = page.split(f'<dd data-field="{field}">')[1].split("</dd>")[0]
    return re.sub(r"<[^>]+>", "", cell).strip()


def test_refined_task_page_offers_its_project_open_versions_to_plan_into(client):
    """
    Given a refined task of a project with a planned and a released version
    When opening the task page
    Then the plan form lists only the planned version, and the details panel shows the state and project
    """
    _create_version(client, dod="Ships")
    client.post("/projects/nexus/versions", data={"number": "0.2.0", "title": "Second", "dod": "Ships"})
    client.post("/projects/nexus/versions/0.1.0/start")
    client.post("/projects/nexus/versions/0.1.0/dod/1/toggle")
    client.post("/projects/nexus/versions/0.1.0/release")
    _refined_task(client, 1, "Write the docs")

    response = client.get("/tasks/1")
    plan_form = response.get_data(as_text=True).split('action="/tasks/1/plan"')[1].split("</form>")[0]
    assert "0.2.0 — Second" in plan_form and "0.1.0" not in plan_form
    assert _shown_field(response, "state") == "REFINED"


def _board_column(response, state):
    """The markup of one state's column on a version page's task board."""
    page = response.get_data(as_text=True)
    return page.split(f'<section class="board-column" data-state="{state}">')[1].split("</section>")[0]


def test_version_board_shows_cancelled_column_only_when_needed(client):
    """
    Given a version with a planned task
    When opening its page, then after cancelling the task
    Then the board has Planned, Doing, Waiting and Done columns, and a Cancelled one only once a task is cancelled
    """
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "First"})
    page = client.get("/projects/nexus/versions/0.1.0").get_data(as_text=True)
    assert re.findall(r'data-state="(\w+)"', page) == ["PLANNED", "DOING", "WAITING", "DONE"]
    client.post("/tasks/1/state", data={"state": "CANCELLED"})
    page = client.get("/projects/nexus/versions/0.1.0").get_data(as_text=True)
    assert re.findall(r'data-state="(\w+)"', page)[-1] == "CANCELLED"


def test_pages_have_no_inline_script_or_handler():
    """
    Given every page template
    When reading its source
    Then none holds a <script> block or an inline event handler: behaviour lives in static/app.js
    """
    from pathlib import Path
    templates = Path(__file__).parents[2] / "src" / "web" / "templates"
    offenders = [t.name for t in templates.glob("*.html")
                 if re.search(r"<script>|\son(input|change|click|submit)=", t.read_text())]
    assert offenders == []


def _refined_task(client, task_id, title, project_key="nexus"):
    """Capture a task (the task_id-th of the test) and clarify it into a project."""
    client.post("/tasks", data={"title": title})
    client.post(f"/tasks/{task_id}/clarify", data={"title": title, "project_key": project_key})


def test_version_page_lists_project_candidates(client):
    """The version page lists the project's refined, unplanned tasks, and only those."""
    _create_version(client)
    client.post("/projects", data={"key": "other", "name": "Other"})
    _refined_task(client, 1, "Candidate")
    _refined_task(client, 2, "Elsewhere", "other")
    client.post("/tasks", data={"title": "Still in the inbox"})
    page = client.get("/projects/nexus/versions/0.1.0").get_data(as_text=True)
    candidates = page.split("<h2>Candidate tasks</h2>")[1].split("<h2>Definition of done</h2>")[0]
    assert "Candidate" in candidates
    assert "Elsewhere" not in candidates
    assert "Still in the inbox" not in candidates


def test_version_candidate_plus_button_adds_it_to_the_version(client):
    """The + button plans a candidate into the version and removes it from the candidates."""
    _create_version(client)
    _refined_task(client, 1, "Candidate")
    response = client.post("/projects/nexus/versions/0.1.0/task/1/plan")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Candidate" in _board_column(response, "PLANNED")
    assert "No candidate tasks." in page


def test_version_candidate_plan_errors(client):
    """Planning an unknown task is a 404; a task that isn't refined shows an error."""
    _create_version(client)
    assert client.post("/projects/nexus/versions/0.1.0/task/9/plan").status_code == 404
    client.post("/tasks", data={"title": "Still in the inbox"})
    response = client.post("/projects/nexus/versions/0.1.0/task/1/plan")
    assert response.status_code == 200
    assert b"isn&#39;t refined" in response.data


def test_version_candidates_hidden_once_released(client):
    """A released version doesn't offer candidates."""
    _create_version(client, dod="Ships")
    client.post("/projects/nexus/versions/0.1.0/start")
    client.post("/projects/nexus/versions/0.1.0/dod/1/toggle")
    client.post("/projects/nexus/versions/0.1.0/release")
    assert b"Candidate tasks" not in client.get("/projects/nexus/versions/0.1.0").data


def test_task_page_moves_task_to_another_version(client):
    """The task page offers the project's other open versions and moves the task."""
    _create_version(client)
    client.post("/projects/nexus/versions", data={"number": "0.2.0", "title": "Second", "dod": "Ships"})
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    page = client.get("/tasks/1").get_data(as_text=True)
    assert 'action="/tasks/1/move"' in page
    assert "0.2.0 — Second" in page
    assert "0.1.0 — " not in page.split('action="/tasks/1/move"')[1].split("</form>")[0]
    response = client.post("/tasks/1/move", data={"version_id": "2"})
    assert _shown_field(response, "version") == "0.2.0"
    assert b"Write the docs" in client.get("/projects/nexus/versions/0.2.0").data
    assert b"Write the docs" not in client.get("/projects/nexus/versions/0.1.0").data


def test_task_move_same_version_shows_error(client):
    """Moving a task to its own version shows an error."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    response = client.post("/tasks/1/move", data={"version_id": "1"})
    assert response.status_code == 200
    assert b"already in version" in response.data


def test_task_page_hides_move_without_other_version(client):
    """With no other open version, the task page has no move form."""
    _create_version(client)
    client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    assert b'action="/tasks/1/move"' not in client.get("/tasks/1").data


def test_version_page_task_links_keep_the_version_url_after_a_post(client):
    """After a POST on the version page, task links still return to the version page itself."""
    _create_version(client)
    response = client.post("/projects/nexus/versions/0.1.0/tasks/", data={"title": "Write the docs"})
    assert b'href="/tasks/1?next=/projects/nexus/versions/0.1.0"' in response.data
    response = client.post("/projects/nexus/versions/0.1.0/task/1/state", data={"state": "DOING"})
    assert b'href="/tasks/1?next=/projects/nexus/versions/0.1.0"' in response.data


def test_task_page_back_link_returns_to_the_parent_page(client):
    """The task page's back link goes to the page it was opened from, else to the task list."""
    client.post("/tasks", data={"title": "Write the docs"})
    page = client.get("/tasks/1?next=/projects/nexus/versions/0.1.0").get_data(as_text=True)
    assert '<a href="/projects/nexus/versions/0.1.0">← Back</a>' in page
    page = client.get("/tasks/1").get_data(as_text=True)
    assert '<a href="/tasks">← Tasks</a>' in page


@pytest.mark.parametrize("target", ["javascript:alert(1)", "https://evil.example", "//evil.example"])
def test_task_page_back_link_ignores_unsafe_next(client, target):
    """An unsafe "next" is neither linked as the back link nor carried in the forms."""
    client.post("/tasks", data={"title": "Write the docs"})
    page = client.get("/tasks/1", query_string={"next": target}).get_data(as_text=True)
    assert '<a href="/tasks">← Tasks</a>' in page
    assert "evil.example" not in page and "javascript:" not in page


def test_lists_use_the_shared_components(client):
    """
    Given a captured task and a project
    When opening the tasks list, the projects list and an empty refine queue
    Then states and statuses are badges, refs are chips and empty lists use the empty item
    """
    client.post("/tasks", data={"title": "Write the docs"})
    client.post("/projects", data={"key": "nx", "name": "Nexus"})

    assert '<span class="badge badge-inbox">INBOX</span>' in client.get("/tasks").get_data(as_text=True)
    projects_page = client.get("/projects").get_data(as_text=True)
    assert '<code class="ref">nx</code>' in projects_page
    assert '<span class="badge badge-active">ACTIVE</span>' in projects_page
    assert '<li class="empty">Nothing to refine.</li>' in client.get("/refine").get_data(as_text=True)


def test_templates_have_no_inline_style_attribute():
    """
    Given every page template
    When reading its source
    Then none uses an inline style attribute: styling lives in static/app.css
    """
    from pathlib import Path
    templates = Path(__file__).parents[2] / "src" / "web" / "templates"
    offenders = [t.name for t in templates.glob("*.html") if "style=" in t.read_text()]
    assert offenders == []


def test_create_forms_use_labelled_fields(client):
    """
    Given the projects page
    When reading its creation form
    Then each control is a labelled field, with no line breaks for layout
    """
    html = client.get("/projects").get_data(as_text=True)
    assert '<form class="form-stacked"' in html and "<br>" not in html
    assert '<span class="field-label">Key</span>' in html
    assert '<input type="text" name="key" value="" required>' in html


def test_task_refs_are_shown_on_detail_and_list(client):
    """A task's ref appears on its detail page and in the tasks list."""
    client.post("/tasks", data={"title": "Write the docs"})

    detail = client.get("/tasks/1").data
    ref = re.search(rb"<code[^>]*>(t-[0-9a-z]+)</code>", detail)
    assert ref is not None
    assert b'<code class="ref">' + ref.group(1) + b"</code>" in client.get("/tasks").data


def test_version_refs_are_shown_on_detail_and_list(client):
    """A version's ref appears on its detail page and in the versions list."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/versions",
                data={"number": "0.1.0", "title": "First version", "dod": "Ships"})

    detail = client.get("/projects/nexus/versions/0.1.0").data
    ref = re.search(rb"<code[^>]*>(v-[0-9a-z]+)</code>", detail)
    assert ref is not None
    assert b'<code class="ref">' + ref.group(1) + b"</code>" in client.get("/projects/nexus/versions").data
