# Implement documentation-v0.md (increments 0.1.0, 0.2.0, scaffold 0.3.0)

## Context

`artifacts/specs/documentation-v0.md` is "approved for implementation" but
nothing exists yet: no `mkdocs.yml`, no `docs/index.md`, no
`docs/architecture/overview.md`, no `docs/reference/`, no `scripts/`. Only
the 4 ADR files under `docs/architecture/adr/` exist. This plan implements
the spec's first two increments in full (0.1.0 skeleton, 0.2.0 architecture
nav) and scaffolds the third (0.3.0 code reference wiring), per the user's
choice. `src/` does not exist yet (the app itself is unimplemented), so the
0.3.0 reference section will build but render empty until app code lands —
that's expected and not a blocker; `journal/` stays excluded per the spec
(depends on `services/events.changelog()`, which ships with the app's own
0.5.0 increment). `1.0.0` (README links to a fully populated four-pillar
site) is out of scope for this pass since the reference pillar has nothing
to show yet.

## Approach

### 1. Dev dependencies

```bash
uv add --dev mkdocs mkdocs-material "mkdocstrings[python]" mkdocs-gen-files mkdocs-literate-nav
```
Updates `pyproject.toml` and `uv.lock`.

### 2. `.gitignore` (new, repo root)

No `.gitignore` exists at all today. Add one covering `site/` (mkdocs build
output — spec §6 says "not committed"), plus the standard Python/uv set:
`.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`.

### 3. `mkdocs.yml` (new, repo root)

- `site_name: Milestone`, Material theme.
- `markdown_extensions: pymdownx.superfences` configured with the standard
  Mermaid custom fence (Material's documented recipe) so `overview.md`'s
  diagrams render.
- Explicit `nav:` entries for `index.md`, `architecture/overview.md`, and
  the 4 files under `architecture/adr/` — ADRs are few and added rarely
  (ADR-D3: one canonical file per decision), so a static nav list is
  simpler than generating one; a new ADR needs one added nav line.
- `plugins: gen-files` (runs `scripts/gen_ref_nav.py`), `literate-nav` (nav
  file `SUMMARY.md`, scoped to `reference/`), `mkdocstrings` (python
  handler) — this is the 0.3.0 wiring (ADR-D2: `reference/` generated,
  never hand-written).

### 4. `docs/index.md` (new)

Summary cards linking to Architecture (overview + ADRs) and Reference, per
spec §11's "cartes de résumé vers chaque section".

### 5. `docs/architecture/overview.md` (new)

Two Mermaid diagrams, built from the domain model already documented in
root `CLAUDE.md` — nothing new to design:
- **ER diagram**: `Project ||--o{ Version`, `Project ||--o{ Task`,
  `Version ||--o{ Task` (the last two optional, reflecting nullable
  `project_id`/`version_id` — the GTD mechanism, not an edge case).
- **State diagram**: `inbox → refined → planned → doing ↔ waiting → done`,
  plus a `someday` branch.

### 6. `scripts/gen_ref_nav.py` (new)

Standard `mkdocs-gen-files` + `mkdocs-literate-nav` recipe (the canonical
pattern from the mkdocstrings docs): walk `src/` for `*.py`, write one
generated page per module with a `::: module.path` mkdocstrings directive,
and build `reference/SUMMARY.md`. Must handle the current zero-module case
gracefully (write an empty `SUMMARY.md`, don't error) since `src/` doesn't
exist yet — the reference nav will legitimately be empty until the app is
implemented.

## Files to change

- `pyproject.toml`, `uv.lock` — dev deps (via `uv add --dev`)
- New: `.gitignore`
- New: `mkdocs.yml`
- New: `docs/index.md`
- New: `docs/architecture/overview.md`
- New: `scripts/gen_ref_nav.py`
- New: `artifacts/plans/documentation-v0-implementation.md` — a copy of
  this plan, per CLAUDE.md's rule that Claude-generated artifacts live
  under `artifacts/`

Not touched: `docs/architecture/adr/*.md` (already correct), `README.md`
(1.0.0 concern, out of scope), anything under `src/` (doesn't exist yet).

## Verification

- `uv run mkdocs build` succeeds with no errors/warnings about missing
  nav targets, despite `reference/` being empty.
- `uv run mkdocs serve` and check in a browser: homepage renders, both
  Mermaid diagrams render on the overview page, all 4 ADR pages are
  reachable from nav, Reference section exists (empty is expected).
- `git status` confirms `site/` is not tracked after a build.
