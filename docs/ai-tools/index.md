# AI tools

How Claude Code is set up to work on this repository. The full
description, in French, is in the Concept map
(`docs/concept/nexus/outils-ia/`).

## CLAUDE.md files

Instructions that load automatically into context, scoped by directory:

- `CLAUDE.md` (root) — project state, languages, commands, where the
  documentation lives.
- `docs/CLAUDE.md` — rules for editing the documentation tree (`concept/`,
  `python/`, `ai-tools/`, generated `reference/`).

## Project agents (`.claude/agents/`)

| Agent | Purpose |
| --- | --- |
| `docs-manager` | Keeps `docs/`: the Concept map (French cards, via the global Concept skills) and the MkDocs site (English). Reads it for context before changes, updates it after a task, runs the card check and `mkdocs build --strict`, reports screenshots to retake. Never hand-writes `docs/reference/`. |
| `git-manager` | Reviews, stages and commits changes, local branching/merging/rebasing. Asks before any push; never force-pushes or skips hooks. |

## Project skill (`.claude/skills/`)

- `revision` — corrects an error or outdated statement in an artifact
  under `artifacts/` (spec, plan).

## Global tools shipped by Nexus (`outils_ai/`)

Tools meant for all of David's projects, deployed into `~/.claude`
(same layout as the Concept project).

- `agents/nexus_agt.md` — French project-management agent working through
  the Nexus MCP server. Triages the inbox, splits a request into a feature
  and sized tasks, tracks progress (states, closing a feature, proposing
  archiving) and reports status (version, remaining criteria, DOING/WAITING,
  INBOX, next task). It reads and writes items only; criteria, projects,
  deletion, import and major releases stay with David. It proposes a list of
  changes and writes only when the prompt says « applique », so it can be
  used anywhere without surprise writes.
- `deployer.sh [--essai]` — symlinks `skills/<name>` to
  `~/.claude/skills/<name>` and `agents/<name>.md` to
  `~/.claude/agents/<name>.md`. Never replaces anything that is not a link
  to the repository; removes dead links to it. `--essai` is a dry run;
  `CLAUDE_DIR` overrides `~/.claude` for testing. Rerun only for a new or
  removed agent/skill; an agent loads when a Claude Code session starts.

## Global tools used for the Concept map

The Concept skills (`ecrire-fiche`, `dessiner-schema`, `verifier-fiches`,
`planifier-carte`) are global, not part of this repository. `docs-manager`
follows them to keep the map in `docs/concept/`; the global `documentaliste`
agent was used to write it first.

## Conventions

- **Source of truth is `docs/`**: the Concept map for the project, MkDocs
  for the code. `artifacts/specs/` is background only; on conflict `docs/`
  wins.
- **Decisions live in the Concept card of their part**, with their reason.
  When one changes, the card is rewritten; git keeps the history. There are
  no ADR files.
- **Generated artifacts** (specs, plans) go in `artifacts/`.
- **`docs/reference/`** is generated at build time from `src/` docstrings —
  never hand-edited.
- Every task that changes behavior updates `docs/` in the same pass.
