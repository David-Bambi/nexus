import subprocess

import pytest

from src import git_history


def _git(repo, *args):
    """Run git in the test repository."""
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A repository with a commit by hand, then one co-signed by Claude touching a binary file."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "dev@example.com")
    _git(tmp_path, "config", "user.name", "Dev")
    (tmp_path / "main.py").write_text("a\nb\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "By hand")
    (tmp_path / "main.py").write_text("a\nb\nc\n")
    (tmp_path / "logo.bin").write_bytes(b"\x00\x01\x02")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "With Claude\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    return tmp_path


def test_commits_reads_messages_and_added_lines_newest_first(repo):
    """Each commit comes with its message and its text files' added lines; binary files are left out."""
    newest, oldest = git_history.commits(str(repo))
    assert "Co-Authored-By: Claude" in newest.message and newest.files == [("main.py", 1)]
    assert oldest.message.strip() == "By hand" and oldest.files == [("main.py", 2)]
    assert git_history.head(str(repo)) == newest.sha


def test_a_folder_that_is_not_a_repository_reads_as_none(tmp_path):
    """No repository, or no folder at all: nothing is read."""
    assert git_history.head(str(tmp_path)) is None
    assert git_history.commits(str(tmp_path / "missing")) is None
