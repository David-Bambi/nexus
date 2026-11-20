import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from src import git_history
from src.models.project import Project


# Categories, in display order.
CATEGORIES = ("code", "tests", "docs")

# A commit made with Claude carries this trailer (any case).
_CLAUDE_TRAILER = re.compile(r"^co-authored-by:\s*claude\b", re.IGNORECASE | re.MULTILINE)

# Files that are generated, not written: their lines don't count.
_GENERATED_SUFFIXES = (".lock", ".layout.json")

# Extensions of documentation files.
_DOC_SUFFIXES = (".md", ".cpt")

# Last result per repository folder: (head hash, shares), reused while the
# head doesn't move.
_cache : dict = {}


@dataclass
class CategoryShare:
    """Lines added in one category of files, and how many came with Claude."""

    # "code", "tests" or "docs".
    category: str
    # Lines added in commits co-signed by Claude.
    ai_lines: int
    # All lines added.
    total_lines: int

    @property
    def percent(self) -> int:
        """The AI share, rounded to a whole percent (0 when nothing was added)."""
        return round(100 * self.ai_lines / self.total_lines) if self.total_lines else 0


def category(path : str) -> str | None:
    """Sort a file into code, tests or docs.

    Args:
        path: Path of the file, relative to the repository.

    Returns:
        "tests" under test/ or tests/, or named test_* or *_test; "docs"
        under docs/ or in Markdown or Concept; None for a generated file
        (*.lock, *.layout.json); "code" otherwise.
    """
    file = PurePosixPath(path)
    name = file.name.lower()
    if name.endswith(_GENERATED_SUFFIXES):
        return None
    folders = {part.lower() for part in file.parts[:-1]}
    if folders & {"test", "tests"} or name.startswith("test_") or file.stem.lower().endswith("_test"):
        return "tests"
    if "docs" in folders or name.endswith(_DOC_SUFFIXES):
        return "docs"
    return "code"


def is_ai(commit : git_history.Commit) -> bool:
    """Tell whether a commit was made with Claude (co-signed by it)."""
    return bool(_CLAUDE_TRAILER.search(commit.message))


def shares(commits : list[git_history.Commit]) -> list[CategoryShare]:
    """Add up the lines of each category, and the ones made with Claude.

    A co-signed commit counts entirely for the AI.

    Args:
        commits: The commits to count.

    Returns:
        One CategoryShare per category, in CATEGORIES order.
    """
    totals = {name: CategoryShare(name, 0, 0) for name in CATEGORIES}
    for commit in commits:
        made_with_ai = is_ai(commit)
        for path, added in commit.files:
            name = category(path)
            if name is None:
                continue
            totals[name].total_lines += added
            if made_with_ai:
                totals[name].ai_lines += added
    return [totals[name] for name in CATEGORIES]


def of_project(project : Project) -> list[CategoryShare] | None:
    """The AI share of a project's repository, per category.

    Only a project with its own directory has one: a subproject that uses
    its root's folder shows nothing.

    Args:
        project: The project or subproject.

    Returns:
        The shares, or None if the project has no directory of its own or
        its folder isn't a readable git repository.
    """
    if not project.directory:
        return None
    current = git_history.head(project.directory)
    if current is None:
        return None
    cached = _cache.get(project.directory)
    if cached and cached[0] == current:
        return cached[1]
    commits = git_history.commits(project.directory)
    if commits is None:
        return None
    result = shares(commits)
    _cache[project.directory] = (current, result)
    return result
