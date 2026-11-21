import re

import pytest

from src.models.project import Project
from src.models.task import Task, TaskKind
from src.services import projects, refs, resolve, tasks
from src.services.errors import NotFoundError, ValidationError


def _subproject(session, key="bilan", ref="s-abc"):
    """Insert a root project "metrique" and a subproject under it."""
    root = Project(key="metrique", name="Métriques")
    session.add(root)
    session.flush()
    sub = Project(key=key, name=key, ref=ref, parent_id=root.id)
    session.add(sub)
    session.commit()
    return sub


def _item(session, ref, kind=TaskKind.TASK):
    """Insert a work item with a given ref and kind."""
    item = Task(ref=ref, kind=kind, title=ref)
    session.add(item)
    session.commit()
    return item


def test_generate_formats_ref_with_prefix(session):
    """
    Given an empty database
    When refs are generated for a subproject, a feature and a task
    Then they are prefixed "s-" / "f-" / "t-" followed by a base36 code
    """
    assert re.fullmatch(r"s-[0-9a-z]{3}", refs.generate(session, refs.SUBPROJECT))
    assert re.fullmatch(r"f-[0-9a-z]{3}", refs.generate(session, refs.KIND_PREFIXES[TaskKind.FEATURE]))
    assert re.fullmatch(r"t-[0-9a-z]{3}", refs.generate(session, refs.KIND_PREFIXES[TaskKind.TASK]))


def test_generate_retries_on_collision(session, monkeypatch):
    """
    Given a task already holding the first candidate code
    When a task ref is generated
    Then the taken candidate is skipped
    """
    candidates = iter("aaabbb")
    monkeypatch.setattr(refs.secrets, "choice", lambda _alphabet: next(candidates))
    _item(session, "t-aaa")
    assert refs.generate(session, "t") == "t-bbb"


def test_features_and_tasks_share_one_code_namespace(session, monkeypatch):
    """
    Given a task holding code "aaa"
    When a feature ref is generated and the first candidate is "aaa"
    Then "f-aaa" is refused, since it would name the same code
    """
    candidates = iter("aaabbb")
    monkeypatch.setattr(refs.secrets, "choice", lambda _alphabet: next(candidates))
    _item(session, "t-aaa")
    assert refs.generate(session, "f") == "f-bbb"


def test_subprojects_have_their_own_namespace(session, monkeypatch):
    """
    Given a task holding code "aaa"
    When a subproject ref is generated and the first candidate is "aaa"
    Then "s-aaa" is accepted
    """
    candidates = iter("aaa")
    monkeypatch.setattr(refs.secrets, "choice", lambda _alphabet: next(candidates))
    _item(session, "t-aaa")
    assert refs.generate(session, refs.SUBPROJECT) == "s-aaa"


def test_generate_widens_code_when_crowded(session, monkeypatch):
    """
    Given a namespace where every short candidate collides
    When a ref is generated
    Then the code grows by one character after repeated collisions
    """
    monkeypatch.setattr(refs, "_is_taken", lambda _s, _p, code: len(code) == 3)
    assert len(refs.generate(session, "t")) == len("t-abcd")


@pytest.mark.parametrize("text, expected", [
    ("s-4k2", True), ("F-4K2", True), (" t-4k2 ", True), ("t-4k2x", True),
    ("v-4k2", False), ("t-4k", False), ("nexus", False), ("t4k2", False),
])
def test_is_ref(text, expected):
    """
    Given a string
    When asking whether it is shaped like a ref
    Then only s-/f-/t- followed by 3+ base36 characters match
    """
    assert refs.is_ref(text) is expected


def test_with_kind_keeps_the_code():
    """
    Given a task ref
    When respelled for a feature
    Then only the prefix changes
    """
    assert refs.with_kind("t-4k2", TaskKind.FEATURE) == "f-4k2"
    assert refs.with_kind("f-4k2", TaskKind.TASK) == "t-4k2"


def test_get_by_ref_finds_an_item_under_either_prefix(session):
    """
    Given a feature stored as "f-abc"
    When looked up as "f-abc", "T-ABC" or " t-abc "
    Then the feature is found each time
    """
    feature = _item(session, "f-abc", TaskKind.FEATURE)
    for spelling in ("f-abc", "T-ABC", " t-abc "):
        assert tasks.get_by_ref(session, spelling) is feature


def test_get_by_ref_unknown_raises(session):
    """
    Given an empty database
    When looking up an unknown or malformed item ref
    Then a not-found error is raised
    """
    for ref in ("t-zzz", "s-zzz", "nexus"):
        with pytest.raises(NotFoundError):
            tasks.get_by_ref(session, ref)
    with pytest.raises(NotFoundError):
        projects.get_by_ref(session, "s-zzz")


def test_projects_get_by_ref_finds_a_subproject(session):
    """
    Given a subproject "s-abc"
    When looked up by ref, in any letter case
    Then it is returned
    """
    sub = _subproject(session)
    assert projects.get_by_ref(session, " S-ABC ") is sub


def test_resolve_names_each_kind(session):
    """
    Given a project, a subproject, a feature and a task
    When each reference is resolved
    Then the target kind follows the row
    """
    sub = _subproject(session)
    feature = _item(session, "f-fff", TaskKind.FEATURE)
    task = _item(session, "t-ttt")

    assert resolve.resolve(session, "metrique").kind == "project"
    assert resolve.resolve(session, "s-abc").entity is sub
    assert resolve.resolve(session, "s-abc").kind == "subproject"
    assert resolve.resolve(session, "f-fff").entity is feature
    assert resolve.resolve(session, "t-fff").kind == "feature"
    assert resolve.resolve(session, "t-ttt").entity is task
    assert resolve.resolve(session, "t-ttt").kind == "task"


@pytest.mark.parametrize("key", ["s-abc", "f-abc", "t-abc"])
def test_project_keys_shaped_like_refs_are_refused(session, key):
    """
    Given a key shaped like a subproject, feature or task ref
    When creating a project with it
    Then a validation error is raised
    """
    with pytest.raises(ValidationError):
        projects.create(session, key, "Name")
