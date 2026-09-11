# CLAUDE.md

The file provides guidance to Claude code (claude.ai/code) when working in this repository.

Always respond write code or documents in english.

Keep your replies extremely concise and focus on conveying the key information. No unnecessary fluff, no long code snippets. 

All the artifacts generate by claude goes into @artifacts.

The source of truth is written in the documentation @docs. For each task keep the documentations in @docs updated.

## Nexus

The project nexus is a local webhost application to manage project.

## Project state

This repository currently contains only a project skeleton (`main.py` is a
placeholder) and a full technical specification for the application to be
built, "Milestone" — a single-user, GTD-inspired project manager served as a
local web app.

## Documentations

When you need to document something ask the agent docs-manager to do it. 

## Commands

The project uses `uv` for dependency management (Python >= 3.12).

```bash
uv sync              # install dependencies from pyproject.toml / uv.lock
uv run main.py       # run the current entry point
```

No test runner, linter, or Flask app factory exists yet — they will be
introduced as implementation proceeds per the spec's increment plan (see
`documents/specs/milestone-app-v1.md` §9 for the target tree and §10 for the
testing strategy).

## Architecture

Architecture is documented, not duplicated here — use the `docs-manager`
agent to read `docs/architecture/` (overview + ADRs) before making any
change that touches layering, the stack, the event log, network binding,
or the domain model. Keep those docs updated via the same agent once the
change is made.
