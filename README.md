# Nexus

A single-user, GTD-inspired project manager served as a local web app.

## Requirements

- Python >= 3.12
- [`uv`](https://docs.astral.sh/uv/) for dependency management

## Development

```bash
uv sync                                          # install dependencies from pyproject.toml / uv.lock
NEXUS_DATABASE_URL=sqlite:///instance/nexus.db \
  FLASK_APP=src.app:create_app uv run flask run  # dev server on port 5000, scratch database
uv run pytest                                    # run the test suite
```

Without `NEXUS_DATABASE_URL`, `flask run` uses the real database in
`~/.nexus/`. Migrations are applied automatically at startup.

## Running as a service

The app listens on `http://127.0.0.1:8765` and nowhere else: it has no
authentication, so the address cannot be changed.

```bash
uv run python -m src.main                          # run in the foreground
uv run python scripts/install_service.py install   # start automatically when your session opens
uv run python scripts/install_service.py uninstall # stop and remove the service (data is kept)
```

| System | What `install` creates |
|---|---|
| Linux | systemd user unit `~/.config/systemd/user/nexus.service` (`Restart=on-failure`) |
| macOS | launchd agent `~/Library/LaunchAgents/com.nexus.app.plist` (`KeepAlive`) |
| Windows | scheduled task `nexus`, at logon, restarted up to 3 times on failure |

Only Linux has been verified on a real machine. The macOS and Windows
definitions are generated and unit-tested but have not been run: expect to
adjust them. On Windows, `NEXUS_HOME` is not carried into the task.

The service starts when you log in. To start it at boot without anyone
logging in (Linux), run once:

```bash
loginctl enable-linger
```

Manage it with `systemctl --user status nexus`, `restart nexus`, `stop nexus`.

## Configuration

Environment variables, all optional (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `NEXUS_HOME` | `~/.nexus` | Folder for the database, log and backups |
| `NEXUS_DATABASE_URL` | `sqlite:///<NEXUS_HOME>/data.db` | Full database URL, overrides the default file |
| `NEXUS_PORT` | `8765` | Port to listen on |
| `NEXUS_SECRET_KEY` | `dev` | Flask signing key |

## Data, logs and backups

Everything lives in `NEXUS_HOME` (`~/.nexus` by default):

| Path | Content |
|---|---|
| `data.db` | The SQLite database (WAL mode, so `data.db-wal` and `data.db-shm` sit beside it) |
| `app.log` | Application log, rotated at 1 MB, 5 old files kept. Also in `journalctl --user -u nexus` on Linux |
| `backups/` | `data-YYYYmmdd-HHMMSS.db`, one per start, the 14 newest kept |

A backup is taken each time the app starts, before migrations are applied,
so a bad upgrade can always be undone. Backups happen **only at startup**: a
machine that stays up for weeks gets no new snapshot in between. For a copy
at any time, download `http://127.0.0.1:8765/export.json` (the whole
database as JSON; each version's `definition_of_done` is a list of
`{"description", "done"}` objects).

### Restore a backup

```bash
systemctl --user stop nexus                      # or stop the foreground process
cp ~/.nexus/backups/data-YYYYmmdd-HHMMSS.db ~/.nexus/data.db
rm -f ~/.nexus/data.db-wal ~/.nexus/data.db-shm  # leftovers of the replaced database
systemctl --user start nexus                     # pending migrations are applied on start
```

### Move data from the development database

Data created before `~/.nexus` existed lives in `instance/nexus.db`. With no
server running:

```bash
mkdir -p ~/.nexus && cp instance/nexus.db ~/.nexus/data.db
```

## Documentation

`docs/` is the source of truth (architecture, ADRs, functional mockups,
reference). Build/serve it locally:

```bash
uv run mkdocs serve
```
