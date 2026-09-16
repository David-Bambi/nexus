from src.services import projects, tasks, versions, views

# Inbox --------------------------------------------------------------------------------------------

def test_inbox_returns_only_inbox_tasks(session):
    """Inbox lists only inbox-state tasks
    Given a captured task and a refined task
    When listing the inbox
    Then only the captured task is returned
    """
    inbox_task = tasks.capture(session, "Write the docs")
    refined_task = tasks.capture(session, "Ship the release")
    tasks.clarify(session, refined_task.id, "Ship the release", None, None, None, None)

    result = views.inbox(session)
    assert [t.id for t in result] == [inbox_task.id]

def test_inbox_oldest_first(session):
    """Inbox lists tasks oldest first
    Given two captured tasks
    When listing the inbox
    Then they come back in capture order
    """
    first = tasks.capture(session, "First")
    second = tasks.capture(session, "Second")

    result = views.inbox(session)
    assert [t.id for t in result] == [first.id, second.id]

def test_inbox_empty(session):
    """Inbox with no captured tasks returns an empty list
    Given no tasks
    When listing the inbox
    Then the resulting list is empty
    """
    assert not views.inbox(session)


# To refine ------------------------------------------------------------------------------------------

def test_to_refine_returns_only_unplanned_refined_tasks(session):
    """To-refine lists only refined tasks without a version
    Given an inbox task, a refined task and a planned task
    When listing to-refine
    Then only the refined, unplanned task is returned
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])

    tasks.capture(session, "Still in inbox")

    refined = tasks.capture(session, "Needs planning")
    tasks.clarify(session, refined.id, "Needs planning", None, None, None, None)

    planned = tasks.capture(session, "Already planned")
    tasks.clarify(session, planned.id, "Already planned", None, None, None, None)
    tasks.plan(session, planned.id, version.id)

    result = views.to_refine(session)
    assert [t.id for t in result] == [refined.id]

def test_to_refine_filters_by_context(session):
    """To-refine filters by context when given
    Given two refined tasks with different contexts
    When listing to-refine filtered by one context
    Then only the matching task is returned
    """
    matching = tasks.capture(session, "At the computer")
    tasks.clarify(session, matching.id, "At the computer", None, None, "@ordi", None)

    other = tasks.capture(session, "At the store")
    tasks.clarify(session, other.id, "At the store", None, None, "@achat", None)

    result = views.to_refine(session, context="@ordi")
    assert [t.id for t in result] == [matching.id]

def test_to_refine_filters_by_project_key(session):
    """To-refine filters by project key when given
    Given refined tasks under two different projects
    When listing to-refine filtered by one project key
    Then only that project's task is returned
    """
    projects.create(session, "nexus", "Nexus", "")
    projects.create(session, "other", "Other", "")

    matching = tasks.capture(session, "Nexus task")
    tasks.clarify(session, matching.id, "Nexus task", None, "nexus", None, None)

    other = tasks.capture(session, "Other task")
    tasks.clarify(session, other.id, "Other task", None, "other", None, None)

    result = views.to_refine(session, project_key="nexus")
    assert [t.id for t in result] == [matching.id]

def test_to_refine_unknown_project_key_returns_empty(session):
    """To-refine with an unknown project key returns no results
    Given a refined task with no project
    When listing to-refine filtered by a project key that doesn't exist
    Then the resulting list is empty
    """
    task = tasks.capture(session, "Needs planning")
    tasks.clarify(session, task.id, "Needs planning", None, None, None, None)

    assert not views.to_refine(session, project_key="does-not-exist")


# Search --------------------------------------------------------------------------------------------

def test_search_matches_title(session):
    """Search matches a substring of the title
    Given a captured task
    When searching for part of its title
    Then it is returned
    """
    task = tasks.capture(session, "Write the docs")
    result = views.search(session, "the docs")
    assert [t.id for t in result] == [task.id]

def test_search_matches_body(session):
    """Search matches a substring of the body
    Given a task with a body
    When searching for part of its body
    Then it is returned
    """
    projects.create(session, "nexus", "Nexus", "")
    task = tasks.create(session, "Ship it", "nexus", "Needs a changelog entry")
    result = views.search(session, "changelog")
    assert [t.id for t in result] == [task.id]

def test_search_is_case_insensitive(session):
    """Search matches regardless of case
    Given a captured task
    When searching using different casing than the title
    Then it is still returned
    """
    task = tasks.capture(session, "Write the docs")
    result = views.search(session, "WRITE")
    assert [t.id for t in result] == [task.id]

def test_search_no_match(session):
    """Search with no matching text returns an empty list
    Given a captured task
    When searching for text it doesn't contain
    Then the resulting list is empty
    """
    tasks.capture(session, "Write the docs")
    assert not views.search(session, "nonexistent")

def test_search_empty_term_returns_empty(session):
    """Search with an empty term returns no results, not the whole table
    Given a captured task
    When searching with an empty term
    Then the resulting list is empty
    """
    tasks.capture(session, "Write the docs")
    assert not views.search(session, "")
