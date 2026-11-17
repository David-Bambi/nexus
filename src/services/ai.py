from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from src.models.ai import AiMode, Nature, ProjectAiDomain, ProjectAiTarget
from src.models.task import Task, TaskState
from src.services import events, projects
from src.services.errors import ValidationError

# Every work domain a task can belong to: slug -> (label, default nature).
# A task's domain is stored in its context field.
DOMAINS: dict[str, tuple[str, Nature]] = {
    "exploration": ("Exploration and brainstorming", Nature.FOUNDING),
    "conception": ("Design and architecture", Nature.FOUNDING),
    "code-core": ("Code: core logic", Nature.FOUNDING),
    "code-repetitive": ("Code: repetitive cases, glue", Nature.REPETITIVE),
    "tests-design": ("Tests: what to test", Nature.FOUNDING),
    "tests-variants": ("Tests: writing variants", Nature.REPETITIVE),
    "debug": ("Debugging", Nature.FOUNDING),
    "comments": ("Code comments", Nature.FOUNDING),
    "examples": ("Examples", Nature.FOUNDING),
    "translation": ("Translation", Nature.PERIPHERAL),
    "docs": ("Documentation and guides", Nature.PERIPHERAL),
    "readme": ("README", Nature.PERIPHERAL),
    "project-mgmt": ("Project management", Nature.PERIPHERAL),
    "assets": ("Graphic assets", Nature.PERIPHERAL),
    "tools": ("Tools (scripts, hooks)", Nature.PERIPHERAL),
    "versioning": ("Versioning and releases", Nature.PERIPHERAL),
}

# Symbol and label of each AI mode, for display.
MODE_LABELS: dict[AiMode, tuple[str, str]] = {
    AiMode.AUTONOMOUS: ("✋", "Autonomous"),
    AiMode.LEARNED: ("📚", "Learned"),
    AiMode.DELEGATED: ("✅", "Delegated"),
    AiMode.GUIDED: ("⚠️", "Guided"),
    AiMode.DEPENDENT: ("🔴", "Dependent"),
}

# Label of each nature, for display.
NATURE_LABELS: dict[Nature, str] = {
    Nature.FOUNDING: "Founding",
    Nature.REPETITIVE: "Repetitive",
    Nature.PERIPHERAL: "Peripheral",
}

# Weight of each task size in the profile.
SIZE_WEIGHTS = {"XS": 1, "S": 2, "M": 4, "L": 8}

# Weight of a task without a size (counted as M).
DEFAULT_WEIGHT = SIZE_WEIGHTS["M"]

@dataclass(frozen=True)
class SizeGuide:
    """What a task size means, from the task-size guide."""

    # One-line summary, shown in size lists.
    short: str
    # When to choose this size.
    when: str
    # A typical Nexus task of this size.
    example: str


# Meaning of each task size, in the order of SIZE_WEIGHTS.
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

# Modes where David executed the work himself.
OWN_MODES = (AiMode.AUTONOMOUS, AiMode.LEARNED)


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

def require_domain(context : str | None) -> None:
    """Check that a task context is one of the known domains.

    Args:
        context: The context to check; None (no context) is accepted.

    Raises:
        ValidationError: If the context isn't a known domain slug.
    """
    if context is not None and context not in DOMAINS:
        raise ValidationError(f"context '{context}' isn't a known domain "
                              f"(expected one of: {', '.join(DOMAINS)}).")


def _require_pct(name : str, value : int | None) -> None:
    """Check that an optional percentage is between 0 and 100.

    Raises:
        ValidationError: If the value is set and out of range.
    """
    if value is not None and not 0 <= value <= 100:
        raise ValidationError(f"{name} must be between 0 and 100.")


# -----------------------------------------------------------------------------
# Project settings
# -----------------------------------------------------------------------------

def natures(session : Session, key : str) -> dict[str, Nature]:
    """Give the nature of every domain in a project.

    Args:
        session: Database session to use.
        key: Key of the project.

    Returns:
        Every domain slug, in the order of DOMAINS, mapped to the project's own
        nature for it, or to the default nature if the project has none.

    Raises:
        NotFoundError: If no project has this key.
    """
    project = projects.get(session, key)
    overrides = {row.domain: row.nature for row in project.ai_domains}
    return {slug: overrides.get(slug, default) for slug, (_, default) in DOMAINS.items()}


def set_domain_nature(session : Session, key : str, domain : str, nature : Nature,
                      actor : str = events.ACTOR_WEB) -> None:
    """Set the nature of one domain in a project.

    Setting the default nature removes the project's own value.

    Args:
        session: Database session to use.
        key: Key of the project.
        domain: Domain slug.
        nature: The domain's nature in this project.
        actor: Who made the change, recorded in the event log.

    Raises:
        NotFoundError: If no project has this key.
        ValidationError: If the domain is unknown.
    """
    project = projects.get(session, key)
    if domain not in DOMAINS:
        raise ValidationError(f"domain '{domain}' doesn't exist.")

    row = next((r for r in project.ai_domains if r.domain == domain), None)
    previous = row.nature if row else DOMAINS[domain][1]
    if previous == nature:
        return

    if nature == DOMAINS[domain][1]:
        project.ai_domains.remove(row)
    elif row is None:
        project.ai_domains.append(ProjectAiDomain(domain=domain, nature=nature))
    else:
        row.nature = nature

    events.log(session, actor, "project", project.id, "ai_settings_updated",
               {"domain": domain, "nature": {"from": previous.name, "to": nature.name}})
    session.commit()


def targets(session : Session, key : str) -> dict[Nature, tuple[int | None, int | None]]:
    """Give a project's targets on its AI usage profile.

    Args:
        session: Database session to use.
        key: Key of the project.

    Returns:
        Every nature mapped to (min_own_pct, max_dependent_pct); a bound is None
        when the project sets none.

    Raises:
        NotFoundError: If no project has this key.
    """
    project = projects.get(session, key)
    rows = {row.nature: row for row in project.ai_targets}
    return {nature: ((rows[nature].min_own_pct, rows[nature].max_dependent_pct) if nature in rows
                     else (None, None))
            for nature in Nature}


def set_target(session : Session, key : str, nature : Nature, min_own_pct : int | None,
               max_dependent_pct : int | None, actor : str = events.ACTOR_WEB) -> None:
    """Set a project's target for one nature.

    Args:
        session: Database session to use.
        key: Key of the project.
        nature: The nature the target applies to.
        min_own_pct: Minimum % of autonomous + learned work, or None for no minimum.
        max_dependent_pct: Maximum % of dependent work, or None for no maximum.
        actor: Who made the change, recorded in the event log.

    Raises:
        NotFoundError: If no project has this key.
        ValidationError: If a percentage is out of 0-100.
    """
    project = projects.get(session, key)
    _require_pct("min_own_pct", min_own_pct)
    _require_pct("max_dependent_pct", max_dependent_pct)

    row = next((r for r in project.ai_targets if r.nature == nature), None)
    previous = (row.min_own_pct, row.max_dependent_pct) if row else (None, None)
    if previous == (min_own_pct, max_dependent_pct):
        return

    if min_own_pct is None and max_dependent_pct is None:
        project.ai_targets.remove(row)
    elif row is None:
        project.ai_targets.append(ProjectAiTarget(nature=nature, min_own_pct=min_own_pct,
                                                  max_dependent_pct=max_dependent_pct))
    else:
        row.min_own_pct = min_own_pct
        row.max_dependent_pct = max_dependent_pct

    changes = {name: {"from": old, "to": new}
               for name, old, new in (("min_own_pct", previous[0], min_own_pct),
                                      ("max_dependent_pct", previous[1], max_dependent_pct))
               if old != new}
    events.log(session, actor, "project", project.id, "ai_settings_updated",
               {"target": nature.name, **changes})
    session.commit()


# -----------------------------------------------------------------------------
# Profile
# -----------------------------------------------------------------------------

@dataclass
class NatureProfile:
    """AI usage of one nature in a project, weighted by task size."""

    nature: Nature
    # Total weight of the counted tasks (done, with a mode and a known domain).
    weight: int = 0
    # Weighted share (0-100) of each mode; every mode is present.
    shares: dict[AiMode, float] = field(default_factory=lambda: {mode: 0.0 for mode in AiMode})
    # Target bounds; None when the project sets none.
    min_own_pct: int | None = None
    max_dependent_pct: int | None = None

    @property
    def own_pct(self) -> float:
        """Share of autonomous + learned work."""
        return sum(self.shares[mode] for mode in OWN_MODES)

    @property
    def dependent_pct(self) -> float:
        """Share of dependent work."""
        return self.shares[AiMode.DEPENDENT]

    @property
    def has_target(self) -> bool:
        """True if the project sets at least one bound for this nature."""
        return self.min_own_pct is not None or self.max_dependent_pct is not None

    @property
    def own_gap(self) -> float | None:
        """Own share minus its minimum: negative when short; None without a minimum or tasks."""
        if self.min_own_pct is None or not self.weight:
            return None
        return self.own_pct - self.min_own_pct

    @property
    def dependent_gap(self) -> float | None:
        """Dependent maximum minus its share: negative when over; None without a maximum or tasks."""
        if self.max_dependent_pct is None or not self.weight:
            return None
        return self.max_dependent_pct - self.dependent_pct

    @property
    def met(self) -> bool | None:
        """True if every bound is respected; None without a target or counted tasks."""
        gaps = [gap for gap in (self.own_gap, self.dependent_gap) if gap is not None]
        return all(gap >= 0 for gap in gaps) if gaps else None


@dataclass
class SizeShare:
    """How much one task size weighs in a project's profile."""

    # Counted done tasks of this size.
    count: int = 0
    # Their total weight.
    weight: int = 0
    # Their share (0-100) of the weight of all counted tasks.
    share: float = 0.0


@dataclass
class Profile:
    """AI usage profile of a project, from its done tasks."""

    project_key: str
    # One entry per nature, in the order of Nature.
    natures: list[NatureProfile]
    # Done tasks left out because they have no mode.
    without_mode: int = 0
    # Done tasks left out because their context isn't a known domain.
    unknown_domain: int = 0
    # Counted done tasks without a size (weighed as M).
    without_size: int = 0
    # Weight of each size among counted tasks, in the order of SIZE_WEIGHTS;
    # the key None groups tasks without a size.
    by_size: dict[str | None, SizeShare] = field(
        default_factory=lambda: {size: SizeShare() for size in [*SIZE_WEIGHTS, None]})


def profile(session : Session, key : str) -> Profile:
    """Compute a project's AI usage profile.

    Only done tasks count. A task needs a mode and a known domain to be counted;
    its weight comes from its size (XS=1, S=2, M=4, L=8, none = M).

    Args:
        session: Database session to use.
        key: Key of the project.

    Returns:
        The profile, with each nature's mode shares and target.

    Raises:
        NotFoundError: If no project has this key.
    """
    project = projects.get(session, key)
    domain_natures = natures(session, key)
    bounds = targets(session, key)
    by_nature = {nature: NatureProfile(nature, min_own_pct=bounds[nature][0],
                                       max_dependent_pct=bounds[nature][1])
                 for nature in Nature}
    weights = {nature: {mode: 0 for mode in AiMode} for nature in Nature}
    result = Profile(project.key, list(by_nature.values()))

    done = session.query(Task).filter(Task.project_id == project.id, Task.state == TaskState.DONE)
    for task in done:
        if task.ai_mode is None:
            result.without_mode += 1
            continue
        if task.context not in domain_natures:
            result.unknown_domain += 1
            continue
        size = task.size if task.size in SIZE_WEIGHTS else None
        if size is None:
            result.without_size += 1
        weight = SIZE_WEIGHTS.get(size, DEFAULT_WEIGHT)
        weights[domain_natures[task.context]][task.ai_mode] += weight
        result.by_size[size].count += 1
        result.by_size[size].weight += weight

    for nature, entry in by_nature.items():
        entry.weight = sum(weights[nature].values())
        if entry.weight:
            entry.shares = {mode: 100 * w / entry.weight for mode, w in weights[nature].items()}
    total = sum(entry.weight for entry in by_nature.values())
    if total:
        for entry in result.by_size.values():
            entry.share = 100 * entry.weight / total
    return result
