import subprocess
from dataclasses import dataclass, field


# Longest a git command may run, in seconds, before the read gives up.
GIT_TIMEOUT = 10

# Separators put in git's log format, unlikely to appear in a message.
_RECORD = "\x1e"
_FIELD = "\x1f"


@dataclass
class Commit:
    """One commit of a repository, as far as line counts go."""

    # Full commit hash.
    sha: str
    # Full commit message, trailers included.
    message: str
    # (path, lines added) per text file touched; binary files are left out.
    files: list = field(default_factory=list)


def _git(directory : str, *args : str) -> str | None:
    """Run a git command in a folder and return its output.

    Args:
        directory: Folder to run git in.
        *args: Arguments after `git`.

    Returns:
        The standard output, or None if git is missing, fails (e.g. the
        folder isn't a repository or doesn't exist) or takes too long.
    """
    try:
        result = subprocess.run(["git", "-C", directory, *args], capture_output=True, text=True,
                                timeout=GIT_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def head(directory : str) -> str | None:
    """The hash of a repository's current commit.

    Args:
        directory: Folder of the repository.

    Returns:
        The hash, or None if the folder isn't a git repository with a commit.
    """
    output = _git(directory, "rev-parse", "HEAD")
    return output.strip() if output else None


def commits(directory : str) -> list[Commit] | None:
    """Read every non-merge commit of a repository with its added lines.

    Args:
        directory: Folder of the repository.

    Returns:
        The commits, newest first, or None if the history can't be read.
    """
    output = _git(directory, "log", "--no-merges", "--no-renames", "--numstat",
                  f"--format={_RECORD}%H{_FIELD}%B{_FIELD}")
    if output is None:
        return None
    found = []
    for record in output.split(_RECORD)[1:]:
        sha, message, stats = record.split(_FIELD, 2)
        commit = Commit(sha=sha, message=message)
        for line in stats.splitlines():
            parts = line.split("\t")
            # A binary file shows "-" instead of counts.
            if len(parts) == 3 and parts[0].isdigit():
                commit.files.append((parts[2], int(parts[0])))
        found.append(commit)
    return found
