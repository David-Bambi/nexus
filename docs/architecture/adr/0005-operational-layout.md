---
status: accepted
date: 2026-09-20
---

# 0005 — Operational layout

## Status

Accepted

## Decision

- **Data directory**: `~/.nexus`, overridable with `NEXUS_HOME`. It holds
  `data.db`, `app.log` and `backups/`. This deliberately differs from the
  spec's `~/.milestone`: code, environment variables and docs all say Nexus.
- **Production entry point**: `python -m src.main`, served by waitress (pure
  Python, cross-platform, no build step). `flask run` stays the dev path.
- **WAL**: enabled by a SQLAlchemy `connect` listener (`db.get_engine`), for
  file-based SQLite only.
- **Backups**: SQLite's online backup API, not a file copy (a copy can miss
  the `-wal` file). Taken at startup **before** migrations, so a bad
  migration always has a pre-upgrade snapshot. The 14 newest are kept as
  `data-YYYYmmdd-HHMMSS.db`; other files in the folder are never pruned. A
  failed backup is logged and startup continues.
- **Logging**: one rotating file (1 MB x 5 files) plus stderr, both on the
  root logger so the app, Flask and waitress log alike. Migrations don't
  reconfigure logging: `migrations/env.py` skips alembic's `fileConfig` when
  the app runs them (`configure_logger=False`), which would otherwise replace
  the app's handlers. `env.py` also keeps a URL already set by the caller
  (`create_app` passes its own).
- **Database folder**: `create_app` creates the parent folder of a file-based
  SQLite database.
- **Autostart**: `scripts/install_service.py` installs a systemd user unit
  (`Restart=on-failure`), a launchd agent, or a Windows scheduled task (XML).
  Command: `uv run --frozen --directory <repo> python -m src.main`. Usage
  and environment variables are in the repository's `README.md`.
- **Deploy**: `scripts/deploy.sh [--force]` updates the systemd user service
  from the current checkout: it refuses a dirty git tree (unless `--force`),
  runs `pytest -q` and `uv sync --frozen`, restarts `nexus`, then polls
  `http://127.0.0.1:8765/` for up to 20 s (last 20 journal lines on failure).
  The pre-migration backup is the one taken on start, not a separate step.
  The service name and URL are hardcoded, so a custom `NEXUS_PORT` makes the
  check time out.

See [overview](../overview.md#startup-sequence) for the startup order.

## Why

A single-user app on a personal machine must survive restarts and bad
upgrades without an admin. Each piece is the smallest option that needs no
extra service or build step.

## Consequences and known limits

- Backups happen only at startup: a machine that stays up gets none in
  between. `/export.json` is the on-demand copy.
- A crash loop takes one backup per restart and could push older ones out of
  the 14 kept. systemd's start limit bounds this.
- Linux is verified live: install, `kill -9` of the server and of `uv` both
  restarted by systemd, one backup per restart. Reboot-at-boot was verified
  on 2026-09-20 with linger enabled: after a reboot, `nexus.service` was
  active with no manual action (0 restarts), `GET /` returned 200 on
  `127.0.0.1:8765`, and that boot created a startup backup. The 1.0.0
  definition of done (available unattended after a reboot) therefore holds
  on Linux. macOS and Windows definitions are only unit-tested.
- List pages `/search`, `/refine`, `/tasks` are capped at `PAGE_LIMIT = 100`
  rows with a note when cut (`views.search`, `views.to_refine`, `tasks.list`
  take an optional `limit`). The export loads tags and criteria in bulk
  (10 025 -> 26 queries).

## Measured performance

Synthetic database of 10 000 tasks and 34 000 events, target < 100 ms per
page. All pages meet it except two accepted gaps:

- Version detail page: 110-295 ms (renders the whole changelog, ~265 tasks).
- `/export.json`: 5-8 s (ORM object creation for 44 000 rows plus a 13 MB
  JSON). Raw-row reads would cut it several times.
