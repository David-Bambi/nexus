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


# Dashboard ----------------------------------------------------------------------------------------

def _refined_task(session, title, version=None):
    """Capture and clarify a task, optionally planning it into a version."""
    task = tasks.capture(session, title)
    tasks.clarify(session, task.id, title, None, None, None, None)
    if version:
        tasks.plan(session, task.id, version.id)
    return task

def test_dashboard_empty(session):
    """Dashboard on an empty database shows nothing
    Given no data
    When building the dashboard
    Then there are no versions or tasks and both counters are zero
    """
    result = views.dashboard(session)

    assert not result.versions
    assert not result.doing
    assert not result.waiting
    assert result.inbox_count == 0
    assert result.refine_count == 0

def test_dashboard_only_lists_in_progress_versions(session):
    """Dashboard lists only started, unreleased versions
    Given a planned, an in-progress and a released version
    When building the dashboard
    Then only the in-progress version is listed
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "Released", ["Ships"])
    started = versions.create(session, "nexus", "0.2.0", "Started", ["Ships"])
    versions.create(session, "nexus", "0.3.0", "Planned", ["Ships"])
    released = versions.get(session, "nexus", "0.1.0")
    versions.start(session, released.id)
    versions.set_criterion_done(session, released.definition_of_done[0].id, True)
    versions.release(session, released.id)
    versions.start(session, started.id)

    result = views.dashboard(session)
    assert [p.version.number for p in result.versions] == ["0.2.0"]

def test_dashboard_version_progress(session):
    """Dashboard shows how many of a version's tasks are done
    Given a started version with two planned tasks, one of them completed
    When building the dashboard
    Then the version reports 1 done out of 2
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    finished = _refined_task(session, "Finished", version)
    _refined_task(session, "Pending", version)
    tasks.start(session, finished.id)
    tasks.complete(session, finished.id)

    [progress] = views.dashboard(session).versions
    assert (progress.done, progress.total) == (1, 2)

def test_dashboard_version_without_tasks(session):
    """Dashboard shows a started version with no tasks as 0 out of 0
    Given a started version with no tasks
    When building the dashboard
    Then the version reports 0 done out of 0
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)

    [progress] = views.dashboard(session).versions
    assert (progress.done, progress.total) == (0, 0)

def test_dashboard_progress_is_per_version(session):
    """Dashboard counts each version's tasks separately
    Given two started versions with one and two planned tasks
    When building the dashboard
    Then each version reports its own total
    """
    projects.create(session, "nexus", "Nexus", "")
    first = versions.create(session, "nexus", "0.1.0", "First", ["Ships"])
    second = versions.create(session, "nexus", "0.2.0", "Second", ["Ships"])
    versions.start(session, first.id)
    versions.start(session, second.id)
    _refined_task(session, "A", first)
    _refined_task(session, "B", second)
    _refined_task(session, "C", second)

    result = views.dashboard(session)
    assert [(p.version.number, p.total) for p in result.versions] == [("0.1.0", 1), ("0.2.0", 2)]

def test_dashboard_splits_doing_and_waiting(session):
    """Dashboard separates tasks in progress from blocked ones
    Given a doing task, a waiting task and a merely planned task
    When building the dashboard
    Then doing and waiting hold one task each, and the planned task appears in neither
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    doing = _refined_task(session, "Doing", version)
    waiting = _refined_task(session, "Waiting", version)
    _refined_task(session, "Planned", version)
    tasks.start(session, doing.id)
    tasks.start(session, waiting.id)
    tasks.block(session, waiting.id, "Waiting for review")

    result = views.dashboard(session)
    assert [t.id for t in result.doing] == [doing.id]
    assert [t.id for t in result.waiting] == [waiting.id]

def test_dashboard_counters_match_inbox_and_refine(session):
    """Dashboard counters match the inbox and refine queues
    Given two inbox tasks, one refined unplanned task and one planned task
    When building the dashboard
    Then the counters equal the lengths of inbox() and to_refine()
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    tasks.capture(session, "First")
    tasks.capture(session, "Second")
    _refined_task(session, "To plan")
    _refined_task(session, "Planned", version)

    result = views.dashboard(session)
    assert result.inbox_count == len(views.inbox(session)) == 2
    assert result.refine_count == len(views.to_refine(session)) == 1


# Limits -------------------------------------------------------------------------------------------

def test_to_refine_limit_keeps_the_oldest(session):
    """To refine with a limit returns only the oldest tasks
    Given three refined tasks
    When listing the queue with a limit of 2
    Then the two oldest are returned, oldest first
    """
    ids = [_refined_task(session, name).id for name in ("First", "Second", "Third")]

    result = views.to_refine(session, limit=2)
    assert [t.id for t in result] == ids[:2]

def test_to_refine_without_limit_returns_everything(session):
    """To refine without a limit returns the whole queue
    Given three refined tasks
    When listing the queue
    Then all three are returned
    """
    for name in ("First", "Second", "Third"):
        _refined_task(session, name)

    assert len(views.to_refine(session)) == 3

def test_search_limit_keeps_the_oldest_matches(session):
    """Search with a limit returns only the oldest matches
    Given three tasks containing 'docs'
    When searching with a limit of 2
    Then the two oldest matches are returned
    """
    ids = [tasks.capture(session, f"Docs {n}").id for n in range(3)]

    result = views.search(session, "docs", limit=2)
    assert [t.id for t in result] == ids[:2]

def test_dashboard_version_dod_progress(session):
    """Dashboard shows how many of a version's DOD criteria are checked
    Given a started version with three criteria, one of them checked
    When building the dashboard
    Then the version reports 1 checked out of 3
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships", "Docs", "Tests"])
    versions.start(session, version.id)
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)

    [progress] = views.dashboard(session).versions
    assert (progress.dod_done, progress.dod_total) == (1, 3)


def test_dashboard_progress_ignores_cancelled_tasks(session):
    """Dashboard progress leaves cancelled tasks out of the total
    Given a started version with a done task and a cancelled task
    When building the dashboard
    Then the version reports 1 done out of 1
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    finished = _refined_task(session, "Finished", version)
    dropped = _refined_task(session, "Dropped", version)
    tasks.start(session, finished.id)
    tasks.complete(session, finished.id)
    tasks.cancel(session, dropped.id)

    [progress] = views.dashboard(session).versions
    assert (progress.done, progress.total) == (1, 1)
