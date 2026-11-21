from dataclasses import dataclass


@dataclass(frozen=True)
class SizeGuide:
    """What a task size means, from the task-size guide."""

    # One-line summary, shown in size lists.
    short: str
    # When to choose this size.
    when: str
    # A typical Nexus task of this size.
    example: str


# Meaning of each task size, from the smallest to the biggest.
SIZE_GUIDE: dict[str, SizeGuide] = {
    "XS": SizeGuide("trivial change in one place, no decision",
                    "Trivial change in one place, no decision.",
                    "Fix a typo or a label, change a config value."),
    "S": SizeGuide("small change you understand, one layer, with its test",
                   "Small change you already understand, in one layer, with its test.",
                   "Add a field to a form; an MCP tool wrapping an existing service."),
    "M": SizeGuide("several layers, or a small design decision; clear path",
                   "Feature across several layers (model, service, page, tests), or with a small "
                   "design decision. Clear path.",
                   "Add a project setting and its form."),
    "L": SizeGuide("new concept or open questions; several sessions",
                   "New concept or open questions: needs design and several work sessions.",
                   "A new entity with its migration, service, pages and docs."),
}

# Rules for choosing a size, from the task-size guide.
SIZE_RULES = (
    "When you hesitate between two sizes, take the bigger one.",
    "A task bigger than L is split.",
    "A task mixing defining and doing is split too.",
)
