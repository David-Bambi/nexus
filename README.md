# Nexus

A single-user, GTD-inspired project manager served as a local web app.

## Requirements

- Python >= 3.12
- [`uv`](https://docs.astral.sh/uv/) for dependency management

## Setup

```bash
uv sync              # install dependencies from pyproject.toml / uv.lock
uv run main.py       # run the current entry point
```

## Documentation

`docs/` is the source of truth (architecture, ADRs, functional mockups,
reference). Build/serve it locally:

```bash
uv run mkdocs serve
```
