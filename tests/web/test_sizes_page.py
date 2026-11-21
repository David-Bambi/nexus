import re

from src.services import projects, tasks


def test_sizes_page_shows_guide_and_rules(client):
    """
    Given the app
    When opening the sizes page
    Then each size row shows when to use it and an example, followed by the rules
    """
    html = client.get("/sizes").get_data(as_text=True)
    row = re.search(r'<tr data-size="L">(.*?)</tr>', html, re.S).group(1)
    assert "New concept or open questions" in row and "A new entity" in row
    assert "A task bigger than L is split." in html


def test_task_size_list_explains_each_size_and_links_the_guide(client):
    """
    Given a task of size S
    When opening its page
    Then the size list explains each size, keeps S selected, and links to the sizes page
    """
    session = client.application.extensions["db_session"]()
    projects.create(session, "nx", "Nexus", "")
    task = tasks.create(session, "Task", "nx", None, "@ordi", "S")
    html = client.get(f"/tasks/{task.id}").get_data(as_text=True)
    assert '<option value="S" selected>S — small change you understand' in html
    assert 'href="/sizes"' in html
