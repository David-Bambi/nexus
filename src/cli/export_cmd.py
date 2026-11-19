import json
from pathlib import Path
from typing import TextIO

from sqlalchemy.orm import Session

from src.cli import commands
from src.cli.errors import UsageError, UsageParser
from src.services import export


def export_data(session : Session, args : list[str], out : TextIO) -> None:
    """`nexus export features [-o FILE]`: write the feature export as JSON.

    The export is the stable contract read by the metrique project (see
    services/export.features). It goes to stdout unless a file is given.

    Args:
        session: Database session to use.
        args: Arguments after `export`.
        out: Stream receiving the JSON, or the confirmation with -o.

    Raises:
        UsageError: If the command line is malformed or the file can't be written.
    """
    parser = UsageParser(prog="nexus export", add_help=False)
    parser.add_argument("what", choices=["features"])
    parser.add_argument("-o", "--output")
    options = parser.parse_args(args)

    data = export.features(session)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if options.output is None:
        print(text, file=out)
        return
    try:
        Path(options.output).write_text(text + "\n", encoding="utf-8")
    except OSError as error:
        raise UsageError(f"cannot write '{options.output}': {error.strerror}") from error
    print(f"Exported {len(data['features'])} feature(s) to {options.output} ({data['schema']}).", file=out)


commands.COMMANDS["export"] = export_data
