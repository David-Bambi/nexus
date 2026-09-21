"""Full-page routes, split by area; all share the one ``pages`` blueprint."""

from src.web.pages._shared import bp

# Importing the modules registers their routes on ``bp``.
from src.web.pages import inbox, projects, tasks, versions  # noqa: E402,F401

__all__ = ["bp"]
