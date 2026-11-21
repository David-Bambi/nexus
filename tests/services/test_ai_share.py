import pytest

from src import git_history
from src.models.project import Project
from src.services import ai_share


@pytest.mark.parametrize("path, expected", [
    ("src/app.py", "code"),
    ("scripts/run.gd", "code"),
    ("tests/web/test_pages.py", "tests"),
    ("test/unit.gd", "tests"),
    ("src/test_helpers.py", "tests"),
    ("grid/hex_test.gd", "tests"),
    ("docs/index.md", "docs"),
    ("docs/concept/nexus/etats.svg", "docs"),
    ("README.md", "docs"),
    ("notes/arbre.cpt", "docs"),
    ("uv.lock", None),
    ("docs/concept/nexus/journal/journal.layout.json", None),
])
def test_category_sorts_files(path, expected):
    """Files go to code, tests or docs by folder and name; generated files are left out."""
    assert ai_share.category(path) == expected


def test_shares_count_co_signed_commits_for_the_ai():
    """
    Given a co-signed commit and one by hand, touching code, tests, docs and a lock file
    When counting the shares
    Then each category adds its lines, the co-signed ones for the AI, the lock file ignored
    """
    commits = [
        git_history.Commit("a", "Add\n\nco-authored-by: claude opus <x@y>", [("src/a.py", 30), ("tests/test_a.py", 10)]),
        git_history.Commit("b", "By hand", [("src/a.py", 10), ("README.md", 5), ("uv.lock", 900)]),
    ]
    code, tests, docs = ai_share.shares(commits)
    assert (code.category, code.ai_lines, code.total_lines, code.percent) == ("code", 30, 40, 75)
    assert (tests.percent, docs.percent, docs.total_lines) == (100, 0, 5)


def test_a_category_with_no_lines_is_zero_percent():
    """Nothing added: 0 %, not a division error."""
    assert ai_share.CategoryShare("docs", 0, 0).percent == 0


def test_of_project_needs_its_own_directory_and_reuses_the_count_while_head_stays(monkeypatch):
    """
    Given a project without a directory, then one with a directory
    When asking twice for its share with the same head
    Then the first gives nothing, the second reads the history once
    """
    reads = []
    monkeypatch.setattr(git_history, "head", lambda directory: "h1")
    monkeypatch.setattr(git_history, "commits",
                        lambda directory: reads.append(directory) or [git_history.Commit("a", "x", [("a.py", 1)])])
    monkeypatch.setattr(ai_share, "_cache", {})

    assert ai_share.of_project(Project(key="sub", name="Sub")) is None
    project = Project(key="nx", name="Nexus", directory="/repo")
    assert ai_share.of_project(project)[0].total_lines == 1
    ai_share.of_project(project)
    assert reads == ["/repo"]


def test_of_project_outside_a_repository_is_none(monkeypatch):
    """A directory that isn't a git repository gives nothing."""
    monkeypatch.setattr(git_history, "head", lambda directory: None)
    assert ai_share.of_project(Project(key="nx", name="Nexus", directory="/nowhere")) is None
