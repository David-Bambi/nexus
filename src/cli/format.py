def table(headers : list[str], rows : list[list[str]]) -> str:
    """Lay rows out as left-aligned columns.

    Args:
        headers: Column titles.
        rows: One list of cell strings per row, as many cells as headers.

    Returns:
        The table as text, or "(none)" when there are no rows.
    """
    if not rows:
        return "(none)"
    widths = [max(len(cell) for cell in column) for column in zip(headers, *rows)]
    lines = ["  ".join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip()
             for line in [headers, *rows]]
    return "\n".join(lines)


def detail(fields : list[tuple[str, str | None]]) -> str:
    """Lay out labelled fields, one per line, values aligned.

    Args:
        fields: (label, value) pairs; pairs whose value is None or empty are
            left out.

    Returns:
        The fields as text.
    """
    shown = [(label, value) for label, value in fields if value]
    width = max((len(label) for label, _ in shown), default=0)
    return "\n".join(f"{label.ljust(width)}  {value}" for label, value in shown)


def section(title : str, body : str) -> str:
    """Put a titled block after a blank line.

    Args:
        title: Section heading.
        body: Section content.
    """
    return f"\n{title}\n{body}"
