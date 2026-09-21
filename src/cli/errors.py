import argparse
from typing import NoReturn


class UsageError(Exception):
    """The command line itself is wrong (unknown command, missing argument).

    Distinct from the domain errors of services/, which mean valid input met
    a rule of the data; the CLI reports the two with different exit codes.
    """


class UsageParser(argparse.ArgumentParser):
    """Argument parser that reports mistakes as a UsageError instead of exiting."""

    def error(self, message : str) -> NoReturn:
        """Raise the parsing mistake as a UsageError."""
        raise UsageError(message)
