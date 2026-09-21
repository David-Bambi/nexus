from typing import Callable, TextIO

from sqlalchemy.orm import Session

from src.cli.resolve import Target

# A named command: (session, arguments after the command name, output stream).
Command = Callable[[Session, list[str], TextIO], None]

# A viewer for a resolved reference: (session, target, arguments after the
# reference, output stream).
Viewer = Callable[[Session, Target, list[str], TextIO], None]

# Commands by the word that invokes them, e.g. "tasks" or "add".
COMMANDS : dict[str, Command] = {}

# Detail viewers by target kind, for `nexus <reference>`.
VIEWERS : dict[str, Viewer] = {}
