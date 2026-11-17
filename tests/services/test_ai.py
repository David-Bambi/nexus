import pytest

from src.models.ai import AiMode, Nature, ProjectAiDomain, ProjectAiTarget
from src.models.task import TaskState
from src.services import ai, events, projects, tasks
from src.services.errors import NotFoundError, ValidationError


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


# Context as domain ---------------------------------------------------------------------------------

def test_create_refuses_unknown_context(session, project):
    """
    Given a project
    When creating a task with a context that isn't a domain
    Then a ValidationError is raised
    """
    with pytest.raises(ValidationError):
        tasks.create(session, "Task", "nx", None, "@ordi", "S")


def test_update_keeps_legacy_context_but_refuses_new_one(session, project):
    """
    Given a task whose context was set before the domain list existed
    When updating its title, then setting another unknown context
    Then the first update passes and the second raises a ValidationError
    """
    task = tasks.create(session, "Task", "nx")
    task.context = "@ordi"
    session.commit()
    tasks.update(session, task.id, title="Renamed", context="@ordi")
    with pytest.raises(ValidationError):
        tasks.update(session, task.id, context="@atelier")


# AI mode -------------------------------------------------------------------------------------------

def test_set_ai_mode_records_the_change(session, project):
    """
    Given a task without a mode
    When setting its mode to delegated
    Then the mode is stored and an 'updated' event records it
    """
    task = tasks.create(session, "Task", "nx")
    tasks.set_ai_mode(session, task.id, AiMode.DELEGATED, actor=events.ACTOR_MCP)
    assert task.ai_mode is AiMode.DELEGATED
    event = events.history(session, "task", task.id)[-1]
    assert (event.action, event.actor) == ("updated", "mcp")
    assert event.payload == {"ai_mode": {"from": None, "to": "DELEGATED"}}


def test_set_same_ai_mode_logs_nothing(session, project):
    """
    Given a task with a mode
    When setting the same mode again
    Then no event is added
    """
    task = tasks.create(session, "Task", "nx")
    tasks.set_ai_mode(session, task.id, AiMode.GUIDED)
    count = len(events.history(session, "task", task.id))
    tasks.set_ai_mode(session, task.id, AiMode.GUIDED)
    assert len(events.history(session, "task", task.id)) == count


# Domain natures ------------------------------------------------------------------------------------

def test_natures_default_to_the_domain_list(session, project):
    """
    Given a project without its own settings
    When reading its natures
    Then every domain has its default nature
    """
    assert ai.natures(session, "nx") == {slug: nature for slug, (_, nature) in ai.DOMAINS.items()}


def test_set_domain_nature_overrides_then_returns_to_default(session, project):
    """
    Given a project
    When making 'assets' founding, then peripheral (its default) again
    Then the override exists, then is removed, and both changes are logged
    """
    ai.set_domain_nature(session, "nx", "assets", Nature.FOUNDING)
    assert ai.natures(session, "nx")["assets"] is Nature.FOUNDING
    ai.set_domain_nature(session, "nx", "assets", Nature.PERIPHERAL)
    assert ai.natures(session, "nx")["assets"] is Nature.PERIPHERAL
    assert session.query(ProjectAiDomain).count() == 0
    payloads = [e.payload for e in events.history(session, "project", project.id)
                if e.action == "ai_settings_updated"]
    assert payloads == [{"domain": "assets", "nature": {"from": "PERIPHERAL", "to": "FOUNDING"}},
                        {"domain": "assets", "nature": {"from": "FOUNDING", "to": "PERIPHERAL"}}]


def test_set_domain_nature_refuses_unknown_domain(session, project):
    """
    Given a project
    When setting the nature of a domain that doesn't exist
    Then a ValidationError is raised
    """
    with pytest.raises(ValidationError):
        ai.set_domain_nature(session, "nx", "cooking", Nature.FOUNDING)


def test_settings_of_unknown_project(session):
    """
    Given no project 'nx'
    When reading its natures
    Then a NotFoundError is raised
    """
    with pytest.raises(NotFoundError):
        ai.natures(session, "nx")


# Targets -------------------------------------------------------------------------------------------

def test_set_target_stores_logs_and_clears(session, project):
    """
    Given a project
    When setting a founding target, then clearing both bounds
    Then the target is read back, logged, then removed
    """
    ai.set_target(session, "nx", Nature.FOUNDING, 80, 0)
    assert ai.targets(session, "nx")[Nature.FOUNDING] == (80, 0)
    event = events.history(session, "project", project.id)[-1]
    assert event.payload == {"target": "FOUNDING",
                             "min_own_pct": {"from": None, "to": 80},
                             "max_dependent_pct": {"from": None, "to": 0}}
    ai.set_target(session, "nx", Nature.FOUNDING, None, None)
    assert ai.targets(session, "nx")[Nature.FOUNDING] == (None, None)
    assert session.query(ProjectAiTarget).count() == 0


@pytest.mark.parametrize("bounds", [(101, None), (None, -1)])
def test_set_target_refuses_out_of_range(session, project, bounds):
    """
    Given a project
    When setting a percentage outside 0-100
    Then a ValidationError is raised
    """
    with pytest.raises(ValidationError):
        ai.set_target(session, "nx", Nature.FOUNDING, *bounds)


def test_deleting_project_deletes_its_settings(session, project):
    """
    Given a project with a domain override and a target
    When deleting the project
    Then its AI settings are deleted too
    """
    ai.set_domain_nature(session, "nx", "assets", Nature.FOUNDING)
    ai.set_target(session, "nx", Nature.FOUNDING, 80, None)
    projects.delete(session, "nx")
    assert session.query(ProjectAiDomain).count() == 0
    assert session.query(ProjectAiTarget).count() == 0


# Profile -------------------------------------------------------------------------------------------

def test_profile_weights_modes_by_size(session, project):
    """
    Given founding done tasks: one L autonomous, one S dependent, one unsized learned
    When computing the profile
    Then shares are weighted 8 / 2 / 4 and the unsized task is reported
    """
    _done(session, "code-core", AiMode.AUTONOMOUS, "L")
    _done(session, "conception", AiMode.DEPENDENT, "S")
    _done(session, "debug", AiMode.LEARNED, None)
    result = ai.profile(session, "nx")
    founding = result.natures[0]
    assert founding.nature is Nature.FOUNDING
    assert founding.weight == 14
    assert founding.shares[AiMode.AUTONOMOUS] == pytest.approx(100 * 8 / 14)
    assert founding.own_pct == pytest.approx(100 * 12 / 14)
    assert founding.dependent_pct == pytest.approx(100 * 2 / 14)
    assert result.without_size == 1


def test_profile_counts_only_done_tasks_with_mode_and_domain(session, project):
    """
    Given a done task without mode, a done task with an unknown context, and an open task
    When computing the profile
    Then none is counted, and the first two are reported
    """
    _done(session, None, None)
    legacy = _done(session, None, AiMode.DELEGATED)
    legacy.context = "@ordi"
    tasks.create(session, "Open", "nx", None, "docs", "S")
    session.commit()
    result = ai.profile(session, "nx")
    assert all(entry.weight == 0 for entry in result.natures)
    assert (result.without_mode, result.unknown_domain) == (1, 1)


def test_profile_uses_project_natures(session, project):
    """
    Given 'assets' made founding in the project, and a delegated assets task
    When computing the profile
    Then the task counts as founding
    """
    ai.set_domain_nature(session, "nx", "assets", Nature.FOUNDING)
    _done(session, "assets", AiMode.DELEGATED)
    natures = {entry.nature: entry for entry in ai.profile(session, "nx").natures}
    assert natures[Nature.FOUNDING].shares[AiMode.DELEGATED] == 100
    assert natures[Nature.PERIPHERAL].weight == 0


def test_profile_compares_with_target(session, project):
    """
    Given a founding target of own >= 80 % and dependent <= 0 %, and 75 % own / 25 % dependent
    When computing the profile
    Then the target isn't met, with gaps of -5 and -25
    """
    ai.set_target(session, "nx", Nature.FOUNDING, 80, 0)
    _done(session, "code-core", AiMode.AUTONOMOUS, "L")
    _done(session, "code-core", AiMode.LEARNED, "M")
    _done(session, "code-core", AiMode.DEPENDENT, "M")
    founding = ai.profile(session, "nx").natures[0]
    assert founding.own_gap == pytest.approx(-5)
    assert founding.dependent_gap == pytest.approx(-25)
    assert founding.met is False


def test_profile_target_met_or_unknown(session, project):
    """
    Given a met founding target and a repetitive target with no tasks
    When computing the profile
    Then founding is met and repetitive has no verdict
    """
    ai.set_target(session, "nx", Nature.FOUNDING, 50, None)
    ai.set_target(session, "nx", Nature.REPETITIVE, None, 10)
    _done(session, "code-core", AiMode.AUTONOMOUS)
    natures = {entry.nature: entry for entry in ai.profile(session, "nx").natures}
    assert natures[Nature.FOUNDING].met is True
    assert natures[Nature.REPETITIVE].met is None
