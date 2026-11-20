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


def test_clarify_start_complete_task(client):
    """Clarifying, starting then completing a task updates its state."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/tasks", data={"title": "Write the docs"})

    response = client.post(
        "/tasks/1/clarify",
        data={"title": "Write the docs", "project_key": "nexus"},
    )
    assert response.status_code == 200
    assert b"REFINED" in response.data

    response = client.post("/tasks/1/start")
    assert response.status_code == 200
    assert b"DOING" in response.data

    response = client.post("/tasks/1/complete")
    assert response.status_code == 200
    assert b"DONE" in response.data


def test_start_task_not_refined_shows_error(client):
    """Starting a task that isn't refined shows an error, not a 500."""
    client.post("/tasks", data={"title": "Write the docs"})

    response = client.post("/tasks/1/start")
    assert response.status_code == 200
    assert b"isn&#39;t refined" in response.data


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


def _refined_task_in_project(client):
    """Create project 'nexus' and task 1 refined into it."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/capture", data={"title": "Write the docs"})
    client.post("/tasks/1/clarify", data={"title": "Write the docs", "project_key": "nexus"})


def test_dashboard_shows_work_in_progress(client):
    """The dashboard lists doing and waiting tasks, and the counters."""
    _refined_task_in_project(client)
    client.post("/tasks/1/start")
    client.post("/capture", data={"title": "Second task"})
    client.post("/capture", data={"title": "Blocked task"})
    client.post("/tasks/3/clarify", data={"title": "Blocked task"})
    client.post("/tasks/3/start")
    client.post("/tasks/3/block", data={"reason": "Waiting for review"})

    response = client.get("/")
    assert response.status_code == 200
    assert b"Write the docs" in response.data
    assert b"Waiting for review" in response.data
    html = response.get_data(as_text=True)
    assert re.search(r'href="/inbox">\s*<span class="stat-value">1</span>\s*<span class="stat-label">Inbox</span>', html)
    assert "Versions in progress" not in html


def test_dashboard_counters_link_to_queues(client):
    """The inbox and refine counters link to their pages."""
    response = client.get("/")
    assert b'href="/inbox"' in response.data
    assert b'href="/refine"' in response.data


def test_task_detail_shows_history(client):
    """A task's page lists each transition it went through, in order."""
    _refined_task_in_project(client)
    client.post("/tasks/1/start")

    response = client.get("/tasks/1")
    assert response.status_code == 200
    body = response.data.decode()
    positions = [body.index(action) for action in ("created", "clarified", "started")]
    assert positions == sorted(positions)


def test_task_transition_response_shows_new_history_entry(client):
    """The page returned after a transition already includes its event."""
    _refined_task_in_project(client)

    response = client.post("/tasks/1/start")
    assert response.status_code == 200
    assert b"started" in response.data


def test_export_json_is_an_attachment_with_all_tables(client):
    """The export downloads as a JSON file holding every table."""
    _refined_task_in_project(client)

    response = client.get("/export.json")
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert response.headers["Content-Disposition"].startswith("attachment; filename=")

    data = response.get_json()
    assert set(data) == {"exported_at", "projects", "criteria", "tasks", "tags", "events"}
    assert [p["key"] for p in data["projects"]] == ["nexus"]
    assert [t["title"] for t in data["tasks"]] == ["Write the docs"]
    assert data["events"]


@pytest.mark.parametrize("path,current", [
    ("/", "Dashboard"), ("/projects", "Projects"), ("/projects/nx", "Projects"),
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


def test_task_delete_returns_to_next_page(client):
    """Deleting a task opened from another page brings back to that page."""
    _refined_task_in_project(client)
    response = client.get("/tasks/1?next=/projects/nexus")
    assert b'/tasks/1/delete?next=/projects/nexus' in response.data
    response = client.post("/tasks/1/delete?next=/projects/nexus")
    assert response.status_code == 302
    assert response.headers["Location"] == "/projects/nexus"
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
    _refined_task_in_project(client)
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
    ({"state": "SOMEDAY"}, b"can&#39;t go from REFINED to SOMEDAY"),
    ({"state": "PLANNED"}, b"unknown state"),
])
def test_task_state_invalid_shows_error(client, data, message):
    """An unknown or not allowed state shows an error and keeps the task's state."""
    _refined_task_in_project(client)
    response = client.post("/tasks/1/state", data=data)
    assert response.status_code == 200
    assert message in response.data
    assert _shown_field(response, "state") == "REFINED"


def test_task_state_returns_to_the_given_page(client):
    """A state change with a local "return_to" goes back to that page."""
    _refined_task_in_project(client)
    response = client.post("/tasks/1/state", data={"state": "DOING",
                                                   "return_to": "/projects/nexus?view=kanban"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/projects/nexus?view=kanban"
    assert _shown_field(client.get("/tasks/1"), "state") == "DOING"


@pytest.mark.parametrize("target", ["https://evil.example", "//evil.example"])
def test_task_state_ignores_an_external_return_to(client, target):
    """An external "return_to" is ignored: the task page is shown."""
    _refined_task_in_project(client)
    response = client.post("/tasks/1/state", data={"state": "DOING", "return_to": target})
    assert response.status_code == 200
    assert _shown_field(response, "state") == "DOING"


def test_task_state_refused_shows_the_task_page_despite_return_to(client):
    """A refused change (waiting without a reason) shows the error on the task page."""
    _refined_task_in_project(client)
    client.post("/tasks/1/state", data={"state": "DOING"})
    response = client.post("/tasks/1/state", data={"state": "WAITING",
                                                   "return_to": "/projects/nexus?view=kanban"})
    assert response.status_code == 200
    assert _shown_field(response, "state") == "DOING"


def test_task_state_select_absent_for_inbox_task(client):
    """A captured task has no state select; clarifying comes first."""
    client.post("/tasks", data={"title": "Write the docs"})
    response = client.get("/tasks/1")
    assert b'name="state"' not in response.data


def test_task_state_unknown_task_returns_404(client):
    """Changing the state of an unknown task returns 404."""
    response = client.post("/tasks/9/state", data={"state": "DOING"})
    assert response.status_code == 404


def test_task_cancel_and_restore(client):
    """A task can be cancelled from its page, then restored to refined."""
    _refined_task_in_project(client)
    assert b'action="/tasks/1/cancel"' in client.get("/tasks/1").data
    response = client.post("/tasks/1/cancel")
    assert _shown_field(response, "state") == "CANCELLED"
    assert b'action="/tasks/1/cancel"' not in response.data
    assert b'action="/tasks/1/restore"' in response.data
    response = client.post("/tasks/1/restore")
    assert _shown_field(response, "state") == "REFINED"


def test_task_cancel_done_task_shows_error(client):
    """Cancelling a done task shows an error and keeps it done."""
    _refined_task_in_project(client)
    client.post("/tasks/1/state", data={"state": "DOING"})
    client.post("/tasks/1/state", data={"state": "DONE"})
    response = client.post("/tasks/1/cancel")
    assert b"already done or cancelled" in response.data
    assert _shown_field(response, "state") == "DONE"


def _shown_field(response, field):
    """The text of one field of a task page's details panel, tags stripped (e.g. "DOING" for the state)."""
    page = response.get_data(as_text=True)
    cell = page.split(f'<dd data-field="{field}">')[1].split("</dd>")[0]
    return re.sub(r"<[^>]+>", "", cell).strip()


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



def test_project_page_lists_its_subprojects(app, client):
    """
    Given a project with a subproject
    When opening both pages
    Then the project lists the subproject, and the subproject names its parent
    """
    from src.services import projects
    session = app.extensions["db_session"]()
    projects.create(session, "nexus", "Nexus")
    sub = projects.create(session, "v2", "Nexus 2", parent_key="nexus")
    html = client.get("/projects/nexus").get_data(as_text=True)
    assert "Subprojects" in html and "Nexus 2" in html and sub.ref in html
    assert "Subproject of" in client.get("/projects/v2").get_data(as_text=True)


def test_deleting_a_non_empty_project_shows_why(client):
    """
    Given a project holding a task
    When deleting it
    Then it is kept and the page explains why, with status 409
    """
    _refined_task_in_project(client)
    response = client.post("/projects/nexus/delete")
    assert response.status_code == 409 and b"isn&#39;t empty" in response.data
    assert b'<section id="delete-project" class="danger-zone">' in response.data
    assert b'aria-expanded="true" aria-controls="delete-project"' in response.data
    assert client.get("/projects/nexus").status_code == 200


def test_delete_confirmation_is_hidden_behind_the_trash(client):
    """The delete confirmation starts hidden, opened by the trash next to the project's name."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    html = client.get("/projects/nexus").get_data(as_text=True)
    assert 'aria-label="Delete the project"' in html and 'data-reveal="delete-project"' in html
    assert '<section id="delete-project" class="danger-zone" hidden>' in html
    assert html.index('data-reveal="delete-project"') < html.index('id="work"')


def test_task_page_shows_kind_and_parent(app, client):
    """
    Given a task under a feature
    When opening the task page
    Then its kind and its parent feature are shown
    """
    from src.models.task import TaskKind
    from src.services import projects, tasks
    session = app.extensions["db_session"]()
    projects.create(session, "nexus", "Nexus")
    feature = tasks.create(session, "Tree", "nexus", kind=TaskKind.FEATURE)
    task = tasks.create(session, "Model", parent_ref=feature.ref)
    response = client.get(f"/tasks/{task.id}")
    assert _shown_field(response, "kind") == "task"
    assert "Tree" in _shown_field(response, "parent")


# Project tree --------------------------------------------------------------------------------------

def _project_with_feature(client):
    """Create project 'nexus' and add a feature to it through the web; return the feature's ref."""
    from src.models.task import Task

    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Auth", "kind": "feature"})
    session = client.application.extensions["db_session"]
    return session.query(Task).filter_by(title="Auth").one().ref


def test_add_items_builds_the_tree(client):
    """
    Given a project with a feature
    When a task is added under the feature and another at the top
    Then the project page shows them nested, each inbox
    """
    feature_ref = _project_with_feature(client)
    response = client.post("/projects/nexus/items",
                           data={"title": "Login form", "kind": "task", "parent_ref": feature_ref})
    assert response.status_code == 302
    client.post("/projects/nexus/items", data={"title": "Readme"})

    html = client.get("/projects/nexus").get_data(as_text=True)
    assert html.index("Auth") < html.index("Login form") < html.index("Readme")
    assert html.count("tree-feature") == 1 and html.count("tree-task") == 2
    assert "INBOX" in html and "REFINED" not in html


def test_add_forms_are_hidden_behind_plus_buttons(client):
    """
    Given a project with a feature
    When opening the backlog
    Then the root add form and the feature's add form are hidden, each opened by its "+" button
    """
    feature_ref = _project_with_feature(client)
    html = client.get("/projects/nexus").get_data(as_text=True)
    for form_id, label in (("add-root", "Add an item to the project"),
                           (f"add-{feature_ref}", "Add an item under Auth")):
        assert f'<form class="form-inline add-item" id="{form_id}" hidden' in html
        assert f'aria-label="{label}"' in html and f'data-reveal="{form_id}"' in html
    assert html.count('class="form-inline add-item"') == 2


def test_add_item_comes_back_to_its_place(client):
    """An add under a feature comes back to the feature's row; an add at the top, to the work section."""
    feature_ref = _project_with_feature(client)
    response = client.post("/projects/nexus/items", data={"title": "Form", "parent_ref": feature_ref})
    assert response.headers["Location"] == f"/projects/nexus#item-{feature_ref}"
    response = client.post("/projects/nexus/items", data={"title": "Readme"})
    assert response.headers["Location"] == "/projects/nexus#work"


def test_refused_add_shows_its_form_open(client):
    """An add refused under a feature shows the page with that form open and the others hidden."""
    feature_ref = _project_with_feature(client)
    response = client.post("/projects/nexus/items", data={"title": " ", "parent_ref": feature_ref})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert f'id="add-{feature_ref}" method="post"' in html
    assert '<form class="form-inline add-item" id="add-root" hidden' in html
    assert f'aria-expanded="true" aria-controls="add-{feature_ref}"' in html


def test_feature_page_tree_keeps_its_plus_buttons(client):
    """On a feature's page, a sub-feature of its tree has its "+" and hidden add form too."""
    feature_ref = _project_with_feature(client)
    client.post("/projects/nexus/items", data={"title": "Login", "kind": "feature", "parent_ref": feature_ref})
    from src.models.task import Task
    session = client.application.extensions["db_session"]
    auth, login = (session.query(Task).filter_by(title=t).one() for t in ("Auth", "Login"))
    html = client.get(f"/tasks/{auth.id}").get_data(as_text=True)
    assert f'data-reveal="add-{login.ref}"' in html
    assert f'id="add-{login.ref}" hidden' in html


def test_add_item_with_empty_title_shows_the_error(client):
    """An empty title is refused and the project page shows why."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    response = client.post("/projects/nexus/items", data={"title": " "})
    assert response.status_code == 400
    assert "The title must be specified." in response.get_data(as_text=True)


def test_add_item_under_a_feature_of_another_project_is_refused(client):
    """A parent ref from another project is refused, and nothing is created."""
    feature_ref = _project_with_feature(client)
    client.post("/projects", data={"key": "other", "name": "Other"})
    response = client.post("/projects/other/items", data={"title": "Stray", "parent_ref": feature_ref})
    assert response.status_code == 400
    assert "Stray" not in client.get("/projects/nexus").get_data(as_text=True)
    assert client.get("/inbox").get_data(as_text=True).count("Stray") == 0


def test_add_item_to_a_missing_project_is_404(client):
    """Adding to an unknown project answers 404."""
    assert client.post("/projects/missing/items", data={"title": "X"}).status_code == 404


def test_backlog_shows_open_items_only(client):
    """
    Given a cancelled item and a done item
    When opening the backlog, even with ?closed=1
    Then neither is shown, and there is no show-closed switch
    """
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Dropped idea"})
    client.post("/projects/nexus/items", data={"title": "Shipped"})
    client.post("/tasks/1/cancel")
    client.post("/tasks/2/state", data={"state": "REFINED"})
    client.post("/tasks/2/start")
    client.post("/tasks/2/complete")

    for path in ("/projects/nexus", "/projects/nexus?closed=1"):
        html = client.get(path).get_data(as_text=True)
        assert "Dropped idea" not in html and "Shipped" not in html
        assert "Show closed" not in html and "Hide closed" not in html


def test_backlog_feature_row_shows_its_overview(client):
    """
    Given a feature with two sized tasks, one of them done, and a cancelled one
    When opening the backlog
    Then the feature row reads 1/2 and the open size, and each row has its anchor
    """
    feature_ref = _project_with_feature(client)
    for title in ("Form", "Hash", "Dropped"):
        client.post("/projects/nexus/items", data={"title": title, "parent_ref": feature_ref})
    session = client.application.extensions["db_session"]
    from src.models.task import Task
    by_title = {t.title: t for t in session.query(Task).all()}
    for title, size in (("Form", "S"), ("Hash", "M")):
        client.post(f"/tasks/{by_title[title].id}/update", data={"title": title, "size": size})
    client.post(f"/tasks/{by_title['Hash'].id}/state", data={"state": "REFINED"})
    client.post(f"/tasks/{by_title['Hash'].id}/start")
    client.post(f"/tasks/{by_title['Hash'].id}/complete")
    client.post(f"/tasks/{by_title['Dropped'].id}/cancel")

    html = client.get("/projects/nexus").get_data(as_text=True)
    assert ">1/2 · 1 S</span>" in html
    assert f'id="item-{feature_ref}"' in html and f'id="item-{by_title["Form"].ref}"' in html
    assert html.count('class="tree-row"') == 2


# Kanban view ---------------------------------------------------------------------------------------

def _kanban_project(client):
    """Create project 'nexus' with feature Auth > Login > Form, task Auth > Hash and a loose
    task Readme, all through the web; return the refs by title."""
    from src.models.task import Task

    feature_ref = _project_with_feature(client)
    client.post("/projects/nexus/items", data={"title": "Login", "kind": "feature", "parent_ref": feature_ref})
    session = client.application.extensions["db_session"]
    login_ref = session.query(Task).filter_by(title="Login").one().ref
    client.post("/projects/nexus/items", data={"title": "Form", "parent_ref": login_ref})
    client.post("/projects/nexus/items", data={"title": "Hash", "parent_ref": feature_ref})
    client.post("/projects/nexus/items", data={"title": "Readme"})
    items = session.query(Task).all()
    for item in items:
        client.post(f"/tasks/{item.id}/state", data={"state": "REFINED"})
    return {t.title: t for t in items}


def test_project_page_shows_the_backlog_by_default(client):
    """Without a view, or with an unknown one, the page shows the tree, its tab marked current."""
    _kanban_project(client)
    for path in ("/projects/nexus", "/projects/nexus?view=nope"):
        html = client.get(path).get_data(as_text=True)
        assert "tree-feature" in html and "kanban-lane" not in html
        assert 'aria-current="true">Backlog</a>' in html


def test_kanban_view_lays_tasks_out_in_lanes_and_columns(client):
    """
    Given a feature with a sub-feature and a task, and a loose task
    When opening the kanban view
    Then there is a lane per feature then one for loose tasks, four columns each,
    and no card for a feature
    """
    _kanban_project(client)
    html = client.get("/projects/nexus?view=kanban").get_data(as_text=True)

    assert 'aria-current="true">Kanban</a>' in html
    assert html.count('class="kanban-lane"') == 2
    assert html.count('class="kanban-column"') == 8
    for state in ("DONE", "SOMEDAY", "CANCELLED"):
        assert f'<div class="kanban-column" data-state="{state}"' not in html
    assert html.index("Auth") < html.index("Form") < html.index("No feature") < html.index("Readme")
    assert html.count('class="kanban-card"') == 3
    assert "tree-feature" not in html


def test_kanban_card_has_the_state_form_coming_back_to_the_board(client):
    """A refined card has an icon per next state (doing, cancelled), each naming its target,
    posting back to the board; no select, no Move button."""
    _kanban_project(client)
    html = client.get("/projects/nexus?view=kanban").get_data(as_text=True)
    board = html.split('class="kanban"')[1].split("add-item")[0]
    assert board.count('title="Move to DOING"') == 3
    assert board.count('title="Move to CANCELLED"') == 3
    assert "<select" not in board and ">Move</button>" not in board


def test_kanban_inbox_card_can_be_refined_in_place(client):
    """A card added to the project sits in INBOX with a REFINED icon; moving it keeps its feature."""
    feature_ref = _project_with_feature(client)
    client.post("/projects/nexus/items", data={"title": "Form", "parent_ref": feature_ref})
    html = client.get("/projects/nexus?view=kanban").get_data(as_text=True)
    inbox = html.index('<div class="kanban-column" data-state="INBOX"')
    assert inbox < html.index("Form") < html.index('<div class="kanban-column" data-state="REFINED"', inbox)
    assert 'title="Move to REFINED"' in html

    client.post("/tasks/2/state", data={"state": "REFINED", "return_to": "/projects/nexus?view=kanban"})
    html = client.get("/tasks/2").get_data(as_text=True)
    assert _shown_field(client.get("/tasks/2"), "state") == "REFINED" and feature_ref in html


def test_inbox_page_leaves_out_items_placed_in_a_project(client):
    """The inbox page shows a capture, not an item added to a project."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Placed item"})
    client.post("/tasks", data={"title": "Loose capture"})
    html = client.get("/inbox").get_data(as_text=True)
    assert "Loose capture" in html and "Placed item" not in html


def test_kanban_waiting_icon_reveals_a_reason_field(client):
    """A started card's WAITING icon reveals a hidden reason form posting WAITING."""
    refs = _kanban_project(client)
    task_id = refs["Hash"].id
    client.post(f"/tasks/{task_id}/start")
    html = client.get("/projects/nexus?view=kanban").get_data(as_text=True)
    assert f'data-reveal="reason-{task_id}"' in html
    reason_form = html.split(f'id="reason-{task_id}"')[1].split("</form>")[0]
    assert "hidden" in reason_form.split(">")[0]
    assert 'name="state" value="WAITING"' in reason_form
    assert 'name="reason"' in reason_form and "required" in reason_form
    assert 'name="return_to" value="/projects/nexus?view=kanban"' in html


def test_kanban_leaves_out_closed_tasks_and_their_empty_lane(client):
    """
    Given the only loose task cancelled
    When opening the kanban view, even with closed items asked for
    Then the task and its lane are gone, and there is no show-closed switch
    """
    refs = _kanban_project(client)
    client.post(f"/tasks/{refs['Readme'].id}/cancel")
    html = client.get("/projects/nexus?view=kanban&closed=1").get_data(as_text=True)
    assert "Readme" not in html and "No feature" not in html
    assert "Show closed" not in html and "Hide closed" not in html


def test_kanban_state_change_goes_back_to_the_board(client):
    """Moving a card from the board comes back to the board, with the card in its new column."""
    refs = _kanban_project(client)
    response = client.post(f"/tasks/{refs['Hash'].id}/state",
                           data={"state": "DOING", "return_to": "/projects/nexus?view=kanban"})
    assert response.headers["Location"] == "/projects/nexus?view=kanban"
    html = client.get("/projects/nexus?view=kanban").get_data(as_text=True)
    doing = html.index('<div class="kanban-column" data-state="DOING"')
    assert doing < html.index("Hash") < html.index('<div class="kanban-column" data-state="WAITING"', doing)


def test_kanban_shows_subproject_lanes(client):
    """A subproject's lane comes after the project's own, titled with the subproject."""
    _kanban_project(client)
    client.post("/projects/nexus/subprojects", data={"key": "web", "name": "Web UI"})
    client.post("/projects/web/items", data={"title": "Pages"})
    html = client.get("/projects/nexus?view=kanban").get_data(as_text=True)
    assert html.index("Readme") < html.index("Web UI /") < html.index("Pages")


def test_kanban_view_has_no_creation_or_management_forms(client):
    """The kanban view only moves tasks: no add item, criteria, edit, subproject, status or
    delete form; the backlog view keeps them."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    html = client.get("/projects/nexus?view=kanban").get_data(as_text=True)
    assert "No tasks to do." in html
    for marker in ('class="form-inline add-item"', "New criterion", 'id="edit-project"',
                   "Create subproject", "<h2>Status</h2>", "danger-zone"):
        assert marker not in html
    backlog = client.get("/projects/nexus").get_data(as_text=True)
    assert 'class="form-inline add-item"' in backlog and "Create subproject" in backlog


# Project management --------------------------------------------------------------------------------

def test_create_subproject_from_the_project_page(client):
    """A subproject created on its root project's page is listed there."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    response = client.post("/projects/nexus/subprojects", data={"key": "web", "name": "Web UI"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/projects/nexus#subprojects"

    html = client.get("/projects/nexus").get_data(as_text=True)
    assert "Web UI" in html
    sub = client.get("/projects/web").get_data(as_text=True)
    assert "Subproject of" in sub
    assert "Subprojects" not in sub and 'id="add-subproject"' not in sub


def test_root_project_shows_subprojects_title_with_its_plus(client):
    """A root project without subprojects still shows the title, with a "+" opening the hidden form."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    html = client.get("/projects/nexus").get_data(as_text=True)
    assert '<h2 id="subprojects" class="heading-actions">Subprojects' in html
    assert 'aria-label="Add a subproject"' in html and 'data-reveal="add-subproject"' in html
    assert 'action="/projects/nexus/subprojects" hidden>' in html
    assert "<h2>New subproject</h2>" not in html


def test_create_subproject_with_a_taken_key_shows_the_error(client):
    """A duplicate key is refused on the project page."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    response = client.post("/projects/nexus/subprojects", data={"key": "nexus", "name": "Again"})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "already exists" in html
    assert 'action="/projects/nexus/subprojects">' in html
    assert 'aria-expanded="true" aria-controls="add-subproject"' in html


def test_update_project_name_and_description(client):
    """Saving the edit form changes the name and description."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/update", data={"name": "Nexus 2", "description": "Tree manager"})
    html = client.get("/projects/nexus").get_data(as_text=True)
    assert "Nexus 2" in html and "Tree manager" in html


def test_update_project_with_empty_name_shows_the_error(client):
    """An empty name is refused, and the page shows the edit form open."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    response = client.post("/projects/nexus/update", data={"name": " "})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "name must be specified" in html
    assert 'id="edit-project" class="form-stacked" method="post" action="/projects/nexus/update">' in html
    assert 'aria-expanded="true" aria-controls="edit-project"' in html


def test_edit_form_is_hidden_behind_the_pencil(client):
    """The edit form starts hidden, opened by the pencil next to the project's name."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    html = client.get("/projects/nexus").get_data(as_text=True)
    assert '<h1 class="heading-actions">Nexus' in html
    assert 'aria-label="Edit the project"' in html and 'data-reveal="edit-project"' in html
    assert 'action="/projects/nexus/update" hidden>' in html
    assert "<h2>Edit</h2>" not in html


def test_archive_then_restore_a_project(client):
    """Archiving shows the restore button; restoring brings back the archive one."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/archive")
    html = client.get("/projects/nexus").get_data(as_text=True)
    assert "ARCHIVED" in html and "Restore project" in html

    client.post("/projects/nexus/restore")
    assert "Archive project" in client.get("/projects/nexus").get_data(as_text=True)


def test_restore_an_active_project_shows_the_error(client):
    """Restoring a project that isn't archived is refused."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    response = client.post("/projects/nexus/restore")
    assert response.status_code == 409
    assert "archived." in response.get_data(as_text=True)


# Version block ---------------------------------------------------------------------------------------

def test_project_page_shows_the_version(client):
    """A new project shows v0.0 and a disabled release button."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    html = client.get("/projects/nexus").get_data(as_text=True)
    assert "v0.0" in html
    assert 'type="submit" disabled>Release 1.0' in html


def test_criteria_then_major_release(client):
    """
    Given a project with one criterion
    When it is edited and checked, then the project released
    Then the button gets enabled, and the project goes to v1.0 with no criterion
    """
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/criteria", data={"text": "Tests green"})
    client.post("/projects/nexus/criteria/1/update", data={"text": "All tests green"})
    client.post("/projects/nexus/criteria/1/check", data={"done": "1"})

    html = client.get("/projects/nexus").get_data(as_text=True)
    assert "All tests green" in html and 'type="submit">Release 1.0' in html

    assert client.post("/projects/nexus/release").status_code == 302
    html = client.get("/projects/nexus").get_data(as_text=True)
    assert "v1.0" in html and "No criterion yet." in html and "Release 2.0" in html


def test_release_with_an_unchecked_criterion_shows_the_error(client):
    """The service refuses the release even if the form is sent."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/criteria", data={"text": "Docs built"})
    response = client.post("/projects/nexus/release")
    assert response.status_code == 409
    assert "unchecked criteria" in response.get_data(as_text=True)


def test_uncheck_and_delete_a_criterion(client):
    """A criterion can be unchecked, then deleted."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/criteria", data={"text": "Docs built"})
    client.post("/projects/nexus/criteria/1/check", data={"done": "1"})
    client.post("/projects/nexus/criteria/1/check", data={"done": "0"})
    assert 'aria-label="Check"' in client.get("/projects/nexus").get_data(as_text=True)

    client.post("/projects/nexus/criteria/1/delete")
    assert "Docs built" not in client.get("/projects/nexus").get_data(as_text=True)


def test_criterion_row_has_its_full_text_and_save_and_delete_icons(client):
    """
    Given a criterion with a long text
    When opening the backlog
    Then its row holds the whole text, a save icon sending it and a delete icon sending the
    hidden delete form; the add form is hidden behind its "+"
    """
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    text = "Every page works with the keyboard alone, and every form shows its errors in place"
    client.post("/projects/nexus/criteria", data={"text": text})
    html = client.get("/projects/nexus").get_data(as_text=True)

    assert f'value="{text}"' in html
    assert 'aria-label="Save criterion"' in html
    assert 'form="delete-criterion-1"' in html and 'aria-label="Delete criterion"' in html
    assert 'id="delete-criterion-1" method="post" action="/projects/nexus/criteria/1/delete" hidden' in html
    assert 'id="add-criterion"' in html and 'data-reveal="add-criterion"' in html
    assert '/criteria" hidden>' in html


def test_criterion_actions_come_back_to_the_criteria(client):
    """Adding, editing, checking and deleting a criterion come back to the criteria section."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    for path, data in (("/projects/nexus/criteria", {"text": "Docs built"}),
                       ("/projects/nexus/criteria/1/update", {"text": "Docs built and checked"}),
                       ("/projects/nexus/criteria/1/check", {"done": "1"}),
                       ("/projects/nexus/criteria/1/delete", {})):
        response = client.post(path, data=data)
        assert response.headers["Location"] == "/projects/nexus#criteria"


def test_refused_criterion_add_shows_its_form_open(client):
    """An empty criterion is refused, and the page shows the add form open."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    response = client.post("/projects/nexus/criteria", data={"text": " "})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert 'action="/projects/nexus/criteria">' in html
    assert 'aria-expanded="true" aria-controls="add-criterion"' in html


def test_criterion_of_another_project_is_404(client):
    """A criterion can't be changed through another project's URL."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects", data={"key": "other", "name": "Other"})
    client.post("/projects/nexus/criteria", data={"text": "Docs built"})
    assert client.post("/projects/other/criteria/1/delete").status_code == 404
    assert client.post("/projects/nexus/criteria/99/delete").status_code == 404


def test_completed_feature_raises_the_shown_version(client):
    """Completing a feature from the web shows the new minor version."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Auth", "kind": "feature"})
    client.post("/tasks/1/state", data={"state": "REFINED"})
    client.post("/tasks/1/start")
    client.post("/tasks/1/complete")
    assert "v0.1" in client.get("/projects/nexus").get_data(as_text=True)


# Projects list ------------------------------------------------------------------------------------------

def test_projects_list_nests_subprojects_with_versions(client):
    """
    Given two root projects, the first with a subproject at 0.1
    When listing projects
    Then the subproject is right under its root, indented, and each row shows its version
    """
    client.post("/projects", data={"key": "alpha", "name": "Alpha"})
    client.post("/projects", data={"key": "beta", "name": "Beta"})
    client.post("/projects/alpha/subprojects", data={"key": "sub", "name": "Sub"})
    client.post("/projects/sub/items", data={"title": "Feat", "kind": "feature"})
    client.post("/tasks/1/state", data={"state": "REFINED"})
    client.post("/tasks/1/start")
    client.post("/tasks/1/complete")

    html = client.get("/projects").get_data(as_text=True)
    assert html.index("Alpha") < html.index("Sub") < html.index("Beta")
    assert html.count('class="subproject"') == 1
    assert "v0.1" in html and html.count("v0.0") == 2


def test_projects_list_hides_archived_subprojects(client):
    """An archived subproject is left out, like an archived root project."""
    client.post("/projects", data={"key": "alpha", "name": "Alpha"})
    client.post("/projects/alpha/subprojects", data={"key": "sub", "name": "Old sub"})
    client.post("/projects/sub/archive")
    assert "Old sub" not in client.get("/projects").get_data(as_text=True)


# Item page ----------------------------------------------------------------------------------------------

def test_feature_page_adds_and_shows_children(client):
    """
    Given a feature
    When a child is added from its page
    Then the feature page lists it, refined, and shows the release field
    """
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Auth", "kind": "feature"})
    response = client.post("/tasks/1/children", data={"title": "Login form", "kind": "task"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/tasks/1#children"

    html = client.get("/tasks/1").get_data(as_text=True)
    assert "Login form" in html and "REFINED" in html
    assert 'data-field="released_in">—' in html


def test_feature_page_add_form_is_hidden_behind_its_plus(client):
    """On a feature's page, the add form starts hidden, opened by the "+" next to Children."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Auth", "kind": "feature"})
    html = client.get("/tasks/1").get_data(as_text=True)
    assert '<h2 id="children" class="heading-actions">Children' in html
    assert 'aria-label="Add an item under Auth"' in html and 'data-reveal="add-child"' in html
    assert 'action="/tasks/1/children" hidden>' in html


def test_feature_page_refused_add_shows_its_form_open(client):
    """An empty title is refused, and the feature page shows the add form open, keeping next."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Auth", "kind": "feature"})
    response = client.post("/tasks/1/children?next=/projects/nexus", data={"title": " "})
    html = response.get_data(as_text=True)
    assert "title must be specified" in html
    assert 'action="/tasks/1/children?next=/projects/nexus">' in html
    assert 'aria-expanded="true" aria-controls="add-child"' in html


def test_feature_page_add_keeps_its_back_link(client):
    """After an add, the feature page comes back with the same back link."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Auth", "kind": "feature"})
    response = client.post("/tasks/1/children?next=/projects/nexus", data={"title": "Login"})
    assert response.headers["Location"] == "/tasks/1?next=/projects/nexus#children"


def test_feature_page_shows_its_release(client):
    """A completed feature shows the version it shipped in."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Auth", "kind": "feature"})
    client.post("/tasks/1/state", data={"state": "REFINED"})
    client.post("/tasks/1/start")
    client.post("/tasks/1/complete")
    assert 'data-field="released_in">v0.1' in client.get("/tasks/1").get_data(as_text=True)


def test_task_page_has_no_children_section(client):
    """A task (a leaf) shows neither children nor a release field."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Readme"})
    html = client.get("/tasks/1").get_data(as_text=True)
    assert "<h2>Children</h2>" not in html and "released_in" not in html


def test_move_an_item_under_a_feature_then_to_another_project(client):
    """An item moves under a feature, then to the top of another project."""
    from src.services import tasks as task_service

    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects", data={"key": "other", "name": "Other"})
    client.post("/projects/nexus/items", data={"title": "Auth", "kind": "feature"})
    client.post("/projects/nexus/items", data={"title": "Readme"})
    session = client.application.extensions["db_session"]
    auth_ref = task_service.get(session, 1).ref

    client.post("/tasks/2/move", data={"parent_ref": auth_ref})
    assert task_service.get(session, 2).parent.ref == auth_ref

    client.post("/tasks/2/move", data={"project_key": "other"})
    moved = task_service.get(session, 2)
    assert (moved.project.key, moved.parent) == ("other", None)


def test_move_without_target_shows_the_error(client):
    """A move with neither project nor parent is refused on the page."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Readme"})
    response = client.post("/tasks/1/move", data={})
    assert response.status_code == 200
    assert 'class="error"' in response.get_data(as_text=True)


def test_change_kind_both_ways_and_refusal(client):
    """A task becomes a feature and back; a feature with children can't become a task."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Auth"})

    client.post("/tasks/1/kind", data={"kind": "feature"})
    assert 'data-field="kind">feature' in client.get("/tasks/1").get_data(as_text=True)

    client.post("/tasks/1/children", data={"title": "Login"})
    response = client.post("/tasks/1/kind", data={"kind": "task"})
    assert "has children" in response.get_data(as_text=True)

    client.post("/tasks/2/delete")
    client.post("/tasks/1/kind", data={"kind": "task"})
    assert 'data-field="kind">task' in client.get("/tasks/1").get_data(as_text=True)


# Inbox triage in the tree ---------------------------------------------------------------------------------

def test_inbox_triage_turns_a_capture_into_a_feature(client):
    """
    Given a captured task
    When it is refined in the inbox as a feature of a project
    Then it is a refined feature at the top of that project
    """
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/tasks", data={"title": "Auth"})
    assert "Parent feature ref" in client.get("/inbox").get_data(as_text=True)

    client.post("/inbox/1/clarify", data={"title": "Auth", "project_key": "nexus", "kind": "feature"})

    html = client.get("/tasks/1").get_data(as_text=True)
    assert 'data-field="kind">feature' in html and "REFINED" in html
    assert "tree-feature" in client.get("/projects/nexus").get_data(as_text=True)


def test_inbox_triage_places_a_capture_under_a_feature(client):
    """A capture refined with only a parent ref goes under that feature, in its project."""
    from src.services import tasks as task_service

    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Auth", "kind": "feature"})
    client.post("/tasks", data={"title": "Login form"})
    session = client.application.extensions["db_session"]
    auth_ref = task_service.get(session, 1).ref

    client.post("/inbox/2/clarify", data={"title": "Login form", "parent_ref": auth_ref, "kind": "task"})

    item = task_service.get(session, 2)
    assert (item.parent.ref, item.project.key) == (auth_ref, "nexus")


def test_inbox_triage_with_a_bad_parent_shows_the_error(client):
    """An unknown parent ref is refused and the item stays in the inbox."""
    client.post("/tasks", data={"title": "Login form"})
    response = client.post("/inbox/1/clarify", data={"title": "Login form", "parent_ref": "f-zzz"})
    assert 'class="error"' in response.get_data(as_text=True)
    assert "Login form" in client.get("/inbox").get_data(as_text=True)


def test_item_page_links_back_to_its_project(client):
    """An item in a project links back to that project; a loose capture to the tasks list."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Readme"})
    client.post("/tasks", data={"title": "Loose"})

    assert '<a href="/projects/nexus">← Nexus</a>' in client.get("/tasks/1").get_data(as_text=True)
    assert '<a href="/tasks">← Tasks</a>' in client.get("/tasks/2").get_data(as_text=True)


# Reorder ------------------------------------------------------------------------------------------------

def test_reorder_buttons_move_an_item_and_come_back(client):
    """
    Given a project with items A then B
    When B's up button is sent from the project page with a query string
    Then it comes back to that exact page, with B before A
    """
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Item A"})
    client.post("/projects/nexus/items", data={"title": "Item B"})
    page = client.get("/projects/nexus?view=backlog").get_data(as_text=True)
    assert 'aria-label="Move Item B up"' in page

    response = client.post("/tasks/2/reorder?next=/projects/nexus?view%3Dbacklog", data={"direction": "up"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/projects/nexus?view=backlog"

    html = client.get("/projects/nexus").get_data(as_text=True)
    assert html.index("Item B") < html.index("Item A")


def test_reorder_refused_shows_the_item_page(client):
    """Moving the first item up shows the reason on its page."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Item A"})
    response = client.post("/tasks/1/reorder", data={"direction": "up"})
    assert response.status_code == 200
    assert "already first" in response.get_data(as_text=True)


def test_reorder_without_next_goes_back_to_the_project(client):
    """Without a next page, a reorder goes back to the item's project."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Item A"})
    client.post("/projects/nexus/items", data={"title": "Item B"})
    response = client.post("/tasks/2/reorder", data={"direction": "up"})
    assert response.headers["Location"] == "/projects/nexus"


# Project directory -----------------------------------------------------------------------------------

def test_project_directory_set_on_creation_shown_and_inherited(client):
    """
    Given a project created with a directory and a subproject without one
    When viewing them
    Then the project shows its directory and the subproject the inherited one
    """
    client.post("/projects", data={"key": "nexus", "name": "Nexus", "directory": "/srv/nexus/"})
    client.post("/projects/nexus/subprojects", data={"key": "web", "name": "Web"})
    assert '<code data-field="directory">/srv/nexus</code>' in client.get("/projects/nexus").get_data(as_text=True)
    sub = client.get("/projects/web").get_data(as_text=True)
    assert '<code data-field="directory">/srv/nexus</code> (from Nexus)' in sub


def test_project_edit_changes_or_clears_the_directory(client):
    """The edit form sets the directory, refuses a relative one, and clears it when blank."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/update", data={"name": "Nexus", "directory": "/srv/nexus"})
    assert 'value="/srv/nexus"' in client.get("/projects/nexus").get_data(as_text=True)

    response = client.post("/projects/nexus/update", data={"name": "Nexus", "directory": "rel"})
    assert response.status_code == 400 and "absolute path" in response.get_data(as_text=True)

    client.post("/projects/nexus/update", data={"name": "Nexus", "directory": ""})
    assert 'data-field="directory"' not in client.get("/projects/nexus").get_data(as_text=True)


def test_task_edit_with_the_correction_box_logs_corrected(client):
    """The edit form's correction box logs the change as corrected."""
    from src.models.event import Event

    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Wirte docs"})
    assert 'name="correction"' in client.get("/tasks/1").get_data(as_text=True)

    client.post("/tasks/1/update", data={"title": "Write docs", "correction": "1"})
    client.post("/tasks/1/update", data={"title": "Write the docs"})
    session = client.application.extensions["db_session"]
    actions = [e.action for e in session.query(Event).filter_by(entity_type="task").order_by(Event.id)]
    assert actions[-2:] == ["corrected", "updated"]


def test_features_export_is_served_as_json(client):
    """The feature export is served inline as JSON, under its schema name."""
    client.post("/projects", data={"key": "nexus", "name": "Nexus"})
    client.post("/projects/nexus/items", data={"title": "Auth", "kind": "feature"})
    response = client.get("/export/features.json")
    assert response.status_code == 200 and response.mimetype == "application/json"
    data = response.get_json()
    assert data["schema"] == "nexus.features/1" and [f["title"] for f in data["features"]] == ["Auth"]
