import re

import pytest

from src.models.ai import AiMode, Nature
from src.models.task import TaskState
from src.services import ai, projects, tasks


@pytest.fixture
def session(client):
    """The session the app under test uses."""
    return client.application.extensions["db_session"]()


@pytest.fixture
def project(session):
    """A project 'nx'."""
    return projects.create(session, "nx", "Nexus", "")


def _done(session, context, mode, size="M"):
    """A done task of project 'nx' with the given domain, AI mode and size."""
    task = tasks.create(session, "Task", "nx", None, context, size)
    task.state = TaskState.DONE
    task.ai_mode = mode
    session.commit()
    return task


def _row(html, nature):
    """The HTML of one nature's row in the AI usage table."""
    return re.search(rf'<tr data-nature="{nature}">(.*?)</tr>', html, re.S).group(1)


# Task page -----------------------------------------------------------------------------------------

def test_task_edit_sets_domain_and_mode(client, session, project):
    """
    Given a task
    When saving its edit form with a domain and an AI mode
    Then the task page shows the domain label and the mode
    """
    task = tasks.create(session, "Task", "nx")
    html = client.post(f"/tasks/{task.id}/update",
                       data={"title": "Task", "context": "code-core", "ai_mode": "LEARNED"}).get_data(as_text=True)
    assert task.context == "code-core" and task.ai_mode is AiMode.LEARNED
    assert "Code: core logic" in html and "📚 Learned" in html


def test_task_edit_keeps_a_legacy_context(client, session, project):
    """
    Given a task whose context predates the domain list
    When opening it and saving its edit form unchanged
    Then the old value is offered, selected, and kept
    """
    task = tasks.create(session, "Task", "nx")
    task.context = "@ordi"
    session.commit()
    assert '<option value="@ordi" selected>' in client.get(f"/tasks/{task.id}").get_data(as_text=True)
    client.post(f"/tasks/{task.id}/update", data={"title": "Task", "context": "@ordi"})
    assert task.context == "@ordi"


def test_task_edit_refuses_an_unknown_mode_and_saves_nothing(client, session, project):
    """
    Given a task
    When saving its edit form with a new title and an unknown mode
    Then an error is shown and the title is unchanged
    """
    task = tasks.create(session, "Task", "nx")
    html = client.post(f"/tasks/{task.id}/update", data={"title": "Renamed", "ai_mode": "LAZY"}).get_data(as_text=True)
    assert "doesn&#39;t exist" in html and task.title == "Task"


# Project page --------------------------------------------------------------------------------------

def test_project_page_shows_the_profile_against_its_target(client, session, project):
    """
    Given a founding target of own >= 80 %, and done founding tasks: L autonomous, M dependent
    When opening the project page
    Then the founding row shows 67 % / 33 %, the target and a miss; left-out tasks are counted
    """
    ai.set_target(session, "nx", Nature.FOUNDING, 80, None)
    _done(session, "code-core", AiMode.AUTONOMOUS, "L")
    _done(session, "debug", AiMode.DEPENDENT, "M")
    _done(session, "docs", None)
    html = client.get("/projects/nx").get_data(as_text=True)
    row = _row(html, "FOUNDING")
    assert "67 %" in row and "33 %" in row and "✋+📚 ≥ 80 %" in row and "❌ 67 %" in row
    assert "Done tasks without mode: 1" in html


def test_project_ai_settings_form_saves_natures_and_targets(client, session, project):
    """
    Given a project
    When posting its AI settings form with 'assets' founding and a founding target
    Then both are stored and the page shows them
    """
    response = client.post("/projects/nx/ai", data={"nature_assets": "FOUNDING", "min_own_FOUNDING": "80",
                                                     "max_dependent_FOUNDING": "0"})
    assert response.status_code == 302
    assert ai.natures(session, "nx")["assets"] is Nature.FOUNDING
    assert ai.targets(session, "nx")[Nature.FOUNDING] == (80, 0)
    assert "✋+📚 ≥ 80 %" in _row(client.get("/projects/nx").get_data(as_text=True), "FOUNDING")


@pytest.mark.parametrize("value", ["120", "abc", "-5"])
def test_project_ai_settings_refuses_a_bad_percentage_and_saves_nothing(client, session, project, value):
    """
    Given a project
    When posting its AI settings with a domain change and a bad percentage
    Then a 400 page shows the error and nothing is saved
    """
    response = client.post("/projects/nx/ai", data={"nature_assets": "FOUNDING", "min_own_FOUNDING": value})
    assert response.status_code == 400 and b"between 0 and 100" in response.data
    assert ai.natures(session, "nx")["assets"] is Nature.PERIPHERAL


def test_project_ai_settings_missing_project_returns_404(client):
    """Posting AI settings for an unknown project returns 404."""
    assert client.post("/projects/nope/ai", data={}).status_code == 404


def test_task_size_select_explains_each_size(client, session, project):
    """
    Given a task of size S
    When opening its page
    Then the size list explains each size, keeps S selected, and reminds the rule
    """
    task = tasks.create(session, "Task", "nx", None, None, "S")
    html = client.get(f"/tasks/{task.id}").get_data(as_text=True)
    assert '<option value="S" selected>S — small change you understand' in html
    assert "L — new concept or open questions" in html and "split anything bigger than L" in html


def test_sizes_page_shows_weights_guide_and_rules(client):
    """
    Given the app
    When opening the sizes page
    Then each size row shows its weight, when to use it and an example, followed by the rules
    """
    html = client.get("/sizes").get_data(as_text=True)
    row = re.search(r'<tr data-size="L">(.*?)</tr>', html, re.S).group(1)
    assert "<td>8</td>" in row and "New concept or open questions" in row and "A new entity" in row
    assert "A task bigger than L is split." in html


def test_size_lists_and_project_link_to_the_sizes_page(client, session, project):
    """
    Given a task and its project
    When opening the task page and the project page
    Then both link to the sizes page
    """
    task = tasks.create(session, "Task", "nx")
    assert 'href="/sizes"' in client.get(f"/tasks/{task.id}").get_data(as_text=True)
    assert 'href="/sizes"' in client.get("/projects/nx").get_data(as_text=True)


def test_project_page_shows_weight_by_size(client, session, project):
    """
    Given done counted tasks of size L and S
    When opening the project page
    Then the weight-by-size table shows L at 80 % and S at 20 %
    """
    _done(session, "code-core", AiMode.AUTONOMOUS, "L")
    _done(session, "docs", AiMode.DELEGATED, "S")
    html = client.get("/projects/nx").get_data(as_text=True)
    row_l = re.search(r'<tr data-size="L">(.*?)</tr>', html, re.S).group(1)
    row_s = re.search(r'<tr data-size="S">(.*?)</tr>', html, re.S).group(1)
    assert "<td>8</td>" in row_l and "80 %" in row_l and "20 %" in row_s
    assert '<tr data-size="none">' in html
