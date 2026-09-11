# Technical Spec — Documentation System v0

**Working name:** Milestone docs
**Type:** local static documentation site (MkDocs)
**Date:** 2026-09-11
**Status:** approved for implementation

---

## 1. Objective

Give the project a single browsable, generated site — not a wiki, not
hand-copied duplication of what already lives in the repo. Four things must
be visible from a browser:

1. **Decision journal** — every ADR, one page each.
2. **Code reference** — the `src/` tree, navigable.
3. **Python docstrings** — rendered inline on each reference page.
4. **Architectural documents** — diagrams tying the pieces together.

### Success criterion

`mkdocs serve` renders all four, live-reloading on edits to `docs/` or to
source docstrings, with zero hand-written HTML.

---

## 2. Scope

### Included in v0

| Domain | Content |
|---|---|
| ADR pages | One Markdown file per decision, under Architecture |
| Architecture overview | Mermaid diagrams (ER, state machine) |
| Code reference | Nav auto-generated from `src/`, one page per module |
| Docstrings | Rendered via mkdocstrings — never copied by hand |
| Serving | `mkdocs serve`, local dev port |

### Excluded from v0

Docs served by the Flask app (already excluded from Milestone V1 —
`specs/milestone-app-v1.md` §2). In-site search beyond MkDocs' default.
Versioned/multi-version docs (`mike`). Public hosting or deploy.
`docs/journal/` — depends on Milestone's event log
(`services/events.changelog()`), which doesn't exist yet (see
`specs/milestone-app-v1.md` §12, increment 0.5.0). Wire it up once that
ships.

---

## 3. Architecture decisions

### ADR-D1 — MkDocs + Material, no other generator

Already fixed in `specs/milestone-app-v1.md` §11. Markdown source, no build
step beyond `mkdocs build`; Material renders Mermaid, admonitions, and tabs
natively via `pymdownx.superfences`.

### ADR-D2 — `reference/` is generated, never hand-written

`mkdocs-gen-files` + `mkdocs-literate-nav` build the nav tree from `src/`
at build time; `mkdocstrings` renders each module's docstrings.
**Why:** a hand-maintained mirror of `src/` rots the first time a file is
renamed. Generated, it can't drift.

### ADR-D3 — One file per decision, not embedded in prose

`docs/architecture/adr/NNNN-title.md`, numbered sequentially, with a status
field (`proposed` / `accepted` / `superseded`). `specs/*.md` may still
narrate decisions, but the ADR file is canonical and addressable by its own
URL.

### ADR-D4 — The doc site is not served by the app

`mkdocs serve` / `mkdocs build` run as a separate process; nothing under
`src/web/` renders documentation. Matches the V1 exclusion in
`specs/milestone-app-v1.md` §2 — no coupling to keep alive.

---

## 4. Structure

```
docs/
├── index.md
├── architecture/
│   ├── overview.md
│   └── adr/
│       ├── 0001-services-ignore-http.md
│       ├── 0002-append-only-event-log.md
│       ├── 0003-flask-jinja-htmx.md
│       └── 0004-localhost-only.md
└── reference/            # generated at build time — see ADR-D2
mkdocs.yml
scripts/gen_ref_nav.py    # gen-files hook driving reference/
```

---

## 5. Tooling

`mkdocs`, `mkdocs-material`, `mkdocstrings[python]`, `mkdocs-gen-files`,
`mkdocs-literate-nav`. Add as dev dependencies:

```bash
uv add --dev mkdocs mkdocs-material "mkdocstrings[python]" mkdocs-gen-files mkdocs-literate-nav
```

---

## 6. Commands

```bash
uv run mkdocs serve   # local dev server, live reload
uv run mkdocs build   # static site to site/, not committed
```

---

## 7. Increments

| Version | Content | Definition of done |
|---|---|---|
| **0.1.0** | Skeleton: `mkdocs.yml`, Material theme, `index.md` | `mkdocs serve` renders a homepage |
| **0.2.0** | Architecture: `overview.md` with the ER + state diagrams, ADR folder with the 4 existing decisions | Architecture nav shows overview + 4 ADR pages |
| **0.3.0** | Code reference: gen-files + literate-nav + mkdocstrings wired to `src/` | Every module in `src/` has a reference page with rendered docstrings |
| **1.0.0** | All four pillars browsable from one nav; README links to it | A cold `uv sync && uv run mkdocs serve` shows decisions, architecture, and code reference with no manual step |

---

## 8. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| `reference/` drifts from `src/` | Stale docs nobody trusts | Generated at build time (ADR-D2), never hand-edited |
| New decisions get written as prose in `specs/*.md` instead of a new ADR file | Decision journal falls out of date again | Every new architectural decision starts as a file in `docs/architecture/adr/`; `specs/` only links to it — already done for the first 4 (see `specs/milestone-app-v1.md` §3) |
| Doc site becomes a second source of truth alongside `specs/` | Conflicting guidance | `CLAUDE.md` already states `docs/`, not `specs/`, is the source of truth |
